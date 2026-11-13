"""Scenario runs on a real network: single runs, Monte Carlo ensembles and N-1 screening.

A scenario is a list of timed events against real assets (ids of ``odbl.grid_assets``)
plus rules that pick assets (for incidents whose exact targets are not public). Dated
overrides of assets (destroyed, occupied, capacity…) are part of every run.

Event types:

* ``outage``   — targets go out (substation: its buses; line: its branches; plant: its
  capacity, or ``capacity_share`` of it); optional ``probability`` per target and
  ``repair_hours`` (a number or ``[min, mode, max]``) after which they return;
* ``strike``   — the same as outage, named for attacks;
* ``restore``  — targets return;
* ``rule_strike`` — like strike, targets chosen by ``selector`` (kind, voltage, fuel,
  countries, count) with the run's random generator;
* ``demand``   — demand factor for ``countries`` (cold spell, heat wave);
* ``fuel``     — availability factor for a ``fuel`` (gas shortage, low water);
* ``separate`` / ``resync`` — open or close the branches between ``countries`` (pairs).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
from sqlalchemy import Engine, text

from app.grid.engine import (
    SEPARATIONS,
    Network,
    State,
    adapt_to_losses,
    commit,
    load_network,
    secure_base_case,
    solve,
)
from app.grid.topology import SnapshotParams, build_snapshot

MAX_FRAMES = 400
CONDITIONS = {"demand", "fuel", "separate", "resync"}
OUT_STATUSES = {"destroyed", "damaged", "occupied", "disused", "abandoned", "demolished"}


def _moment(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


@dataclass
class Applied:
    at: datetime
    kind: str
    label: str
    targets: list[int]
    source_url: str | None = None
    event_id: str | None = None
    origin: str = "scenario"

    def as_dict(self) -> dict:
        return {
            "at": self.at.isoformat(),
            "type": self.kind,
            "label": self.label,
            "targets": self.targets,
            "source_url": self.source_url,
            "event_id": self.event_id,
            "origin": self.origin,
        }


def _sample_repair(value, rng: np.random.Generator) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    low, mode, high = (list(value) + [None, None, None])[:3]
    if high is None:
        return float(low)
    return float(rng.triangular(low, mode if mode is not None else (low + high) / 2, high))


class Timeline:
    """Expands scenario events into concrete actions with the run's random generator."""

    def __init__(self, net: Network, scenario: dict, overrides: list[dict], rng: np.random.Generator):
        self.net = net
        self.rng = rng
        self.actions: list[tuple[datetime, int, dict]] = []
        self.counter = 0
        start = _moment(scenario["start_at"])
        for event in scenario.get("events", []):
            self._add(_moment(event["at"]), event)
        for override in overrides:
            self._override(override, start)
        self.actions.sort(key=lambda item: (item[0], item[1]))
        self.position = 0

    def _push(self, at: datetime, action: dict) -> None:
        self.counter += 1
        self.actions.append((at, self.counter, action))

    def _override(self, override: dict, start: datetime) -> None:
        begin = override.get("valid_from")
        end = override.get("valid_to")
        at = max(start, datetime.combine(begin, datetime.min.time(), UTC)) if begin else start
        field = override["field"]
        value = override["value"]
        label = override.get("note") or f"Правка: {field} = {value}"
        # A correction in force before the start is the normal state of the system, not a shock.
        prior = bool(begin) and datetime.combine(begin, datetime.min.time(), UTC) < start
        base = {"targets": [override["asset_id"]], "source_url": override.get("source_url"), "label": label, "origin": "override", "prior": prior}
        if field == "status":
            kind = "outage" if value in OUT_STATUSES else "restore"
            self._push(at, {**base, "type": kind})
            if end and kind == "outage":
                self._push(datetime.combine(end, datetime.min.time(), UTC), {**base, "type": "restore", "label": f"Кінець правки: {field}"})
        elif field in {"capacity_mw", "availability"}:
            self._push(at, {**base, "type": "capacity" if field == "capacity_mw" else "availability", "value": float(value)})

    def _add(self, at: datetime, event: dict) -> None:
        kind = event.get("type", "outage")
        payload = event.get("payload") or {}
        base = {
            "label": event.get("label") or kind,
            "source_url": event.get("source_url"),
            "event_id": event.get("id"),
        }
        if kind == "rule_strike":
            targets = self.select(payload.get("selector") or {})
            kind = "strike"
        else:
            targets = [int(t) for t in event.get("targets") or []]
        if kind in {"outage", "strike"}:
            probability = float(payload.get("probability", 1.0))
            hit = [t for t in targets if probability >= 1 or self.rng.random() < probability]
            share = float(payload.get("capacity_share", 1.0))
            self._push(at, {**base, "type": "outage", "targets": hit, "capacity_share": share})
            repair = payload.get("repair_hours")
            for target in hit:
                hours = _sample_repair(repair, self.rng)
                if hours is not None and hours > 0:
                    self._push(
                        at + timedelta(hours=hours),
                        {"type": "restore", "targets": [target], "label": "Ремонт завершено", "origin": "repair", "event_id": event.get("id"), "capacity_share": share},
                    )
        elif kind == "restore":
            self._push(at, {**base, "type": "restore", "targets": targets})
        elif kind in {"demand", "fuel", "separate", "resync"}:
            self._push(at, {**base, "type": kind, **payload, "targets": targets})
        else:
            raise ValueError(f"невідомий тип події: {kind}")

    def select(self, selector: dict) -> list[int]:
        """Assets matching a rule, a random sample of ``count`` of them (deterministic per seed)."""
        kind = selector.get("kind", "substation")
        countries = {c.upper() for c in selector.get("countries") or []}
        min_kv = float(selector.get("min_kv", 0))
        net = self.net
        if kind == "plant":
            fuels = set(selector.get("fuels") or [])
            min_mw = float(selector.get("min_mw", 0))
            pool = sorted(
                {
                    int(net.gen_asset[i])
                    for i in range(len(net.gen_asset))
                    if net.gen_asset[i] >= 0
                    and (not fuels or net.gen_fuel[i] in fuels)
                    and net.gen_pmax[i] >= min_mw
                    and (not countries or net.bus_country[net.gen_bus[i]] in countries)
                }
            )
        elif kind == "line":
            pool = sorted(
                {
                    int(a)
                    for i, assets in enumerate(net.br_assets)
                    if net.br_kind[i] != "transformer" and net.br_kv[i] >= min_kv
                    and (not countries or net.bus_country[net.br_from[i]] in countries)
                    for a in assets[:1]
                }
            )
        else:
            pool = sorted(
                {
                    int(net.bus_asset[i])
                    for i in range(len(net.bus_asset))
                    if net.bus_asset[i] >= 0 and net.bus_kv[i] >= min_kv
                    and (not countries or net.bus_country[i] in countries)
                }
            )
        count = min(int(selector.get("count", 1)), len(pool))
        if count <= 0:
            return []
        return sorted(int(x) for x in self.rng.choice(pool, size=count, replace=False))

    def due(self, moment: datetime) -> list[dict]:
        actions = []
        while self.position < len(self.actions) and self.actions[self.position][0] <= moment:
            at, _, action = self.actions[self.position]
            actions.append({**action, "at": at})
            self.position += 1
        return actions

    def event_times(self) -> list[datetime]:
        return sorted({at for at, _, action in self.actions if action.get("origin") != "repair"})


