import json
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    LabCepRule, LabCheckpoint, LabComponentType, LabEdge, LabFlowSample, LabNode,
    LabResourcePool, LabResourceTransaction, LabRun, LabRunEvent, LabRunSample,
    LabScenario, LabScriptVersion, LabWorkflowInstance, LabWorkflowNode,
    LabWorkflowToken, LabWorkOrder,
)
from app.services.model_contracts import connection_diagnostics, validate_port_contract
from app.services.cep import evaluate_rules

RUNNER = Path(__file__).with_name("script_runner.py")


def _ordered_nodes(nodes: list[LabNode], edges: list[LabEdge]) -> list[LabNode]:
    """Stable topological order; canvas layout must never change simulation semantics."""
    by_id = {node.id: node for node in nodes}
    incoming = {node.id: 0 for node in nodes}
    outgoing = {node.id: set() for node in nodes}
    for edge in edges:
        if edge.enabled is False or edge.source_node_id not in by_id or edge.target_node_id not in by_id:
            continue
        if edge.target_node_id not in outgoing[edge.source_node_id]:
            outgoing[edge.source_node_id].add(edge.target_node_id)
            incoming[edge.target_node_id] += 1
    key = lambda node_id: (by_id[node_id].instance_key or by_id[node_id].id, node_id)
    ready = sorted((node_id for node_id, count in incoming.items() if count == 0), key=key)
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for target in sorted(outgoing[current], key=key):
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
                ready.sort(key=key)
    # Acausal/cyclic nets are handled by the legacy single-pass adapter for now,
    # but their order remains stable and independent of visual coordinates.
    ordered.extend(sorted((node_id for node_id in by_id if node_id not in ordered), key=key))
    return [by_id[node_id] for node_id in ordered]


def _edge_output_candidates(edge: LabEdge, outputs: dict) -> list[str]:
    domain = edge.domain or edge.flow_type
    if domain == "natural_gas" or edge.flow_type == "gas":
        return ["gas_energy_mw", "gas_flow_mw"]
    if domain == "electric.ac" or edge.flow_type == "electricity":
        return ["electric_power_mw"]
    return list(outputs)


def execute_script(code: str, action: str, context: dict, *, event=None, dt=0, timeout=2.0) -> dict:
    payload = json.dumps({"code": code, "action": action, "context": context, "event": event, "dt": dt})
    try:
        completed = subprocess.run([sys.executable, "-I", str(RUNNER)], input=payload, text=True, capture_output=True, timeout=timeout, check=False, env={"PYTHONIOENCODING": "utf-8"})
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Python callback exceeded {timeout}s") from exc
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip()[-2000:] or "Python callback failed")
    return json.loads(completed.stdout)


def validate_graph(db: Session, version_id: str) -> dict:
    nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == version_id)))
    edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == version_id)))
    types = {item.id: item for item in db.scalars(select(LabComponentType))}
    errors, warnings = [], []
    if not nodes:
        errors.append("Модель не містить вузлів")
    node_ids = {node.id for node in nodes}
    nodes_by_id = {node.id: node for node in nodes}
    for edge in edges:
        if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids:
            errors.append(f"Зв’язок {edge.id} посилається на відсутній вузол")
            continue
        source_node, target_node = nodes_by_id[edge.source_node_id], nodes_by_id[edge.target_node_id]
        source_type, target_type = types.get(source_node.component_type_id), types.get(target_node.component_type_id)
        if source_type and target_type:
            diagnostics = connection_diagnostics(
                source_type, edge.source_port, target_type, edge.target_port,
                source_overrides=source_node.port_overrides,
                target_overrides=target_node.port_overrides,
            )
            errors.extend(f"Зв’язок {edge.connection_key or edge.id}: {item}" for item in diagnostics)
    forbidden = {"latitude", "longitude", "coordinates", "territory_id", "location"}
    for node in nodes:
        component = types.get(node.component_type_id)
        if not component:
            errors.append(f"Невідомий тип компонента {node.component_type_id}")
            continue
        errors.extend(validate_port_contract(component))
        if forbidden.intersection(node.parameters):
            errors.append(f"{node.name}: територіальні поля заборонені")
        try:
            compile(node.python_code or component.python_code, f"<{node.name}>", "exec")
            result = execute_script(node.python_code or component.python_code, "validate", {"time": datetime.now(UTC).isoformat(), "parameters": node.parameters, "state": {}, "inputs": {}, "seed": 42})
            errors.extend(f"{node.name}: {item}" for item in result.get("result", []))
        except Exception as exc:
            errors.append(f"{node.name}: {exc}")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "nodes": len(nodes), "edges": len(edges)}


