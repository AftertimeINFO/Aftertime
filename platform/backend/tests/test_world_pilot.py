from datetime import UTC, datetime, timedelta

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
    HISTORY,
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


CARGOES: list[int] = []


def cargoes() -> int:
    """Cargoes of the run: one refining event each."""
    return CARGOES[-1]


@pytest.fixture(autouse=True)
def _count_cargoes(db):
    CARGOES.append(
        db.scalar(
            select(func.count())
            .select_from(WorldEvent)
            .where(WorldEvent.run_id == RUN_ID, WorldEvent.event_type_id == "type:transform")
        )
    )


def offtakes(db) -> int:
    """Monthly off-take events: Ghawar output outside the pilot route."""
    return db.scalar(
        select(func.count())
        .select_from(WorldEvent)
        .where(WorldEvent.run_id == RUN_ID, WorldEvent.attributes.has_key("month"))
    )


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
    from app.world_disposition import RECIPIENTS

    other = sum(balance_of(db, portion_id(r[0], CRUDE), "mass") for r in RECIPIENTS)
    assert other > produced  # Ghawar sends most of its crude elsewhere
    assert balance_of(db, portion_id("place:ghawar", CRUDE), "mass") == pytest.approx(
        -(produced + other)
    )
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
    assert after == before
    # Ten events per cargo (the return legs of the last voyages may end after the run),
    # plus one off-take a month.
    voyages = after - offtakes(db)
    assert cargoes() * 10 - len(VESSELS) <= voyages <= cargoes() * 10
    # One extraction a month per recipient.
    assert offtakes(db) >= 12 * len(HISTORY)
    # Every movement names its sources.
    unsourced = db.scalar(
        select(func.count())
        .select_from(WorldEvent)
        .where(
            WorldEvent.run_id == RUN_ID,
            func.jsonb_array_length(WorldEvent.attributes["sources"]) == 0,
        )
    )
    assert unsourced == 0
    months = db.scalar(
        select(func.count(func.distinct(WorldEvent.attributes["month"].astext))).where(
            WorldEvent.run_id == RUN_ID, WorldEvent.attributes.has_key("month")
        )
    )
    from app.world_pilot import GHAWAR_HISTORY

    assert months == 12 * len(GHAWAR_HISTORY)


def test_history_years_follow_the_published_flows(db):
    from app.world_pilot import HISTORY

    for year, (bbl_per_day, provenance, _) in HISTORY.items():
        start, end = datetime(year, 1, 1, tzinfo=UTC), datetime(year + 1, 1, 1, tzinfo=UTC)
        refined = db.scalar(
            select(func.count())
            .select_from(WorldEvent)
            .where(
                WorldEvent.run_id == RUN_ID,
                WorldEvent.event_type_id == "type:extract",
                ~WorldEvent.attributes.has_key("month"),
                WorldEvent.occurred_at >= start,
                WorldEvent.occurred_at < end,
            )
        )
        expected = bbl_per_day * 365 / PARAMETERS["cargo_bbl"]
        # The last cargoes of the run are cut where their refining would end after it.
        assert abs(refined - expected) <= (5 if year == max(HISTORY) else 2), year
        kinds = set(
            db.scalars(
                select(WorldEvent.provenance).where(
                    WorldEvent.run_id == RUN_ID,
                    WorldEvent.event_type_id == "type:extract",
                    ~WorldEvent.attributes.has_key("month"),
                    WorldEvent.occurred_at >= start + timedelta(days=5),
                    WorldEvent.occurred_at < end,
                )
            )
        )
        assert kinds == {provenance}, year


