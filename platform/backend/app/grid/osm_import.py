"""Import OpenStreetMap power infrastructure into the ODbL layer (``odbl.grid_assets``).

Pipeline per region:

1. a Geofabrik ``*.osm.pbf`` extract (downloaded beforehand or by ``download``);
2. ``osmium tags-filter`` keeps power objects and the nodes they reference (tens of MB
   instead of GB);
3. pyosmium reads the filtered file with node locations and multipolygon assembly;
   ``app.grid.osm_tags.classify`` turns tags into features;
4. rows are streamed with COPY into a staging table and upserted by (osm_type, osm_id),
   so asset ids stay stable across re-imports (overrides and scenarios refer to them);
5. post-processing: line lengths, plant capacity from the generators inside it, removal of
   objects that disappeared from the region since the previous import.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, text

from app.grid import OSM_ATTRIBUTION, OSM_LICENCE
from app.grid.osm_tags import KINDS, LIFECYCLE_PREFIXES, classify, keep_generator

GEOFABRIK = "https://download.geofabrik.de"
# Region code -> Geofabrik path. Ukraine goes first: the Crimea is in both the Ukrainian
# and the Russian extracts and keeps the country of the first import.
REGIONS: dict[str, str] = {
    "ua": "europe/ukraine",
    "md": "europe/moldova",
    "pl": "europe/poland",
    "sk": "europe/slovakia",
    "hu": "europe/hungary",
    "ro": "europe/romania",
    "ru": "russia",
    "by": "europe/belarus",
}

AREA_KINDS = {"substation", "plant", "generator", "converter"}
LINE_KINDS = {"line", "minor_line", "cable"}
CHUNK = 20_000

STAGE_COLUMNS = (
    "osm_type", "osm_id", "kind", "subkind", "status", "name", "name_en", "operator", "ref",
    "voltages_kv", "max_voltage_kv", "frequency_hz", "circuits", "cables", "capacity_mw",
    "capacity_source", "fuel", "start_date", "tags", "quality", "geom_wkb", "area_way",
)


def source_url(region: str) -> str:
    return f"{GEOFABRIK}/{REGIONS[region]}-latest.osm.pbf"


def raw_path(directory: Path, region: str) -> Path:
    return directory / "raw" / f"{Path(REGIONS[region]).name}-latest.osm.pbf"


def filtered_path(directory: Path, region: str) -> Path:
    return directory / "filtered" / f"{region}-power.osm.pbf"


def md5sum(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - Geofabrik publishes MD5 checksums
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(directory: Path, region: str) -> Path:
    """Download the Geofabrik extract unless a copy with a matching checksum is present."""
    import httpx

    target = raw_path(directory, region)
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = httpx.get(source_url(region) + ".md5", timeout=60).text.split()[0]
    if target.exists() and md5sum(target) == expected:
        return target
    with httpx.stream("GET", source_url(region), timeout=None, follow_redirects=True) as reply:
        reply.raise_for_status()
        with target.open("wb") as handle:
            for chunk in reply.iter_bytes(1 << 20):
                handle.write(chunk)
    if md5sum(target) != expected:
        raise RuntimeError(f"checksum mismatch for {target.name}")
    return target


def filter_power(raw: Path, out: Path) -> Path:
    """Keep power objects (with lifecycle prefixes) and everything they reference."""
    out.parent.mkdir(parents=True, exist_ok=True)
    expressions = ["nwr/power"] + [f"nwr/{prefix}:power" for prefix in LIFECYCLE_PREFIXES]
    # Write next to the target and rename, so an interrupted run never leaves a partial file
    # that a later run would take for a finished one.
    partial = out.with_name(out.name + ".partial.osm.pbf")
    subprocess.run(
        ["osmium", "tags-filter", "--overwrite", "-o", str(partial), str(raw), *expressions],
        check=True,
    )
    partial.replace(out)
    return out


def _short(value: str | None, limit: int = 40) -> str | None:
    """Free-text tags sometimes hold sentences; the coded columns keep the first 40 chars."""
    return value[:limit] if value else value


def _row(osm_type: str, osm_id: int, tags: dict, wkb: str, area_way: bool) -> tuple | None:
    feature = classify(tags)
    if feature is None:
        return None
    if feature.kind == "generator" and not keep_generator(feature):
        return None
    voltages = "{" + ",".join(str(v) for v in feature.voltages_kv) + "}"
    return (
        osm_type, osm_id, feature.kind, _short(feature.subkind), feature.status, feature.name,
        feature.name_en, feature.operator, feature.ref, voltages, feature.max_voltage_kv,
        feature.frequency_hz, feature.circuits, feature.cables, feature.capacity_mw,
        feature.capacity_source, feature.fuel, _short(feature.start_date),
        json.dumps(tags, ensure_ascii=False), json.dumps(feature.quality), wkb, area_way,
    )


def _power_kind(tags: dict) -> str | None:
    """Kind of a power object from its raw tags, before full classification."""
    from app.grid.osm_tags import lifecycle

    power, _ = lifecycle(tags)
    return KINDS.get(power or "")


def read_features(path: Path) -> Iterator[tuple]:
    """Rows for the staging table from a (filtered) OSM file."""
    import osmium

    factory = osmium.geom.WKBFactory()
    processor = (
        osmium.FileProcessor(str(path))
        .with_locations()
        .with_areas(osmium.filter.KeyFilter("power", "construction:power", "disused:power"))
    )
    for obj in processor:
        if obj.is_node():
            tags = {tag.k: tag.v for tag in obj.tags}
            if not tags or _power_kind(tags) not in AREA_KINDS:
                continue
            try:
                wkb = factory.create_point(obj)
            except Exception:  # noqa: BLE001 - invalid location
                continue
            row = _row("n", obj.id, tags, wkb, False)
        elif obj.is_way():
            tags = {tag.k: tag.v for tag in obj.tags}
            kind = _power_kind(tags) if tags else None
            if kind is None:
                continue
            try:
                wkb = factory.create_linestring(obj)
            except Exception:  # noqa: BLE001 - missing node locations or one-node way
                continue
            row = _row("w", obj.id, tags, wkb, kind in AREA_KINDS and obj.is_closed())
        elif obj.is_area():
            # Ways become polygons in SQL; only multipolygon relations are taken here.
            if obj.from_way():
                continue
            tags = {tag.k: tag.v for tag in obj.tags}
            if _power_kind(tags) not in AREA_KINDS:
                continue
            try:
                wkb = factory.create_multipolygon(obj)
            except Exception:  # noqa: BLE001 - broken multipolygon
                continue
            row = _row("r", obj.orig_id(), tags, wkb, False)
        else:
            continue
        if row is not None:
            yield row


STAGE_DDL = """
CREATE TEMP TABLE grid_stage (
    osm_type text, osm_id bigint, kind text, subkind text, status text, name text,
    name_en text, operator text, ref text, voltages_kv text, max_voltage_kv double precision,
    frequency_hz double precision, circuits integer, cables integer,
    capacity_mw double precision, capacity_source text, fuel text, start_date text,
    tags text, quality text, geom_wkb text, area_way boolean
) ON COMMIT DROP
"""

UPSERT = """
INSERT INTO odbl.grid_assets (
    osm_type, osm_id, kind, subkind, status, name, name_en, operator, ref, voltages_kv,
    max_voltage_kv, frequency_hz, circuits, cables, capacity_mw, capacity_source, fuel,
    start_date, country, tags, quality, geom, batch_id, updated_at)
