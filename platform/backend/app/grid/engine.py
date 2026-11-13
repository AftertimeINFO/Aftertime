"""Quasi-static cascade on a real network: DC power flow, islands, load shedding, protection.

One step of the model at a moment ``t``:

1. apply the events due by ``t`` (outages of substations, lines and plants, repairs, demand
   and fuel changes, separation of synchronous areas);
2. find the islands of the energised network; in each island balance generation against
   demand — generators are dispatched in proportion to what they have available, and a
   deficit is covered by shedding load in proportion (the role of under-frequency load
   shedding and of emergency schedules);
3. solve the DC power flow of every island and compute branch loadings;
4. protection: branches loaded above the trip threshold are switched off, and the step
   repeats from 2 until nothing more trips (a cascade);
5. report metrics and compact states for the map.

The base case is made N-0 secure: ratings (which OSM does not carry, so they are typical
values) are raised where the undisturbed network would already exceed them. Without this
the estimate of ratings, not the incident, would drive the cascade.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve
from sqlalchemy import Engine, text

from app.grid.topology import BASE_MVA

# --- demand and availability ---------------------------------------------------------------

# Average demand, MW, by country (annual consumption / 8760), with the war-time drop in UA.
BASE_DEMAND_MW: dict[str, list[tuple[int, float]]] = {
    "UA": [(0, 16_500), (2022, 13_500), (2023, 13_000)],
    "MD": [(0, 520)],
    "PL": [(0, 19_500)],
    "SK": [(0, 3_200)],
    "HU": [(0, 4_900)],
    "RO": [(0, 6_200)],
    "RU": [(0, 125_000)],
    "BY": [(0, 4_300)],
}
MONTH_FACTOR = [1.18, 1.15, 1.05, 0.95, 0.88, 0.88, 0.92, 0.92, 0.9, 0.98, 1.08, 1.15]
TIMEZONE_OFFSET = {"UA": 2, "MD": 2, "RO": 2, "PL": 1, "SK": 1, "HU": 1, "BY": 3, "RU": 3}

# Share of installed capacity that is typically available and running.
AVAILABILITY = {
    "nuclear": 0.85, "coal": 0.55, "gas": 0.5, "oil": 0.3, "hydro": 0.5, "wind": 0.3,
    "biomass": 0.6, "waste": 0.6, "geothermal": 0.8, "storage": 0.0,
}
DEFAULT_AVAILABILITY = 0.5

# Areas that stopped operating synchronously from a date (branches between them open).
SEPARATIONS: list[tuple[frozenset[str], date, str]] = [
    (frozenset({"UA", "RU"}), date(2022, 2, 24), "UA відокремлено від ОЕС Росії"),
    (frozenset({"UA", "BY"}), date(2022, 2, 24), "UA відокремлено від ОЕС Білорусі"),
]
# Territory outside the operator's control is not a separation: see ``control``.


def hour_factor(hour: int) -> float:
    if hour < 6:
        return 0.78
    if hour < 8:
        return 0.92
    if hour < 17:
        return 1.03
    if hour < 22:
        return 1.15
    return 0.92


def solar_factor(moment: datetime) -> float:
    hour = moment.hour + 2 + moment.minute / 60
    if hour < 6 or hour > 19:
        return 0.0
    season = 0.55 + 0.45 * math.cos((moment.month - 6.5) / 12 * 2 * math.pi)
    return max(0.0, math.sin((hour - 6) / 13 * math.pi)) * 0.7 * season


def peak_demand_mw(country: str, moment: datetime) -> float:
    """Demand at the evening peak of the day of ``moment``."""
    local = moment + timedelta(hours=TIMEZONE_OFFSET.get(country, 2))
    return demand_mw(country, moment) / hour_factor(local.hour) * hour_factor(19)


def demand_mw(country: str, moment: datetime) -> float:
    levels = BASE_DEMAND_MW.get(country)
    if not levels:
        return 0.0
    base = [mw for year, mw in levels if moment.year >= year][-1]
    local = moment + timedelta(hours=TIMEZONE_OFFSET.get(country, 2))
    return base * MONTH_FACTOR[local.month - 1] * hour_factor(local.hour)


# --- network --------------------------------------------------------------------------------


@dataclass
class Network:
    snapshot_id: int
    as_of: date
    bus_id: np.ndarray
    bus_asset: np.ndarray  # -1 for junctions
    bus_country: list[str]
    bus_kv: np.ndarray
    bus_lonlat: np.ndarray
    br_id: np.ndarray
    br_from: np.ndarray
    br_to: np.ndarray
    br_x: np.ndarray
    br_rating: np.ndarray
    br_kind: list[str]
    br_kv: np.ndarray
    br_assets: list[list[int]]
    gen_bus: np.ndarray
    gen_pmax: np.ndarray
    gen_fuel: list[str | None]
    gen_asset: np.ndarray
    load_bus: np.ndarray
    load_share: np.ndarray
    load_country: list[str]
    # Asset id -> indices.
    asset_buses: dict[int, list[int]] = field(default_factory=dict)
    asset_branches: dict[int, list[int]] = field(default_factory=dict)
    asset_gens: dict[int, list[int]] = field(default_factory=dict)
    # Control areas: the ids each bus lies in, and the areas with their dates.
    bus_areas: list[tuple[int, ...]] = field(default_factory=list)
    areas: dict[int, dict] = field(default_factory=dict)

    @property
    def countries(self) -> list[str]:
        return sorted(set(self.load_country))


def load_network(engine: Engine, snapshot_id: int) -> Network:
    with engine.connect() as connection:
        snap = connection.execute(
            text("SELECT id, as_of FROM odbl.grid_snapshots WHERE id = :id AND status = 'ready'"),
            {"id": snapshot_id},
        ).one()
        buses = connection.execute(
            text(
                "SELECT id, coalesce(asset_id, -1) AS asset_id, coalesce(country, '') AS country, "
                "voltage_kv, lon, lat, areas FROM odbl.grid_buses WHERE snapshot_id = :s ORDER BY id"
            ),
            {"s": snapshot_id},
        ).all()
        areas = connection.execute(
            text(
                "SELECT id, name, controlled_by, valid_from, valid_to, source_url "
                "FROM odbl.grid_control_areas ORDER BY id"
            )
        ).all()
        branches = connection.execute(
            text(
                "SELECT id, kind, from_bus, to_bus, x_pu, s_nom_mva, voltage_kv, asset_ids "
                "FROM odbl.grid_branches WHERE snapshot_id = :s ORDER BY id"
            ),
            {"s": snapshot_id},
        ).all()
        gens = connection.execute(
            text(
                "SELECT bus_id, p_max_mw, fuel, coalesce(asset_id, -1) AS asset_id "
                "FROM odbl.grid_generators WHERE snapshot_id = :s ORDER BY id"
            ),
            {"s": snapshot_id},
        ).all()
        loads = connection.execute(
            text(
                "SELECT bus_id, share, coalesce(country, '') AS country FROM odbl.grid_loads "
                "WHERE snapshot_id = :s ORDER BY id"
            ),
            {"s": snapshot_id},
        ).all()
    index = {row.id: i for i, row in enumerate(buses)}
    net = Network(
        snapshot_id=snap.id,
        as_of=snap.as_of,
        bus_id=np.array([b.id for b in buses], dtype=np.int64),
        bus_asset=np.array([b.asset_id for b in buses], dtype=np.int64),
        bus_country=[b.country for b in buses],
        bus_kv=np.array([b.voltage_kv for b in buses]),
        bus_lonlat=np.array([[b.lon, b.lat] for b in buses]).reshape(-1, 2),
        br_id=np.array([b.id for b in branches], dtype=np.int64),
        br_from=np.array([index[b.from_bus] for b in branches], dtype=np.int64),
        br_to=np.array([index[b.to_bus] for b in branches], dtype=np.int64),
        br_x=np.array([b.x_pu for b in branches]),
        br_rating=np.array([b.s_nom_mva for b in branches]),
        br_kind=[b.kind for b in branches],
        br_kv=np.array([b.voltage_kv for b in branches]),
        br_assets=[list(b.asset_ids or []) for b in branches],
        gen_bus=np.array([index[g.bus_id] for g in gens], dtype=np.int64),
        gen_pmax=np.array([g.p_max_mw for g in gens]),
        gen_fuel=[g.fuel for g in gens],
        gen_asset=np.array([g.asset_id for g in gens], dtype=np.int64),
        load_bus=np.array([index[load.bus_id] for load in loads], dtype=np.int64),
        load_share=np.array([load.share for load in loads]),
        load_country=[load.country for load in loads],
        bus_areas=[tuple(b.areas or ()) for b in buses],
        areas={a.id: a._asdict() for a in areas},
    )
    for i, asset in enumerate(net.bus_asset):
        if asset >= 0:
            net.asset_buses.setdefault(int(asset), []).append(i)
    for i, assets in enumerate(net.br_assets):
        if net.br_kind[i] == "transformer":
            continue  # a transformer goes down with its substation's buses
        for asset in assets:
            net.asset_branches.setdefault(int(asset), []).append(i)
    for i, asset in enumerate(net.gen_asset):
        if asset >= 0:
            net.asset_gens.setdefault(int(asset), []).append(i)
    return net


# --- state ----------------------------------------------------------------------------------


@dataclass
class State:
    bus_up: np.ndarray
    br_up: np.ndarray  # switched by events / separations
    br_tripped: np.ndarray  # switched by protection
    gen_factor: np.ndarray  # 0…1, damage of plants
    gen_capacity: np.ndarray  # MW, may be overridden
    demand_factor: dict[str, float] = field(default_factory=dict)
    fuel_factor: dict[str, float] = field(default_factory=dict)
    separated: set[frozenset[str]] = field(default_factory=set)
    rating: np.ndarray | None = None
    # Unmodelled supply per bus as a share of that bus's demand (base-case balancing).
    balancing_ratio: np.ndarray | None = None
    # Capacity of running units, MW (unit commitment); None: everything available runs.
    committed: np.ndarray | None = None
    # Buses in territory outside the operator's control (see ``control``) and the load
    # shares spread over the territory still controlled; None: no control area in force.
    occupied: np.ndarray | None = None
    load_share: np.ndarray | None = None
    ens_mwh: float = 0.0
    previous_unserved: float = 0.0

    @classmethod
    def initial(cls, net: Network) -> State:
        return cls(
            bus_up=np.ones(len(net.bus_id), dtype=bool),
            br_up=np.ones(len(net.br_id), dtype=bool),
            br_tripped=np.zeros(len(net.br_id), dtype=bool),
            gen_factor=np.ones(len(net.gen_pmax)),
            gen_capacity=net.gen_pmax.copy(),
            rating=net.br_rating.copy(),
        )


def areas_in_force(net: Network, day: date) -> set[int]:
    return {
        area_id for area_id, area in net.areas.items()
        if area["valid_from"] <= day and (area["valid_to"] is None or area["valid_to"] > day)
    }


def control(net: Network, state: State, day: date) -> set[int]:
    """Put the control areas in force on ``day``: their buses, plants and loads leave the
    system, and each country's demand is spread over the territory it still controls (the
    national demand profile describes controlled territory). Returns the areas in force."""
    active = areas_in_force(net, day)
    occupied = np.array([bool(active.intersection(ids)) for ids in net.bus_areas], dtype=bool)
    if len(occupied) != len(net.bus_id):
        occupied = np.zeros(len(net.bus_id), dtype=bool)
    state.occupied = occupied
    share = net.load_share.copy()
    lost = occupied[net.load_bus]
    share[lost] = 0.0
    countries = np.array(net.load_country)
    for country in set(net.load_country):
        mine = countries == country
        kept = share[mine].sum()
        if kept > 0:
            share[mine] *= net.load_share[mine].sum() / kept
    state.load_share = share
    return active


def live_buses(state: State) -> np.ndarray:
    """Buses in service and in controlled territory."""
    return state.bus_up if state.occupied is None else state.bus_up & ~state.occupied


def load_shares(net: Network, state: State) -> np.ndarray:
    return net.load_share if state.load_share is None else state.load_share


def separation_mask(net: Network, pairs: set[frozenset[str]]) -> np.ndarray:
    """Branches whose two ends lie in a pair of separated countries."""
    mask = np.zeros(len(net.br_id), dtype=bool)
    if not pairs:
        return mask
    for i in range(len(net.br_id)):
        a = net.bus_country[net.br_from[i]]
        b = net.bus_country[net.br_to[i]]
        if a and b and a != b and frozenset({a, b}) in pairs:
            mask[i] = True
    return mask


@dataclass
class Solution:
    unserved_mw: float
    demand_mw: float
    served_mw: float
    generation_mw: float
    available_mw: float
    islands: int
    tripped: list[int]
    flows: np.ndarray
    loading: np.ndarray
    bus_supplied: np.ndarray  # fully served
    bus_ratio: np.ndarray  # served share of each bus's demand (1 where there is none)
    gen_dispatch: np.ndarray
    by_country: dict[str, dict[str, float]]
    iterations: int


def _available(net: Network, state: State, moment: datetime, *, committed: bool = True) -> np.ndarray:
    """What each generator can deliver now: installed × availability × damage, and — unless
    ``committed`` is False — no more than the capacity of its running units."""
    avail = np.empty(len(net.gen_pmax))
    sun = solar_factor(moment)
    for i, fuel in enumerate(net.gen_fuel):
        factor = sun if fuel == "solar" else AVAILABILITY.get(fuel or "", DEFAULT_AVAILABILITY)
        country = net.bus_country[net.gen_bus[i]]
        factor *= state.fuel_factor.get(f"{fuel}@{country}", state.fuel_factor.get(fuel or "", 1.0))
        avail[i] = state.gen_capacity[i] * factor * state.gen_factor[i]
    if committed and state.committed is not None:
        avail = np.minimum(avail, state.committed)
    return avail


# Unit commitment: must-run and cheapest first, a spinning reserve on top of demand.
MERIT_ORDER = ["nuclear", "hydro", "wind", "solar", "geothermal", "biomass", "waste", "coal", "gas", "oil", None, "storage"]
SPINNING_RESERVE = 0.08
# How fast units that are not running can be brought in, share of capacity per hour.
RAMP_UP = {
    "hydro": 1.0, "storage": 1.0, "wind": 1.0, "solar": 1.0, "gas": 0.5, "oil": 0.5,
    "biomass": 0.2, "waste": 0.2, "coal": 0.15, "geothermal": 0.1, "nuclear": 0.03,
}
DEFAULT_RAMP_UP = 0.3


def commitment_target(net: Network, state: State, moment: datetime) -> np.ndarray:
    """Running capacity each generator should have: per country, merit order up to demand
    plus reserve, net of the unmodelled supply."""
    avail = _available(net, state, moment, committed=False)
    if state.occupied is not None:
        avail = np.where(state.occupied[net.gen_bus], 0.0, avail)
    shares = load_shares(net, state)
    target = np.zeros(len(net.gen_pmax))
    rank = {fuel: k for k, fuel in enumerate(MERIT_ORDER)}
    gen_country = [net.bus_country[b] for b in net.gen_bus]
    load_country = np.array(net.load_country)
    for country in net.countries:
        # Units are committed for the day's peak: the planned load curve needs no ramping.
        demand = peak_demand_mw(country, moment) * state.demand_factor.get(country, 1.0)
        covered = 0.0
        if state.balancing_ratio is not None:
            mine = load_country == country
            covered = float((state.balancing_ratio[net.load_bus[mine]] * shares[mine]).sum())
        need = max(0.0, demand * (1 + SPINNING_RESERVE - covered))
        order = sorted(
            (i for i, c in enumerate(gen_country) if c == country),
            key=lambda i: (rank.get(net.gen_fuel[i], len(MERIT_ORDER)), -avail[i]),
        )
        for i in order:
            if need <= 0:
                break
            take = min(avail[i], need)
            target[i] = take
            need -= take
    return target


def commit(net: Network, state: State, moment: datetime, hours: float | None) -> None:
    """Move running capacity towards the target: at once on the first call (``hours`` None),
    afterwards limited by ramp rates; units lost to damage stop at once."""
    target = commitment_target(net, state, moment)
    if hours is None or state.committed is None:
        state.committed = target
        return
    ramp = np.array([RAMP_UP.get(f or "", DEFAULT_RAMP_UP) for f in net.gen_fuel])
    rising = np.minimum(target, state.committed + ramp * state.gen_capacity * max(hours, 0.0))
    state.committed = np.where(target > state.committed, rising, target)


def solve(
    net: Network, state: State, moment: datetime, *, trip_threshold: float = 1.25, max_iterations: int = 30
) -> Solution:
    """Steady state at ``moment`` with protection cascade; trips are written into ``state``."""
    n = len(net.bus_id)
    demand_by_country = {
        c: demand_mw(c, moment) * state.demand_factor.get(c, 1.0) for c in net.countries
    }
    bus_demand = np.zeros(n)
    bus_up = live_buses(state)
    load_mw = np.array(
        [demand_by_country.get(c, 0.0) * s for c, s in zip(net.load_country, load_shares(net, state), strict=True)]
    )
    np.add.at(bus_demand, net.load_bus, load_mw)
    avail = _available(net, state, moment)
    # Unmodelled generation and imports that keep the undisturbed base case balanced: a share
    # of each bus's own demand (see secure_base_case).
    balancing = bus_demand * state.balancing_ratio if state.balancing_ratio is not None else np.zeros(n)
    separated = separation_mask(net, state.separated)
    tripped_now: list[int] = []
    iterations = 0
    rating = state.rating if state.rating is not None else net.br_rating
    while True:
        iterations += 1
        active = state.br_up & ~state.br_tripped & ~separated
        active &= bus_up[net.br_from] & bus_up[net.br_to]
        f, t = net.br_from[active], net.br_to[active]
        graph = coo_matrix((np.ones(len(f)), (f, t)), shape=(n, n))
        count, labels = connected_components(graph, directed=False)
        gen_bus_avail = np.zeros(n)
        live_gen = bus_up[net.gen_bus]
        np.add.at(gen_bus_avail, net.gen_bus[live_gen], avail[live_gen])
        gen_bus_avail += balancing * bus_up
        island_avail = np.bincount(labels, weights=gen_bus_avail * bus_up, minlength=count)
        island_demand = np.bincount(labels, weights=bus_demand * bus_up, minlength=count)
        with np.errstate(divide="ignore", invalid="ignore"):
            served_ratio = np.where(island_demand > 0, np.minimum(1.0, island_avail / island_demand), 1.0)
            dispatch_ratio = np.where(island_avail > 0, np.minimum(1.0, island_demand / island_avail), 0.0)
        bus_served = bus_demand * served_ratio[labels] * bus_up
        bus_gen = gen_bus_avail * dispatch_ratio[labels] * bus_up
        injection = (bus_gen - bus_served) / BASE_MVA
        theta = np.zeros(n)
        # Solve each island with load or generation; slack = bus with most generation.
        for island in range(count):
            members = np.flatnonzero(labels == island)
            if len(members) < 2 or (island_avail[island] <= 0 and island_demand[island] <= 0):
                continue
            slack = members[np.argmax(gen_bus_avail[members])]
            others = members[members != slack]
            position = -np.ones(n, dtype=np.int64)
            position[others] = np.arange(len(others))
            in_island = active & (labels[net.br_from] == island)
            fi, ti = net.br_from[in_island], net.br_to[in_island]
            b = 1.0 / net.br_x[in_island]
            rows, cols, vals = [], [], []
            for a_, c_, v in ((fi, fi, b), (ti, ti, b), (fi, ti, -b), (ti, fi, -b)):
                pa, pc = position[a_], position[c_]
                keep = (pa >= 0) & (pc >= 0)
                rows.append(pa[keep])
                cols.append(pc[keep])
                vals.append(v[keep])
            matrix = coo_matrix(
                (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                shape=(len(others), len(others)),
            ).tocsc()
            try:
                theta[others] = spsolve(matrix, injection[others])
            except Exception:  # noqa: BLE001 - singular island: leave flows at zero
                continue
        flows = np.zeros(len(net.br_id))
        flows[active] = (theta[net.br_from[active]] - theta[net.br_to[active]]) / net.br_x[active] * BASE_MVA
        loading = np.abs(flows) / np.maximum(rating, 1.0)
        over = np.flatnonzero(active & (loading > trip_threshold))
        if not len(over) or iterations >= max_iterations:
            break
        # Trip the most loaded first, as protection with the shortest delay would.
        worst = over[np.argsort(-loading[over])][: max(1, len(over) // 3)]
        state.br_tripped[worst] = True
        tripped_now.extend(int(i) for i in worst)

    gen_dispatch = np.zeros(len(net.gen_pmax))
    gen_ratio = dispatch_ratio[labels[net.gen_bus]] * bus_up[net.gen_bus]
    gen_dispatch[:] = avail * gen_ratio
    by_country: dict[str, dict[str, float]] = defaultdict(lambda: {"demand_mw": 0.0, "served_mw": 0.0})
    for k, c in enumerate(net.load_country):
        bus = net.load_bus[k]
        share = load_mw[k]
        ratio = served_ratio[labels[bus]] if bus_up[bus] else 0.0
        by_country[c]["demand_mw"] += share
        by_country[c]["served_mw"] += share * ratio
    demand_total = float(bus_demand.sum())
    served_total = float(bus_served.sum())
    bus_ratio = np.where(bus_up, served_ratio[labels], 0.0)
    supplied = bus_ratio > 0.999
    energised = int(np.unique(labels[(island_demand[labels] > 0) & (island_avail[labels] > 0)]).size)
    return Solution(
        unserved_mw=demand_total - served_total,
        demand_mw=demand_total,
        served_mw=served_total,
        generation_mw=float(gen_dispatch.sum() + (balancing * dispatch_ratio[labels] * bus_up).sum()),
        available_mw=float(island_avail.sum()),
        islands=energised,
        tripped=tripped_now,
        flows=flows,
        loading=loading,
        bus_supplied=supplied,
        bus_ratio=bus_ratio,
        gen_dispatch=gen_dispatch,
        by_country={c: {k: round(v, 1) for k, v in d.items()} for c, d in by_country.items()},
        iterations=iterations,
    )


def secure_base_case(net: Network, state: State, moment: datetime) -> dict:
    """Make the undisturbed base case balanced and N-0 secure.

    * A country whose modelled generation does not cover its demand (capacity missing in
      OSM, imports, small plants) gets unmodelled supply spread over its loads.
    * Loads left in islands without any generation (parts of the network OSM does not
      connect) get local unmodelled supply, so data gaps do not show up as outages.
    * Ratings the base flows already exceed are lifted to keep a 10% margin.
    """
    n = len(net.bus_id)
    ratio = np.zeros(n)
    avail = _available(net, state, moment, committed=False)
    if state.occupied is not None:
        avail = np.where(state.occupied[net.gen_bus], 0.0, avail)
    shares = load_shares(net, state)
    report: dict = {"balancing_mw": {}, "isolated_load_mw": 0, "ratings_raised": 0}
    load_country = np.array(net.load_country)
    for country in net.countries:
        gens = [i for i in range(len(net.gen_pmax)) if net.bus_country[net.gen_bus[i]] == country]
        have = float(avail[gens].sum()) if gens else 0.0
        need = demand_mw(country, moment) * state.demand_factor.get(country, 1.0)
        gap = need * 1.05 - have
        if gap > 0 and need > 0:
            ratio[net.load_bus[load_country == country]] = gap / need
            report["balancing_mw"][country] = round(gap)
    state.balancing_ratio = ratio
    commit(net, state, moment, None)
    first = solve(net, state, moment, trip_threshold=float("inf"))
    isolated = ~first.bus_supplied & live_buses(state)
    if isolated.any():
        demand = np.zeros(n)
        demand_by_country = {c: demand_mw(c, moment) for c in net.countries}
        np.add.at(
            demand,
            net.load_bus,
            np.array([demand_by_country.get(c, 0.0) * s for c, s in zip(net.load_country, shares, strict=True)]),
        )
        ratio[isolated] = np.maximum(ratio[isolated], 1.05)
        report["isolated_load_mw"] = round(float(demand[isolated].sum()))
        state.balancing_ratio = ratio
        commit(net, state, moment, None)
    solution = solve(net, state, moment, trip_threshold=float("inf"))
    over = solution.loading > 0.9
    state.rating = state.rating.copy()
    state.rating[over] = np.abs(solution.flows[over]) / 0.9
    report["ratings_raised"] = int(over.sum())
    report["base_unserved_mw"] = round(solution.unserved_mw)
    return report


def adapt_to_losses(net: Network, state: State, moment: datetime) -> dict:
    """After long-standing losses (in force before the start) the system has adapted: units
    are re-committed and the routing of flows was reinforced — but no supply is added, so a
    standing deficit stays visible."""
    commit(net, state, moment, None)
    solution = solve(net, state, moment, trip_threshold=float("inf"))
    over = solution.loading > 0.9
    state.rating = state.rating.copy()
    state.rating[over] = np.abs(solution.flows[over]) / 0.9
    return {"ratings_raised_after_losses": int(over.sum()), "standing_unserved_mw": round(solution.unserved_mw)}
