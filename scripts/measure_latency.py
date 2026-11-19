#!/usr/bin/env python
"""Measure one live turn, the way the browser does it.

The eval harness (`eval_run.py`) grades correctness over the *batch* path, where the
whole reply WAV is synthesised before it returns — that number is not what a learner
feels. This script drives the same endpoints the page drives and reports the three
things that are actually on screen:

  stt      turn closes -> final transcript            (POST /api/stream/<id>/stop)
  llm      transcript -> reply text + speech segments (POST /api/turn)
  tts      first byte out of /speak/<token>           (the number behind "first sound")

The silence window is deliberately NOT included: it is the learner's pause, not cost.

Usage:
    ./run.sh &                     # server on http://127.0.0.1:7860
    python scripts/measure_latency.py [turns]
"""

from __future__ import annotations

import os
import statistics
import subprocess
import sys
import tempfile
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sarvam  # noqa: E402

BASE = os.environ.get("TUTOR_URL", "http://127.0.0.1:7860")
SAID = "I am go to office yesterday and I am do the work"
TURNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def learner_pcm(text: str) -> bytes:
    """Synthesise a learner sentence and convert it to what the mic sends."""
    wav = sarvam.speak(text, language_code="en-IN")   # a WAV file path
    raw = tempfile.mktemp(suffix=".pcm")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
                        "-ar", "16000", "-ac", "1", "-f", "s16le", raw], check=True)
        with open(raw, "rb") as f:
            return f.read()
    finally:
        for path in (wav, raw):
            try:
                os.unlink(path)
            except OSError:
                pass


def one_turn(s: requests.Session, pcm: bytes) -> dict:
    sid = s.post(f"{BASE}/api/stream/start", timeout=60).json()["id"]
    slice_bytes = 16000 * 2 * 128 // 1000          # 128 ms, the app's block
    for i in range(0, len(pcm), slice_bytes):
        s.post(f"{BASE}/api/stream/{sid}/audio", data=pcm[i:i + slice_bytes],
               headers={"Content-Type": "application/octet-stream"}, timeout=60)
        time.sleep(0.128)                          # real time, like a person talking

    t_stop = time.time()
    final = s.post(f"{BASE}/api/stream/{sid}/stop", timeout=120).json()
    stt_ms = round((time.time() - t_stop) * 1000)

    t_llm = time.time()
    turn = s.post(f"{BASE}/api/turn",
                  json={"text": final.get("text") or "", "stt_ms": stt_ms},
                  timeout=180).json()
    llm_ms = round((time.time() - t_llm) * 1000)

    tts_ms = 0
    if turn.get("audio"):
        t = time.time()
        with s.get(BASE + turn["audio"], stream=True, timeout=120) as r:
            next(r.iter_content(4096))
            tts_ms = round((time.time() - t) * 1000)
            for _ in r.iter_content(65536):        # drain, so the token is spent
                pass
    return {"heard": final.get("text") or "", "stt": stt_ms, "llm": llm_ms,
            "tts": tts_ms, "first_sound": stt_ms + llm_ms + tts_ms}


def main() -> None:
    print(f"measuring {TURNS} turns against {BASE}\n")
    s = requests.Session()
    s.post(f"{BASE}/api/session", json={"topic": "Job interview"}, timeout=120)
    pcm = learner_pcm(SAID)

    rows = []
    for i in range(TURNS):
        row = one_turn(s, pcm)
        rows.append(row)
        print(f"  turn {i + 1}: stt {row['stt']} ms · llm {row['llm']} ms · "
              f"tts {row['tts']} ms · first sound {row['first_sound']} ms")
        print(f"          heard: {row['heard']!r}")

    def avg(k: str) -> int:
        return round(statistics.mean(r[k] for r in rows))

    print(f"\n  average: stt {avg('stt')} · llm {avg('llm')} · tts {avg('tts')} "
          f"· first sound {avg('first_sound')} ms")
    if len(rows) > 1:
        print(f"  spread : first sound {min(r['first_sound'] for r in rows)}–"
              f"{max(r['first_sound'] for r in rows)} ms")


if __name__ == "__main__":
    main()
