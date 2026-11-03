import json
import math
import re
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    LabCepRule,
    LabCheckpoint,
    LabComponentType,
    LabEdge,
    LabEventAction,
    LabEventProgram,
    LabEventType,
    LabFlowSample,
    LabNode,
    LabResourcePool,
    LabResourceTransaction,
    LabRun,
    LabRunEvent,
    LabRunSample,
    LabScenario,
    LabScenarioAssemblyMember,
    LabScenarioAssemblyNodeMap,
    LabScenarioProcessBinding,
    LabScenarioEventTemplate,
    LabScriptVersion,
    LabWorkflowInstance,
    LabWorkflowNode,
    LabWorkflowToken,
    LabWorkflowTransition,
    LabWorkflowVersion,
    LabProcessSetWorkflow,
    LabWorkOrder,
)
from app.services.cep import evaluate_rules
from app.services.model_contracts import connection_diagnostics, validate_port_contract

RUNNER = Path(__file__).with_name("script_runner.py")


def _ordered_nodes(
    nodes: list[LabNode], edges: list[LabEdge], *, respect_enabled: bool = True
) -> list[LabNode]:
    """Stable topological order; canvas layout must never change simulation semantics."""
    by_id = {node.id: node for node in nodes}
    incoming = {node.id: 0 for node in nodes}
    outgoing = {node.id: set() for node in nodes}
    for edge in edges:
        if (
            (respect_enabled and edge.enabled is False)
            or edge.source_node_id not in by_id
            or edge.target_node_id not in by_id
        ):
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


def _zero_delay_emit_cycle(
    programs: list[LabEventProgram],
    actions_by_program: dict[str, list[LabEventAction]],
) -> list[str] | None:
    """Return one immediate event-emission cycle, if the published graph contains one."""
    graph = {program.event_type_id: set() for program in programs if program.enabled}
    for program in programs:
        if not program.enabled:
            continue
        for action in actions_by_program.get(program.id, []):
            config = action.config or {}
            delay = config.get("delay_seconds", 0)
            if (
                action.action_type == "event.emit"
                and not isinstance(delay, bool)
                and isinstance(delay, int | float)
                and math.isfinite(float(delay))
                and float(delay) == 0
                and isinstance(config.get("event_type"), str)
            ):
                graph[program.event_type_id].add(config["event_type"])

    colors: dict[str, int] = {}
    stack: list[str] = []

    def visit(event_type: str) -> list[str] | None:
        colors[event_type] = 1
        stack.append(event_type)
        for emitted_type in sorted(graph.get(event_type, set())):
            if emitted_type not in graph:
                continue
            if colors.get(emitted_type) == 1:
                start = stack.index(emitted_type)
                return [*stack[start:], emitted_type]
            if colors.get(emitted_type, 0) == 0:
                cycle = visit(emitted_type)
                if cycle:
                    return cycle
        stack.pop()
        colors[event_type] = 2
        return None

    for event_type in sorted(graph):
        if colors.get(event_type, 0) == 0:
            cycle = visit(event_type)
            if cycle:
                return cycle
    return None


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
    event_type_ids = set(db.scalars(select(LabEventType.id)))
    programs = list(
        db.scalars(
            select(LabEventProgram).where(LabEventProgram.model_version_id == version_id)
        )
    )
    actions_by_program: dict[str, list[LabEventAction]] = {}
    edges_by_id = {edge.id: edge for edge in edges}
    for program in programs:
        if program.event_type_id not in event_type_ids:
            errors.append(
                f"Програма «{program.name}» посилається на невідомий тип події "
                f"«{program.event_type_id}»"
            )
        actions = list(
            db.scalars(
                select(LabEventAction)
                .where(LabEventAction.program_id == program.id)
                .order_by(LabEventAction.sequence, LabEventAction.id)
            )
        )
        actions_by_program[program.id] = actions
        if program.enabled and not actions:
            errors.append(f"Увімкнена програма «{program.name}» не містить дій")
        for action in actions:
            errors.extend(
                f"Програма «{program.name}», дія {action.sequence}: {item}"
                for item in event_action_diagnostics(
                    action,
                    nodes_by_id,
                    edges_by_id,
                    types,
                    event_type_ids,
                )
            )
    immediate_cycle = _zero_delay_emit_cycle(programs, actions_by_program)
    if immediate_cycle:
        errors.append(
            "Дії event.emit з нульовою затримкою утворюють нескінченний цикл: "
            + " → ".join(immediate_cycle)
        )
    return {"valid": not errors, "errors": errors, "warnings": warnings, "nodes": len(nodes), "edges": len(edges)}


