"""Daemon control API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services.iptvrec import (
    load_cfg, daemon_is_running, get_daemon_pid,
    start_daemon as svc_start_daemon,
    stop_daemon as svc_stop_daemon,
    get_daemon_log_path, read_log_lines,
)

router = APIRouter(prefix="/api/daemon", tags=["daemon"])


@router.get("/status")
def api_daemon_status():
    running = daemon_is_running()
    pid = get_daemon_pid()
    return {"running": running, "pid": pid}


@router.post("/start")
def api_daemon_start():
    if daemon_is_running():
        raise HTTPException(status_code=409, detail="El demonio ya está en ejecución")
    ok = svc_start_daemon()
    if not ok:
        raise HTTPException(status_code=500, detail="No se pudo iniciar el demonio")
    return {"success": True, "message": "Demonio iniciado"}


@router.post("/stop")
def api_daemon_stop():
    if not daemon_is_running():
        raise HTTPException(status_code=409, detail="El demonio no está en ejecución")
    ok = svc_stop_daemon()
    return {"success": ok, "message": "Demonio detenido" if ok else "No se pudo detener el demonio"}


@router.post("/restart")
def api_daemon_restart():
    if daemon_is_running():
        svc_stop_daemon()
        import time
        time.sleep(2)
    ok = svc_start_daemon()
    if not ok:
        raise HTTPException(status_code=500, detail="No se pudo reiniciar el demonio")
    return {"success": True, "message": "Demonio reiniciado"}


@router.get("/log")
def api_daemon_log(offset: int = 0, limit: int = 200):
    path = get_daemon_log_path()
    if not path.exists():
        return {"lines": [], "total_lines": 0, "offset": offset, "limit": limit, "has_more": False}
    lines = read_log_lines(path, offset=offset, limit=limit)
    total_lines = 0
    try:
        with open(path, "rb") as fh:
            total_lines = sum(1 for _ in fh)
    except OSError:
        pass
    return {
        "lines": lines,
        "total_lines": total_lines,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total_lines,
    }