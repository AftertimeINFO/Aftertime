"""Read model of the world core: what an entity contains and which operations touch it.

Everything here is derived (emergent) from the universal tables:

* containment follows ``part_of`` and ``located_in`` relations that are valid at
  the requested time, so a region contains its facilities, a terminal contains a
  berthed vessel and a vessel contains its cargo portion;
* the amount of a portion is its latest mass estimate (observation) plus all
  ledger postings after that estimate, or just the sum of postings without one;
* element amounts come from ``composed_of`` relations with ``kg/kg`` coefficients.
"""

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session
from sqlalchemy.types import String

AVOGADRO = 6.02214076e23
CONTAINMENT = ("part_of", "located_in")
FAR_FUTURE = datetime(9999, 1, 1, tzinfo=UTC)


def contained_ids(db: Session, entity_id: str, at: datetime) -> list[str]:
    """The entity and everything inside it at ``at`` (transitively)."""
    rows = db.execute(
        text(
            """
            WITH RECURSIVE inside(id) AS (
                SELECT CAST(:entity_id AS varchar)
                UNION
                SELECT r.subject_id FROM relations r JOIN inside ON r.object_id = inside.id
                WHERE r.predicate IN ('part_of', 'located_in')
                  AND (r.valid_from IS NULL OR r.valid_from <= :at)
                  AND (r.valid_to IS NULL OR r.valid_to > :at)
            )
            SELECT id FROM inside
            """
        ),
        {"entity_id": entity_id, "at": at},
    )
    return [row[0] for row in rows]


def portion_amounts(db: Session, ids: list[str], at: datetime) -> list[dict]:
    """Mass of every portion among ``ids`` at ``at``: estimate plus later postings."""
    if not ids:
        return []
    query = text(
        """
        WITH base AS (
            SELECT DISTINCT ON (subject_id) subject_id, value, valid_time
            FROM observations
            WHERE subject_id = ANY(:ids) AND property = 'mass' AND unit = 'kg'
              AND valid_time <= :at
            ORDER BY subject_id, valid_time DESC
        ),
        moved AS (
            SELECT p.entity_id, sum(p.delta) AS delta
            FROM postings p
            JOIN events ev ON ev.id = p.event_id
            LEFT JOIN base b ON b.subject_id = p.entity_id
            WHERE p.entity_id = ANY(:ids) AND p.property = 'mass' AND ev.occurred_at <= :at
              AND (b.valid_time IS NULL OR ev.occurred_at > b.valid_time)
            GROUP BY p.entity_id
        )
        SELECT e.id, e.name, coalesce(b.value, 0) + coalesce(m.delta, 0) AS kg,
               b.value IS NOT NULL AS estimated,
               (SELECT r.object_id FROM relations r
                 WHERE r.subject_id = e.id AND r.predicate = 'instance_of'
                   AND r.object_id <> 'type:portion' LIMIT 1) AS material,
               (SELECT r.object_id FROM relations r
                 WHERE r.subject_id = e.id AND r.predicate = 'located_in'
                   AND r.valid_from IS NULL LIMIT 1) AS holder
        FROM entities e
        LEFT JOIN base b ON b.subject_id = e.id
        LEFT JOIN moved m ON m.entity_id = e.id
        WHERE e.id = ANY(:ids) AND e.kind = 'portion'
        ORDER BY e.id
        """
    ).bindparams(bindparam("ids", type_=ARRAY(String)))
    return [
        {
            "id": row.id,
            "name": row.name,
            "kg": float(row.kg),
            "estimated": row.estimated,
            "material": row.material,
            "holder": row.holder,
        }
        for row in db.execute(query, {"ids": ids, "at": at})
    ]


def element_fractions(db: Session, material_id: str, _seen: frozenset = frozenset()) -> dict:
    """Element id -> kg per kg of the material, following composed_of (kg/kg) recursively."""
    if material_id in _seen:
        return {}
    parts = db.execute(
        text(
            """
            SELECT r.object_id, r.coefficient, e.kind FROM relations r
            JOIN entities e ON e.id = r.object_id
            WHERE r.subject_id = :id AND r.predicate = 'composed_of' AND r.unit = 'kg/kg'
              AND r.coefficient IS NOT NULL
            """
        ),
        {"id": material_id},
    ).all()
    result: dict[str, float] = defaultdict(float)
    for part_id, coefficient, kind in parts:
        if kind == "element":
            result[part_id] += coefficient
            continue
        for element, fraction in element_fractions(db, part_id, _seen | {material_id}).items():
            result[element] += coefficient * fraction
    return dict(result)