def apply(net: Network, state: State, action: dict) -> None:
    kind = action["type"]
    targets = action.get("targets") or []
    if kind in {"outage", "restore"}:
        up = kind == "restore"
        share = float(action.get("capacity_share", 1.0))
        for asset in targets:
            for b in net.asset_buses.get(asset, []):
                if not net.asset_gens.get(asset):
                    state.bus_up[b] = up
            for br in net.asset_branches.get(asset, []):
                state.br_up[br] = up
                if up:
                    state.br_tripped[br] = False
            for g in net.asset_gens.get(asset, []):
                state.gen_factor[g] = min(1.0, state.gen_factor[g] + share) if up else max(0.0, state.gen_factor[g] - share)
        if kind == "restore":
            # Protection trips around restored assets are reset by operators.
            state.br_tripped[:] = False
    elif kind == "capacity":
        for asset in targets:
            for g in net.asset_gens.get(asset, []):
                state.gen_capacity[g] = float(action["value"])
    elif kind == "availability":
        for asset in targets:
            for g in net.asset_gens.get(asset, []):
                state.gen_factor[g] = max(0.0, min(1.0, float(action["value"])))
    elif kind == "demand":
        for country in action.get("countries") or net.countries:
            state.demand_factor[country.upper()] = float(action.get("factor", 1.0))
    elif kind == "fuel":
        factor = float(action.get("factor", 1.0))
        fuels = action.get("fuels") or [action["fuel"]]
        countries = [c.upper() for c in action.get("countries") or []]
        for fuel in fuels:
            for key in ([f"{fuel}@{c}" for c in countries] if countries else [fuel]):
                state.fuel_factor[key] = factor
    elif kind in {"separate", "resync"}:
        countries = [c.upper() for c in action.get("countries") or []]
        pairs = {frozenset({a, b}) for a in countries for b in countries if a != b}
        if kind == "separate":
            state.separated |= pairs
        else:
            state.separated -= pairs


