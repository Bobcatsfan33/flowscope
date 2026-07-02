"""Unit tests for the flow scoring engine (pure, no network)."""
from __future__ import annotations

from app.models import (
    ZERO_OI_VOL_OI_RATIO_CAP,
    Catalyst,
    CatalystKind,
    ContractFlow,
    Direction,
)
from app.scoring import catalyst_boost, score_ticker


def _contract(**kw) -> ContractFlow:
    base = dict(
        symbol="TEST",
        expiration="2026-07-17",
        strike=100.0,
        option_type="call",
        last_price=2.0,
        volume=1000,
        open_interest=100,
        implied_volatility=0.5,
        underlying_price=100.0,
        source="test",
    )
    base.update(kw)
    return ContractFlow(**base)


def test_contract_derived_metrics():
    c = _contract(volume=500, open_interest=100, last_price=3.0)
    assert c.vol_oi_ratio == 5.0
    assert c.premium == 500 * 3.0 * 100
    assert c.moneyness == 0.0  # strike == underlying


def test_zero_oi_with_volume_is_max_unusual():
    # Volume on a brand-new strike (OI 0) is the MOST unusual case: it maps
    # to the documented cap, not to 0.0.
    c = _contract(volume=500, open_interest=0)
    assert c.vol_oi_ratio == ZERO_OI_VOL_OI_RATIO_CAP
    dead = _contract(volume=0, open_interest=0)
    assert dead.vol_oi_ratio == 0.0


def test_empty_returns_none():
    assert score_ticker("TEST", [], 100.0, ["test"]) is None
    zero_vol = [_contract(volume=0)]
    assert score_ticker("TEST", zero_vol, 100.0, ["test"]) is None


def test_bullish_direction_from_call_premium():
    contracts = [
        _contract(option_type="call", volume=5000, last_price=4.0, strike=101),
        _contract(option_type="put", volume=100, last_price=1.0, strike=99),
    ]
    flow = score_ticker("TEST", contracts, 100.0, ["test"])
    assert flow is not None
    assert flow.direction == Direction.BULLISH
    assert flow.call_premium > flow.put_premium
    assert 0.0 <= flow.direction_confidence <= 1.0
    assert flow.direction_basis == "premium_skew_proxy"


def test_bearish_direction_from_put_premium():
    contracts = [
        _contract(option_type="put", volume=8000, last_price=5.0, strike=99),
        _contract(option_type="call", volume=100, last_price=1.0, strike=101),
    ]
    flow = score_ticker("TEST", contracts, 100.0, ["test"])
    assert flow.direction == Direction.BEARISH


def test_balanced_flow_is_neutral():
    contracts = [
        _contract(option_type="call", volume=1000, last_price=2.0, strike=100),
        _contract(option_type="put", volume=1000, last_price=2.0, strike=100),
    ]
    flow = score_ticker("TEST", contracts, 100.0, ["test"])
    assert flow.direction == Direction.NEUTRAL


def test_unusual_contracts_counted():
    contracts = [
        # vol/OI = 50, premium = 1000*5*100 = 500k -> unusual
        _contract(volume=1000, open_interest=20, last_price=5.0),
        # vol/OI = 0.1 -> not unusual
        _contract(volume=10, open_interest=100, last_price=5.0),
    ]
    flow = score_ticker("TEST", contracts, 100.0, ["test"])
    assert flow.unusual_contracts == 1


def test_flow_score_bounded_0_100():
    huge = [_contract(volume=10_000_000, open_interest=1, last_price=50.0)]
    flow = score_ticker("TEST", huge, 100.0, ["test"])
    assert 0.0 <= flow.flow_score <= 100.0


def test_tiny_print_does_not_drive_peak_score():
    # A 5-lot on OI 1 has vol/OI = 5 but trivial premium: the premium floor
    # inside the peak component keeps it from claiming the full 25 points.
    tiny = [_contract(volume=5, open_interest=1, last_price=1.0)]
    flow = score_ticker("TEST", tiny, 100.0, ["test"])
    assert flow is not None
    assert flow.flow_score == 0.0


def test_call_put_ratio_none_when_no_puts():
    calls_only = [_contract(option_type="call", volume=5000, last_price=4.0)]
    flow = score_ticker("TEST", calls_only, 100.0, ["test"])
    assert flow.call_put_ratio is None  # undefined/infinite, no sentinel
    puts_only = [_contract(option_type="put", volume=5000, last_price=4.0)]
    flow = score_ticker("TEST", puts_only, 100.0, ["test"])
    assert flow.call_put_ratio == 0.0


def test_catalyst_boost_capped():
    cats = [
        Catalyst("T", CatalystKind.INSIDER, Direction.BULLISH, "h", "d", "", "s", "t", 5),
        Catalyst("T", CatalystKind.CONGRESS, Direction.BULLISH, "h", "d", "", "s", "t", 5),
        Catalyst("T", CatalystKind.NEWS, Direction.NEUTRAL, "h", "d", "", "s", "t", 5),
    ]
    assert catalyst_boost(cats) <= 20.0


def test_insider_boost_only_when_bullish():
    bullish = [Catalyst("T", CatalystKind.INSIDER, Direction.BULLISH, "h", "d", "", "s", "t", 1.0)]
    neutral = [Catalyst("T", CatalystKind.INSIDER, Direction.NEUTRAL, "h", "d", "", "s", "t", 1.0)]
    bearish = [Catalyst("T", CatalystKind.INSIDER, Direction.BEARISH, "h", "d", "", "s", "t", 1.0)]
    assert catalyst_boost(bullish) == 6.0
    assert catalyst_boost(neutral) == 0.0  # routine Form 4 (e.g. SEC EDGAR)
    assert catalyst_boost(bearish) == 0.0  # insider sale


def test_with_catalysts_boosts_score():
    contracts = [_contract(volume=2000, open_interest=50, last_price=3.0)]
    flow = score_ticker("TEST", contracts, 100.0, ["test"])
    cats = [Catalyst("TEST", CatalystKind.INSIDER, Direction.BULLISH, "h", "d", "", "s", "t", 1.0)]
    boosted = flow.with_catalysts(cats)
    assert boosted.flow_score >= flow.flow_score
    assert len(boosted.catalysts) == 1
    assert boosted.direction_basis == "premium_skew_proxy"
