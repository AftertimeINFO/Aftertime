"""Database materialization for immutable event-specific qualification models."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, insert

from app.lab_seed import (
    COMPONENTS,
    EVENT_COMPONENTS,
    EVENT_COMPONENT_PARAMETERS,
    EVENT_GENERATION_SCRIPT,
    SCRIPT,
    component_ports,
)


def materialize_event_model(connection: sa.Connection, package: dict[str, Any]) -> None:
    """Replace one published system model with the topology embedded in its package."""

    model = package["model"]
    model_id = model["id"]
    tables = set(sa.inspect(connection).get_table_names())
    required = {
        "lab_component_types",
        "lab_model_versions",
        "lab_nodes",
        "lab_edges",
        "lab_qualification_definitions",
    }
    if not required <= tables or not connection.scalar(
        sa.text("SELECT 1 FROM lab_model_versions WHERE id = :id"), {"id": model_id}
    ):
        return

    component_table = sa.table(
        "lab_component_types",
        sa.column("id", sa.String), sa.column("name", sa.String),
        sa.column("category", sa.String), sa.column("level", sa.String),
        sa.column("description", sa.Text), sa.column("parameters_schema", JSONB),
        sa.column("initial_state", JSONB), sa.column("ports", JSONB),
        sa.column("python_code", sa.Text), sa.column("tick_seconds", sa.Float),
        sa.column("repairable", sa.Boolean), sa.column("version", sa.Integer),
    )
    component_specs = {item[0]: item for item in [*COMPONENTS, *EVENT_COMPONENTS]}
    for component_id in sorted({item["component_type_id"] for item in model["nodes"]}):
        cid, name, category, level, mode, output, capacity, efficiency = component_specs[component_id]
        parameters = {
            "mode": mode, "capacity_mw": capacity, "efficiency": efficiency,
            **EVENT_COMPONENT_PARAMETERS.get(cid, {}),
        }
        values = {
            "id": cid, "name": name, "category": category, "level": level,
            "description": "Тип компонента для окремих моделей історичних подій",
            "parameters_schema": parameters, "initial_state": {"online": True},
            "ports": component_ports(cid, category, output),
            "python_code": EVENT_GENERATION_SCRIPT if cid in EVENT_COMPONENT_PARAMETERS else SCRIPT,
            "tick_seconds": 3600, "repairable": True, "version": 3,
        }
        statement = insert(component_table).values(**values)
        connection.execute(statement.on_conflict_do_update(
            index_elements=[component_table.c.id],
            set_={key: value for key, value in values.items() if key != "id"},
        ))

    connection.execute(sa.text("DELETE FROM lab_edges WHERE model_version_id = :id"), {"id": model_id})
    connection.execute(sa.text("DELETE FROM lab_nodes WHERE model_version_id = :id"), {"id": model_id})
    objects = {item["id"]: item for item in package["objects"]}

    node_table = sa.table(
        "lab_nodes",
        sa.column("id", sa.String), sa.column("model_version_id", sa.String),
        sa.column("component_type_id", sa.String), sa.column("name", sa.String),
        sa.column("parent_node_id", sa.String), sa.column("x", sa.Float), sa.column("y", sa.Float),
        sa.column("parameters", JSONB), sa.column("initial_state", JSONB),
        sa.column("python_code", sa.Text), sa.column("refinement_contract", JSONB),
        sa.column("instance_key", sa.String), sa.column("port_overrides", JSONB),
        sa.column("observable_overrides", JSONB),
    )
    node_rows = []
    for node in model["nodes"]:
        cid, _, _, _, mode, output, default_capacity, efficiency = component_specs[node["component_type_id"]]
        definition = objects.get(node.get("qualification_object_id"))
        parameters = {
            "mode": mode, "capacity_mw": node.get("capacity_mw", default_capacity),
            "efficiency": efficiency, "output_key": output,
            **EVENT_COMPONENT_PARAMETERS.get(cid, {}),
            "qualification_scenario": package["scenario_id"],
            "qualification_object_id": node.get("qualification_object_id"),
            **node.get("parameters", {}),
        }
        node_rows.append({
            "id": node["id"], "model_version_id": model_id,
            "component_type_id": node["component_type_id"], "name": node["name"],
            "parent_node_id": None, "x": float(node["x"]), "y": float(node["y"]),
            "parameters": parameters,
            "initial_state": {
                "online": node.get("initial_online", True),
                "qualification_state": (definition or {}).get("initial_state", "not_applicable"),
            },
            "python_code": None,
            "refinement_contract": {
                "boundary_ports": ["in", "out"], "time_scale": "hybrid", "tolerance": .001,
                "capabilities": sorted((definition or {}).get("capabilities", {})),
                "scenario_model": package["scenario_id"], "event_model_id": model_id,
            },
            "instance_key": node["id"], "port_overrides": {}, "observable_overrides": {},
        })
    connection.execute(node_table.insert(), node_rows)

    edge_table = sa.table(
        "lab_edges",
        sa.column("id", sa.String), sa.column("model_version_id", sa.String),
        sa.column("source_node_id", sa.String), sa.column("source_port", sa.String),
        sa.column("target_node_id", sa.String), sa.column("target_port", sa.String),
        sa.column("flow_type", sa.String), sa.column("parameters", JSONB),
        sa.column("connection_key", sa.String), sa.column("domain", sa.String),
        sa.column("enabled", sa.Boolean),
    )
    connection.execute(edge_table.insert(), [{
        "id": edge["id"], "model_version_id": model_id,
        "source_node_id": edge["source"], "source_port": edge.get("source_port", "out"),
        "target_node_id": edge["target"], "target_port": edge.get("target_port", "in"),
        "flow_type": edge.get("flow_type", "electricity"),
        "domain": edge.get("domain", "electric.ac"), "enabled": edge.get("enabled", True),
        "connection_key": edge["id"],
        "parameters": {"efficiency": .98, "evidence": "event_specific_l1", **edge.get("parameters", {})},
    } for edge in model["edges"]])

    settings = connection.scalar(sa.text("SELECT settings FROM lab_model_versions WHERE id = :id"), {"id": model_id}) or {}
    connection.execute(sa.text(
        "UPDATE lab_model_versions SET settings = CAST(:settings AS jsonb), "
        "validation = CAST(:validation AS jsonb) WHERE id = :id"
    ), {
        "id": model_id,
        "settings": json.dumps({
            **settings, "event_model_id": model_id,
            "topology_revision": model["topology_revision"], "dedicated_topology": True,
        }),
        "validation": json.dumps({"valid": True, "qualification_model": True, "dedicated_topology": True}),
    })
    connection.execute(sa.text(
        "UPDATE lab_qualification_definitions SET document = CAST(:document AS jsonb), "
        "revision = revision + 1 WHERE model_version_id = :id"
    ), {"id": model_id, "document": json.dumps(package)})

    if "lab_scenario_event_templates" in tables:
        for event_type, target in model.get("event_targets", {}).items():
            connection.execute(sa.text(
                "UPDATE lab_scenario_event_templates SET target_node_id = :target "
                "WHERE scenario_id = :scenario_id AND event_type = :event_type"
            ), {"target": target, "scenario_id": package["scenario_id"], "event_type": event_type})
    if "lab_scenarios" not in tables:
        return
    scenario = connection.execute(sa.text(
        "SELECT events, configuration FROM lab_scenarios WHERE id = :id"
    ), {"id": package["scenario_id"]}).mappings().first()
    if not scenario:
        return
    events = deepcopy(scenario["events"] or [])
    configuration = deepcopy(scenario["configuration"] or {})
    targets = model.get("event_targets", {})
    for event in events:
        if event.get("event_type") in targets:
            event["target_node_id"] = targets[event["event_type"]]
    for event in configuration.get("script_events", []):
        if event.get("event_type") in targets:
            event["target"] = targets[event["event_type"]]
    configuration.update({"event_model_id": model_id, "topology_revision": model["topology_revision"]})
    connection.execute(sa.text(
        "UPDATE lab_scenarios SET events = CAST(:events AS jsonb), "
        "configuration = CAST(:configuration AS jsonb) WHERE id = :id"
    ), {
        "id": package["scenario_id"], "events": json.dumps(events),
        "configuration": json.dumps(configuration),
    })
