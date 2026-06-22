"""Recordings management API."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..services.iptvrec import (
    load_cfg, get_active_recordings, get_recent_recordings,
    start_recording_adhoc, stop_recording, get_all_job_logs,
    read_log_lines, get_job_log_path, daemon_is_running,
    scheduler, paths, read_json, _safe, write_json_atomic,
)

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


@router.get("")
def api_list_recordings(status_filter: str = Query("", alias="status")):
    cfg = load_cfg()
    active = get_active_recordings(cfg)
    recent = get_recent_recordings(cfg, limit=50)
    if status_filter:
        try:
            from ..models import JobStatus
            s = JobStatus(status_filter)
            active = [r for r in active if r.status == s]
            recent = [r for r in recent if r.status == s]
        except ValueError:
            pass
    return {"active": [r.model_dump() for r in active],
            "recent": [r.model_dump() for r in recent]}


class StartRecordingRequest(BaseModel):
    source: str
    channel: str
    duration: int
    name: Optional[str] = None
    youtube: bool = False


@router.post("")
def api_start_recording(req: StartRecordingRequest):
    cfg = load_cfg()
    tz = ZoneInfo(cfg.timezone)
    now = datetime.now(tz)
    end = now + timedelta(seconds=req.duration)
    import uuid
    job_id = f"adhoc-{_safe(req.name or req.channel)}_{now.strftime('%Y%m%dT%H%M')}_{uuid.uuid4().hex[:6]}"
    spec = {
        "job_id": job_id,
        "entry_id": "adhoc",
        "name": req.name or req.channel,
        "source": req.source,
        "channel": req.channel,
        "start": now.isoformat(),
        "end": end.isoformat(),
        "youtube": {"upload": bool(req.youtube)},
    }
    try:
        start_recording_adhoc(cfg, spec)
        return {"success": True, "job_id": job_id, "name": spec["name"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{job_id}/stop")
def api_stop_recording(job_id: str):
    ok = stop_recording(job_id)
    return {"success": ok}


@router.get("/{job_id}/log")
def api_get_log(
    job_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=5000),
):
    path = get_job_log_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Log no encontrado")
    lines = read_log_lines(path, offset=offset, limit=limit)
    total_lines = 0
    try:
        with open(path, "rb") as fh:
            total_lines = sum(1 for _ in fh)
    except OSError:
        pass
    return {
        "job_id": job_id,
        "lines": lines,
        "total_lines": total_lines,
        "offset": offset,
        "limit": limit,
        "has_more": (offset + limit) < total_lines,
    }


@router.get("/logs")
def api_list_logs():
    logs = get_all_job_logs()
    return {"logs": logs}


@router.get("/{job_id}")
def api_get_recording(job_id: str):
    state_path = paths.JOBS_DIR / f"{job_id}.json"
    data = read_json(state_path)
    if not data:
        raise HTTPException(status_code=404, detail="Grabación no encontrada")
    return data