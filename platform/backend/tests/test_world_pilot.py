from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.world import pilot_playback
from app.db import SessionLocal, get_db
from app.main import app
from app.models import Posting, Relation, WorldEvent
from app.services.world_ledger import balance_of
from app.world_pilot import (
    CRUDE,
    PARAMETERS,
    RUN_ID,
    VESSELS,
    generate_pilot_events,
    portion_id,
    sea_lane_nm,
    seed_pilot_world,
)


@pytest.fixture
def db():
    """Session whose work is always rolled back; pilot seed and run happen inside it."""
    with SessionLocal() as session:
        seed_pilot_world(session)
        generate_pilot_events(session, force=True)
        try:
            yield session
        finally:
            session.rollback()


def cargoes() -> int:
    return round(PARAMETERS["flow_bbl_per_day"] * 365 / PARAMETERS["cargo_bbl"])


def cargo_kg() -> float:
    return PARAMETERS["cargo_bbl"] * PARAMETERS["kg_per_bbl"]


def test_sea_lane_length_is_plausible():
    assert 1_000 < sea_lane_nm() < 1_500


def test_run_conserves_mass_and_ends_in_products(db):
    total = db.scalar(
        select(func.sum(Posting.delta))
        .join(WorldEvent, WorldEvent.id == Posting.event_id)
        .where(WorldEvent.run_id == RUN_ID, Posting.property == "mass")
    )
    assert total == pytest.approx(0.0, abs=1e-3)

    produced = cargoes() * cargo_kg()
    assert balance_of(db, portion_id("place:ghawar", CRUDE), "mass") == pytest.approx(-produced)
    for holder in ("asset:abqaiq", "asset:ras-tanura", "asset:sikka", "asset:jamnagar"):
        assert balance_of(db, portion_id(holder, CRUDE), "mass") == pytest.approx(0, abs=1e-3)
    products = sum(
        balance_of(db, portion_id("asset:jamnagar", product), "mass")
        for product in PARAMETERS["refinery_yields"]
    )
    assert products == pytest.approx(produced)


def test_regeneration_is_idempotent(db):
    before = db.scalar(
        select(func.count()).select_from(WorldEvent).where(WorldEvent.run_id == RUN_ID)
    )
    assert generate_pilot_events(db) == 0
    assert generate_pilot_events(db, force=True) == before
    after = db.scalar(
        select(func.count()).select_from(WorldEvent).where(WorldEvent.run_id == RUN_ID)
    )
    assert after == before == cargoes() * 10


def test_vessel_locations_do_not_overlap(db):
    for vessel_id, _ in VESSELS:
        rows = db.execute(
            select(Relation.valid_from, Relation.valid_to)
            .where(
                Relation.subject_id == vessel_id,
                Relation.predicate == "located_in",
                Relation.cause_event_id.is_not(None),
            )
            .order_by(Relation.valid_from)
        ).all()
        assert rows
        for (_, end), (start, _) in zip(rows, rows[1:], strict=False):
            assert end == start


def test_playback_payload(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/api/v1/world/pilot")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == pilot_playback(db)["run_id"]
    assert len(payload["voyages"]) == cargoes() * 2
    laden = [v for v in payload["voyages"] if v["direction"] == "laden"]
    assert all(
        datetime.fromisoformat(v["arrive"]) > datetime.fromisoformat(v["depart"]) for v in laden
    )
    ids = {place["id"] for place in payload["places"]}
    assert {"place:ghawar", "asset:ras-tanura", "asset:sikka", "asset:jamnagar"} <= ids
    assert payload["estimate"]["evidence"]["class"] == "1P"
