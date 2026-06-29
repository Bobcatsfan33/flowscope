"""Senate trading disclosures (STOCK Act) — no key, market-wide.

Pulls the senate-stock-watcher aggregate JSON and emits recent trades as
CONGRESS catalysts. Purchases read bullish, sales bearish. The aggregate file
is fetched once per cycle and filtered to the recent window.

Note: as of 2026 the upstream senate-stock-watcher mirrors are intermittently
stale (S3 bucket 403s; GitHub mirror updates lapsed). This source fails soft
(returns []) in that case. For reliably *live* both-chamber congressional
trades, set FINNHUB_API_KEY — the Finnhub catalyst source is the primary feed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.http_client import get_json
from app.models import Catalyst, CatalystKind, Direction

logger = logging.getLogger("flowscope.catalysts.senate")

# Primary + mirror for the aggregated senate transactions feed.
FEED_URLS = (
    "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json",
    "https://raw.githubusercontent.com/timothycarambat/senate-stock-watcher-data/master/aggregate/all_transactions.json",
)
RECENT_DAYS = 30
MAX_EVENTS = 200


def _parse_date(value: str) -> datetime | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _direction(tx_type: str) -> Direction:
    t = (tx_type or "").lower()
    if "purchase" in t or "buy" in t:
        return Direction.BULLISH
    if "sale" in t or "sell" in t:
        return Direction.BEARISH
    return Direction.NEUTRAL


class SenateCongressSource:
    name = "senate_stock_watcher"

    @property
    def available(self) -> bool:
        return True  # no key required

    async def fetch_recent(self) -> list[Catalyst]:
        rows: list[dict] = []
        for url in FEED_URLS:
            try:
                data = await get_json(url)
                if isinstance(data, list) and data:
                    rows = data
                    break
            except Exception as exc:  # noqa: BLE001
                logger.debug("senate feed %s failed: %s", url, exc)
                continue
        if not rows:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
        out: list[Catalyst] = []
        for row in rows:
            ticker = str(row.get("ticker") or "").upper().strip()
            if not ticker or ticker in {"--", "N/A"}:
                continue
            dt = _parse_date(str(row.get("transaction_date") or ""))
            if dt is None or dt < cutoff:
                continue
            senator = row.get("senator") or "US Senator"
            tx_type = row.get("type") or ""
            amount = row.get("amount") or ""
            out.append(
                Catalyst(
                    symbol=ticker.replace(".", "-"),
                    kind=CatalystKind.CONGRESS,
                    direction=_direction(tx_type),
                    headline=f"{senator}: {tx_type} {ticker} ({amount})",
                    detail=str(row.get("asset_description") or ""),
                    url=str(row.get("ptr_link") or "https://efdsearch.senate.gov/"),
                    source=self.name,
                    timestamp=dt.isoformat(),
                    weight=1.0,
                )
            )
        # Most recent first, capped.
        out.sort(key=lambda c: c.timestamp, reverse=True)
        return out[:MAX_EVENTS]
