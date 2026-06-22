"""WebSocket handler for live log streaming."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from ..services.iptvrec import get_job_log_path, get_daemon_log_path


async def stream_log(websocket: WebSocket, log_path: Path):
    """Stream new lines from a log file as they are written."""
    await websocket.accept()
    try:
        if not log_path.exists():
            await websocket.send_json({"type": "error", "message": "Archivo de log no encontrado"})
            await websocket.close()
            return

        # Read initial file position
        offset = 0
        with open(log_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            offset = fh.tell()

        await websocket.send_json({"type": "ready", "path": str(log_path)})

        # Poll for new lines
        while True:
            try:
                with open(log_path, "rb") as fh:
                    fh.seek(offset)
                    new_data = fh.read()
                    if new_data:
                        text = new_data.decode("utf-8", errors="replace")
                        lines = text.splitlines()
                        for line in lines:
                            if line.strip():
                                await websocket.send_json({
                                    "type": "line",
                                    "data": line,
                                })
                        offset = fh.tell()
                await asyncio.sleep(0.5)
            except FileNotFoundError:
                await websocket.send_json({"type": "error", "message": "Archivo de log eliminado"})
                break
            except Exception as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


async def recording_log_ws(websocket: WebSocket, job_id: str):
    log_path = get_job_log_path(job_id)
    await stream_log(websocket, log_path)


async def daemon_log_ws(websocket: WebSocket):
    log_path = get_daemon_log_path()
    await stream_log(websocket, log_path)