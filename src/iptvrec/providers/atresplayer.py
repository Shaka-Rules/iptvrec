"""Proveedor atresplayer — port fiel de atresplayer_channel_id.sh.

Cadena de resolución:
  nombre/slug -> GET /client/v1/url?href=/directos/{slug}/ -> channel_id (24 hex)
  channel_id  -> GET /player/v1/live/{id}?NODRM=true       -> sourcesLive[0].src (m3u8)
La URL del stream es EFÍMERA: se resuelve en cada (re)inicio de grabación.
"""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin

from ..errors import ResolveError
from ..net import build_session, get_json
from .base import Channel, normalize

OBJECTID_RE = re.compile(r"/([a-f0-9]{24})$")   # mismo patrón que el .sh
_HEX24_RE = re.compile(r"^[a-f0-9]{24}$")
_CACHE: dict = {"channels": None, "ts": 0.0}
_CACHE_TTL = 3600.0


def _headers() -> dict:
    return {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.atresplayer.com",
        "Referer": "https://www.atresplayer.com/",
    }


def _api_base(cfg) -> str:
    return str(cfg.atresplayer.get("api_base", "https://api.atresplayer.com")).rstrip("/")


def _session(cfg, session):
    return session or build_session(user_agent=cfg.ffmpeg_user_agent())


def list_channels(cfg, *, session=None, force_refresh=False) -> list[Channel]:
    """GET /client/v1/info/channels → [Channel(name, slug)]. Cacheado 1h."""
    now = time.monotonic()
    if not force_refresh and _CACHE["channels"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["channels"]
    s = _session(cfg, session)
    data = get_json(s, f"{_api_base(cfg)}/client/v1/info/channels", headers=_headers())
    out: list[Channel] = []
    for ch in data or []:
        title = ch.get("title", "?")
        url = (ch.get("link", {}) or {}).get("url", "/") or "/"
        slug = url.strip("/")
        if slug:
            out.append(Channel(name=title, source="atresplayer", ref=slug,
                               attributes={"slug": slug}))
    _CACHE["channels"] = out
    _CACHE["ts"] = now
    return out


def _slug_to_id(slug, cfg, session) -> str:
    s = _session(cfg, session)
    data = get_json(s, f"{_api_base(cfg)}/client/v1/url",
                    params={"href": f"/directos/{slug}/"}, headers=_headers())
    if isinstance(data, dict) and data.get("error"):
        raise ResolveError(f"atresplayer: canal '{slug}' no encontrado ({data.get('error')})")
    href_full = data.get("href", "") if isinstance(data, dict) else ""
    m = OBJECTID_RE.search(href_full)
    if not m:
        raise ResolveError(f"atresplayer: no se pudo extraer channel_id de '{href_full}'")
    return m.group(1)


def _best_variant_url(master_url: str, session) -> str:
    """Descarga el master playlist HLS y devuelve la variante con mayor BANDWIDTH.
    Si no puede parsearlo (formato inesperado, error de red), devuelve el master tal
    cual — ffmpeg seguirá funcionando, simplemente sin selección explícita de calidad.
    """
    try:
        resp = session.get(master_url, timeout=10)
        resp.raise_for_status()
        lines = resp.text.splitlines()
    except Exception:
        return master_url

    best_bw = -1
    best_uri = None
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"BANDWIDTH=(\d+)", line)
            bw = int(m.group(1)) if m else 0
            if i + 1 < len(lines) and bw > best_bw:
                best_bw = bw
                best_uri = lines[i + 1].strip()

    if not best_uri:
        return master_url
    return urljoin(master_url, best_uri)


def _id_to_stream(channel_id, cfg, session) -> str:
    s = _session(cfg, session)
    data = get_json(s, f"{_api_base(cfg)}/player/v1/live/{channel_id}",
                    params={"NODRM": "true"}, headers=_headers())
    if isinstance(data, dict) and data.get("error"):
        raise ResolveError(
            f"atresplayer player: {data.get('error')} - {data.get('error_description', '')}"
        )
    sources = data.get("sourcesLive", []) if isinstance(data, dict) else []
    if not sources or not sources[0].get("src"):
        raise ResolveError("atresplayer: sin sourcesLive[0].src (¿geobloqueo/DRM/IP no española?)")
    return _best_variant_url(sources[0]["src"], s)


def resolve_to_id(target, cfg, session=None) -> str:
    """Resuelve nombre / slug / id-24hex → channel_id."""
    target = str(target).strip()
    if _HEX24_RE.match(target):
        return target
    norm = normalize(target)
    try:
        for ch in list_channels(cfg, session=session):
            if normalize(ch.name) == norm or ch.ref == target:
                return _slug_to_id(ch.ref, cfg, session)
    except ResolveError:
        pass  # si falla el listado, probamos como slug directo
    slug = cfg.atresplayer.get("channels", {}).get(target.lower(), target)
    return _slug_to_id(slug, cfg, session)


def resolve(target, cfg, session=None) -> str:
    """Resuelve nombre/slug/id → URL m3u8 FRESCA (el player es el paso más inestable)."""
    channel_id = resolve_to_id(target, cfg, session=session)
    last = None
    for _ in range(3):
        try:
            return _id_to_stream(channel_id, cfg, session)
        except ResolveError as exc:
            last = exc
            time.sleep(1.0)
    raise last
