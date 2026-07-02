"""Background scan scheduler.

Runs the universe refresh and flow scan on an interval using APScheduler's
AsyncIOScheduler (jobs run on the app event loop). The first scan is kicked off
shortly after startup so the dashboard populates without waiting a full cycle.

Scan cycles are gated on the US regular session (Mon-Fri 09:30-16:00
America/New_York). Off-hours cycles are skipped so stale market data is never
re-stamped with a fresh `generated_at`; the last snapshot keeps being served.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from datetime import time as dt_time
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.aggregator import run_scan
from app.config import get_settings
from app.store import store
from app.universe import UniverseCache

logger = logging.getLogger("flowscope.scheduler")

MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = dt_time(9, 30)
MARKET_CLOSE = dt_time(16, 0)

_scheduler: AsyncIOScheduler | None = None
_universe: UniverseCache | None = None
_scan_lock = asyncio.Lock()


def current_market_session(now: datetime | None = None) -> str:
    """Return "open" during the US regular session, else "closed".

    Regular session = Mon-Fri 09:30-16:00 America/New_York. Exchange holidays
    are not modeled (no holiday-calendar dependency); holiday scans will run
    but only re-observe the last session's data.
    """
    now_et = (now or datetime.now(MARKET_TZ)).astimezone(MARKET_TZ)
    if now_et.weekday() >= 5:  # Saturday/Sunday
        return "closed"
    return "open" if MARKET_OPEN <= now_et.time() < MARKET_CLOSE else "closed"


def get_universe_cache() -> UniverseCache:
    global _universe
    if _universe is None:
        _universe = UniverseCache(get_settings().universe_refresh_hours * 3600)
    return _universe


async def run_cycle(force: bool = False) -> None:
    """One scheduled cycle: refresh universe if stale, then scan.

    Skips when the market is closed (keeping the last snapshot served) unless
    `force` is set (manual /api/refresh) or no snapshot exists yet (first boot
    off-hours still populates the dashboard once).
    """
    if (
        not force
        and current_market_session() == "closed"
        and store.get_snapshot() is not None
    ):
        logger.info("Market closed; skipping scan cycle (serving last snapshot).")
        return
    if _scan_lock.locked():
        logger.info("Previous scan still running; skipping this tick.")
        return
    async with _scan_lock:
        store.mark_started()
        universe = get_universe_cache()
        try:
            if universe.is_stale():
                # Universe scrape is blocking (pandas.read_html) -> thread.
                await asyncio.to_thread(universe.refresh)
            snapshot = await run_scan(universe.tickers)
            store.set_snapshot(snapshot)
            store.mark_finished(None)
            logger.info(
                "Scan complete: %d flows, %d catalysts",
                len(snapshot.flows),
                len(snapshot.catalysts),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Scan cycle failed")
            store.mark_finished(str(exc))


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_cycle,
        "interval",
        seconds=settings.refresh_interval_seconds,
        id="flow_scan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    # Kick off an immediate first scan (don't block startup).
    asyncio.create_task(run_cycle())
    _scheduler = scheduler
    logger.info(
        "Scheduler started; scan every %ds during market hours",
        settings.refresh_interval_seconds,
    )
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
