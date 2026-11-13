"""Grid API: OSM power assets as vector tiles, search, asset cards, quality and overrides.

Everything served here is derived from OpenStreetMap (ODbL); every response that carries
asset data also carries the attribution.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db, request_layer
from app.grid import OSM_ATTRIBUTION, OSM_LICENCE
from app.layers import LAYER_POLICY

router = APIRouter(prefix="/api/v1/grid")

OVERRIDE_FIELDS = {
    "status": "Статус (active / destroyed / damaged / disused / occupied)",
    "capacity_mw": "Фактична потужність, МВт",
    "availability": "Доступність 0…1",
    "controlled_by": "Під контролем (країна/оператор)",
    "in_service_from": "Введено в експлуатацію",
    "out_of_service_from": "Виведено з експлуатації",
}


def require(capability: str):
    def check(request: Request) -> None:
        layer = request_layer(request)
        if capability not in LAYER_POLICY[layer]["capabilities"]:
            label = LAYER_POLICY[layer]["label"]
            raise HTTPException(403, f"У шарі {label} ця дія недоступна")

    return check


def _has_table(db: Session) -> bool:
    return bool(db.scalar(text("SELECT to_regclass('odbl.grid_assets') IS NOT NULL")))


# --- vector tiles -----------------------------------------------------------------------

# Minimum zoom per voltage band: the network reads top-down as you zoom in.
LINE_FILTER = """
    a.kind IN ('line', 'cable', 'minor_line') AND (
        (:z >= 12) OR
        (a.kind <> 'minor_line' AND (
            (a.max_voltage_kv >= 500) OR
            (:z >= 4 AND a.max_voltage_kv >= 300) OR
            (:z >= 6 AND a.max_voltage_kv >= 200) OR
            (:z >= 7 AND a.max_voltage_kv >= 100) OR
            (:z >= 9 AND a.max_voltage_kv >= 30) OR
            (:z >= 10)
        ))
    )
"""
SUBSTATION_FILTER = """
    a.kind IN ('substation', 'converter') AND (
        (:z >= 13) OR
        (a.max_voltage_kv >= 300 AND :z >= 4) OR
        (a.max_voltage_kv >= 200 AND :z >= 6) OR
        (a.max_voltage_kv >= 100 AND :z >= 7) OR
        (:z >= 10 AND coalesce(a.subkind, '') NOT IN ('minor_distribution', 'distribution'))
    )
"""
PLANT_FILTER = """
    a.kind = 'plant' AND (
        (:z >= 9) OR
        (a.capacity_mw >= 1000) OR
        (:z >= 5 AND a.capacity_mw >= 200) OR
        (:z >= 7 AND a.capacity_mw >= 20)
    )
"""

TILE_SQL = f"""
WITH env AS (SELECT ST_TileEnvelope(:z, :x, :y) AS box,
                    ST_Expand(ST_TileEnvelope(:z, :x, :y), :buffer) AS wide),