def _initial_state(db: Session, run: LabRun) -> dict:
    nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == run.model_version_id)))
    types = {item.id: item for item in db.scalars(select(LabComponentType))}
    state = {"nodes": {}, "metrics": {}, "sequence": 0, "resources": {}, "script_metrics": {}, "script_flows": [], "flows": []}
    for resource in db.scalars(select(LabResourcePool)):
        state["resources"][resource.id] = {"available": resource.available, "reserved": 0, "external_available": resource.external_available, "unit": resource.attributes.get("unit", "item")}
    for node in nodes:
        component = types[node.component_type_id]
        context = {"time": run.current_time.isoformat(), "parameters": node.parameters, "state": deepcopy(node.initial_state or component.initial_state), "inputs": {}, "seed": run.seed}
        result = execute_script(node.python_code or component.python_code, "initialize", context)
        state["nodes"][node.id] = {"state": result["state"], "outputs": result["outputs"], "logs": result["logs"]}
    return state


def _next_event_sequence(db: Session, run_id: str) -> int:
    existing = list(db.scalars(select(LabRunEvent.sequence).where(LabRunEvent.run_id == run_id)))
    return max(existing, default=0) + 1


def _apply_script_result(db: Session, run: LabRun, state: dict, result: dict, *, workflow_instance_id: str | None = None) -> None:
    """Apply only capability operations emitted by a sandboxed script."""
    sequence = _next_event_sequence(db, run.id)
    for item in [*result.get("emitted", []), *result.get("scheduled", [])]:
        at = datetime.fromisoformat(item.get("at") or run.current_time.isoformat())
        db.add(LabRunEvent(
            run_id=run.id, sequence=sequence, scheduled_at=at, priority=int(item.get("priority", 100)),
            event_type=item["event_type"], target_node_id=item.get("target"), origin="script",
            payload={**item.get("payload", {}), "_phase": item.get("phase", "process"), "_title": item.get("title", item["event_type"]), "_evidence": item.get("evidence", "derived")},
        ))
        sequence += 1
    for operation in result.get("operations", []):
        group, action = operation["group"], operation["action"]
        if group == "nodes" and action == "patch_state":
            target = state["nodes"].get(operation["node_id"])
            if target: target["state"].update(operation.get("patch", {}))
        elif group == "nodes" and action == "command":
            db.add(LabRunEvent(run_id=run.id, sequence=sequence, scheduled_at=run.current_time, priority=20, event_type=f"component.command.{operation['command']}", target_node_id=operation["node_id"], origin="script", payload={**operation.get("payload", {}), "_phase": "control", "_evidence": "derived"}))
            sequence += 1
        elif group == "clock" and action == "cancel":
            scheduled = db.get(LabRunEvent, operation.get("event_id"))
            if scheduled and scheduled.run_id == run.id and scheduled.status == "scheduled": scheduled.status = "cancelled"
        elif group == "resources":
            resource_id = operation["resource_id"]
            quantity = float(operation.get("quantity", 0))
            ledger = state.setdefault("resources", {}).setdefault(resource_id, {"available": 0, "reserved": 0, "external_available": 0, "unit": operation.get("unit", "item")})
            rejected = (action == "reserve" and ledger["available"] < quantity) or (action == "consume" and ledger["reserved"] < quantity)
            if rejected:
                db.add(LabResourceTransaction(run_id=run.id, model_time=run.current_time, resource_id=resource_id, operation="rejected", quantity=quantity, unit=operation.get("unit", "item"), workflow_instance_id=workflow_instance_id, details={"requested_operation": action, "reason": "insufficient_resource", **operation.get("details", {})}))
                db.add(LabRunEvent(run_id=run.id, sequence=sequence, scheduled_at=run.current_time, priority=10, event_type="resource.operation_rejected", origin="engine", payload={"resource_id": resource_id, "operation": action, "quantity": quantity, "_phase": "resources", "_evidence": "derived"}))
                sequence += 1
                continue
            if action == "reserve": ledger["available"] -= quantity; ledger["reserved"] += quantity
            elif action == "release": ledger["available"] += quantity; ledger["reserved"] = max(0, ledger["reserved"] - quantity)
            elif action == "consume": ledger["reserved"] = max(0, ledger["reserved"] - quantity)
            elif action == "produce": ledger["available"] += quantity
            elif action == "transfer": ledger.setdefault("transfers", []).append(operation.get("details", {}))
            db.add(LabResourceTransaction(run_id=run.id, model_time=run.current_time, resource_id=resource_id, operation=action, quantity=quantity, unit=operation.get("unit", "item"), workflow_instance_id=workflow_instance_id, details=operation.get("details", {})))
        elif group == "work" and action == "create":
            fields = operation.get("fields", {})
            db.add(LabWorkOrder(run_id=run.id, node_id=fields.get("node_id", "system"), status=fields.get("status", "new"), required_resources=fields.get("required_resources", {}), workflow_instance_id=workflow_instance_id, planned_at=run.current_time, result={"logical_id": fields.get("logical_id"), **fields.get("result", {})}))
        elif group == "work" and action in {"update", "complete"}:
            logical_id = operation.get("work_id")
            work = next((work for work in db.scalars(select(LabWorkOrder).where(LabWorkOrder.run_id == run.id)) if work.id == logical_id or work.result.get("logical_id") == logical_id), None)
            if work:
                fields = operation.get("fields", {})
                for name in ["status", "required_resources", "hazard_delay_hours", "repair_hours"]:
                    if name in fields: setattr(work, name, fields[name])
                if action == "complete": work.status = fields.get("status", "completed"); work.completed_at = run.current_time; work.result = {**work.result, **operation.get("result", {})}
        elif group == "metrics" and action == "publish":
            state.setdefault("script_metrics", {})[operation["metric_id"]] = {"value": operation["value"], "unit": operation.get("unit", ""), "dimensions": operation.get("dimensions", {})}
        elif group == "flows" and action == "publish":
            state.setdefault("script_flows", []).append({key: operation[key] for key in ["source", "target", "flow_type", "value", "unit"]})


