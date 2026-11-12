"""World computation to a forecast horizon and the coverage it gives the balance (DEV)."""

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engines, get_db
from app.main import app
from app.models import WorldComputation, WorldEvent
from app.services.world_balance import balance
from app.services.world_compute import ComputeError, check_period, compute, coverage
from app.world_pilot import HISTORY, PARAMETERS, RUN_ID

KG_PER_YEAR = PARAMETERS["kg_per_bbl"] * 365


@pytest.fixture()
def db():
    """A DEV session whose commits are rolled back at the end of the test."""
    connection = engines["dev"].connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    outer.rollback()
    connection.close()


def year(y: int) -> tuple[datetime, datetime]:
    return datetime(y, 1, 1, tzinfo=UTC), datetime(y + 1, 1, 1, tzinfo=UTC)


def test_compute_extends_history_with_a_forecast(db):
    result = compute(db, date(2027, 12, 31), growth_pct=10.0, note="test")
    assert result["coverage"]["from"] == "1951-01-01"
    assert result["coverage"]["to"] == "2027-12-31"
    assert result["coverage"]["history_to"] == "2025-12-31"
    assert result["coverage"]["forecast"] is True
    assert result["computations"][0]["note"] == "test"

    # Refinery intake follows the published yearly figure, then the grown forecast.
    last = max(HISTORY)
    for y, bbl in ((2024, HISTORY[2024][0]), (2027, HISTORY[last][0] * 1.1**2)):
        totals = balance(db, "asset:jamnagar", *year(y), "substance")["totals"]
        assert totals["inflow"] == pytest.approx(bbl * KG_PER_YEAR, rel=0.03), y
    forecast = balance(db, "place:earth", *year(2027), "substance")
    assert forecast["residual_ok"]
    assert set(forecast["provenance"]) == {"forecast"}
    latest = db.scalar(select(func.max(WorldEvent.occurred_at)).where(WorldEvent.run_id == RUN_ID))
    assert latest < datetime(2028, 1, 1, tzinfo=UTC)


def test_recompute_replaces_the_ledger(db):
    compute(db, date(2030, 12, 31))
    long = db.scalar(select(func.count()).select_from(WorldEvent).where(WorldEvent.run_id == RUN_ID))
    compute(db, date(2025, 12, 31))
    short = db.scalar(select(func.count()).select_from(WorldEvent).where(WorldEvent.run_id == RUN_ID))
    assert short < long
    assert coverage(db)["to"] == "2025-12-31" and coverage(db)["forecast"] is False
    assert db.scalar(select(func.count()).select_from(WorldComputation)) >= 2


def test_period_outside_coverage_is_refused(db):
    compute(db, date(2026, 6, 30))
    check_period(db, *year(2025))
    with pytest.raises(ComputeError):
        check_period(db, *year(2026))
    with pytest.raises(ComputeError):
        check_period(db, *year(1950))


def test_bad_horizons_are_refused(db):
    with pytest.raises(ComputeError):
        compute(db, date(1951, 1, 15))
    with pytest.raises(ComputeError):
        compute(db, date(2075, 1, 1))
    with pytest.raises(ComputeError):
        compute(db, date(2030, 1, 1), growth_pct=500)


def test_api(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        done = client.post("/api/v1/world/compute", json={"horizon": "2026-12-31", "growth_pct": 0})
        overview = client.get("/api/v1/world/coverage").json()
        inside = client.get(
            "/api/v1/world/balance",
            params={"scope": "place:earth", "from": "2026-01-01T00:00:00Z", "to": "2027-01-01T00:00:00Z"},
        )
        outside = client.get(
            "/api/v1/world/balance",
            params={"scope": "place:earth", "from": "2026-01-01T00:00:00Z", "to": "2027-01-02T00:00:00Z"},
        )
        prod = client.post(
            "/api/v1/world/compute",
            json={"horizon": "2026-12-31"},
            headers={"X-Aftertime-Layer": "prod"},
        )
    finally:
        app.dependency_overrides.clear()
    assert done.status_code == 200, done.text
    assert done.json()["events"] > 0
    assert overview["coverage"]["to"] == "2026-12-31"
    assert [f["provenance"] for f in overview["flows"]][-1] == "forecast"
    assert inside.status_code == 200 and inside.json()["coverage"]["to"] == "2026-12-31"
    assert outside.status_code == 422 and "2026-12-31" in outside.json()["detail"]
    assert prod.status_code == 403