def test_ghawar_produces_its_whole_derived_output(db):
    from app.world_pilot import GHAWAR_HISTORY

    ghawar = portion_id("place:ghawar", CRUDE)
    for year, (bbl_per_day, provenance, _) in GHAWAR_HISTORY.items():
        start, end = datetime(year, 1, 1, tzinfo=UTC), datetime(year + 1, 1, 1, tzinfo=UTC)
        out = -(balance_of(db, ghawar, "mass", at=end) - balance_of(db, ghawar, "mass", at=start))
        expected = bbl_per_day * (end - start).days * PARAMETERS["kg_per_bbl"]
        # Cargo timing shifts at most a few cargoes across the turn of the year.
        assert out == pytest.approx(expected, abs=5 * cargo_kg()), year
        kinds = set(
            db.scalars(
                select(WorldEvent.provenance).where(
                    WorldEvent.run_id == RUN_ID,
                    WorldEvent.attributes.has_key("month"),
                    WorldEvent.occurred_at >= start,
                    WorldEvent.occurred_at < end,
                )
            )
        )
        assert kinds == {provenance}, year
    # From 2019 about a third of Saudi output: 2.8-3.4 mb/d; the 1981 peak about 5.7 mb/d.
    assert all(2.8e6 < bbl < 3.4e6 for y, (bbl, _, _) in GHAWAR_HISTORY.items() if y >= 2019)
    assert GHAWAR_HISTORY[1981][0] == pytest.approx(5.7e6, rel=0.01)
    # The reconstruction meets the published cumulative production (IEA: 66 bn bbl by 2007).
    from app.world_history import cumulative_ghawar_bbl

    assert cumulative_ghawar_bbl(1951, 2007) == pytest.approx(66e9, rel=0.05)


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
    assert payload["run_id"] == pilot_playback(None, None, db)["run_id"]
    window = payload["window"]
    span = datetime.fromisoformat(window["to"]) - datetime.fromisoformat(window["from"])
    assert span <= timedelta(days=366)
    assert payload["voyages"] and len(payload["voyages"]) < cargoes() * 2
    laden = [v for v in payload["voyages"] if v["direction"] == "laden"]
    assert all(
        datetime.fromisoformat(v["arrive"]) > datetime.fromisoformat(v["depart"]) for v in laden
    )
    ids = {place["id"] for place in payload["places"]}
    assert {"place:ghawar", "asset:ras-tanura", "asset:sikka", "asset:jamnagar"} <= ids
    assert payload["estimate"]["evidence"]["class"] == "1P"

    # A later window starts from the postings before it.
    app.dependency_overrides[get_db] = lambda: db
    try:
        later = TestClient(app).get(
            "/api/v1/world/pilot",
            params={"from": "2024-01-01T00:00:00Z", "to": "2025-01-01T00:00:00Z"},
        ).json()
    finally:
        app.dependency_overrides.clear()
    ghawar = portion_id("place:ghawar", CRUDE)
    before = balance_of(db, ghawar, "mass", at=datetime(2023, 12, 31, 23, 59, tzinfo=UTC))
    assert later["initial"][ghawar] == pytest.approx(before)
    assert all(e["t"] >= "2024-01-01" for e in later["events"])


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

    # The deposit holds its latest estimate minus the production since; elements carry
    # atom counts.
    from app.world_pilot import ghawar_estimates

    end = datetime(2024, 6, 1, tzinfo=UTC)
    bbl, valid_time, _ = max(
        (row for row in ghawar_estimates().values() if row[1] <= end), key=lambda row: row[1]
    )
    ghawar = contents(db, "place:ghawar", end)
    deposit = portion_id("place:ghawar", CRUDE)
    produced = balance_of(db, deposit, "mass", at=valid_time) - balance_of(
        db, deposit, "mass", at=end
    )
    assert produced > 0
    estimate = bbl * PARAMETERS["kg_per_bbl"]
    expected = estimate - produced
    assert ghawar["total_kg"] == pytest.approx(expected)
    carbon = next(e for e in ghawar["elements"] if e["symbol"] == "C")
    assert carbon["kg"] == pytest.approx(expected * 0.8465)
    assert carbon["atoms"] == pytest.approx(carbon["kg"] * 1000 / 12.011 * 6.02214076e23)

    # Earth contains everything: the run only moves matter; estimates reset the deposit.
    earth = contents(db, "place:earth", end)
    moved_out = -balance_of(db, deposit, "mass", at=valid_time)
    assert earth["total_kg"] == pytest.approx(estimate + moved_out)


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


def test_recipients_take_the_rest_of_ghawar_output(db):
    from app.world_disposition import UNKNOWN
    from app.world_pilot import GHAWAR_HISTORY, HISTORY, recipients_of

    for year in GHAWAR_HISTORY:
        shares = recipients_of(datetime(year, 6, 1, tzinfo=UTC))
        total = sum(share.bbl_per_day for share in shares)
        pilot = HISTORY[year][0] if year in HISTORY else 0.0
        assert total == pytest.approx(GHAWAR_HISTORY[year][0] - pilot), year
        assert all(share.bbl_per_day > 0 for share in shares)
        # Whatever no statistic places is shown as unknown, never dropped.
        assert sum(1 for share in shares if share.recipient == UNKNOWN) <= 1


def test_reserves_are_re_estimated_from_aramco_figures(db):
    from app.services.world_balance import balance
    from app.world_pilot import ARAMCO_RESERVES, ghawar_estimates

    estimates = ghawar_estimates()
    assert set(estimates) == {1950} | {y for y in ARAMCO_RESERVES if y >= 2018}
    # Before production: the end-2018 reserves plus the production of 1951-2018.
    assert estimates[1950][0] > 120e9
    assert all(row[2]["sources"] for row in estimates.values())
    assert estimates[2018][0] == pytest.approx(48.25e9)
    later = [y for y in estimates if y > 2018]
    if not later:
        return
    year = later[0]
    result = balance(
        db, "place:ghawar", datetime(year, 1, 1, tzinfo=UTC), estimates[year][1], "substance"
    )
    totals = result["totals"]
    # The closing stock is the new estimate; the change it brings is a revision, not residual.
    assert totals["closing"] == pytest.approx(estimates[year][0] * PARAMETERS["kg_per_bbl"])
    assert totals["revision"] != 0
    assert abs(totals["residual"]) < 1.0
