"""Typed, versioned contracts shared by the editor, validator and runtime adapters."""

# ruff: noqa: E501

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.models import LabComponentType, LabEdge, LabMetricDefinition, LabNode

DOMAINS = {
    "electric.ac",
    "natural_gas",
    "water_steam",
    "thermal",
    "control",
    "staff",
    "maintenance",
    "emission",
    "legacy.energy",
}
DIRECTIONS = {"input", "output", "bidirectional"}
ROLES = {"potential", "flow", "stream", "signal", "availability"}

_SLUG = re.compile(r"[^a-z0-9_.-]+")


def stable_key(value: str, fallback: str) -> str:
    normalized = _SLUG.sub("-", (value or "").strip().lower()).strip("-")
    return normalized or fallback


def _legacy_domain(component: LabComponentType, port: dict[str, Any]) -> str:
    if port.get("domain"):
        return str(port["domain"])
    if component.category in {"gas", "resource"}:
        return "natural_gas"
    if component.category in {"generation", "substation", "line", "grid", "end_product"}:
        if component.id == "steam-plant" and port.get("direction") == "input":
            return "natural_gas"
        return "electric.ac"
    return str(port.get("flow_type") or "legacy.energy")


def normalized_ports(component: LabComponentType, overrides: dict | None = None) -> list[dict[str, Any]]:
    """Return the v2 contract while accepting legacy ``flow_type`` definitions."""
    patches = overrides or {}
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(component.ports or []):
        key = str(raw.get("key") or raw.get("id") or f"port-{index + 1}")
        port = {
            "key": key,
            "name": raw.get("name") or key.replace("_", " ").title(),
            "direction": raw.get("direction", "bidirectional"),
            "domain": _legacy_domain(component, raw),
            "role": raw.get("role", "flow"),
            "quantity": raw.get("quantity") or raw.get("variable") or "flow",
            "variable": raw.get("variable"),
            "unit": raw.get("unit", ""),
            "required": bool(raw.get("required", False)),
            "multiple": bool(raw.get("multiple", False)),
            "variables": list(raw.get("variables", [])),
            "capabilities": list(raw.get("capabilities", [])),
        }
        port.update(patches.get(key, {}))
        result.append(port)
    return result


def port_by_key(component: LabComponentType, key: str, overrides: dict | None = None) -> dict[str, Any] | None:
    return next((port for port in normalized_ports(component, overrides) if port["key"] == key), None)


def connection_diagnostics(
    source_component: LabComponentType,
    source_port_key: str,
    target_component: LabComponentType,
    target_port_key: str,
    *,
    source_overrides: dict | None = None,
    target_overrides: dict | None = None,
) -> list[str]:
    source = port_by_key(source_component, source_port_key, source_overrides)
    target = port_by_key(target_component, target_port_key, target_overrides)
    errors: list[str] = []
    if not source:
        return [f"Вихідний порт «{source_port_key}» не існує"]
    if not target:
        return [f"Вхідний порт «{target_port_key}» не існує"]
    if source["direction"] not in {"output", "bidirectional"}:
        errors.append(f"Порт «{source_port_key}» не передає потік назовні")
    if target["direction"] not in {"input", "bidirectional"}:
        errors.append(f"Порт «{target_port_key}» не приймає потік")
    if source["domain"] != target["domain"]:
        errors.append(f"Несумісні середовища: {source['domain']} → {target['domain']}")
    if source.get("quantity") and target.get("quantity") and source["quantity"] != target["quantity"]:
        # A domain connector can expose several variables. Quantity mismatch is a warning-level
        # detail for bidirectional/acausal connectors, but invalid for simple directed streams.
        if source["role"] == "stream" or target["role"] == "stream":
            errors.append(f"Несумісні фізичні величини: {source['quantity']} → {target['quantity']}")
    return errors


def validate_port_contract(component: LabComponentType) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for port in normalized_ports(component):
        if port["key"] in seen:
            errors.append(f"{component.name}: дубльований порт «{port['key']}»")
        seen.add(port["key"])
        if port["direction"] not in DIRECTIONS:
            errors.append(f"{component.name}.{port['key']}: невідомий напрям «{port['direction']}»")
        if port["domain"] not in DOMAINS:
            errors.append(f"{component.name}.{port['key']}: невідоме середовище «{port['domain']}»")
        if port["role"] not in ROLES:
            errors.append(f"{component.name}.{port['key']}: невідома роль «{port['role']}»")
    return errors