lines AS (
    SELECT a.id, a.kind, a.subkind AS sub, a.status, a.name, a.max_voltage_kv AS v,
           a.circuits AS c, a.frequency_hz AS f,
           ST_AsMVTGeom(
               CASE WHEN :z < 10 THEN ST_Simplify(a.geom_3857, :tol) ELSE a.geom_3857 END,
               env.box, 4096, 64, true) AS geom
    FROM odbl.grid_assets a, env
    WHERE a.geom_3857 && env.wide AND {LINE_FILTER}
),
subs AS (
    SELECT a.id, a.kind, a.subkind AS sub, a.status, a.name, a.max_voltage_kv AS v,
           ST_AsMVTGeom(ST_PointOnSurface(a.geom_3857), env.box, 4096, 64, true) AS geom
    FROM odbl.grid_assets a, env
    WHERE a.geom_3857 && env.wide AND {SUBSTATION_FILTER}
),
sub_areas AS (
    SELECT a.id, a.kind, a.status, a.max_voltage_kv AS v,
           ST_AsMVTGeom(a.geom_3857, env.box, 4096, 64, true) AS geom
    FROM odbl.grid_assets a, env
    WHERE :z >= 13 AND a.kind IN ('substation', 'converter')
      AND ST_Dimension(a.geom) = 2 AND a.geom_3857 && env.wide
),
plants AS (
    SELECT a.id, a.status, a.name, a.fuel, a.capacity_mw AS cap,
           (a.capacity_source IS DISTINCT FROM 'osm') AS est,
           ST_AsMVTGeom(ST_PointOnSurface(a.geom_3857), env.box, 4096, 64, true) AS geom
    FROM odbl.grid_assets a, env
    WHERE a.geom_3857 && env.wide AND {PLANT_FILTER}
),
plant_areas AS (
    SELECT a.id, a.status, a.fuel,
           ST_AsMVTGeom(a.geom_3857, env.box, 4096, 64, true) AS geom
    FROM odbl.grid_assets a, env
    WHERE :z >= 10 AND a.kind = 'plant' AND ST_Dimension(a.geom) = 2
      AND a.geom_3857 && env.wide
),
gens AS (
    SELECT a.id, a.status, a.fuel, a.capacity_mw AS cap,
           ST_AsMVTGeom(ST_PointOnSurface(a.geom_3857), env.box, 4096, 64, true) AS geom
    FROM odbl.grid_assets a, env
    WHERE :z >= 12 AND a.kind = 'generator' AND a.geom_3857 && env.wide
)
SELECT
    coalesce((SELECT ST_AsMVT(lines, 'power_line', 4096, 'geom', 'id') FROM lines), '')
 || coalesce((SELECT ST_AsMVT(sub_areas, 'power_substation_area', 4096, 'geom', 'id')
              FROM sub_areas), '')
 || coalesce((SELECT ST_AsMVT(subs, 'power_substation', 4096, 'geom', 'id') FROM subs), '')
 || coalesce((SELECT ST_AsMVT(plant_areas, 'power_plant_area', 4096, 'geom', 'id')
              FROM plant_areas), '')
 || coalesce((SELECT ST_AsMVT(plants, 'power_plant', 4096, 'geom', 'id') FROM plants), '')
 || coalesce((SELECT ST_AsMVT(gens, 'power_generator', 4096, 'geom', 'id') FROM gens), '')
