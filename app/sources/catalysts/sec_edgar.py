"""SEC EDGAR per-symbol catalyst source (no key).

Emits two catalyst kinds from a company's recent filings:
  * Form 4  -> INSIDER (officer/director transaction filed)
  * 8-K     -> SEC_FILING (material corporate event)

Uses the public data.sec.gov submissions API. A ticker->CIK map is loaded once
from company_tickers.json and cached in-process. SEC requires a descriptive
User-Agent (set via SEC_USER_AGENT) — already applied by the shared client.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.http_client import get_json
from app.models import Catalyst, CatalystKind, Direction

logger = logging.getLogger("flowscope.catalysts.sec")

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
RECENT_DAYS = 14
TRACKED_FORMS = {"4": CatalystKind.INSIDER, "8-K": CatalystKind.SEC_FILING}

_cik_map: dict[str, str] | None = None


async def _load_cik_map() -> dict[str, str]:
    global _cik_map
    if _cik_map is not None:
        return _cik_map
    data = await get_json(TICKERS_URL)
    mapping: dict[str, str] = {}
    # data is a dict keyed by index: {"0": {"cik_str":.., "ticker":.., "title":..}}
    for entry in (data or {}).values():
        ticker = str(entry.get("ticker", "")).upper().replace(".", "-")
        cik = str(entry.get("cik_str", "")).zfill(10)
        if ticker and cik:
            mapping[ticker] = cik
    _cik_map = mapping
    logger.info("Loaded SEC ticker->CIK map: %d entries", len(mapping))
    return mapping


def _is_recent(filing_date: str, cutoff: datetime) -> bool:
    try:
        return datetime.strptime(filing_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        ) >= cutoff
    except (ValueError, TypeError):
        return False


class SecEdgarSource:
    name = "sec_edgar"

    @property
    def available(self) -> bool:
        return True  # no key required

    async def fetch(self, symbol: str) -> list[Catalyst]:
        cik_map = await _load_cik_map()
        cik = cik_map.get(symbol.upper())
        if not cik:
            return []
        data = await get_json(SUBMISSIONS_URL.format(cik=cik))
        recent = ((data or {}).get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        dates = recent.get("filingDate") or []
        accns = recent.get("accessionNumber") or []
        docs = recent.get("primaryDocument") or []

        cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
        cik_int = int(cik)
        out: list[Catalyst] = []
        seen_kinds: set[CatalystKind] = set()
        for i, form in enumerate(forms):
            kind = TRACKED_FORMS.get(str(form))
            if kind is None:
                continue
            filing_date = dates[i] if i < len(dates) else ""
            if not _is_recent(filing_date, cutoff):
                continue
            # Only keep the most recent of each kind to avoid feed spam.
            if kind in seen_kinds:
                continue
            seen_kinds.add(kind)
            accn = (accns[i] if i < len(accns) else "").replace("-", "")
            doc = docs[i] if i < len(docs) else ""
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn}/{doc}"
                if accn
                else f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
            )
            headline = (
                f"Insider Form 4 filed ({filing_date})"
                if kind == CatalystKind.INSIDER
                else f"8-K material event filed ({filing_date})"
            )
            out.append(
                Catalyst(
                    symbol=symbol.upper(),
                    kind=kind,
                    direction=Direction.NEUTRAL,
                    headline=headline,
                    detail=f"SEC {form} filing",
                    url=url,
                    source=self.name,
                    timestamp=f"{filing_date}T00:00:00+00:00",
                    weight=1.0,
                )
            )
            if len(seen_kinds) == len(TRACKED_FORMS):
                break
        return out
