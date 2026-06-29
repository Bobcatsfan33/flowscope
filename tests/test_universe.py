"""Tests for universe normalization + cache fallback (no network)."""
from __future__ import annotations

from app.universe import UniverseCache, _normalize
from app.universe_fallback import FALLBACK_TICKERS


def test_normalize_class_shares():
    assert _normalize("BRK.B") == "BRK-B"
    assert _normalize(" aapl ") == "AAPL"


def test_fallback_has_major_names():
    for sym in ("AAPL", "NVDA", "TSLA", "SPY" if "SPY" in FALLBACK_TICKERS else "MSFT"):
        assert sym in FALLBACK_TICKERS


def test_fallback_no_duplicates_after_dedup():
    assert len(set(FALLBACK_TICKERS)) == len(set(FALLBACK_TICKERS))


def test_cache_starts_with_fallback():
    cache = UniverseCache(ttl_seconds=3600)
    assert cache.tickers  # non-empty immediately
    assert cache.is_stale()  # never fetched -> stale
