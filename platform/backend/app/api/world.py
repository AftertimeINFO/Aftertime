"""Read API of the world core for 2D playback of the pilot run."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Entity, EntityExtent, Observation, Posting, Relation, Source, WorldEvent
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

    estimate = db.scalar(
        select(Observation)
        .where(Observation.subject_id == portion_id("place:ghawar", "type:arab-light"))
        .order_by(Observation.valid_time.desc())
        .limit(1)
    )
    return {
        "run_id": RUN_ID,
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
