"""Sarvam AI clients — STT (Saaras v3), chat (sarvam-105b-conversations), TTS (Bulbul v3).

Only Sarvam models are used, per the assignment constraint. Auth is the
`api-subscription-key` header for speech endpoints and a Bearer token for the
OpenAI-compatible chat endpoint.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "https://api.sarvam.ai"
STT_MODEL = "saaras:v3"
# mode=codemix, measured: on 6 fresh recordings of a deliberately
# ungrammatical sentence, `transcribe` returned the grammar FIXED in 2
# ("He goes … I went … I am explaining") while `codemix` kept the learner's
# words in all 6 and stayed in Latin script. `verbatim` also keeps the words
# but flips English into Devanagari (ही गो टू स्कूल), which this tutor cannot
# quote and correct. For a grammar tutor the transcript must show the mistake.
STT_MODE = "codemix"
TTS_MODEL = "bulbul:v3"
TTS_SPEAKER = "shreya"   # bulbul:v3 default for this app

# bulbul:v3 ships 37 voices. The picker offers five of them, chosen to span the
# range and described by character instead of by name — the tutor is Priyanka, so
# each option is a voice she can wear, not a different person.
SPEAKERS: list[dict] = [
    {"id": "priya", "label": "Warm female"},
    {"id": "shreya", "label": "Calm female"},
    {"id": "tanya", "label": "Young female"},
    {"id": "rahul", "label": "Professional male"},
    {"id": "vijay", "label": "Mature male"},
]
SPEAKER_IDS = {sp["id"] for sp in SPEAKERS}


def speaker_or_default(name: str | None) -> str:
    """A speaker the API will accept — anything unknown falls back to the default."""
    name = (name or "").strip().lower()
    return name if name in SPEAKER_IDS else TTS_SPEAKER
CHAT_MODEL = "sarvam-105b-conversations"

STT_MAX_SECONDS = 30  # REST endpoint limit
TTS_MAX_CHARS = 450   # keep each synthesis request safely small


def api_key() -> str:
    """SARVAM_API_KEY from the environment, else the local AISHE config."""
    key = os.environ.get("SARVAM_API_KEY", "").strip()
    if key:
        return key
    try:
        import yaml

        cfg = yaml.safe_load(open(os.path.expanduser("~/.config/aishe/config.yaml")))
        key = ((cfg.get("providers") or {}).get("sarvam") or {}).get("api_key", "") or ""
    except Exception:
        key = ""
    if not key:
        raise RuntimeError(
            "Sarvam API key not found. Export SARVAM_API_KEY "
            "(get one at https://dashboard.sarvam.ai)."
        )
    return key


def _speech_headers() -> dict:
    return {"api-subscription-key": api_key()}


# ── audio helpers ──────────────────────────────────────────────────────────

def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _ffprobe_duration(path: str) -> float:
    ff = shutil.which("ffprobe")
    if not ff:
        return 0.0
    out = subprocess.run(
        [ff, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def to_wav_16k(src: str) -> str:
    """Normalise a mic recording (webm/ogg/mp4/…) to 16 kHz mono WAV."""
    ff = _ffmpeg()
    if not ff or src.lower().endswith(".wav"):
        return src
    dst = tempfile.mktemp(suffix=".wav", prefix="tutor_stt_")
    subprocess.run(
        [ff, "-y", "-i", src, "-ac", "1", "-ar", "16000", dst],
        check=True, capture_output=True,
    )
    return dst


def _wav_chunks(path: str) -> list[str]:
    """Split a long recording into pieces under the 30 s endpoint limit."""
    dur = _ffprobe_duration(path)
    if dur and dur <= STT_MAX_SECONDS:
        return [path]
    ff = _ffmpeg()
    if not ff:
        return [path]
    pattern = tempfile.mktemp(suffix="_%03d.wav", prefix="tutor_chunk_")
    subprocess.run(
        [ff, "-y", "-i", path, "-f", "segment",
         "-segment_time", str(STT_MAX_SECONDS - 2), pattern],
        check=True, capture_output=True,
    )
    import glob

    parts = sorted(glob.glob(pattern.replace("%03d", "*")))
    return parts or [path]


def concat_wavs(wavs: list[bytes]) -> bytes:
    """Join PCM WAV segments (Bulbul always returns 22.05 kHz mono PCM16)."""
    if len(wavs) == 1:
        return wavs[0]
    out = tempfile.mktemp(suffix=".wav", prefix="tutor_tts_")
    with wave.open(out, "wb") as w:
        w.setparams(wave.open(__import__("io").BytesIO(wavs[0]), "rb").getparams())
        for data in wavs:
            with wave.open(__import__("io").BytesIO(data), "rb") as r:
                w.writeframes(r.readframes(r.getnframes()))
    with open(out, "rb") as f:
        return f.read()


def _post(url: str, *, attempts: int = 4, backoff=(2.0, 5.0, 10.0),
          retry_on=(429,), **kwargs) -> requests.Response:
    """POST with backoff on 429/5xx — Sarvam rate-limits bursts of STT calls.

    `retry_on` adds statuses worth retrying: Saaras answers 400 when it cannot
    read the audio file (its body says so) and 429 when you burst it, and both
    clear once the payload is fixed or the window passes.
    """
    last: Exception | None = None
    body = ""
    for i in range(attempts):
        try:
            r = requests.post(url, **kwargs)
            if r is None:  # requests never returns None; keeps the type checker quiet
                raise RuntimeError("requests returned no response")
        except requests.RequestException as e:
            last = e
        else:
            if r.status_code in retry_on or r.status_code >= 500:
                last = RuntimeError(f"HTTP {r.status_code}")
                body = (r.text or "")[:300]     # Sarvam says why in the body
            else:
                r.raise_for_status()
                return r
        if i < attempts - 1:
            time.sleep(backoff[min(i, len(backoff) - 1)])
    raise RuntimeError(
        f"Sarvam gave up after {attempts} attempts: {last} :: {body}") from last


# ── STT: Sarvam Saaras v3 ─────────────────────────────────────────────────

def transcribe(audio_path: str) -> str:
    """Speech → text. Handles long recordings by chunking under 30 s.

    Every file this creates (the 16 kHz conversion and any 28 s chunks) is
    removed afterwards — without this each turn leaves bytes in the temp dir
    for as long as the OS takes to notice.
    """
    wav = to_wav_16k(audio_path)
    created: list[str] = []
    try:
        texts = []
        for chunk in _wav_chunks(wav):
            if chunk != audio_path:
                created.append(chunk)
            with open(chunk, "rb") as f:
                r = _post(
                    BASE + "/speech-to-text",
                    headers=_speech_headers(),
                    files={"file": ("speech.wav", f, "audio/wav")},
                    data={"model": STT_MODEL, "mode": STT_MODE},
                    timeout=60,
                    attempts=7, backoff=(2.0, 4.0, 8.0, 15.0, 30.0, 45.0),
                    retry_on=(400, 429),
                )
            texts.append((r.json().get("transcript") or "").strip())
        return " ".join(t for t in texts if t).strip()
    finally:
        for path in dict.fromkeys(created):   # dedupe, keep order
            try:
                os.unlink(path)
            except OSError:
                pass


# ── chat: Sarvam sarvam-105b-conversations ────────────────────────────────

def chat(messages: list[dict], temperature: float = 0.4, max_tokens: int = 700) -> str:
    """Chat completion. The -conversations variant puts the answer in `content`
    (the base sarvam-105b is a reasoning model that hides it in
    `reasoning_content`)."""
    r = _post(
        BASE + "/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key()}",
                 "Content-Type": "application/json"},
        json={"model": CHAT_MODEL, "messages": messages,
              "temperature": temperature, "max_tokens": max_tokens},
        timeout=120,
        attempts=3, backoff=(2.0, 5.0),
    )
    msg = r.json()["choices"][0]["message"]
    return (msg.get("content") or "").strip()


# ── TTS: Sarvam Bulbul v3 ─────────────────────────────────────────────────

def _speak_once(text: str, language_code: str,
                speaker: str = TTS_SPEAKER) -> bytes:
    """One synthesis call, retried once — a hung request would stall the reply."""
    body = {"text": text, "language_code": language_code,
            "speaker": speaker_or_default(speaker), "model": TTS_MODEL}
    audio = b""
    for attempt in (1, 2):
        try:
            r = requests.post(BASE + "/text-to-speech", headers=_speech_headers(),
                              json=body, timeout=60)
            if r.status_code >= 500 or r.status_code == 429:
                raise RuntimeError(f"Sarvam TTS HTTP {r.status_code}")
            r.raise_for_status()
            audios = r.json().get("audios") or []
            if not audios:
                raise RuntimeError("Sarvam TTS returned no audio")
            audio = base64.b64decode(audios[0])
            break
        except (requests.RequestException, RuntimeError) as e:
            if attempt == 2:
                raise RuntimeError(f"Sarvam TTS failed twice: {e}") from e
            time.sleep(0.5)
    if not audio:
        raise RuntimeError("Sarvam TTS returned no audio")
    return audio


def _split_for_tts(text: str) -> list[str]:
    """Break long text at sentence boundaries under TTS_MAX_CHARS."""
    if len(text) <= TTS_MAX_CHARS:
        return [text]
    parts, buf = [], ""
    for sent in text.replace("\n", " ").split(". "):
        cand = (buf + ". " + sent).strip() if buf else sent
        if len(cand) > TTS_MAX_CHARS and buf:
            parts.append(buf)
            buf = sent
        else:
            buf = cand
    if buf:
        parts.append(buf.rstrip("."))
    return parts


def normalize_wav(path: str) -> str:
    """Re-encode to 16 kHz mono PCM16 — the format Saaras always accepts.

    Bulbul does not return the same format on every call (22.05 kHz today,
    something else tomorrow), and Saaras answers HTTP 400 "Failed to read the
    file" for the ones it does not recognise. ffmpeg makes it deterministic.
    """
    ff = shutil.which("ffmpeg")
    if not ff:
        return path
    dst = path + ".16k.wav"
    try:
        subprocess.run([ff, "-y", "-i", path, "-ac", "1", "-ar", "16000",
                        "-c:a", "pcm_s16le", dst],
                       check=True, capture_output=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        return path
    if os.path.getsize(dst) < 4000:     # conversion produced nothing useful
        return path
    os.replace(dst, path)
    return path


def speak(text: str, language_code: str = "en-IN",
          speaker: str = TTS_SPEAKER) -> str:
    """Text → speech. Returns the path of a WAV file ready to play.

    Sarvam occasionally answers a rate-limited request with blank audio. That
    file would be rejected by STT with HTTP 400 for ever, so it is rebuilt
    instead of being handed on.
    """
    for attempt in range(3):
        chunks = [_speak_once(part, language_code, speaker)
                  for part in _split_for_tts(text)]
        data = concat_wavs(chunks)
        if len(data) >= 4000:          # ~0.1s of 16-bit audio — blank otherwise
            break
        time.sleep(1.0 + attempt)
    else:
        raise RuntimeError("Sarvam TTS returned blank audio three times in a row")
    out = tempfile.mktemp(suffix=".wav", prefix="tutor_out_")
    with open(out, "wb") as f:
        f.write(data)
    return normalize_wav(out)


def _merge_segments(segments: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Join neighbouring segments that share a language — one TTS call each."""
    merged: list[tuple[str, str]] = []
    for lang, text in segments:
        text = (text or "").strip()
        if not text:
            continue
        if merged and merged[-1][0] == lang:
            merged[-1] = (lang, f"{merged[-1][1]} {text}")
        else:
            merged.append((lang, text))
    return merged


def speak_mixed(segments: list[tuple[str, str]],
                speaker: str = TTS_SPEAKER) -> str:
    """Speak [(language_code, text), …] in order as one continuous audio file.

    The segments are independent, so they are synthesised in parallel and
    stitched back in the order they were written — a Hindi sentence plus its
    English correction costs about the slowest segment, not the sum.
    """
    jobs = [(lang, part)
            for lang, text in _merge_segments(segments)
            for part in _split_for_tts(text)]
    if not jobs:
        raise RuntimeError("nothing to speak")

    chunks: list[bytes | None] = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=min(6, len(jobs))) as pool:
        futures = [pool.submit(_speak_once, text, lang, speaker)
                   for lang, text in jobs]
        for i, fut in enumerate(futures):
            chunks[i] = fut.result()  # re-raises the first real failure
    data = concat_wavs([c for c in chunks if c])
    if len(data) < 4000:        # blank TTS answer — never hand that to STT
        raise RuntimeError("Sarvam TTS returned blank audio")
    out = tempfile.mktemp(suffix=".wav", prefix="tutor_out_")
    with open(out, "wb") as f:
        f.write(data)
    return normalize_wav(out)
