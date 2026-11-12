"""Pilot: Arab Light crude from Ghawar to Jamnagar, from 2019 history to a forecast horizon.

The pilot is a thin vertical slice through the world core (see
docs/en/design/MATTER_FLOW_AND_LOCATIONS.md, section 9). It seeds places, assets,
vessels and portions as ordinary entities, a reserve estimate as an observation,
and turns yearly flow figures (history, then a forecast) into a deterministic sequence
of ledger events:

    produce -> transfer -> load -> depart -> arrive -> discharge -> transfer -> transform

Yearly volumes of Saudi crude delivered to India come from published trade figures
(``HISTORY``, each with its reference); years after the history are a forecast. Timings,
vessels and the single route are assumptions; every event carries its provenance.

The rest of Ghawar's output (``GHAWAR_HISTORY``: Saudi crude output times Ghawar's share
of Aramco's capacity) leaves the field monthly into one aggregate off-take, so the field
balance shows its whole production, not only the cargoes of the pilot route.
"""

import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.models import Entity, EntityExtent, Observation, Posting, Relation, Source, WorldEvent
from app.services.world_ledger import PostingInput, check_balance, conserved_units
from app.world_core import seed_world_core

RUN_ID = "pilot-saudi-india"
LEGACY_RUN_IDS = ("pilot-saudi-india-2023",)
SOURCE_ID = "aftertime-pilot-saudi-india"
YEAR = 2023  # reference year of the first pilot, kept for playback defaults

# Saudi crude delivered to India per calendar year, barrels per day:
# (bbl/d, provenance, reference). "statistic" is a published annual figure; "derived" is
# computed from a published share or from fiscal-year (April-March) tonnage at 7.33 bbl/t.
HISTORY: dict[int, tuple[float, str, str]] = {
    2019: (855_000, "statistic", "Argus Media: India's Saudi crude imports 855,000 b/d in 2019"),
    2020: (753_000, "statistic", "Argus Media: 753,000 b/d in 2020 (Covid-19 demand loss)"),
    2021: (670_000, "derived", "NBR: 16% of India's 4.2 mb/d crude imports in 2021"),
    2022: (793_000, "derived", "Embassy of India, Riyadh: 39.47 Mt in FY2022-23"),
    2023: (708_000, "derived", "Informist: 15% of India's 4.72 mb/d crude imports in 2023"),
    2024: (626_000, "statistic", "Informist / MoneyWire: 625,997 b/d in 2024"),
    2025: (705_000, "derived", "Embassy of India, Riyadh: 33.14 Mt FY2024-25, 35.88 Mt FY2025-26"),
}
# Ghawar's share of Saudi crude output: its maximum sustainable capacity over Aramco's
# (3.8 of 12.0 mb/d, Saudi Aramco bond prospectus, April 2019, as of 31.12.2018).
GHAWAR_SHARE = 3.8 / 12.0
GHAWAR_SHARE_REFERENCE = (
    "Saudi Aramco bond prospectus, April 2019: Ghawar MSC 3.8 mb/d of Aramco's 12.0 mb/d"
)
# Saudi crude oil output per calendar year, barrels per day: (bbl/d, reference).
SAUDI_CRUDE: dict[int, tuple[float, str]] = {
    2019: (9_808_000, "OPEC Annual Statistical Bulletin 2020: 9.81 mb/d"),
    2020: (9_213_000, "OPEC data via Arab News: 9.22 mb/d"),
    2021: (9_125_000, "OPEC Annual Statistical Bulletin 2022 via S&P Global: 9.125 mb/d"),
    2022: (10_591_000, "OPEC Annual Statistical Bulletin 2023 (EIA: 10.4-10.6 mb/d)"),
    2023: (9_606_000, "OPEC Annual Statistical Bulletin 2025: 9,606 kb/d"),
    2024: (8_955_000, "OPEC Annual Statistical Bulletin 2025: 8,955 kb/d"),
    2025: (9_484_000, "GASTAT: 3,461.8 million barrels in 2025"),
}
# Whole Ghawar output, barrels per day: derived from the two figures above.
GHAWAR_HISTORY: dict[int, tuple[float, str, str]] = {
    year: (bbl * GHAWAR_SHARE, "derived", f"{reference}; x {GHAWAR_SHARE:.4f} ({GHAWAR_SHARE_REFERENCE})")
    for year, (bbl, reference) in SAUDI_CRUDE.items()
}
OFFTAKE = "place:ghawar-other-offtake"

