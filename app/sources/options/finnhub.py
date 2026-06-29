"""Finnhub options provider (free key). Used as a tertiary failover.

Finnhub's `/stock/option-chain` returns expirations each with CALL/PUT lists.
Volume/OI availability varies by plan; contracts without volume are skipped.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.http_client import get_json
from app.models import ContractFlow

logger = logging.getLogger("flowscope.options.finnhub")

BASE = "https://finnhub.io/api/v1"
MAX_EXPIRATIONS = 3
SOURCE_NAME = "finnhub"


async def _quote(symbol: str) -> float:
    key = get_settings().finnhub_api_key
    data = await get_json(f"{BASE}/quote", params={"symbol": symbol, "token": key})
    return float((data or {}).get("c") or 0.0)


class FinnhubOptionsProvider:
    name = SOURCE_NAME

    @property
    def available(self) -> bool:
        return get_settings().has_finnhub

    async def fetch(self, symbol: str) -> tuple[list[ContractFlow], float]:
        key = get_settings().finnhub_api_key
        underlying = await _quote(symbol)
        data = await get_json(
            f"{BASE}/stock/option-chain", params={"symbol": symbol, "token": key}
        )
        chains = (data or {}).get("data") or []
        contracts: list[ContractFlow] = []
        for entry in chains[:MAX_EXPIRATIONS]:
            expiration = str(entry.get("expirationDate") or "")
            options = entry.get("options") or {}
            for opt_type, items in (("call", options.get("CALL") or []),
                                    ("put", options.get("PUT") or [])):
                for opt in items:
                    volume = int(opt.get("volume") or 0)
                    if volume <= 0:
                        continue
                    contracts.append(
                        ContractFlow(
                            symbol=symbol,
                            expiration=expiration,
                            strike=float(opt.get("strike") or 0.0),
                            option_type=opt_type,
                            last_price=float(opt.get("lastPrice") or 0.0),
                            volume=volume,
                            open_interest=int(opt.get("openInterest") or 0),
                            implied_volatility=float(opt.get("impliedVolatility") or 0.0),
                            underlying_price=underlying,
                            source=SOURCE_NAME,
                        )
                    )
        return contracts, underlying
