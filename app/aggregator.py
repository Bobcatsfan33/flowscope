"""Scan orchestration: universe -> options flow -> ranking -> catalyst overlay.

Pipeline per cycle:
  1. Resolve (capped) universe.
  2. Concurrently fetch + score options flow for each symbol (bounded).
  3. Rank by flow_score.
  4. Fetch market-wide catalysts once (Senate trades) and bucket by symbol.
  5. For the top-ranked symbols, fetch per-symbol catalysts (SEC, Finnhub,
     USAspending) to respect free-tier rate limits.
  6. Attach catalysts (boosting score) and assemble a Snapshot.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

from app.config import get_settings
from app.models import Catalyst, Snapshot, TickerFlow
from app.scoring import score_ticker
from app.sources.catalysts.base import safe_fetch_recent, safe_fetch_symbol
from app.sources.catalysts.congress_senate import SenateCongressSource
from app.sources.catalysts.finnhub_catalysts import FinnhubCatalystSource
from app.sources.catalysts.sec_edgar import SecEdgarSource
from app.sources.catalysts.usaspending import UsaSpendingSource
from app.sources.options.base import fetch_options
from app.sources.options.finnhub import FinnhubOptionsProvider
from app.sources.options.tradier import TradierOptionsProvider
from app.sources.options.yahoo import YahooOptionsProvider

logger = logging.getLogger("flowscope.aggregator")

OPTIONS_CONCURRENCY = 8
TOP_N_FOR_CATALYSTS = 25
CATALYST_CONCURRENCY = 5
STANDALONE_FEED_LIMIT = 120

# Provider priority: no-key Yahoo first, then key-gated richer sources.
_OPTIONS_PROVIDERS = [
    YahooOptionsProvider(),
    TradierOptionsProvider(),
    FinnhubOptionsProvider(),
]
_MARKET_WIDE_CATALYSTS = [SenateCongressSource()]
_PER_SYMBOL_CATALYSTS = [
    SecEdgarSource(),
    FinnhubCatalystSource(),
    UsaSpendingSource(),
]

# Rotating scan-window offset, persisted across cycles. The universe is
# alphabetically sorted, so a fixed `[:max_tickers_per_cycle]` slice would
# scan the same leading names forever (NVDA/TSLA/etc. would never appear).
_cycle_offset: int = 0


def _rotation_slice(tickers: list[str], window: int) -> list[str]:
    """Return the current rotating window into the universe, wrapping around.

    Advances the module-level offset each call so successive cycles cover the
    full universe in slices of `window` symbols.
    """
    global _cycle_offset
    if not tickers or window >= len(tickers):
        _cycle_offset = 0
        return list(tickers)
    start = _cycle_offset % len(tickers)
    end = start + window
    window_slice = tickers[start:end]
    if end > len(tickers):
        window_slice = window_slice + tickers[: end - len(tickers)]
    _cycle_offset = end % len(tickers)
    return window_slice


async def _scan_symbol(
    symbol: str, sem: asyncio.Semaphore
) -> tuple[TickerFlow | None, str | None]:
    """Fetch + score one symbol. Returns (flow, error).

    `error` is set when every provider failed with an exception, so the
    aggregator can surface the failure instead of dropping it silently.
    """
    async with sem:
        contracts, price, source, fetch_errors = await fetch_options(
            symbol, _OPTIONS_PROVIDERS
        )
        if not contracts:
            error = f"{symbol}: {'; '.join(fetch_errors)}" if fetch_errors else None
            return None, error
        sources = sorted({c.source for c in contracts}) or ([source] if source else [])
        return score_ticker(symbol, contracts, price, sources), None


async def _gather_market_wide() -> dict[str, list[Catalyst]]:
    by_symbol: dict[str, list[Catalyst]] = defaultdict(list)
    results = await asyncio.gather(
        *(safe_fetch_recent(src) for src in _MARKET_WIDE_CATALYSTS)
    )
    for catalysts in results:
        for cat in catalysts:
            by_symbol[cat.symbol].append(cat)
    return by_symbol


async def _gather_symbol_catalysts(symbol: str, sem: asyncio.Semaphore) -> list[Catalyst]:
    async with sem:
        results = await asyncio.gather(
            *(safe_fetch_symbol(src, symbol) for src in _PER_SYMBOL_CATALYSTS)
        )
    return [cat for group in results for cat in group]


async def run_scan(tickers: list[str]) -> Snapshot:
    """Execute one full scan and return an immutable Snapshot."""
    settings = get_settings()
    errors: list[str] = []
    universe_size = len(tickers)
    scan_list = _rotation_slice(tickers, settings.max_tickers_per_cycle)

    # 1-3: options flow + ranking.
    opt_sem = asyncio.Semaphore(OPTIONS_CONCURRENCY)
    scanned_results = await asyncio.gather(
        *(_scan_symbol(sym, opt_sem) for sym in scan_list)
    )
    flows: list[TickerFlow] = []
    for flow, error in scanned_results:
        if error:
            errors.append(error)
        if flow is not None:
            flows.append(flow)
    flows.sort(key=lambda f: f.flow_score, reverse=True)

    # 4: market-wide catalysts (bucketed by symbol).
    market_catalysts = await _gather_market_wide()

    # 5: per-symbol catalysts for the top ranked names.
    cat_sem = asyncio.Semaphore(CATALYST_CONCURRENCY)
    top_symbols = [f.symbol for f in flows[:TOP_N_FOR_CATALYSTS]]
    per_symbol_results = await asyncio.gather(
        *(_gather_symbol_catalysts(sym, cat_sem) for sym in top_symbols)
    )
    per_symbol_map: dict[str, list[Catalyst]] = {
        sym: cats for sym, cats in zip(top_symbols, per_symbol_results)
    }

    # 6: attach catalysts (boost score) + assemble standalone feed.
    all_catalysts: list[Catalyst] = []
    enriched: list[TickerFlow] = []
    for flow in flows:
        cats = list(market_catalysts.get(flow.symbol, []))
        cats.extend(per_symbol_map.get(flow.symbol, []))
        all_catalysts.extend(cats)
        enriched.append(flow.with_catalysts(cats) if cats else flow)

    # Catalysts can re-order ranking via their boost.
    enriched.sort(key=lambda f: f.flow_score, reverse=True)

    # Standalone feed also includes market-wide catalysts for non-scanned names.
    for sym, cats in market_catalysts.items():
        if sym not in {f.symbol for f in flows}:
            all_catalysts.extend(cats)
    all_catalysts.sort(key=lambda c: c.timestamp, reverse=True)

    symbols_requested = len(scan_list)
    symbols_returned = len(flows)
    coverage_ratio = (
        round(symbols_returned / symbols_requested, 3) if symbols_requested else 0.0
    )

    return Snapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        universe_size=universe_size,
        scanned=len(scan_list),
        flows=[f.to_dict() for f in enriched],
        catalysts=[c.to_dict() for c in all_catalysts[:STANDALONE_FEED_LIMIT]],
        capabilities=settings.capability_report(),
        symbols_requested=symbols_requested,
        symbols_returned=symbols_returned,
        coverage_ratio=coverage_ratio,
        errors=errors,
    )
