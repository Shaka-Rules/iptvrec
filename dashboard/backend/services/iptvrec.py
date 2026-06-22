"""Wrapper to reuse existing iptvrec modules."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import yaml

from ..models import RecordingModel, JobStatus

try:
    from iptvrec import config, paths, providers, scheduler, monitor, notify, recorder
    from iptvrec.state import read_json, write_json_atomic
    from iptvrec.scheduler import _safe, candidate_fires, next_upcoming
    from iptvrec.providers.base import Channel
    from iptvrec.errors import IPTVRecError
    INSTALL_ROOT = paths.INSTALL_ROOT
except ImportError as e:
    raise ImportError(
        f"No se pudieron cargar los modulos de iptvrec: {e}. "
        "Asegurate de que PYTHONPATH incluye la carpeta src/ de iptvrec."
    ) from e


def load_cfg(config_path: Optional[Path] = None):
    return config.load_config(config_path)


def list_channels(source: str, cfg, query: str = "", page: int = 1, size: int = 50):
    force_refresh = False
    chans = providers.list_channels(source, cfg, force_refresh=force_refresh)
    
    if query:
        q = query.lower().strip()
        chans = [c for c in chans if q in c.name.lower() or q in c.ref.lower()
                 or any(q in str(v).lower() for v in c.attributes.values())]
    
    total = len(chans)
    start = (page - 1) * size
    end = start + size
    page_chans = chans[start:end]
    
    out = []
    for c in page_chans:
        d = {"name": c.name, "source": source, "ref": c.ref,
             "attributes": c.attributes}
        if c.url:
            d["url"] = c.url
        out.append(d)
    
    return {
        "channels": out,
        "total": total,
        "page": page,
        "size": size,
        "has_more": end < total,
    }


def resolve_stream_url(source: str, channel: str, cfg):
    return providers.resolve_stream_url(source, channel, cfg)


def get_status(cfg):
    data = read_json(paths.STATUS_FILE, {}) or {}
    return data


def get_active_recordings(cfg) -> list[RecordingModel]:
    status = get_status(cfg)
    active = []
    for a in status.get("active", []):
        try:
            start = datetime.fromisoformat(a["start"])
            end = datetime.fromisoformat(a["end"])
        except (KeyError, ValueError):
            continue
        active.append(RecordingModel(
            job_id=a.get("job_id", ""),
            entry_id=a.get("entry_id"),
            name=a.get("name", a.get("channel", "")),
            source=a.get("source", ""),
            channel=a.get("channel", ""),
            start=start, end=end,
            status=JobStatus(a.get("status", "starting")),
            pid=a.get("pid"),
            segments=a.get("segments", 0),
            retries=a.get("retries", 0),
            current_size_bytes=a.get("current_size_bytes", 0),
            elapsed_s=a.get("elapsed_s"),
            remaining_s=a.get("remaining_s"),
            last_error=a.get("last_error"),
        ))
    return active


def get_recent_recordings(cfg, limit: int = 20) -> list[RecordingModel]:
    status = get_status(cfg)
    recent = []
    for r in status.get("recent", [])[:limit]:
        try:
            start = datetime.fromisoformat(r["start"]) if r.get("start") else datetime.min
            end = datetime.fromisoformat(r["end"]) if r.get("end") else datetime.min
        except (KeyError, ValueError):
            continue
        fin = None
        if r.get("finished_at"):
            try:
                fin = datetime.fromisoformat(r["finished_at"])
            except ValueError:
                pass
        recent.append(RecordingModel(
            job_id=r.get("job_id", ""),
            entry_id=r.get("entry_id"),
            name=r.get("name", r.get("channel", "")),
            source=r.get("source", ""),
            channel=r.get("channel", ""),
            start=start, end=end,
            status=JobStatus(r.get("status", "success")),
            final_path=r.get("final_path"),
            youtube_url=r.get("youtube_url"),
            current_size_bytes=r.get("bytes", 0),
            last_error=r.get("last_error"),
            finished_at=fin,
        ))
    return recent


def load_schedule_entries(cfg) -> list[dict]:
    if not paths.SCHEDULE_FILE.exists():
        return []
    with open(paths.SCHEDULE_FILE, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("recordings", [])


def save_schedule_entries(entries: list[dict]) -> None:
    doc = {"recordings": entries}
    tmp = paths.SCHEDULE_FILE.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh, allow_unicode=True, sort_keys=False)
    tmp.replace(paths.SCHEDULE_FILE)


def start_recording_adhoc(cfg, spec: dict) -> str:
    job_id = spec.get("job_id", "")
    if not job_id:
        tz = ZoneInfo(cfg.timezone)
        now = datetime.now(tz)
        name = spec.get("name") or spec.get("channel") or "rec"
        job_id = f"adhoc-{_safe(name)}_{now.strftime('%Y%m%dT%H%M')}_{uuid.uuid4().hex[:6]}"
        spec["job_id"] = job_id
    
    spec_path = paths.JOBS_DIR / f"{job_id}.spec.json"
    write_json_atomic(spec_path, spec)
    
    env = dict(os.environ)
    src = str(paths.INSTALL_ROOT / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    
    logfh = open(paths.LOGS_DIR / f"{job_id}.log", "ab")
    cmd = [sys.executable, "-m", "iptvrec", "record", "--from-spec", str(spec_path)]
    subprocess.Popen(
        cmd, cwd=str(paths.INSTALL_ROOT), env=env,
        stdin=subprocess.DEVNULL, stdout=logfh, stderr=logfh,
        start_new_session=True,
    )
    return job_id


def stop_recording(job_id: str) -> bool:
    state_path = paths.JOBS_DIR / f"{job_id}.json"
    data = read_json(state_path, {}) or {}
    pid = data.get("pid")
    if not pid:
        return False
    try:
        os.kill(int(pid), 15)
        return True
    except (OSError, ValueError):
        return False


def get_job_log_path(job_id: str) -> Path:
    return paths.LOGS_DIR / f"{job_id}.log"


def get_all_job_logs() -> list[dict]:
    logs = []
    for f in sorted(paths.LOGS_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        name = f.stem
        size = f.stat().st_size
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        logs.append({"job_id": name, "filename": f.name, "size_bytes": size, "modified": mtime.isoformat()})
    return logs


_LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)?)\s+-\s+"
    r"(\w+)\s+-\s+"
    r"(.*)$"
)


def parse_log_line(line: str, line_num: int = 0) -> dict:
    m = _LOG_RE.match(line)
    if m:
        return {"line": line_num, "timestamp": m.group(1), "level": m.group(2), "message": m.group(3), "raw": line}
    return {"line": line_num, "timestamp": "", "level": "", "message": line, "raw": line}


def read_log_lines(path: Path, offset: int = 0, limit: int = 100) -> list[dict]:
    lines = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        raw_lines = content.splitlines()
        for i, line in enumerate(raw_lines):
            if i < offset:
                continue
            if len(lines) >= limit:
                break
            lines.append(parse_log_line(line, i))
    except FileNotFoundError:
        pass
    return lines


def get_daemon_log_path() -> Path:
    return paths.LOGS_DIR / "daemon.log"


def get_daemon_pid() -> int | None:
    data = read_json(paths.PID_FILE, {}) or {}
    return data.get("pid")


def daemon_is_running() -> bool:
    pid = get_daemon_pid()
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def start_daemon() -> bool:
    script = paths.INSTALL_ROOT / "start.sh"
    if not script.exists():
        return False
    result = subprocess.run(["bash", str(script)], capture_output=True, timeout=30)
    return result.returncode == 0


def stop_daemon() -> bool:
    script = paths.INSTALL_ROOT / "stop.sh"
    if not script.exists():
        pid = get_daemon_pid()
        if pid:
            try:
                os.kill(int(pid), 15)
                return True
            except OSError:
                pass
        return False
    result = subprocess.run(["bash", str(script)], capture_output=True, timeout=30)
    return result.returncode == 0


def validate_configuration(cfg) -> dict:
    from iptvrec.config import validate_config, ensure_dirs, VALID_FORMATS
    import shutil as _shutil
    errors = []
    warnings = []
    try:
        validate_config(cfg)
    except Exception as exc:
        errors.append(str(exc))
    ensure_dirs(cfg)
    ff = _shutil.which(cfg.ffmpeg.get("binary", "ffmpeg"))
    fp = _shutil.which(cfg.ffmpeg.get("ffprobe_binary", "ffprobe"))
    if not ff:
        errors.append("ffmpeg no encontrado en el PATH")
    if not fp:
        errors.append("ffprobe no encontrado en el PATH")
    if cfg.output_format not in VALID_FORMATS:
        errors.append(f"Formato '{cfg.output_format}' invalido")
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "ffmpeg": ff or None,
        "ffprobe": fp or None,
        "timezone": cfg.timezone,
        "output_dir": str(cfg.output_dir),
        "temp_dir": str(cfg.temp_dir),
        "output_format": cfg.output_format,
        "recordings_scheduled": len(load_schedule_entries(cfg)),
    }


def youtube_token_status(cfg) -> dict:
    from iptvrec import youtube as yt
    return yt.token_status(cfg)


def get_config_model(cfg) -> dict:
    d = dict(cfg.data)
    if "telegram" in d:
        d["telegram"] = {**d["telegram"], "bot_token": "***"} if d["telegram"].get("bot_token") else d["telegram"]
    if "xtream" in d:
        d["xtream"] = {**d["xtream"], "password": "***"} if d["xtream"].get("password") else d["xtream"]
    return d


def update_config(cfg, updates: dict) -> bool:
    cfg_path = paths.CONFIG_FILE
    if not cfg_path.exists():
        return False
    with open(cfg_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    _deep_merge(data, updates)
    tmp = cfg_path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
    tmp.replace(cfg_path)
    return True


def _deep_merge(base: dict, over: dict) -> None:
    for key, val in over.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val