"""In-memory snapshot store.

Holds the latest scan Snapshot plus run metadata. A single writer (scheduler)
and many readers (API). Guarded by a lock; reads return the immutable snapshot
reference so callers never see partial state.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.models import Snapshot


class SnapshotStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: Snapshot | None = None
        self._last_run_started: str | None = None
        self._last_error: str | None = None
        self._running: bool = False
        self._data_as_of: str | None = None  # last *successful* scan time

    def set_snapshot(self, snapshot: Snapshot) -> None:
        with self._lock:
            self._snapshot = snapshot
            self._data_as_of = snapshot.generated_at

    def get_snapshot(self) -> Snapshot | None:
        with self._lock:
            return self._snapshot

    def mark_started(self) -> None:
        with self._lock:
            self._running = True
            self._last_run_started = datetime.now(timezone.utc).isoformat()

    def mark_finished(self, error: str | None = None) -> None:
        with self._lock:
            self._running = False
            self._last_error = error

    def status(self) -> dict:
        with self._lock:
            snap = self._snapshot
            return {
                "running": self._running,
                "last_run_started": self._last_run_started,
                "last_error": self._last_error,
                "has_snapshot": snap is not None,
                "generated_at": snap.generated_at if snap else None,
                "data_as_of": self._data_as_of,
                "flows_count": len(snap.flows) if snap else 0,
                "catalysts_count": len(snap.catalysts) if snap else 0,
                "coverage_ratio": snap.coverage_ratio if snap else None,
                "symbols_requested": snap.symbols_requested if snap else 0,
                "symbols_returned": snap.symbols_returned if snap else 0,
                "scan_errors_count": len(snap.errors) if snap else 0,
                "scan_errors": list(snap.errors[:20]) if snap else [],
            }


store = SnapshotStore()