def _advance_workflow(db: Session, run: LabRun, event: LabRunEvent, state: dict) -> str | None:
    instance = db.scalar(select(LabWorkflowInstance).where(LabWorkflowInstance.run_id == run.id).limit(1))
    if not instance: return None
    matching = db.scalar(select(LabWorkflowNode).where(LabWorkflowNode.workflow_version_id == instance.workflow_version_id, LabWorkflowNode.config["event_type"].astext == event.event_type).limit(1))
    if not matching: return instance.id
    if instance.current_node_id:
        previous = db.scalar(select(LabWorkflowToken).where(LabWorkflowToken.instance_id == instance.id, LabWorkflowToken.status == "active").order_by(LabWorkflowToken.entered_at.desc()).limit(1))
        if previous: previous.status = "completed"; previous.exited_at = run.current_time
    instance.current_node_id = matching.id
    instance.status = "completed" if matching.block_type in {"success", "failure"} else "running"
    instance.variables = {**instance.variables, "last_event": event.event_type, "phase": matching.config.get("phase", "process")}
    db.add(LabWorkflowToken(instance_id=instance.id, node_id=matching.id, status="active" if instance.status == "running" else "completed", entered_at=run.current_time, exited_at=run.current_time if instance.status == "completed" else None, data={"event_id": event.id}))
    return instance.id