def contents(db: Session, entity_id: str, at: datetime) -> dict:
    """Portions inside the entity, totals by material and by chemical element."""
    portions = portion_amounts(db, contained_ids(db, entity_id, at), at)
    by_material: dict[str, float] = defaultdict(float)
    for portion in portions:
        by_material[portion["material"]] += portion["kg"]

    elements: dict[str, float] = defaultdict(float)
    unresolved = 0.0
    for material, kg in by_material.items():
        fractions = element_fractions(db, material) if material else {}
        if not fractions:
            unresolved += kg
        for element, fraction in fractions.items():
            elements[element] += kg * fraction

    meta = {}
    if elements or by_material:
        rows = db.execute(
            text(
                "SELECT id, name, symbol, attributes FROM entities WHERE id = ANY(:ids)"
            ).bindparams(bindparam("ids", type_=ARRAY(String))),
            {"ids": [*elements, *(m for m in by_material if m)]},
        )
        meta = {row.id: row for row in rows}

    def element_row(element: str, kg: float) -> dict:
        row = meta.get(element)
        molar_mass = (row.attributes or {}).get("molar_mass_g_per_mol") if row else None
        mol = kg * 1000 / molar_mass if molar_mass else None
        return {
            "id": element,
            "name": row.name if row else element,
            "symbol": row.symbol if row else None,
            "kg": kg,
            "mol": mol,
            "atoms": mol * AVOGADRO if mol is not None else None,
        }

    return {
        "at": at.isoformat(),
        "total_kg": sum(by_material.values()),
        "portions": portions,
        "materials": [
            {
                "id": material,
                "name": meta[material].name if material in meta else material,
                "kg": kg,
            }
            for material, kg in sorted(by_material.items(), key=lambda item: -abs(item[1]))
        ],
        "elements": [
            element_row(element, kg)
            for element, kg in sorted(elements.items(), key=lambda item: -abs(item[1]))
        ],
        "unresolved_kg": unresolved,
    }


def own_portion_ids(db: Session, entity_id: str) -> list[str]:
    """The entity itself plus portions it holds directly (not time-dependent)."""
    rows = db.execute(
        text(
            """
            SELECT r.subject_id FROM relations r JOIN entities e ON e.id = r.subject_id
            WHERE r.object_id = :id AND r.predicate = 'located_in' AND e.kind = 'portion'
            """
        ),
        {"id": entity_id},
    )
    return [entity_id, *(row[0] for row in rows)]


def operations(
    db: Session, entity_id: str, *, at: datetime | None = None, limit: int = 100, offset: int = 0
) -> dict:
    """Events that post on the entity or its own portions, or that moved the entity."""
    ids = own_portion_ids(db, entity_id)
    params = {"ids": ids, "entity_id": entity_id, "at": at or FAR_FUTURE}
    where = """
        WHERE ev.occurred_at <= :at AND (
            ev.id IN (SELECT event_id FROM postings WHERE entity_id = ANY(:ids))
            OR ev.id IN (SELECT cause_event_id FROM relations
                         WHERE subject_id = :entity_id AND cause_event_id IS NOT NULL)
        )
    """
    total = db.execute(
        text(f"SELECT count(*) FROM events ev {where}").bindparams(
            bindparam("ids", type_=ARRAY(String))
        ),
        params,
    ).scalar_one()
    rows = db.execute(
        text(
            f"""
            SELECT ev.id, ev.occurred_at, ev.event_type_id, ev.provenance, ev.run_id,
                   ev.attributes, t.name AS type_name
            FROM events ev JOIN entities t ON t.id = ev.event_type_id
            {where}
            ORDER BY ev.occurred_at DESC, ev.id
            LIMIT :limit OFFSET :offset
            """
        ).bindparams(bindparam("ids", type_=ARRAY(String))),
        {**params, "limit": limit, "offset": offset},
    ).all()
    postings: dict[str, list] = defaultdict(list)
    if rows:
        for event_id, posted_on, prop, delta, unit in db.execute(
            text(
                """
                SELECT event_id, entity_id, property, delta, unit FROM postings
                WHERE event_id = ANY(:events)
                """
            ).bindparams(bindparam("events", type_=ARRAY(String))),
            {"events": [row.id for row in rows]},
        ):
            postings[event_id].append(
                {
                    "entity_id": posted_on,
                    "property": prop,
                    "delta": delta,
                    "unit": unit,
                    "own": posted_on in ids,
                }
            )
    return {
        "total": total,
        "items": [
            {
                "id": row.id,
                "occurred_at": row.occurred_at.isoformat(),
                "type": row.event_type_id,
                "type_name": row.type_name,
                "provenance": row.provenance,
                "run_id": row.run_id,
                "attributes": row.attributes,
                "postings": postings.get(row.id, []),
            }
            for row in rows
        ],
    }


def runs_of(db: Session, entity_id: str) -> list[str]:
    """Runs whose events touch the entity, its own portions or its location history."""
    ids = own_portion_ids(db, entity_id)
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ev.run_id FROM events ev
            WHERE ev.run_id IS NOT NULL AND (
                ev.id IN (SELECT event_id FROM postings WHERE entity_id = ANY(:ids))
                OR ev.id IN (SELECT cause_event_id FROM relations
                             WHERE subject_id = :entity_id AND cause_event_id IS NOT NULL)
            )
            """
        ).bindparams(bindparam("ids", type_=ARRAY(String))),
        {"ids": ids, "entity_id": entity_id},
    )
    return sorted(row[0] for row in rows)
