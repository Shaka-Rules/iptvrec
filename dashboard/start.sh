#!/usr/bin/env bash
# Start IPTVrec Dashboard
set -e
cd "$(dirname "$0")"
export PYTHONPATH="$(dirname "$(pwd)")/src:$(dirname "$(pwd)"):${PYTHONPATH:-}"
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 3000 --log-level info
