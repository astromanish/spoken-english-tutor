"""Web UI for the spoken-English tutor — stdlib HTTP server, no framework.

The browser side is plain HTML/CSS/JS in `static/`; all tutor logic stays in
`tutor.py` / `sarvam.py`. Audio goes up as the raw request body, replies come
back as JSON with a URL to the synthesised WAV.

Live transcription has its own three endpoints (`/api/stream/*`), which relay
raw PCM through `realtime.py` to Sarvam's realtime websocket.

Run:  python server.py   →   http://127.0.0.1:7860
"""

from __future__ import annotations

import json
import mimetypes
import os
import tempfile
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import realtime
from tutor import LEVELS, TOPICS, Tutor

HOST = os.environ.get("TUTOR_HOST", "127.0.0.1")
PORT = int(os.environ.get("TUTOR_PORT", "7860"))

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

AUDIO_SUFFIX = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}

# One learner at a time: the session lives in memory behind a lock.
_lock = threading.Lock()
_state: dict[str, Tutor | None] = {"tutor": None}
_audio: dict[str, bytes] = {}
_audio_order: list[str] = []
MAX_AUDIO = 30

# Live-transcription sessions, one per microphone recording.
_streams: dict[str, "realtime.StreamSession"] = {}
MAX_STREAMS = 4


def remember_audio(data: bytes) -> str:
    token = uuid.uuid4().hex
    _audio[token] = data
    _audio_order.append(token)
    while len(_audio_order) > MAX_AUDIO:
        _audio.pop(_audio_order.pop(0), None)
    return token


class Handler(BaseHTTPRequestHandler):
    server_version = "TutorHTTP/1.0"

    def log_message(self, fmt, *args):  # keep the console readable
        pass

    # ── GET ───────────────────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._file(os.path.join(STATIC, "index.html"))
        if path.startswith("/static/"):
            return self._file(os.path.join(STATIC, path[len("/static/"):]))
        if path.startswith("/audio/"):
            return self._audio_file(path[len("/audio/"):])
        if path == "/api/meta":
            return self._json({
                "topics": TOPICS,
            })
        self.send_error(HTTPStatus.NOT_FOUND)

    # ── POST ──────────────────────────────────────────────────────────────
    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            if path == "/api/session":
                return self._start()
            if path == "/api/turn":
                return self._turn()
            if path == "/api/summary":
                return self._summary()
            if path == "/api/stream/start":
                return self._stream_start()
            if path.startswith("/api/stream/"):
                return self._stream_route(path)
        except Exception as e:  # surface the real reason to the UI
            return self._json({"error": f"{type(e).__name__}: {e}"},
                              HTTPStatus.INTERNAL_SERVER_ERROR)
        self.send_error(HTTPStatus.NOT_FOUND)

    # ── endpoints ─────────────────────────────────────────────────────────
    def _start(self):
        body = self._body_json()
        topic = body.get("topic") or TOPICS[0]
        if topic not in TOPICS:
            topic = TOPICS[0]

        with _lock:
            # No level picker: the tutor asks his confidence in the first
            # message and sets the correction level from the answer.
            tutor = Tutor(topic=topic)
            _state["tutor"] = tutor
            self._json({
                "greeting": tutor.greeting,
                "level": tutor.level,
                "level_name": LEVELS.get(tutor.level, "?"),
                "awaiting_confidence": tutor.awaiting_confidence,
                "topic": topic,
            })

    def _turn(self):
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        raw = self._body()
        audio_path = None
        text = None

        stt_ms = 0
        if ctype == "application/json":
            try:
                payload = json.loads(raw or b"{}")
                text = (payload.get("text") or "").strip() or None
                stt_ms = int(payload.get("stt_ms") or 0)
            except (ValueError, TypeError, AttributeError):
                return self._json({"error": "Malformed JSON body."},
                                  HTTPStatus.BAD_REQUEST)
            if not text:
                return self._json({"error": "Say something first."},
                                  HTTPStatus.BAD_REQUEST)
        else:
            if not raw:
                return self._json({"error": "Empty recording — try again."},
                                  HTTPStatus.BAD_REQUEST)
            suffix = AUDIO_SUFFIX.get(ctype, ".webm")
            fd, audio_path = tempfile.mkstemp(suffix=suffix, prefix="tutor_in_")
            with os.fdopen(fd, "wb") as f:
                f.write(raw)

        with _lock:
            tutor = _state["tutor"]
            if tutor is None:
                return self._json({"error": "Press Start first."},
                                  HTTPStatus.CONFLICT)
            turn = tutor.turn(audio_path=audio_path, text=text, stt_ms=stt_ms)
            with open(turn.audio_path, "rb") as f:
                token = remember_audio(f.read())
            self._json({
                "heard": turn.heard,
                "reply": turn.spoken_text,
                "level": turn.level,
                "level_name": LEVELS.get(turn.level, "?"),
                "awaiting_confidence": tutor.awaiting_confidence,
                "audio": f"/audio/{token}.wav",
                "timings": {
                    "stt": turn.ms_stt,
                    "llm": turn.ms_llm,
                    "tts": turn.ms_tts,
                    "total": turn.ms_total,
                },
            })

    def _summary(self):
        with _lock:
            tutor = _state["tutor"]
            if tutor is None:
                return self._json({"error": "No active session."},
                                  HTTPStatus.CONFLICT)
            self._json({"markdown": tutor.summary()})

    # ── live transcription (relayed to Sarvam's realtime websocket) ───────
    def _stream_start(self):
        with _lock:
            # drop finished or abandoned recordings so the slot count stays honest
            for sid in [k for k, s in _streams.items() if s.closed or s.age > 600]:
                _streams.pop(sid, None)
            if len(_streams) >= MAX_STREAMS:
                return self._json({"error": "Too many recordings open — "
                                            "reload the page."},
                                  HTTPStatus.TOO_MANY_REQUESTS)
            session = realtime.StreamSession()
            session.start()
            _streams[session.id] = session
        self._json({"id": session.id})

    def _stream_route(self, path: str):
        parts = [p for p in path.split("/") if p]  # api, stream, <id>, <action>
        if len(parts) != 4:
            return self.send_error(HTTPStatus.NOT_FOUND)
        token, action = parts[2], parts[3]
        with _lock:
            session = _streams.get(token)
        if session is None:
            return self._json({"error": "Recording session expired."},
                              HTTPStatus.GONE)

        if action == "audio":
            pcm = self._body()
            if not pcm:
                return self._json(session.snapshot())
            return self._json(session.feed(pcm))

        if action == "stop":
            result = session.stop()
            with _lock:
                _streams.pop(token, None)
            return self._json(result)

        self.send_error(HTTPStatus.NOT_FOUND)

    # ── plumbing ──────────────────────────────────────────────────────────
    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _body_json(self) -> dict:
        raw = self._body()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            return {}

    def _json(self, obj, status: int = HTTPStatus.OK):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: str):
        real = os.path.realpath(path)
        if not real.startswith(STATIC + os.sep) or not os.path.isfile(real):
            return self.send_error(HTTPStatus.NOT_FOUND)
        ctype = mimetypes.guess_type(real)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "text/javascript"):
            ctype += "; charset=utf-8"
        self._send_bytes(open(real, "rb").read(), ctype)

    def _audio_file(self, name: str):
        token = name.split(".")[0]
        data = _audio.get(token)
        if not data:
            return self.send_error(HTTPStatus.NOT_FOUND)
        self._send_bytes(data, "audio/wav")

    def _send_bytes(self, data: bytes, ctype: str):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Spoken English Tutor → http://{HOST}:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
