"""Strict, deterministic L1 historical qualification replay.

The legacy Model Lab replay applies a short list of raw events directly to every
matching component.  This module deliberately uses a narrower and safer contract:
every state change must be produced by a declared capability, every reported fact
must cite a source, and process steps/checkpoints are verified during the replay.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any
from xml.etree import ElementTree

INPUT_ORIGINS = {
    "external_event",
    "planned_process_start",
    "observed_internal_fact",
}
EVIDENCE_KINDS = {"reported", "derived", "assumed"}
TIMELINE_KINDS = {"input", "process_action", "derived"}
BPMN_NAMESPACE = "http://www.omg.org/spec/BPMN/20100524/MODEL"
DMN_NAMESPACE = "https://www.omg.org/spec/DMN/20191111/MODEL/"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _conditions_hold(
    conditions: list[dict[str, Any]],
    object_states: dict[str, str],
    facts: set[str],
    metrics: dict[str, Any],
) -> bool:
    for condition in conditions:
        if "object" in condition:
            if object_states.get(condition["object"]) != condition.get("state"):
                return False
        elif "fact" in condition:
            if condition["fact"] not in facts:
                return False
        elif "metric" in condition:
            actual = metrics.get(condition["metric"])
            if "equals" in condition and actual != condition["equals"]:
                return False
            if "at_least" in condition and (
                actual is None or float(actual) < float(condition["at_least"])
            ):
                return False
        else:
            return False
    return True


def validate_qualification_package(package: dict[str, Any]) -> list[str]:
    """Validate the static contract without executing its timeline."""

    errors: list[str] = []
    if not isinstance(package.get("id"), str) or not package.get("id"):
        errors.append("qualification package id is required")
    if not isinstance(package.get("scenario_id"), str) or not package.get("scenario_id"):
        errors.append("qualification package scenario_id is required")
    if package.get("schema_version") not in {1, 2}:
        errors.append("qualification package schema_version must be 1 or 2")
    if package.get("level") != 1:
        errors.append("qualification package must use generalized level 1")
    if package.get("boundary") != "stabilization":
        errors.append("qualification package boundary must be stabilization")
    if package.get("run_policy", "pause") not in {"pause", "stop", "continue_failed"}:
        errors.append("qualification package has an invalid run policy")

    sources = {item.get("id") for item in package.get("sources", [])}
    object_items = package.get("objects", [])
    process_items = package.get("processes", [])
    situation_items = package.get("situations", [])
    objects = {item.get("id"): item for item in object_items}
    processes = {item.get("id"): item for item in process_items}
    situations = {item.get("id"): item for item in situation_items}
    if len(objects) != len(object_items) or None in objects:
        errors.append("qualification objects must have unique non-empty ids")
    if len(processes) != len(process_items) or None in processes:
        errors.append("qualification processes must have unique non-empty ids")
    if len(situations) != len(situation_items) or None in situations:
        errors.append("qualification situations must have unique non-empty ids")

    model = package.get("model")
    if package.get("schema_version") == 2 and not isinstance(model, dict):
        errors.append("schema version 2 requires an event-specific model")
    if isinstance(model, dict):
        expected_model_id = f"qualification-{package.get('scenario_id', '')}"
        if model.get("id") != expected_model_id:
            errors.append(
                f"event-specific model id must be {expected_model_id}"
            )
        if model.get("level") != package.get("level"):
            errors.append("event-specific model level must match the package level")
        node_items = model.get("nodes", [])
        edge_items = model.get("edges", [])
        nodes = {item.get("id"): item for item in node_items}
        edges = {item.get("id"): item for item in edge_items}
        if len(nodes) != len(node_items) or None in nodes:
            errors.append("event-specific model nodes must have unique non-empty ids")
        if len(edges) != len(edge_items) or None in edges:
            errors.append("event-specific model edges must have unique non-empty ids")
        if not nodes:
            errors.append("event-specific model must define nodes")
        for node_id, node in nodes.items():
            if not node.get("component_type_id"):
                errors.append(f"model node {node_id} has no component type")
            object_id = node.get("qualification_object_id")
            if object_id and object_id not in objects:
                errors.append(
                    f"model node {node_id} binds an unknown qualification object"
                )
        for edge_id, edge in edges.items():
            if edge.get("source") not in nodes or edge.get("target") not in nodes:
                errors.append(
                    f"model edge {edge_id} references a node outside the event model"
                )
        bound_nodes: set[str] = set()
        for object_id, definition in objects.items():
            model_node_id = definition.get("model_node_id")
            if not model_node_id:
                errors.append(
                    f"qualification object {object_id} is not bound to its event model"
                )
                continue
            if model_node_id not in nodes:
                errors.append(
                    f"qualification object {object_id} binds an unknown model node"
                )
                continue
            if model_node_id in bound_nodes:
                errors.append(
                    f"model node {model_node_id} is bound to more than one qualification object"
                )
            bound_nodes.add(model_node_id)
            declared_object = nodes[model_node_id].get("qualification_object_id")
            if declared_object != object_id:
                errors.append(
                    f"qualification object {object_id} and model node {model_node_id} do not bind each other"
                )

    try:
        dmn_root = ElementTree.fromstring(package.get("dmn_xml", ""))
    except (ElementTree.ParseError, TypeError):
        errors.append("qualification package does not contain valid DMN XML")
    else:
        decision_ids = {
            decision.get("id")
            for decision in dmn_root.findall(f".//{{{DMN_NAMESPACE}}}decision")
        }
        missing_decisions = sorted(set(situations) - decision_ids)
        if missing_decisions:
            errors.append(
                "DMN XML misses situations: " + ", ".join(missing_decisions)
            )
        for decision in dmn_root.findall(f".//{{{DMN_NAMESPACE}}}decision"):
            situation = situations.get(decision.get("id"))
            expression = decision.find(f".//{{{DMN_NAMESPACE}}}text")
            if situation and situation.get("all") and (
                expression is None
                or not (expression.text or "").strip()
                or (expression.text or "").strip() in {"true", "false"}
            ):
                errors.append(
                    f"DMN decision {decision.get('id')} must materialize its conditions"
                )

    if not sources:
        errors.append("qualification package must cite at least one source")
    if not objects:
        errors.append("qualification package must define at least one object")

    for object_id, definition in objects.items():
        states = set(definition.get("states", []))
        if definition.get("initial_state") not in states:
            errors.append(f"object {object_id} has an undeclared initial state")
        for capability, transitions in definition.get("capabilities", {}).items():
            if not transitions:
                errors.append(f"object {object_id} capability {capability} has no transitions")
            for transition in transitions:
                origins = transition.get("from", [])
                origins = [origins] if isinstance(origins, str) else origins
                if any(origin not in states for origin in origins):
                    errors.append(
                        f"object {object_id} capability {capability} has an unknown origin"
                    )
                if transition.get("to") not in states:
                    errors.append(
                        f"object {object_id} capability {capability} has an unknown target"
                    )

    for process_id, process in processes.items():
        step_items = process.get("steps", [])
        step_ids = {step.get("id") for step in step_items}
        if len(step_ids) != len(step_items) or None in step_ids:
            errors.append(f"process {process_id} steps must have unique non-empty ids")
        for step in step_items:
            step_id = step.get("id")
            unknown_predecessors = sorted(set(step.get("after", [])) - step_ids)
            if unknown_predecessors:
                errors.append(
                    f"process {process_id} step {step_id} has unknown predecessors: "
                    + ", ".join(unknown_predecessors)
                )
            target_id = step.get("target")
            capability = step.get("capability")
            if bool(target_id) != bool(capability):
                errors.append(
                    f"process {process_id} step {step_id} must declare target and capability together"
                )
            elif target_id:
                target = objects.get(target_id)
                if not target:
                    errors.append(
                        f"process {process_id} step {step_id} targets an unknown object"
                    )
                elif capability not in target.get("capabilities", {}):
                    errors.append(
                        f"process {process_id} step {step_id} uses undeclared capability {capability}"
                    )
        try:
            root = ElementTree.fromstring(process.get("bpmn_xml", ""))
        except (ElementTree.ParseError, TypeError):
            errors.append(f"process {process_id} does not contain valid BPMN XML")
            continue
        process_element = root.find(f".//{{{BPMN_NAMESPACE}}}process")
        if process_element is None or process_element.get("id") != process_id:
            errors.append(f"process {process_id} BPMN process id does not match")
            continue
        xml_ids = {
            element.get("id")
            for element in process_element.iter()
            if element.get("id")
        }
        missing = sorted(step_ids - xml_ids)
        if missing:
            errors.append(f"process {process_id} BPMN misses steps: {', '.join(missing)}")

    timeline_ids: set[str] = set()
    for item in package.get("timeline", []):
        item_id = item.get("id")
        if not item_id or item_id in timeline_ids:
            errors.append(f"timeline contains an empty or duplicate id: {item_id}")
        timeline_ids.add(item_id)
        entry_kind = item.get("entry_kind")
        if entry_kind not in TIMELINE_KINDS:
            errors.append(f"timeline item {item_id} has an invalid entry kind")
        if entry_kind == "input" and item.get("origin") not in INPUT_ORIGINS:
            errors.append(f"input timeline item {item_id} has an invalid origin")
        if entry_kind != "input" and item.get("origin") is not None:
            errors.append(f"non-input timeline item {item_id} cannot declare input origin")
        if entry_kind == "derived" and item.get("evidence") != "derived":
            errors.append(f"derived timeline item {item_id} must use derived evidence")
        if item.get("evidence") not in EVIDENCE_KINDS:
            errors.append(f"timeline item {item_id} has invalid evidence")
        if item.get("evidence") == "reported" and item.get("source") not in sources:
            errors.append(f"reported timeline item {item_id} must cite a package source")
        try:
            datetime.fromisoformat(item.get("at", ""))
        except ValueError:
            errors.append(f"timeline item {item_id} has an invalid timestamp")

        action = item.get("action")
        if action:
            target = objects.get(action.get("target"))
            capability = action.get("capability")
            if not target:
                errors.append(f"timeline item {item_id} targets an unknown object")
            elif capability not in target.get("capabilities", {}):
                errors.append(
                    f"timeline item {item_id} uses undeclared capability {capability}"
                )

        process_ref = item.get("process")
        if process_ref:
            process = processes.get(process_ref.get("id"))
            if not process:
                errors.append(f"timeline item {item_id} references an unknown process")
            elif process_ref.get("step") not in {
                step.get("id") for step in process.get("steps", [])
            }:
                errors.append(f"timeline item {item_id} references an unknown process step")
            else:
                step = next(
                    step
                    for step in process.get("steps", [])
                    if step.get("id") == process_ref.get("step")
                )
                if step.get("target") and (
                    not action
                    or action.get("target") != step.get("target")
                    or action.get("capability") != step.get("capability")
                ):
                    errors.append(
                        f"timeline item {item_id} action diverges from its BPMN step"
                    )

        for situation_id in item.get("confirm_situations", []):
            if situation_id not in situations:
                errors.append(f"timeline item {item_id} confirms an unknown situation")

    for situation_id, situation in situations.items():
        for condition in situation.get("all", []):
            if "object" in condition:
                target = objects.get(condition.get("object"))
                if not target or condition.get("state") not in target.get("states", []):
                    errors.append(
                        f"situation {situation_id} references an unknown object state"
                    )
            elif not ({"fact", "metric"} & set(condition)):
                errors.append(f"situation {situation_id} has an invalid condition")

    for checkpoint in package.get("checkpoints", []):
        if checkpoint.get("after") not in timeline_ids:
            errors.append(
                f"checkpoint {checkpoint.get('id')} references an unknown timeline item"
            )
    return errors


def _apply_capability(
    definition: dict[str, Any], current: str, capability: str
) -> tuple[str, str | None]:
    for transition in definition.get("capabilities", {}).get(capability, []):
        origins = transition.get("from", [])
        origins = [origins] if isinstance(origins, str) else origins
        if current in origins:
            return transition["to"], None
    return current, f"capability {capability} is not permitted from state {current}"


def replay_qualification_package(package: dict[str, Any]) -> dict[str, Any]:
    """Replay one immutable L1 package and return a complete verification report."""

    errors = validate_qualification_package(package)
    object_definitions = {item["id"]: item for item in package.get("objects", [])}
    object_states = {
        object_id: definition["initial_state"]
        for object_id, definition in object_definitions.items()
    }
    process_definitions = {item["id"]: item for item in package.get("processes", [])}
    situation_definitions = {item["id"]: item for item in package.get("situations", [])}
    resources = deepcopy(package.get("resources", {}))
    completed_steps: dict[str, list[str]] = {
        process_id: [] for process_id in process_definitions
    }
    confirmed_situations: list[str] = []
    facts: set[str] = set()
    metrics: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    checkpoint_results: list[dict[str, Any]] = []
    previous_time: datetime | None = None
    run_policy = package.get("run_policy", "pause")
    interrupted = False

    checkpoints_by_entry: dict[str, list[dict[str, Any]]] = {}
    for checkpoint in package.get("checkpoints", []):
        checkpoints_by_entry.setdefault(checkpoint["after"], []).append(checkpoint)

    for sequence, item in enumerate(package.get("timeline", []), 1):
        item_errors: list[str] = []
        try:
            current_time = datetime.fromisoformat(item["at"])
        except (KeyError, ValueError):
            current_time = previous_time
        if current_time and previous_time and current_time < previous_time:
            item_errors.append("timeline is not chronological")
        if current_time:
            previous_time = current_time

        process_ref = item.get("process")
        if process_ref and process_ref.get("id") in process_definitions:
            process_id = process_ref["id"]
            step_id = process_ref.get("step")
            step = next(
                (
                    candidate
                    for candidate in process_definitions[process_id].get("steps", [])
                    if candidate.get("id") == step_id
                ),
                None,
            )
            if step:
                missing = [
                    predecessor
                    for predecessor in step.get("after", [])
                    if predecessor not in completed_steps[process_id]
                ]
                if missing:
                    item_errors.append(
                        f"process step {step_id} misses predecessors: {', '.join(missing)}"
                    )
                action = item.get("action", {})
                if step.get("target") and step.get("target") != action.get("target"):
                    item_errors.append(f"process step {step_id} targets the wrong object")
                if step.get("capability") and step.get("capability") != action.get(
                    "capability"
                ):
                    item_errors.append(f"process step {step_id} uses the wrong capability")

        action_result: dict[str, Any] | None = None
        if item.get("action"):
            action = item["action"]
            target_id = action.get("target")
            capability = action.get("capability")
            definition = object_definitions.get(target_id)
            if definition:
                before = object_states[target_id]
                after, capability_error = _apply_capability(
                    definition, before, capability
                )
                if capability_error:
                    item_errors.append(capability_error)
                else:
                    object_states[target_id] = after
                expected_state = action.get("postcondition", {}).get("state")
                if expected_state is not None and object_states[target_id] != expected_state:
                    item_errors.append(
                        f"postcondition failed for {target_id}: expected {expected_state}"
                    )
                action_result = {
                    "target": target_id,
                    "capability": capability,
                    "before": before,
                    "after": object_states[target_id],
                    "postcondition_confirmed": not item_errors,
                }

        for operation in item.get("resource_operations", []):
            pool_id = operation.get("pool")
            pool = resources.get(pool_id)
            quantity = float(operation.get("quantity", 0))
            if not pool or quantity < 0:
                item_errors.append(f"invalid resource operation for {pool_id}")
                continue
            kind = operation.get("operation")
            if kind == "produce":
                pool["available"] = float(pool.get("available", 0)) + quantity
            elif kind == "reserve":
                if float(pool.get("available", 0)) < quantity:
                    item_errors.append(f"resource pool {pool_id} has insufficient capacity")
                else:
                    pool["available"] = float(pool.get("available", 0)) - quantity
                    pool["reserved"] = float(pool.get("reserved", 0)) + quantity
            elif kind == "consume":
                if float(pool.get("reserved", 0)) < quantity:
                    item_errors.append(f"resource pool {pool_id} has insufficient reserve")
                else:
                    pool["reserved"] = float(pool.get("reserved", 0)) - quantity
                    pool["consumed"] = float(pool.get("consumed", 0)) + quantity
            elif kind == "release":
                if float(pool.get("reserved", 0)) < quantity:
                    item_errors.append(f"resource pool {pool_id} cannot release capacity")
                else:
                    pool["reserved"] = float(pool.get("reserved", 0)) - quantity
                    pool["available"] = float(pool.get("available", 0)) + quantity
            else:
                item_errors.append(f"unsupported resource operation {kind}")

        metrics.update(item.get("metrics", {}))
        facts.add(item["id"])
        if item.get("fact"):
            facts.add(item["fact"])

        for situation_id in item.get("confirm_situations", []):
            situation = situation_definitions.get(situation_id)
            if situation and _conditions_hold(
                situation.get("all", []), object_states, facts, metrics
            ):
                if situation_id not in confirmed_situations:
                    confirmed_situations.append(situation_id)
            else:
                item_errors.append(f"situation {situation_id} was confirmed too early")

        if process_ref and process_ref.get("id") in completed_steps and not item_errors:
            step_id = process_ref.get("step")
            if step_id not in completed_steps[process_ref["id"]]:
                completed_steps[process_ref["id"]].append(step_id)

        errors.extend(f"{item.get('id')}: {message}" for message in item_errors)
        trace.append(
            {
                "sequence": sequence,
                "id": item.get("id"),
                "at": item.get("at"),
                "entry_kind": item.get("entry_kind"),
                "origin": item.get("origin"),
                "evidence": item.get("evidence"),
                "action": action_result,
                "situations": list(confirmed_situations),
                "process": deepcopy(process_ref),
                "object_states": deepcopy(object_states),
                "resources": deepcopy(resources),
                "metrics": deepcopy(metrics),
                "status": "failed" if item_errors else "completed",
            }
        )

        for checkpoint in checkpoints_by_entry.get(item.get("id"), []):
            checkpoint_errors: list[str] = []
            if not _conditions_hold(
                checkpoint.get("all", []), object_states, facts, metrics
            ):
                checkpoint_errors.append("checkpoint conditions are not satisfied")
            for assertion in checkpoint.get("process_steps", []):
                if assertion.get("step") not in completed_steps.get(
                    assertion.get("process"), []
                ):
                    checkpoint_errors.append(
                        f"process step {assertion.get('step')} is incomplete"
                    )
            errors.extend(
                f"checkpoint {checkpoint.get('id')}: {message}"
                for message in checkpoint_errors
            )
            checkpoint_results.append(
                {
                    "id": checkpoint.get("id"),
                    "after": checkpoint.get("after"),
                    "passed": not checkpoint_errors,
                }
            )
        if item_errors and run_policy in {"pause", "stop"}:
            interrupted = True
            break

    for process_id, process in process_definitions.items():
        required = {
            step["id"] for step in process.get("steps", []) if step.get("required", True)
        }
        missing = sorted(required - set(completed_steps[process_id]))
        if missing:
            errors.append(f"process {process_id} has incomplete steps: {', '.join(missing)}")

    final = package.get("expected_final", {})
    for object_id, expected_state in final.get("object_states", {}).items():
        if object_states.get(object_id) != expected_state:
            errors.append(
                f"final state of {object_id} is {object_states.get(object_id)}, "
                f"expected {expected_state}"
            )
    for situation_id in final.get("situations", []):
        if situation_id not in confirmed_situations:
            errors.append(f"final situation {situation_id} was not confirmed")

    for pool_id, pool in resources.items():
        if any(float(pool.get(field, 0)) < 0 for field in ("available", "reserved")):
            errors.append(f"resource pool {pool_id} has a negative balance")

    if errors:
        run_status = "continued_with_failures" if run_policy == "continue_failed" else (
            "stopped_failed" if run_policy == "stop" else "paused_failed"
        )
    else:
        run_status = "completed"

    result_without_checksum = {
        "package_id": package.get("id"),
        "passed": not errors,
        "run_status": run_status,
        "run_policy": run_policy,
        "interrupted": interrupted,
        "errors": errors,
        "object_states": object_states,
        "situations": confirmed_situations,
        "completed_process_steps": completed_steps,
        "resources": resources,
        "metrics": metrics,
        "checkpoints": checkpoint_results,
        "trace": trace,
    }
    checksum = hashlib.sha256(
        _canonical({"package": package, "result": result_without_checksum}).encode()
    ).hexdigest()
    return {**result_without_checksum, "checksum": checksum}
