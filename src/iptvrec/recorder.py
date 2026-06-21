"""Grabador resiliente: supervisa ffmpeg, graba segmentos .ts, concatena y remuxea.

Cada lanzamiento de ffmpeg escribe ``seg_NNNN.ts``. Si ffmpeg muere antes de la
hora de fin, se re-resuelve la URL (efímera) y se relanza con backoff. Al final se
concatenan los segmentos y se remuxea al contenedor configurado (mp4 por defecto):
un .ts truncado es reproducible, un .mp4 a medias no.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import signal
import subprocess
import time as _time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import notify, paths, providers, verify_copy, youtube
from .config import Config
from .state import read_json, write_json_atomic

log = logging.getLogger("iptvrec")

_EXT = {"mp4": "mp4", "mkv": "mkv", "ts": "ts"}
_STOP = {"flag": False}


def _tz(cfg) -> ZoneInfo:
    return ZoneInfo(cfg.timezone)


def _now(cfg) -> datetime:
    return datetime.now(_tz(cfg))


def _parse_dt(value, cfg) -> datetime:
    dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz(cfg))
    return dt


def _install_signal_handlers() -> None:
    def handler(signum, frame):
        _STOP["flag"] = True
    for s in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(s, handler)
        except Exception:
            pass


def _job_state_path(job_id):
    return paths.JOBS_DIR / f"{job_id}.json"


def _write_job_state(job_id, **fields) -> None:
    path = _job_state_path(job_id)
    data = read_json(path, {}) or {}
    data["job_id"] = job_id
    data.update(fields)
    write_json_atomic(path, data)


def _reconnect_args(cfg) -> list:
    rc = cfg.ffmpeg.get("reconnect", {}) or {}
    args = []
    for key in ("reconnect", "reconnect_at_eof", "reconnect_streamed",
                "reconnect_on_network_error"):
        if rc.get(key):
            args += [f"-{key}", "1"]
    if rc.get("reconnect_delay_max"):
        args += ["-reconnect_delay_max", str(rc["reconnect_delay_max"])]
    return args


def _build_ffmpeg_cmd(cfg, url, out_path, duration=0) -> list:
    f = cfg.ffmpeg
    cmd = [f.get("binary", "ffmpeg"), "-hide_banner", "-nostdin",
           "-loglevel", str(f.get("loglevel", "warning")),
           "-user_agent", cfg.ffmpeg_user_agent()]
    if str(url).startswith(("http://", "https://")):
        cmd += _reconnect_args(cfg)
        if f.get("rw_timeout"):
            cmd += ["-rw_timeout", str(f["rw_timeout"])]
    cmd += list(f.get("extra_input_args", []) or [])
    cmd += ["-i", str(url)]
    if duration > 0:
        cmd += ["-t", str(duration)]
    cmd += ["-map", "0", "-c", "copy", "-ignore_unknown",
            "-f", "mpegts", str(out_path)]
    return cmd


def _spawn(cmd):
    return subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        start_new_session=True,  # grupo propio → poder matar a ffmpeg y sus hijos
    )


def _terminate(proc) -> None:
    """SIGINT (flush) → SIGTERM → SIGKILL al grupo de procesos; siempre reapea."""
    if proc.poll() is not None:
        return
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, OSError):
            try:
                proc.send_signal(sig)
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


def _wait_until(proc, deadline, cfg):
    """Espera a que ffmpeg acabe o se alcance deadline / stop. rc o None si se cortó."""
    while True:
        if _STOP["flag"] or _now(cfg) >= deadline:
            _terminate(proc)
            return None
        try:
            return proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            continue


def _sleep_capped(seconds, end, cfg) -> None:
    remaining = (end - _now(cfg)).total_seconds()
    _time.sleep(max(0.0, min(seconds, remaining)))


def _update_size(job_id, job_dir) -> None:
    total = 0
    try:
        for f in job_dir.glob("seg_*.ts"):
            total += f.stat().st_size
    except OSError:
        pass
    _write_job_state(job_id, current_size_bytes=total)


def _supervise(cfg, spec, job_dir, end) -> int:
    """Bucle de grabación hasta ``end`` con re-resolución de URL y backoff. Devuelve nº de lanzamientos."""
    res = cfg.resilience
    backoff_base = float(res.get("backoff_base_seconds", 2))
    backoff = backoff_base
    backoff_max = float(res.get("backoff_max_seconds", 60))
    backoff_reset = float(res.get("backoff_reset_seconds", 120))
    factor = float(res.get("backoff_factor", 2.0))
    max_restarts = int(res.get("max_restarts", 0))
    refresh_each = bool(res.get("url_refresh_each_restart", True))
    duration = int(spec.get("duration", 0))

    source, channel, job_id = spec["source"], spec["channel"], spec["job_id"]
    launch = 0
    url = None
    while _now(cfg) < end and not _STOP["flag"]:
        if (end - _now(cfg)).total_seconds() <= 1:
            break
        try:
            if url is None or refresh_each:
                url = providers.resolve_stream_url(source, channel, cfg)
                _write_job_state(job_id, resolved=True, last_error=None)
        except Exception as exc:
            log.warning("[%s] no se pudo resolver URL: %s", job_id, exc)
            _write_job_state(job_id, last_error=str(exc))
            if max_restarts and launch >= max_restarts:
                break
            _sleep_capped(backoff, end, cfg)
            backoff = min(backoff * factor, backoff_max)
            continue

        seg = job_dir / f"seg_{launch:04d}.ts"
        log.info("[%s] ffmpeg #%d -> %s", job_id, launch, seg.name)
        run_started = _now(cfg)
        proc = _spawn(_build_ffmpeg_cmd(cfg, url, seg, duration=duration))
        _write_job_state(job_id, status="recording", pid=proc.pid, segments=launch + 1)
        rc = _wait_until(proc, end, cfg)
        launch += 1
        _update_size(job_id, job_dir)

        if _STOP["flag"] or _now(cfg) >= end:
            break
        if rc is not None and rc == 0:
            break  # ffmpeg completÃ³ normalmente (ej. -t cumplido); no relanzar
        ran = (_now(cfg) - run_started).total_seconds()
        if ran >= backoff_reset:
            backoff = backoff_base  # corrió bien un buen rato → resetea el backoff
        log.warning("[%s] ffmpeg terminó pronto (rc=%s, %.0fs). Reintento…", job_id, rc, ran)
        _write_job_state(job_id, retries=launch, last_error=f"ffmpeg rc={rc}")
        if max_restarts and launch > max_restarts:
            break
        _sleep_capped(backoff, end, cfg)
        backoff = min(backoff * factor, backoff_max)
    return launch


def _ffprobe_ok(cfg, path) -> bool:
    probe = cfg.ffmpeg.get("ffprobe_binary", "ffprobe")
    try:
        r = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, timeout=30,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _valid_segments(cfg, job_dir) -> list:
    min_bytes = int(cfg.resilience.get("min_valid_segment_bytes", 1024))
    good = []
    for s in sorted(job_dir.glob("seg_*.ts")):
        try:
            if s.stat().st_size >= min_bytes and _ffprobe_ok(cfg, s):
                good.append(s)
            else:
                log.warning("Segmento descartado (basura): %s", s.name)
        except OSError:
            pass
    return good


def _concat(cfg, job_dir, segments) -> Path:
    (job_dir / "concat.txt").write_text(
        "".join(f"file '{s.name}'\n" for s in segments), encoding="utf-8")
    cmd = [cfg.ffmpeg.get("binary", "ffmpeg"), "-hide_banner", "-nostdin",
           "-loglevel", str(cfg.ffmpeg.get("loglevel", "warning")),
           "-f", "concat", "-safe", "0", "-i", "concat.txt",
           "-map", "0", "-c", "copy", "-fflags", "+genpts",
           "-f", "mpegts", "assembled.ts"]
    subprocess.run(cmd, cwd=str(job_dir), check=True)
    return job_dir / "assembled.ts"


def _remux(cfg, assembled, out_path, fmt) -> None:
    bin_ = cfg.ffmpeg.get("binary", "ffmpeg")
    base = [bin_, "-hide_banner", "-nostdin", "-loglevel",
            str(cfg.ffmpeg.get("loglevel", "warning")), "-i", str(assembled),
            "-map", "0", "-c", "copy"]
    if fmt == "mp4":
        subprocess.run(base + ["-movflags", "+faststart", "-f", "mp4", str(out_path)], check=True)
    elif fmt == "mkv":
        subprocess.run(base + ["-f", "matroska", str(out_path)], check=True)
    else:  # ts: sin remux
        shutil.copyfile(assembled, out_path)


def _safe(s) -> str:
    return re.sub(r"[^\w.\- ]", "_", str(s)).strip().replace(" ", "_") or "rec"


def _output_filename(cfg, spec, start_dt) -> str:
    ext = _EXT.get(cfg.output_format, "mp4")
    try:
        return cfg.output_template.format(
            name=_safe(spec.get("name") or spec.get("channel") or "rec"),
            source=spec.get("source", ""), channel=_safe(spec.get("channel", "")),
            date=start_dt, time=start_dt, ext=ext, job_id=spec["job_id"],
        )
    except Exception:
        return f"{spec['job_id']}.{ext}"


def _cleanup(job_dir) -> None:
    shutil.rmtree(job_dir, ignore_errors=True)


def _upload(cfg, final_path, spec, start_dt):
    yt_cfg = cfg.youtube
    yt = spec.get("youtube") or {}
    name = spec.get("name") or spec.get("channel")
    title = youtube.build_title(
        yt.get("title_template") or yt_cfg.get("title_template"),
        channel=spec.get("channel"), name=name, when=start_dt, source=spec.get("source", ""))
    description = youtube.build_title(
        yt.get("description_template") or yt_cfg.get("description_template"),
        channel=spec.get("channel"), name=name, when=start_dt, source=spec.get("source", ""))
    url = youtube.upload(
        cfg, final_path, title=title, description=description,
        tags=yt.get("tags"), category_id=yt.get("category_id"),
        privacy=yt.get("privacy"), made_for_kids=yt.get("made_for_kids"))

    playlist_id = yt.get("playlist_id")
    if playlist_id:
        video_id = url.rsplit("v=", 1)[-1]
        try:
            youtube.add_to_playlist(cfg, video_id, playlist_id)
        except Exception as exc:
            log.warning("[%s] no se pudo añadir a la playlist %s: %s",
                        spec.get("job_id"), playlist_id, exc)

    if yt.get("delete_local_after_upload", yt_cfg.get("delete_local_after_upload")):
        try:
            Path(final_path).unlink()
        except OSError:
            pass
    return url


def _finalize(cfg, spec, job_dir, start_dt, end_dt):
    job_id = spec["job_id"]
    name = spec.get("name") or spec.get("channel")
    segments = _valid_segments(cfg, job_dir)
    if not segments:
        _write_job_state(job_id, status="failed", last_error="sin segmentos válidos",
                         finished_at=_now(cfg).isoformat())
        notify.notify_error(cfg, channel=name,
                            error="No se grabó nada (sin segmentos válidos)", status="abortado")
        _cleanup(job_dir)
        return None

    _write_job_state(job_id, status="finalizing")
    assembled = _concat(cfg, job_dir, segments)
    for s in job_dir.glob("seg_*.ts"):
        try:
            s.unlink()
        except OSError:
            pass
    staged = job_dir / _output_filename(cfg, spec, start_dt)
    _remux(cfg, assembled, staged, cfg.output_format)
    try:
        assembled.unlink()
    except OSError:
        pass

    final_path = verify_copy.verified_move(staged, cfg.output_dir)
    size = final_path.stat().st_size
    actual = (min(_now(cfg), end_dt) - start_dt).total_seconds()

    yt_url = None
    if (spec.get("youtube") or {}).get("upload"):
        try:
            yt_url = _upload(cfg, final_path, spec, start_dt)
        except Exception as exc:
            log.error("[%s] subida YouTube falló: %s", job_id, exc)
            notify.notify_error(cfg, channel=name, error=f"Subida YouTube: {exc}",
                                status="grabación OK, subida fallida")

    _cleanup(job_dir)
    _write_job_state(job_id, status="success", final_path=str(final_path), bytes=size,
                     youtube_url=yt_url, finished_at=_now(cfg).isoformat())
    notify.notify_finished(cfg, channel=name, file_size_bytes=size, actual_duration_s=actual,
                           final_path=str(final_path), youtube_url=yt_url)
    return final_path


def record_job(cfg: Config, spec: dict) -> None:
    """Graba un job completo (resolución → grabación → ensamblado → copia → subida)."""
    _install_signal_handlers()
    job_id = spec["job_id"]
    job_dir = cfg.temp_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    start_dt = _parse_dt(spec["start"], cfg)
    end_dt = _parse_dt(spec["end"], cfg)
    name = spec.get("name") or spec.get("channel")

    _write_job_state(job_id, entry_id=spec.get("entry_id"), name=name,
                     source=spec.get("source"), channel=spec.get("channel"),
                     start=start_dt.isoformat(), end=end_dt.isoformat(), status="starting",
                     pid=os.getpid(), segments=0, retries=0, current_size_bytes=0)
    notify.notify_started(cfg, channel=name, source=spec.get("source"), scheduled_end=end_dt,
                          duration_s=(end_dt - start_dt).total_seconds())
    try:
        _supervise(cfg, spec, job_dir, end_dt)
    except Exception as exc:
        log.exception("[%s] error en supervisión", job_id)
        _write_job_state(job_id, last_error=str(exc))
    try:
        _finalize(cfg, spec, job_dir, start_dt, end_dt)
    except Exception as exc:
        log.exception("[%s] error en finalize", job_id)
        _write_job_state(job_id, status="failed", last_error=str(exc),
                         finished_at=_now(cfg).isoformat())
        notify.notify_error(cfg, channel=name, error=str(exc), status="finalize fallido")


def record_from_spec(cfg: Config, spec_path) -> None:
    spec = read_json(spec_path)
    if not spec:
        raise FileNotFoundError(f"spec no encontrada: {spec_path}")
    record_job(cfg, spec)
