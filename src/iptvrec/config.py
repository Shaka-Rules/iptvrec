"""Carga, validación y acceso a la configuración (config.yaml)."""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

import yaml

from . import paths
from .errors import ConfigError

# Valores por defecto: garantizan que toda clave existe aunque el usuario la omita.
DEFAULTS: dict = {
    "output_dir": "recordings",
    "temp_dir": "tmp",
    "output_format": "mp4",
    "output_template": "{name}_{date:%Y-%m-%d}_{time:%H%M}.{ext}",
    "ffmpeg": {
        "binary": "ffmpeg",
        "ffprobe_binary": "ffprobe",
        "user_agent": "",  # vacío => se usa net.DEFAULT_UA
        "rw_timeout": 30000000,
        "loglevel": "warning",
        "reconnect": {
            "reconnect": 1,
            "reconnect_at_eof": 1,
            "reconnect_streamed": 1,
            "reconnect_on_network_error": 1,
            "reconnect_delay_max": 30,
        },
        "extra_input_args": [],
    },
    "resilience": {
        "max_restarts": 0,
        "backoff_base_seconds": 2,
        "backoff_factor": 2.0,
        "backoff_max_seconds": 60,
        "backoff_reset_seconds": 120,
        "min_valid_segment_bytes": 1024,
        "url_refresh_each_restart": True,
    },
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "chat_id": "",
        "notify_on": ["start", "success", "failure", "upload", "token_expiry"],
    },
    "youtube": {
        "enabled": False,
        "credentials_file": "credentials.json",
        "token_file": "token.json",
        "privacy": "private",
        "category_id": "22",
        "title_template": "{name} - {date:%Y-%m-%d}",
        "description_template": "Grabado desde {source}/{channel} el {date:%Y-%m-%d} {time:%H:%M}.",
        "tags": ["iptv", "grabacion"],
        "delete_local_after_upload": False,
        "made_for_kids": False,
        "token_lifetime_days": 7,
        "token_warn_days": 2,
    },
    "xtream": {
        "enabled": False,
        "base_url": "",
        "username": "",
        "password": "",
        "container": "ts",
        "channel_cache_minutes": 60,
    },
    "m3u8": {
        "enabled": False,
        "sources": [],
        "channel_cache_minutes": 60,
    },
    "atresplayer": {
        "enabled": True,
        "api_base": "https://api.atresplayer.com",
        "channels": {
            "antena3": "antena3",
            "lasexta": "lasexta",
            "mega": "mega",
            "neox": "neox",
            "nova": "nova",
            "atreseries": "atreseries",
        },
    },
    "rtveplay": {
        "enabled": True,
        "channels": {
            "la-1": "La 1",
            "la-2": "La 2",
            "24h": "24h",
            "tdp": "Teledeporte",
            "clan": "Clan",
            "rtve-play": "RTVE Play",
            "canal-24h": "Canal 24h",
        },
    },
    "logging": {
        "level": "INFO",
        "file": "logs/daemon.log",
        "max_bytes": 10485760,
        "backup_count": 5,
        "console": True,
    },
    "scheduler": {
        "tick_seconds": 15,
        "catchup_grace_seconds": 120,
        "max_concurrent": 4,
        "min_free_mb_temp": 2048,
        "min_free_mb_output": 2048,
    },
    "timezone": "Europe/Madrid",
}

_ENV_RE = re.compile(r"^\$\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}$")


