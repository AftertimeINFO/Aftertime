"""Append-only event ledger of the world core.

An event is a header plus signed postings. For every conserved quantity (an
entity that is ``instance_of`` the Conserved quantity type) the postings of one
event must net to zero: matter is moved, split, merged or transformed, never
created or destroyed. See docs/en/design/MATTER_FLOW_AND_LOCATIONS.md, 4.1 and 6.1.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Entity, Posting, Relation, WorldEvent
from app.world_core import CONSERVED_QUANTITY, EVENT_TYPE

PROVENANCES = frozenset({"statistic", "derived", "assumed", "forecast"})
RELATIVE_TOLERANCE = 1e-9


class LedgerError(ValueError):
    """The event cannot be recorded as given."""


@dataclass(frozen=True)
class PostingInput:
    entity_id: str
    property: str
    delta: float
    unit: str


def is_subtype(db: Session, type_id: str, ancestor_id: str) -> bool:
    """True when ``type_id`` equals ``ancestor_id`` or reaches it via ``subclass_of``."""
    if type_id == ancestor_id:
        return True
    found = db.execute(
        text(
            """
            WITH RECURSIVE up(id) AS (
                SELECT object_id FROM relations
                WHERE subject_id = :type_id AND predicate = 'subclass_of'
                UNION
                SELECT r.object_id FROM relations r JOIN up ON r.subject_id = up.id
                WHERE r.predicate = 'subclass_of'
            )
            SELECT 1 FROM up WHERE id = :ancestor_id LIMIT 1
            """
        ),
        {"type_id": type_id, "ancestor_id": ancestor_id},
    ).first()
    return found is not None


def conserved_units(db: Session) -> dict[str, str]:
    """Conserved property symbol -> canonical unit, read from the vocabulary."""
    rows = db.execute(
        select(Entity.symbol, Entity.attributes)
        .join(Relation, Relation.subject_id == Entity.id)
        .where(Relation.predicate == "instance_of", Relation.object_id == CONSERVED_QUANTITY)
    )
    return {symbol: (attributes or {}).get("canonical_unit", "") for symbol, attributes in rows}


def check_balance(postings: Iterable[PostingInput], conserved: dict[str, str]) -> None:
    """Raise LedgerError unless every conserved quantity nets to zero in its canonical unit."""
    net: dict[str, float] = defaultdict(float)
    gross: dict[str, float] = defaultdict(float)
    for posting in postings:
        unit = conserved.get(posting.property)
        if unit is None:
            continue
        if posting.unit != unit:
            raise LedgerError(
                f"{posting.property} must be posted in {unit}, got {posting.unit}"
            )
        net[posting.property] += posting.delta
        gross[posting.property] += abs(posting.delta)
    for prop, value in net.items():
        if abs(value) > RELATIVE_TOLERANCE * max(1.0, gross[prop]):
            raise LedgerError(f"{prop} does not balance: net {value} {conserved[prop]}")


def record_event(
    db: Session,
    *,
    event_type_id: str,
    occurred_at: datetime,
    provenance: str,
    postings: Iterable[PostingInput],
    source_id: str | None = None,
    scenario_id: str | None = None,
    run_id: str | None = None,
    attributes: dict | None = None,
) -> WorldEvent:
    """Validate and append one event with its postings. Does not commit."""
    if provenance not in PROVENANCES:
        raise LedgerError(f"unknown provenance {provenance!r}")
    if occurred_at.tzinfo is None:
        raise LedgerError("occurred_at must be timezone-aware")
    if not is_subtype(db, event_type_id, EVENT_TYPE):
        raise LedgerError(f"{event_type_id} is not an event type")
    # Events without postings are allowed: a departure or arrival moves an asset
    # (a located_in relation caused by the event) without changing any quantity.
    items = list(postings)
    missing = {p.entity_id for p in items} - set(
        db.scalars(select(Entity.id).where(Entity.id.in_({p.entity_id for p in items})))
    )
    if missing:
        raise LedgerError(f"unknown entities: {sorted(missing)}")
    check_balance(items, conserved_units(db))

    event = WorldEvent(
        event_type_id=event_type_id,
        occurred_at=occurred_at,
        provenance=provenance,
        source_id=source_id,
        scenario_id=scenario_id,
        run_id=run_id,
        attributes=attributes or {},
    )
    db.add(event)
    db.flush()
    db.add_all(
        Posting(
            event_id=event.id,
            entity_id=p.entity_id,
            property=p.property,
            delta=p.delta,
            unit=p.unit,
        )
        for p in items
    )
    db.flush()
    return event


def balance_of(
    db: Session, entity_id: str, prop: str, *, at: datetime | None = None
) -> float:
    """Net of all postings on one entity property, up to and including ``at``."""
    query = (
        select(func.coalesce(func.sum(Posting.delta), 0.0))
        .join(WorldEvent, WorldEvent.id == Posting.event_id)
        .where(Posting.entity_id == entity_id, Posting.property == prop)
    )
    if at is not None:
        query = query.where(WorldEvent.occurred_at <= at)
    return float(db.scalar(query))
