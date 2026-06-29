"""Tests for catalyst direction parsing + serialization (no network)."""
from __future__ import annotations

from app.models import Catalyst, CatalystKind, Direction
from app.sources.catalysts.congress_senate import _direction, _parse_date
from app.sources.catalysts.usaspending import _search_term


def test_congress_direction_mapping():
    assert _direction("Purchase") == Direction.BULLISH
    assert _direction("Sale (Full)") == Direction.BEARISH
    assert _direction("Exchange") == Direction.NEUTRAL


def test_date_parsing_formats():
    assert _parse_date("01/15/2026") is not None
    assert _parse_date("2026-01-15") is not None
    assert _parse_date("garbage") is None


def test_usaspending_search_term_strips_suffixes():
    assert _search_term("Lockheed Martin Corporation") == "lockheed martin"
    assert _search_term("Apple Inc.") == "apple"


def test_catalyst_to_dict_serializes_enums():
    cat = Catalyst(
        "AAPL", CatalystKind.INSIDER, Direction.BULLISH,
        "headline", "detail", "http://x", "src", "2026-01-01T00:00:00+00:00", 1.0,
    )
    d = cat.to_dict()
    assert d["kind"] == "insider"
    assert d["direction"] == "bullish"
    assert d["symbol"] == "AAPL"