"""

WORLD = 40_075_016.68557849
_tile_cache: OrderedDict[tuple, bytes] = OrderedDict()
_version_cache: dict[str, tuple[float, int]] = {}
TILE_CACHE_SIZE = 6000


def _data_version(db: Session, layer: str) -> int:
    cached = _version_cache.get(layer)
    if cached and time.monotonic() - cached[0] < 30:
        return cached[1]
    version = db.scalar(
        text(
            "SELECT coalesce(max(id), 0) + coalesce((SELECT max(id) FROM odbl.grid_overrides), 0)"
            " FROM odbl.grid_import_batches WHERE status = 'succeeded'"
        )
    )
    _version_cache[layer] = (time.monotonic(), int(version or 0))
    return int(version or 0)


@router.get("/tiles/{z}/{x}/{y}.pbf")
def tile(z: int, x: int, y: int, request: Request, db: Session = Depends(get_db)) -> Response:
    if not (0 <= z <= 22 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(404, "tile out of range")
    if not _has_table(db):
        return Response(b"", media_type="application/vnd.mapbox-vector-tile")
    layer = request_layer(request)
    key = (layer, _data_version(db, layer), z, x, y)
    data = _tile_cache.get(key)
    if data is None:
        pixel = WORLD / (256 * 2**z)
        data = bytes(
            db.scalar(
                text(TILE_SQL),
                {"z": z, "x": x, "y": y, "tol": pixel * 0.5, "buffer": pixel * 16},
            )
            or b""
        )
        _tile_cache[key] = data
        if len(_tile_cache) > TILE_CACHE_SIZE:
            _tile_cache.popitem(last=False)
    else:
        _tile_cache.move_to_end(key)
    return Response(
        data,
        media_type="application/vnd.mapbox-vector-tile",
        headers={"Cache-Control": "public, max-age=600"},
    )


# --- overview, search and cards ----------------------------------------------------------


_summary_cache: dict[tuple, dict] = {}


@router.get("/summary")
def summary(request: Request, db: Session = Depends(get_db)) -> dict:
    """What is imported: counts by country and kind, batches, extent and attribution.

    Aggregating millions of rows takes seconds, so the answer is cached per data version.
    """
    if not _has_table(db):
        return {"imported": False, "countries": [], "batches": [], "attribution": OSM_ATTRIBUTION}
    layer = request_layer(request)
    key = (layer, _data_version(db, layer))
    if key not in _summary_cache:
        _summary_cache.clear()
        _summary_cache[key] = _summary(db)
    return _summary_cache[key]


def _summary(db: Session) -> dict:
    rows = db.execute(
        text(
            "SELECT country, kind, count(*) AS n, sum(capacity_mw) AS mw, sum(length_km) AS km "
            "FROM odbl.grid_assets WHERE status = 'active' GROUP BY country, kind"
        )
    ).mappings()
    countries: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = countries.setdefault(row["country"] or "?", {"country": row["country"]})
        entry[row["kind"]] = row["n"]
        if row["kind"] == "plant":
            entry["plant_mw"] = round(row["mw"] or 0)
        if row["kind"] in {"line", "cable"}:
            entry[f"{row['kind']}_km"] = round(row["km"] or 0)
    batches = db.execute(
        text(
            "SELECT DISTINCT ON (region) id, region, source_url, source_timestamp, status, "
            "counts, finished_at FROM odbl.grid_import_batches "
            "ORDER BY region, id DESC"
        )
    ).mappings()
    extent = db.execute(
        text(
            "SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e) FROM "
            "(SELECT ST_Extent(geom) AS e FROM odbl.grid_assets "
            "WHERE kind = 'substation' AND max_voltage_kv >= 220) s"
        )
    ).first()
    batch_list = [dict(row) for row in batches]
    return {
        "imported": any(b["status"] == "succeeded" for b in batch_list),
        "countries": sorted(countries.values(), key=lambda c: c["country"] or ""),
        "batches": batch_list,
        "bounds": list(extent) if extent and extent[0] is not None else None,
        "licence": OSM_LICENCE,
        "attribution": OSM_ATTRIBUTION,
    }


SEARCH_SQL = """
SELECT id, kind, subkind, name, name_en, ref, max_voltage_kv, capacity_mw, fuel, country,
       status,
       ST_X(ST_PointOnSurface(geom)) AS lon, ST_Y(ST_PointOnSurface(geom)) AS lat,
       ARRAY[ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom)] AS bbox
FROM odbl.grid_assets
WHERE lower(coalesce(name, '') || ' ' || coalesce(name_en, '') || ' ' || coalesce(ref, ''))
      LIKE :pattern
  AND kind IN ('substation', 'plant', 'line', 'cable', 'converter')
  AND (:kind = '' OR kind = :kind)
ORDER BY
  CASE kind WHEN 'plant' THEN 0 WHEN 'substation' THEN 1 WHEN 'converter' THEN 1 ELSE 2 END,
  coalesce(capacity_mw, 0) DESC, coalesce(max_voltage_kv, 0) DESC, name
LIMIT :limit
"""


@router.get("/search")
def search(
    q: str = Query(..., min_length=2, max_length=120),
    kind: str = "",
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    if not _has_table(db):
        return {"items": []}
    pattern = "%" + q.strip().lower().replace("%", "").replace("_", "\\_") + "%"
    rows = db.execute(
        text(SEARCH_SQL), {"pattern": pattern, "kind": kind, "limit": limit}
    ).mappings()
    return {"items": [dict(row) for row in rows]}


ASSET_SQL = """
SELECT id, osm_type, osm_id, kind, subkind, status, name, name_en, operator, ref,
       voltages_kv, max_voltage_kv, frequency_hz, circuits, cables, capacity_mw,
       capacity_source, fuel, start_date, country, length_km, tags, quality, batch_id,
       updated_at, GeometryType(geom) AS geometry_type,
       ST_X(ST_PointOnSurface(geom)) AS lon, ST_Y(ST_PointOnSurface(geom)) AS lat,
       ARRAY[ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom)] AS bbox