def _network_metrics(nodes: list[LabNode], edges: list[LabEdge], state: dict, types: dict[str, LabComponentType] | None = None) -> dict:
    nodes_by_id = {node.id: node for node in nodes}
    online = {node.id for node in nodes if state["nodes"].get(node.id, {}).get("state", {}).get("online", True)}
    graph = {node.id: set() for node in nodes if node.id in online}
    for edge in edges:
        if edge.source_node_id in online and edge.target_node_id in online:
            graph[edge.source_node_id].add(edge.target_node_id); graph[edge.target_node_id].add(edge.source_node_id)
    components, seen = [], set()
    for node_id in graph:
        if node_id in seen: continue
        island = set(); stack = [node_id]
        while stack:
            current = stack.pop()
            if current in seen: continue
            seen.add(current); island.add(current); stack.extend(graph[current] - seen)
        components.append(island)
    generated = demand = deficit = 0.0
    island_stats: list[dict] = []
    for island in components:
        island_generation = sum(
            float(state["nodes"].get(node_id, {}).get("outputs", {}).get("electric_power_mw", 0))
            for node_id in island
            if types is None or types[nodes_by_id[node_id].component_type_id].category == "generation"
        )
        island_demand = sum(float(state["nodes"].get(node_id, {}).get("state", {}).get("demand_mw", 0)) for node_id in island)
        island_deficit = max(0.0, island_demand - island_generation)
        energized = island_generation > 0
        island_frequency = (
            max(47.5, 50 - 2.8 * island_deficit / max(island_demand, 1))
            if energized else 0.0
        )
        island_stats.append({
            "nodes": island, "generation_mw": island_generation,
            "demand_mw": island_demand, "deficit_mw": island_deficit,
            "energized": energized, "frequency_hz": island_frequency,
        })
        generated += island_generation; demand += island_demand; deficit += island_deficit
    # Frequency exists only in energized synchronous islands. A disconnected
    # consumer is represented by zero voltage/frequency at its own control
    # point and must not pull the generator island frequency down to 47.5 Hz.
    energized_frequencies = [item["frequency_hz"] for item in island_stats if item["energized"]]
    frequency = min(energized_frequencies, default=0.0)
    islands = len(components)
    # Quasi-static AC voltage approximation: per-unit drops accumulate from
    # active/reactive flow and edge impedance inside each energized island.
    voltage_drop = 0.0
    for edge in edges:
        if edge.source_node_id in online and edge.target_node_id in online and edge.flow_type == "electricity":
            r = float(edge.parameters.get("resistance_pu", .01)); x = float(edge.parameters.get("reactance_pu", .08))
            p_pu = demand / max(generated, demand, 1); q_pu = p_pu * .25
            voltage_drop += max(0, r * p_pu + x * q_pu)
    voltage = (
        max(0.72, 1 - voltage_drop - 0.12 * deficit / max(demand, 1) - 0.015 * max(0, islands - 1))
        if energized_frequencies else 0.0
    )
    node_metrics = {}
    for node in nodes:
        node_state = state["nodes"].get(node.id, {})
        node_online = node.id in online
        island = next((item for item in island_stats if node.id in item["nodes"]), None)
        energized = bool(node_online and island and island["energized"])
        component = types.get(node.component_type_id) if types else None
        is_generator = bool(component and component.category == "generation")
        node_voltage = 0.0
        if energized:
            node_voltage = 1.02 if is_generator else max(
                0.72,
                1 - voltage_drop - 0.06 * island["deficit_mw"] / max(island["demand_mw"], 1),
            )
        node_metrics[node.id] = {
            "online": node_online,
            "energized": energized,
            "voltage_pu": round(node_voltage, 4),
            "frequency_hz": round(island["frequency_hz"], 3) if energized else 0.0,
            "electric_power_mw": round(float(node_state.get("outputs", {}).get("electric_power_mw", 0)), 3),
            "demand_mw": round(float(node_state.get("state", {}).get("demand_mw", 0)), 3),
        }
    online_outputs = [state["nodes"][node.id].get("outputs", {}) for node in nodes if node.id in online]
    gas_consumption = sum(float(output.get("gas_consumption_mw", 0)) for output in online_outputs)
    co2_tph = sum(float(output.get("co2_tph", 0)) for output in online_outputs)
    co2_t = sum(float(item.get("state", {}).get("co2_t", 0)) for item in state["nodes"].values())
    heat_mw = sum(float(output.get("waste_heat_mw", 0)) + float(output.get("room_heat_mw", 0)) + float(output.get("heat_mw", 0)) for output in online_outputs)
    visible_mw = sum(float(output.get("visible_radiation_mw", 0)) for output in online_outputs)
    resource_remaining = sum(float(item.get("state", {}).get("resource_mwh", 0)) for item in state["nodes"].values())
    return {"generation_mw": round(generated, 3), "demand_mw": round(demand, 3), "served_load_mw": round(max(0, demand - deficit), 3), "unserved_mw": round(deficit, 3), "frequency_hz": round(frequency, 3), "voltage_pu": round(voltage, 4), "islands": islands, "black_system": frequency < 48.2 or voltage < 0.78 or deficit > 0, "gas_consumption_mw": round(gas_consumption, 3), "gas_remaining_mwh": round(resource_remaining, 3), "co2_tph": round(co2_tph, 3), "co2_t": round(co2_t, 3), "heat_mw": round(heat_mw, 3), "visible_radiation_mw": round(visible_mw, 3), "node_metrics": node_metrics}


