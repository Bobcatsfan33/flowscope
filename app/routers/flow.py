"""Options-flow endpoints: ranked, searchable, filterable."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.store import store

router = APIRouter(prefix="/api", tags=["flow"])


@router.get("/flow")
def get_flow(
    q: str | None = Query(default=None, description="Search by ticker substring"),
    direction: str | None = Query(default=None, pattern="^(bullish|bearish|neutral)$"),
    min_score: float = Query(default=0.0, ge=0.0, le=100.0),
    limit: int = Query(default=100, ge=1, le=600),
) -> dict:
    """Return the ranked flow list, filtered server-side."""
    snapshot = store.get_snapshot()
    if snapshot is None:
        return {"success": True, "data": [], "meta": {"status": "warming_up"}}

    flows = snapshot.flows
    if q:
        needle = q.upper()
        flows = [f for f in flows if needle in f["symbol"]]
    if direction:
        flows = [f for f in flows if f["direction"] == direction]
    if min_score > 0:
        flows = [f for f in flows if f["flow_score"] >= min_score]

    return {
        "success": True,
        "data": flows[:limit],
        "meta": {
            "generated_at": snapshot.generated_at,
            "universe_size": snapshot.universe_size,
            "scanned": snapshot.scanned,
            "returned": min(len(flows), limit),
            "total_matched": len(flows),
        },
    }


@router.get("/flow/{symbol}")
def get_flow_symbol(symbol: str) -> dict:
    snapshot = store.get_snapshot()
    if snapshot is None:
        raise HTTPException(status_code=503, detail="Scan warming up")
    sym = symbol.upper()
    for flow in snapshot.flows:
        if flow["symbol"] == sym:
            return {"success": True, "data": flow}
    raise HTTPException(status_code=404, detail=f"No flow data for {sym}")
