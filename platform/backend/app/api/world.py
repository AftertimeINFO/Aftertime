"""Read API of the world core: entity browser, entity cards and pilot playback."""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app import __version__
from app.db import get_db
from app.models import Entity, EntityExtent, Observation, Posting, Relation, Source, WorldEvent
from app.services.world_query import FAR_FUTURE, contents, operations, runs_of
from app.world_pilot import RUN_ID, SOURCE_ID, portion_id

router = APIRouter(prefix="/api/v1/world")


def _types(db: Session, ids: set[str]) -> dict[str, str]:
    rows = db.execute(
        select(Relation.subject_id, Relation.object_id).where(
            Relation.subject_id.in_(ids),
            Relation.predicate == "instance_of",
            Relation.object_id != "type:portion",
        )
    )
    return {subject: obj for subject, obj in rows}


@router.get("/version")
def version() -> dict:
    """API version, shown next to the UI version on world pages."""
    return {"api": __version__}


def _moment(at: datetime | None) -> datetime:
    if at is None:
        return FAR_FUTURE
    return at if at.tzinfo else at.replace(tzinfo=UTC)


@router.get("/entities")
def list_entities(
    q: str | None = None,
    kind: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Every entity of the world model, searchable by name or id and filterable by kind."""
    filters = []
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(Entity.name.ilike(pattern), Entity.id.ilike(pattern)))
    kinds = dict(
        db.execute(select(Entity.kind, func.count()).where(*filters).group_by(Entity.kind)).all()
    )
    if kind:
        filters.append(Entity.kind == kind)
    total = db.scalar(select(func.count()).select_from(Entity).where(*filters))
    rows = db.scalars(
        select(Entity)
        .where(*filters)
        .order_by(Entity.kind, Entity.name)
        .limit(limit)
        .offset(offset)
    ).all()
    types = _types(db, {row.id for row in rows}) if rows else {}
    return {
        "total": total,
        "kinds": kinds,
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "kind": row.kind,
                "level": row.level,
                "symbol": row.symbol,
                "type": types.get(row.id),
            }
            for row in rows
        ],
    }


@router.get("/entities/{entity_id}")
def entity_card(entity_id: str, at: datetime | None = None, db: Session = Depends(get_db)) -> dict:
    """One entity with its relations, extents, estimates, contained matter and operations."""
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(404, "Entity not found")
    moment = _moment(at)
    other = aliased(Entity)
    valid = [
        or_(Relation.valid_from.is_(None), Relation.valid_from <= moment),
        or_(Relation.valid_to.is_(None), Relation.valid_to > moment),
    ]

    def relations(direction: str) -> list[dict]:
        mine, theirs = (
            (Relation.subject_id, Relation.object_id)
            if direction == "out"
            else (Relation.object_id, Relation.subject_id)
        )
        rows = db.execute(
            select(Relation, other.name, other.kind)
            .join(other, other.id == theirs)
            .where(mine == entity_id, *valid)
            .order_by(Relation.predicate, other.name)
            .limit(200)
        ).all()
        return [
            {
                "predicate": relation.predicate,
                "entity_id": relation.object_id if direction == "out" else relation.subject_id,
                "name": name,
                "kind": kind,
                "coefficient": relation.coefficient,
                "unit": relation.unit,
                "valid_from": relation.valid_from.isoformat() if relation.valid_from else None,
                "valid_to": relation.valid_to.isoformat() if relation.valid_to else None,
                "cause_event_id": relation.cause_event_id,
            }
            for relation, name, kind in rows
        ]

    extents = db.scalars(select(EntityExtent).where(EntityExtent.entity_id == entity_id)).all()
    observations = db.scalars(
        select(Observation)
        .where(Observation.subject_id == entity_id)
        .order_by(Observation.valid_time.desc())
        .limit(50)
    ).all()
    return {
        "entity": {
            "id": entity.id,
            "name": entity.name,
            "kind": entity.kind,
            "level": entity.level,
            "symbol": entity.symbol,
            "description": entity.description,
            "jurisdiction": entity.jurisdiction,
            "attributes": entity.attributes,
        },
        "at": None if at is None else moment.isoformat(),
        "outgoing": relations("out"),
        "incoming": relations("in"),
        "extents": [
            {
                "geometry": json.loads(extent.geom) if extent.geom else None,
                "z_min_m": extent.z_min_m,
                "z_max_m": extent.z_max_m,
                "z_surface_ref": extent.z_surface_ref,
            }
            for extent in extents
        ],
        "observations": [
            {
                "property": o.property,
                "value": o.value,
                "unit": o.unit,
                "low": o.uncertainty_low,
                "high": o.uncertainty_high,
                "valid_time": o.valid_time.isoformat(),
                "epistemic_status": o.epistemic_status,
                "evidence": o.evidence,
                "source_id": o.source_id,
            }
            for o in observations
        ],
        "contents": contents(db, entity_id, moment),
        "operations": operations(db, entity_id, at=moment, limit=50),
        "runs": runs_of(db, entity_id),
    }


@router.get("/entities/{entity_id}/operations")
def entity_operations(
    entity_id: str,
    at: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(Entity, entity_id) is None:
        raise HTTPException(404, "Entity not found")
    return operations(db, entity_id, at=_moment(at), limit=limit, offset=offset)


@router.get("/pilot")
def pilot_playback(db: Session = Depends(get_db)) -> dict:
    """Everything the 2D player needs for the pilot run, in one payload."""
    source = db.get(Source, SOURCE_ID)
    if source is None:
        raise HTTPException(404, "Pilot run is not seeded")

    extents = db.execute(
        select(EntityExtent, Entity)
        .join(Entity, Entity.id == EntityExtent.entity_id)
        .where(EntityExtent.source_id == SOURCE_ID)
    ).all()
    types = _types(db, {entity.id for _, entity in extents})
    places = [
        {
            "id": entity.id,
            "name": entity.name,
            "kind": entity.kind,
            "type": types.get(entity.id),
            "geometry": json.loads(extent.geom) if extent.geom else None,
            "z_min_m": extent.z_min_m,
            "z_max_m": extent.z_max_m,
        }
        for extent, entity in extents
    ]

    portions = [
        {
            "id": entity.id,
            "holder": entity.attributes.get("holder"),
            "material": entity.attributes.get("material"),
        }
        for entity in db.scalars(
            select(Entity).where(
                Entity.kind == "portion", Entity.attributes["pilot"].astext == RUN_ID
            )
        )
    ]
    names_needed = {p["holder"] for p in portions} | {p["material"] for p in portions}
    names = {
        entity_id: name
        for entity_id, name in db.execute(
            select(Entity.id, Entity.name).where(Entity.id.in_(names_needed))
        )
    }

    events = db.scalars(
        select(WorldEvent).where(WorldEvent.run_id == RUN_ID).order_by(WorldEvent.occurred_at)
    ).all()
    postings: dict[str, list] = {}
    for event_id, entity_id, delta in db.execute(
        select(Posting.event_id, Posting.entity_id, Posting.delta)
        .join(WorldEvent, WorldEvent.id == Posting.event_id)
        .where(WorldEvent.run_id == RUN_ID, Posting.property == "mass")
    ):
        postings.setdefault(event_id, []).append([entity_id, delta])

    arrivals = {
        e.attributes.get("voyage"): e.occurred_at
        for e in events
        if e.event_type_id == "type:arrive"
    }
    voyages = [
        {
            "id": e.attributes["voyage"],
            "vessel": e.attributes["vessel"],
            "route": e.attributes["route"],
            "direction": e.attributes["direction"],
            "cargo_kg": e.attributes.get("cargo_kg", 0),
            "depart": e.occurred_at.isoformat(),
            "arrive": arrivals[e.attributes["voyage"]].isoformat(),
        }
        for e in events
        if e.event_type_id == "type:depart"
    ]

    pilot_entities = db.scalars(
        select(Entity)
        .where(Entity.attributes["pilot"].astext == RUN_ID, Entity.level != "meta")
        .order_by(Entity.kind, Entity.name)
    ).all()
    kinds_of = _types(db, {entity.id for entity in pilot_entities})
    estimate = db.scalar(
        select(Observation)
        .where(Observation.subject_id == portion_id("place:ghawar", "type:arab-light"))
        .order_by(Observation.valid_time.desc())
        .limit(1)
    )
    objects = [
        {"id": entity.id, "name": entity.name, "kind": entity.kind, "type": kinds_of.get(entity.id)}
        for entity in pilot_entities
    ]
    return {
        "run_id": RUN_ID,
        "objects": objects,
        "source": {"id": source.id, "name": source.name, "license": source.license},
        "parameters": source.configuration,
        "places": places,
        "names": names,
        "portions": portions,
        "voyages": voyages,
        "events": [
            {
                "id": e.id,
                "t": e.occurred_at.isoformat(),
                "type": e.event_type_id,
                "provenance": e.provenance,
                "attributes": e.attributes,
                "postings": postings.get(e.id, []),
            }
            for e in events
        ],
        "estimate": None
        if estimate is None
        else {
            "portion": estimate.subject_id,
            "value_kg": estimate.value,
            "low_kg": estimate.uncertainty_low,
            "high_kg": estimate.uncertainty_high,
            "valid_time": estimate.valid_time.isoformat(),
            "evidence": estimate.evidence,
        },
    }
