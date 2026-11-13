"""Build a bus-branch network (a topology snapshot) from OSM power assets.

The approach follows PyPSA-Eur's OSM network builder in spirit:

* each substation becomes one bus per voltage level its lines use; levels are joined by
  transformers;
* OSM line ways are split at towers and junctions, so ways are chained through their
  shared end nodes; a chain that runs from one substation (or T-junction) to another
  becomes one branch, keeping the ids of all its ways;
* dangling chains (ending nowhere) carry no flow and are pruned;
* electrical parameters that OSM does not have (reactance, rating) are typical values for
  the voltage class and are marked ``estimated``;
* loads are spread over the substations of a country by the number of distribution
  substations around them (a density proxy available from OSM itself), also ``estimated``.

The snapshot is what existed on ``as_of`` (start dates and lifecycle); damage and other
dated changes are applied by the engine as states over time, not removed here.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Engine, text

# Typical overhead line data per voltage class: reactance Ω/km and thermal current kA per
# circuit (conductor bundles common in the region). Cables: lower reactance.
LINE_TYPES: list[tuple[float, float, float]] = [
    # (min kV, x Ω/km, I kA)
    (700, 0.28, 3.0),
    (450, 0.30, 2.0),
    (380, 0.30, 2.0),
    (300, 0.33, 1.6),
    (200, 0.40, 1.0),
    (100, 0.40, 0.6),
    (0, 0.40, 0.4),
]
CABLE_X = 0.12
TRANSFORMER_X = 0.12  # per unit on its own rating
BASE_MVA = 100.0


def line_type(kv: float) -> tuple[float, float]:
    for minimum, x, current in LINE_TYPES:
        if kv >= minimum:
            return x, current
    return LINE_TYPES[-1][1], LINE_TYPES[-1][2]


def transformer_rating(high_kv: float, low_kv: float) -> float:
    """Typical installed transformation capacity of a substation between two levels, MVA."""
    if high_kv >= 700:
        return 2000.0
    if high_kv >= 380:
        return 1000.0
    if high_kv >= 300:
        return 600.0 if low_kv >= 200 else 400.0
    if high_kv >= 200:
        return 250.0
    return 80.0


def line_parameters(kv: float, length_km: float, circuits: int, cable: bool) -> tuple[float, float]:
    """``(x_pu on 100 MVA, rating MVA)`` of a branch."""
    x_km, current = line_type(kv)
    if cable:
        x_km = CABLE_X
    length = max(length_km, 0.1)
    circuits = max(circuits, 1)
    x_ohm = x_km * length / circuits
    x_pu = x_ohm / (kv * kv / BASE_MVA)
    rating = math.sqrt(3) * kv * current * circuits
    return max(x_pu, 1e-6), rating


@dataclass
class SnapshotParams:
    countries: list[str]
    as_of: date
    min_voltage_kv: float = 110.0
    snap_m: float = 150.0
    plant_reach_m: float = 3000.0
    big_plant_reach_m: float = 10000.0

    def key(self) -> dict:
        return {
            "countries": sorted(c.upper() for c in self.countries),
            "as_of": self.as_of.isoformat(),
            "min_voltage_kv": self.min_voltage_kv,
            "snap_m": self.snap_m,
            "plant_reach_m": self.plant_reach_m,
            "big_plant_reach_m": self.big_plant_reach_m,
            "builder": 4,
        }


# Assets as they existed on the date: built (start_date year not after), not only planned.
EXISTED = r"""
    a.country = ANY(:countries)
    AND (
        a.status = 'active'
        -- Retired since the date: it still existed then.
        OR (a.status IN ('disused', 'abandoned', 'demolished')
            AND substring(a.tags->>'end_date' from '^\d{4}-\d{2}-\d{2}') IS NOT NULL
            AND substring(a.tags->>'end_date' from '^\d{4}-\d{2}-\d{2}')::date > :as_of)
        OR EXISTS (
            SELECT 1 FROM odbl.grid_overrides o
            WHERE o.asset_id = a.id AND o.field = 'in_service_from'
              AND (o.value #>> '{}')::date <= :as_of
        )
    )
    AND NOT (coalesce(substring(a.start_date from '^(\d{4})'), '0')::int > extract(year from CAST(:as_of AS date)))
    AND NOT EXISTS (
        SELECT 1 FROM odbl.grid_overrides o
        WHERE o.asset_id = a.id AND o.field = 'out_of_service_from'
          AND (o.value #>> '{}')::date <= :as_of
    )
"""

# Territory outside the operator's control on the date: the area's code replaces the country.
CONTROL = """
LEFT JOIN LATERAL (
    SELECT c.controlled_by FROM odbl.grid_control_areas c
    WHERE c.country = a.country AND c.valid_from <= :as_of
      AND (c.valid_to IS NULL OR c.valid_to > :as_of)
      AND ST_Intersects(c.geom, ST_PointOnSurface(a.geom))
    LIMIT 1
) ca ON true
"""

STATIONS_SQL = f"""
CREATE TEMP TABLE snap_stations ON COMMIT DROP AS
SELECT a.id, a.kind, a.max_voltage_kv, a.voltages_kv, coalesce(ca.controlled_by, a.country) AS country,
       a.capacity_mw, a.fuel, a.geom, a.geom_3857, ST_X(ST_PointOnSurface(a.geom)) AS lon,
       ST_Y(ST_PointOnSurface(a.geom)) AS lat
FROM odbl.grid_assets a
{CONTROL}
WHERE a.kind IN ('substation', 'converter', 'plant') AND {EXISTED}
  AND (
    a.kind = 'plant'
    OR a.max_voltage_kv >= :min_v
    OR (a.max_voltage_kv IS NULL AND coalesce(a.subkind, '') NOT IN ('minor_distribution', 'distribution'))
  )
"""

LINES_SQL = f"""
CREATE TEMP TABLE snap_lines ON COMMIT DROP AS
SELECT a.id, a.kind, a.max_voltage_kv, a.voltages_kv, a.circuits, a.cables, a.frequency_hz,
       coalesce(ca.controlled_by, a.country) AS country, coalesce(a.length_km, ST_Length(a.geom::geography) / 1000) AS length_km,
       a.geom, a.geom_3857,
       ST_StartPoint(a.geom) AS p0, ST_EndPoint(a.geom) AS p1
FROM odbl.grid_assets a
{CONTROL}
WHERE a.kind IN ('line', 'cable') AND GeometryType(a.geom) = 'LINESTRING' AND {EXISTED}
  AND (a.max_voltage_kv >= :min_v OR a.max_voltage_kv IS NULL)
  AND coalesce(a.frequency_hz, 50) <> 16.7
"""

# For every line end: the nearest station within reach (3857 prefilter, true distance check).
ENDS_SQL = """
SELECT l.id, e.side, ST_X(e.p) AS lon, ST_Y(e.p) AS lat, s.id AS station
FROM snap_lines l
CROSS JOIN LATERAL (VALUES ('a', l.p0), ('b', l.p1)) AS e(side, p)
LEFT JOIN LATERAL (
    SELECT st.id FROM snap_stations st
    WHERE st.geom_3857 && ST_Expand(ST_Transform(e.p, 3857), :snap * 3.5)
      AND ST_DWithin(st.geom::geography, e.p::geography, :snap)
    ORDER BY st.kind = 'plant', st.geom::geography <-> e.p::geography
    LIMIT 1
) s ON true
"""


def _fingerprint(engine: Engine, params: SnapshotParams) -> str:
    with engine.connect() as connection:
        data = connection.execute(
            text(
                "SELECT (SELECT coalesce(max(id), 0) FROM odbl.grid_import_batches "
                "WHERE status = 'succeeded'), (SELECT coalesce(max(id), 0) || ':' || count(*) "
                "FROM odbl.grid_overrides WHERE field IN ('in_service_from', 'out_of_service_from')), "
                "(SELECT coalesce(max(id), 0) || ':' || count(*) FROM odbl.grid_control_areas)"
            )
        ).one()
    payload = json.dumps({**params.key(), "data": list(map(str, data))}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:40]


@dataclass
class _Chain:
    ways: list[int] = field(default_factory=list)
    length_km: float = 0.0
    voltages: list[float | None] = field(default_factory=list)
    circuits: list[int] = field(default_factory=list)
    cable: bool = False
    countries: list[str] = field(default_factory=list)


def _contract(segments: list[dict], station_nodes: set) -> list[tuple]:
    """Chain line ways between stations and T-junctions.

    ``segments``: dicts with ``a``/``b`` node keys. Returns ``(start, end, chain)`` for every
    chain whose both ends are stations or junctions; dangling chains are pruned.
    """
    adjacency: dict = defaultdict(list)
    for index, seg in enumerate(segments):
        adjacency[seg["a"]].append(index)
        adjacency[seg["b"]].append(index)

    def is_terminal(node) -> bool:
        return node in station_nodes or len(adjacency[node]) != 2

    used = [False] * len(segments)
    chains: list[tuple] = []
    for start in list(adjacency):
        if not is_terminal(start):
            continue
        for first in adjacency[start]:
            if used[first]:
                continue
            chain = _Chain()
            node = start
            index = first
            while True:
                used[index] = True
                seg = segments[index]
                chain.ways.append(seg["id"])
                chain.length_km += seg["length_km"]
                chain.voltages.append(seg["kv"])
                chain.circuits.append(seg["circuits"])
                chain.cable = chain.cable or seg["cable"]
                if seg["country"]:
                    chain.countries.append(seg["country"])
                node = seg["b"] if seg["a"] == node else seg["a"]
                if is_terminal(node):
                    break
                following = [i for i in adjacency[node] if not used[i]]
                if not following:
                    break
                index = following[0]
            chains.append((start, node, chain))
    # Pure loops of non-terminal nodes are dropped (no station on them).
    # Prune dangling ends repeatedly: a non-station terminal with one chain carries no flow.
    while True:
        degree: dict = defaultdict(int)
        for a, b, _ in chains:
            if a != b:
                degree[a] += 1
                degree[b] += 1
        kept = [
            (a, b, c)
            for a, b, c in chains
            if a != b
            and (a in station_nodes or degree[a] > 1)
            and (b in station_nodes or degree[b] > 1)
        ]
        if len(kept) == len(chains):
            return kept
        chains = kept


def _chain_voltage(chain: _Chain, levels_a: set[float], levels_b: set[float], min_v: float) -> tuple[float | None, bool]:
    known = [v for v in chain.voltages if v]
    if known:
        # The most common declared voltage along the chain.
        counts: dict[float, int] = defaultdict(int)
        for v in known:
            counts[v] += 1
        return max(counts, key=lambda v: (counts[v], v)), len(known) < len(chain.voltages)
    common = sorted({v for v in levels_a & levels_b if v >= min_v}, reverse=True)
    if common:
        return common[0], True
    either = sorted({v for v in levels_a | levels_b if v >= min_v})
    if either:
        return either[0], True
    return None, True


def _level(kv: float) -> float:
    """Merge near-equal declared voltages (e.g. 330 and 330.0, 400 and 380 stay apart)."""
    return round(kv)


def build_snapshot(engine: Engine, params: SnapshotParams, *, force: bool = False, log=print) -> int:
    """Build (or reuse) the snapshot for the parameters; returns its id."""
    fingerprint = _fingerprint(engine, params)
    if not force:
        with engine.connect() as connection:
            existing = connection.execute(
                text(
                    "SELECT id FROM odbl.grid_snapshots WHERE fingerprint = :f AND status = 'ready' "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"f": fingerprint},
            ).scalar()
        if existing:
            return int(existing)

    countries = [c.upper() for c in params.countries]
    bind = {"countries": countries, "as_of": params.as_of, "min_v": params.min_voltage_kv}
    with engine.begin() as connection:
        snapshot_id = connection.execute(
            text(
                "INSERT INTO odbl.grid_snapshots (as_of, countries, min_voltage_kv, status, "
                "parameters, stats, fingerprint) VALUES (:as_of, :countries, :min_v, 'building', "
                "CAST(:params AS jsonb), '{}'::jsonb, :f) RETURNING id"
            ),
            {**bind, "params": json.dumps(params.key()), "f": fingerprint},
        ).scalar_one()

    stats: dict = {}
    try:
        with engine.begin() as connection:
            connection.execute(text(STATIONS_SQL), bind)
            connection.execute(text("CREATE INDEX ON snap_stations USING gist (geom_3857)"))
            connection.execute(text("ANALYZE snap_stations"))
            connection.execute(text(LINES_SQL), bind)
            stations = {
                row.id: row
                for row in connection.execute(
                    text(
                        "SELECT id, kind, max_voltage_kv, voltages_kv, country, capacity_mw, fuel, "
                        "lon, lat FROM snap_stations"
                    )
                )
            }
            lines = {
                row.id: row
                for row in connection.execute(
                    text(
                        "SELECT id, kind, max_voltage_kv, circuits, cables, frequency_hz, country, "
                        "length_km FROM snap_lines"
                    )
                )
            }
            ends: dict[int, dict] = defaultdict(dict)
            for row in connection.execute(text(ENDS_SQL), {"snap": params.snap_m}):
                key = ("S", row.station) if row.station else ("P", round(row.lon, 6), round(row.lat, 6))
                ends[row.id][row.side] = (key, row.lon, row.lat)
            log(f"snapshot {snapshot_id}: {len(stations)} stations, {len(lines)} line ways")

            segments = []
            point_xy: dict = {}
            for line_id, line in lines.items():
                if "a" not in ends[line_id] or "b" not in ends[line_id]:
                    continue
                (a, ax, ay), (b, bx, by) = ends[line_id]["a"], ends[line_id]["b"]
                if a == b:
                    continue
                point_xy.setdefault(a, (ax, ay))
                point_xy.setdefault(b, (bx, by))
                circuits = line.circuits or (max(1, (line.cables or 3) // 3) if line.cables else 1)
                segments.append(
                    {
                        "id": line_id, "a": a, "b": b, "length_km": float(line.length_km or 0),
                        "kv": line.max_voltage_kv, "circuits": circuits,
                        "cable": line.kind == "cable", "country": line.country,
                        "hvdc": line.frequency_hz == 0,
                    }
                )
            station_nodes = {("S", sid) for sid in stations}
            chains = _contract(segments, station_nodes)

            # Voltage levels each station is declared with (for inference of unknown lines).
            declared: dict = defaultdict(set)
            for sid, st in stations.items():
                for v in st.voltages_kv or []:
                    declared[("S", sid)].add(_level(v))

            branches = []
            dropped_no_voltage = 0
            for a, b, chain in chains:
                kv, inferred = _chain_voltage(chain, declared[a], declared[b], params.min_voltage_kv)
                if kv is None or kv < params.min_voltage_kv:
                    dropped_no_voltage += kv is None
                    continue
                branches.append((a, b, _level(kv), chain, inferred))

            # Buses: (node, level). Stations get one bus per level used by their branches.
            bus_levels: dict = defaultdict(set)
            for a, b, kv, _, _ in branches:
                bus_levels[a].add(kv)
                bus_levels[b].add(kv)

            # Plants that are not a line end attach to a nearby station.
            plant_station: dict[int, tuple] = {}
            for row in connection.execute(
                text(
                    """
                    SELECT p.id, s.id AS station, ST_Distance(p.geom::geography, s.geom::geography) AS d
                    FROM snap_stations p
                    CROSS JOIN LATERAL (
                        SELECT st.id, st.geom FROM snap_stations st
                        WHERE st.kind <> 'plant'
                          AND st.geom_3857 && ST_Expand(p.geom_3857, :reach * 3.5)
                        ORDER BY st.geom_3857 <-> p.geom_3857 LIMIT 4
                    ) s
                    WHERE p.kind = 'plant' AND p.capacity_mw IS NOT NULL
                    """
                ),
                {"reach": params.big_plant_reach_m},
            ):
                node = ("S", row.station)
                if node not in bus_levels:
                    continue
                plant = stations[row.id]
                reach = params.big_plant_reach_m if (plant.capacity_mw or 0) >= 300 else params.plant_reach_m
                if row.d <= reach and (row.id not in plant_station or row.d < plant_station[row.id][1]):
                    plant_station[row.id] = (node, row.d)

            bus_rows = []
            bus_index: dict = {}
            for node, levels in bus_levels.items():
                for kv in sorted(levels, reverse=True):
                    if node[0] == "S":
                        st = stations[node[1]]
                        role = "plant" if st.kind == "plant" else "substation"
                        bus_rows.append((node, kv, st.id, st.country, False, role, st.lon, st.lat))
                    else:
                        x, y = point_xy[node]
                        bus_rows.append((node, kv, None, None, True, "junction", x, y))

            # Junction buses take the country of the chains that meet there.
            junction_country: dict = {}
            for a, b, _, chain, _ in branches:
                for node in (a, b):
                    if node[0] == "P" and chain.countries:
                        junction_country.setdefault(node, chain.countries[0])

            for node, kv, asset_id, country, synthetic, role, lon, lat in bus_rows:
                bus_id = connection.execute(
                    text(
                        "INSERT INTO odbl.grid_buses (snapshot_id, asset_id, voltage_kv, country, "
                        "synthetic, role, lon, lat) VALUES (:s, :asset, :kv, :country, :syn, :role, "
                        ":lon, :lat) RETURNING id"
                    ),
                    {
                        "s": snapshot_id, "asset": asset_id, "kv": kv,
                        "country": country or junction_country.get(node), "syn": synthetic,
                        "role": role, "lon": lon, "lat": lat,
                    },
                ).scalar_one()
                bus_index[(node, kv)] = bus_id

            branch_rows = []
            estimated_lines = 0
            for a, b, kv, chain, inferred in branches:
                circuits = min(chain.circuits) if chain.circuits else 1
                x_pu, rating = line_parameters(kv, chain.length_km, circuits, chain.cable)
                flags = ["x_pu", "s_nom"]
                if inferred:
                    flags.append("voltage")
                if not all(c and c > 0 for c in chain.circuits):
                    flags.append("circuits")
                estimated_lines += 1
                branch_rows.append(
                    {
                        "s": snapshot_id, "kind": "cable" if chain.cable else "line",
                        "asset": chain.ways[0], "assets": chain.ways,
                        "f": bus_index[(a, kv)], "t": bus_index[(b, kv)], "kv": kv,
                        "c": circuits, "len": round(chain.length_km, 3), "x": x_pu,
                        "rating": round(rating, 1), "est": json.dumps(flags),
                    }
                )
            # Transformers between consecutive levels of one station.
            transformers = 0
            for node, levels in bus_levels.items():
                ordered = sorted(levels, reverse=True)
                for high, low in zip(ordered, ordered[1:], strict=False):
                    rating = transformer_rating(high, low)
                    branch_rows.append(
                        {
                            "s": snapshot_id, "kind": "transformer",
                            "asset": node[1] if node[0] == "S" else None,
                            "assets": [node[1]] if node[0] == "S" else [],
                            "f": bus_index[(node, high)], "t": bus_index[(node, low)], "kv": high,
                            "c": 1, "len": 0, "x": TRANSFORMER_X * BASE_MVA / rating,
                            "rating": rating, "est": json.dumps(["x_pu", "s_nom"]),
                        }
                    )
                    transformers += 1
            if branch_rows:
                connection.execute(
                    text(
                        "INSERT INTO odbl.grid_branches (snapshot_id, kind, asset_id, asset_ids, "
                        "from_bus, to_bus, voltage_kv, circuits, length_km, x_pu, s_nom_mva, "
                        "estimated) VALUES (:s, :kind, :asset, :assets, :f, :t, :kv, :c, :len, :x, "
                        ":rating, CAST(:est AS jsonb))"
                    ),
                    branch_rows,
                )

            # Generators: plants at a line end use their own buses, others a nearby station.
            gen_rows = []
            unconnected_mw = 0.0
            unconnected = 0
            for sid, st in stations.items():
                if st.kind != "plant" or not st.capacity_mw:
                    continue
                node = ("S", sid) if ("S", sid) in bus_levels else plant_station.get(sid, (None,))[0]
                if node is None:
                    unconnected += 1
                    unconnected_mw += st.capacity_mw
                    continue
                levels = sorted(bus_levels[node], reverse=True)
                kv = levels[0] if st.capacity_mw >= 300 or node == ("S", sid) else levels[-1]
                gen_rows.append(
                    {
                        "s": snapshot_id, "bus": bus_index[(node, kv)], "asset": sid,
                        "fuel": st.fuel, "p": st.capacity_mw,
                        "est": json.dumps([] if node == ("S", sid) else ["connection"]),
                    }
                )
            if gen_rows:
                connection.execute(
                    text(
                        "INSERT INTO odbl.grid_generators (snapshot_id, bus_id, asset_id, fuel, "
                        "p_max_mw, availability, estimated) VALUES (:s, :bus, :asset, :fuel, :p, 1, "
                        "CAST(:est AS jsonb))"
                    ),
                    gen_rows,
                )

            # Loads: every substation bus at its lowest level, weighted by the distribution
            # substations closest to it (OSM density as a proxy for demand density).
            load_nodes = [n for n in bus_levels if n[0] == "S" and stations[n[1]].kind != "plant"]
            connection.execute(
                text(
                    "CREATE TEMP TABLE snap_load_nodes (id bigint, country text, geom_3857 geometry) "
                    "ON COMMIT DROP"
                )
            )
            if load_nodes:
                connection.execute(
                    text(
                        "INSERT INTO snap_load_nodes SELECT id, country, geom_3857 FROM snap_stations "
                        "WHERE id = ANY(:ids)"
                    ),
                    {"ids": [n[1] for n in load_nodes]},
                )
            connection.execute(text("CREATE INDEX ON snap_load_nodes USING gist (geom_3857)"))
            connection.execute(text("ANALYZE snap_load_nodes"))
            weights: dict[int, float] = {n[1]: 1.0 for n in load_nodes}
            for row in connection.execute(
                text(
                    """
                    SELECT n.id, count(*) AS c
                    FROM odbl.grid_assets d
                    CROSS JOIN LATERAL (
                        SELECT ln.id FROM snap_load_nodes ln WHERE ln.country = d.country
                        ORDER BY ln.geom_3857 <-> d.geom_3857 LIMIT 1
                    ) n
                    WHERE d.kind = 'substation' AND d.country = ANY(:countries)
                      AND coalesce(d.max_voltage_kv, 0) < :min_v AND d.status = 'active'
                      -- Demand density of controlled territory only.
                      AND NOT EXISTS (
                          SELECT 1 FROM odbl.grid_control_areas c
                          WHERE c.country = d.country AND c.valid_from <= :as_of
                            AND (c.valid_to IS NULL OR c.valid_to > :as_of)
                            AND ST_Intersects(c.geom, d.geom)
                      )
                    GROUP BY n.id
                    """
                ),
                bind,
            ):
                weights[row.id] = weights.get(row.id, 1.0) + float(row.c)
            totals: dict[str, float] = defaultdict(float)
            for node in load_nodes:
                totals[stations[node[1]].country] += weights[node[1]]
            load_rows = []
            for node in load_nodes:
                st = stations[node[1]]
                kv = min(bus_levels[node])
                load_rows.append(
                    {
                        "s": snapshot_id, "bus": bus_index[(node, kv)], "country": st.country,
                        "share": weights[node[1]] / totals[st.country],
                    }
                )
            if load_rows:
                connection.execute(
                    text(
                        "INSERT INTO odbl.grid_loads (snapshot_id, bus_id, country, share) "
                        "VALUES (:s, :bus, :country, :share)"
                    ),
                    load_rows,
                )

            stats = {
                "buses": len(bus_rows),
                "branches": len(branches),
                "transformers": transformers,
                "line_km": round(sum(c.length_km for *_, c, _ in branches)),
                "generators": len(gen_rows),
                "generation_mw": round(sum(r["p"] for r in gen_rows)),
                "unconnected_plants": unconnected,
                "unconnected_mw": round(unconnected_mw),
                "loads": len(load_rows),
                "dropped_no_voltage": dropped_no_voltage,
                "line_ways": len(lines),
                "stations": len(stations),
            }
            stats.update(_islands(bus_index.values(), branch_rows, {r["bus"] for r in gen_rows}))
            connection.execute(
                text(
                    "UPDATE odbl.grid_snapshots SET status = 'ready', stats = CAST(:stats AS jsonb) "
                    "WHERE id = :id"
                ),
                {"stats": json.dumps(stats), "id": snapshot_id},
            )
    except Exception as exc:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE odbl.grid_snapshots SET status = 'failed', "
                    "stats = CAST(:stats AS jsonb) WHERE id = :id"
                ),
                {"stats": json.dumps({"error": str(exc)[:2000]}), "id": snapshot_id},
            )
        raise
    log(f"snapshot {snapshot_id}: {stats}")
    return int(snapshot_id)


def _islands(bus_ids, branch_rows: list[dict], gen_buses: set) -> dict:
    """Connectivity of the built network: number of islands and the share of the largest."""
    parent = {b: b for b in bus_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for row in branch_rows:
        ra, rb = find(row["f"]), find(row["t"])
        if ra != rb:
            parent[ra] = rb
    sizes: dict = defaultdict(int)
    with_gen: set = set()
    for b in parent:
        sizes[find(b)] += 1
        if b in gen_buses:
            with_gen.add(find(b))
    total = sum(sizes.values()) or 1
    return {
        "islands": len(sizes),
        "islands_with_generation": len(with_gen),
        "largest_island_share": round(max(sizes.values(), default=0) / total, 3),
    }
