#!/usr/bin/env bash
# Instalación de una sola vez: crea un venv RELATIVO, instala dependencias,
# comprueba ffmpeg y prepara la configuración. No instala nada en el sistema.
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$ROOT"

echo "== iptvrec :: instalación =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 no está instalado (apt-get install -y python3 python3-venv)." >&2
  exit 1
fi
echo "  python3 $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"

if [ ! -d "$ROOT/.venv" ]; then
  echo "  creando entorno virtual (.venv)…"
  python3 -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/pip" install --quiet --upgrade pip
echo "  instalando dependencias de requirements.txt…"
"$ROOT/.venv/bin/pip" install --quiet -r "$ROOT/requirements.txt"

miss=0
for b in ffmpeg ffprobe; do
  if command -v "$b" >/dev/null 2>&1; then
    echo "  $b: $(command -v "$b")"
  else
    echo "  $b: NO ENCONTRADO" >&2; miss=1
  fi
done
if [ "$miss" = "1" ]; then
  echo "" >&2
  echo "Falta ffmpeg/ffprobe. Instálalos (como root) y reintenta:" >&2
  echo "    apt-get update && apt-get install -y ffmpeg" >&2
  exit 1
fi

chmod +x "$ROOT/bin/iptvrec" "$ROOT/start.sh" "$ROOT/stop.sh" 2>/dev/null || true
mkdir -p "$ROOT/logs" "$ROOT/recordings" "$ROOT/tmp" "$ROOT/state/jobs"

[ -f "$ROOT/config/config.yaml" ]   || cp "$ROOT/config/config.example.yaml"   "$ROOT/config/config.yaml"
[ -f "$ROOT/config/schedule.yaml" ] || cp "$ROOT/config/schedule.example.yaml" "$ROOT/config/schedule.yaml"
chmod 600 "$ROOT/config/config.yaml" "$ROOT/config/credentials.json" 2>/dev/null || true

echo ""
echo "✓ Instalación completa. Próximos pasos:"
echo "    ./bin/iptvrec validate"
echo "    ./bin/iptvrec youtube-auth      # solo si vas a subir a YouTube"
echo "    ./bin/iptvrec test-telegram     # si has activado Telegram"
echo "    ./start.sh                      # arranca el programador en 2º plano"
