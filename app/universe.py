"""Resolve the tradable universe: S&P 500 + Nasdaq-100 constituents.

Primary source: Wikipedia constituent tables (no key). Cached in-process and
refreshed periodically. Falls back to a bundled large-cap list on failure.
"""
from __future__ import annotations

import logging
import time

from app.universe_fallback import FALLBACK_TICKERS

logger = logging.getLogger("flowscope.universe")

_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_NDX100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"

# Yahoo/most APIs use '-' for class shares (BRK-B), Wikipedia uses '.' (BRK.B).
def _normalize(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


# Wikipedia blocks default urllib/pandas user-agents (403). Use a browser UA
# and fetch the HTML ourselves, then parse the string with pandas.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _scrape_table(url: str, column_candidates: tuple[str, ...]) -> set[str]:
    """Scrape constituent tickers from a Wikipedia page using pandas.read_html."""
    import httpx
    import pandas as pd  # imported lazily; heavy dep

    resp = httpx.get(
        url, headers={"User-Agent": _BROWSER_UA}, follow_redirects=True, timeout=20.0
    )
    resp.raise_for_status()
    from io import StringIO

    tables = pd.read_html(StringIO(resp.text))
    found: set[str] = set()
    for table in tables:
        cols = {str(c).strip().lower(): c for c in table.columns}
        for candidate in column_candidates:
            if candidate in cols:
                series = table[cols[candidate]].dropna().astype(str)
                for value in series:
                    sym = _normalize(value)
                    # Filter out obvious non-tickers (headers, footnotes).
                    if 1 <= len(sym) <= 6 and sym.replace("-", "").isalpha():
                        found.add(sym)
                if found:
                    return found
    return found


def fetch_universe() -> list[str]:
    """Return the merged, de-duplicated, sorted ticker universe.

    Network-bound and synchronous (uses pandas.read_html); call from a thread
    in async contexts. Never raises — degrades to the bundled fallback.
    """
    tickers: set[str] = set()
    try:
        tickers |= _scrape_table(_SP500_URL, ("symbol", "ticker symbol"))
    except Exception as exc:  # noqa: BLE001 - resilience over precision
        logger.warning("S&P 500 scrape failed: %s", exc)
    try:
        tickers |= _scrape_table(_NDX100_URL, ("ticker", "symbol", "ticker symbol"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Nasdaq-100 scrape failed: %s", exc)

    if len(tickers) < 100:
        logger.warning(
            "Universe scrape returned only %d names; merging bundled fallback.",
            len(tickers),
        )
        tickers |= set(FALLBACK_TICKERS)

    return sorted(tickers)


class UniverseCache:
    """Process-local cache with timed refresh."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._tickers: list[str] = list(FALLBACK_TICKERS)
        self._fetched_at: float = 0.0

    @property
    def tickers(self) -> list[str]:
        return self._tickers

    def is_stale(self) -> bool:
        return (time.time() - self._fetched_at) > self._ttl

    def refresh(self) -> list[str]:
        self._tickers = fetch_universe()
        self._fetched_at = time.time()
        logger.info("Universe refreshed: %d tickers", len(self._tickers))
        return self._tickers