SELECT DISTINCT ON (osm_type, osm_id)
    osm_type, osm_id, kind, subkind, status, name, name_en, operator, ref,
    voltages_kv::double precision[], max_voltage_kv, frequency_hz, circuits, cables,
    capacity_mw, capacity_source, fuel, start_date, :country, tags::jsonb, quality::jsonb,
    CASE
        WHEN area_way AND ST_IsClosed(g) AND ST_NPoints(g) >= 4
            THEN ST_MakePolygon(g)
        ELSE g
    END,
    :batch, now()
FROM (SELECT *, ST_SetSRID(geom_wkb::geometry, 4326) AS g FROM grid_stage) s
ORDER BY osm_type, osm_id
ON CONFLICT (osm_type, osm_id) DO UPDATE SET
    kind = EXCLUDED.kind, subkind = EXCLUDED.subkind, status = EXCLUDED.status,
    name = EXCLUDED.name, name_en = EXCLUDED.name_en, operator = EXCLUDED.operator,
    ref = EXCLUDED.ref, voltages_kv = EXCLUDED.voltages_kv,
    max_voltage_kv = EXCLUDED.max_voltage_kv, frequency_hz = EXCLUDED.frequency_hz,
    circuits = EXCLUDED.circuits, cables = EXCLUDED.cables,
    capacity_mw = EXCLUDED.capacity_mw, capacity_source = EXCLUDED.capacity_source,
    fuel = EXCLUDED.fuel, start_date = EXCLUDED.start_date,
    country = coalesce(odbl.grid_assets.country, EXCLUDED.country),
    tags = EXCLUDED.tags, quality = EXCLUDED.quality, geom = EXCLUDED.geom,
    batch_id = EXCLUDED.batch_id, updated_at = now()
