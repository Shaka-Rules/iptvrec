"""System status API."""
from __future__ import annotations

from fastapi import APIRouter
from ..services.iptvrec import load_cfg, get_status

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("")
def api_get_status():
    cfg = load_cfg()
    status = get_status(cfg)
    return status


@router.get("/disk")
def api_get_disk():
    cfg = load_cfg()
    import shutil
    from ..services.iptvrec import paths
    def _free_mb(p):
        try:
            return shutil.disk_usage(str(p)).free // (1024 * 1024)
        except OSError:
            return 0
    return {
        "temp": {"path": str(cfg.temp_dir), "free_mb": _free_mb(cfg.temp_dir)},
        "output": {"path": str(cfg.output_dir), "free_mb": _free_mb(cfg.output_dir)},
    }


@router.get("/validate")
def api_validate():
    cfg = load_cfg()
    from ..services.iptvrec import validate_configuration
    return validate_configuration(cfg)