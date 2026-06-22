"""Schedule CRUD API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

from ..services.iptvrec import load_cfg, load_schedule_entries, save_schedule_entries

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


class ScheduleEntryCreate(BaseModel):
    id: str
    name: str
    source: str
    channel: str
    recurrence: dict[str, Any]
    duration: int
    youtube: dict[str, Any] = {}
    enabled: bool = True
    output_dir: Optional[str] = None
    output_format: Optional[str] = None


class ScheduleEntryUpdate(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = None
    source: Optional[str] = None
    channel: Optional[str] = None
    recurrence: Optional[dict[str, Any]] = None
    duration: Optional[int] = None
    youtube: Optional[dict[str, Any]] = None
    output_dir: Optional[str] = None
    output_format: Optional[str] = None


@router.get("")
def api_list_schedule():
    cfg = load_cfg()
    entries = load_schedule_entries(cfg)
    return {"entries": entries}


@router.post("")
def api_create_schedule(entry: ScheduleEntryCreate):
    cfg = load_cfg()
    entries = load_schedule_entries(cfg)
    if any(r.get("id") == entry.id for r in entries):
        raise HTTPException(status_code=409, detail=f"Ya existe una entrada con id '{entry.id}'")
    rec = {
        "id": entry.id,
        "enabled": entry.enabled,
        "name": entry.name,
        "source": entry.source,
        "channel": entry.channel,
        "recurrence": entry.recurrence,
        "duration": entry.duration,
    }
    if entry.youtube:
        rec["youtube"] = entry.youtube
    if entry.output_dir:
        rec["output_dir"] = entry.output_dir
    if entry.output_format:
        rec["output_format"] = entry.output_format
    entries.append(rec)
    save_schedule_entries(entries)
    return {"success": True, "id": entry.id}


@router.get("/{entry_id}")
def api_get_schedule(entry_id: str):
    cfg = load_cfg()
    entries = load_schedule_entries(cfg)
    for e in entries:
        if e.get("id") == entry_id:
            return e
    raise HTTPException(status_code=404, detail="Entrada no encontrada")


@router.patch("/{entry_id}")
def api_update_schedule(entry_id: str, update: ScheduleEntryUpdate):
    cfg = load_cfg()
    entries = load_schedule_entries(cfg)
    for e in entries:
        if e.get("id") == entry_id:
            update_data = update.model_dump(exclude_none=True)
            if "enabled" in update_data:
                e["enabled"] = update_data["enabled"]
            for key in ("name", "source", "channel", "recurrence", "duration",
                        "youtube", "output_dir", "output_format"):
                if key in update_data:
                    if update_data[key] is not None:
                        e[key] = update_data[key]
                    elif key in e:
                        del e[key]
            save_schedule_entries(entries)
            return {"success": True, "id": entry_id}
    raise HTTPException(status_code=404, detail="Entrada no encontrada")


@router.delete("/{entry_id}")
def api_delete_schedule(entry_id: str):
    cfg = load_cfg()
    entries = load_schedule_entries(cfg)
    for i, e in enumerate(entries):
        if e.get("id") == entry_id:
            entries.pop(i)
            save_schedule_entries(entries)
            return {"success": True, "id": entry_id}
    raise HTTPException(status_code=404, detail="Entrada no encontrada")


@router.post("/{entry_id}/enable")
def api_enable_schedule(entry_id: str):
    cfg = load_cfg()
    entries = load_schedule_entries(cfg)
    for e in entries:
        if e.get("id") == entry_id:
            e["enabled"] = True
            save_schedule_entries(entries)
            return {"success": True, "id": entry_id, "enabled": True}
    raise HTTPException(status_code=404, detail="Entrada no encontrada")


@router.post("/{entry_id}/disable")
def api_disable_schedule(entry_id: str):
    cfg = load_cfg()
    entries = load_schedule_entries(cfg)
    for e in entries:
        if e.get("id") == entry_id:
            e["enabled"] = False
            save_schedule_entries(entries)
            return {"success": True, "id": entry_id, "enabled": False}
    raise HTTPException(status_code=404, detail="Entrada no encontrada")