from datetime import UTC, datetime

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
    ELEMENTS,
    PARAMETERS,
    RUN_ID,
    VESSELS,
    element_id,
    generate_pilot_events,
    holders,
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


def test_refining_conserves_every_element(db):
    from app.services.world_query import element_fractions

    event = db.scalars(
        select(WorldEvent).where(
            WorldEvent.run_id == RUN_ID, WorldEvent.event_type_id == "type:transform"
        )
    ).first()
    material_of = {
        portion_id(holder, material): material
        for holder, materials in holders()
        for material in materials
    }
    net: dict[str, float] = {}
    gross = 0.0
    for posting in db.scalars(select(Posting).where(Posting.event_id == event.id)):
        gross += abs(posting.delta)
        for element, fraction in element_fractions(db, material_of[posting.entity_id]).items():
            net[element] = net.get(element, 0.0) + posting.delta * fraction
    assert set(net) == {element_id(symbol) for symbol, _, _ in ELEMENTS}
    for value in net.values():
        assert abs(value) < 1e-6 * gross


def test_contents_emerge_from_containment(db):
    from app.services.world_query import contents

    # A berthed vessel's cargo counts inside the terminal and the region around it.
    berth = db.scalars(
        select(Relation)
        .where(
            Relation.predicate == "located_in",
            Relation.object_id == "asset:sikka",
            Relation.cause_event_id.is_not(None),
        )
        .order_by(Relation.valid_from)
    ).first()
    moment = berth.valid_from + (berth.valid_to - berth.valid_from) / 4
    sikka = contents(db, "asset:sikka", moment)
    assert any(p["holder"] == berth.subject_id and p["kg"] > 0 for p in sikka["portions"])
    gujarat = contents(db, "place:gujarat", moment)
    assert gujarat["total_kg"] >= sikka["total_kg"] > 0

    # The deposit holds its estimate minus the pilot's production; elements carry atom counts.
    end = datetime(2024, 6, 1, tzinfo=UTC)
    ghawar = contents(db, "place:ghawar", end)
    expected = 48.25e9 * PARAMETERS["kg_per_bbl"] - cargoes() * cargo_kg()
    assert ghawar["total_kg"] == pytest.approx(expected)
    carbon = next(e for e in ghawar["elements"] if e["symbol"] == "C")
    assert carbon["kg"] == pytest.approx(expected * 0.8465)
    assert carbon["atoms"] == pytest.approx(carbon["kg"] * 1000 / 12.011 * 6.02214076e23)

    # Earth contains everything: nothing is created or lost by the run.
    earth = contents(db, "place:earth", end)
    assert earth["total_kg"] == pytest.approx(48.25e9 * PARAMETERS["kg_per_bbl"])


def test_entity_api(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        listed = client.get("/api/v1/world/entities", params={"q": "Pilot VLCC"}).json()
        card = client.get(
            "/api/v1/world/entities/vessel:pilot-vlcc-1", params={"at": "2023-03-01T00:00:00Z"}
        ).json()
        more = client.get(
            "/api/v1/world/entities/vessel:pilot-vlcc-1/operations", params={"limit": 5}
        ).json()
        missing = client.get("/api/v1/world/entities/nope")
    finally:
        app.dependency_overrides.clear()
    assert listed["total"] == len(VESSELS) and listed["kinds"] == {"asset": len(VESSELS)}
    assert card["runs"] == [RUN_ID]
    assert card["operations"]["total"] > 0
    assert all(
        datetime.fromisoformat(item["occurred_at"]) <= datetime(2023, 3, 1, tzinfo=UTC)
        for item in card["operations"]["items"]
    )
    assert [r["predicate"] for r in card["outgoing"]].count("located_in") == 1
    assert len(more["items"]) == 5 and more["total"] > card["operations"]["total"]
    assert missing.status_code == 404


def test_version_endpoint():
    from app import __version__

    response = TestClient(app).get("/api/v1/world/version")
    assert response.json() == {"api": __version__}
    assert app.version == __version__
