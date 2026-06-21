"""Notificaciones por Telegram (port de telegram_notify.sh), best-effort.

Nunca lanza excepción: un fallo de Telegram jamás debe tumbar una grabación.
Token y chat_id se leen de la config (no van incrustados en el código).
"""
from __future__ import annotations

import html
import logging
import re
import socket

import requests

log = logging.getLogger("iptvrec")

_API = "https://api.telegram.org/bot{token}/sendMessage"


def esc(value) -> str:
    """Escapa & < > para parse_mode=HTML."""
    return html.escape(str(value), quote=False)


def _strip_tags(text) -> str:
    return re.sub(r"<[^>]+>", "", str(text))


def hms(seconds) -> str:
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def human_size(num_bytes) -> str:
    n = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _enabled_for(cfg, event) -> bool:
    tg = cfg.telegram
    if not tg.get("enabled"):
        return False
    notify_on = tg.get("notify_on")
    return True if not notify_on else event in notify_on


def _send(cfg, text, *, disable_notification=False, retry_plain=True) -> bool:
    """Envía un mensaje. Best-effort: nunca lanza; devuelve True si ok."""
    tg = cfg.telegram
    token, chat_id = tg.get("bot_token"), tg.get("chat_id")
    if not token or not chat_id:
        log.warning("telegram: bot_token/chat_id ausentes; no se envía")
        return False
    data = {
        "chat_id": str(chat_id),
        "text": text[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": disable_notification,
    }
    try:
        resp = requests.post(_API.format(token=token), data=data, timeout=15)
        body = resp.json() if resp.content else {}
        if resp.status_code == 200 and body.get("ok"):
            return True
        log.warning("telegram: fallo (%s) %s", resp.status_code, body.get("description"))
        if retry_plain:  # degradar a texto plano si el HTML no parsea
            data.pop("parse_mode", None)
            data["text"] = _strip_tags(text)[:4096]
            r2 = requests.post(_API.format(token=token), data=data, timeout=15)
            return r2.status_code == 200 and bool(r2.json().get("ok") if r2.content else False)
        return False
    except Exception as exc:  # best-effort
        log.warning("telegram: excepción enviando: %s", exc)
        return False


def notify_started(cfg, *, channel, source, scheduled_end, duration_s) -> bool:
    if not _enabled_for(cfg, "start"):
        return False
    end = (scheduled_end.strftime("%H:%M:%S (%d/%m/%Y)")
           if hasattr(scheduled_end, "strftime") else esc(scheduled_end))
    msg = (
        "🔴 <b>Grabación iniciada</b>\n"
        f"📺 Canal: <b>{esc(channel)}</b>\n"
        f"🔗 Fuente: {esc(source)}\n"
        f"⏱ Duración: {hms(duration_s)}\n"
        f"🏁 Fin previsto: {end}"
    )
    return _send(cfg, msg)


def notify_finished(cfg, *, channel, file_size_bytes, actual_duration_s,
                    final_path, youtube_url=None) -> bool:
    if not _enabled_for(cfg, "success"):
        return False
    msg = (
        "✅ <b>Grabación finalizada</b>\n"
        f"📺 Canal: <b>{esc(channel)}</b>\n"
        f"💾 Tamaño: {human_size(file_size_bytes)}\n"
        f"⏱ Duración real: {hms(actual_duration_s)}\n"
        f"📁 Archivo: <code>{esc(final_path)}</code>"
    )
    if youtube_url:
        msg += f"\n▶️ YouTube: {esc(youtube_url)}"
    return _send(cfg, msg)


def notify_error(cfg, *, channel, error, status="") -> bool:
    if not _enabled_for(cfg, "failure"):
        return False
    err = str(error)
    if len(err) > 3500:
        err = err[:3500] + "… (truncado)"
    msg = (
        "⚠️ <b>Error de grabación</b>\n"
        f"📺 Canal: <b>{esc(channel)}</b>\n"
        f"❌ {esc(err)}"
    )
    if status:
        msg += f"\n🔁 Estado: {esc(status)}"
    return _send(cfg, msg)


def notify_token_expiring(cfg, *, days_left) -> bool:
    if not _enabled_for(cfg, "token_expiry"):
        return False
    if days_left <= 0:
        msg = ("🔑 <b>Token de YouTube CADUCADO</b>\n"
               "Las subidas fallarán. Re-ejecuta: <code>iptvrec youtube-auth</code>")
    else:
        msg = ("🔑 <b>Token de YouTube por caducar</b>\n"
               f"Caduca en ~{int(days_left)} día(s). Re-ejecútalo pronto: "
               "<code>iptvrec youtube-auth</code>")
    return _send(cfg, msg)


def notify_test(cfg, message=None) -> bool:
    text = message or (
        "🧪 <b>iptvrec test</b>\n"
        "Si ves este mensaje, Telegram está configurado correctamente.\n"
        f"Host: <code>{esc(socket.gethostname())}</code>"
    )
    return _send(cfg, text, retry_plain=False)
