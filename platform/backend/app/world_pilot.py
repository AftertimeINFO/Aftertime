"""Pilot: Arab Light crude from Ghawar to Jamnagar, approximated for one year.

The pilot is a thin vertical slice through the world core (see
docs/en/design/MATTER_FLOW_AND_LOCATIONS.md, section 9). It seeds places, assets,
vessels and portions as ordinary entities, a reserve estimate as an observation,
and turns one yearly flow figure into a deterministic sequence of ledger events:

    produce -> transfer -> load -> depart -> arrive -> discharge -> transfer -> transform

All numbers are approximations. Flow volume and timings are assumptions until the
BACI / JODI importers (phase 4) replace them; every event carries its provenance.
"""

import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Entity, EntityExtent, Observation, Relation, Source, WorldEvent
from app.services.world_ledger import PostingInput, record_event
from app.world_core import seed_world_core

RUN_ID = "pilot-saudi-india-2023"
SOURCE_ID = "aftertime-pilot-saudi-india"
YEAR = 2023

# Assumptions of the approximation. Stored on the source so the API can show them.
PARAMETERS = {
    "year": YEAR,
    "flow_bbl_per_day": 750_000,
    "cargo_bbl": 2_000_000,
    "kg_per_bbl": 136.4,
    "speed_knots": 13.0,
    "load_hours": 36,
    "discharge_hours": 36,
    "fleet_size": 5,
    "refinery_yields": {
        "type:gasoline": 0.22,
        "type:diesel": 0.38,
        "type:jet-fuel": 0.10,
        "type:fuel-oil": 0.10,
        "type:other-refinery-output": 0.20,
    },
    "notes": [
        "Flow volume is an order-of-magnitude assumption for Saudi crude delivered to India in"
        " 2023; it is replaced by BACI / JODI statistics in phase 4.",
        "The whole flow is routed through Sikka and Jamnagar; in reality it is split between"
        " several Indian ports and refineries.",
        "Vessels are synthetic. Sea lane and facility coordinates are schematic.",
        "Refinery yields are assumed mass shares that sum to one.",
    ],
}

# Pilot-specific types extend the core lattice: (id, name, parent).
PILOT_TYPES = [
    ("type:planet", "Planet", "type:place"),
    ("type:sea-lane", "Sea lane", "type:place"),
    ("type:other-refinery-output", "Other refinery outputs and losses", "type:material"),
]

# (id, name, type, part_of, located_in, description)
PLACES = [
    ("place:earth", "Earth", "type:planet", None, None, None),
    ("place:hydrosphere", "Hydrosphere", "type:sphere", "place:earth", None, None),
    ("place:lithosphere", "Lithosphere", "type:sphere", "place:earth", None, None),
    ("place:land-surface", "Land surface", "type:sphere", "place:earth", None, None),
    ("place:indian-ocean", "Indian Ocean", "type:water-body", "place:hydrosphere", None, None),
    ("place:persian-gulf", "Persian Gulf", "type:water-body", "place:indian-ocean", None, None),
    (
        "place:strait-of-hormuz",
        "Strait of Hormuz",
        "type:water-body",
        "place:indian-ocean",
        None,
        "Chokepoint between the Persian Gulf and the Gulf of Oman.",
    ),
    ("place:gulf-of-oman", "Gulf of Oman", "type:water-body", "place:arabian-sea", None, None),
    ("place:arabian-sea", "Arabian Sea", "type:water-body", "place:indian-ocean", None, None),
    ("place:gulf-of-kutch", "Gulf of Kutch", "type:water-body", "place:arabian-sea", None, None),
    ("place:saudi-arabia", "Saudi Arabia", "type:region", "place:land-surface", None, None),
    ("place:eastern-province", "Eastern Province", "type:region", "place:saudi-arabia", None, None),
    ("place:india", "India", "type:region", "place:land-surface", None, None),
    ("place:gujarat", "Gujarat", "type:region", "place:india", None, None),
    (
        "place:arabian-basin",
        "Arabian sedimentary basin",
        "type:geologic-unit",
        "place:lithosphere",
        None,
        None,
    ),
    (
        "place:ghawar",
        "Ghawar field",
        "type:deposit",
        "place:arabian-basin",
        "place:eastern-province",
        "Largest conventional oil field; Arab-D reservoir.",
    ),
    (
        "place:sea-lane-ras-tanura-sikka",
        "Sea lane Ras Tanura - Sikka",
        "type:sea-lane",
        "place:indian-ocean",
        None,
        "Schematic tanker route via the Strait of Hormuz.",
    ),
]

