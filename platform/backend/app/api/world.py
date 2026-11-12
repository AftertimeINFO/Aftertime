"""Read API of the world core: entity browser, entity cards and pilot playback."""

import json
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app import __version__
from app.db import get_db
from app.layers import LAYER_POLICY, current_layer
from app.models import Entity, EntityExtent, Observation, Posting, Relation, Source, WorldEvent
from app.services.world_balance import BalanceError, balance, balance_series
from app.services.world_compute import ComputeError, check_period, compute, coverage, overview
from app.services.world_query import FAR_FUTURE, contents, operations, runs_of
from app.services.world_scope import scope_tree
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
def pilot_playback(
    start: datetime | None = Query(None, alias="from"),
    end: datetime | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> dict:
    """Everything the 2D player needs for the pilot run in a window of at most a year.

    The window defaults to the first year of the computed coverage. ``initial`` holds the
    net postings of every portion before the window, so the player starts from them.
    """
    source = db.get(Source, SOURCE_ID)
    if source is None:
        raise HTTPException(404, "Pilot run is not seeded")
    covered = coverage(db)
    lo = _moment(start) if start else (
        datetime.fromisoformat(covered["from"]).replace(tzinfo=UTC) if covered else datetime(2019, 1, 1, tzinfo=UTC)
    )
    hi = _moment(end) if end else lo + timedelta(days=366)
    hi = min(hi, lo + timedelta(days=366))

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

    window = (WorldEvent.run_id == RUN_ID, WorldEvent.occurred_at >= lo, WorldEvent.occurred_at < hi)
    events = db.scalars(select(WorldEvent).where(*window).order_by(WorldEvent.occurred_at)).all()
    postings: dict[str, list] = {}
    for event_id, entity_id, delta in db.execute(
        select(Posting.event_id, Posting.entity_id, Posting.delta)
        .join(WorldEvent, WorldEvent.id == Posting.event_id)
        .where(*window, Posting.property == "mass")
    ):
        postings.setdefault(event_id, []).append([entity_id, delta])
    initial = {
        entity_id: float(total)
        for entity_id, total in db.execute(
            select(Posting.entity_id, func.sum(Posting.delta))
            .join(WorldEvent, WorldEvent.id == Posting.event_id)
            .where(WorldEvent.run_id == RUN_ID, WorldEvent.occurred_at < lo, Posting.property == "mass")
            .group_by(Posting.entity_id)
        )
    }

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
            "arrive": (
                arrivals[e.attributes["voyage"]].isoformat()
                if e.attributes["voyage"] in arrivals
                else e.attributes.get("arrive_at")
            ),
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
        "window": {"from": lo.isoformat(), "to": hi.isoformat()},
        "coverage": covered,
        "initial": initial,
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


@router.get("/scopes")
def scopes(db: Session = Depends(get_db)) -> dict:
    """Scope trees of both axes: geography (Earth to asset) and control (state to asset)."""
    return scope_tree(db)


@router.get("/balance")
def material_balance(
    scope: str,
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
    level: str = "substance",
    db: Session = Depends(get_db),
) -> dict:
    """Trial balance of matter for a scope and period, by level of matter."""
    try:
        check_period(db, _moment(start), _moment(end))
        result = balance(db, scope, _moment(start), _moment(end), level)
    except BalanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ComputeError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    result["coverage"] = coverage(db)
    return result


@router.get("/balance/series")
def material_balance_series(
    scope: str,
    row: str,
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
    level: str = "substance",
    step: str = "month",
    flow: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """One balance row (or one flow of it) by month, quarter or year: turnover statement and chart."""
    try:
        check_period(db, _moment(start), _moment(end))
        result = balance_series(db, scope, _moment(start), _moment(end), level, row, step, flow)
    except BalanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ComputeError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    result["coverage"] = coverage(db)
    return result


class ComputeRequest(BaseModel):
    horizon: date
    growth_pct: float = 0.0
    note: str = Field("", max_length=2000)


@router.get("/coverage")
def world_coverage(db: Session = Depends(get_db)) -> dict:
    """How far the world is computed in this layer, yearly flows and the computation journal."""
    return {"layer": current_layer.get(), **overview(db)}


@router.post("/compute")
def world_compute(body: ComputeRequest, db: Session = Depends(get_db)) -> dict:
    """Recompute the world ledger from the start of history to the horizon (inclusive)."""
    layer = current_layer.get()
    if "compute" not in LAYER_POLICY[layer]["capabilities"]:
        raise HTTPException(403, f"Розрахунок світу недоступний у шарі {LAYER_POLICY[layer]['label']}")
    try:
        return {"layer": layer, **compute(db, body.horizon, body.growth_pct, body.note)}
    except ComputeError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
