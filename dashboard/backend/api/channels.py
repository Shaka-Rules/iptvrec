"""Channel listing and search API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from ..services.iptvrec import load_cfg, list_channels

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("/{source}")
def api_list_channels(
    source: str,
    q: str = Query("", alias="q"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    refresh: bool = Query(False),
):
    cfg = load_cfg()
    result = list_channels(source, cfg, query=q, page=page, size=size)
    return result


@router.get("/{source}/{channel}/preview")
def api_preview_channel(source: str, channel: str):
    from ..services.iptvrec import load_cfg, resolve_stream_url, get_job_log_path
    import subprocess, tempfile, os
    cfg = load_cfg()
    try:
        url = resolve_stream_url(source, channel, cfg)
        # Quick ffprobe test
        ffprobe = cfg.ffmpeg.get("ffprobe_binary", "ffprobe")
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=format_name,duration,size",
             "-of", "csv=p=0", url],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(",")
            return {
                "ok": True,
                "url": url,
                "format": parts[0] if len(parts) > 0 else "",
                "duration": parts[1] if len(parts) > 1 else "",
            }
        return {"ok": False, "url": url, "error": "ffprobe no pudo analizar el stream"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/{source}/search")
def api_search_channels(
    source: str,
    q: str = Query("", alias="q"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    cfg = load_cfg()
    result = list_channels(source, cfg, query=q, page=page, size=size)
    return result