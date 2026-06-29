"""Yahoo Finance options provider via yfinance — the no-key default source.

yfinance is synchronous and somewhat heavy, so calls run in a thread executor.
We sample the nearest few expirations (where flow concentrates) to bound cost.
"""
from __future__ import annotations

import asyncio
import logging
import math

from app.models import ContractFlow

logger = logging.getLogger("flowscope.options.yahoo")

MAX_EXPIRATIONS = 3   # nearest N expirations carry most fresh flow
SOURCE_NAME = "yahoo"


def _safe_float(value, default: float = 0.0) -> float:
    try:
        f = float(value)
        return default if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        f = float(value)
        return default if math.isnan(f) or math.isinf(f) else int(f)
    except (TypeError, ValueError):
        return default


def _fetch_sync(symbol: str) -> tuple[list[ContractFlow], float]:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    expirations = list(ticker.options or ())[:MAX_EXPIRATIONS]
    if not expirations:
        return [], 0.0

    # Resolve underlying price (fast_info is cheap; fall back to history).
    underlying = 0.0
    try:
        underlying = _safe_float(getattr(ticker, "fast_info", {}).get("last_price"))
    except Exception:  # noqa: BLE001
        underlying = 0.0
    if underlying <= 0:
        try:
            hist = ticker.history(period="1d")
            if not hist.empty:
                underlying = _safe_float(hist["Close"].iloc[-1])
        except Exception:  # noqa: BLE001
            underlying = 0.0

    contracts: list[ContractFlow] = []
    for exp in expirations:
        try:
            chain = ticker.option_chain(exp)
        except Exception as exc:  # noqa: BLE001
            logger.debug("chain fetch failed %s %s: %s", symbol, exp, exc)
            continue
        for frame, opt_type in ((chain.calls, "call"), (chain.puts, "put")):
            for row in frame.itertuples(index=False):
                volume = _safe_int(getattr(row, "volume", 0))
                if volume <= 0:
                    continue
                contracts.append(
                    ContractFlow(
                        symbol=symbol,
                        expiration=str(exp),
                        strike=_safe_float(getattr(row, "strike", 0.0)),
                        option_type=opt_type,
                        last_price=_safe_float(getattr(row, "lastPrice", 0.0)),
                        volume=volume,
                        open_interest=_safe_int(getattr(row, "openInterest", 0)),
                        implied_volatility=_safe_float(
                            getattr(row, "impliedVolatility", 0.0)
                        ),
                        underlying_price=underlying,
                        source=SOURCE_NAME,
                    )
                )
    return contracts, underlying


class YahooOptionsProvider:
    name = SOURCE_NAME

    @property
    def available(self) -> bool:
        return True  # no key required

    async def fetch(self, symbol: str) -> tuple[list[ContractFlow], float]:
        return await asyncio.to_thread(_fetch_sync, symbol)
