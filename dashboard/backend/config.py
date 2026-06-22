"""Dashboard configuration."""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 3000
    
    # Paths (relative to iptvrec root)
    iptvrec_root: Path = Path(__file__).resolve().parents[2]
    
    # CORS - allow LAN
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://192.168.*.*",
            "http://10.*.*.*",
            "http://172.16.*.*",
            "http://172.17.*.*",
            "http://172.18.*.*",
            "http://172.19.*.*",
            "http://172.20.*.*",
            "http://172.21.*.*",
            "http://172.22.*.*",
            "http://172.23.*.*",
            "http://172.24.*.*",
            "http://172.25.*.*",
            "http://172.26.*.*",
            "http://172.27.*.*",
            "http://172.28.*.*",
            "http://172.29.*.*",
            "http://172.30.*.*",
            "http://172.31.*.*",
        ]
    )
    
    # YouTube OAuth
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://localhost:3000/auth/youtube/callback"
    
    # Session secret for OAuth state
    session_secret: str = "change-me-in-production"
    
    # Daemon service name
    daemon_service: str = "iptvrec"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()