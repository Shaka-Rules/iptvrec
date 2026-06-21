"""Tipos comunes y utilidades para los proveedores de stream."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class Channel:
    """Canal resuelto o listable, común a las tres fuentes."""
    name: str                      # nombre legible
    source: str                    # "atresplayer" | "rtveplay" | xtream" | "m3u8"
    ref: str                       # slug/id (atres), stream_id (xtream), nombre (m3u8)
    url: str | None = None         # URL del stream (None hasta resolver)
    attributes: dict = field(default_factory=dict)


def normalize(s) -> str:
    """Normaliza un nombre para emparejar: sin acentos, minúsculas, solo alfanumérico.

    'laSexta' -> 'lasexta'; 'Antena 3' -> 'antena3'; 'AtresSeries' -> 'atreseries'.
    """
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())