def _initial_state(db: Session, run: LabRun) -> dict:
    nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == run.model_version_id)))
    edges = list(
        db.scalars(select(LabEdge).where(LabEdge.model_version_id == run.model_version_id))
    )
    types = {item.id: item for item in db.scalars(select(LabComponentType))}
    state = {
        "nodes": {},
        "connections": {edge.id: {"enabled": bool(edge.enabled)} for edge in edges},
        "metrics": {},
        "sequence": 0,
        "resources": {},
        "script_metrics": {},
        "script_flows": [],
        "flows": [],
    }
    for resource in db.scalars(select(LabResourcePool)):
        state["resources"][resource.id] = {"available": resource.available, "reserved": 0, "external_available": resource.external_available, "unit": resource.attributes.get("unit", "item")}
    for node in nodes:
        component = types[node.component_type_id]
        context = {
            "time": run.current_time.isoformat(),
            "parameters": node.parameters,
            "state": deepcopy(
                {**(component.initial_state or {}), **(node.initial_state or {})}
            ),
            "inputs": {},
            "seed": run.seed,
        }
        result = execute_script(node.python_code or component.python_code, "initialize", context)
        state["nodes"][node.id] = {"state": result["state"], "outputs": result["outputs"], "logs": result["logs"]}
    return state


def _next_event_sequence(db: Session, run_id: str) -> int:
    existing = list(db.scalars(select(LabRunEvent.sequence).where(LabRunEvent.run_id == run_id)))
    return max(existing, default=0) + 1


class EventProgramActionError(RuntimeError):
    """A configured event action could not be executed safely."""


def _action_value(action: LabEventAction | dict, name: str, default=None):
    return action.get(name, default) if isinstance(action, dict) else getattr(action, name, default)


def _component_patch_schema(node: LabNode, component: LabComponentType) -> dict:
    return {**(component.initial_state or {}), **(node.initial_state or {})}


