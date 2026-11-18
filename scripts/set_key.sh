#!/bin/bash
# Prompt for a Sarvam API key (hidden input) and save it to ../.env
set -euo pipefail
cd "$(dirname "$0")/.."
printf 'Paste Sarvam API key (input hidden): '
read -rs KEY
echo
KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"
if [ -z "$KEY" ]; then echo "empty key — nothing written" >&2; exit 1; fi
umask 077
printf 'SARVAM_API_KEY=%s\n' "$KEY" > .env
echo "saved to $(pwd)/.env (${#KEY} chars)"
