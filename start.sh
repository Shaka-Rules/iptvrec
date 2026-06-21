#!/usr/bin/env bash
# Arranca el demonio programador en segundo plano (proceso normal; NO es un
# servicio de arranque del sistema).
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$ROOT"
PIDFILE="$ROOT/state/daemon.pid"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

if [ -f "$PIDFILE" ]; then
  PID=$(python3 -c "import json;print(json.load(open('$PIDFILE')).get('pid',''))" 2>/dev/null || true)
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    echo "Ya está en marcha (pid $PID)."
    exit 0
  fi
  rm -f "$PIDFILE"
fi

mkdir -p "$ROOT/logs"
nohup "$PY" -m iptvrec daemon run >> "$ROOT/logs/daemon.out" 2>&1 &
NEWPID=$!
sleep 1
if kill -0 "$NEWPID" 2>/dev/null; then
  echo "Demonio iniciado (pid $NEWPID). Estado: ./bin/iptvrec status"
else
  echo "ERROR: el demonio no arrancó; revisa logs/daemon.out" >&2
  exit 1
fi
