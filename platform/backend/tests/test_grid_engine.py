"""Cascade engine and topology contraction on small synthetic networks (no database)."""

from datetime import UTC, date, datetime

import numpy as np
import pytest

from app.grid.engine import Network, State, demand_mw, secure_base_case, solve
from app.grid.runner import Timeline, apply, check_expected, frame_times, simulate
from app.grid.topology import _contract, line_parameters

MOMENT = datetime(2024, 1, 15, 17, 0, tzinfo=UTC)


def network(ratings=(5000.0, 5000.0, 5000.0, 5000.0), gens=((0, 2000.0, "nuclear"),)) -> Network:
    """Ring of four 330 kV buses: 0-1-2-3-0, one plant at bus 0, loads at 1, 2 and 3.

    Assets: buses 101..104 (substations), branches 201..204 (lines), plant 301.
    """
    net = Network(
        snapshot_id=1,
        as_of=date(2024, 1, 1),
        bus_id=np.array([1, 2, 3, 4]),
        bus_asset=np.array([101, 102, 103, 104]),
        bus_country=["UA"] * 4,
        bus_kv=np.array([330.0] * 4),
        bus_lonlat=np.zeros((4, 2)),
        br_id=np.array([11, 12, 13, 14]),
        br_from=np.array([0, 1, 2, 3]),
        br_to=np.array([1, 2, 3, 0]),
        br_x=np.array([0.01, 0.01, 0.01, 0.01]),
        br_rating=np.array(ratings),
        br_kind=["line"] * 4,
        br_kv=np.array([330.0] * 4),
        br_assets=[[201], [202], [203], [204]],
        gen_bus=np.array([g[0] for g in gens]),
        gen_pmax=np.array([g[1] for g in gens]),
        gen_fuel=[g[2] for g in gens],
        gen_asset=np.array([301 + i for i in range(len(gens))]),
        load_bus=np.array([1, 2, 3]),
        load_share=np.array([0.3, 0.4, 0.3]),
        load_country=["UA"] * 3,
    )
    for i, a in enumerate(net.bus_asset):
        net.asset_buses[int(a)] = [i]
    for i, assets in enumerate(net.br_assets):
        net.asset_branches[assets[0]] = [i]
    for i, a in enumerate(net.gen_asset):
        net.asset_gens[int(a)] = [i]
    return net


def scaled(net: Network, state: State, share: float = 0.05) -> None:
    """Shrink UA demand to `share` of the national figure so one plant can carry it."""
    state.demand_factor["UA"] = share


def test_balanced_ring_flows_conserve_power():
    net = network()
    state = State.initial(net)
    scaled(net, state)
    solution = solve(net, state, MOMENT)
    demand = demand_mw("UA", MOMENT) * 0.05
    assert solution.unserved_mw == pytest.approx(0, abs=1e-6)
    assert solution.demand_mw == pytest.approx(demand)
    # Bus 0 sends everything out over branches 0 (0→1) and 3 (3→0, reversed).
    out_of_plant = solution.flows[0] - solution.flows[3]
    assert out_of_plant == pytest.approx(demand, rel=1e-6)
    assert solution.islands == 1


def test_losing_both_lines_of_the_plant_blacks_out_the_ring():
    net = network()
    state = State.initial(net)
    scaled(net, state)
    apply(net, state, {"type": "outage", "targets": [201, 204]})
    solution = solve(net, state, MOMENT)
    assert solution.unserved_mw == pytest.approx(solution.demand_mw)
    assert not solution.bus_supplied[1:].any()


def test_substation_outage_islands_only_its_load():
    net = network()
    state = State.initial(net)
    scaled(net, state)
    apply(net, state, {"type": "outage", "targets": [103]})  # bus 2, 40% of load
    solution = solve(net, state, MOMENT)
    assert solution.unserved_mw == pytest.approx(0.4 * solution.demand_mw)
    apply(net, state, {"type": "restore", "targets": [103]})
    assert solve(net, state, MOMENT).unserved_mw == pytest.approx(0, abs=1e-6)


def test_plant_loss_sheds_load_in_proportion():
    net = network(gens=((0, 2000.0, "nuclear"), (2, 2000.0, "nuclear")))
    state = State.initial(net)
    state.demand_factor["UA"] = 2 * 0.85 * 2000 / demand_mw("UA", MOMENT)  # exactly both plants
    assert solve(net, state, MOMENT).unserved_mw == pytest.approx(0, abs=1e-3)
    apply(net, state, {"type": "outage", "targets": [302], "capacity_share": 1.0})
    solution = solve(net, state, MOMENT)
    assert solution.served_mw == pytest.approx(0.85 * 2000, rel=1e-6)
    assert solution.unserved_mw == pytest.approx(0.85 * 2000, rel=1e-6)


def test_overload_trips_cascade_after_a_line_loss():
    # Base flows fit; after losing 0→1 everything goes the long way round and trips.
    net = network(ratings=(400.0, 400.0, 400.0, 400.0))
    state = State.initial(net)
    state.demand_factor["UA"] = 600 / demand_mw("UA", MOMENT)
    base = solve(net, state, MOMENT)
    assert not base.tripped
    apply(net, state, {"type": "outage", "targets": [201]})
    after = solve(net, state, MOMENT, trip_threshold=1.0)
    assert after.tripped, "the remaining path is overloaded and protection trips it"
    assert after.unserved_mw > 0