FAILURE_EVENTS = {
    "failure", "external_damage", "trip", "line_fault", "substation_fault",
    "voltage_excursion", "overload", "vegetation_contact", "operator_error",
    "fire_spread", "gas_supply_loss", "pipeline_rupture", "fire",
    "gas_accumulation", "barrier_failure", "uncontrolled_flow",
}


def replay_scenario(db: Session, scenario: LabScenario, version_id: str) -> dict:
    """Replay any qualification profile through the common component engine."""
    nodes = sorted(db.scalars(select(LabNode).where(LabNode.model_version_id == version_id)), key=lambda node: (node.x, node.y))
    edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == version_id)))
    types = {item.id: item for item in db.scalars(select(LabComponentType))}
    state = {"nodes": {}, "metrics": {}, "sequence": 0}
    for node in nodes:
        component = types[node.component_type_id]
        result = execute_script(node.python_code or component.python_code, "initialize", {
            "time": scenario.start_at.isoformat(), "parameters": node.parameters,
            "state": deepcopy(node.initial_state or component.initial_state), "inputs": {}, "seed": scenario.seed,
        })
        state["nodes"][node.id] = {"state": result["state"], "outputs": result["outputs"], "logs": result["logs"]}

    # Establish the same pre-incident operating point for every scenario.
    for node in nodes:
        current = state["nodes"][node.id]
        inputs = {}
        for edge in (item for item in edges if item.target_node_id == node.id):
            for key, value in state["nodes"][edge.source_node_id]["outputs"].items():
                if edge.flow_type == "gas" and "gas" not in key: continue
                if edge.flow_type == "electricity" and key != "electric_power_mw": continue
                inputs[f"{edge.source_node_id}.{key}"] = value
        result = execute_script(node.python_code or types[node.component_type_id].python_code, "tick", {
            "time": scenario.start_at.isoformat(), "parameters": node.parameters, "state": current["state"],
            "inputs": inputs, "seed": scenario.seed,
        }, dt=types[node.component_type_id].tick_seconds)
        current.update(state=result["state"], outputs=result["outputs"], logs=result["logs"])

    trace, failed_nodes, restored_nodes, work_orders = [], set(), set(), 0
    ordered = sorted(enumerate(scenario.events), key=lambda item: (item[1]["at"], item[1].get("priority", 100), item[0]))
    for sequence, (_, event) in enumerate(ordered, 1):
        target_id = event.get("target_node_id")
        targets = [node for node in nodes if not target_id or node.id == target_id]
        for node in targets:
            current = state["nodes"][node.id]
            result = execute_script(node.python_code or types[node.component_type_id].python_code, "event", {
                "time": event["at"], "parameters": node.parameters, "state": current["state"],
                "inputs": {}, "seed": scenario.seed + sequence,
            }, event={"type": event["event_type"], "payload": event.get("payload", {})})
            current.update(state=result["state"], outputs=result["outputs"], logs=(current.get("logs", []) + result["logs"])[-100:])
            if event["event_type"] in FAILURE_EVENTS:
                failed_nodes.add(node.id); work_orders += 1
            if event["event_type"] in {"repair", "restore", "black_start", "resynchronize"} and current["state"].get("online", True):
                restored_nodes.add(node.id)
        metrics = _network_metrics(nodes, edges, state, types)
        trace.append({"sequence": sequence, "at": event["at"], "event_type": event["event_type"], "target_node_id": target_id, "metrics": metrics})

    metrics_trace = [item["metrics"] for item in trace] or [_network_metrics(nodes, edges, state, types)]
    observed = {
        "processed_events": len(trace), "processed_event_types": sorted({item["event_type"] for item in trace}),
        "failed_assets": len(failed_nodes), "restored_assets": len(restored_nodes), "work_orders": work_orders,
        "max_islands": max(item["islands"] for item in metrics_trace),
        "max_unserved_mw": max(item["unserved_mw"] for item in metrics_trace),
        "minimum_frequency_hz": min(item["frequency_hz"] for item in metrics_trace),
        "minimum_voltage_pu": min(item["voltage_pu"] for item in metrics_trace),
        "black_system": any(item["black_system"] for item in metrics_trace),
    }
    event_types = set(observed["processed_event_types"])
    predicates = {
        "damaged_assets": lambda expected: observed["failed_assets"] >= int(expected),
        "critical_impact": lambda expected: not expected or observed["max_unserved_mw"] > 0,
        "inventory_stress": lambda expected: not expected or observed["work_orders"] >= 3,
        "system_separation": lambda expected: not expected or observed["max_islands"] > 1,
        "resynchronized": lambda expected: not expected or "resynchronize" in event_types,
        "voltage_cascade": lambda expected: not expected or observed["minimum_voltage_pu"] < .9,
        "black_system": lambda expected: observed["black_system"] is bool(expected),
        "repeated_voltage_dips": lambda expected: not expected or len(event_types & FAILURE_EVENTS) >= 2,
        "frequency_cascade": lambda expected: not expected or observed["minimum_frequency_hz"] < 49.5,
        "black_start": lambda expected: not expected or "black_start" in event_types and observed["restored_assets"] > 0,
        "overload_cascade": lambda expected: not expected or {"overload", "line_fault"}.issubset(event_types),
        "situational_awareness_loss": lambda expected: not expected or "scada_loss" in event_types,
        "cascade": lambda expected: not expected or observed["failed_assets"] >= 2,
        "operator_cascade": lambda expected: not expected or "operator_error" in event_types and observed["failed_assets"] >= 2,
        "frequency_shedding": lambda expected: not expected or observed["minimum_frequency_hz"] < 49.5,
        "staged_restoration": lambda expected: not expected or "repair" in event_types and observed["restored_assets"] > 0,
        "crew_shortage": lambda expected: not expected or observed["work_orders"] >= 2,
        "long_restoration": lambda expected: not expected or observed["failed_assets"] > observed["restored_assets"],
        "gas_power_common_cause": lambda expected: not expected or {"gas_supply_loss", "trip"}.issubset(event_types),
        "frequency_reserve_shortage": lambda expected: not expected or observed["minimum_frequency_hz"] < 49.5,
        "linepack_loss": lambda expected: not expected or "pipeline_rupture" in event_types,
        "fuel_shortage": lambda expected: not expected or "pipeline_rupture" in event_types,
        "explosion": lambda expected: not expected or "gas_accumulation" in event_types and "external_damage" in event_types,
        "response_required": lambda expected: not expected or observed["work_orders"] > 0,
        "barrier_loss": lambda expected: not expected or "barrier_failure" in event_types,
        "long_duration_release": lambda expected: not expected or "uncontrolled_flow" in event_types,
    }
    outcome_checks = {
        name: predicates[name](expected)
        for name, expected in scenario.expected.items()
        if name in predicates
    }
    required = set(scenario.expected.get("required_event_types", []))
    checks = {
        "replay_completed": len(trace) == len(scenario.events),
        "event_order": [item["at"] for item in trace] == sorted(item["at"] for item in trace),
        "mechanisms_executed": required.issubset(observed["processed_event_types"]),
        "failure_changed_state": not failed_nodes or all(not state["nodes"][node_id]["state"].get("online", True) or node_id in restored_nodes for node_id in failed_nodes),
        "impact_calculated": all("frequency_hz" in item["metrics"] and "voltage_pu" in item["metrics"] for item in trace),
        "abstract_targets": all(not item["target_node_id"] or str(item["target_node_id"]).startswith(("p-", "q")) for item in trace),
        "no_coordinates": all(not ({"latitude", "longitude", "coordinates"} & set(event.get("payload", {}))) for event in scenario.events),
        "expected_outcomes": all(outcome_checks.values()),
    }
    return {"passed": all(checks.values()), "checks": checks, "outcome_checks": outcome_checks, "observed": observed, "trace": trace}


