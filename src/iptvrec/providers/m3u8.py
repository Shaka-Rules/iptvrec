"""Proveedor de playlists M3U/M3U8 (fichero local o URL remota)."""
from __future__ import annotations

import re

from ..errors import ResolveError
from ..net import build_session
from .base import Channel, normalize

# '#EXTINF:-1 tvg-id="x" group-title="y",Nombre Del Canal'
_EXTINF_RE = re.compile(r"^#EXTINF:-?\d+\s*(?P<attrs>[^,]*),(?P<name>.*)$")
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _load_text(source, cfg, session=None) -> str:
    if str(source).startswith(("http://", "https://")):
        s = session or build_session(user_agent=cfg.ffmpeg_user_agent())
        resp = s.get(source, timeout=30)
        resp.raise_for_status()
        return resp.text
    from ..paths import resolve_path
    return resolve_path(source).read_text(encoding="utf-8", errors="replace")


def parse(text) -> list[Channel]:
    """Parsea el texto del playlist en canales. El nombre puede contener comas."""
    out: list[Channel] = []
    pending = None
    for raw in text.splitlines():
        line = raw.lstrip("﻿").strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            m = _EXTINF_RE.match(line)
            if m:
                attrs = dict(_ATTR_RE.findall(m.group("attrs")))
                pending = (m.group("name").strip(), attrs)
        elif line.startswith("#EXTGRP:"):
            if pending:
                pending[1].setdefault("group-title", line.split(":", 1)[1].strip())
        elif line.startswith("#"):
            continue
        else:
            if pending:
                name, attrs = pending
                out.append(Channel(name=name or attrs.get("tvg-name", line),
                                   source="m3u8", ref=name, url=line, attributes=attrs))
                pending = None
    return out


def _default_source(cfg):
    srcs = cfg.m3u8.get("sources", []) or []
    if not srcs or not srcs[0].get("url"):
        raise ResolveError("m3u8: no hay 'sources' configuradas en config.yaml")
    return srcs[0]["url"]


def list_channels(cfg, *, session=None, playlist=None, **kwargs) -> list[Channel]:
    src = playlist or _default_source(cfg)
    return parse(_load_text(src, cfg, session))


def resolve(target, cfg, session=None, playlist=None) -> str:
    """Resuelve nombre / tvg-id / tvg-name → URL (o devuelve la URL si target ya lo es)."""
    target = str(target).strip()
    if target.startswith(("http://", "https://")):
        return target
    norm = normalize(target)
    for c in list_channels(cfg, session=session, playlist=playlist):
        if (normalize(c.name) == norm
                or c.attributes.get("tvg-id") == target
                or normalize(c.attributes.get("tvg-name", "")) == norm):
            return c.url
    raise ResolveError(f"m3u8: canal '{target}' no encontrado en el playlist")
