"""Proveedor rtveplay — emisiones en directo de RTVE Play.

Resolución:
  1. Slug/nombre del canal (la-1, la-2, 24h, tdp, clan, …)
  2. Scrapea la página del directo para extraer `idAsset` (JS object / JSON)
  3. Obtiene PNG cifrado desde ZTNR y lo descifra → URL HLS
"""
from __future__ import annotations

import base64
import html
import json
import logging
import re
import struct
import time
from io import BytesIO

from ..errors import ResolveError
from ..net import build_session
from .base import Channel, normalize

log = logging.getLogger("iptvrec")

_CACHE: dict = {"channels": None, "ts": 0.0}
_CACHE_TTL = 3600.0

# Slug -> nombre mostrable por defecto (sobrescribible desde config.yaml)
DEFAULT_CHANNELS = {
    "la-1": "La 1",
    "la-2": "La 2",
    "24h": "24h",
    "tdp": "Teledeporte",
    "clan": "Clan",
    "rtve-play": "RTVE Play",
    "canal-24h": "Canal 24h",
}

_PLAY_BASE = "https://www.rtve.es/play/videos/directo/canales-lineales"


def _headers() -> dict:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Origin": "https://www.rtve.es",
        "Referer": "https://www.rtve.es/",
    }


def _session(cfg, session=None):
    return session or build_session(user_agent=cfg.ffmpeg_user_agent())


# ---------------------------------------------------------------------------
# Descifrado ZTNR PNG (port fiel de yt-dlp)
# ---------------------------------------------------------------------------

def _decrypt_url(png_text: str):
    """Decodifica las URLs HLS desde el PNG en base64 devuelto por ZTNR.

    Yields (quality_label, url).
    """
    buf = BytesIO(base64.b64decode(png_text)[8:])  # salta cabecera PNG
    while True:
        raw_len = buf.read(4)
        if not raw_len or len(raw_len) < 4:
            break
        length = struct.unpack("!I", raw_len)[0]
        chunk_type = buf.read(4)
        if chunk_type == b"IEND":
            break
        data = buf.read(length)
        if chunk_type == b"tEXt":
            clean = bytes(b for b in data if b != 0)
            alpha_raw, _, url_data = clean.partition(b"#")
            quality_raw, _, url_raw = url_data.rpartition(b"%%")
            quality = quality_raw.decode() or ""
            alphabet = _build_alphabet(alpha_raw)
            url = _decode_url(alphabet, url_raw)
            yield quality, url
        buf.read(4)  # CRC


def _build_alphabet(raw: bytes) -> list[str]:
    alpha: list[str] = []
    e = 0
    d = 0
    for ch in raw.decode("iso-8859-1"):
        if d == 0:
            alpha.append(ch)
            d = e = (e + 1) % 4
        else:
            d -= 1
    return alpha


def _decode_url(alphabet: list[str], raw: bytes) -> str:
    url = ""
    f = 0
    e = 3
    b = 1
    for ch in raw.decode("iso-8859-1"):
        if f == 0:
            l = int(ch) * 10
            f = 1
        else:
            if e == 0:
                l += int(ch)
                url += alphabet[l]
                e = (b + 3) % 4
                f = 0
                b += 1
            else:
                e -= 1
    return url


def _fetch_ztnr_png(video_id: str, session, media_type: str = "videos") -> str | None:
    """Descarga el PNG ZTNR como texto base64."""
    for manager in ("rtveplayw", "default"):
        for base in ("https://ztnr.rtve.es", "http://www.rtve.es"):
            url = f"{base}/ztnr/movil/thumbnail/{manager}/{media_type}/{video_id}.png"
            try:
                resp = session.get(url, params={"q": "v2"}, timeout=15)
                if resp.status_code == 200:
                    text = resp.text.strip()
                    if text:
                        return text
            except Exception:
                continue
    return None