def prepare_run(db: Session, run: LabRun) -> None:
    run.state = _initial_state(db, run)
    state = deepcopy(run.state)
    scenario = db.get(LabScenario, run.scenario_id) if run.scenario_id else None
    if scenario:
        workflow_version_id = scenario.configuration.get("workflow_version_id")
        if workflow_version_id and not db.scalar(select(LabWorkflowInstance).where(LabWorkflowInstance.run_id == run.id)):
            db.add(LabWorkflowInstance(run_id=run.id, workflow_version_id=workflow_version_id, status="ready", variables={"scenario_id": scenario.id}))
        script_version = db.get(LabScriptVersion, scenario.configuration.get("scenario_script_version_id"))
        if script_version:
            result = execute_script(script_version.code, "before_start", {"time": run.current_time.isoformat(), "parameters": scenario.configuration, "state": {}, "inputs": {}, "seed": run.seed, "snapshot": state})
            _apply_script_result(db, run, state, result)
            if result.get("timeline"):
                run.summary = {**run.summary, "timeline": result["timeline"]}
    run.state = state
    scenario_events = list(db.scalars(select(LabRunEvent).where(LabRunEvent.run_id == run.id)))
    if not scenario_events:
        db.add(LabRunEvent(run_id=run.id, sequence=1, scheduled_at=run.current_time, priority=0, event_type="simulation.started", origin="system", payload={}))
    run.status = "paused"
    db.commit()


