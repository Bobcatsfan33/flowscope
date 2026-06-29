"""Catalyst feed endpoints (insider, congress, filings, contracts, news)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.store import store

router = APIRouter(prefix="/api", tags=["catalysts"])

_VALID_KINDS = {
    "insider", "institutional", "congress",
    "gov_contract", "sec_filing", "news", "earnings",
}


@router.get("/catalysts")
def get_catalysts(
    kind: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    snapshot = store.get_snapshot()
    if snapshot is None:
        return {"success": True, "data": [], "meta": {"status": "warming_up"}}

    items = snapshot.catalysts
    if kind and kind in _VALID_KINDS:
        items = [c for c in items if c["kind"] == kind]
    if symbol:
        sym = symbol.upper()
        items = [c for c in items if c["symbol"] == sym]

    return {
        "success": True,
        "data": items[:limit],
        "meta": {
            "generated_at": snapshot.generated_at,
            "total_matched": len(items),
            "returned": min(len(items), limit),
        },
    }
