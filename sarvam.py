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
import wave

import requests

BASE = "https://api.sarvam.ai"
STT_MODEL = "saaras:v3"
STT_MODE = "transcribe"  # keep the learner's own words (Hindi/Hinglish) as spoken
TTS_MODEL = "bulbul:v3"
TTS_SPEAKER = "shreya"
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


# ── STT: Sarvam Saaras v3 ─────────────────────────────────────────────────

def transcribe(audio_path: str) -> str:
    """Speech → text. Handles long recordings by chunking under 30 s."""
    wav = to_wav_16k(audio_path)
    texts = []
    for chunk in _wav_chunks(wav):
        with open(chunk, "rb") as f:
            r = requests.post(
                BASE + "/speech-to-text",
                headers=_speech_headers(),
                files={"file": ("speech.wav", f, "audio/wav")},
                data={"model": STT_MODEL, "mode": STT_MODE},
                timeout=60,
            )
        r.raise_for_status()
        texts.append((r.json().get("transcript") or "").strip())
    return " ".join(t for t in texts if t).strip()


# ── chat: Sarvam sarvam-105b-conversations ────────────────────────────────

def chat(messages: list[dict], temperature: float = 0.4, max_tokens: int = 700) -> str:
    """Chat completion. The -conversations variant puts the answer in `content`
    (the base sarvam-105b is a reasoning model that hides it in
    `reasoning_content`)."""
    r = requests.post(
        BASE + "/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key()}",
                 "Content-Type": "application/json"},
        json={"model": CHAT_MODEL, "messages": messages,
              "temperature": temperature, "max_tokens": max_tokens},
        timeout=120,
    )
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    return (msg.get("content") or "").strip()


# ── TTS: Sarvam Bulbul v3 ─────────────────────────────────────────────────

def _speak_once(text: str, language_code: str) -> bytes:
    r = requests.post(
        BASE + "/text-to-speech",
        headers=_speech_headers(),
        json={"text": text, "language_code": language_code,
              "speaker": TTS_SPEAKER, "model": TTS_MODEL},
        timeout=120,
    )
    r.raise_for_status()
    audios = r.json().get("audios") or []
    if not audios:
        raise RuntimeError("Sarvam TTS returned no audio")
    return base64.b64decode(audios[0])


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


def speak(text: str, language_code: str = "en-IN") -> str:
    """Text → speech. Returns the path of a WAV file ready to play."""
    chunks = []
    for part in _split_for_tts(text):
        chunks.append(_speak_once(part, language_code))
    data = concat_wavs(chunks)
    out = tempfile.mktemp(suffix=".wav", prefix="tutor_out_")
    with open(out, "wb") as f:
        f.write(data)
    return out


def speak_mixed(segments: list[tuple[str, str]]) -> str:
    """Speak [(language_code, text), …] in order as one continuous audio file."""
    chunks = [_speak_once(text, lang) for lang, text in segments if text.strip()]
    if not chunks:
        raise RuntimeError("nothing to speak")
    data = concat_wavs(chunks)
    out = tempfile.mktemp(suffix=".wav", prefix="tutor_out_")
    with open(out, "wb") as f:
        f.write(data)
    return out