def process_next(db: Session, run: LabRun, *, max_step_seconds: float | None = None) -> dict:
    if not run.state:
        prepare_run(db, run); db.refresh(run)
    event = db.scalar(select(LabRunEvent).where(LabRunEvent.run_id == run.id, LabRunEvent.status == "scheduled").order_by(LabRunEvent.scheduled_at, LabRunEvent.priority, LabRunEvent.sequence).limit(1))
    raw_nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == run.model_version_id)))
    types = {item.id: item for item in db.scalars(select(LabComponentType))}
    edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == run.model_version_id, LabEdge.enabled.is_(True))))
    nodes = _ordered_nodes(raw_nodes, edges)
    state = deepcopy(run.state)
    component_step = min((types[n.component_type_id].tick_seconds for n in nodes), default=3600)
    # Playback may deliberately aggregate many physical ticks into one large dt.
    # The next scheduled event still forms a hard boundary below.
    step_seconds = max_step_seconds if max_step_seconds else component_step
    next_tick = run.current_time + timedelta(seconds=max(.001, step_seconds))
    if event and event.scheduled_at <= next_tick:
        run.current_time = event.scheduled_at
        targets = [n for n in nodes if not event.target_node_id or n.id == event.target_node_id]
        for node in targets:
            current = state["nodes"][node.id]
            ctx = {"time": run.current_time.isoformat(), "parameters": node.parameters, "state": current["state"], "inputs": {}, "seed": run.seed + event.sequence}
            result = execute_script(node.python_code or types[node.component_type_id].python_code, "event", ctx, event={"type": event.event_type, "payload": event.payload})
            current.update(state=result["state"], outputs=result["outputs"], logs=(current.get("logs", []) + result["logs"])[-100:])
        event.status = "processed"; event.processed_at = datetime.now(UTC); event.result = {"targets": len(targets)}
        scenario = db.get(LabScenario, run.scenario_id) if run.scenario_id else None
        workflow_instance_id = _advance_workflow(db, run, event, state)
        if scenario:
            process_script = db.get(LabScriptVersion, scenario.configuration.get("process_script_version_id"))
            if process_script:
                script_result = execute_script(process_script.code, "event", {"time": run.current_time.isoformat(), "parameters": scenario.configuration, "state": {}, "inputs": {}, "seed": run.seed + event.sequence, "snapshot": state}, event={"type": event.event_type, "payload": event.payload, "target": event.target_node_id})
                _apply_script_result(db, run, state, script_result, workflow_instance_id=workflow_instance_id)
        # Recalculate the physical operating point at the event timestamp.
        # Without this pass, a run that jumps from event to event would store
        # empty/stale electrical measurements until the first free physics tick.
        for node in nodes:
            current = state["nodes"][node.id]
            inputs = {}
            for edge in (item for item in edges if item.target_node_id == node.id):
                for key, value in state["nodes"].get(edge.source_node_id, {}).get("outputs", {}).items():
                    if key not in _edge_output_candidates(edge, state["nodes"].get(edge.source_node_id, {}).get("outputs", {})): continue
                    inputs[f"{edge.source_node_id}.{key}"] = value
            ctx = {"time": run.current_time.isoformat(), "parameters": node.parameters, "state": current["state"], "inputs": inputs, "seed": run.seed + event.sequence}
            result = execute_script(node.python_code or types[node.component_type_id].python_code, "tick", ctx, dt=.001)
            current.update(state=result["state"], outputs=result["outputs"], logs=(current.get("logs", []) + result["logs"])[-100:])
    else:
        previous_time = run.current_time
        run.current_time = min(next_tick, run.end_time)
        actual_dt = max(.001, (run.current_time - previous_time).total_seconds())
        for node in nodes:
            current = state["nodes"][node.id]
            incoming = [edge for edge in edges if edge.target_node_id == node.id]
            inputs = {}
            for edge in incoming:
                for key, value in state["nodes"].get(edge.source_node_id, {}).get("outputs", {}).items():
                    if key not in _edge_output_candidates(edge, state["nodes"].get(edge.source_node_id, {}).get("outputs", {})): continue
                    inputs[f"{edge.source_node_id}.{key}"] = value
            ctx = {"time": run.current_time.isoformat(), "parameters": node.parameters, "state": current["state"], "inputs": inputs, "seed": run.seed + int(run.current_time.timestamp())}
            result = execute_script(node.python_code or types[node.component_type_id].python_code, "tick", ctx, dt=actual_dt)
            current.update(state=result["state"], outputs=result["outputs"], logs=(current.get("logs", []) + result["logs"])[-100:])
    state["sequence"] = int(state.get("sequence", 0)) + 1
    state["flows"] = list(state.get("script_flows", [])[-100:])
    for edge in edges:
        outputs = state["nodes"].get(edge.source_node_id, {}).get("outputs", {})
        candidates = _edge_output_candidates(edge, outputs)
        key = next((name for name in candidates if name in outputs), None)
        if key:
            state["flows"].append({"source": edge.source_node_id, "target": edge.target_node_id, "flow_type": edge.flow_type, "value": float(outputs[key]), "unit": "MW"})
    metrics = _network_metrics(nodes, edges, state, types)
    ratio = 1 - metrics["unserved_mw"] / max(metrics["demand_mw"], 1)
    metrics["impact_contract"] = {"unserved_load_mw": metrics["unserved_mw"], "affected_groups": [name for name, threshold in [("Критичні функції", .8), ("Телекомунікації", .9), ("Домогосподарства", .99), ("Промисловість", 1.0)] if ratio < threshold], "territorial_ids": []}
    scenario = db.get(LabScenario, run.scenario_id) if run.scenario_id else None
    dashboard_script = db.get(LabScriptVersion, scenario.configuration.get("dashboard_script_version_id")) if scenario else None
    if dashboard_script:
        state["metrics"] = metrics
        dashboard_result = execute_script(dashboard_script.code, "collect", {"time": run.current_time.isoformat(), "parameters": scenario.configuration, "state": {}, "inputs": {}, "seed": run.seed + state["sequence"], "snapshot": state})
        _apply_script_result(db, run, state, dashboard_result)
    metrics.update({key: value["value"] for key, value in state.get("script_metrics", {}).items()})
    state["metrics"] = metrics
    cep_events = [event.event_type] if event and event.processed_at else []
    if scenario:
        rules = list(db.scalars(select(LabCepRule).where(LabCepRule.scenario_id == scenario.id, LabCepRule.enabled.is_(True))))
        cep_sequence = _next_event_sequence(db, run.id)
        cep_metrics = deepcopy(metrics)
        cep_metrics["component"] = {
            node.instance_key or node.id: metrics.get("node_metrics", {}).get(node.id, {})
            for node in nodes
        }
        for emitted in evaluate_rules(rules, state, run.current_time, cep_metrics, cep_events):
            db.add(LabRunEvent(
                run_id=run.id, sequence=cep_sequence, scheduled_at=run.current_time,
                priority=int(emitted.get("priority", 40)), event_type=emitted["event_type"],
                target_node_id=emitted.get("target_node_id"), origin="cep",
                payload={**emitted.get("payload", {}), "_cep": True},
            ))
            cep_sequence += 1
    timeline = run.summary.get("timeline", {}) if run.summary else {}
    run.state = state; run.summary = {**metrics, "timeline": timeline}
    db.add(LabRunSample(run_id=run.id, model_time=run.current_time, sequence=state["sequence"], metrics=metrics, resources=state.get("resources", {}), emissions={"co2_tph": metrics.get("co2_tph", 0), "co2_t": metrics.get("co2_t", 0)}))
    for flow in state.get("flows", [])[-100:]:
        db.add(LabFlowSample(run_id=run.id, model_time=run.current_time, source_node_id=flow["source"], target_node_id=flow["target"], flow_type=flow["flow_type"], value=float(flow["value"]), unit=flow["unit"]))
    if run.current_time >= run.end_time:
        run.status = "completed"
    if state["sequence"] % 24 == 0 or state["sequence"] == 1:
        db.add(LabCheckpoint(run_id=run.id, model_time=run.current_time, sequence=state["sequence"], state=state, metrics=metrics))
    db.commit()
    return {"time": run.current_time.isoformat(), "metrics": metrics, "sequence": state["sequence"], "event": event.event_type if event and event.processed_at else "physics.tick"}
