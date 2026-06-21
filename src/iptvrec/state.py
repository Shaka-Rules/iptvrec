"""Lectura/escritura de estado en JSON, atómica y tolerante a fallos."""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    import fcntl  # POSIX (Debian). Ausente en Windows (solo entorno de desarrollo).
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore


def read_json(path, default: Any = None) -> Any:
    """Lee JSON; si no existe o está corrupto, devuelve ``default``."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return default


def write_json_atomic(path, data: Any) -> None:
    """Escribe JSON de forma atómica (fichero temporal + os.replace + fsync)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


@contextmanager
def file_lock(lock_path):
    """Lock de fichero asesor (flock en POSIX; no-op si fcntl no está disponible)."""
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+")
    try:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()
