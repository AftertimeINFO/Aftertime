"""Multi-level material balance of a scope over a period, read from the event ledger.

Organised like a financial trial balance (оборотно-сальдова відомість), one row per
material (or chemical element) and the columns

    opening + inflow - outflow + transform + carrier = closing   (+ residual)

* opening / closing — mass of the portions inside the scope at the period bounds
  (estimate plus postings, see ``world_query.portion_amounts``);
* inflow / outflow — postings of events whose counterpart lies outside the scope;
* transform — net change per material of events wholly inside the scope that turn
  one material into others (refining);
* carrier — cargo that crossed the scope boundary together with its carrier, a
  vessel whose ``located_in`` changed, without any posting;
* internal — turnover of moves inside the scope (net zero, shown for reference);
* residual — what the ledger does not explain (for example a new stock estimate in
  the period). The design (MATTER_FLOW_AND_LOCATIONS.md §1) requires it to be shown.

Levels of matter: ``substance`` (materials grouped by the ``subclass_of`` lattice),
``element`` (materials decomposed with ``composed_of`` kg/kg fractions) and
``molecular`` (available only when materials are composed of molecules).
"""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session
from sqlalchemy.types import String

from app.services.world_query import element_fractions, portion_amounts
from app.services.world_scope import ScopeIndex, scope_roots

FLOW_COLUMNS = ("opening", "inflow", "outflow", "transform", "carrier", "closing", "residual")
COLUMNS = (*FLOW_COLUMNS, "internal")
LEVELS = ("substance", "molecular", "element")
MATERIAL_ROOT = "type:material"
UNKNOWN_MATERIAL = "material:unknown"
UNRESOLVED = "element:unresolved"
EPSILON = timedelta(microseconds=1)


class BalanceError(ValueError):
    """The balance cannot be computed for the given request."""


def _zero() -> dict[str, float]:
    return dict.fromkeys(COLUMNS, 0.0)


def _portion_materials(db: Session) -> dict[str, str]:
    rows = db.execute(
        text(
            """
            SELECT e.id, (SELECT r.object_id FROM relations r
                          WHERE r.subject_id = e.id AND r.predicate = 'instance_of'
                            AND r.object_id <> 'type:portion' LIMIT 1) AS material
            FROM entities e WHERE e.kind = 'portion'
            """
        )
    )
    return {row.id: row.material or UNKNOWN_MATERIAL for row in rows}


def _ledger(
    db: Session, start: datetime, end: datetime, materials: dict[str, str], index: ScopeIndex
) -> tuple[dict, dict, dict]:
    """Flows per material, breakdown per material and event type, provenance turnover."""
    portions = list(materials)
    base = {row["id"]: row["kg"] for row in portion_amounts(db, portions, start)}
    running = defaultdict(float, base)

    postings_by_event: dict[str, list] = defaultdict(list)
    headers: dict[str, tuple] = {}
    for row in db.execute(
        text(
            """
            SELECT p.event_id, p.entity_id, p.delta, ev.occurred_at, ev.provenance,
                   ev.event_type_id, t.name AS type_name
            FROM postings p
            JOIN events ev ON ev.id = p.event_id
            JOIN entities t ON t.id = ev.event_type_id
            WHERE p.property = 'mass' AND p.unit = 'kg'
              AND ev.occurred_at > :start AND ev.occurred_at <= :end
            ORDER BY ev.occurred_at, ev.id
            """
        ),
        {"start": start, "end": end},
    ):
        postings_by_event[row.event_id].append((row.entity_id, float(row.delta)))
        headers[row.event_id] = (row.occurred_at, row.provenance, row.type_name)

    # Boundaries where a moving carrier changes container, with the carriers concerned.
    moved_at: dict[datetime, set[str]] = defaultdict(set)
    for subject in index.moving:
        for _, valid_from, valid_to in index.parents[subject]:
            for moment in (valid_from, valid_to):
                if moment is not None and start < moment <= end:
                    moved_at[moment].add(subject)

    # Timeline: carrier crossings at a moment come before the postings of that moment,
    # so the cargo crosses with the amount it had just before.
    timeline = sorted(
        [(moment, 0, None) for moment in moved_at]
        + [(headers[event_id][0], 1, event_id) for event_id in headers],
        key=lambda item: (item[0], item[1], item[2] or ""),
    )

    flows: dict[str, dict[str, float]] = defaultdict(_zero)
    breakdown: dict[str, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )
    provenance: dict[str, float] = defaultdict(float)

    for moment, kind, event_id in timeline:
        if kind == 0:
            for carrier in moved_at[moment]:
                cargo = (index.descendants(carrier) | {carrier}) & materials.keys()
                for portion in cargo:
                    was = index.contains(portion, moment - EPSILON)
                    now = index.contains(portion, moment)
                    amount = running[portion]
                    if was == now or not amount:
                        continue
                    sign = 1.0 if now else -1.0
                    flows[materials[portion]]["carrier"] += sign * amount
                    breakdown[materials[portion]]["Переміщення з носієм"]["carrier"] += (
                        sign * amount
                    )
            continue

        _, prov, type_name = headers[event_id]
        postings = postings_by_event[event_id]
        inside = [
            (entity, delta)
            for entity, delta in postings
            if entity in materials and index.contains(entity, moment)
        ]
        outside = [(entity, delta) for entity, delta in postings if (entity, delta) not in inside]
        for entity, delta in postings:
            if entity in materials:
                running[entity] += delta
        if not inside:
            continue
        for _, delta in inside:
            provenance[prov] += abs(delta)
        if outside:
            for entity, delta in inside:
                material = materials[entity]
                column = "inflow" if delta > 0 else "outflow"
                flows[material][column] += abs(delta)
                breakdown[material][type_name][column] += abs(delta)
            continue
        net: dict[str, float] = defaultdict(float)
        for entity, delta in inside:
            net[materials[entity]] += delta
        if len(net) > 1:
            for material, delta in net.items():
                flows[material]["transform"] += delta
                breakdown[material][type_name]["transform"] += delta
        else:
            material = next(iter(net))
            turnover = sum(delta for _, delta in inside if delta > 0)
            flows[material]["internal"] += turnover
            breakdown[material][type_name]["internal"] += turnover
    return flows, breakdown, provenance