def observable_catalog(
    nodes: Iterable[LabNode],
    components: dict[str, LabComponentType],
    metrics: Iterable[LabMetricDefinition],
    edges: Iterable[LabEdge] = (),
) -> list[dict[str, Any]]:
    """Build addresses from the graph itself; the frontend never chooses metric IDs."""
    metric_map = {item.id: item for item in metrics}
    catalog: list[dict[str, Any]] = []
    common = {
        "online": ("Стан", "", "state.online", "boolean"),
        "voltage_pu": ("Напруга", "pu", "metrics.node_metrics.{node_id}.voltage_pu", "number"),
        "frequency_hz": ("Частота", "Hz", "metrics.node_metrics.{node_id}.frequency_hz", "number"),
    }
    for node in nodes:
        component = components.get(node.component_type_id)
        if not component:
            continue
        keys: dict[str, tuple[str, str, str, str]] = {"online": common["online"]}
        ports = normalized_ports(component, node.port_overrides)
        for port in ports:
            if port["domain"] == "electric.ac":
                keys.update({key: common[key] for key in ("voltage_pu", "frequency_hz")})
                if port["direction"] in {"output", "bidirectional"}:
                    keys["electric_power_mw"] = ("Активна потужність", "MW", "metrics.node_metrics.{node_id}.electric_power_mw", "number")
                    keys["reactive_power_mvar"] = ("Реактивна потужність", "Mvar", "metrics.node_metrics.{node_id}.reactive_power_mvar", "number")
                if port["direction"] in {"input", "bidirectional"}:
                    keys["demand_mw"] = ("Навантаження", "MW", "metrics.node_metrics.{node_id}.demand_mw", "number")
            for variable in port.get("variables", []):
                metric_key = str(variable.get("key") or variable.get("id"))
                if metric_key:
                    keys[metric_key] = (
                        variable.get("name", metric_key), variable.get("unit", ""),
                        variable.get("path", f"outputs.{metric_key}"), variable.get("value_type", "number"),
                    )
        output_key = str(node.parameters.get("output_key") or "")
        if output_key:
            spec = metric_map.get(output_key)
            source_port = next((port for port in ports if port.get("variable") == output_key), None)
            keys[output_key] = (
                spec.name if spec else source_port.get("name", output_key) if source_port else output_key,
                spec.unit if spec else source_port.get("unit", "") if source_port else "",
                f"outputs.{output_key}", "number",
            )
        if node.parameters.get("mode") in {"load", "refrigerator", "led"}:
            keys["demand_mw"] = ("Навантаження", "MW", "metrics.node_metrics.{node_id}.demand_mw", "number")
        for metric_key, (name, unit, path, value_type) in keys.items():
            override = node.observable_overrides.get(metric_key, {})
            if override.get("enabled") is False:
                continue
            catalog.append({
                "address": f"component:{node.instance_key or node.id}:{metric_key}",
                "scope": "component",
                "target_id": node.id,
                "target_key": node.instance_key or node.id,
                "target_name": node.name,
                "metric_key": metric_key,
                "name": override.get("name", name),
                "unit": override.get("unit", unit),
                "value_type": value_type,
                "path": path.format(node_id=node.id),
                "recording": override.get("recording", "aggregate"),
                "aggregation": override.get("aggregation", "last"),
            })
    for edge in edges:
        catalog.append({
            "address": f"connection:{edge.connection_key or edge.id}:flow",
            "scope": "connection",
            "target_id": edge.id,
            "target_key": edge.connection_key or edge.id,
            "target_name": edge.connection_key or edge.id,
            "metric_key": "flow",
            "name": "Потік у зв’язку",
            "unit": edge.parameters.get("unit", "MW" if edge.domain == "electric.ac" else ""),
            "value_type": "number",
            "path": f"flows.{edge.id}.value",
            "recording": "aggregate",
            "aggregation": "last",
        })
    return catalog
