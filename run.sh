#!/bin/bash
# Launch the spoken-English tutor (Sarvam STT + LLM + TTS) from its .env.
set -euo pipefail
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
if [ -z "${SARVAM_API_KEY:-}" ]; then
  echo "SARVAM_API_KEY missing — put it in .env (get one at https://dashboard.sarvam.ai)" >&2
  exit 1
fi
exec .venv/bin/python server.py
