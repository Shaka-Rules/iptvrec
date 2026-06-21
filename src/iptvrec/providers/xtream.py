"""Proveedor Xtream Codes (player_api.php)."""
from __future__ import annotations

import time

from ..errors import AuthError, ResolveError
from ..net import build_session, get_json
from .base import Channel, normalize

_CACHE: dict = {"streams": None, "ts": 0.0}


def _base(cfg) -> str:
    base = str(cfg.xtream.get("base_url", "")).rstrip("/")
    if not base:
        raise ResolveError("xtream.base_url no configurado en config.yaml")
    return base


def _creds(cfg):
    return cfg.xtream.get("username", ""), cfg.xtream.get("password", "")


def _session(cfg, session):
    return session or build_session(user_agent=cfg.ffmpeg_user_agent())


def _player_api(cfg, session, action=None):
    user, pwd = _creds(cfg)
    params = {"username": user, "password": pwd}
    if action:
        params["action"] = action
    return get_json(_session(cfg, session), f"{_base(cfg)}/player_api.php",
                    params=params, timeout=30)


def check_auth(cfg, *, session=None) -> dict:
    """Verifica credenciales; devuelve user_info (auth, status, max_connections, exp_date)."""
    data = _player_api(cfg, session)
    info = data.get("user_info", {}) if isinstance(data, dict) else {}
    if int(info.get("auth", 0)) != 1 or str(info.get("status", "")).lower() != "active":
        raise AuthError(f"xtream: cuenta no activa / auth fallida (status={info.get('status')})")
    return info


def list_categories(cfg, *, session=None) -> dict:
    data = _player_api(cfg, session, action="get_live_categories")
    return {str(c.get("category_id")): c.get("category_name", "") for c in (data or [])}


def list_streams(cfg, *, session=None, force_refresh=False) -> list[Channel]:
    ttl = int(cfg.xtream.get("channel_cache_minutes", 60)) * 60
    now = time.monotonic()
    if not force_refresh and _CACHE["streams"] is not None and (now - _CACHE["ts"]) < ttl:
        return _CACHE["streams"]
    cats = list_categories(cfg, session=session)
    data = _player_api(cfg, session, action="get_live_streams")
    out: list[Channel] = []
    for st in (data or []):
        sid = str(st.get("stream_id"))
        out.append(Channel(
            name=st.get("name", "?"), source="xtream", ref=sid,
            attributes={"category": cats.get(str(st.get("category_id")), ""),
                        "epg_channel_id": st.get("epg_channel_id")},
        ))
    _CACHE["streams"] = out
    _CACHE["ts"] = now
    return out


def stream_url(cfg, stream_id, container=None) -> str:
    user, pwd = _creds(cfg)
    container = container or cfg.xtream.get("container", "ts")
    return f"{_base(cfg)}/live/{user}/{pwd}/{stream_id}.{container}"


def resolve(target, cfg, session=None) -> str:
    """Resuelve stream_id (dígitos) o nombre → URL de stream."""
    target = str(target).strip()
    if target.isdigit():
        return stream_url(cfg, target)
    norm = normalize(target)
    matches = [c for c in list_streams(cfg, session=session) if normalize(c.name) == norm]
    if not matches:
        raise ResolveError(f"xtream: canal '{target}' no encontrado")
    if len(matches) > 1:
        ids = ", ".join(m.ref for m in matches[:8])
        raise ResolveError(f"xtream: nombre '{target}' ambiguo; usa el stream_id ({ids}…)")
    return stream_url(cfg, matches[0].ref)
