"""Shared async HTTP client with sane timeouts, retries and a descriptive UA.

A single module-level client is reused across requests (connection pooling).
`get_json` centralizes error handling so source modules stay small.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("flowscope.http")

_client: httpx.AsyncClient | None = None


def _build_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        headers={"User-Agent": settings.sec_user_agent},
        follow_redirects=True,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = _build_client()
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def get_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = 2,
    backoff: float = 0.75,
) -> Any:
    """GET a URL and return parsed JSON, retrying transient failures.

    Raises httpx.HTTPError on final failure; callers decide whether to swallow.
    """
    client = get_client()
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            # Don't retry client errors that won't change (except rate limits).
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status and status != 429 and 400 <= status < 500:
                raise
            if attempt < retries:
                await asyncio.sleep(backoff * (2**attempt))
    assert last_exc is not None
    raise last_exc