"""

POSTPROCESS = [
    # Length of every line and cable.
    """
    UPDATE odbl.grid_assets SET length_km = ST_Length(geom::geography) / 1000
    WHERE batch_id = :batch AND kind IN ('line', 'minor_line', 'cable')
    """,
    # Generators inside a plant belong to it: noted so the topology does not count twice.
    """
    UPDATE odbl.grid_assets g SET quality = g.quality || '["inside_plant"]'::jsonb
    FROM odbl.grid_assets p
    WHERE g.batch_id = :batch AND g.kind = 'generator' AND p.kind = 'plant'
      AND ST_Dimension(p.geom) = 2 AND ST_Intersects(p.geom, g.geom)
      AND NOT g.quality ? 'inside_plant'
    """,
    # Plants without a declared output get the sum of their generators.
    """
    UPDATE odbl.grid_assets p
    SET capacity_mw = s.total, capacity_source = 'generators',
        quality = (p.quality - 'capacity_missing') || '["capacity_from_generators"]'::jsonb
    FROM (
        SELECT p2.id, sum(g.capacity_mw) AS total
        FROM odbl.grid_assets p2
        JOIN odbl.grid_assets g
          ON g.kind = 'generator' AND g.capacity_mw IS NOT NULL
         AND ST_Intersects(p2.geom, g.geom)
        WHERE p2.batch_id = :batch AND p2.kind = 'plant' AND p2.capacity_mw IS NULL
          AND ST_Dimension(p2.geom) = 2
        GROUP BY p2.id
    ) s
    WHERE p.id = s.id
    """,
]


def _copy_rows(connection, rows: list[tuple]) -> None:
    raw = connection.connection.dbapi_connection
    with raw.cursor() as cursor:
        with cursor.copy(f"COPY grid_stage ({', '.join(STAGE_COLUMNS)}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)


def load(
    engine: Engine,
    rows: Iterator[tuple],
    *,
    region: str,
    url: str,
    checksum: str | None = None,
    source_timestamp: datetime | None = None,
    prune: bool = True,
    log=print,
) -> dict:
    """Stream rows into ``odbl.grid_assets`` as one batch; returns the batch counts."""
    with engine.begin() as connection:
        batch = connection.execute(
            text(
                "INSERT INTO odbl.grid_import_batches "
                "(region, source_url, source_timestamp, checksum, licence, attribution, status, "
                "counts) VALUES (:region, :url, :ts, :checksum, :licence, :attribution, "
                "'running', '{}'::jsonb) "
                "RETURNING id"
            ),
            {
                "region": region, "url": url, "ts": source_timestamp, "checksum": checksum,
                "licence": OSM_LICENCE, "attribution": OSM_ATTRIBUTION,
            },
        ).scalar_one()
    counts: Counter[str] = Counter()
    try:
        with engine.begin() as connection:
            connection.execute(text(STAGE_DDL))
            chunk: list[tuple] = []
            for row in rows:
                chunk.append(row)
                counts[row[2]] += 1
                if len(chunk) >= CHUNK:
                    _copy_rows(connection, chunk)
                    chunk.clear()
                    log(f"  {sum(counts.values()):>9} objects read")
            if chunk:
                _copy_rows(connection, chunk)
            connection.execute(text(UPSERT), {"country": region.upper(), "batch": batch})
            for statement in POSTPROCESS:
                connection.execute(text(statement), {"batch": batch})
            removed = 0
            if prune:
                removed = connection.execute(
                    text(
                        "DELETE FROM odbl.grid_assets WHERE country = :country "
                        "AND batch_id IS DISTINCT FROM :batch"
                    ),
                    {"country": region.upper(), "batch": batch},
                ).rowcount
            summary = {**dict(counts), "total": sum(counts.values()), "removed": removed}
            connection.execute(
                text(
                    "UPDATE odbl.grid_import_batches SET status = 'succeeded', counts = :counts, "
                    "finished_at = now() WHERE id = :batch"
                ),
                {"counts": json.dumps(summary), "batch": batch},
            )
    except Exception as exc:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE odbl.grid_import_batches SET status = 'failed', error = :error, "
                    "finished_at = now() WHERE id = :batch"
                ),
                {"error": str(exc)[:4000], "batch": batch},
            )
        raise
    return {"batch": batch, **summary}


def pbf_timestamp(path: Path) -> datetime | None:
    """``osmosis_replication_timestamp`` of a Geofabrik extract, if present."""
    try:
        import osmium

        header = osmium.io.Reader(str(path), osmium.osm.osm_entity_bits.NOTHING).header()
        value = header.get("osmosis_replication_timestamp")
    except Exception:  # noqa: BLE001
        return None
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def import_region(
    engine: Engine, directory: Path, region: str, *, fetch: bool = False, log=print
) -> dict:
    """Full pipeline for one region: (download) → filter → read → load."""
    if region not in REGIONS:
        raise ValueError(f"unknown region {region!r}; known: {', '.join(REGIONS)}")
    raw = download(directory, region) if fetch else raw_path(directory, region)
    if not raw.exists():
        raise FileNotFoundError(f"{raw} is missing; download it or pass --fetch")
    checksum_file = raw.with_name(raw.name + ".md5")
    checksum = checksum_file.read_text().split()[0] if checksum_file.exists() else None
    filtered = filtered_path(directory, region)
    if not filtered.exists() or filtered.stat().st_mtime < raw.stat().st_mtime:
        log(f"{region}: filtering {raw.name}")
        filter_power(raw, filtered)
    log(f"{region}: reading {filtered.name}")
    return load(
        engine,
        read_features(filtered),
        region=region,
        url=source_url(region),
        checksum=checksum,
        source_timestamp=pbf_timestamp(raw),
        log=log,
    )