HISTORY_FROM = datetime(min(HISTORY), 1, 1, tzinfo=UTC)
HISTORY_TO = datetime(max(HISTORY) + 1, 1, 1, tzinfo=UTC)
MAX_HORIZON = datetime(2051, 1, 1, tzinfo=UTC)

# Assumptions of the approximation. Stored on the source so the API can show them.
PARAMETERS = {
    "year": YEAR,
    "flow_bbl_per_day": 750_000,
    "cargo_bbl": 2_000_000,
    "kg_per_bbl": 136.4,
    "speed_knots": 13.0,
    "load_hours": 36,
    "discharge_hours": 36,
    "fleet_size": 8,
    "refinery_yields": {
        "type:gasoline": 0.22,
        "type:diesel": 0.38,
        "type:jet-fuel": 0.10,
        "type:fuel-oil": 0.10,
        "type:other-refinery-output": 0.20,
    },
    "notes": [
        "Yearly flow volumes 2019-2025 are published trade figures or derived from published"
        " shares and fiscal-year tonnage (see history); later years are a forecast.",
        "The whole flow is routed through Sikka and Jamnagar; in reality it is split between"
        " several Indian ports and refineries.",
        "Ghawar output is Saudi crude output times Ghawar's share of Aramco's capacity"
        " (3.8 of 12.0 mb/d); what does not go to India leaves the field monthly into one"
        " aggregate off-take (domestic refining and other exports) outside Saudi Arabia.",
        "Vessels are synthetic. Sea lane and facility coordinates are schematic.",
        "Refinery yields are assumed mass shares that sum to one.",
        "Element compositions are typical values; the composition of other refinery outputs"
        " is the residual that closes the element balance of refining.",
    ],
}

# Chemical elements: (symbol, name, molar mass g/mol).
ELEMENTS = [
    ("C", "Carbon", 12.011),
    ("H", "Hydrogen", 1.008),
    ("S", "Sulfur", 32.06),
    ("N", "Nitrogen", 14.007),
    ("O", "Oxygen", 15.999),
]

# Typical element mass fractions (kg/kg). Other refinery outputs are computed as the residual.
COMPOSITION: dict[str, dict[str, float]] = {
    "type:arab-light": {"C": 0.8465, "H": 0.1295, "S": 0.0195, "N": 0.0015, "O": 0.0030},
    "type:gasoline": {"C": 0.865, "H": 0.135},
    "type:diesel": {"C": 0.862, "H": 0.13799, "S": 0.00001},
    "type:jet-fuel": {"C": 0.858, "H": 0.142},
    "type:fuel-oil": {"C": 0.870, "H": 0.113, "S": 0.005, "N": 0.003, "O": 0.009},
}


def element_id(symbol: str) -> str:
    return f"element:{symbol.lower()}"


def compositions() -> dict[str, dict[str, float]]:
    """Material compositions, with the residual output closing the refining element balance."""
    yields = PARAMETERS["refinery_yields"]
    other = "type:other-refinery-output"
    residual = {}
    for symbol, _, _ in ELEMENTS:
        known = sum(
            share * COMPOSITION[product].get(symbol, 0.0)
            for product, share in yields.items()
            if product != other
        )
        residual[symbol] = (COMPOSITION["type:arab-light"].get(symbol, 0.0) - known) / yields[other]
    return {**COMPOSITION, other: {s: f for s, f in residual.items() if f > 0}}


