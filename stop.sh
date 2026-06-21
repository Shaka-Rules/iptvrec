#!/usr/bin/env bash
# Detiene el demonio limpiamente (SIGTERM → las grabaciones en curso ensamblan
# y copian lo grabado; escala a SIGKILL si no responde).
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PIDFILE="$ROOT/state/daemon.pid"

if [ ! -f "$PIDFILE" ]; then
  echo "No está en marcha."
  exit 0
fi
PID=$(python3 -c "import json;print(json.load(open('$PIDFILE')).get('pid',''))" 2>/dev/null || true)
if [ -z "${PID:-}" ] || ! kill -0 "$PID" 2>/dev/null; then
  echo "No está en marcha (pid obsoleto)."
  rm -f "$PIDFILE"
  exit 0
fi

echo "Deteniendo demonio (pid $PID)…"
kill -TERM "$PID" 2>/dev/null || true
for _ in $(seq 1 30); do
  kill -0 "$PID" 2>/dev/null || break
  sleep 1
done
if kill -0 "$PID" 2>/dev/null; then
  echo "No respondió; forzando (SIGKILL)…"
  kill -KILL "$PID" 2>/dev/null || true
fi
rm -f "$PIDFILE"
echo "Detenido."