def frame_times(start: datetime, end: datetime, step_hours: float, events: list[datetime]) -> list[datetime]:
    step = max(step_hours, 0.25)
    span = (end - start).total_seconds() / 3600
    while span / step > MAX_FRAMES - len(events):
        step *= 2
    times = {start, end}
    k = 0
    while True:
        moment = start + timedelta(hours=k * step)
        if moment > end:
            break
        times.add(moment)
        k += 1
    times |= {e for e in events if start <= e <= end}
    return sorted(times)


def _base_separations(as_of: date) -> set[frozenset[str]]:
    return {pair for pair, since, _ in SEPARATIONS if as_of >= since}


def simulate(
    net: Network,
    scenario: dict,
    overrides: list[dict],
    *,
    seed: int,
    trip_threshold: float = 1.25,
    record: bool = True,
) -> dict:
    rng = np.random.default_rng(seed)
    start, end = _moment(scenario["start_at"]), _moment(scenario["end_at"])
    timeline = Timeline(net, scenario, overrides, rng)
    state = State.initial(net)
    state.separated = _base_separations(start.date())
    # Balance the undisturbed system under normal conditions first. Everything in force at
    # the start — damage, occupation, demand and fuel conditions — is applied afterwards, so
    # unmodelled supply never covers it and a standing deficit stays visible.
    base = secure_base_case(net, state, start)
    initial = timeline.due(start)
    for action in initial:
        apply(net, state, action)
    if initial:
        base.update(adapt_to_losses(net, state, start))
    times = frame_times(start, end, float(scenario.get("step_hours", 1.0)), timeline.event_times())
    frames: list[dict] = []
    previous_time = start
    previous_unserved = 0.0
    previous_share: float | None = None
    peak = {"unserved_mw": 0.0, "at": start.isoformat()}
    for sequence, moment in enumerate(times):
        actions = timeline.due(moment)
        hours = (moment - previous_time).total_seconds() / 3600
        if sequence:
            # Units start up over the interval before this moment, not after its events.
            commit(net, state, moment, hours)
            # Operators re-close lines tripped by protection after a couple of hours; the
            # solve trips them again if they are still overloaded.
            if hours >= 2:
                state.br_tripped[:] = False
        for action in actions:
            apply(net, state, action)
        if not sequence:
            actions = initial + actions
        # Units lost now stop at once; there is no time yet to start others. Losses already
        # in place at the start happened long before: the start is committed around them.
        commit(net, state, moment, 0.0 if sequence else None)
        solution = solve(net, state, moment, trip_threshold=trip_threshold)
        state.ens_mwh += previous_unserved * hours
        share = solution.unserved_mw / solution.demand_mw if solution.demand_mw else 0.0
        # Frequency dip proxy: only a sudden new deficit dips; a standing one is handled by
        # emergency schedules and the frequency is back at 50 Hz.
        # The planned daily rise of demand under a standing deficit is met by schedules, not
        # by a dip: only losses (events, protection trips) count.
        sudden = solution.tripped or any(a["type"] in {"outage", "strike", "separate", "fuel"} for a in actions)
        jump = share - (share if previous_share is None else previous_share)
        frequency = 50.0 - min(2.5, 10 * jump) if sudden and jump > 0.005 else 50.0
        previous_unserved, previous_time, previous_share = solution.unserved_mw, moment, share
        if solution.unserved_mw > peak["unserved_mw"]:
            peak = {"unserved_mw": round(solution.unserved_mw), "at": moment.isoformat()}
        metrics = {
            "demand_mw": round(solution.demand_mw),
            "served_mw": round(solution.served_mw),
            "unserved_mw": round(solution.unserved_mw),
            "unserved_share": round(share, 4),
            "generation_mw": round(solution.generation_mw),
            "available_mw": round(solution.available_mw),
            "islands": solution.islands,
            "frequency_hz": round(frequency, 2),
            "tripped": int(state.br_tripped.sum()),
            "tripped_now": len(solution.tripped),
            "out_branches": int((~state.br_up).sum()),
            "out_buses": int((~state.bus_up).sum()),
            "overloaded": int((solution.loading > 1.0).sum()),
            "ens_mwh": round(state.ens_mwh),
            "by_country": solution.by_country,
        }
        frame = {"sequence": sequence, "at": moment, "metrics": metrics}
        if record:
            active = state.br_up & ~state.br_tripped
            load = np.where(active, np.round(solution.loading * 100), -1).astype(int)
            frame["state"] = {
                "load": load.tolist(),
                "br_out": np.flatnonzero(~state.br_up).tolist(),
                "br_trip": np.flatnonzero(state.br_tripped).tolist(),
                "bus_out": np.flatnonzero(~state.bus_up).tolist(),
                # Without any supply (an island without generation); partial shedding is a metric.
                "bus_dead": np.flatnonzero(state.bus_up & (solution.bus_ratio < 0.001)).tolist(),
                "gen_out": np.flatnonzero(state.gen_factor <= 0.001).tolist(),
                "trip_new": solution.tripped,
            }
            frame["events"] = [
                Applied(a["at"], a["type"], a.get("label", a["type"]), a.get("targets") or [], a.get("source_url"), a.get("event_id"), a.get("origin", "scenario")).as_dict()
                for a in actions
            ]
        frames.append(frame)
    return {"frames": frames, "base": base, "peak": peak, "ens_mwh": round(state.ens_mwh)}


