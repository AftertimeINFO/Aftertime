"""Scopes of the world model: from the whole Earth down to one company or asset.

Two axes are offered, both derived from relations of the world core:

* geography — places and assets linked by ``part_of`` / ``located_in``, from the root
  places (normally Earth) down to single assets;
* control — states, the companies whose assets fall under their jurisdiction, and
  the assets those companies operate or own.

A scope is the set of entities transitively inside its roots at a moment. Moving
carriers (vessels) enter and leave scopes through time-valid ``located_in``
relations; ``ScopeIndex`` answers membership for any moment from one load of the
containment relations.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

CONTAINMENT = ("part_of", "located_in")
CONTROL = ("operated_by", "owned_by", "jurisdiction_of")
CONTROL_ROOT = "control:all"
MAX_DEPTH = 64


def _rows(db: Session, sql: str, **params) -> list:
    return list(db.execute(text(sql), params))


def _instance_types(db: Session) -> dict[str, set[str]]:
    types: dict[str, set[str]] = defaultdict(set)
    for subject, obj in _rows(
        db, "SELECT subject_id, object_id FROM relations WHERE predicate = 'instance_of'"
    ):
        types[subject].add(obj)
    return types


def scope_tree(db: Session) -> dict:
    """Both scope axes as nested trees of ``{id, name, kind, children}``."""
    entities = {
        row.id: row
        for row in _rows(
            db, "SELECT id, name, kind FROM entities WHERE kind IN ('place', 'asset', 'actor')"
        )
    }
    types = _instance_types(db)

    # Geography: static containment between places and assets (moving vessels excluded).
    children: dict[str, list[str]] = defaultdict(list)
    has_parent: set[str] = set()
    for subject, obj in _rows(
        db,
        """
        SELECT subject_id, object_id FROM relations
        WHERE predicate IN ('part_of', 'located_in')
          AND valid_from IS NULL AND valid_to IS NULL
        ORDER BY subject_id
        """,
    ):
        if subject in entities and obj in entities and entities[subject].kind != "actor":
            if "type:vessel" in types.get(subject, set()):
                continue
            children[obj].append(subject)
            has_parent.add(subject)

    def geo_node(entity_id: str, path: frozenset) -> dict:
        row = entities[entity_id]
        kids = [k for k in children.get(entity_id, []) if k not in path]
        return {
            "id": entity_id,
            "name": row.name,
            "kind": row.kind,
            "children": [
                geo_node(k, path | {entity_id})
                for k in sorted(kids, key=lambda k: (entities[k].kind != "place", entities[k].name))
            ],
        }

    geo_roots = sorted(
        (i for i, row in entities.items() if row.kind == "place" and i not in has_parent),
        key=lambda i: entities[i].name,
    )
    # Earth (the place with the largest subtree) first.
    geo = [geo_node(root, frozenset()) for root in geo_roots]
    geo.sort(key=lambda node: -_size(node))

    # Control: state -> company -> asset.
    controlled: dict[str, set[str]] = defaultdict(set)  # actor -> assets
    jurisdiction: dict[str, set[str]] = defaultdict(set)  # asset -> states
    for subject, predicate, obj in _rows(
        db,
        "SELECT subject_id, predicate, object_id FROM relations WHERE predicate = ANY(:p)",
        p=list(CONTROL),
    ):
        if subject not in entities or obj not in entities:
            continue
        controlled[obj].add(subject)
        if predicate == "jurisdiction_of":
            jurisdiction[subject].add(obj)

    actors = {i for i, row in entities.items() if row.kind == "actor"}
    states = {a for a in actors if "type:state" in types.get(a, set())}
    companies = actors - states

    def asset_nodes(asset_ids: set[str]) -> list[dict]:
        return [
            {"id": a, "name": entities[a].name, "kind": entities[a].kind, "children": []}
            for a in sorted(asset_ids, key=lambda a: entities[a].name)
        ]

    def company_node(company: str) -> dict:
        own = {a for a in controlled.get(company, set()) if entities[a].kind != "actor"}
        return {
            "id": company,
            "name": entities[company].name,
            "kind": "actor",
            "children": asset_nodes(own),
        }

    placed: set[str] = set()
    state_nodes = []
    for state in sorted(states, key=lambda s: entities[s].name):
        under = sorted(
            (
                c
                for c in companies
                if any(state in jurisdiction.get(a, set()) for a in controlled.get(c, set()))
            ),
            key=lambda c: entities[c].name,
        )
        placed.update(under)
        state_nodes.append(
            {
                "id": state,
                "name": entities[state].name,
                "kind": "actor",
                "children": [company_node(c) for c in under],
            }
        )
    loose = [company_node(c) for c in sorted(companies - placed, key=lambda c: entities[c].name)]
    control = (
        [
            {
                "id": CONTROL_ROOT,
                "name": "Усі актори",
                "kind": "group",
                "children": state_nodes + loose,
            }
        ]
        if actors
        else []
    )
    return {
        "axes": [
            {"id": "geo", "name": "Географія", "roots": geo},
            {"id": "control", "name": "Власність", "roots": control},
        ]
    }


def _size(node: dict) -> int:
    return 1 + sum(_size(child) for child in node["children"])


def scope_roots(db: Session, scope_id: str) -> set[str]:
    """Entities whose contents form the scope: the place itself, or an actor's assets."""
    if scope_id == CONTROL_ROOT:
        rows = _rows(
            db,
            """
            SELECT r.subject_id FROM relations r JOIN entities e ON e.id = r.object_id
            WHERE r.predicate = ANY(:p) AND e.kind = 'actor'
            """,
            p=list(CONTROL),
        )
        return {row[0] for row in rows}
    kind = db.execute(text("SELECT kind FROM entities WHERE id = :id"), {"id": scope_id}).scalar()
    if kind is None:
        raise LookupError(scope_id)
    if kind != "actor":
        return {scope_id}
    rows = _rows(
        db,
        "SELECT subject_id FROM relations WHERE object_id = :id AND predicate = ANY(:p)",
        id=scope_id,
        p=list(CONTROL),
    )
    return {row[0] for row in rows}


