"""Subida a YouTube (Data API v3): OAuth headless, refresh automático y avisos.

Las librerías de Google se importan de forma perezosa (dentro de las funciones)
para que el paquete pueda importarse aunque aún no estén instaladas (p. ej. para
`iptvrec validate`).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from . import notify, paths
from .errors import AuthError, UploadError
from .state import read_json, write_json_atomic

log = logging.getLogger("iptvrec")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
OAUTH_PORT = 8080


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --- Registro de la fecha de autorización (para avisar de caducidad) ---------

def _record_auth_time() -> None:
    write_json_atomic(paths.YOUTUBE_AUTH_FILE, {
        "authorized_at": _now_utc().isoformat(),
        "last_refresh_ok": _now_utc().isoformat(),
        "last_warn_sent": None,
    })


def _touch_refresh() -> None:
    data = read_json(paths.YOUTUBE_AUTH_FILE, {}) or {}
    data["last_refresh_ok"] = _now_utc().isoformat()
    write_json_atomic(paths.YOUTUBE_AUTH_FILE, data)


def _save_token(cfg, creds) -> None:
    p = cfg.token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


# --- OAuth headless ----------------------------------------------------------

def run_auth(cfg, *, reauth: bool = False) -> None:
    """Flujo OAuth de app de escritorio para LXC headless (túnel SSH + localhost)."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds_file = cfg.credentials_path()
    if not creds_file.exists():
        raise AuthError(
            f"No existe {creds_file}. Coloca tu credentials.json (cliente OAuth 'installed')."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
    print("\n  1) Abre el túnel SSH desde TU equipo (deja la sesión abierta):")
    print(f"       ssh -L {OAUTH_PORT}:localhost:{OAUTH_PORT} usuario@<host-del-lxc>")
    print("  2) Copia la URL que aparece abajo en el navegador de tu equipo.\n")
    creds = flow.run_local_server(
        host="localhost",
        port=OAUTH_PORT,
        open_browser=False,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="     URL de autorización:\n\n     {url}\n",
    )
    _save_token(cfg, creds)
    _record_auth_time()
    print(f"\n  ✓ token guardado en {cfg.token_path()}")


def load_credentials(cfg, *, notify_on_fail: bool = True):
    """Carga token.json y refresca si hace falta. Avisa por Telegram si caduca."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_file = cfg.token_path()
    if not token_file.exists():
        raise AuthError("No existe token.json; ejecuta 'iptvrec youtube-auth'.")
    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(cfg, creds)
            _touch_refresh()
        except RefreshError as exc:
            if notify_on_fail:
                notify.notify_token_expiring(cfg, days_left=0)
            raise AuthError(
                "Token de YouTube caducado/revocado (invalid_grant). "
                "Re-ejecuta 'iptvrec youtube-auth'."
            ) from exc
    if not creds.valid:
        raise AuthError("token.json inválido; re-ejecuta 'iptvrec youtube-auth'.")
    return creds


# --- Subida ------------------------------------------------------------------

def build_title(template, *, channel, name, when, source="") -> str:
    """Formatea plantilla de título/descr.: {name}/{channel}/{source}/{date}/{time}."""
    try:
        return template.format(channel=channel, name=name, source=source,
                               date=when, time=when, datetime=when)
    except Exception:
        return name or channel


def upload(cfg, path, *, title, description="", tags=None, category_id=None,
           privacy=None, made_for_kids=None, progress_cb=None) -> str:
    """Sube un fichero de forma resumible. Devuelve la URL del vídeo. Privado por defecto."""
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    yt = cfg.youtube
    creds = load_credentials(cfg)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {
            "title": (title or "")[:100],
            "description": (description or "")[:5000],
            "tags": tags if tags is not None else yt.get("tags", []),
            "categoryId": str(category_id or yt.get("category_id", "22")),
        },
        "status": {
            "privacyStatus": (privacy or yt.get("privacy", "private")),
            "selfDeclaredMadeForKids": bool(
                made_for_kids if made_for_kids is not None else yt.get("made_for_kids", False)
            ),
        },
    }
    media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status and progress_cb:
                progress_cb(status.progress())
        except HttpError as exc:
            code = getattr(getattr(exc, "resp", None), "status", None)
            if code in (500, 502, 503, 504):
                retries += 1
                if retries > 6:
                    raise UploadError(f"YouTube 5xx persistente: {exc}") from exc
                time.sleep(min(2 ** retries, 60))
                continue
            raise UploadError(f"YouTube rechazó la subida: {exc}") from exc
        except OSError as exc:  # corte de socket → reintentar el chunk
            retries += 1
            if retries > 6:
                raise UploadError(f"Error de E/S subiendo: {exc}") from exc
            time.sleep(min(2 ** retries, 60))
            continue
    return f"https://www.youtube.com/watch?v={response['id']}"


def add_to_playlist(cfg, video_id, playlist_id) -> None:
    """Añade un vídeo ya subido a una playlist existente. Errores no son fatales
    para la grabación: si falla, se loguea pero no se relanza (el vídeo ya está
    subido correctamente, solo falta el añadido a playlist)."""
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    creds = load_credentials(cfg)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id},
        }
    }
    youtube.playlistItems().insert(part="snippet", body=body).execute()


# --- Caducidad del token (avisos por Telegram) -------------------------------

def auth_age_days(cfg):
    """Días transcurridos desde la autorización (None si no hay registro)."""
    data = read_json(paths.YOUTUBE_AUTH_FILE, {}) or {}
    ts = data.get("authorized_at")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (_now_utc() - dt).total_seconds() / 86400.0


def days_until_expiry(cfg):
    """Días estimados hasta la caducidad del refresh token (None si está desactivado)."""
    lifetime = int(cfg.youtube.get("token_lifetime_days", 0) or 0)
    if lifetime <= 0:
        return None
    age = auth_age_days(cfg)
    if age is None:
        return None
    return lifetime - age


def token_status(cfg) -> dict:
    """Resumen para el monitor (NO fuerza refresh)."""
    token_file = cfg.token_path()
    if not token_file.exists():
        return {"configured": False, "valid": False}
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        valid = bool(creds and (creds.valid or creds.refresh_token))
    except Exception:
        valid = False
    return {
        "configured": True,
        "valid": valid,
        "days_until_expiry": days_until_expiry(cfg),
        "auth_age_days": auth_age_days(cfg),
    }


def check_and_warn_expiry(cfg) -> None:
    """Llamado ~1 vez/día por el demonio: avisa por Telegram si el token va a caducar."""
    remaining = days_until_expiry(cfg)
    if remaining is None:
        return
    warn_days = int(cfg.youtube.get("token_warn_days", 2))
    if remaining > warn_days:
        return
    data = read_json(paths.YOUTUBE_AUTH_FILE, {}) or {}
    today = _now_utc().date().isoformat()
    if data.get("last_warn_sent") == today:
        return  # ya avisado hoy (sin spam)
    notify.notify_token_expiring(cfg, days_left=max(0, remaining))
    data["last_warn_sent"] = today
    write_json_atomic(paths.YOUTUBE_AUTH_FILE, data)
