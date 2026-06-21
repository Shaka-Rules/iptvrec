"""Registro de proveedores y despacho de resolución de stream."""
from __future__ import annotations

from ..errors import ResolveError
from .base import Channel  # noqa: F401  (re-exportado para comodidad)
from . import atresplayer, rtveplay, xtream, m3u8

SOURCES = ("atresplayer", "rtveplay", "xtream", "m3u8")


def list_channels(source, cfg, *, session=None, **kwargs):
    """Lista canales de la fuente indicada."""
    if source == "atresplayer":
        return atresplayer.list_channels(cfg, session=session,
                                         force_refresh=kwargs.get("force_refresh", False))
    if source == "rtveplay":
        return rtveplay.list_channels(cfg, session=session,
                                      force_refresh=kwargs.get("force_refresh", False))
    if source == "xtream":
        return xtream.list_streams(cfg, session=session,
                                   force_refresh=kwargs.get("force_refresh", False))
    if source == "m3u8":
        return m3u8.list_channels(cfg, session=session, playlist=kwargs.get("playlist"))
    raise ResolveError(f"Fuente desconocida: {source!r} (usa una de {SOURCES})")


def resolve_stream_url(source, channel, cfg, *, session=None) -> str:
    """Devuelve SIEMPRE una URL fresca para grabar (se re-resuelve en cada reinicio)."""
    if source == "atresplayer":
        return atresplayer.resolve(channel, cfg, session=session)
    if source == "rtveplay":
        return rtveplay.resolve(channel, cfg, session=session)
    if source == "xtream":
        return xtream.resolve(channel, cfg, session=session)
    if source == "m3u8":
        return m3u8.resolve(channel, cfg, session=session)
    raise ResolveError(f"Fuente desconocida: {source!r} (usa una de {SOURCES})")