def check_expected(frames: list[dict], expected: dict) -> list[dict]:
    """Model vs fact: every check compares a metric at a moment with a reported value."""
    results = []
    for check in expected.get("checks", []):
        at = _moment(check["at"]) if check.get("at") else None
        frame = frames[-1]
        if at is not None:
            frame = min(frames, key=lambda f: abs((f["at"] - at).total_seconds()))
        metric = check["metric"]
        value = frame["metrics"].get(metric)
        if check.get("country") and isinstance(frame["metrics"].get("by_country"), dict):
            data = frame["metrics"]["by_country"].get(check["country"], {})
            if metric == "unserved_mw":
                value = data.get("demand_mw", 0) - data.get("served_mw", 0)
        fact = float(check["value"])
        tolerance = float(check.get("tolerance", 0.3))
        op = check.get("op", "approx")
        if value is None:
            ok = False
        elif op == "min":
            ok = float(value) >= fact
        elif op == "max":
            ok = float(value) <= fact
        else:
            # Tolerance is relative to the reported value (an absolute one when it is zero).
            ok = abs(float(value) - fact) <= tolerance * (abs(fact) if fact else 1.0)
        results.append({**check, "model": value, "ok": bool(ok), "at_model": frame["at"].isoformat()})
    return results


# --- persistence ----------------------------------------------------------------------------


def resolve_targets(engine: Engine, scenario: dict) -> dict:
    """Fill ``targets`` of events that name assets by ``match`` rules instead of ids.

    A match rule is ``{"kind": "plant", "name": "%Запорізька АЕС%", "country": "UA"}``;
    ids differ between databases, names and kinds do not.
    """
    events = []
    with engine.connect() as connection:
        for event in scenario.get("events") or []:
            event = dict(event)
            matches = event.get("match") or []
            if matches:
                ids: list[int] = list(event.get("targets") or [])
                for rule in matches:
                    rows = connection.execute(
                        text(
                            "SELECT id FROM odbl.grid_assets WHERE kind = :kind "
                            "AND (coalesce(name, '') ILIKE ANY (ARRAY[:name, :alt]) "
                            "OR coalesce(name_en, '') ILIKE ANY (ARRAY[:name, :alt])) "
                            "AND (CAST(:country AS text) IS NULL OR country = :country) "
                            "ORDER BY coalesce(capacity_mw, 0) DESC, coalesce(max_voltage_kv, 0) DESC "
                            "LIMIT :limit"
                        ),
                        {
                            "kind": rule.get("kind", "plant"), "name": rule["name"],
                            "alt": rule.get("alt", rule["name"]), "country": rule.get("country"),
                            "limit": int(rule.get("limit", 1)),
                        },
                    ).scalars().all()
                    ids.extend(int(r) for r in rows)
                event["targets"] = sorted(set(ids))
            events.append(event)
    return {**scenario, "events": events}



def _scenario_row(engine: Engine, scenario_id: str) -> dict:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT * FROM odbl.grid_scenarios WHERE id = :id"), {"id": scenario_id}
        ).mappings().one()
    return dict(row)