# Pilot-specific types extend the core lattice: (id, name, parent).
PILOT_TYPES = [
    ("type:planet", "Planet", "type:place"),
    ("type:sea-lane", "Sea lane", "type:place"),
    ("type:other-refinery-output", "Other refinery outputs and losses", "type:material"),
    ("type:chemical-element", "Chemical element", "type:substance"),
    ("type:aggregate-offtake", "Aggregate off-take", "type:place"),
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
        OFFTAKE,
        "Other Ghawar off-take (aggregate)",
        "type:aggregate-offtake",
        "place:earth",
        None,
        "Ghawar crude outside the pilot route: Saudi refineries and exports to other"
        " destinations, aggregated.",
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
VESSELS = [(f"vessel:pilot-vlcc-{i}", f"Pilot VLCC {i}") for i in range(1, 9)]

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
    symbol: str | None = None,
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
                symbol=symbol,
                description=description,
                attributes=attributes,
            )
        )
        return
    entity.kind, entity.level, entity.name, entity.description = kind, level, name, description
    entity.symbol = symbol
    entity.attributes = {**(entity.attributes or {}), **attributes}


def _link(
    db: Session,
    subject_id: str,
    predicate: str,
    object_id: str,
    *,
    coefficient: float | None = None,
    unit: str | None = None,
) -> None:
    relation_id = _relation_id(subject_id, predicate, object_id)
    relation = db.get(Relation, relation_id)
    if relation is None:
        db.add(
            Relation(
                id=relation_id,
                subject_id=subject_id,
                predicate=predicate,
                object_id=object_id,
                coefficient=coefficient,
                unit=unit,
                confidence=1,
                source_id=SOURCE_ID,
            )
        )
        return
    relation.coefficient, relation.unit = coefficient, unit


def holders() -> list[tuple[str, list[str]]]:
    """Every entity that holds a portion, with the materials it holds."""
    products = list(PARAMETERS["refinery_yields"])
    rows = [("place:ghawar", [CRUDE]), ("asset:abqaiq", [CRUDE]), ("asset:ras-tanura", [CRUDE])]
    rows += [(OFFTAKE, [CRUDE])]
    rows += [(vessel_id, [CRUDE]) for vessel_id, _ in VESSELS]
    rows += [("asset:sikka", [CRUDE]), ("asset:jamnagar", [CRUDE, *products])]
    return rows