def test_secure_base_case_lifts_ratings_and_balances_country():
    net = network(ratings=(10.0, 10.0, 10.0, 10.0), gens=((0, 100.0, "gas"),))
    state = State.initial(net)
    report = secure_base_case(net, state, MOMENT)
    assert report["balancing_mw"]["UA"] > 0, "a small plant cannot carry a country"
    assert report["ratings_raised"] > 0
    solution = solve(net, state, MOMENT)
    assert solution.unserved_mw == pytest.approx(0, abs=1e-3)
    assert not solution.tripped


def test_timeline_is_deterministic_per_seed_and_schedules_repairs():
    net = network()
    scenario = {
        "start_at": "2024-01-15T00:00:00Z",
        "end_at": "2024-01-16T00:00:00Z",
        "events": [
            {"at": "2024-01-15T10:00:00Z", "type": "rule_strike", "payload": {"selector": {"kind": "substation", "count": 2}, "repair_hours": [2, 4, 6]}},
        ],
    }
    first = Timeline(net, scenario, [], np.random.default_rng(7))
    second = Timeline(net, scenario, [], np.random.default_rng(7))
    assert [a[2]["targets"] for a in first.actions] == [a[2]["targets"] for a in second.actions]
    kinds = [a[2]["type"] for a in first.actions]
    assert kinds.count("outage") == 1 and kinds.count("restore") == 2


def test_simulation_records_frames_and_energy_not_served():
    net = network()
    scenario = {
        "start_at": "2024-01-15T00:00:00Z",
        "end_at": "2024-01-15T06:00:00Z",
        "step_hours": 1,
        "events": [{"at": "2024-01-15T02:00:00Z", "type": "strike", "targets": [103], "payload": {"repair_hours": 2}}],
    }
    result = simulate(net, scenario, [], seed=1)
    frames = result["frames"]
    assert [f["at"].hour for f in frames] == [0, 1, 2, 3, 4, 5, 6]
    assert frames[2]["metrics"]["unserved_mw"] > 0
    assert frames[2]["state"]["bus_out"] == [2]
    assert frames[4]["metrics"]["unserved_mw"] == 0, "repaired after two hours"
    assert result["ens_mwh"] > 0
    checks = check_expected(frames, {"checks": [{"metric": "unserved_mw", "at": "2024-01-15T02:00:00Z", "value": 1, "op": "min"}]})
    assert checks[0]["ok"]


def test_frame_times_cap_and_include_events():
    start = datetime(2022, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    event = datetime(2023, 6, 6, 3, tzinfo=UTC)
    times = frame_times(start, end, 1, [event])
    assert len(times) <= 400 and event in times and times[0] == start and times[-1] == end


def test_contract_chains_ways_between_stations_and_prunes_dangling_ends():
    s1, s2 = ("S", 1), ("S", 2)
    p = [("P", i) for i in range(5)]
    seg = lambda i, a, b: {"id": i, "a": a, "b": b, "length_km": 1.0, "kv": 330.0, "circuits": 1, "cable": False, "country": "UA"}  # noqa: E731
    segments = [
        seg(1, s1, p[0]), seg(2, p[0], p[1]), seg(3, p[1], s2),  # one line in three ways
        seg(4, p[1], p[2]), seg(5, p[2], p[3]),  # a spur that ends nowhere
    ]
    chains = _contract(segments, {s1, s2})
    assert len(chains) == 2, "the T-junction at p1 splits the line; the spur is pruned"
    ways = sorted(sorted(c.ways) for _, _, c in chains)
    assert ways == [[1, 2], [3]]


def test_line_parameters_scale_with_voltage_length_and_circuits():
    x1, r1 = line_parameters(330, 100, 1, False)
    x2, r2 = line_parameters(330, 100, 2, False)
    assert x2 == pytest.approx(x1 / 2) and r2 == pytest.approx(2 * r1)
    x750, r750 = line_parameters(750, 100, 1, False)
    assert x750 < x1 and r750 > r1


def test_sudden_loss_is_covered_only_as_fast_as_units_start():
    # Nuclear carries the load; a gas plant stands by. Losing the nuclear plant leaves a
    # deficit at once that shrinks as gas units start (50% of capacity per hour).
    net = network(gens=((0, 2000.0, "nuclear"), (2, 4000.0, "gas")))
    scenario = {
        "start_at": "2024-01-15T17:00:00Z",
        "end_at": "2024-01-15T20:00:00Z",
        "step_hours": 1,
        "events": [{"at": "2024-01-15T18:00:00Z", "type": "strike", "targets": [301]}],
    }
    state_factor = 1500 / demand_mw("UA", MOMENT)
    scenario["events"].insert(0, {"at": "2024-01-15T17:00:00Z", "type": "demand", "payload": {"countries": ["UA"], "factor": state_factor}})
    frames = simulate(net, scenario, [], seed=1)["frames"]
    unserved = [f["metrics"]["unserved_mw"] for f in frames]
    assert unserved[0] == 0
    assert unserved[1] > 0, "gas was not running when the nuclear plant was lost"
    assert unserved[-1] == 0, "gas has started within two hours"