def _overrides(engine: Engine) -> list[dict]:
    with engine.connect() as connection:
        return [
            dict(r)
            for r in connection.execute(
                text(
                    "SELECT asset_id, field, value, valid_from, valid_to, source_url, note "
                    "FROM odbl.grid_overrides ORDER BY id"
                )
            ).mappings()
        ]


def _progress(engine: Engine, run_id: str, progress: float, **fields) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    with engine.begin() as connection:
        connection.execute(
            text(f"UPDATE odbl.grid_runs SET progress = :p{', ' + sets if sets else ''} WHERE id = :id"),
            {"p": progress, "id": run_id, **fields},
        )


def _store_frames(engine: Engine, run_id: str, frames: list[dict]) -> None:
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM odbl.grid_run_frames WHERE run_id = :id"), {"id": run_id})
        connection.execute(
            text(
                "INSERT INTO odbl.grid_run_frames (run_id, sequence, at, metrics, state, events) "
                "VALUES (:run, :seq, :at, CAST(:metrics AS jsonb), CAST(:state AS jsonb), CAST(:events AS jsonb))"
            ),
            [
                {
                    "run": run_id, "seq": f["sequence"], "at": f["at"],
                    "metrics": json.dumps(f["metrics"]), "state": json.dumps(f.get("state", {})),
                    "events": json.dumps(f.get("events", [])),
                }
                for f in frames
            ],
        )


def _percentiles(values: list[float]) -> dict:
    array = np.array(values, dtype=float)
    return {
        "p10": round(float(np.percentile(array, 10)), 1),
        "p50": round(float(np.percentile(array, 50)), 1),
        "p90": round(float(np.percentile(array, 90)), 1),
    }


def execute_run(engine: Engine, run_id: str, *, log=print) -> None:
    """Run a queued scenario run (single or ensemble) and store frames and summary."""
    started = time.perf_counter()
    with engine.connect() as connection:
        run = dict(connection.execute(text("SELECT * FROM odbl.grid_runs WHERE id = :id"), {"id": run_id}).mappings().one())
    if run["status"] not in {"queued", "running"}:
        return
    _progress(engine, run_id, 0.01, status="running")
    scenario = resolve_targets(engine, _scenario_row(engine, run["scenario_id"]))
    params = SnapshotParams(countries=list(scenario["countries"]), as_of=scenario["as_of"])
    snapshot_id = build_snapshot(engine, params, log=log)
    _progress(engine, run_id, 0.1, snapshot_id=snapshot_id)
    if run["kind"] == "criticality":
        _criticality_run(engine, run_id, snapshot_id, scenario, started, log)
        return
    net = load_network(engine, snapshot_id)
    overrides = _overrides(engine)
    uncertainty = scenario.get("uncertainty") or {}
    threshold = float(uncertainty.get("trip_threshold", 1.25))
    members = max(1, int(run["members"])) if run["kind"] == "ensemble" else 1
    results = []
    for member in range(members):
        results.append(
            simulate(net, scenario, overrides, seed=int(run["seed"]) + member, trip_threshold=threshold, record=members == 1)
        )
        if members > 1 and (member % max(1, members // 20) == 0):
            _progress(engine, run_id, 0.1 + 0.8 * (member + 1) / members)
    if members == 1:
        chosen = results[0]
        summary_extra: dict = {}
    else:
        ens = [r["ens_mwh"] for r in results]
        median = float(np.median(ens))
        representative = int(np.argmin([abs(e - median) for e in ens]))
        chosen = simulate(net, scenario, overrides, seed=int(run["seed"]) + representative, trip_threshold=threshold)
        frame_count = len(chosen["frames"])
        bands = []
        for k in range(frame_count):
            values = [r["frames"][k]["metrics"] for r in results if k < len(r["frames"])]
            bands.append(
                {
                    "at": chosen["frames"][k]["at"].isoformat(),
                    "unserved_mw": _percentiles([v["unserved_mw"] for v in values]),
                    "ens_mwh": _percentiles([v["ens_mwh"] for v in values]),
                }
            )
        summary_extra = {
            "ensemble": {
                "members": members,
                "representative_seed": int(run["seed"]) + representative,
                "ens_mwh": _percentiles(ens),
                "peak_unserved_mw": _percentiles([r["peak"]["unserved_mw"] for r in results]),
                "bands": bands,
            }
        }
    frames = chosen["frames"]
    _store_frames(engine, run_id, frames)
    summary = {
        "snapshot_id": snapshot_id,
        "base": chosen["base"],
        "peak": chosen["peak"],
        "ens_mwh": chosen["ens_mwh"],
        "frames": len(frames),
        "checks": check_expected(frames, scenario.get("expected") or {}),
        "duration_s": round(time.perf_counter() - started, 2),
        **summary_extra,
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE odbl.grid_runs SET status = 'completed', progress = 1, summary = CAST(:s AS jsonb), "
                "snapshot_id = :snap, finished_at = now() WHERE id = :id"
            ),
            {"s": json.dumps(summary, default=str), "snap": snapshot_id, "id": run_id},
        )
    log(f"grid run {run_id}: {len(frames)} frames in {summary['duration_s']} s")


def _criticality_run(engine: Engine, run_id: str, snapshot_id: int, scenario: dict, started: float, log) -> None:
    moment = _moment(scenario["start_at"])
    ranked = criticality(engine, snapshot_id, moment, scenario=scenario, overrides=_overrides(engine))
    with engine.connect() as connection:
        names = {
            r.id: r
            for r in connection.execute(
                text("SELECT id, kind, name, max_voltage_kv, country FROM odbl.grid_assets WHERE id = ANY(:ids)"),
                {"ids": [r["asset_id"] for r in ranked]},
            )
        }
    for item in ranked:
        row = names.get(item["asset_id"])
        if row:
            item.update(kind=row.kind, name=row.name, max_voltage_kv=row.max_voltage_kv, country=row.country)
    summary = {"snapshot_id": snapshot_id, "criticality": ranked, "at": moment.isoformat(), "duration_s": round(time.perf_counter() - started, 2)}
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE odbl.grid_runs SET status = 'completed', progress = 1, summary = CAST(:s AS jsonb), "
                "snapshot_id = :snap, finished_at = now() WHERE id = :id"
            ),
            {"s": json.dumps(summary, default=str), "snap": snapshot_id, "id": run_id},
        )
    log(f"grid criticality {run_id}: {len(ranked)} assets ranked")