def seed_pilot_world(db: Session) -> None:
    """Additive and idempotent: places, assets, vessels, portions, extents and estimate."""
    seed_world_core(db)
    db.merge(
        Source(
            id=SOURCE_ID,
            name="Aftertime pilot: Saudi Arabia to India crude, 2019 to forecast",
            url="https://github.com/AftertimeINFO/Aftertime/blob/DEV/docs/en/design/"
            "MATTER_FLOW_AND_LOCATIONS.md",
            license="CC0-1.0",
            adapter="bootstrap",
            configuration={
                **PARAMETERS,
                "history": {
                    str(year): {"bbl_per_day": bbl, "provenance": prov, "reference": ref}
                    for year, (bbl, prov, ref) in HISTORY.items()
                },
                "ghawar_history": {
                    str(year): {"bbl_per_day": bbl, "provenance": prov, "reference": ref}
                    for year, (bbl, prov, ref) in GHAWAR_HISTORY.items()
                },
            },
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
    for symbol, name, molar_mass in ELEMENTS:
        _upsert(
            db,
            element_id(symbol),
            "element",
            name,
            level="atomic",
            symbol=symbol,
            attributes={"molar_mass_g_per_mol": molar_mass},
        )
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
    for symbol, _, _ in ELEMENTS:
        _link(db, element_id(symbol), "instance_of", "type:chemical-element")
        # Crosswalk to atom entities of the earlier bootstrap seed (ids "n", "h"), if present.
        legacy = db.get(Entity, symbol.lower())
        if legacy is not None and legacy.kind == "atom":
            _link(db, element_id(symbol), "same_as", legacy.id)
    for material_id, fractions in compositions().items():
        for symbol, fraction in fractions.items():
            _link(
                db,
                material_id,
                "composed_of",
                element_id(symbol),
                coefficient=round(fraction, 8),
                unit="kg/kg",
            )
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


def flow_bbl_per_day(at: datetime, growth_pct: float = 0.0) -> tuple[float, str]:
    """Flow rate and provenance at a moment: history, then the last year grown yearly."""
    if at.year in HISTORY:
        bbl, provenance, _ = HISTORY[at.year]
        return bbl, provenance
    if at.year < min(HISTORY):
        return HISTORY[min(HISTORY)][0], "assumed"
    last = max(HISTORY)
    return HISTORY[last][0] * (1 + growth_pct / 100) ** (at.year - last), "forecast"


def ghawar_bbl_per_day(at: datetime, growth_pct: float = 0.0) -> tuple[float, str]:
    """Whole Ghawar output at a moment: derived history, then the last year grown yearly."""
    if at.year in GHAWAR_HISTORY:
        bbl, provenance, _ = GHAWAR_HISTORY[at.year]
        return bbl, provenance
    if at.year < min(GHAWAR_HISTORY):
        return GHAWAR_HISTORY[min(GHAWAR_HISTORY)][0], "assumed"
    last = max(GHAWAR_HISTORY)
    return GHAWAR_HISTORY[last][0] * (1 + growth_pct / 100) ** (at.year - last), "forecast"


def flows_by_year(horizon: datetime, growth_pct: float = 0.0) -> list[dict]:
    """Yearly flow of every year that starts before the horizon."""
    rows = []
    for year in range(min(HISTORY), horizon.year + 1):
        if datetime(year, 1, 1, tzinfo=UTC) >= horizon:
            break
        mid = datetime(year, 7, 1, tzinfo=UTC)
        bbl, provenance = flow_bbl_per_day(mid, growth_pct)
        field_bbl, field_provenance = ghawar_bbl_per_day(mid, growth_pct)
        rows.append(
            {
                "year": year,
                "bbl_per_day": bbl,
                "provenance": provenance,
                "reference": HISTORY[year][2] if year in HISTORY else None,
                "ghawar_bbl_per_day": field_bbl,
                "ghawar_provenance": field_provenance,
                "ghawar_reference": GHAWAR_HISTORY[year][2] if year in GHAWAR_HISTORY else None,
            }
        )
    return rows


def clear_pilot_events(db: Session) -> None:
    """Delete every pilot event with its postings and the vessel location history."""
    run_ids = (RUN_ID, *LEGACY_RUN_IDS)
    run_events = select(WorldEvent.id).where(WorldEvent.run_id.in_(run_ids))
    db.execute(delete(Relation).where(Relation.cause_event_id.in_(run_events)))
    db.execute(
        delete(Relation).where(
            Relation.source_id == SOURCE_ID,
            Relation.predicate == "located_in",
            Relation.valid_from.is_not(None),
        )
    )
    db.execute(delete(Posting).where(Posting.event_id.in_(run_events)))
    db.execute(delete(WorldEvent).where(WorldEvent.run_id.in_(run_ids)))


def generate_pilot_events(
    db: Session,
    *,
    force: bool = False,
    until: datetime | None = None,
    growth_pct: float = 0.0,
) -> int:
    """Turn the yearly flows into ledger events up to ``until`` (default: end of history).

    Events are built in memory and written with bulk inserts, so a decade of cargoes
    takes seconds. A cargo is written only when its chain up to refining ends by
    ``until``; the return leg of the last voyages may end later and is then left out.
    Returns the number of events written.
    """
    existing = db.scalar(
        select(WorldEvent.id).where(WorldEvent.run_id.in_((RUN_ID, *LEGACY_RUN_IDS))).limit(1)
    )
    if existing and not force:
        return 0
    if existing:
        clear_pilot_events(db)
    end = until or HISTORY_TO
    if end.tzinfo is None:
        raise ValueError("until must be timezone-aware")

    p = PARAMETERS
    conserved = conserved_units(db)
    cargo_kg = p["cargo_bbl"] * p["kg_per_bbl"]
    transit = timedelta(hours=sea_lane_nm() / p["speed_knots"])
    load = timedelta(hours=p["load_hours"])
    discharge = timedelta(hours=p["discharge_hours"])
    start = HISTORY_FROM
    lane = "place:sea-lane-ras-tanura-sikka"
    yields = p["refinery_yields"]

    ghawar = portion_id("place:ghawar", CRUDE)
    abqaiq = portion_id("asset:abqaiq", CRUDE)
    ras_tanura = portion_id("asset:ras-tanura", CRUDE)
    sikka = portion_id("asset:sikka", CRUDE)
    jamnagar = portion_id("asset:jamnagar", CRUDE)
    products = [(portion_id("asset:jamnagar", m), share) for m, share in yields.items()]
    fleet = [_Vessel(vessel_id, start) for vessel_id, _ in VESSELS]
    for vessel in fleet:
        vessel.moves.append((start - timedelta(days=1), "asset:ras-tanura", ""))

    events: list[dict] = []
    postings: list[dict] = []

    def record(event_type: str, at: datetime, provenance: str, items: list, **attributes) -> str:
        event_id = uuid.uuid4().hex
        check_balance([PostingInput(e, "mass", d, "kg") for e, d in items], conserved)
        events.append(
            {
                "id": event_id,
                "event_type_id": event_type,
                "occurred_at": at,
                "provenance": provenance,
                "source_id": SOURCE_ID,
                "run_id": RUN_ID,
                "attributes": attributes,
            }
        )
        postings.extend(
            {
                "id": uuid.uuid4().hex,
                "event_id": event_id,
                "entity_id": entity,
                "property": "mass",
                "delta": delta,
                "unit": "kg",
            }
            for entity, delta in items
        )
        return event_id

    ready = start + timedelta(days=2, hours=12)
    k = 0
    while True:
        # The year of production decides the figure (and provenance) a cargo follows.
        rate, provenance = flow_bbl_per_day(ready - timedelta(days=2), growth_pct)
        vessel = min(fleet, key=lambda v: v.free_at)
        load_at = max(ready, vessel.free_at)
        depart_at = load_at + load
        arrive_at = depart_at + transit
        discharged_at = arrive_at + discharge
        refined_at = discharged_at + timedelta(days=2)
        back_at = discharged_at + transit
        if refined_at > end:
            break
        k += 1
        voyage = f"{RUN_ID}:cargo-{k:04d}"
        cargo = portion_id(vessel.id, CRUDE)
        # Cargo movements follow the yearly figure; voyage legs are timing assumptions.
        leg = "forecast" if provenance == "forecast" else "assumed"
        record(
            "type:produce",
            ready - timedelta(days=2),
            provenance,
            [(ghawar, -cargo_kg), (abqaiq, cargo_kg)],
            voyage=voyage,
        )
        record(
            "type:transfer",
            ready - timedelta(days=1),
            provenance,
            [(abqaiq, -cargo_kg), (ras_tanura, cargo_kg)],
            voyage=voyage,
            mode="pipeline",
        )
        record(
            "type:load",
            load_at,
            provenance,
            [(ras_tanura, -cargo_kg), (cargo, cargo_kg)],
            voyage=voyage,
            vessel=vessel.id,
        )
        departed = record(
            "type:depart",
            depart_at,
            leg,
            [],
            voyage=voyage,
            vessel=vessel.id,
            route=lane,
            direction="laden",
            cargo_kg=cargo_kg,
            arrive_at=arrive_at.isoformat(),
        )
        vessel.moves.append((depart_at, lane, departed))
        arrived = record(
            "type:arrive", arrive_at, leg, [], voyage=voyage, vessel=vessel.id, place="asset:sikka"
        )
        vessel.moves.append((arrive_at, "asset:sikka", arrived))
        record(
            "type:discharge",
            discharged_at,
            provenance,
            [(cargo, -cargo_kg), (sikka, cargo_kg)],
            voyage=voyage,
            vessel=vessel.id,
        )
        record(
            "type:transfer",
            discharged_at + timedelta(hours=12),
            provenance,
            [(sikka, -cargo_kg), (jamnagar, cargo_kg)],
            voyage=voyage,
            mode="pipeline",
        )
        record(
            "type:transform",
            refined_at,
            provenance,
            [(jamnagar, -cargo_kg)] + [(pid, cargo_kg * share) for pid, share in products],
            voyage=voyage,
            process="refining",
        )
        ballast = record(
            "type:depart",
            discharged_at,
            leg,
            [],
            voyage=f"{voyage}:ballast",
            vessel=vessel.id,
            route=lane,
            direction="ballast",
            cargo_kg=0,
            arrive_at=back_at.isoformat(),
        )
        vessel.moves.append((discharged_at, lane, ballast))
        if back_at <= end:
            returned = record(
                "type:arrive",
                back_at,
                leg,
                [],
                voyage=f"{voyage}:ballast",
                vessel=vessel.id,
                place="asset:ras-tanura",
            )
            vessel.moves.append((back_at, "asset:ras-tanura", returned))
        vessel.free_at = back_at
        ready = ready + timedelta(days=p["cargo_bbl"] / rate)

    # The rest of Ghawar's output leaves the field once a month (at the month's last noon).
    offtake = portion_id(OFFTAKE, CRUDE)
    month = start
    while True:
        following = datetime(month.year + month.month // 12, month.month % 12 + 1, 1, tzinfo=UTC)
        at = following - timedelta(hours=12)
        if at > end:
            break
        field_rate, field_provenance = ghawar_bbl_per_day(month, growth_pct)
        pilot_rate, _ = flow_bbl_per_day(month, growth_pct)
        days = (following - month).days
        other_kg = max(field_rate - pilot_rate, 0.0) * days * p["kg_per_bbl"]
        if other_kg > 0:
            record(
                "type:produce",
                at,
                field_provenance,
                [(ghawar, -other_kg), (offtake, other_kg)],
                month=month.strftime("%Y-%m"),
                field_bbl_per_day=round(field_rate),
                pilot_bbl_per_day=round(pilot_rate),
            )
        month = following

    relations = []
    for vessel in fleet:
        moves = vessel.moves
        for (at, place_id, event_id), following in zip(moves, [*moves[1:], None], strict=True):
            relations.append(
                {
                    "id": uuid.uuid4().hex,
                    "subject_id": vessel.id,
                    "predicate": "located_in",
                    "object_id": place_id,
                    "confidence": 1,
                    "source_id": SOURCE_ID,
                    "valid_from": at,
                    "valid_to": following[0] if following else None,
                    "cause_event_id": event_id or None,
                }
            )
    _bulk_write(db, WorldEvent, events, json_columns=("attributes",))
    _bulk_write(db, Posting, postings)
    _bulk_write(db, Relation, relations)
    return len(events)


def _bulk_write(db: Session, model, rows: list[dict], json_columns: tuple[str, ...] = ()) -> None:
    """COPY rows into the table of ``model`` (PostgreSQL + psycopg 3), else bulk INSERT."""
    if not rows:
        return
    db.flush()
    connection = db.connection()
    raw = connection.connection.driver_connection
    if connection.dialect.driver != "psycopg" or not hasattr(raw, "cursor"):
        db.execute(insert(model), rows)
        return
    columns = list(rows[0])
    names = ", ".join(columns)
    with raw.cursor() as cursor:
        with cursor.copy(f"COPY {model.__tablename__} ({names}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(
                    [json.dumps(row[c]) if c in json_columns else row[c] for c in columns]
                )
