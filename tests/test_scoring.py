"""Unit tests for the flow scoring engine (pure, no network)."""
from __future__ import annotations

from app.models import Catalyst, CatalystKind, ContractFlow, Direction
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


def test_catalyst_boost_capped():
    cats = [
        Catalyst("T", CatalystKind.INSIDER, Direction.BULLISH, "h", "d", "", "s", "t", 5),
        Catalyst("T", CatalystKind.CONGRESS, Direction.BULLISH, "h", "d", "", "s", "t", 5),
        Catalyst("T", CatalystKind.NEWS, Direction.NEUTRAL, "h", "d", "", "s", "t", 5),
    ]
    assert catalyst_boost(cats) <= 20.0


def test_with_catalysts_boosts_score():
    contracts = [_contract(volume=2000, open_interest=50, last_price=3.0)]
    flow = score_ticker("TEST", contracts, 100.0, ["test"])
    cats = [Catalyst("TEST", CatalystKind.INSIDER, Direction.BULLISH, "h", "d", "", "s", "t", 1.0)]
    boosted = flow.with_catalysts(cats)
    assert boosted.flow_score >= flow.flow_score
    assert len(boosted.catalysts) == 1
