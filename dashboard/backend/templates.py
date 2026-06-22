"""Simple HTML template loader (no Jinja needed, we use HTMX)."""
from __future__ import annotations

from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "frontend" / "templates"


def get_template(name: str) -> str:
    path = _TEMPLATES_DIR / name
    if not path.exists():
        return f"<html><body><h1>404 - {name} no encontrado</h1></body></html>"
    return path.read_text(encoding="utf-8")


def get_partial(name: str) -> str:
    path = _TEMPLATES_DIR / "partials" / name
    if not path.exists():
        return f"<!-- partial {name} not found -->"
    return path.read_text(encoding="utf-8")