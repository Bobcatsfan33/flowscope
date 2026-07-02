"""API endpoint tests with a seeded store (no scheduler, no network)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import Snapshot
from app.routers import catalysts, flow, system
from app.store import store


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(flow.router)
    app.include_router(catalysts.router)
    app.include_router(system.router)
    store.set_snapshot(
        Snapshot(
            generated_at=datetime.now(timezone.utc).isoformat(),
            universe_size=2,
            scanned=2,
            flows=[
                {"symbol": "NVDA", "flow_score": 88.0, "direction": "bullish",
                 "call_premium": 1e6, "put_premium": 1e5, "call_put_ratio": 10.0,
                 "total_volume": 5000, "total_open_interest": 1000,
                 "unusual_contracts": 4, "underlying_price": 120.0,
                 "direction_confidence": 0.8, "top_contracts": [], "catalysts": [],
                 "sources": ["yahoo"]},
                {"symbol": "TSLA", "flow_score": 40.0, "direction": "bearish",
                 "call_premium": 1e5, "put_premium": 1e6, "call_put_ratio": 0.1,
                 "total_volume": 3000, "total_open_interest": 800,
                 "unusual_contracts": 1, "underlying_price": 200.0,
                 "direction_confidence": 0.6, "top_contracts": [], "catalysts": [],
                 "sources": ["yahoo"]},
            ],
            catalysts=[
                {"symbol": "NVDA", "kind": "insider", "direction": "bullish",
                 "headline": "h", "detail": "d", "url": "", "source": "sec_edgar",
                 "timestamp": "2026-06-20T00:00:00+00:00", "weight": 1.0},
            ],
            capabilities={"yahoo_options": True, "finnhub": False},
            symbols_requested=2,
            symbols_returned=2,
            coverage_ratio=1.0,
        )
    )
    return TestClient(app)


def test_flow_returns_ranked(client):
    res = client.get("/api/flow")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data[0]["symbol"] == "NVDA"


def test_flow_search_filter(client):
    res = client.get("/api/flow?q=tsla")
    data = res.json()["data"]
    assert len(data) == 1 and data[0]["symbol"] == "TSLA"


def test_flow_direction_filter(client):
    res = client.get("/api/flow?direction=bearish")
    data = res.json()["data"]
    assert all(f["direction"] == "bearish" for f in data)


def test_flow_min_score_filter(client):
    res = client.get("/api/flow?min_score=50")
    data = res.json()["data"]
    assert all(f["flow_score"] >= 50 for f in data)


def test_flow_symbol_detail_and_404(client):
    assert client.get("/api/flow/NVDA").json()["data"]["symbol"] == "NVDA"
    assert client.get("/api/flow/ZZZZ").status_code == 404


def test_catalysts_filter_by_kind(client):
    res = client.get("/api/catalysts?kind=insider")
    assert len(res.json()["data"]) == 1
    assert client.get("/api/catalysts?kind=news").json()["data"] == []


def test_health_and_meta(client):
    health = client.get("/api/health").json()["data"]
    assert health["has_snapshot"] is True
    assert health["market_session"] in ("open", "closed")
    assert health["data_as_of"] is not None
    assert "capabilities" in client.get("/api/meta").json()["data"]
