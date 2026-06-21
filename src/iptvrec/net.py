"""Sesión HTTP compartida (User-Agent de navegador, reintentos, timeouts) y helpers."""
from __future__ import annotations

import re
from typing import Any

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None  # type: ignore

from .errors import ResolveError

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_DEFAULT_TIMEOUT = 10.0


def build_session(
    user_agent: str = DEFAULT_UA,
    total_retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: tuple = (429, 500, 502, 503, 504),
    pool_maxsize: int = 8,
) -> requests.Session:
    """requests.Session con UA de navegador y reintentos de transporte (429/5xx)."""
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent or DEFAULT_UA})
    if Retry is not None:
        retry = Retry(
            total=total_retries,
            connect=total_retries,
            read=total_retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=frozenset(["GET", "POST"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=pool_maxsize)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
    return session


def get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    headers: dict | None = None,
) -> Any:
    """GET que devuelve JSON. Lanza ResolveError ante fallo de red/HTTP/JSON vacío."""
    try:
        resp = session.get(url, params=params, timeout=timeout, headers=headers)
    except requests.RequestException as exc:
        raise ResolveError(f"Fallo de red en {redact(url)}: {exc}") from exc
    if resp.status_code >= 400:
        raise ResolveError(f"HTTP {resp.status_code} en {redact(url)}")
    text = (resp.text or "").strip()
    if not text:
        raise ResolveError(f"Respuesta vacía de {redact(url)}")
    try:
        return resp.json()
    except ValueError as exc:
        raise ResolveError(f"JSON inválido de {redact(url)}: {exc}") from exc


_SECRET_RE = re.compile(r"(password|token|secret|api[_-]?key)=([^&\s]+)", re.IGNORECASE)


def redact(text: Any) -> str:
    """Oculta credenciales en query strings / tokens antes de loguear."""
    s = str(text)
    s = _SECRET_RE.sub(r"\1=***", s)
    s = re.sub(r"/bot\d+:[A-Za-z0-9_-]+", "/bot***", s)  # token Telegram en la URL
    return s
