"""Configuración del logging con rotación, leída de la config."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from . import paths


def setup_logging(cfg, *, logger_name: str = "iptvrec", filename: str | None = None) -> logging.Logger:
    """Configura un logger con RotatingFileHandler (+ consola opcional)."""
    log_cfg = cfg.logging
    level = getattr(logging, str(log_cfg.get("level", "INFO")).upper(), logging.INFO)
    if filename:
        log_path = paths.LOGS_DIR / filename
    else:
        log_path = paths.resolve_path(log_cfg.get("file", "logs/daemon.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    fh = RotatingFileHandler(
        log_path,
        maxBytes=int(log_cfg.get("max_bytes", 10485760)),
        backupCount=int(log_cfg.get("backup_count", 5)),
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if log_cfg.get("console", True):
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    logger.propagate = False
    return logger
