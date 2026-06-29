#!/usr/bin/env bash
# Local dev launcher: sets up a venv, installs deps, starts the dashboard.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  echo "Creating virtualenv…"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  echo "No .env found — copying .env.example (runs fine with zero keys)."
  cp .env.example .env
fi

echo "FlowScope -> http://localhost:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
