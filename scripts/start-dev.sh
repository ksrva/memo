#!/usr/bin/env bash
# Start the Memo backend for local development.
set -euo pipefail

cd "$(dirname "$0")/.."
VENV="backend/.venv"

if [ ! -d "$VENV" ]; then
  echo "Creating virtualenv..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r backend/requirements.txt
fi

cd backend
exec "../$VENV/bin/python" -m uvicorn app.main:app --reload --port "${PORT:-8000}"
