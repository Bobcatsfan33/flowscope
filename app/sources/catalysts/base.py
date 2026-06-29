"""Catalyst source contracts.

Two shapes:
  * MarketWideSource.fetch_recent() -> list[Catalyst]
      One network call returns recent events across the whole market; the
      aggregator buckets them by symbol. Cheap, runs every cycle.
  * PerSymbolSource.fetch(symbol) -> list[Catalyst]
      Per-ticker lookups; the aggregator only calls these for the top-ranked
      flow symbols to respect free-tier rate limits.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from app.models import Catalyst

logger = logging.getLogger("flowscope.catalysts")


@runtime_checkable
class MarketWideSource(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    async def fetch_recent(self) -> list[Catalyst]: ...


@runtime_checkable
class PerSymbolSource(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    async def fetch(self, symbol: str) -> list[Catalyst]: ...


async def safe_fetch_recent(source: MarketWideSource) -> list[Catalyst]:
    if not source.available:
        return []
    try:
        return await source.fetch_recent()
    except Exception as exc:  # noqa: BLE001
        logger.warning("market-wide catalyst source %s failed: %s", source.name, exc)
        return []


async def safe_fetch_symbol(source: PerSymbolSource, symbol: str) -> list[Catalyst]:
    if not source.available:
        return []
    try:
        return await source.fetch(symbol)
    except Exception as exc:  # noqa: BLE001
        logger.debug("%s failed for %s: %s", source.name, symbol, exc)
        return []
