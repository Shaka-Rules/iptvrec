"""Wizard API for step-by-step recording creation."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.iptvrec import (
    load_cfg, list_channels, resolve_stream_url, load_schedule_entries,
    save_schedule_entries, start_recording_adhoc, _safe, scheduler, paths,
)
from ..models import RecurrenceType, SourceType, WizardSubmitRequest, WizardSubmitResponse

router = APIRouter(prefix="/api/wizard", tags=["wizard"])


@router.get("/sources")
def wizard_get_sources():
    cfg = load_cfg()
    sources = []
    if cfg.atresplayer.get("enabled"):
        sources.append({"id": "atresplayer", "name": "Atresplayer", "icon": "tv"})
    if cfg.rtveplay.get("enabled"):
        sources.append({"id": "rtveplay", "name": "RTVE Play", "icon": "tv"})
    if cfg.xtream.get("enabled"):
        sources.append({"id": "xtream", "name": "Xtream Codes", "icon": "satellite"})
    if cfg.m3u8.get("enabled"):
        sources.append({"id": "m3u8", "name": "Lista M3U", "icon": "list"})
    return {"sources": sources}


@router.get("/channels")
def wizard_get_channels(
    source: str,
    q: str = "",
    page: int = 1,
    size: int = 50,
):
    cfg = load_cfg()
    result = list_channels(source, cfg, query=q, page=page, size=size)
    return result


@router.post("/preview-url")
def wizard_preview_url(body: dict):
    source = body.get("source", "")
    channel = body.get("channel", "")
    cfg = load_cfg()
    try:
        url = resolve_stream_url(source, channel, cfg)
        return {"ok": True, "url": url}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


class ValidateDateTimeRequest(BaseModel):
    recurrence_type: str
    date: Optional[str] = None
    time: str
    days: Optional[list[str]] = None
    duration_seconds: int
    source: Optional[str] = None
    channel: Optional[str] = None


@router.post("/validate-datetime")
def wizard_validate_datetime(req: ValidateDateTimeRequest):
    cfg = load_cfg()
    tz = ZoneInfo(cfg.timezone)
    now = datetime.now(tz)
    warnings = []
    conflicts = []

    if req.recurrence_type == "once":
        if not req.date:
            return {"valid": False, "error": "Se requiere fecha para tipo 'once'"}
        try:
            y, mo, d = (int(x) for x in req.date.split("-"))
            h, mi = (int(x) for x in req.time.split(":"))
            start = datetime(y, mo, d, h, mi, tzinfo=tz)
        except ValueError:
            return {"valid": False, "error": "Fecha u hora inválida"}
    elif req.recurrence_type == "daily":
        h, mi = (int(x) for x in req.time.split(":"))
        start = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if start <= now:
            start += timedelta(days=1)
    elif req.recurrence_type == "weekly":
        if not req.days:
            return {"valid": False, "error": "Se requiere al menos un día para tipo 'weekly'"}
        from ..services.iptvrec import scheduler
        weekday_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        h, mi = (int(x) for x in req.time.split(":"))
        target_days = {weekday_map.get(d.lower()[:3]) for d in req.days if d}
        start = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if start <= now:
            start += timedelta(days=1)
        # Find next matching day
        for _ in range(8):
            if start.weekday() in target_days:
                break
            start += timedelta(days=1)
    else:
        return {"valid": False, "error": "Tipo de recurrencia inválido"}

    end = start + timedelta(seconds=req.duration_seconds)
    end_local = end.strftime("%d/%m/%Y %H:%M")
    start_local = start.strftime("%d/%m/%Y %H:%M")

    # Check conflicts with existing schedule
    if req.source and req.channel:
        entries = load_schedule_entries(cfg)
        for e in entries:
            if not e.get("enabled", True):
                continue
            if e.get("source") != req.source:
                continue
            try:
                fires = scheduler.candidate_fires(e, start, tz)
                e_dur = int(e.get("duration", 0))
                for f in fires:
                    f_end = f + timedelta(seconds=e_dur)
                    if f < end and f_end > start:
                        conflicts.append({
                            "id": e.get("id"),
                            "name": e.get("name"),
                            "start": f.strftime("%d/%m/%Y %H:%M"),
                            "end": f_end.strftime("%d/%m/%Y %H:%M"),
                        })
            except Exception:
                continue

    if start < now and req.recurrence_type == "once":
        warnings.append("La fecha seleccionada ya ha pasado")

    duration_h = req.duration_seconds // 3600
    duration_m = (req.duration_seconds % 3600) // 60
    duration_str = f"{duration_h}h {duration_m}m" if duration_h else f"{duration_m}m"

    return {
        "valid": True,
        "start": start_local,
        "end": end_local,
        "start_utc": start.astimezone(ZoneInfo("UTC")).isoformat(),
        "end_utc": end.astimezone(ZoneInfo("UTC")).isoformat(),
        "duration": duration_str,
        "duration_seconds": req.duration_seconds,
        "timezone": cfg.timezone,
        "conflicts": conflicts,
        "warnings": warnings,
    }


@router.post("/submit")
def wizard_submit(req: WizardSubmitRequest):
    cfg = load_cfg()
    tz = ZoneInfo(cfg.timezone)
    now = datetime.now(tz)

    # Calculate start datetime
    if req.recurrence_type == "once":
        if not req.date:
            raise HTTPException(status_code=400, detail="Fecha requerida para tipo 'once'")
        try:
            y, mo, d = (int(x) for x in req.date.split("-"))
            h, mi = (int(x) for x in req.time.split(":"))
            start = datetime(y, mo, d, h, mi, tzinfo=tz)
        except ValueError:
            raise HTTPException(status_code=400, detail="Fecha u hora inválida")
    elif req.recurrence_type == "daily":
        h, mi = (int(x) for x in req.time.split(":"))
        start = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if start <= now:
            start += timedelta(days=1)
    elif req.recurrence_type == "weekly":
        if not req.days:
            raise HTTPException(status_code=400, detail="Días requeridos para tipo 'weekly'")
        weekday_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        h, mi = (int(x) for x in req.time.split(":"))
        target_days = {weekday_map.get(d.lower()[:3]) for d in req.days if d}
        start = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if start <= now:
            start += timedelta(days=1)
        for _ in range(8):
            if start.weekday() in target_days:
                break
            start += timedelta(days=1)
    else:
        raise HTTPException(status_code=400, detail="Tipo de recurrencia inválido")

    end = start + timedelta(seconds=req.duration_seconds)
    name = req.custom_name or req.channel_name or req.channel
    safe_name = _safe(name)

    if req.action == "now":
        # Launch ad-hoc recording
        job_id = f"adhoc-{safe_name}_{start.strftime('%Y%m%dT%H%M')}_{uuid.uuid4().hex[:6]}"
        spec = {
            "job_id": job_id,
            "entry_id": "adhoc",
            "name": name,
            "source": req.source,
            "channel": req.channel,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration": req.duration_seconds,
            "youtube": {"upload": req.youtube_enabled} if req.youtube_enabled else {},
        }
        if req.youtube_enabled:
            import re
            spec["youtube"] = {
                "upload": True,
                "privacy": req.youtube_privacy,
                "category_id": req.youtube_category_id,
                "tags": req.youtube_tags,
            }
            if req.youtube_playlist_id:
                spec["youtube"]["playlist_id"] = req.youtube_playlist_id

        start_recording_adhoc(cfg, spec)
        return WizardSubmitResponse(
            success=True,
            message=f"Grabación '{name}' iniciada",
            job_id=job_id,
        )
    else:
        # Add to schedule
        schedule_id = safe_name
        recurrence = {"type": req.recurrence_type.value if hasattr(req.recurrence_type, 'value') else req.recurrence_type}
        if req.recurrence_type == "once":
            recurrence["date"] = req.date
            recurrence["time"] = req.time
        elif req.recurrence_type == "daily":
            recurrence["time"] = req.time
        elif req.recurrence_type == "weekly":
            recurrence["days"] = req.days
            recurrence["time"] = req.time

        entry = {
            "id": schedule_id,
            "enabled": True,
            "name": name,
            "source": req.source,
            "channel": req.channel,
            "recurrence": recurrence,
            "duration": req.duration_seconds,
        }
        if req.youtube_enabled:
            entry["youtube"] = {
                "upload": True,
                "privacy": req.youtube_privacy,
                "category_id": req.youtube_category_id,
                "tags": req.youtube_tags,
            }
            if req.youtube_playlist_id:
                entry["youtube"]["playlist_id"] = req.youtube_playlist_id
        if req.output_dir:
            entry["output_dir"] = req.output_dir
        if req.output_format:
            entry["output_format"] = req.output_format

        entries = load_schedule_entries(cfg)
        # Make id unique
        existing_ids = {e.get("id") for e in entries}
        if schedule_id in existing_ids:
            schedule_id = f"{schedule_id}-{uuid.uuid4().hex[:4]}"
            entry["id"] = schedule_id
        entries.append(entry)
        save_schedule_entries(entries)

        next_fire = None
        for f in scheduler.candidate_fires(entry, datetime.now(tz), tz):
            if f >= datetime.now(tz):
                next_fire = f.strftime("%d/%m/%Y %H:%M")
                break

        msg = f"Grabación '{name}' programada"
        if next_fire:
            msg += f" para {next_fire}"
        return WizardSubmitResponse(
            success=True,
            message=msg,
            schedule_id=schedule_id,
        )