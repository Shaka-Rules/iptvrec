"""Copia verificada (sha256) del fichero temporal a la ruta final.

El temporal solo se borra si el destino es byte-idéntico (hash coincide).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from .errors import IntegrityError

_CHUNK = 1024 * 1024  # 1 MiB


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def unique_name(target: Path) -> Path:
    """Evita sobrescrituras: añade -1, -2, … si el destino ya existe."""
    if not target.exists():
        return target
    stem, suffix, parent = target.stem, target.suffix, target.parent
    i = 1
    while True:
        cand = parent / f"{stem}-{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1


def _free_bytes(path) -> int:
    return shutil.disk_usage(str(path)).free


def _copy_chunked(src: Path, dst: Path) -> None:
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        shutil.copyfileobj(fsrc, fdst, length=_CHUNK)
        fdst.flush()
        os.fsync(fdst.fileno())


def verified_move(src, dst_dir, *, use_rsync: bool = True, delete_src: bool = True) -> Path:
    """Copia src→dst_dir verificando sha256; borra el origen SOLO si coincide.

    Escribe primero a ``<final>.part`` y hace ``os.replace`` atómico al nombre final.
    Si el hash no coincide: borra el .part, conserva el origen y lanza IntegrityError.
    """
    src = Path(src)
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    size = src.stat().st_size
    if _free_bytes(dst_dir) < int(size * 1.05):
        raise IntegrityError(f"Espacio insuficiente en {dst_dir} para {size} bytes")

    final_dst = unique_name(dst_dir / src.name)
    tmp_dst = final_dst.with_suffix(final_dst.suffix + ".part")
    src_hash = sha256_file(src)
    try:
        if use_rsync and shutil.which("rsync"):
            subprocess.run(
                ["rsync", "-c", "--partial", "--inplace", str(src), str(tmp_dst)],
                check=True,
            )
        else:
            _copy_chunked(src, tmp_dst)
        if sha256_file(tmp_dst) != src_hash:
            raise IntegrityError(f"sha256 no coincide al copiar {src.name}")
        os.replace(tmp_dst, final_dst)
    except Exception:
        if tmp_dst.exists():
            try:
                tmp_dst.unlink()
            except OSError:
                pass
        raise

    if delete_src:
        try:
            src.unlink()
        except OSError:
            pass
    return final_dst
