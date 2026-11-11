import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Entity, EntityExtent, Relation
from app.services.world_ledger import (
    LedgerError,
    PostingInput,
    balance_of,
    check_balance,
    conserved_units,
    is_subtype,
    record_event,
)
from app.world_core import seed_world_core

T0 = datetime(2023, 1, 1, tzinfo=UTC)
T1 = datetime(2023, 1, 5, tzinfo=UTC)


@pytest.fixture
def db():
    """Session whose work is always rolled back; the seed runs inside it."""
    with SessionLocal() as session:
        seed_world_core(session)
        try:
            yield session
        finally:
            session.rollback()


def portion(db, entity_id: str, material: str) -> str:
    db.add(Entity(id=entity_id, kind="portion", level="object", name=entity_id, attributes={}))
    db.flush()
    db.add(Relation(subject_id=entity_id, predicate="instance_of", object_id=material))
    db.flush()
    return entity_id


def kg(entity_id: str, delta: float) -> PostingInput:
    return PostingInput(entity_id, "mass", delta, "kg")


def test_check_balance_accepts_zero_net_and_ignores_unconserved():
    check_balance(
        [kg("a", -10.0), kg("b", 4.0), kg("c", 6.0), PostingInput("a", "temperature", 3, "K")],
        {"mass": "kg"},
    )


def test_check_balance_rejects_creation_of_matter():
    with pytest.raises(LedgerError, match="does not balance"):
        check_balance([kg("a", -10.0), kg("b", 11.0)], {"mass": "kg"})


def test_check_balance_requires_canonical_unit():
    with pytest.raises(LedgerError, match="must be posted in kg"):
        check_balance([PostingInput("a", "mass", -1, "t"), kg("b", 1000)], {"mass": "kg"})


def test_seed_is_idempotent_and_builds_type_lattice(db):
    before = db.scalar(select(func.count()).select_from(Relation))
    seed_world_core(db)
    assert db.scalar(select(func.count()).select_from(Relation)) == before
    assert is_subtype(db, "type:arab-light", "type:material")
    assert is_subtype(db, "type:transform", "type:event-type")
    assert not is_subtype(db, "type:vessel", "type:place")
    assert conserved_units(db)["mass"] == "kg"


def test_production_and_transfer_keep_balance(db):
    deposit = portion(db, "test:ghawar-oil", "type:arab-light")
    storage = portion(db, "test:abqaiq-oil", "type:arab-light")
    cargo = portion(db, "test:vlcc-cargo", "type:arab-light")

    record_event(
        db,
        event_type_id="type:produce",
        occurred_at=T0,
        provenance="derived",
        postings=[kg(deposit, -3.0e8), kg(storage, 3.0e8)],
    )
    record_event(
        db,
        event_type_id="type:load",
        occurred_at=T1,
        provenance="assumed",
        postings=[kg(storage, -2.7e8), kg(cargo, 2.7e8)],
    )

    assert balance_of(db, deposit, "mass") == pytest.approx(-3.0e8)
    assert balance_of(db, storage, "mass") == pytest.approx(0.3e8)
    assert balance_of(db, storage, "mass", at=T0) == pytest.approx(3.0e8)
    assert balance_of(db, cargo, "mass") == pytest.approx(2.7e8)


def test_record_event_rejects_invalid_input(db):
    a = portion(db, "test:a", "type:crude-oil")
    b = portion(db, "test:b", "type:crude-oil")
    with pytest.raises(LedgerError, match="does not balance"):
        record_event(
            db,
            event_type_id="type:transfer",
            occurred_at=T0,
            provenance="derived",
            postings=[kg(a, -1.0), kg(b, 2.0)],
        )
    with pytest.raises(LedgerError, match="is not an event type"):
        record_event(
            db,
            event_type_id="type:vessel",
            occurred_at=T0,
            provenance="derived",
            postings=[kg(a, -1.0), kg(b, 1.0)],
        )
    with pytest.raises(LedgerError, match="unknown entities"):
        record_event(
            db,
            event_type_id="type:transfer",
            occurred_at=T0,
            provenance="derived",
            postings=[kg(a, -1.0), kg("test:missing", 1.0)],
        )
    with pytest.raises(LedgerError, match="provenance"):
        record_event(
            db,
            event_type_id="type:transfer",
            occurred_at=T0,
            provenance="guess",
            postings=[kg(a, -1.0), kg(b, 1.0)],
        )


def test_extent_round_trips_geojson_and_checks_vertical_band(db):
    db.add(Entity(id="test:stratosphere", kind="place", level="object", name="Stratosphere"))
    db.flush()
    footprint = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    extent = EntityExtent(
        entity_id="test:stratosphere",
        geom=json.dumps(footprint),
        z_min_m=11_000,
        z_max_m=50_000,
    )
    db.add(extent)
    db.flush()
    db.expire(extent)
    assert json.loads(extent.geom)["type"] == "Polygon"

    savepoint = db.begin_nested()
    db.add(EntityExtent(entity_id="test:stratosphere", z_min_m=50_000, z_max_m=11_000))
    with pytest.raises(IntegrityError):
        db.flush()
    savepoint.rollback()
