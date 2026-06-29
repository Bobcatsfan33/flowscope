"""Options provider contract + failover orchestration.

Each provider implements `fetch(symbol)` returning (contracts, underlying_price)
or raising on failure. `fetch_options` tries providers in priority order and
returns the first non-empty result, recording which source won.
"""
from __future__ import annotations

import logging
from typing import Protocol

from app.models import ContractFlow

logger = logging.getLogger("flowscope.options")


class OptionsProvider(Protocol):
    name: str

    @property
    def available(self) -> bool:
        """Whether this provider is configured (e.g. has a key)."""
        ...

    async def fetch(self, symbol: str) -> tuple[list[ContractFlow], float]:
        """Return (contracts, underlying_price). May raise on failure."""
        ...


async def fetch_options(
    symbol: str, providers: list[OptionsProvider]
) -> tuple[list[ContractFlow], float, str | None]:
    """Try each available provider in order; return first success.

    Returns (contracts, underlying_price, winning_source_name). On total
    failure returns ([], 0.0, None) — callers skip the symbol.
    """
    for provider in providers:
        if not provider.available:
            continue
        try:
            contracts, price = await provider.fetch(symbol)
            if contracts:
                return contracts, price, provider.name
        except Exception as exc:  # noqa: BLE001 - failover should be resilient
            logger.debug("%s failed for %s: %s", provider.name, symbol, exc)
            continue
    return [], 0.0, None