FROM odbl.grid_assets WHERE id = :id
"""

# Lines whose ends lie at a substation, and substations at the ends of a line.
LINES_AT_SUBSTATION = """
SELECT l.id, l.kind, l.name, l.max_voltage_kv, l.circuits, l.status, l.length_km
FROM odbl.grid_assets s
JOIN odbl.grid_assets l
  ON l.kind IN ('line', 'cable') AND l.geom_3857 && ST_Expand(s.geom_3857, 600)
 AND (ST_DWithin(ST_StartPoint(l.geom)::geography, s.geom::geography, :radius)
   OR ST_DWithin(ST_EndPoint(l.geom)::geography, s.geom::geography, :radius))
WHERE s.id = :id
ORDER BY l.max_voltage_kv DESC NULLS LAST, l.name
LIMIT 200
"""
SUBSTATIONS_AT_LINE = """
SELECT s.id, s.kind, s.name, s.max_voltage_kv, s.status, s.subkind,
       CASE WHEN ST_DWithin(ST_StartPoint(l.geom)::geography, s.geom::geography, :radius)
            THEN 'start' ELSE 'end' END AS side
FROM odbl.grid_assets l
JOIN odbl.grid_assets s
  ON s.kind IN ('substation', 'converter', 'plant')
 AND (s.geom_3857 && ST_Expand(ST_StartPoint(l.geom_3857), 600)
   OR s.geom_3857 && ST_Expand(ST_EndPoint(l.geom_3857), 600))
 AND (ST_DWithin(ST_StartPoint(l.geom)::geography, s.geom::geography, :radius)
   OR ST_DWithin(ST_EndPoint(l.geom)::geography, s.geom::geography, :radius))
WHERE l.id = :id
LIMIT 20
"""
NEAREST_SUBSTATIONS = """
SELECT s.id, s.kind, s.name, s.max_voltage_kv, s.status,
       round((ST_Distance(s.geom::geography, p.geom::geography))::numeric) AS distance_m
FROM odbl.grid_assets p
JOIN odbl.grid_assets s ON s.kind = 'substation' AND s.max_voltage_kv >= 6
 AND s.geom_3857 && ST_Expand(p.geom_3857, 6000)
