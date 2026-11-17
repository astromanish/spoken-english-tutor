"""Live transcription bridge for Sarvam's realtime speech-to-text websocket.

One `StreamSession` per microphone recording. The browser posts raw PCM16
16 kHz chunks over plain HTTP; this module keeps a single websocket to
`saaras:v3-realtime` alive on a background asyncio loop and hands back the
partial transcripts as they arrive. The API key stays on the server — the
browser never sees it, and the UI needs no websocket of its own.

Protocol notes (verified against the live API):
  → {"event": "audio_input", "audio": "<base64 linear16 pcm>"}
  ← {"event": "transcript.partial", "utterance_idx": 0, "text": "...", "language": "en-IN"}
  ← {"event": "transcript.final",   "utterance_idx": 0, "text": "...", ...}
The server VAD needs ~1 s of trailing silence before it emits the final
transcript, so `stop()` feeds a quiet tail and waits for it.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
import uuid

import websockets

import sarvam

URL = "wss://api.sarvam.ai/speech-to-text-realtime/ws"
MODEL = "saaras:v3-realtime"
SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2  # linear16, mono

TRAILING_SILENCE_S = 1.6
FINAL_TIMEOUT_S = 6.0
SILENCE_SLICE = 16000 * 2 * 250 // 1000  # 250 ms
MAX_FRAME = 16000 * 2 * 500 // 1000      # 500 ms — API caps a frame at ~1 s

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """One asyncio loop for every session, in a daemon thread."""
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is None:
            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, name="sarvam-stt",
                             daemon=True).start()
            _loop = loop
        return _loop


class StreamSession:
    """A single recording: audio in over HTTP, partial text out."""

    def __init__(self) -> None:
        self.id = uuid.uuid4().hex
        self._lock = threading.Lock()
        self._final: dict[int, str] = {}
        self._partial: dict[int, str] = {}
        self._language = ""
        self._speech = False
        self._error: str | None = None
        self._last_idx = -1
        self._queue: asyncio.Queue | None = None
        self._closed = False
        self._created = time.time()
        self._final_at: float | None = None
        self._speech_end_at: float | None = None
        self._last_feed_at: float | None = None

    # ── lifecycle, called from HTTP handler threads ──────────────────────
    def start(self) -> None:
        self._queue = asyncio.Queue(maxsize=600)
        loop = _ensure_loop()
        loop.call_soon_threadsafe(lambda: loop.create_task(self._run()))

    def feed(self, pcm: bytes) -> dict:
        """Push recorded PCM and return the transcript as it stands now."""
        if self._closed or self._queue is None:
            return self.snapshot()
        if pcm.strip(b"\x00"):  # real audio, not the silence tail
            self._last_feed_at = time.time()
        asyncio.run_coroutine_threadsafe(self._queue.put(pcm), _ensure_loop()).result(
            timeout=15
        )
        return self.snapshot()

    def stop(self) -> dict:
        """End the recording: quiet tail, final transcript, close."""
        if self._closed:
            return self.snapshot()
        t_stop = time.time()

        silence = b"\x00" * SILENCE_SLICE
        for _ in range(int(TRAILING_SILENCE_S * 1000 / 250)):
            self.feed(silence)
            time.sleep(0.01)

        deadline = t_stop + FINAL_TIMEOUT_S
        while time.time() < deadline:
            with self._lock:
                done = self._last_idx >= 0 and self._last_idx in self._final
            if done:
                break
            time.sleep(0.05)

        result = self.snapshot()
        # STT cost = end of speech → final transcript. When the VAD already
        # finalised during the recording this is the real streaming latency,
        # not the time the learner waited after pressing stop.
        anchor = self._speech_end_at or self._last_feed_at or t_stop
        result["stt_ms"] = int(max(0.0, ((self._final_at or time.time()) - anchor) * 1000))
        self.close()
        return result

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._queue is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._queue.put(None), _ensure_loop()
                ).result(timeout=5)
            except Exception:  # loop already gone — nothing to close
                pass

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def age(self) -> float:
        return time.time() - self._created

    def snapshot(self) -> dict:
        with self._lock:
            idxs = sorted(set(self._final) | set(self._partial))
            parts = [(self._final.get(i) or self._partial.get(i) or "").strip()
                     for i in idxs]
            return {
                "text": " ".join(p for p in parts if p).strip(),
                "language": self._language,
                "speech": self._speech,
                "final": bool(self._final) and all(i in self._final for i in idxs),
                "error": self._error,
            }

    # ── asyncio side ─────────────────────────────────────────────────────
    async def _run(self) -> None:
        url = (f"{URL}?language_code=auto&model={MODEL}"
               f"&stream_type=balanced&mode=transcribe")
        try:
            async with websockets.connect(
                url,
                additional_headers={"api-subscription-key": sarvam.api_key()},
                max_size=2 ** 23,
                ping_interval=20,
            ) as ws:
                reader = asyncio.ensure_future(self._read(ws))
                while True:
                    chunk = await self._queue.get()
                    if chunk is None:
                        break
                    # The API rejects frames over ~1 s, and the browser's
                    # buffers can arrive bundled, so always cut them down.
                    for i in range(0, len(chunk), MAX_FRAME):
                        piece = chunk[i:i + MAX_FRAME]
                        if not piece:
                            continue
                        await ws.send(json.dumps({
                            "event": "audio_input",
                            "audio": base64.b64encode(piece).decode(),
                        }))
                reader.cancel()
        except Exception as e:  # reported to the UI, never swallowed
            with self._lock:
                self._error = f"{type(e).__name__}: {e}"
            self._closed = True

    async def _read(self, ws) -> None:
        async for raw in ws:
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            self._handle(event)

    def _handle(self, event: dict) -> None:
        kind = event.get("event") or ""
        idx = int(event.get("utterance_idx") or 0)
        text = (event.get("text") or "").strip()
        with self._lock:
            if event.get("language"):
                self._language = event["language"]
            if kind == "vad.speech_start":
                self._speech = True
            elif kind == "vad.speech_end":
                self._speech_end_at = time.time()
            elif kind == "transcript.partial":
                self._partial[idx] = text
                self._last_idx = max(self._last_idx, idx)
            elif kind == "transcript.final":
                self._final[idx] = text
                self._partial.pop(idx, None)
                self._last_idx = max(self._last_idx, idx)
                self._final_at = time.time()
            elif kind == "error":
                self._error = event.get("message") or str(event)
