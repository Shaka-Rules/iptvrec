"""YouTube OAuth and status API."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services.iptvrec import load_cfg, youtube_token_status, paths

router = APIRouter(prefix="/auth/youtube", tags=["youtube"])

# In-memory OAuth state store
_oauth_states: dict = {}


@router.get("/status")
def api_youtube_status():
    cfg = load_cfg()
    status = youtube_token_status(cfg)
    if cfg.youtube.get("enabled"):
        from iptvrec import youtube as yt
        status["days_until_expiry"] = yt.days_until_expiry(cfg)
    return status


@router.get("/start")
def api_youtube_start(request: Request):
    """Start OAuth flow: redirect to Google consent screen."""
    from iptvrec.youtube import SCOPES, OAUTH_PORT

    cfg = load_cfg()
    creds_file = cfg.credentials_path()
    if not creds_file.exists():
        raise HTTPException(
            status_code=400,
            detail=f"No existe {creds_file}. Coloca tu credentials.json (cliente OAuth 'installed')."
        )

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = True

    # Build Google OAuth URL
    import urllib.parse
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
    # Get the auth URL
    flow.redirect_uri = str(request.base_url).rstrip("/") + "/auth/youtube/callback"
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    return {"auth_url": auth_url, "state": state}


@router.get("/callback")
def api_youtube_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Handle OAuth callback from Google."""
    from iptvrec.youtube import SCOPES, run_auth, _save_token, _record_auth_time

    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Faltan parámetros code o state")

    # Verify state
    if state not in _oauth_states:
        raise HTTPException(status_code=403, detail="Estado OAuth inválido")
    del _oauth_states[state]

    cfg = load_cfg()
    creds_file = cfg.credentials_path()
    if not creds_file.exists():
        raise HTTPException(status_code=400, detail="credentials.json no encontrado")

    from google_auth_oauthlib.flow import InstalledAppFlow
    import google.auth.transport.requests

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
    flow.redirect_uri = str(request.base_url).rstrip("/") + "/auth/youtube/callback"

    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        _save_token(cfg, creds)
        _record_auth_time()
        return {"success": True, "message": "YouTube autenticado correctamente"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error al obtener token: {exc}")