WHERE p.id = :id
ORDER BY ST_Distance(s.geom::geography, p.geom::geography)
LIMIT 5
"""

OSM_TYPES = {"n": "node", "w": "way", "r": "relation"}


@router.get("/assets/{asset_id}")
def asset(asset_id: int, db: Session = Depends(get_db)) -> dict:
    if not _has_table(db):
        raise HTTPException(404, "Мережу ще не імпортовано")
    row = db.execute(text(ASSET_SQL), {"id": asset_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "Об'єкт не знайдено")
    card = dict(row)
    params = {"id": asset_id, "radius": 200}
    if card["kind"] in {"substation", "converter"}:
        card["lines"] = [dict(r) for r in db.execute(text(LINES_AT_SUBSTATION), params).mappings()]
    elif card["kind"] in {"line", "cable", "minor_line"}:
        card["ends"] = [dict(r) for r in db.execute(text(SUBSTATIONS_AT_LINE), params).mappings()]
    elif card["kind"] in {"plant", "generator"}:
        card["nearby"] = [
            dict(r) for r in db.execute(text(NEAREST_SUBSTATIONS), params).mappings()
        ]
    card["overrides"] = [
        dict(r)
        for r in db.execute(
            text(
                "SELECT id, field, value, valid_from, valid_to, source_url, note, author, "
                "created_at FROM odbl.grid_overrides WHERE asset_id = :id "
                "ORDER BY valid_from NULLS FIRST, id"
            ),
            {"id": asset_id},
        ).mappings()
    ]
    card["source"] = {
        "url": f"https://www.openstreetmap.org/{OSM_TYPES[card['osm_type']]}/{card['osm_id']}",
        "licence": OSM_LICENCE,
        "attribution": OSM_ATTRIBUTION,
    }
    return card


# --- data quality ------------------------------------------------------------------------

QUALITY_LABELS = {
    "voltage_missing": "Не вказано напругу",
    "capacity_missing": "Не вказано потужність станції",
    "power_unit_missing": "Потужність без одиниць (прочитано як МВт)",
    "capacity_from_generators": "Потужність станції — сума генераторів",
    "inside_plant": "Генератор у межах станції",
}


@router.get("/quality")
def quality(db: Session = Depends(get_db)) -> dict:
    if not _has_table(db):
        return {"items": []}
    rows = db.execute(
        text(
            "SELECT flag, kind, count(*) AS n, (array_agg(id ORDER BY max_voltage_kv DESC "
            "NULLS LAST, capacity_mw DESC NULLS LAST))[1:20] AS sample "
            "FROM odbl.grid_assets, jsonb_array_elements_text(quality) AS flag "
            "WHERE status = 'active' AND kind <> 'minor_line' "
            "GROUP BY flag, kind ORDER BY count(*) DESC"
        )
    ).mappings()
    return {
        "items": [
            {**dict(row), "label": QUALITY_LABELS.get(row["flag"], row["flag"])} for row in rows
        ]
    }


# --- overrides ---------------------------------------------------------------------------


class OverrideIn(BaseModel):
    asset_id: int
    field: str
    value: Any
    valid_from: date | None = None
    valid_to: date | None = None
    source_url: str = Field(min_length=8, max_length=2000)
    note: str = Field("", max_length=4000)
    author: str = Field("", max_length=80)

    @field_validator("field")
    @classmethod
    def known_field(cls, value: str) -> str:
        if value not in OVERRIDE_FIELDS:
            raise ValueError(f"поле має бути одним із: {', '.join(OVERRIDE_FIELDS)}")
        return value

    @field_validator("source_url")
    @classmethod
    def web_source(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("джерело має бути посиланням http(s)")
        return value


@router.get("/overrides")
def list_overrides(asset_id: int | None = None, db: Session = Depends(get_db)) -> dict:
    if not _has_table(db):
        return {"fields": OVERRIDE_FIELDS, "items": []}
    rows = db.execute(
        text(
            "SELECT o.*, a.name AS asset_name, a.kind AS asset_kind FROM odbl.grid_overrides o "
            "JOIN odbl.grid_assets a ON a.id = o.asset_id "
            "WHERE (CAST(:asset AS bigint) IS NULL OR o.asset_id = :asset) "
            "ORDER BY o.created_at DESC LIMIT 500"
        ),
        {"asset": asset_id},
    ).mappings()
    return {"fields": OVERRIDE_FIELDS, "items": [dict(row) for row in rows]}


@router.post("/overrides", dependencies=[Depends(require("grid.run"))], status_code=201)
def create_override(payload: OverrideIn, db: Session = Depends(get_db)) -> dict:
    import json

    if not db.scalar(text("SELECT 1 FROM odbl.grid_assets WHERE id = :id"), {"id": payload.asset_id}):
        raise HTTPException(404, "Об'єкт не знайдено")
    row = db.execute(
        text(
            "INSERT INTO odbl.grid_overrides "
            "(asset_id, field, value, valid_from, valid_to, source_url, note, author) "
            "VALUES (:asset_id, :field, CAST(:value AS jsonb), :valid_from, :valid_to, "
            ":source_url, :note, :author) RETURNING *"
        ),
        {**payload.model_dump(), "value": json.dumps(payload.value)},
    ).mappings().one()
    db.commit()
    return dict(row)


@router.delete("/overrides/{override_id}", dependencies=[Depends(require("grid.run"))])
def delete_override(override_id: int, db: Session = Depends(get_db)) -> dict:
    deleted = db.execute(
        text("DELETE FROM odbl.grid_overrides WHERE id = :id"), {"id": override_id}
    ).rowcount
    db.commit()
    if not deleted:
        raise HTTPException(404, "Правку не знайдено")
    return {"deleted": override_id}


# --- snapshots, scenarios and runs -------------------------------------------------------

import json as _json  # noqa: E402
import re  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime as _datetime  # noqa: E402

from app.services.run_queue import SimulationQueueUnavailable, enqueue_grid  # noqa: E402

EVENT_TYPES = {
    "strike": "Удар / ураження",
    "outage": "Аварійне відключення",
    "rule_strike": "Ураження за правилом (умовні цілі)",
    "restore": "Відновлення",
    "demand": "Зміна попиту",
    "fuel": "Обмеження палива / ресурсу",
    "separate": "Відокремлення енергосистем",
    "resync": "Повторна синхронізація",
}


class EventIn(BaseModel):
    id: str | None = None
    at: _datetime
    type: str
    label: str = Field("", max_length=300)
    targets: list[int] = Field(default_factory=list, max_length=5000)
    match: list[dict] = Field(default_factory=list, max_length=50)
    payload: dict = Field(default_factory=dict)
    source_url: str | None = Field(None, max_length=2000)

    @field_validator("type")
    @classmethod
    def known_type(cls, value: str) -> str:
        if value not in EVENT_TYPES:
            raise ValueError(f"тип має бути одним із: {', '.join(EVENT_TYPES)}")
        return value


class ScenarioIn(BaseModel):
    id: str | None = Field(None, max_length=80)
    name: str = Field(min_length=3, max_length=200)
    mode: str = Field("whatif", pattern="^(historical|whatif)$")
    description: str = Field("", max_length=8000)
    countries: list[str] = Field(min_length=1, max_length=8)
    as_of: date | None = None
    start_at: _datetime
    end_at: _datetime
    step_hours: float = Field(1.0, ge=0.25, le=24 * 31)
    events: list[EventIn] = Field(default_factory=list, max_length=500)
    uncertainty: dict = Field(default_factory=dict)
    expected: dict = Field(default_factory=dict)
    sources: list[dict] = Field(default_factory=list)
    author: str = Field("", max_length=80)

    @field_validator("countries")
    @classmethod
    def upper(cls, value: list[str]) -> list[str]:
        return [c.upper() for c in value]


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "scenario"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _scenario_out(row: dict) -> dict:
    out = dict(row)
    out["step_hours"] = (row.get("uncertainty") or {}).get("step_hours", 1.0)
    return out


@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db)) -> dict:
    if not _has_table(db):
        return {"items": [], "event_types": EVENT_TYPES}
    rows = db.execute(
        text(
            """
            SELECT s.id, s.name, s.mode, s.description, s.countries, s.as_of, s.start_at, s.end_at,
                   jsonb_array_length(s.events) AS events, s.author, s.updated_at,
                   r.id AS last_run_id, r.status AS last_run_status, r.kind AS last_run_kind
            FROM odbl.grid_scenarios s
            LEFT JOIN LATERAL (
                SELECT id, status, kind FROM odbl.grid_runs
                WHERE scenario_id = s.id AND kind <> 'criticality'
                ORDER BY created_at DESC LIMIT 1
            ) r ON true
            ORDER BY s.mode, s.start_at
            """
        )
    ).mappings()
    return {"items": [dict(r) for r in rows], "event_types": EVENT_TYPES}


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        text("SELECT * FROM odbl.grid_scenarios WHERE id = :id"), {"id": scenario_id}
    ).mappings().first()
    if row is None:
        raise HTTPException(404, "Сценарій не знайдено")
    scenario = _scenario_out(dict(row))
    # Targets named by rules (match) are shown as the assets they resolve to now.
    from app.grid.runner import resolve_targets

    scenario = resolve_targets(db.get_bind(), scenario)
    ids = sorted({t for e in scenario["events"] for t in e.get("targets") or []})
    names = {}
    if ids:
        names = {
            r["id"]: dict(r)
            for r in db.execute(
                text(
                    "SELECT id, kind, name, max_voltage_kv, capacity_mw, fuel, country, "
                    "ST_X(ST_PointOnSurface(geom)) AS lon, ST_Y(ST_PointOnSurface(geom)) AS lat "
                    "FROM odbl.grid_assets WHERE id = ANY(:ids)"
                ),
                {"ids": ids},
            ).mappings()
        }
    scenario["assets"] = names
    return scenario


def _save_scenario(db: Session, scenario_id: str, payload: ScenarioIn) -> dict:
    if payload.end_at <= payload.start_at:
        raise HTTPException(422, "Кінець має бути пізніше за початок")
    if (payload.end_at - payload.start_at).days > 6 * 366:
        raise HTTPException(422, "Сценарій довший за 6 років")
    uncertainty = {**payload.uncertainty, "step_hours": payload.step_hours}
    events = [
        {**e.model_dump(mode="json", exclude_none=True), "id": e.id or f"e{i + 1}"}
        for i, e in enumerate(sorted(payload.events, key=lambda e: e.at))
    ]
    db.execute(
        text(
            """
            INSERT INTO odbl.grid_scenarios (id, name, mode, description, countries, as_of,
                start_at, end_at, events, uncertainty, expected, sources, author)
            VALUES (:id, :name, :mode, :description, :countries, :as_of, :start_at, :end_at,
                CAST(:events AS jsonb), CAST(:uncertainty AS jsonb), CAST(:expected AS jsonb),
                CAST(:sources AS jsonb), :author)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, mode = EXCLUDED.mode,
                description = EXCLUDED.description, countries = EXCLUDED.countries,
                as_of = EXCLUDED.as_of, start_at = EXCLUDED.start_at, end_at = EXCLUDED.end_at,
                events = EXCLUDED.events, uncertainty = EXCLUDED.uncertainty,
                expected = EXCLUDED.expected, sources = EXCLUDED.sources,
                author = EXCLUDED.author, updated_at = now()
            """
        ),
        {
            "id": scenario_id, "name": payload.name, "mode": payload.mode,
            "description": payload.description, "countries": payload.countries,
            "as_of": payload.as_of or payload.start_at.date(), "start_at": payload.start_at,
            "end_at": payload.end_at, "events": _json.dumps(events),
            "uncertainty": _json.dumps(uncertainty), "expected": _json.dumps(payload.expected),
            "sources": _json.dumps(payload.sources), "author": payload.author,
        },
    )
    db.commit()
    return get_scenario(scenario_id, db)


@router.post("/scenarios", dependencies=[Depends(require("grid.run"))], status_code=201)
def create_scenario(payload: ScenarioIn, db: Session = Depends(get_db)) -> dict:
    return _save_scenario(db, payload.id or _slug(payload.name), payload)


@router.put("/scenarios/{scenario_id}", dependencies=[Depends(require("grid.run"))])
def update_scenario(
    scenario_id: str, payload: ScenarioIn, db: Session = Depends(get_db)
) -> dict:
    return _save_scenario(db, scenario_id, payload)


@router.delete("/scenarios/{scenario_id}", dependencies=[Depends(require("grid.run"))])
def delete_scenario(scenario_id: str, db: Session = Depends(get_db)) -> dict:
    deleted = db.execute(
        text("DELETE FROM odbl.grid_scenarios WHERE id = :id"), {"id": scenario_id}
    ).rowcount
    db.commit()
    if not deleted:
        raise HTTPException(404, "Сценарій не знайдено")
    return {"deleted": scenario_id}


class RunIn(BaseModel):
    kind: str = Field("single", pattern="^(single|ensemble|criticality)$")
    members: int = Field(1, ge=1, le=500)
    seed: int = Field(42, ge=0, le=2**31 - 1)


@router.post(
    "/scenarios/{scenario_id}/runs", dependencies=[Depends(require("grid.run"))], status_code=201
)
def start_run(
    scenario_id: str, payload: RunIn, request: Request, db: Session = Depends(get_db)
) -> dict:
    if not db.scalar(text("SELECT 1 FROM odbl.grid_scenarios WHERE id = :id"), {"id": scenario_id}):
        raise HTTPException(404, "Сценарій не знайдено")
    if not db.scalar(
        text("SELECT 1 FROM odbl.grid_import_batches WHERE status = 'succeeded' LIMIT 1")
    ):
        raise HTTPException(409, "Мережу ще не імпортовано: спершу виконайте імпорт OSM")
    run_id = f"gr-{uuid.uuid4().hex[:12]}"
    members = payload.members if payload.kind == "ensemble" else 1
    db.execute(
        text(
            "INSERT INTO odbl.grid_runs (id, scenario_id, kind, members, seed, status, progress, "
            "summary) VALUES (:id, :s, :kind, :members, :seed, 'queued', 0, CAST('{}' AS jsonb))"
        ),
        {
            "id": run_id, "s": scenario_id, "kind": payload.kind, "members": members,
            "seed": payload.seed,
        },
    )
    db.commit()
    try:
        enqueue_grid(run_id, request_layer(request))
    except SimulationQueueUnavailable as exc:
        db.execute(
            text("UPDATE odbl.grid_runs SET status = 'failed', error = :e WHERE id = :id"),
            {"e": str(exc), "id": run_id},
        )
        db.commit()
        raise HTTPException(503, str(exc)) from exc
    return get_run(run_id, db)


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        text("SELECT * FROM odbl.grid_runs WHERE id = :id"), {"id": run_id}
    ).mappings().first()
    if row is None:
        raise HTTPException(404, "Прогін не знайдено")
    return dict(row)


@router.get("/scenarios/{scenario_id}/runs")
def scenario_runs(scenario_id: str, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        text(
            "SELECT id, kind, members, seed, status, progress, error, created_at, finished_at "
            "FROM odbl.grid_runs WHERE scenario_id = :id ORDER BY created_at DESC LIMIT 30"
        ),
        {"id": scenario_id},
    ).mappings()
    return {"items": [dict(r) for r in rows]}


@router.get("/runs/{run_id}/frames")
def run_frames(run_id: str, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        text(
            "SELECT sequence, at, metrics, state, events FROM odbl.grid_run_frames "
            "WHERE run_id = :id ORDER BY sequence"
        ),
        {"id": run_id},
    ).mappings()
    return {"items": [dict(r) for r in rows]}


@router.get("/snapshots/{snapshot_id}/network")
def snapshot_network(snapshot_id: int, db: Session = Depends(get_db)) -> dict:
    """Index arrays of a snapshot: frame states refer to buses, branches and generators by
    their position here."""
    snap = db.execute(
        text("SELECT id, as_of, countries, stats FROM odbl.grid_snapshots WHERE id = :id"),
        {"id": snapshot_id},
    ).mappings().first()
    if snap is None:
        raise HTTPException(404, "Знімок мережі не знайдено")
    buses = db.execute(
        text(
            "SELECT asset_id, voltage_kv, country, role, lon, lat FROM odbl.grid_buses "
            "WHERE snapshot_id = :s ORDER BY id"
        ),
        {"s": snapshot_id},
    ).all()
    branches = db.execute(
        text(
            "SELECT kind, asset_ids, voltage_kv FROM odbl.grid_branches WHERE snapshot_id = :s "
            "ORDER BY id"
        ),
        {"s": snapshot_id},
    ).all()
    gens = db.execute(
        text(
            "SELECT asset_id, fuel, p_max_mw FROM odbl.grid_generators WHERE snapshot_id = :s "
            "ORDER BY id"
        ),
        {"s": snapshot_id},
    ).all()
    return {
        **dict(snap),
        "buses": [
            [b.asset_id, b.voltage_kv, b.country, b.role, round(b.lon, 5), round(b.lat, 5)]
            for b in buses
        ],
        "branches": [[b.kind, list(b.asset_ids or []), b.voltage_kv] for b in branches],
        "generators": [[g.asset_id, g.fuel, g.p_max_mw] for g in gens],
    }