def _stock(
    db: Session, materials: dict[str, str], index: ScopeIndex, at: datetime
) -> dict[str, float]:
    stock: dict[str, float] = defaultdict(float)
    for row in portion_amounts(db, list(materials), at):
        if index.contains(row["id"], at):
            stock[materials[row["id"]]] += row["kg"]
    return stock


def _names(db: Session, ids: set[str]) -> dict[str, dict]:
    if not ids:
        return {}
    rows = db.execute(
        text("SELECT id, name, symbol, kind, attributes FROM entities WHERE id = ANY(:ids)")
        .bindparams(bindparam("ids", type_=ARRAY(String))),
        {"ids": list(ids)},
    )
    return {
        row.id: {
            "name": row.name,
            "symbol": row.symbol,
            "kind": row.kind,
            "attributes": row.attributes or {},
        }
        for row in rows
    }


def _with_residual(values: dict[str, float]) -> dict[str, float]:
    values["residual"] = values["closing"] - (
        values["opening"]
        + values["inflow"]
        - values["outflow"]
        + values["transform"]
        + values["carrier"]
    )
    return values


def _add(target: dict[str, float], source: dict[str, float], factor: float = 1.0) -> None:
    for column in COLUMNS:
        target[column] += source.get(column, 0.0) * factor


def _substance_rows(db: Session, per_material: dict[str, dict], breakdown: dict) -> list[dict]:
    """Materials as a tree of the subclass_of lattice below Material, with subtotals."""
    parent: dict[str, str] = {}
    for subject, obj in db.execute(
        text("SELECT subject_id, object_id FROM relations WHERE predicate = 'subclass_of'")
    ):
        parent.setdefault(subject, obj)

    def chain(material: str) -> list[str]:
        path = [material]
        seen = {material}
        while path[-1] in parent and parent[path[-1]] != MATERIAL_ROOT:
            nxt = parent[path[-1]]
            if nxt in seen or nxt not in parent:
                return [material]  # not under Material: show it at the top level
            seen.add(nxt)
            path.append(nxt)
        return list(reversed(path))

    children: dict[str | None, list[str]] = defaultdict(list)
    own: dict[str, dict[str, float]] = {}
    for material, values in per_material.items():
        path = chain(material) if material != UNKNOWN_MATERIAL else [material]
        for depth, node in enumerate(path):
            up = path[depth - 1] if depth else None
            if node not in children[up]:
                children[up].append(node)
        own[material] = values

    names = _names(db, {n for nodes in children.values() for n in nodes} | set(own))
    names[UNKNOWN_MATERIAL] = {"name": "Матеріал не визначено", "symbol": None}
    rows: list[dict] = []

    def visit(node: str, depth: int, up: str | None) -> dict[str, float]:
        kids = children.get(node, [])
        label = names.get(node, {}).get("name", node)
        row = {
            "id": node,
            "name": label,
            "symbol": names.get(node, {}).get("symbol"),
            "depth": depth,
            "parent": up,
            "group": bool(kids),
            "values": {},
        }
        rows.append(row)
        total = _zero()
        if kids:
            if node in own:
                rows.append(
                    {
                        "id": f"{node}#own",
                        "name": f"{label} (без уточнення)",
                        "symbol": None,
                        "depth": depth + 1,
                        "parent": node,
                        "group": False,
                        "values": _with_residual(dict(own[node])),
                        "breakdown": _breakdown_rows(breakdown.get(node, {})),
                    }
                )
                _add(total, own[node])
            for kid in sorted(kids, key=lambda k: names.get(k, {}).get("name", k)):
                _add(total, visit(kid, depth + 1, node))
        else:
            _add(total, own.get(node, {}))
            row["breakdown"] = _breakdown_rows(breakdown.get(node, {}))
        row["values"] = _with_residual(total)
        return total

    for top in sorted(children.get(None, []), key=lambda k: names.get(k, {}).get("name", k)):
        visit(top, 0, None)
    return rows


