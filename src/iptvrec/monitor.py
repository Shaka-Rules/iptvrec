"""Monitor de estado: renderiza state/status.json en una tabla de texto."""
from __future__ import annotations

import json
import os
import time

from . import paths
from .state import read_json


def _pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def _hms(s) -> str:
    s = int(s or 0)
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _human(n) -> str:
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def _fmt_in(seconds) -> str:
    s = int(seconds or 0)
    if s <= 0:
        return "ahora"
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m, _ = divmod(r, 60)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def render(status) -> str:
    lines = []
    d = status.get("daemon", {})
    pid = d.get("pid")
    alive = _pid_alive(pid) and bool(d.get("running"))
    lines.append(f"iptvrec — {d.get('timezone', '')} — {status.get('generated_at', '?')}")
    lines.append(f"Demonio: {'UP' if alive else 'DOWN'}   pid {pid}   tick {d.get('tick_seconds')}s")

    active = status.get("active", [])
    lines.append("")
    lines.append(f"ACTIVAS ({len(active)})")
    for a in active:
        lines.append(f"  {a.get('name')}   {a.get('source')}/{a.get('channel')}   "
                     f"transcurrido {_hms(a.get('elapsed_s'))} / quedan {_hms(a.get('remaining_s'))}")
        lines.append(f"     tamaño {_human(a.get('current_size_bytes'))}   "
                     f"segmentos {a.get('segments')}   reintentos {a.get('retries')}   "
                     f"[{a.get('status')}]")
    if not active:
        lines.append("  (ninguna)")

    up = status.get("upcoming", [])
    lines.append("")
    lines.append("PRÓXIMAS")
    for u in up[:8]:
        lines.append(f"  {u.get('name')}   en {_fmt_in(u.get('in_s'))}   "
                     f"({u.get('source')}/{u.get('channel')})")
    if not up:
        lines.append("  (ninguna)")

    rec = status.get("recent", [])
    lines.append("")
    lines.append("RECIENTES")
    for r in rec[:8]:
        if r.get("status") == "success":
            extra = f"{_human(r.get('bytes'))} -> {r.get('final_path')}"
            if r.get("youtube_url"):
                extra += "  (YouTube)"
            lines.append(f"  ✓ {r.get('name')}   {extra}")
        else:
            lines.append(f"  ✗ {r.get('name')}   error: {r.get('last_error', '?')}")
    if not rec:
        lines.append("  (ninguna)")

    disk = status.get("disk", {})
    t, o = disk.get("temp", {}), disk.get("output", {})
    lines.append("")
    lines.append(f"DISCO   temp {t.get('free_mb', '?')} MB libres   |   "
                 f"final {o.get('free_mb', '?')} MB libres")

    yt = status.get("youtube", {})
    if yt.get("configured"):
        due = yt.get("days_until_expiry")
        due_s = (f"caduca en ~{due:.1f} días" if isinstance(due, (int, float))
                 else "sin caducidad programada")
        lines.append(f"YOUTUBE  token {'válido' if yt.get('valid') else 'INVÁLIDO'}   {due_s}")
    return "\n".join(lines)


def show(cfg=None, *, as_json: bool = False, watch=None) -> str:
    def _load():
        return read_json(paths.STATUS_FILE, {}) or {}

    if as_json:
        return json.dumps(_load(), ensure_ascii=False, indent=2)
    if watch:
        try:
            while True:
                print("\x1b[2J\x1b[H" + render(_load()), flush=True)
                time.sleep(float(watch))
        except KeyboardInterrupt:
            return ""
    return render(_load())
