"""Configuration view/edit API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

from ..services.iptvrec import load_cfg, get_config_model, update_config, validate_configuration

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def api_get_config():
    cfg = load_cfg()
    return get_config_model(cfg)


@router.get("/raw")
def api_get_config_raw():
    from ..services.iptvrec import paths
    cfg = load_cfg()
    path = paths.CONFIG_FILE
    if path.exists():
        text = path.read_text(encoding="utf-8")
        return {"yaml": text}
    return {"yaml": "", "error": "config.yaml no encontrado"}


class ConfigUpdateRequest(BaseModel):
    updates: dict[str, Any]


@router.patch("")
def api_update_config(req: ConfigUpdateRequest):
    cfg = load_cfg()
    try:
        ok = update_config(cfg, req.updates)
        if ok:
            cfg = load_cfg()
            validation = validate_configuration(cfg)
            return {"success": True, "validation": validation}
        raise HTTPException(status_code=500, detail="No se pudo actualizar la configuración")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/validate")
def api_validate():
    cfg = load_cfg()
    return validate_configuration(cfg)