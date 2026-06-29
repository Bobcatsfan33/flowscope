"""Finnhub per-symbol catalysts (free key): insider, congress, news, earnings.

Richer than the no-key sources because it carries *direction* (share deltas,
purchase vs sale) and covers both congressional chambers. Only invoked for the
top-ranked flow symbols to stay within free-tier limits (60 calls/min).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.http_client import get_json
from app.models import Catalyst, CatalystKind, Direction

logger = logging.getLogger("flowscope.catalysts.finnhub")

BASE = "https://finnhub.io/api/v1"
LOOKBACK_DAYS = 21
EARNINGS_AHEAD_DAYS = 10
MAX_PER_KIND = 3


def _window() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=LOOKBACK_DAYS)
    return start.isoformat(), today.isoformat()


def _iso(value) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc).isoformat()


class FinnhubCatalystSource:
    name = "finnhub"

    @property
    def available(self) -> bool:
        return get_settings().has_finnhub

    async def fetch(self, symbol: str) -> list[Catalyst]:
        key = get_settings().finnhub_api_key
        out: list[Catalyst] = []
        out.extend(await self._insider(symbol, key))
        out.extend(await self._congress(symbol, key))
        out.extend(await self._news(symbol, key))
        out.extend(await self._earnings(symbol, key))
        return out

    async def _insider(self, symbol: str, key: str) -> list[Catalyst]:
        start, end = _window()
        data = await get_json(
            f"{BASE}/stock/insider-transactions",
            params={"symbol": symbol, "from": start, "to": end, "token": key},
        )
        rows = (data or {}).get("data") or []
        out: list[Catalyst] = []
        for row in rows[:MAX_PER_KIND]:
            change = float(row.get("change") or 0.0)
            direction = (
                Direction.BULLISH if change > 0
                else Direction.BEARISH if change < 0
                else Direction.NEUTRAL
            )
            verb = "bought" if change > 0 else "sold" if change < 0 else "filed"
            out.append(
                Catalyst(
                    symbol=symbol,
                    kind=CatalystKind.INSIDER,
                    direction=direction,
                    headline=f"{row.get('name', 'Insider')} {verb} {abs(int(change)):,} shares",
                    detail=f"transaction code {row.get('transactionCode', '?')}",
                    url=f"https://finnhub.io/",
                    source=self.name,
                    timestamp=f"{row.get('transactionDate', start)}T00:00:00+00:00",
                    weight=1.2,
                )
            )
        return out

    async def _congress(self, symbol: str, key: str) -> list[Catalyst]:
        start, end = _window()
        data = await get_json(
            f"{BASE}/stock/congressional-trading",
            params={"symbol": symbol, "from": start, "to": end, "token": key},
        )
        rows = (data or {}).get("data") or []
        out: list[Catalyst] = []
        for row in rows[:MAX_PER_KIND]:
            tx = str(row.get("transactionType") or "").lower()
            direction = (
                Direction.BULLISH if "purchase" in tx or "buy" in tx
                else Direction.BEARISH if "sale" in tx or "sell" in tx
                else Direction.NEUTRAL
            )
            amt = f"${row.get('amountFrom', '?')}-{row.get('amountTo', '?')}"
            out.append(
                Catalyst(
                    symbol=symbol,
                    kind=CatalystKind.CONGRESS,
                    direction=direction,
                    headline=f"{row.get('name', 'Official')}: {row.get('transactionType', '?')} ({amt})",
                    detail=str(row.get("position") or ""),
                    url="https://www.quiverquant.com/congresstrading/",
                    source=self.name,
                    timestamp=f"{row.get('transactionDate', start)}T00:00:00+00:00",
                    weight=1.2,
                )
            )
        return out

    async def _news(self, symbol: str, key: str) -> list[Catalyst]:
        start, end = _window()
        data = await get_json(
            f"{BASE}/company-news",
            params={"symbol": symbol, "from": start, "to": end, "token": key},
        )
        rows = data or []
        out: list[Catalyst] = []
        for row in rows[:MAX_PER_KIND]:
            out.append(
                Catalyst(
                    symbol=symbol,
                    kind=CatalystKind.NEWS,
                    direction=Direction.NEUTRAL,
                    headline=str(row.get("headline") or "")[:160],
                    detail=str(row.get("source") or ""),
                    url=str(row.get("url") or ""),
                    source=self.name,
                    timestamp=_iso(row.get("datetime")),
                    weight=0.8,
                )
            )
        return out

    async def _earnings(self, symbol: str, key: str) -> list[Catalyst]:
        today = datetime.now(timezone.utc).date()
        end = today + timedelta(days=EARNINGS_AHEAD_DAYS)
        data = await get_json(
            f"{BASE}/calendar/earnings",
            params={"symbol": symbol, "from": today.isoformat(),
                    "to": end.isoformat(), "token": key},
        )
        rows = (data or {}).get("earningsCalendar") or []
        out: list[Catalyst] = []
        for row in rows[:1]:
            out.append(
                Catalyst(
                    symbol=symbol,
                    kind=CatalystKind.EARNINGS,
                    direction=Direction.NEUTRAL,
                    headline=f"Earnings {row.get('date', '?')} ({row.get('hour', '?')})",
                    detail=f"EPS est {row.get('epsEstimate', 'n/a')}",
                    url="https://finnhub.io/",
                    source=self.name,
                    timestamp=f"{row.get('date', today.isoformat())}T00:00:00+00:00",
                    weight=1.0,
                )
            )
        return out
