"""Options-flow scoring: turn raw contracts into a ranked, directional signal.

Design goals:
  * Pure functions, no I/O — fully unit-testable and deterministic.
  * A composite 0-100 `flow_score` capturing *intensity* of unusual activity.
  * A `direction` (bullish/bearish) with a 0-1 confidence from premium skew.

Heuristics (mirroring how flow desks read the tape):
  * Unusual = contract volume exceeds open interest (vol/OI > 1) AND meaningful
    premium — i.e. fresh positioning, not just churn on existing OI.
  * Bullish premium = call buying + put selling pressure; we approximate using
    call vs put traded premium, lightly weighted toward near-the-money strikes
    where directional conviction concentrates.
  * Score blends: total unusual premium (log-scaled), peak vol/OI, and breadth
    (how many contracts are unusual), so a single fat print and broad-based
    accumulation both surface.
"""
from __future__ import annotations

import math

from app.models import Catalyst, ContractFlow, Direction, TickerFlow

# Tunables (kept as named constants per coding-style: no magic numbers).
VOL_OI_UNUSUAL_THRESHOLD = 1.0      # vol > OI flags fresh positioning
MIN_CONTRACT_PREMIUM = 25_000.0     # ignore tiny prints when counting unusual
PREMIUM_LOG_BASE = 10.0
PREMIUM_SCORE_CEILING = 8.0         # log10($100M) ≈ 8 → maps to full marks
NEAR_MONEY_BAND = 0.07              # within 7% of spot = "near the money"
NEAR_MONEY_WEIGHT = 1.5             # directional premium emphasis near the money

# Composite weights (sum = 1.0).
W_PREMIUM = 0.55
W_PEAK_VOL_OI = 0.25
W_BREADTH = 0.20

# Per-catalyst score boost added on top of options flow_score.
CATALYST_BOOST = {
    "insider": 6.0,
    "institutional": 4.0,
    "congress": 5.0,
    "gov_contract": 3.0,
    "sec_filing": 3.0,
    "news": 2.0,
    "earnings": 2.0,
}
MAX_CATALYST_BOOST = 20.0


def _directional_premium(contract: ContractFlow) -> float:
    """Signed premium contribution: positive = bullish, negative = bearish.

    Calls contribute positively, puts negatively. Near-the-money contracts get
    extra weight because that's where directional conviction lives.
    """
    weight = (
        NEAR_MONEY_WEIGHT
        if abs(contract.moneyness) <= NEAR_MONEY_BAND
        else 1.0
    )
    signed = contract.premium if contract.option_type == "call" else -contract.premium
    return signed * weight


def _premium_score(unusual_premium: float) -> float:
    """Log-scale total unusual premium into 0-1."""
    if unusual_premium <= 0:
        return 0.0
    log_prem = math.log(unusual_premium, PREMIUM_LOG_BASE)
    return max(0.0, min(1.0, log_prem / PREMIUM_SCORE_CEILING))


def _peak_vol_oi_score(contracts: list[ContractFlow]) -> float:
    """Map the single most extreme vol/OI ratio into 0-1 (saturates at 5x)."""
    if not contracts:
        return 0.0
    peak = max(c.vol_oi_ratio for c in contracts)
    return max(0.0, min(1.0, peak / 5.0))


def _breadth_score(unusual_count: int) -> float:
    """More distinct unusual contracts = broader conviction (saturates at 10)."""
    return max(0.0, min(1.0, unusual_count / 10.0))


def catalyst_boost(catalysts: list[Catalyst]) -> float:
    """Total score boost from attached catalysts, capped."""
    total = sum(
        CATALYST_BOOST.get(c.kind.value, 0.0) * c.weight for c in catalysts
    )
    return min(MAX_CATALYST_BOOST, total)


def score_ticker(
    symbol: str,
    contracts: list[ContractFlow],
    underlying_price: float,
    sources: list[str],
) -> TickerFlow | None:
    """Aggregate a list of contracts into a single ranked, directional signal.

    Returns None when there is no usable volume (nothing to rank).
    """
    live = [c for c in contracts if c.volume > 0]
    if not live:
        return None

    call_premium = sum(c.premium for c in live if c.option_type == "call")
    put_premium = sum(c.premium for c in live if c.option_type == "put")
    total_volume = sum(c.volume for c in live)
    total_oi = sum(c.open_interest for c in live)

    unusual = [
        c
        for c in live
        if c.vol_oi_ratio > VOL_OI_UNUSUAL_THRESHOLD
        and c.premium >= MIN_CONTRACT_PREMIUM
    ]
    unusual_premium = sum(c.premium for c in unusual)

    # Composite intensity score (0-100).
    composite = (
        W_PREMIUM * _premium_score(unusual_premium)
        + W_PEAK_VOL_OI * _peak_vol_oi_score(live)
        + W_BREADTH * _breadth_score(len(unusual))
    )
    flow_score = round(composite * 100.0, 2)

    # Direction from signed premium skew.
    net_directional = sum(_directional_premium(c) for c in live)
    gross_directional = sum(abs(_directional_premium(c)) for c in live)
    confidence = abs(net_directional) / gross_directional if gross_directional else 0.0
    if confidence < 0.10 or gross_directional == 0:
        direction = Direction.NEUTRAL
    elif net_directional > 0:
        direction = Direction.BULLISH
    else:
        direction = Direction.BEARISH

    call_put_ratio = (
        call_premium / put_premium if put_premium > 0 else float("inf")
        if call_premium > 0
        else 0.0
    )

    # Top contracts by premium for the drill-down panel.
    top = sorted(live, key=lambda c: c.premium, reverse=True)[:5]
    top_contracts = [
        {
            "type": c.option_type,
            "strike": c.strike,
            "expiration": c.expiration,
            "volume": c.volume,
            "open_interest": c.open_interest,
            "vol_oi_ratio": round(c.vol_oi_ratio, 2),
            "premium": round(c.premium, 0),
            "iv": round(c.implied_volatility, 4),
            "source": c.source,
        }
        for c in top
    ]

    return TickerFlow(
        symbol=symbol,
        underlying_price=round(underlying_price, 2),
        flow_score=flow_score,
        direction=direction,
        direction_confidence=round(confidence, 3),
        call_premium=round(call_premium, 0),
        put_premium=round(put_premium, 0),
        call_put_ratio=round(call_put_ratio, 2) if call_put_ratio != float("inf") else 999.99,
        total_volume=total_volume,
        total_open_interest=total_oi,
        unusual_contracts=len(unusual),
        top_contracts=top_contracts,
        sources=sources,
    )
