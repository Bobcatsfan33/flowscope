"""Tradier options provider (free sandbox token). Adds greeks + delayed quotes.

Tradier returns full chains with greeks in one call per expiration. We pull the
options expirations list, then the nearest few chains.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.http_client import get_json
from app.models import ContractFlow

logger = logging.getLogger("flowscope.options.tradier")

MAX_EXPIRATIONS = 3
SOURCE_NAME = "tradier"


def _headers() -> dict:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.tradier_token}",
        "Accept": "application/json",
    }


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


async def _quote(symbol: str) -> float:
    base = get_settings().tradier_base_url
    data = await get_json(
        f"{base}/v1/markets/quotes",
        params={"symbols": symbol},
        headers=_headers(),
    )
    quotes = _as_list(((data or {}).get("quotes") or {}).get("quote"))
    if quotes:
        return float(quotes[0].get("last") or 0.0)
    return 0.0


async def _expirations(symbol: str) -> list[str]:
    base = get_settings().tradier_base_url
    data = await get_json(
        f"{base}/v1/markets/options/expirations",
        params={"symbol": symbol},
        headers=_headers(),
    )
    dates = ((data or {}).get("expirations") or {}).get("date")
    return _as_list(dates)[:MAX_EXPIRATIONS]


async def _chain(symbol: str, expiration: str, underlying: float) -> list[ContractFlow]:
    base = get_settings().tradier_base_url
    data = await get_json(
        f"{base}/v1/markets/options/chains",
        params={"symbol": symbol, "expiration": expiration, "greeks": "true"},
        headers=_headers(),
    )
    options = _as_list(((data or {}).get("options") or {}).get("option"))
    contracts: list[ContractFlow] = []
    for opt in options:
        volume = int(opt.get("volume") or 0)
        if volume <= 0:
            continue
        greeks = opt.get("greeks") or {}
        contracts.append(
            ContractFlow(
                symbol=symbol,
                expiration=str(opt.get("expiration_date") or expiration),
                strike=float(opt.get("strike") or 0.0),
                option_type=str(opt.get("option_type") or "").lower(),
                last_price=float(opt.get("last") or 0.0),
                volume=volume,
                open_interest=int(opt.get("open_interest") or 0),
                implied_volatility=float(greeks.get("mid_iv") or 0.0),
                underlying_price=underlying,
                source=SOURCE_NAME,
            )
        )
    return contracts


class TradierOptionsProvider:
    name = SOURCE_NAME

    @property
    def available(self) -> bool:
        return get_settings().has_tradier

    async def fetch(self, symbol: str) -> tuple[list[ContractFlow], float]:
        underlying = await _quote(symbol)
        expirations = await _expirations(symbol)
        contracts: list[ContractFlow] = []
        for exp in expirations:
            contracts.extend(await _chain(symbol, exp, underlying))
        return contracts, underlying