# (id, name, type, located_in, operator, jurisdiction)
ASSETS = [
    (
        "asset:abqaiq",
        "Abqaiq processing and storage",
        "type:storage",
        "place:eastern-province",
        "actor:saudi-aramco",
        "actor:saudi-arabia",
    ),
    (
        "asset:ras-tanura",
        "Ras Tanura terminal",
        "type:terminal",
        "place:eastern-province",
        "actor:saudi-aramco",
        "actor:saudi-arabia",
    ),
    (
        "asset:sikka",
        "Sikka marine terminal",
        "type:terminal",
        "place:gujarat",
        "actor:reliance",
        "actor:india",
    ),
    (
        "asset:jamnagar",
        "Jamnagar refinery",
        "type:process-unit",
        "place:gujarat",
        "actor:reliance",
        "actor:india",
    ),
]

ACTORS = [
    ("actor:saudi-arabia", "Saudi Arabia", "type:state"),
    ("actor:india", "India", "type:state"),
    ("actor:saudi-aramco", "Saudi Aramco", "type:company"),
    ("actor:reliance", "Reliance Industries", "type:company"),
]

# Schematic extents: (entity, GeoJSON geometry, z_min_m, z_max_m, z_surface_ref)
GHAWAR_OUTLINE = [
    [49.45, 24.0],
    [49.75, 24.0],
    [49.85, 25.2],
    [49.75, 26.3],
    [49.55, 26.3],
    [49.45, 25.2],
    [49.45, 24.0],
]
SEA_LANE = [
    [50.25, 26.70],
    [51.50, 26.95],
    [53.00, 26.65],
    [54.80, 26.45],
    [56.40, 26.62],
    [56.90, 26.20],
    [57.60, 25.20],
    [59.50, 24.20],
    [63.00, 23.20],
    [67.00, 22.60],
    [69.00, 22.62],
    [69.65, 22.55],
]
EXTENTS = [
    (
        "place:ghawar",
        {"type": "Polygon", "coordinates": [GHAWAR_OUTLINE]},
        -2300.0,
        -1900.0,
        "ground",
    ),
    (
        "place:sea-lane-ras-tanura-sikka",
        {"type": "LineString", "coordinates": SEA_LANE},
        None,
        None,
        None,
    ),
    ("place:persian-gulf", {"type": "Point", "coordinates": [51.3, 27.3]}, None, None, None),
    ("place:strait-of-hormuz", {"type": "Point", "coordinates": [56.35, 26.6]}, None, None, None),
    ("place:gulf-of-oman", {"type": "Point", "coordinates": [58.3, 24.9]}, None, None, None),
    ("place:arabian-sea", {"type": "Point", "coordinates": [63.0, 18.5]}, None, None, None),
    ("place:gulf-of-kutch", {"type": "Point", "coordinates": [69.6, 22.75]}, None, None, None),
    ("asset:abqaiq", {"type": "Point", "coordinates": [49.68, 25.94]}, None, None, None),
    ("asset:ras-tanura", {"type": "Point", "coordinates": [50.16, 26.64]}, None, None, None),
    ("asset:sikka", {"type": "Point", "coordinates": [69.80, 22.47]}, None, None, None),
    ("asset:jamnagar", {"type": "Point", "coordinates": [69.87, 22.35]}, None, None, None),
]

CRUDE = "type:arab-light"
VESSELS = [(f"vessel:pilot-vlcc-{i}", f"Pilot VLCC {i}") for i in range(1, 6)]

# Reserve estimate (remaining proved reserves) as reported from the Saudi Aramco 2019 bond
# prospectus. One proved figure only, so no P90/P10 bounds are stored.
GHAWAR_ESTIMATE = {
    "bbl": 48.25e9,
    "valid_time": datetime(2018, 12, 31, tzinfo=UTC),
    "evidence": {
        "system": "PRMS",
        "class": "1P",
        "basis": "remaining proved reserves, liquids",
        "reference": "Saudi Aramco bond prospectus, April 2019 (as reported)",
    },
}


def portion_id(holder_id: str, material_id: str) -> str:
    return f"portion:{holder_id.split(':', 1)[1]}:{material_id.split(':', 1)[1]}"