def _json_value_kind(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def event_payload_diagnostics(payload: dict, schema: dict | None) -> list[str]:
    """Validate the supported top-level JSON Schema subset used by event types."""
    schema = schema or {}
    errors: list[str] = []
    required = schema.get("required", [])
    if isinstance(required, list):
        errors.extend(f"Відсутнє обов’язкове поле «{key}»" for key in required if key not in payload)
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return errors

    def matches_type(value, expected: str) -> bool:
        return {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "number": not isinstance(value, bool) and isinstance(value, int | float),
            "integer": not isinstance(value, bool) and isinstance(value, int),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(expected, True)

    for key, value in payload.items():
        field_schema = properties.get(key)
        if not isinstance(field_schema, dict):
            continue
        expected_type = field_schema.get("type")
        if isinstance(expected_type, str) and not matches_type(value, expected_type):
            errors.append(f"Поле «{key}» має мати тип {expected_type}")
            continue
        choices = field_schema.get("enum")
        if isinstance(choices, list) and value not in choices:
            errors.append(f"Поле «{key}» має недопустиме значення")
        if not isinstance(value, bool) and isinstance(value, int | float):
            minimum = field_schema.get("minimum")
            maximum = field_schema.get("maximum")
            if isinstance(minimum, int | float) and value < minimum:
                errors.append(f"Поле «{key}» має бути не менше {minimum}")
            if isinstance(maximum, int | float) and value > maximum:
                errors.append(f"Поле «{key}» має бути не більше {maximum}")
    return errors


def event_action_diagnostics(
    action: LabEventAction | dict,
    nodes_by_id: dict[str, LabNode],
    edges_by_id: dict[str, LabEdge],
    component_types: dict[str, LabComponentType],
    event_type_ids: set[str] | None = None,
    event_types_by_id: dict[str, LabEventType] | None = None,
    enabled_program_event_types: set[str] | None = None,
) -> list[str]:
    """Validate an event action against the model snapshot it belongs to."""
    action_type = _action_value(action, "action_type", "")
    target_kind = _action_value(action, "target_kind")
    target_id = _action_value(action, "target_id")
    config = _action_value(action, "config", {})
    errors: list[str] = []
    if not isinstance(config, dict):
        return ["Конфігурація дії має бути об’єктом"]

    if action_type in {"component.capability", "component.patch_state"}:
        if target_kind != "component" or not target_id:
            return ["Для дії над компонентом потрібна ціль типу component"]
        node = nodes_by_id.get(target_id)
        if not node:
            return [f"Компонент-ціль «{target_id}» не належить цій версії моделі"]
        component = component_types.get(node.component_type_id)
        if not component:
            return [f"Для компонента «{node.name}» не знайдено тип"]
        if action_type == "component.capability":
            capability = config.get("capability")
            if not isinstance(capability, str) or not capability.strip():
                errors.append("component.capability потребує непорожнє поле capability")
            elif capability not in set(node.refinement_contract.get("capabilities", [])):
                errors.append(f"Компонент «{node.name}» не оголошує capability «{capability}»")
            if not isinstance(config.get("payload", {}), dict):
                errors.append("component.capability.payload має бути об’єктом")
            if not isinstance(config.get("forward_payload", True), bool):
                errors.append("component.capability.forward_payload має бути boolean")
        else:
            patch = config.get("patch")
            if not isinstance(patch, dict):
                errors.append("component.patch_state потребує об’єкт patch")
            else:
                schema = _component_patch_schema(node, component)
                for key, value in patch.items():
                    if key not in schema:
                        errors.append(f"Стан компонента «{node.name}» не містить поля «{key}»")
                        continue
                    expected = schema[key]
                    if isinstance(expected, dict | list) or isinstance(value, dict | list):
                        errors.append(
                            f"Поле стану «{key}» можна змінювати лише примітивним значенням"
                        )
                    elif _json_value_kind(value) != _json_value_kind(expected):
                        errors.append(
                            f"Поле стану «{key}» очікує {_json_value_kind(expected)}, "
                            f"отримано {_json_value_kind(value)}"
                        )
        return errors

    if action_type in {"connection.disable", "connection.enable"}:
        if target_kind != "connection" or not target_id:
            return ["Для дії над зв’язком потрібна ціль типу connection"]
        if target_id not in edges_by_id:
            return [f"Зв’язок-ціль «{target_id}» не належить цій версії моделі"]
        return errors

    if action_type == "event.emit":
        if target_kind not in {None, ""} or target_id not in {None, ""}:
            errors.append("event.emit не може мати об’єкт-ціль")
        emitted_type = config.get("event_type")
        if not isinstance(emitted_type, str) or not emitted_type.strip():
            errors.append("event.emit потребує непорожнє поле event_type")
        elif event_type_ids is not None and emitted_type not in event_type_ids:
            errors.append(f"event.emit посилається на невідомий тип події «{emitted_type}»")
        delay = config.get("delay_seconds", 0)
        if (
            isinstance(delay, bool)
            or not isinstance(delay, int | float)
            or not math.isfinite(float(delay))
            or delay < 0
        ):
            errors.append("event.emit.delay_seconds має бути скінченним числом не менше нуля")
        if not isinstance(config.get("payload", {}), dict):
            errors.append("event.emit.payload має бути об’єктом")
        return errors

    return [f"Непідтримуваний тип дії «{action_type}»"]


def _effective_edges(edges: list[LabEdge], state: dict) -> list[LabEdge]:
    """Resolve mutable run-local connection state without changing the model snapshot."""
    connections = state.setdefault("connections", {})
    effective: list[LabEdge] = []
    for edge in edges:
        runtime = connections.setdefault(edge.id, {"enabled": bool(edge.enabled)})
        if bool(runtime.get("enabled", edge.enabled)):
            effective.append(edge)
    return effective


def _execute_event_program(
    db: Session,
    run: LabRun,
    event: LabRunEvent,
    state: dict,
    nodes: list[LabNode],
    edges: list[LabEdge],
    component_types: dict[str, LabComponentType],
) -> bool:
    """Execute the matching enabled program; return false for legacy delivery."""
    program = db.scalar(
        select(LabEventProgram).where(
            LabEventProgram.model_version_id == run.model_version_id,
            LabEventProgram.event_type_id == event.event_type,
            LabEventProgram.enabled.is_(True),
        ).limit(1)
    )
    if not program:
        return False

    actions = list(
        db.scalars(
            select(LabEventAction)
            .where(LabEventAction.program_id == program.id)
            .order_by(LabEventAction.sequence, LabEventAction.id)
        )
    )
    nodes_by_id = {node.id: node for node in nodes}
    edges_by_id = {edge.id: edge for edge in edges}
    action_results: list[dict] = []
    emitted_sequence = _next_event_sequence(db, run.id)
    event_type_ids = set(db.scalars(select(LabEventType.id)))

    for action in actions:
        outcome = {
            "action_id": action.id,
            "type": action.action_type,
            "status": "completed",
            "target_kind": action.target_kind,
            "target_id": action.target_id,
        }
        try:
            diagnostics = event_action_diagnostics(
                action, nodes_by_id, edges_by_id, component_types, event_type_ids
            )
            if diagnostics:
                raise EventProgramActionError("; ".join(diagnostics))
            config = action.config or {}
            if action.action_type == "component.capability":
                node = nodes_by_id[action.target_id]
                current = state["nodes"].get(node.id)
                if not current:
                    raise EventProgramActionError(
                        f"Стан компонента «{node.name}» не ініціалізовано"
                    )
                forwarded = {
                    key: value
                    for key, value in (event.payload or {}).items()
                    if not str(key).startswith("_")
                } if config.get("forward_payload", True) else {}
                payload = {**forwarded, **config.get("payload", {})}
                context = {
                    "time": run.current_time.isoformat(),
                    "parameters": node.parameters,
                    "state": current["state"],
                    "inputs": {},
                    "seed": run.seed + event.sequence,
                }
                try:
                    result = execute_script(
                        node.python_code or component_types[node.component_type_id].python_code,
                        "event",
                        context,
                        event={"type": config["capability"], "payload": payload},
                    )
                except RuntimeError as exc:
                    raise EventProgramActionError(str(exc)) from exc
                if not all(key in result for key in ("state", "outputs", "logs")):
                    raise EventProgramActionError("Callback компонента повернув неповний результат")
                current.update(
                    state=result["state"],
                    outputs=result["outputs"],
                    logs=(current.get("logs", []) + result["logs"])[-100:],
                )
                outcome["capability"] = config["capability"]
            elif action.action_type == "component.patch_state":
                node = nodes_by_id[action.target_id]
                current = state["nodes"].get(node.id)
                if not current:
                    raise EventProgramActionError(
                        f"Стан компонента «{node.name}» не ініціалізовано"
                    )
                current["state"].update(deepcopy(config["patch"]))
                outcome["patch"] = deepcopy(config["patch"])
            elif action.action_type in {"connection.disable", "connection.enable"}:
                enabled = action.action_type == "connection.enable"
                state.setdefault("connections", {}).setdefault(
                    action.target_id, {"enabled": bool(edges_by_id[action.target_id].enabled)}
                )["enabled"] = enabled
                outcome["enabled"] = enabled
            elif action.action_type == "event.emit":
                delay = float(config.get("delay_seconds", 0))
                scheduled_at = run.current_time + timedelta(seconds=delay)
                emitted = LabRunEvent(
                    run_id=run.id,
                    sequence=emitted_sequence,
                    scheduled_at=scheduled_at,
                    priority=40,
                    event_type=config["event_type"],
                    origin="program",
                    payload=deepcopy(config.get("payload", {})),
                )
                db.add(emitted)
                emitted_sequence += 1
                outcome.update(
                    emitted_event_type=config["event_type"],
                    scheduled_at=scheduled_at.isoformat(),
                )
            action_results.append(outcome)
        except EventProgramActionError as exc:
            outcome["status"] = "failed"
            outcome["error"] = str(exc)
            action_results.append(outcome)
            event.status = "failed"
            event.processed_at = datetime.now(UTC)
            event.result = {
                "program_id": program.id,
                "actions": action_results,
                "error": str(exc),
            }
            return True

    event.status = "processed"
    event.processed_at = datetime.now(UTC)
    event.result = {"program_id": program.id, "actions": action_results}
    return True


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


def _event_target_context(db: Session, run: LabRun, event: LabRunEvent) -> tuple[LabScenarioAssemblyMember | None, LabScenarioAssemblyNodeMap | None, LabNode | None]:
    if not run.assembly_version_id or not event.target_node_id:
        return None, None, None
    mapping = db.scalar(select(LabScenarioAssemblyNodeMap).where(LabScenarioAssemblyNodeMap.assembly_version_id == run.assembly_version_id, LabScenarioAssemblyNodeMap.composite_node_id == event.target_node_id).limit(1))
    if not mapping:
        return None, None, None
    return db.get(LabScenarioAssemblyMember, mapping.member_id), mapping, db.get(LabNode, event.target_node_id)


def _activation_matches_target(activation: LabProcessSetWorkflow, member: LabScenarioAssemblyMember, target_member: LabScenarioAssemblyMember | None, target_map: LabScenarioAssemblyNodeMap | None, target_node: LabNode | None, requested_alias: str | None) -> bool:
    if requested_alias:
        return member.alias == requested_alias
    if activation.scope_kind == "jurisdiction":
        return True
    if activation.scope_kind == "actor":
        return target_member is None or target_member.id == member.id
    if not target_member or target_member.id != member.id:
        return False
    if activation.scope_kind == "asset_instance":
        return bool(target_map and activation.scope_ref in {target_map.source_node_key, target_map.qualified_ref})
    if activation.scope_kind == "asset_class":
        return bool(target_node and target_node.component_type_id == activation.scope_ref)
    return False


def _route_event_to_processes(db: Session, run: LabRun, event: LabRunEvent) -> list[LabWorkflowInstance]:
    if not run.assembly_version_id:
        return []
    bindings = list(db.scalars(select(LabScenarioProcessBinding).where(LabScenarioProcessBinding.assembly_version_id == run.assembly_version_id)))
    if not bindings:
        return []
    activations = list(db.scalars(select(LabProcessSetWorkflow).where(LabProcessSetWorkflow.process_set_version_id.in_([item.process_set_version_id for item in bindings]), LabProcessSetWorkflow.start_event_type == event.event_type, LabProcessSetWorkflow.enabled.is_(True)).order_by(LabProcessSetWorkflow.priority, LabProcessSetWorkflow.id)))
    bindings_by_set: dict[str, list[LabScenarioProcessBinding]] = {}
    for binding in bindings:
        bindings_by_set.setdefault(binding.process_set_version_id, []).append(binding)
    target_member, target_map, target_node = _event_target_context(db, run, event)
    requested_alias = (event.payload or {}).get("_target_member_alias")
    correlation_id = (event.payload or {}).get("_correlation_id") or event.id
    started: list[LabWorkflowInstance] = []
    next_sequence = _next_event_sequence(db, run.id)
    for activation in activations:
        for binding in bindings_by_set.get(activation.process_set_version_id, []):
            member = db.get(LabScenarioAssemblyMember, binding.member_id)
            if not member or not _activation_matches_target(activation, member, target_member, target_map, target_node, requested_alias):
                continue
            existing = db.scalar(select(LabWorkflowInstance).where(LabWorkflowInstance.run_id == run.id, LabWorkflowInstance.workflow_version_id == activation.workflow_version_id, LabWorkflowInstance.assembly_member_id == member.id, LabWorkflowInstance.correlation_id == correlation_id).limit(1))
            if existing:
                continue
            starts = list(db.scalars(select(LabWorkflowNode).where(LabWorkflowNode.workflow_version_id == activation.workflow_version_id, LabWorkflowNode.block_type.in_(["start", "start_event"])).order_by(LabWorkflowNode.node_key)))
            start = next((candidate for candidate in starts if not (candidate.config or {}).get("parent_subprocess")), None)
            instance = LabWorkflowInstance(run_id=run.id, workflow_version_id=activation.workflow_version_id, status="running", current_node_id=start.id if start else None, variables={"scenario_id": run.scenario_id, "participant_alias": member.alias, "owner_entity_id": member.entity_id, "start_event": event.event_type, "start_mode": activation.start_mode}, assembly_member_id=member.id, process_set_version_id=activation.process_set_version_id, trigger_event_id=event.id, correlation_id=correlation_id, target_ref=target_map.qualified_ref if target_map else requested_alias)
            db.add(instance); db.flush()
            if start:
                db.add(LabWorkflowToken(instance_id=instance.id, node_id=start.id, status="active", entered_at=run.current_time, data={"event_id": event.id, "activation_id": activation.id}))
            workflow = db.get(LabWorkflowVersion, activation.workflow_version_id)
            for emitted in (workflow.settings or {}).get("on_start_emit", []) if workflow else []:
                db.add(LabRunEvent(run_id=run.id, sequence=next_sequence, scheduled_at=run.current_time, priority=30, event_type=emitted["event_type"], origin="workflow", payload={"_correlation_id": correlation_id, "_source_member_alias": member.alias, "_target_member_alias": emitted.get("target_member_alias"), "_phase": "coordination", "_evidence": "derived"}))
                next_sequence += 1
            started.append(instance)
    return started


WAITING_BLOCKS = {
    "intermediate_catch_event",
    "service_task",
    "user_task",
    "manual_task",
    "script_task",
    "business_rule_task",
    "receive_task",
    # Compatibility with workflow definitions created before the BPMN migration.
    "event_trigger",
    "timer",
    "wait",
    "component_command",
    "resource_operation",
    "python_action",
    "metric_check",
    "manual_command",
}


def _workflow_graph(db: Session, instance: LabWorkflowInstance) -> tuple[dict[str, LabWorkflowNode], dict[str, list[LabWorkflowTransition]], dict[str, list[LabWorkflowTransition]]]:
    nodes = {
        node.id: node
        for node in db.scalars(
            select(LabWorkflowNode).where(
                LabWorkflowNode.workflow_version_id == instance.workflow_version_id
            )
        )
    }
    outgoing: dict[str, list[LabWorkflowTransition]] = {}
    incoming: dict[str, list[LabWorkflowTransition]] = {}
    for flow in db.scalars(
        select(LabWorkflowTransition)
        .where(LabWorkflowTransition.workflow_version_id == instance.workflow_version_id)
        .order_by(LabWorkflowTransition.priority, LabWorkflowTransition.id)
    ):
        outgoing.setdefault(flow.source_node_id, []).append(flow)
        incoming.setdefault(flow.target_node_id, []).append(flow)
    return nodes, outgoing, incoming


def _condition_matches(expression: str, instance: LabWorkflowInstance, state: dict) -> bool:
    if not expression or expression.strip() in {"True", "true"}:
        return True
    if expression.strip() in {"False", "false"}:
        return False
    try:
        return bool(
            eval(
                expression,
                {"__builtins__": {}},
                {"variables": instance.variables, "state": state},
            )
        )
    except Exception:
        return False


def _complete_token(token: LabWorkflowToken, now: datetime) -> None:
    token.status = "completed"
    token.exited_at = now


def _create_token(db: Session, instance: LabWorkflowInstance, node_id: str, run: LabRun, data: dict | None = None) -> LabWorkflowToken:
    token = LabWorkflowToken(
        instance_id=instance.id,
        node_id=node_id,
        status="active",
        entered_at=run.current_time,
        data=data or {},
    )
    db.add(token)
    db.flush()
    node = db.get(LabWorkflowNode, node_id)
    config = node.config or {} if node else {}
    if node and config.get("event_definition") == "timer":
        due = _timer_due(run.current_time, config.get("timer_kind"), config.get("timer_value"))
        if due is not None:
            db.add(
                LabRunEvent(
                    run_id=run.id,
                    sequence=_next_event_sequence(db, run.id),
                    scheduled_at=due,
                    priority=50,
                    event_type=config.get("event_type") or f"timer.{node.node_key}",
                    origin="workflow_timer",
                    payload={"_correlation_id": instance.correlation_id, "_workflow_token_id": token.id, "_phase": "timer", "_evidence": "derived"},
                )
            )
    return token


def _timer_due(now: datetime, timer_kind: str | None, timer_value: str | None) -> datetime | None:
    if not timer_value:
        return None
    if timer_kind == "timeDate":
        try:
            value = datetime.fromisoformat(timer_value.replace("Z", "+00:00"))
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value
        except ValueError:
            return None
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", timer_value)
    if not match:
        return None
    days, hours, minutes, seconds = match.groups()
    return now + timedelta(days=int(days or 0), hours=int(hours or 0), minutes=int(minutes or 0), seconds=float(seconds or 0))


def schedule_timer_start_events(db: Session, run: LabRun) -> int:
    """Create subscriptions for top-level BPMN Timer Start Events in an assembly."""
    if not run.assembly_version_id:
        return 0
    bindings = list(
        db.scalars(
            select(LabScenarioProcessBinding).where(
                LabScenarioProcessBinding.assembly_version_id == run.assembly_version_id
            )
        )
    )
    if not bindings:
        return 0
    sequence = _next_event_sequence(db, run.id)
    created = 0
    for binding in bindings:
        member = db.get(LabScenarioAssemblyMember, binding.member_id)
        activations = db.scalars(
            select(LabProcessSetWorkflow).where(
                LabProcessSetWorkflow.process_set_version_id == binding.process_set_version_id,
                LabProcessSetWorkflow.enabled.is_(True),
            )
        )
        for activation in activations:
            start = db.scalar(
                select(LabWorkflowNode)
                .where(
                    LabWorkflowNode.workflow_version_id == activation.workflow_version_id,
                    LabWorkflowNode.block_type == "start_event",
                )
                .order_by(LabWorkflowNode.node_key)
            )
            config = start.config or {} if start else {}
            if (
                not start
                or config.get("parent_subprocess")
                or config.get("event_definition") != "timer"
            ):
                continue
            due = _timer_due(
                run.current_time, config.get("timer_kind"), config.get("timer_value")
            )
            if due is None:
                continue
            db.add(
                LabRunEvent(
                    run_id=run.id,
                    sequence=sequence,
                    scheduled_at=due,
                    priority=50,
                    event_type=activation.start_event_type
                    or config.get("event_type")
                    or f"timer.{start.node_key}",
                    origin="workflow_timer_start",
                    payload={
                        "_target_member_alias": member.alias if member else None,
                        "_timer_start_node": start.node_key,
                        "_phase": "timer",
                        "_evidence": "derived",
                    },
                )
            )
            sequence += 1
            created += 1
    return created


def complete_manual_workflow_task(
    db: Session,
    run: LabRun,
    token: LabWorkflowToken,
    *,
    completed_by: str,
    result: dict | None = None,
) -> LabWorkflowInstance:
    """Complete a BPMN User/Manual Task and continue by Sequence Flow."""
    instance = db.get(LabWorkflowInstance, token.instance_id)
    node = db.get(LabWorkflowNode, token.node_id)
    if not instance or instance.run_id != run.id:
        raise ValueError("Workflow task does not belong to this run")
    if token.status != "active" or not node or node.block_type not in {
        "user_task",
        "manual_task",
    }:
        raise ValueError("Only an active BPMN User Task or Manual Task can be completed")
    _, outgoing, _ = _workflow_graph(db, instance)
    token.data = {
        **(token.data or {}),
        "completed_manually": True,
        "completed_by": completed_by,
        "result": result or {},
    }
    _move_token_along(db, run, instance, token, outgoing.get(node.id, []))
    instance.variables = {
        **(instance.variables or {}),
        "last_manual_task": node.node_key,
        "last_manual_result": result or {},
    }
    db.flush()
    _settle_workflow_tokens(db, run, instance, run.state or {})
    return instance


def _emit_workflow_event(db: Session, run: LabRun, instance: LabWorkflowInstance, node: LabWorkflowNode) -> None:
    event_type = (node.config or {}).get("event_type")
    if not event_type:
        return
    member = db.get(LabScenarioAssemblyMember, instance.assembly_member_id) if instance.assembly_member_id else None
    db.add(
        LabRunEvent(
            run_id=run.id,
            sequence=_next_event_sequence(db, run.id),
            scheduled_at=run.current_time,
            priority=40,
            event_type=event_type,
            origin="workflow",
            payload={
                "_correlation_id": instance.correlation_id,
                "_source_member_alias": member.alias if member else None,
                "_target_member_alias": (node.config or {}).get("target_member_alias"),
                "_phase": "coordination",
                "_evidence": "derived",
            },
        )
    )


def _move_token_along(
    db: Session,
    run: LabRun,
    instance: LabWorkflowInstance,
    token: LabWorkflowToken,
    flows: list[LabWorkflowTransition],
    *,
    event_id: str | None = None,
) -> None:
    _complete_token(token, run.current_time)
    for flow in flows:
        _create_token(
            db,
            instance,
            flow.target_node_id,
            run,
            {"event_id": event_id, "sequence_flow_id": flow.id},
        )


def _settle_workflow_tokens(db: Session, run: LabRun, instance: LabWorkflowInstance, state: dict) -> None:
    """Advance all non-wait states until the process reaches stable wait points."""
    nodes, outgoing, incoming = _workflow_graph(db, instance)
    for _ in range(200):
        active = list(
            db.scalars(
                select(LabWorkflowToken)
                .where(
                    LabWorkflowToken.instance_id == instance.id,
                    LabWorkflowToken.status == "active",
                )
                .order_by(LabWorkflowToken.entered_at, LabWorkflowToken.id)
            )
        )
        if not active:
            instance.status = "completed"
            instance.current_node_id = None
            return
        progressed = False
        for token in active:
            node = nodes.get(token.node_id)
            if not node:
                _complete_token(token, run.current_time)
                progressed = True
                continue
            block = node.block_type
            if block in {"end_event", "success", "failure"}:
                _complete_token(token, run.current_time)
                progressed = True
                continue
            if block in WAITING_BLOCKS and (
                (node.config or {}).get("event_type")
                or (node.config or {}).get("capability")
            ):
                continue
            if block in {"intermediate_throw_event", "send_task"}:
                _emit_workflow_event(db, run, instance, node)
            flows = outgoing.get(node.id, [])
            if block in {"exclusive_gateway", "condition"}:
                selected = [flow for flow in flows if _condition_matches(flow.condition_code, instance, state)]
                flows = selected[:1]
            elif block == "inclusive_gateway":
                flows = [flow for flow in flows if _condition_matches(flow.condition_code, instance, state)]
            elif block in {"parallel_gateway", "parallel_split", "join"} and len(incoming.get(node.id, [])) > 1:
                arrivals = [candidate for candidate in active if candidate.node_id == node.id]
                if len(arrivals) < len(incoming[node.id]):
                    continue
                for extra in arrivals[1:]:
                    _complete_token(extra, run.current_time)
            _move_token_along(db, run, instance, token, flows)
            progressed = True
        db.flush()
        if not progressed:
            current = list(
                db.scalars(
                    select(LabWorkflowToken)
                    .where(
                        LabWorkflowToken.instance_id == instance.id,
                        LabWorkflowToken.status == "active",
                    )
                    .order_by(LabWorkflowToken.entered_at, LabWorkflowToken.id)
                )
            )
            instance.status = "running"
            instance.current_node_id = current[0].node_id if current else None
            return
    instance.status = "failed"
    instance.variables = {**(instance.variables or {}), "workflow_error": "automatic BPMN traversal exceeded 200 steps"}


def _token_accepts_event(node: LabWorkflowNode, event: LabRunEvent) -> bool:
    config = node.config or {}
    expected = config.get("event_type") or config.get("capability")
    return bool(expected and expected == event.event_type)


def _trigger_boundary_events(db: Session, run: LabRun, instance: LabWorkflowInstance, event: LabRunEvent, nodes: dict[str, LabWorkflowNode]) -> bool:
    active = list(db.scalars(select(LabWorkflowToken).where(LabWorkflowToken.instance_id == instance.id, LabWorkflowToken.status == "active")))
    active_keys = {nodes[token.node_id].node_key for token in active if token.node_id in nodes}
    triggered = False
    for boundary in nodes.values():
        config = boundary.config or {}
        if boundary.block_type != "boundary_event" or config.get("attached_to_ref") not in active_keys or not _token_accepts_event(boundary, event):
            continue
        if config.get("cancel_activity", True):
            for token in active:
                if nodes.get(token.node_id) and nodes[token.node_id].node_key == config.get("attached_to_ref"):
                    _complete_token(token, run.current_time)
        _create_token(db, instance, boundary.id, run, {"event_id": event.id, "boundary": True})
        triggered = True
    return triggered


def _trigger_event_subprocesses(db: Session, run: LabRun, instance: LabWorkflowInstance, event: LabRunEvent, nodes: dict[str, LabWorkflowNode]) -> bool:
    triggered = False
    for start in nodes.values():
        config = start.config or {}
        if start.block_type != "start_event" or not config.get("parent_subprocess") or not _token_accepts_event(start, event):
            continue
        if config.get("is_interrupting", True):
            for token in db.scalars(select(LabWorkflowToken).where(LabWorkflowToken.instance_id == instance.id, LabWorkflowToken.status == "active")):
                _complete_token(token, run.current_time)
        _create_token(db, instance, start.id, run, {"event_id": event.id, "event_subprocess": config["parent_subprocess"]})
        triggered = True
    return triggered


def _advance_workflows(db: Session, run: LabRun, event: LabRunEvent, state: dict) -> list[str]:
    started = _route_event_to_processes(db, run, event)
    instances = list(db.scalars(select(LabWorkflowInstance).where(LabWorkflowInstance.run_id == run.id).order_by(LabWorkflowInstance.id)))
    advanced: list[str] = []
    for instance in instances:
        if instance in started:
            _settle_workflow_tokens(db, run, instance, state)
            advanced.append(instance.id)
            continue
        if instance.status != "running":
            continue
        nodes, outgoing, _ = _workflow_graph(db, instance)
        changed = _trigger_event_subprocesses(db, run, instance, event, nodes)
        changed = _trigger_boundary_events(db, run, instance, event, nodes) or changed
        active = list(db.scalars(select(LabWorkflowToken).where(LabWorkflowToken.instance_id == instance.id, LabWorkflowToken.status == "active")))
        for token in active:
            node = nodes.get(token.node_id)
            requested_token = (event.payload or {}).get("_workflow_token_id")
            if requested_token and requested_token != token.id:
                continue
            if not node or not _token_accepts_event(node, event):
                continue
            token.data = {
                **(token.data or {}),
                "completed_by_event": event.event_type,
                "target_ref": (node.config or {}).get("target_ref"),
                "capability": (node.config or {}).get("capability"),
            }
            _move_token_along(db, run, instance, token, outgoing.get(node.id, []), event_id=event.id)
            instance.variables = {**(instance.variables or {}), "last_event": event.event_type, "phase": (node.config or {}).get("phase", "process")}
            changed = True
        if changed:
            db.flush()
            _settle_workflow_tokens(db, run, instance, state)
            advanced.append(instance.id)
    return advanced


def _advance_workflow(db: Session, run: LabRun, event: LabRunEvent, state: dict) -> str | None:
    """Compatibility wrapper for callers that still expect one workflow id."""
    advanced = _advance_workflows(db, run, event, state)
    return advanced[0] if advanced else None


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
        recorded_outputs = {
            key: round(float(value), 6)
            for key, value in node_state.get("outputs", {}).items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
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
            **recorded_outputs,
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
    "failure", "external_damage", "generation_attack", "substation_attack", "transmission_attack", "trip", "line_fault", "distribution_fault", "substation_fault", "interconnector_trip", "corridor_trip",
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
        "max_affected_customers": max(
            (
                int(node.parameters.get("affected_customers", 0))
                for node in nodes
                if node.id in failed_nodes
            ),
            default=0,
        ),
        "minimum_frequency_hz": min(item["frequency_hz"] for item in metrics_trace),
        "minimum_voltage_pu": min(item["voltage_pu"] for item in metrics_trace),
        "black_system": any(item["black_system"] for item in metrics_trace),
    }
    event_types = set(observed["processed_event_types"])
    predicates = {
        "damaged_assets": lambda expected: observed["failed_assets"] >= int(expected),
        "critical_impact": lambda expected: not expected or observed["max_unserved_mw"] > 0 or observed["max_affected_customers"] > 0,
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
        "model_scoped_targets": all(
            not item["target_node_id"] or item["target_node_id"] in {node.id for node in nodes}
            for item in trace
        ),
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
        if not run.assembly_version_id and workflow_version_id and not db.scalar(select(LabWorkflowInstance).where(LabWorkflowInstance.run_id == run.id)):
            db.add(LabWorkflowInstance(run_id=run.id, workflow_version_id=workflow_version_id, status="ready", variables={"scenario_id": scenario.id}))
        script_version = db.get(LabScriptVersion, scenario.configuration.get("scenario_script_version_id"))
        if script_version:
            parameters = deepcopy(scenario.configuration)
            templates = list(
                db.scalars(
                    select(LabScenarioEventTemplate)
                    .where(LabScenarioEventTemplate.scenario_id == scenario.id)
                    .order_by(
                        LabScenarioEventTemplate.offset_seconds,
                        LabScenarioEventTemplate.priority,
                        LabScenarioEventTemplate.id,
                    )
                )
            )
            invalid_offset = next(
                (
                    item
                    for item in templates
                    if isinstance(item.offset_seconds, bool)
                    or not isinstance(item.offset_seconds, int)
                    or item.offset_seconds < 0
                ),
                None,
            )
            if invalid_offset:
                raise RuntimeError(
                    f"Scenario event {invalid_offset.id} has an invalid offset_seconds"
                )
            parameters["script_events"] = [
                {
                    "offset_seconds": item.offset_seconds,
                    "event_type": item.event_type,
                    "payload": deepcopy(item.payload),
                    "target": item.target_node_id,
                    "priority": item.priority,
                    "phase": item.phase,
                    "title": item.title,
                    "evidence": item.evidence_kind,
                }
                for item in templates
            ]
            result = execute_script(
                script_version.code,
                "before_start",
                {
                    "time": run.current_time.isoformat(),
                    "parameters": parameters,
                    "state": {},
                    "inputs": {},
                    "seed": run.seed,
                    "snapshot": state,
                },
            )
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
    all_edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == run.model_version_id)))
    state = deepcopy(run.state)
    edges = _effective_edges(all_edges, state)
    nodes = _ordered_nodes(raw_nodes, edges, respect_enabled=False)
    component_step = min((types[n.component_type_id].tick_seconds for n in nodes), default=3600)
    # Playback may deliberately aggregate many physical ticks into one large dt.
    # The next scheduled event still forms a hard boundary below.
    step_seconds = max_step_seconds if max_step_seconds else component_step
    next_tick = run.current_time + timedelta(seconds=max(.001, step_seconds))
    if event and event.scheduled_at <= next_tick:
        run.current_time = event.scheduled_at
        programmed = _execute_event_program(
            db, run, event, state, raw_nodes, all_edges, types
        )
        if not programmed:
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
        # Connection actions are run-local and take effect at the same model timestamp.
        edges = _effective_edges(all_edges, state)
        nodes = _ordered_nodes(raw_nodes, edges, respect_enabled=False)
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
