"""Background scan scheduler.

Runs the universe refresh and flow scan on an interval using APScheduler's
AsyncIOScheduler (jobs run on the app event loop). The first scan is kicked off
shortly after startup so the dashboard populates without waiting a full cycle.
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.aggregator import run_scan
from app.config import get_settings
from app.store import store
from app.universe import UniverseCache

logger = logging.getLogger("flowscope.scheduler")

_scheduler: AsyncIOScheduler | None = None
_universe: UniverseCache | None = None
_scan_lock = asyncio.Lock()


def get_universe_cache() -> UniverseCache:
    global _universe
    if _universe is None:
        _universe = UniverseCache(get_settings().universe_refresh_hours * 3600)
    return _universe


async def run_cycle() -> None:
    """One scheduled cycle: refresh universe if stale, then scan."""
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
        "Scheduler started; scan every %ds", settings.refresh_interval_seconds
    )
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
