"""Pydantic models for the dashboard API."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class SourceType(str, Enum):
    ATRESPLAYER = "atresplayer"
    RTVEPLAY = "rtveplay"
    XTREAM = "xtream"
    M3U8 = "m3u8"


class RecurrenceType(str, Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


class JobStatus(str, Enum):
    STARTING = "starting"
    RECORDING = "recording"
    FINALIZING = "finalizing"
    SUCCESS = "success"
    FAILED = "failed"


class ChannelModel(BaseModel):
    name: str
    source: str
    ref: str
    url: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ChannelsResponse(BaseModel):
    channels: list[ChannelModel]
    total: int
    page: int
    size: int
    has_more: bool


class RecordingModel(BaseModel):
    job_id: str
    entry_id: Optional[str] = None
    name: str
    source: str
    channel: str
    start: datetime
    end: datetime
    status: JobStatus
    pid: Optional[int] = None
    segments: int = 0
    retries: int = 0
    current_size_bytes: int = 0
    elapsed_s: Optional[int] = None
    remaining_s: Optional[int] = None
    final_path: Optional[str] = None
    youtube_url: Optional[str] = None
    last_error: Optional[str] = None
    finished_at: Optional[datetime] = None


class ScheduleEntryModel(BaseModel):
    id: str
    enabled: bool = True
    name: str
    source: str
    channel: str
    recurrence: dict[str, Any]
    duration: int
    youtube: dict[str, Any] = Field(default_factory=dict)
    output_dir: Optional[str] = None
    output_format: Optional[str] = None


class ScheduleListResponse(BaseModel):
    entries: list[ScheduleEntryModel]


class StatusModel(BaseModel):
    generated_at: datetime
    daemon: dict[str, Any]
    active: list[RecordingModel]
    upcoming: list[dict[str, Any]]
    recent: list[RecordingModel]
    disk: dict[str, Any]
    youtube: dict[str, Any]


class WizardStep1Response(BaseModel):
    sources: list[dict[str, Any]]


class WizardChannelsRequest(BaseModel):
    source: SourceType
    page: int = 1
    size: int = 50
    q: str = ""


class WizardValidateDateTimeRequest(BaseModel):
    recurrence_type: RecurrenceType
    date: Optional[str] = None  # YYYY-MM-DD for once
    time: str  # HH:MM
    days: Optional[list[str]] = None  # for weekly
    duration_seconds: int


class WizardValidateDateTimeResponse(BaseModel):
    valid: bool
    start_utc: datetime
    end_utc: datetime
    start_local: str
    end_local: str
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WizardSubmitRequest(BaseModel):
    action: str  # "schedule" or "now"
    source: SourceType
    channel: str
    channel_name: str
    recurrence_type: RecurrenceType
    date: Optional[str] = None
    time: str
    days: Optional[list[str]] = None
    duration_seconds: int
    output_dir: Optional[str] = None
    output_format: str = "mp4"
    youtube_enabled: bool = False
    youtube_privacy: str = "private"
    youtube_category_id: str = "22"
    youtube_tags: list[str] = Field(default_factory=list)
    youtube_playlist_id: Optional[str] = None
    telegram_notify: bool = True
    custom_name: Optional[str] = None


class WizardSubmitResponse(BaseModel):
    success: bool
    message: str
    job_id: Optional[str] = None
    schedule_id: Optional[str] = None


class ConfigModel(BaseModel):
    output_dir: str
    temp_dir: str
    output_format: str
    output_template: str
    timezone: str
    ffmpeg: dict[str, Any]
    resilience: dict[str, Any]
    telegram: dict[str, Any]
    youtube: dict[str, Any]
    xtream: dict[str, Any]
    m3u8: dict[str, Any]
    atresplayer: dict[str, Any]
    rtveplay: dict[str, Any]
    logging: dict[str, Any]
    scheduler: dict[str, Any]


class YouTubeStatusModel(BaseModel):
    configured: bool
    valid: bool
    days_until_expiry: Optional[float] = None
    auth_age_days: Optional[float] = None


class YouTubeAuthStartResponse(BaseModel):
    auth_url: str
    state: str


class DaemonStatusModel(BaseModel):
    running: bool
    pid: Optional[int] = None
    uptime: Optional[str] = None


class LogLine(BaseModel):
    timestamp: str
    level: str
    message: str
    raw: str