def criticality(
    engine: Engine,
    snapshot_id: int,
    moment: datetime,
    *,
    scenario: dict | None = None,
    overrides: list[dict] | None = None,
    min_kv: float = 220,
    limit: int = 60,
) -> list[dict]:
    """N-1 screening: unserved power after the loss of each substation and line (with cascade).

    The base is the state at ``moment``: everything the scenario and the overrides put in
    place by then (occupied or destroyed plants, demand) is applied first.
    """
    net = load_network(engine, snapshot_id)
    base_state = State.initial(net)
    base_state.separated = _base_separations(moment.date())
    if scenario is not None:
        timeline = Timeline(net, {**scenario, "start_at": moment}, overrides or [], np.random.default_rng(0))
        secure_base_case(net, base_state, moment)
        for action in timeline.due(moment):
            apply(net, base_state, action)
        adapt_to_losses(net, base_state, moment)
    else:
        secure_base_case(net, base_state, moment)
    already_out = {
        int(net.bus_asset[i]) for i in np.flatnonzero(~base_state.bus_up) if net.bus_asset[i] >= 0
    } | {int(net.gen_asset[i]) for i in np.flatnonzero(base_state.gen_factor <= 0.001)}
    base = solve(net, base_state, moment)
    candidates = sorted(
        {int(net.bus_asset[i]) for i in range(len(net.bus_asset)) if net.bus_asset[i] >= 0 and net.bus_kv[i] >= min_kv}
        | {int(assets[0]) for i, assets in enumerate(net.br_assets) if net.br_kind[i] != "transformer" and net.br_kv[i] >= max(min_kv, 300) and assets}
    )
    results = []
    for asset in candidates:
        if asset in already_out:
            continue
        state = State(
            bus_up=base_state.bus_up.copy(), br_up=base_state.br_up.copy(),
            br_tripped=base_state.br_tripped.copy(), gen_factor=base_state.gen_factor.copy(),
            gen_capacity=base_state.gen_capacity.copy(), separated=set(base_state.separated),
            rating=base_state.rating.copy(), balancing_ratio=base_state.balancing_ratio.copy(),
            committed=base_state.committed.copy(),
        )
        apply(net, state, {"type": "outage", "targets": [asset]})
        solution = solve(net, state, moment)
        results.append(
            {
                "asset_id": asset,
                "unserved_mw": round(max(0.0, solution.unserved_mw - base.unserved_mw)),
                "tripped": int(state.br_tripped.sum()),
                "islands": solution.islands,
            }
        )
    results.sort(key=lambda r: (-r["unserved_mw"], -r["tripped"]))
    return results[:limit]

