"""System endpoints: health, capabilities, manual refresh."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.config import get_settings
from app.store import store

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    from app.scheduler import current_market_session  # local import (matches refresh)

    data = store.status()
    data["market_session"] = current_market_session()
    return {"success": True, "data": data}


@router.get("/meta")
def meta() -> dict:
    settings = get_settings()
    return {
        "success": True,
        "data": {
            "capabilities": settings.capability_report(),
            "refresh_interval_seconds": settings.refresh_interval_seconds,
            "max_tickers_per_cycle": settings.max_tickers_per_cycle,
            "version": "1.0.0",
        },
    }


@router.post("/refresh")
async def refresh() -> dict:
    """Trigger an out-of-band scan cycle (non-blocking, bypasses market gate)."""
    from app.scheduler import run_cycle

    asyncio.create_task(run_cycle(force=True))
    return {"success": True, "data": {"status": "scan_triggered"}}
