"""Immutable data models shared across the engine and API layer.

All models are frozen dataclasses (immutability per project coding-style rules):
transformations return new objects rather than mutating in place.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

# Cap applied when volume trades on a strike with zero open interest.
# Fresh positioning on a brand-new strike is the *most* unusual case, so it
# maps to a capped maximum instead of scoring zero. 50.0 comfortably saturates
# all downstream scoring (peak vol/OI saturates at 5x).
ZERO_OI_VOL_OI_RATIO_CAP = 50.0


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class CatalystKind(str, Enum):
    INSIDER = "insider"            # Form 4 officer/director transactions
    INSTITUTIONAL = "institutional"  # 13F holdings changes
    CONGRESS = "congress"          # politician trades (STOCK Act)
    GOV_CONTRACT = "gov_contract"  # federal contract awards
    SEC_FILING = "sec_filing"      # 8-K and other material filings
    NEWS = "news"                  # market-moving headlines
    EARNINGS = "earnings"          # upcoming earnings date


@dataclass(frozen=True, slots=True)
class ContractFlow:
    """Normalized single option contract observation."""

    symbol: str
    expiration: str            # ISO date
    strike: float
    option_type: str           # "call" | "put"
    last_price: float
    volume: int
    open_interest: int
    implied_volatility: float
    underlying_price: float
    source: str

    @property
    def vol_oi_ratio(self) -> float:
        if self.open_interest > 0:
            return self.volume / self.open_interest
        # Zero OI with volume = entirely fresh positioning: maximum
        # unusualness (capped) rather than a silent 0.0.
        return ZERO_OI_VOL_OI_RATIO_CAP if self.volume > 0 else 0.0

    @property
    def premium(self) -> float:
        """Estimated traded premium in dollars (volume * price * 100)."""
        return self.volume * self.last_price * 100.0

    @property
    def moneyness(self) -> float:
        """How far ITM/OTM the strike is, signed relative to the contract bias."""
        if self.underlying_price <= 0:
            return 0.0
        return (self.underlying_price - self.strike) / self.underlying_price


@dataclass(frozen=True, slots=True)
class Catalyst:
    """A non-options signal that could move a stock (insider buy, congress, etc.)."""

    symbol: str
    kind: CatalystKind
    direction: Direction
    headline: str
    detail: str
    url: str
    source: str
    timestamp: str             # ISO datetime
    weight: float = 1.0        # relative importance, used in scoring boost

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["direction"] = self.direction.value
        return d


@dataclass(frozen=True, slots=True)
class TickerFlow:
    """Aggregated options-flow signal for one underlying."""

    symbol: str
    underlying_price: float
    flow_score: float          # 0-100 composite intensity
    direction: Direction
    direction_confidence: float  # 0-1
    call_premium: float
    put_premium: float
    call_put_ratio: float | None  # None = undefined/infinite (calls, no puts)
    total_volume: int
    total_open_interest: int
    unusual_contracts: int     # # of contracts with vol/OI above threshold
    top_contracts: list[dict] = field(default_factory=list)
    catalysts: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    # Direction is derived from call-vs-put traded premium skew, not from
    # observed trade-by-trade order flow; surfaced so consumers know.
    direction_basis: str = "premium_skew_proxy"

    def with_catalysts(self, catalysts: list[Catalyst]) -> "TickerFlow":
        """Return a new TickerFlow with catalysts attached and score boosted."""
        from app.scoring import catalyst_boost  # local import avoids cycle

        boosted = min(100.0, self.flow_score + catalyst_boost(catalysts))
        return TickerFlow(
            symbol=self.symbol,
            underlying_price=self.underlying_price,
            flow_score=round(boosted, 2),
            direction=self.direction,
            direction_confidence=self.direction_confidence,
            call_premium=self.call_premium,
            put_premium=self.put_premium,
            call_put_ratio=self.call_put_ratio,
            total_volume=self.total_volume,
            total_open_interest=self.total_open_interest,
            unusual_contracts=self.unusual_contracts,
            top_contracts=self.top_contracts,
            catalysts=[c.to_dict() for c in catalysts],
            sources=self.sources,
            direction_basis=self.direction_basis,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["direction"] = self.direction.value
        return d


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A full scan result served to the dashboard."""

    generated_at: str          # ISO datetime
    universe_size: int
    scanned: int
    flows: list[dict]          # serialized TickerFlow, ranked
    catalysts: list[dict]      # standalone catalyst feed (most recent)
    capabilities: dict
    symbols_requested: int = 0   # symbols in this cycle's scan window
    symbols_returned: int = 0    # symbols that yielded a scored flow
    coverage_ratio: float = 0.0  # symbols_returned / symbols_requested
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
