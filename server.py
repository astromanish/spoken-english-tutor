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
import sarvam
from tutor import LEVELS, TOPICS, Tutor

# Render/Fly/Railway hand you $PORT and expect 0.0.0.0; locally it stays loopback.
PORT = int(os.environ.get("PORT") or os.environ.get("TUTOR_PORT") or "7860")
HOST = os.environ.get("TUTOR_HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")

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

# Sessions live in memory, one per browser (cookie), behind a lock. In memory is
# fine for a single-process host: the tutor's conversation and its audio die with
# the process, which is exactly what a role-play session wants.
_lock = threading.Lock()
_sessions: dict[str, Tutor] = {}
MAX_SESSIONS = 200
COOKIE = "priyanka_sid"
_audio: dict[str, bytes] = {}
_audio_order: list[str] = []
MAX_AUDIO = 30

# Live-transcription sessions, one per microphone recording.
_streams: dict[str, "realtime.StreamSession"] = {}
MAX_STREAMS = 4


def _unlink(path: str | None) -> None:
    """Best-effort temp cleanup — a missing file is not an error here."""
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


def remember_audio(data: bytes) -> str:
    token = uuid.uuid4().hex
    _audio[token] = data
    _audio_order.append(token)
    while len(_audio_order) > MAX_AUDIO:
        _audio.pop(_audio_order.pop(0), None)
    return token


class Handler(BaseHTTPRequestHandler):
    server_version = "TutorHTTP/1.0"

    # Each browser gets its own tutor: a shared link must not put two visitors in
    # the same conversation.
    sid = ""
    fresh_sid = False

    def _cookie_sid(self) -> None:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and value:
                self.sid = value
                return
        self.sid = uuid.uuid4().hex
        self.fresh_sid = True

    def _session(self) -> Tutor | None:
        with _lock:
            return _sessions.get(self.sid)

    def log_message(self, fmt, *args):  # keep the console readable
        pass

    # ── GET ───────────────────────────────────────────────────────────────
    def do_GET(self):
        self._cookie_sid()
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
                "speakers": sarvam.SPEAKERS,
                "default_speaker": sarvam.TTS_SPEAKER,
            })
        self.send_error(HTTPStatus.NOT_FOUND)

    # ── POST ──────────────────────────────────────────────────────────────
    def do_POST(self):
        self._cookie_sid()
        path = self.path.split("?")[0]
        try:
            if path == "/api/session":
                return self._start()
            if path == "/api/turn":
                return self._turn()
            if path == "/api/summary":
                return self._summary()
            if path == "/api/preview":
                return self._preview()
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
        speaker = sarvam.speaker_or_default(body.get("speaker"))

        with _lock:
            # No level picker: the tutor asks his confidence in the first
            # message and sets the correction level from the answer.
            tutor = Tutor(topic=topic, speaker=speaker)
            _sessions[self.sid] = tutor
            while len(_sessions) > MAX_SESSIONS:      # never grows unbounded
                _sessions.pop(next(iter(_sessions)), None)

            # The first message is spoken, not printed: it is synthesised here
            # so the browser can start the ear and the mouth in the same beat.
            greeting_audio, warning = "", ""
            try:
                path = sarvam.speak_mixed(tutor.greeting_segments, tutor.speaker)
                try:
                    with open(path, "rb") as f:
                        token = remember_audio(f.read())
                finally:
                    _unlink(path)
                greeting_audio = f"/audio/{token}.wav"
            except Exception as e:  # the session still runs, just silently
                warning = f"Greeting could not be spoken: {type(e).__name__}: {e}"

            self._json({
                "greeting": tutor.greeting,
                "audio": greeting_audio,
                "warning": warning,
                "level": tutor.level,
                "level_name": LEVELS.get(tutor.level, "?"),
                "awaiting_confidence": tutor.awaiting_confidence,
                "topic": topic,
                "speaker": tutor.speaker,
            })

    def _turn(self):
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        raw = self._body()
        audio_path = None
        text = None

        stt_ms = 0
        replace = False
        if ctype == "application/json":
            try:
                payload = json.loads(raw or b"{}")
                text = (payload.get("text") or "").strip() or None
                stt_ms = int(payload.get("stt_ms") or 0)
                replace = bool(payload.get("replace_previous"))
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
            tutor = _sessions.get(self.sid)
            if tutor is None:
                return self._json({"error": "Press Start first."},
                                  HTTPStatus.CONFLICT)
            turn = tutor.turn(audio_path=audio_path, text=text, stt_ms=stt_ms,
                              replace_previous=replace)
            # one line per turn, so a merge is visible while testing
            print(f"[turn] replace={replace} heard={turn.heard[:80]!r}", flush=True)
            try:
                with open(turn.audio_path, "rb") as f:
                    token = remember_audio(f.read())
                token2 = ""
                if turn.followup_audio:      # the question, asked separately
                    with open(turn.followup_audio, "rb") as f:
                        token2 = remember_audio(f.read())
            finally:
                _unlink(audio_path)          # the recording — held in memory now
                _unlink(turn.audio_path)     # the reply WAV — read above
                _unlink(turn.followup_audio)
            self._json({
                "heard": turn.heard,
                "reply": turn.spoken_text,
                "reply2": turn.followup_text,
                "level": turn.level,
                "level_name": LEVELS.get(turn.level, "?"),
                "awaiting_confidence": tutor.awaiting_confidence,
                "audio": f"/audio/{token}.wav",
                "audio2": f"/audio/{token2}.wav" if token2 else "",
                "timings": {
                    "stt": turn.ms_stt,
                    "llm": turn.ms_llm,
                    "tts": turn.ms_tts,
                    "total": turn.ms_total,
                },
            })

    # Two lines, so the picker can be judged on English and on Hinglish before
    # a session starts — the voice has to handle both. The name follows the
    # voice: a male speaker introduces himself as Priyank.
    PREVIEW_HINGLISH = "Chaliye shuru karein — aap bas bolna shuru kijiye."
    NAMES = {"female": "Priyanka", "male": "Priyank"}

    def _preview(self):
        speaker = sarvam.speaker_or_default(
            (self._body_json() or {}).get("speaker"))
        name = self.NAMES.get(sarvam.gender_of(speaker), "Priyanka")
        segments = [
            ("en-IN", f"Hi, I am {name}, and I will help you speak English."),
            ("en-IN", self.PREVIEW_HINGLISH),
        ]
        path = sarvam.speak_mixed(segments, speaker)
        try:
            with open(path, "rb") as f:
                token = remember_audio(f.read())
        finally:
            _unlink(path)
        self._json({
            "speaker": speaker,
            "name": name,
            "text": " ".join(text for _, text in segments),
            "audio": f"/audio/{token}.wav",
        })

    def _summary(self):
        with _lock:
            tutor = _sessions.get(self.sid)
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
        if self.fresh_sid:
            self.send_header("Set-Cookie", f"{COOKIE}={self.sid}; Path=/; SameSite=Lax")
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
