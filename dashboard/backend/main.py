"""IPTVrec Dashboard - FastAPI application."""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

# Add iptvrec src to path (relative to dashboard location)
_root = Path(__file__).resolve().parents[2]
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from .config import settings
from .api import channels, status, recordings, schedule, wizard, config_api, youtube, daemon
from .websocket.logs import recording_log_ws, daemon_log_ws

log = logging.getLogger("dashboard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="IPTVrec Dashboard",
    description="Panel de control web para IPTVrec",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - allow LAN access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    log.error("Unhandled error on %s %s: %s", request.method, request.url, exc)
    log.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )

# Health check
@app.get("/api/health")
async def health():
    return {"status": "ok"}

# Static files
static_dir = _root / "dashboard" / "frontend" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# API routers
app.include_router(channels.router)
app.include_router(status.router)
app.include_router(recordings.router)
app.include_router(schedule.router)
app.include_router(wizard.router)
app.include_router(config_api.router)
app.include_router(youtube.router)
app.include_router(daemon.router)

# TEMPLATES
from .templates import get_template


@app.get("/", response_class=HTMLResponse)
async def index():
    return get_template("index.html")


@app.get("/recordings", response_class=HTMLResponse)
async def recordings_page():
    return get_template("recordings.html")


@app.get("/schedule", response_class=HTMLResponse)
async def schedule_page():
    return get_template("schedule.html")


@app.get("/wizard", response_class=HTMLResponse)
async def wizard_page():
    return get_template("wizard.html")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    return get_template("settings.html")


# WebSocket endpoints - specific routes first
@app.websocket("/ws/logs/daemon")
async def ws_daemon_log(websocket: WebSocket):
    await daemon_log_ws(websocket)

@app.websocket("/ws/logs/{job_id}")
async def ws_recording_log(websocket: WebSocket, job_id: str):
    await recording_log_ws(websocket, job_id)


def run():
    import uvicorn
    uvicorn.run(
        "dashboard.backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()