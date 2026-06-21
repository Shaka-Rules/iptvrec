"""Descubrimiento de la raíz de instalación y rutas canónicas.

Todo es relativo a la carpeta extraída: el paquete vive en
``<root>/src/iptvrec/``, así que la raíz es ``parents[2]`` de este fichero.
No se depende de CWD, ``$HOME`` ni variables de entorno → portable: funciona
allí donde se copie y descomprima.
"""
from __future__ import annotations

from pathlib import Path

# <root>/src/iptvrec/paths.py  ->  parents[0]=iptvrec [1]=src [2]=<root>
INSTALL_ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = INSTALL_ROOT / "config"
STATE_DIR = INSTALL_ROOT / "state"
JOBS_DIR = STATE_DIR / "jobs"
LOGS_DIR = INSTALL_ROOT / "logs"
DEFAULT_TMP = INSTALL_ROOT / "tmp"
DEFAULT_OUTPUT = INSTALL_ROOT / "recordings"

CONFIG_FILE = CONFIG_DIR / "config.yaml"
SCHEDULE_FILE = CONFIG_DIR / "schedule.yaml"
PID_FILE = STATE_DIR / "daemon.pid"
STATUS_FILE = STATE_DIR / "status.json"
FIRED_FILE = STATE_DIR / "fired.json"
YOUTUBE_AUTH_FILE = STATE_DIR / "youtube_auth.json"


def resolve_path(value, base: Path = INSTALL_ROOT) -> Path:
    """Resuelve una ruta de config: relativa → contra la raíz; absoluta → tal cual."""
    p = Path(str(value)).expanduser()
    return p if p.is_absolute() else (base / p).resolve()
