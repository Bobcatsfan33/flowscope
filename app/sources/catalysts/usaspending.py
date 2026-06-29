"""USAspending.gov federal contract awards (no key) — per-symbol, best-effort.

Large new federal contract awards can move defense/industrial/tech names. We
map a ticker to a company search term (from SEC company names) and query recent
contract awards. Recipient-name matching is fuzzy, so results are flagged
best-effort and weighted modestly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.http_client import get_client, get_json
from app.models import Catalyst, CatalystKind, Direction

logger = logging.getLogger("flowscope.catalysts.usaspending")

NAMES_URL = "https://www.sec.gov/files/company_tickers.json"
AWARD_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
LOOKBACK_DAYS = 90
MIN_AWARD = 5_000_000.0           # ignore small awards as non-material
CONTRACT_TYPE_CODES = ["A", "B", "C", "D"]
_SUFFIXES = (" inc", " corp", " corporation", " co", " company", " ltd",
             " plc", " holdings", " group", " the", ",", ".")

_name_map: dict[str, str] | None = None


async def _load_names() -> dict[str, str]:
    global _name_map
    if _name_map is not None:
        return _name_map
    data = await get_json(NAMES_URL)
    mapping: dict[str, str] = {}
    for entry in (data or {}).values():
        ticker = str(entry.get("ticker", "")).upper().replace(".", "-")
        title = str(entry.get("title", "")).strip()
        if ticker and title:
            mapping[ticker] = title
    _name_map = mapping
    return mapping


def _search_term(company_title: str) -> str:
    term = company_title.lower()
    for suffix in _SUFFIXES:
        term = term.replace(suffix, " ")
    return " ".join(term.split()[:2]).strip() or company_title


class UsaSpendingSource:
    name = "usaspending"

    @property
    def available(self) -> bool:
        return True  # no key required

    async def fetch(self, symbol: str) -> list[Catalyst]:
        names = await _load_names()
        title = names.get(symbol.upper())
        if not title:
            return []
        term = _search_term(title)
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=LOOKBACK_DAYS)
        body = {
            "filters": {
                "recipient_search_text": [term],
                "time_period": [
                    {"start_date": start.isoformat(), "end_date": today.isoformat()}
                ],
                "award_type_codes": CONTRACT_TYPE_CODES,
            },
            "fields": [
                "Award ID", "Recipient Name", "Award Amount",
                "Description", "Awarding Agency", "Action Date",
            ],
            "sort": "Award Amount",
            "order": "desc",
            "limit": 3,
        }
        resp = await get_client().post(AWARD_URL, json=body)
        resp.raise_for_status()
        results = (resp.json() or {}).get("results") or []
        out: list[Catalyst] = []
        for row in results:
            amount = float(row.get("Award Amount") or 0.0)
            if amount < MIN_AWARD:
                continue
            recipient = str(row.get("Recipient Name") or "")
            # Guard fuzzy matches: require term to appear in recipient.
            if term.split()[0] not in recipient.lower():
                continue
            out.append(
                Catalyst(
                    symbol=symbol.upper(),
                    kind=CatalystKind.GOV_CONTRACT,
                    direction=Direction.BULLISH,
                    headline=f"Federal award ${amount/1e6:,.1f}M — {row.get('Awarding Agency', '')}",
                    detail=str(row.get("Description") or "")[:160],
                    url="https://www.usaspending.gov/",
                    source=self.name,
                    timestamp=f"{row.get('Action Date', today.isoformat())}T00:00:00+00:00",
                    weight=0.9,
                )
            )
        return out[:1]