def _resolve_via_ztnr(video_id: str, session) -> str:
    """Resuelve un id numérico a URL HLS vía PNG ZTNR. Retorna la de mayor calidad."""
    png = _fetch_ztnr_png(video_id, session)
    if not png:
        raise ResolveError(f"rtveplay: no se pudo obtener PNG ZTNR para id {video_id}")

    quality_map = {"Media": 0, "Alta": 1, "HQ": 2, "HD_READY": 3, "HD_FULL": 4}
    best_url, best_q = None, -1

    for qlabel, url in _decrypt_url(png):
        clean_url = url.replace("_drm", "")
        q = quality_map.get(qlabel, -1)
        if q > best_q or best_url is None:
            best_q = q
            best_url = clean_url

    if not best_url:
        raise ResolveError(f"rtveplay: ninguna URL válida en PNG ZTNR para {video_id}")

    # Obtener el master playlist y extraer la variante 720p
    # para que ffmpeg lea un solo video + audio, no todas las calidades mezcladas
    try:
        resp = session.get(best_url, timeout=15, headers=_headers())
        if resp.status_code == 200:
            lines = resp.text.split("\n")
            best_res, best_variant = 0, None
            for i, line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF"):
                    m = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
                    if m and i + 1 < len(lines):
                        w, h = int(m.group(1)), int(m.group(2))
                        if w * h > best_res:
                            url = lines[i + 1].strip()
                            if not url.startswith("http"):
                                base = best_url.rsplit("/", 1)[0]
                                url = f"{base}/{url}"
                            best_res = w * h
                            best_variant = url
            if best_variant:
                return best_variant
    except Exception:
        pass

    return best_url


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def list_channels(cfg, *, session=None, force_refresh=False) -> list[Channel]:
    """Lista canales desde la configuración (cacheado 1h)."""
    now = time.monotonic()
    if not force_refresh and _CACHE["channels"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["channels"]

    ch_map = cfg.rtveplay.get("channels", DEFAULT_CHANNELS)
    out = [Channel(name=v, source="rtveplay", ref=k) for k, v in ch_map.items()]
    _CACHE["channels"] = out
    _CACHE["ts"] = now
    return out


def resolve(target, cfg, session=None) -> str:
    """Resuelve slug/nombre → URL HLS efímera.

    Scrapea la página del directo para extraer idAsset (numérico) y luego lo
    resuelve vía ZTNR PNG.
    """
    target = str(target).strip()
    s = _session(cfg, session)

    # 1) Obtener idAsset por web scraping
    live_url = f"{_PLAY_BASE}/{target}/"
    try:
        resp = s.get(live_url, timeout=15, headers=_headers())
        resp.raise_for_status()
    except Exception as exc:
        raise ResolveError(f"rtveplay: no se pudo acceder a {live_url}: {exc}")

    # Buscar idAsset directamente en el HTML
    m = re.search(r'["\']?idAsset["\']?\s*:\s*["\']?(\d+)["\']?\s*[,}]', resp.text)
    if m:
        asset_id = m.group(1)
    else:
        asset_id = None

    if not asset_id:
        # fallback 1: data-setup attribute (con HTML entities)
        m = re.search(r"data-setup='(.*?)'", resp.text, re.DOTALL)
        if not m:
            m = re.search(r'data-setup="(.*?)"', resp.text, re.DOTALL)
        if m:
            try:
                data_setup = json.loads(html.unescape(m.group(1)))
                asset_id = data_setup.get("idAsset")
            except json.JSONDecodeError:
                pass

    if not asset_id:
        # fallback 2: meta tag DC.identifier
        m = re.search(r'<meta\s+name="DC\.identifier"\s+content="(\d+)"', resp.text)
        if m:
            asset_id = m.group(1)

    if not asset_id:
        # fallback 3: JSON-LD embedUrl
        m = re.search(r'"embedUrl"\s*:\s*"https://[^"]*/video/(\d+)"', resp.text)
        if m:
            asset_id = m.group(1)

    if not asset_id:
        raise ResolveError(f"rtveplay: no se encontró idAsset en {live_url}")

    log.debug("rtveplay: %s -> idAsset %s", target, asset_id)

    # 2) Resolver vía ZTNR
    return _resolve_via_ztnr(str(asset_id), s)