def _breakdown_rows(by_type: dict) -> list[dict]:
    rows = []
    for name, values in sorted(by_type.items()):
        kept = {column: amount for column, amount in values.items() if abs(amount) > 1e-6}
        if kept:
            rows.append({"event_type": name, **kept})
    return rows


def _element_rows(db: Session, per_material: dict[str, dict]) -> tuple[list[dict], bool]:
    """Materials decomposed into chemical elements; mass without composition stays apart."""
    per_element: dict[str, dict[str, float]] = defaultdict(_zero)
    resolved_any = False
    for material, values in per_material.items():
        fractions = element_fractions(db, material) if material != UNKNOWN_MATERIAL else {}
        if not fractions:
            _add(per_element[UNRESOLVED], values)
            continue
        resolved_any = True
        covered = sum(fractions.values())
        for element, fraction in fractions.items():
            _add(per_element[element], values, fraction)
        if covered < 1 - 1e-9:
            _add(per_element[UNRESOLVED], values, 1 - covered)

    names = _names(db, set(per_element) - {UNRESOLVED})
    rows = []
    for element, values in per_element.items():
        meta = names.get(element, {})
        molar = (meta.get("attributes") or {}).get("molar_mass_g_per_mol")
        rows.append(
            {
                "id": element,
                "name": meta.get("name", "Нерозкладена маса")
                if element != UNRESOLVED
                else "Нерозкладена маса (склад невідомий)",
                "symbol": meta.get("symbol"),
                "molar_mass_g_per_mol": molar,
                "depth": 0,
                "parent": None,
                "group": False,
                "values": _with_residual(values),
            }
        )
    rows.sort(key=lambda row: (row["id"] == UNRESOLVED, -abs(row["values"]["closing"])))
    return rows, resolved_any


def available_levels(db: Session) -> dict[str, bool]:
    composed = dict(
        db.execute(
            text(
                """
                SELECT o.kind, count(*) FROM relations r JOIN entities o ON o.id = r.object_id
                WHERE r.predicate = 'composed_of' GROUP BY o.kind
                """
            )
        ).all()
    )
    return {
        "substance": True,
        "molecular": bool(composed.get("molecule")),
        "element": bool(composed.get("element")),
    }


def balance(db: Session, scope_id: str, start: datetime, end: datetime, level: str) -> dict:
    if level not in LEVELS:
        raise BalanceError(f"Невідомий рівень матерії {level!r}")
    if end <= start:
        raise BalanceError("Кінець періоду має бути пізніше за початок")
    levels = available_levels(db)
    if not levels[level]:
        raise BalanceError("Для цього рівня матерії в шарі немає даних про склад")
    try:
        roots = scope_roots(db, scope_id)
    except LookupError as exc:
        raise BalanceError(f"Невідомий scope {scope_id!r}") from exc

    index = ScopeIndex(db, roots)
    materials = _portion_materials(db)
    opening = _stock(db, materials, index, start)
    closing = _stock(db, materials, index, end)
    flows, breakdown, provenance = _ledger(db, start, end, materials, index)

    per_material: dict[str, dict[str, float]] = {}
    for material in set(opening) | set(closing) | set(flows):
        values = dict(flows.get(material, _zero()))
        values["opening"] = opening.get(material, 0.0)
        values["closing"] = closing.get(material, 0.0)
        if any(abs(values[column]) > 0 for column in COLUMNS):
            per_material[material] = _with_residual(values)

    if level == "element":
        rows, _ = _element_rows(db, per_material)
    else:
        rows = _substance_rows(db, per_material, breakdown)

    totals = _zero()
    for values in per_material.values():
        _add(totals, values)
    _with_residual(totals)
    gross = max(1.0, abs(totals["opening"]) + abs(totals["closing"]))
    turnover = sum(provenance.values())
    return {
        "scope": scope_id,
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "level": level,
        "levels": levels,
        "unit": "kg",
        "columns": list(COLUMNS),
        "rows": rows,
        "totals": totals,
        "residual_ok": abs(totals["residual"]) <= 1e-9 * gross,
        "provenance": {
            name: amount / turnover for name, amount in sorted(provenance.items())
        }
        if turnover
        else {},
        "empty": not per_material,
    }