def _relation_id(subject_id: str, predicate: str, object_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{subject_id}|{predicate}|{object_id}"))


def _upsert(
    db: Session,
    entity_id: str,
    kind: str,
    name: str,
    *,
    level: str = "object",
    description: str | None = None,
    attributes: dict | None = None,
) -> None:
    entity = db.get(Entity, entity_id)
    attributes = {"pilot": RUN_ID, **(attributes or {})}
    if entity is None:
        db.add(
            Entity(
                id=entity_id,
                kind=kind,
                level=level,
                name=name,
                description=description,
                attributes=attributes,
            )
        )
        return
    entity.kind, entity.level, entity.name, entity.description = kind, level, name, description
    entity.attributes = {**(entity.attributes or {}), **attributes}


def _link(
    db: Session,
    subject_id: str,
    predicate: str,
    object_id: str,
    *,
    coefficient: float | None = None,
) -> None:
    relation_id = _relation_id(subject_id, predicate, object_id)
    if db.get(Relation, relation_id) is None:
        db.add(
            Relation(
                id=relation_id,
                subject_id=subject_id,
                predicate=predicate,
                object_id=object_id,
                coefficient=coefficient,
                confidence=1,
                source_id=SOURCE_ID,
            )
        )


def holders() -> list[tuple[str, list[str]]]:
    """Every entity that holds a portion, with the materials it holds."""
    products = list(PARAMETERS["refinery_yields"])
    rows = [("place:ghawar", [CRUDE]), ("asset:abqaiq", [CRUDE]), ("asset:ras-tanura", [CRUDE])]
    rows += [(vessel_id, [CRUDE]) for vessel_id, _ in VESSELS]
    rows += [("asset:sikka", [CRUDE]), ("asset:jamnagar", [CRUDE, *products])]
    return rows


def seed_pilot_world(db: Session) -> None:
    """Additive and idempotent: places, assets, vessels, portions, extents and estimate."""
    seed_world_core(db)
    db.merge(
        Source(
            id=SOURCE_ID,
            name="Aftertime pilot: Saudi Arabia to India crude, 2023",
            url="https://github.com/AftertimeINFO/Aftertime/blob/DEV/docs/en/design/"
            "MATTER_FLOW_AND_LOCATIONS.md",
            license="CC0-1.0",
            adapter="bootstrap",
            configuration=PARAMETERS,
        )
    )
    for type_id, name, _ in PILOT_TYPES:
        _upsert(db, type_id, "type", name, level="meta")
    for entity_id, name, _, _, _, description in PLACES:
        _upsert(db, entity_id, "place", name, description=description)
    for entity_id, name, _, _, _, _ in ASSETS:
        _upsert(db, entity_id, "asset", name)
    for entity_id, name, _ in ACTORS:
        _upsert(db, entity_id, "actor", name, level="institutional")
    for vessel_id, name in VESSELS:
        _upsert(
            db,
            vessel_id,
            "asset",
            name,
            attributes={
                "synthetic": True,
                "class": "VLCC",
                "capacity_bbl": PARAMETERS["cargo_bbl"],
            },
        )
    for holder_id, materials in holders():
        for material_id in materials:
            _upsert(
                db,
                portion_id(holder_id, material_id),
                "portion",
                f"{material_id.split(':', 1)[1]} at {holder_id.split(':', 1)[1]}",
                attributes={"holder": holder_id, "material": material_id},
            )
    db.flush()

    for type_id, _, parent_id in PILOT_TYPES:
        _link(db, type_id, "subclass_of", parent_id)
    for entity_id, _, type_id, part_of, located_in, _ in PLACES:
        _link(db, entity_id, "instance_of", type_id)
        if part_of:
            _link(db, entity_id, "part_of", part_of)
        if located_in:
            _link(db, entity_id, "located_in", located_in)
    for entity_id, _, type_id, located_in, operator, jurisdiction in ASSETS:
        _link(db, entity_id, "instance_of", type_id)
        _link(db, entity_id, "located_in", located_in)
        _link(db, entity_id, "operated_by", operator)
        _link(db, entity_id, "jurisdiction_of", jurisdiction)
    for entity_id, _, type_id in ACTORS:
        _link(db, entity_id, "instance_of", type_id)
    for vessel_id, _ in VESSELS:
        _link(db, vessel_id, "instance_of", "type:vessel")
    for holder_id, materials in holders():
        for material_id in materials:
            _link(db, portion_id(holder_id, material_id), "instance_of", material_id)
            _link(db, portion_id(holder_id, material_id), "instance_of", "type:portion")
            _link(db, portion_id(holder_id, material_id), "located_in", holder_id)
    _link(db, "place:sea-lane-ras-tanura-sikka", "connects", "asset:ras-tanura")
    _link(db, "place:sea-lane-ras-tanura-sikka", "connects", "asset:sikka")
    _link(db, "place:sea-lane-ras-tanura-sikka", "passes_through", "place:strait-of-hormuz")
    for product_id, share in PARAMETERS["refinery_yields"].items():
        _link(db, "asset:jamnagar", "produces", product_id, coefficient=share)
    _link(db, "asset:jamnagar", "consumes", CRUDE, coefficient=1.0)

    db.execute(delete(EntityExtent).where(EntityExtent.source_id == SOURCE_ID))
    for entity_id, geometry, z_min, z_max, z_ref in EXTENTS:
        db.add(
            EntityExtent(
                entity_id=entity_id,
                geom=json.dumps(geometry),
                z_min_m=z_min,
                z_max_m=z_max,
                z_surface_ref=z_ref,
                source_id=SOURCE_ID,
            )
        )

    deposit_portion = portion_id("place:ghawar", CRUDE)
    estimate_id = _relation_id(deposit_portion, "estimate", "mass")
    if db.get(Observation, estimate_id) is None:
        db.add(
            Observation(
                id=estimate_id,
                subject_id=deposit_portion,
                property="mass",
                value=GHAWAR_ESTIMATE["bbl"] * PARAMETERS["kg_per_bbl"],
                unit="kg",
                actuality="estimate",
                epistemic_status="estimated",
                valid_time=GHAWAR_ESTIMATE["valid_time"],
                source_id=SOURCE_ID,
                evidence={**GHAWAR_ESTIMATE["evidence"], "value_bbl": GHAWAR_ESTIMATE["bbl"]},
            )
        )
    db.flush()


def _haversine_nm(a: list[float], b: list[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 3440.065 * math.asin(math.sqrt(h))


def sea_lane_nm() -> float:
    return sum(_haversine_nm(a, b) for a, b in zip(SEA_LANE, SEA_LANE[1:], strict=False))


@dataclass
class _Vessel:
    id: str
    free_at: datetime
    moves: list[tuple[datetime, str, str]] = field(default_factory=list)


def _record(
    db: Session,
    event_type: str,
    at: datetime,
    provenance: str,
    postings: list[PostingInput],
    **attributes,
) -> WorldEvent:
    return record_event(
        db,
        event_type_id=event_type,
        occurred_at=at,
        provenance=provenance,
        postings=postings,
        source_id=SOURCE_ID,
        run_id=RUN_ID,
        attributes=attributes,
    )


def _move(db: Session, vessel: _Vessel, at: datetime, place_id: str, event_id: str) -> None:
    vessel.moves.append((at, place_id, event_id))


def generate_pilot_events(db: Session, *, force: bool = False) -> int:
    """Turn the yearly flow into ledger events. Returns the number of events written."""
    existing = db.scalar(select(WorldEvent.id).where(WorldEvent.run_id == RUN_ID).limit(1))
    if existing and not force:
        return 0
    if existing:
        run_events = select(WorldEvent.id).where(WorldEvent.run_id == RUN_ID)
        db.execute(delete(Relation).where(Relation.cause_event_id.in_(run_events)))
        db.execute(delete(WorldEvent).where(WorldEvent.run_id == RUN_ID))

    p = PARAMETERS
    cargo_kg = p["cargo_bbl"] * p["kg_per_bbl"]
    cargoes = round(p["flow_bbl_per_day"] * 365 / p["cargo_bbl"])
    interval = timedelta(days=365 / cargoes)
    transit = timedelta(hours=sea_lane_nm() / p["speed_knots"])
    load = timedelta(hours=p["load_hours"])
    discharge = timedelta(hours=p["discharge_hours"])
    start = datetime(p["year"], 1, 1, tzinfo=UTC)
    lane = "place:sea-lane-ras-tanura-sikka"
    yields = p["refinery_yields"]

    ghawar = portion_id("place:ghawar", CRUDE)
    abqaiq = portion_id("asset:abqaiq", CRUDE)
    ras_tanura = portion_id("asset:ras-tanura", CRUDE)
    sikka = portion_id("asset:sikka", CRUDE)
    jamnagar = portion_id("asset:jamnagar", CRUDE)
    fleet = [_Vessel(vessel_id, start) for vessel_id, _ in VESSELS]
    for vessel in fleet:
        _move(db, vessel, start - timedelta(days=1), "asset:ras-tanura", "")

    def kg(entity_id: str, delta: float) -> PostingInput:
        return PostingInput(entity_id, "mass", delta, "kg")

    count = 0
    for k in range(cargoes):
        ready = start + interval * k + timedelta(hours=12)
        voyage = f"{RUN_ID}:cargo-{k + 1:03d}"
        _record(
            db,
            "type:produce",
            ready - timedelta(days=2),
            "derived",
            [kg(ghawar, -cargo_kg), kg(abqaiq, cargo_kg)],
            voyage=voyage,
        )
        _record(
            db,
            "type:transfer",
            ready - timedelta(days=1),
            "derived",
            [kg(abqaiq, -cargo_kg), kg(ras_tanura, cargo_kg)],
            voyage=voyage,
            mode="pipeline",
        )

        vessel = min(fleet, key=lambda v: v.free_at)
        cargo = portion_id(vessel.id, CRUDE)
        load_at = max(ready, vessel.free_at)
        depart_at = load_at + load
        arrive_at = depart_at + transit
        discharged_at = arrive_at + discharge
        back_at = discharged_at + transit

        _record(
            db,
            "type:load",
            load_at,
            "derived",
            [kg(ras_tanura, -cargo_kg), kg(cargo, cargo_kg)],
            voyage=voyage,
            vessel=vessel.id,
        )
        departed = _record(
            db,
            "type:depart",
            depart_at,
            "assumed",
            [],
            voyage=voyage,
            vessel=vessel.id,
            route=lane,
            direction="laden",
            cargo_kg=cargo_kg,
            arrive_at=arrive_at.isoformat(),
        )
        _move(db, vessel, depart_at, lane, departed.id)
        arrived = _record(
            db,
            "type:arrive",
            arrive_at,
            "assumed",
            [],
            voyage=voyage,
            vessel=vessel.id,
            place="asset:sikka",
        )
        _move(db, vessel, arrive_at, "asset:sikka", arrived.id)
        _record(
            db,
            "type:discharge",
            discharged_at,
            "derived",
            [kg(cargo, -cargo_kg), kg(sikka, cargo_kg)],
            voyage=voyage,
            vessel=vessel.id,
        )
        _record(
            db,
            "type:transfer",
            discharged_at + timedelta(hours=12),
            "derived",
            [kg(sikka, -cargo_kg), kg(jamnagar, cargo_kg)],
            voyage=voyage,
            mode="pipeline",
        )
        _record(
            db,
            "type:transform",
            discharged_at + timedelta(days=2),
            "derived",
            [kg(jamnagar, -cargo_kg)]
            + [
                kg(portion_id("asset:jamnagar", product), cargo_kg * share)
                for product, share in yields.items()
            ],
            voyage=voyage,
            process="refining",
        )
        ballast = _record(
            db,
            "type:depart",
            discharged_at,
            "assumed",
            [],
            voyage=f"{voyage}:ballast",
            vessel=vessel.id,
            route=lane,
            direction="ballast",
            cargo_kg=0,
            arrive_at=back_at.isoformat(),
        )
        _move(db, vessel, discharged_at, lane, ballast.id)
        returned = _record(
            db,
            "type:arrive",
            back_at,
            "assumed",
            [],
            voyage=f"{voyage}:ballast",
            vessel=vessel.id,
            place="asset:ras-tanura",
        )
        _move(db, vessel, back_at, "asset:ras-tanura", returned.id)
        vessel.free_at = back_at
        count += 10

    # Vessel location history as time-valid located_in relations caused by the events.
    for vessel in fleet:
        moves = vessel.moves
        for (at, place_id, event_id), following in zip(moves, [*moves[1:], None], strict=True):
            if not event_id:
                continue
            db.add(
                Relation(
                    subject_id=vessel.id,
                    predicate="located_in",
                    object_id=place_id,
                    confidence=1,
                    source_id=SOURCE_ID,
                    valid_from=at,
                    valid_to=following[0] if following else None,
                    cause_event_id=event_id,
                )
            )
    db.flush()
    return count