class ScopeIndex:
    """Membership of entities in a scope at any moment, from one load of containment."""

    def __init__(self, db: Session, roots: set[str]):
        self.roots = roots
        self.parents: dict[str, list[tuple[str, datetime | None, datetime | None]]] = (
            defaultdict(list)
        )
        self.children: dict[str, list[str]] = defaultdict(list)
        self.boundaries: set[datetime] = set()
        self.moving: set[str] = set()
        for subject, obj, valid_from, valid_to in _rows(
            db,
            """
            SELECT subject_id, object_id, valid_from, valid_to FROM relations
            WHERE predicate IN ('part_of', 'located_in')
            """,
        ):
            self.parents[subject].append((obj, valid_from, valid_to))
            self.children[obj].append(subject)
            if valid_from is not None or valid_to is not None:
                self.moving.add(subject)
                self.boundaries.update(t for t in (valid_from, valid_to) if t is not None)
        self._cache: dict[tuple[str, datetime], bool] = {}

    def contains(self, entity_id: str, at: datetime, _depth: int = 0) -> bool:
        if entity_id in self.roots:
            return True
        if _depth > MAX_DEPTH:
            return False
        key = (entity_id, at)
        if key in self._cache:
            return self._cache[key]
        result = any(
            (valid_from is None or valid_from <= at)
            and (valid_to is None or valid_to > at)
            and self.contains(parent, at, _depth + 1)
            for parent, valid_from, valid_to in self.parents.get(entity_id, [])
        )
        self._cache[key] = result
        return result

    def descendants(self, entity_id: str) -> set[str]:
        """Everything ever contained in the entity, regardless of time."""
        seen: set[str] = set()
        stack = [entity_id]
        while stack:
            for child in self.children.get(stack.pop(), []):
                if child not in seen:
                    seen.add(child)
                    stack.append(child)
        return seen