def _expand_env(value: Any) -> Any:
    """Expande recursivamente strings ``${ENV:NOMBRE}`` desde el entorno."""
    if isinstance(value, str):
        m = _ENV_RE.match(value.strip())
        if m:
            return os.environ.get(m.group(1), "")
        return value
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def _deep_merge(base: dict, over: dict) -> dict:
    """Mezcla profunda de ``over`` sobre una copia de ``base``."""
    out = copy.deepcopy(base)
    for key, val in (over or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


class Config:
    """Acceso ergonómico a la configuración ya mezclada con los DEFAULTS."""

    def __init__(self, data: dict):
        self.data = data

    # --- Secciones (dicts) ---
    @property
    def ffmpeg(self) -> dict:
        return self.data["ffmpeg"]

    @property
    def resilience(self) -> dict:
        return self.data["resilience"]

    @property
    def telegram(self) -> dict:
        return self.data["telegram"]

    @property
    def youtube(self) -> dict:
        return self.data["youtube"]

    @property
    def xtream(self) -> dict:
        return self.data["xtream"]

    @property
    def m3u8(self) -> dict:
        return self.data["m3u8"]

    @property
    def atresplayer(self) -> dict:
        return self.data["atresplayer"]

    @property
    def rtveplay(self) -> dict:
        return self.data["rtveplay"]

    @property
    def logging(self) -> dict:
        return self.data["logging"]

    @property
    def scheduler(self) -> dict:
        return self.data["scheduler"]

    # --- Escalares / rutas ---
    @property
    def output_format(self) -> str:
        return str(self.data["output_format"]).lower()

    @property
    def output_template(self) -> str:
        return self.data["output_template"]

    @property
    def timezone(self) -> str:
        return self.data["timezone"]

    @property
    def output_dir(self) -> Path:
        return paths.resolve_path(self.data["output_dir"])

    @property
    def temp_dir(self) -> Path:
        return paths.resolve_path(self.data["temp_dir"])

    def credentials_path(self) -> Path:
        return paths.CONFIG_DIR / self.youtube["credentials_file"]

    def token_path(self) -> Path:
        return paths.CONFIG_DIR / self.youtube["token_file"]

    def ffmpeg_user_agent(self) -> str:
        from .net import DEFAULT_UA
        return self.ffmpeg.get("user_agent") or DEFAULT_UA


VALID_FORMATS = {"mp4", "mkv", "ts"}


def load_config(path=None, *, validate: bool = True) -> Config:
    """Carga config.yaml, mezcla con DEFAULTS, expande ${ENV:} y valida."""
    cfg_path = Path(path) if path else paths.CONFIG_FILE
    user: dict = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as fh:
            user = yaml.safe_load(fh) or {}
        if not isinstance(user, dict):
            raise ConfigError(f"{cfg_path} no contiene un mapa YAML válido")
    merged = _deep_merge(DEFAULTS, user)
    merged = _expand_env(merged)
    cfg = Config(merged)
    if validate:
        validate_config(cfg)
    return cfg


def validate_config(cfg: Config) -> None:
    """Validaciones rápidas con mensajes accionables."""
    if cfg.output_format not in VALID_FORMATS:
        raise ConfigError(
            f"output_format '{cfg.output_format}' inválido; usa uno de {sorted(VALID_FORMATS)}"
        )
    if int(cfg.scheduler["tick_seconds"]) < 1:
        raise ConfigError("scheduler.tick_seconds debe ser >= 1")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(cfg.timezone)
    except Exception as exc:
        raise ConfigError(
            f"timezone '{cfg.timezone}' no resoluble (¿falta el paquete tzdata?): {exc}"
        )
    if cfg.telegram.get("enabled"):
        if not cfg.telegram.get("bot_token") or not str(cfg.telegram.get("chat_id")):
            raise ConfigError("telegram.enabled=true requiere bot_token y chat_id")
    priv = str(cfg.youtube.get("privacy", "private")).lower()
    if priv not in {"private", "unlisted", "public"}:
        raise ConfigError("youtube.privacy debe ser private | unlisted | public")


def ensure_dirs(cfg: Config) -> None:
    """Crea los directorios de trabajo (relativos a la raíz o donde indique la config)."""
    for d in (cfg.output_dir, cfg.temp_dir, paths.LOGS_DIR, paths.STATE_DIR, paths.JOBS_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)
