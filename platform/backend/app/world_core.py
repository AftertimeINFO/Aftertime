"""Seed of the universal world core: the type lattice and the predicate vocabulary.

Types, predicates and conserved quantities are ordinary entities, so the domain
can grow by adding data rather than tables. See
docs/en/design/MATTER_FLOW_AND_LOCATIONS.md, sections 2 and 4.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import Entity, Relation, Source

SOURCE_ID = "aftertime-world-core"
TYPE_KIND = "type"
PREDICATE_KIND = "predicate"
META_LEVEL = "meta"

THING = "type:thing"
PREDICATE = "type:predicate"
EVENT_TYPE = "type:event-type"
CONSERVED_QUANTITY = "type:conserved-quantity"
PORTION = "type:portion"

# (id, name, parent id or None, description)
TYPES: list[tuple[str, str, str | None, str | None]] = [
    (THING, "Thing", None, "Root of the type lattice."),
    ("type:material", "Material", THING, None),
    ("type:substance", "Substance", "type:material", None),
    ("type:crude-oil", "Crude oil", "type:substance", None),
    ("type:arab-light", "Arab Light", "type:crude-oil", "Saudi crude grade."),
    ("type:refined-product", "Refined product", "type:substance", None),
    ("type:gasoline", "Gasoline", "type:refined-product", None),
    ("type:diesel", "Diesel", "type:refined-product", None),
    ("type:jet-fuel", "Jet fuel", "type:refined-product", None),
    ("type:fuel-oil", "Fuel oil", "type:refined-product", None),
    ("type:place", "Place", THING, None),
    ("type:sphere", "Sphere", "type:place", None),
    ("type:layer", "Layer", "type:place", None),
    ("type:water-body", "Water body", "type:place", None),
    ("type:region", "Region", "type:place", None),
    ("type:geologic-unit", "Geologic unit", "type:place", None),
    ("type:deposit", "Deposit", "type:place", None),
    (PORTION, "Portion", THING, "A bounded quantity of one material."),
    ("type:asset", "Asset", THING, None),
    ("type:storage", "Storage", "type:asset", None),
    ("type:vessel", "Vessel", "type:asset", None),
    ("type:pipeline-segment", "Pipeline segment", "type:asset", None),
    ("type:terminal", "Terminal", "type:asset", None),
    ("type:process-unit", "Process unit", "type:asset", None),
    ("type:process", "Process", THING, "Transformation template."),
    ("type:actor", "Actor", THING, None),
    ("type:state", "State", "type:actor", None),
    ("type:company", "Company", "type:actor", None),
    (EVENT_TYPE, "Event type", THING, None),
    ("type:produce", "Produce", EVENT_TYPE, None),
    ("type:transfer", "Transfer", EVENT_TYPE, None),
    ("type:load", "Load", EVENT_TYPE, None),
    ("type:depart", "Depart", EVENT_TYPE, None),
    ("type:arrive", "Arrive", EVENT_TYPE, None),
    ("type:discharge", "Discharge", EVENT_TYPE, None),
    ("type:transform", "Transform", EVENT_TYPE, None),
    ("type:quantity-kind", "Quantity kind", THING, None),
    (
        CONSERVED_QUANTITY,
        "Conserved quantity",
        "type:quantity-kind",
        "Postings of one event must net to zero for every conserved quantity.",
    ),
    (PREDICATE, "Predicate", THING, "Relation vocabulary."),
]

# (symbol, description)
PREDICATES: list[tuple[str, str]] = [
    ("instance_of", "Typing: entity is an instance of a type."),
    ("subclass_of", "Typing: type specialises another type."),
    ("part_of", "Composition; drives emergence and aggregation."),
    ("composed_of", "Chemical or material composition, with coefficient."),
    ("located_in", "Containment of a portion or asset in a place or asset; time-valid."),
    ("overlaps", "Spatial overlap computed from extents."),
    ("adjacent_to", "Spatial adjacency computed from extents."),
    ("connects", "A route or segment links two places or assets."),
    ("passes_through", "A route passes a chokepoint."),
    ("consumes", "Process input, coefficient per kg of reference input."),
    ("produces", "Process output, coefficient per kg of reference input."),
    ("can_hold", "What an asset type can contain."),
    ("capacity_of", "Capacity as coefficient."),
    ("operated_by", "Control: operator."),
    ("owned_by", "Control: owner."),
    ("jurisdiction_of", "Control: jurisdiction."),
    ("same_as", "Crosswalk between duplicates from different sources."),
]

# (symbol, name, canonical unit)
CONSERVED: list[tuple[str, str, str]] = [
    ("mass", "Mass", "kg"),
]


def predicate_id(symbol: str) -> str:
    return f"predicate:{symbol}"


def quantity_id(symbol: str) -> str:
    return f"quantity:{symbol}"


def _upsert_entity(
    db: Session,
    entity_id: str,
    *,
    kind: str,
    name: str,
    symbol: str | None = None,
    description: str | None = None,
    attributes: dict | None = None,
) -> None:
    entity = db.get(Entity, entity_id)
    attributes = {"seed": SOURCE_ID, **(attributes or {})}
    if entity is None:
        db.add(
            Entity(
                id=entity_id,
                kind=kind,
                level=META_LEVEL,
                name=name,
                symbol=symbol,
                description=description,
                attributes=attributes,
            )
        )
        return
    entity.kind = kind
    entity.level = META_LEVEL
    entity.name = name
    entity.symbol = symbol
    entity.description = description
    entity.attributes = {**(entity.attributes or {}), **attributes}


def _ensure_relation(db: Session, subject_id: str, predicate: str, object_id: str) -> None:
    relation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{subject_id}|{predicate}|{object_id}"))
    if db.get(Relation, relation_id) is None:
        db.add(
            Relation(
                id=relation_id,
                subject_id=subject_id,
                predicate=predicate,
                object_id=object_id,
                confidence=1,
                source_id=SOURCE_ID,
            )
        )


def seed_world_core(db: Session) -> None:
    """Additive and idempotent: creates or updates seed rows, never deletes."""
    db.merge(
        Source(
            id=SOURCE_ID,
            name="Aftertime world core vocabulary",
            url="https://github.com/AftertimeINFO/Aftertime/blob/DEV/docs/en/design/MATTER_FLOW_AND_LOCATIONS.md",
            license="CC0-1.0",
            adapter="bootstrap",
        )
    )
    for type_id, name, _, description in TYPES:
        _upsert_entity(db, type_id, kind=TYPE_KIND, name=name, description=description)
    for symbol, description in PREDICATES:
        _upsert_entity(
            db,
            predicate_id(symbol),
            kind=PREDICATE_KIND,
            name=symbol,
            symbol=symbol,
            description=description,
        )
    for symbol, name, unit in CONSERVED:
        _upsert_entity(
            db,
            quantity_id(symbol),
            kind="quantity",
            name=name,
            symbol=symbol,
            attributes={"canonical_unit": unit},
        )
    db.flush()

    for type_id, _, parent_id, _ in TYPES:
        if parent_id:
            _ensure_relation(db, type_id, "subclass_of", parent_id)
    for symbol, _ in PREDICATES:
        _ensure_relation(db, predicate_id(symbol), "instance_of", PREDICATE)
    for symbol, _, _ in CONSERVED:
        _ensure_relation(db, quantity_id(symbol), "instance_of", CONSERVED_QUANTITY)
    db.flush()
