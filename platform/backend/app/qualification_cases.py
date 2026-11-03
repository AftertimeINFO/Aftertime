"""Source-backed generalized L1 qualification packages."""

from __future__ import annotations

from copy import deepcopy
from html import escape
from typing import Any

from app.services.bpmn_profile import build_bpmn_xml, meaningful_end_name


def _transitions(*pairs: tuple[str | list[str], str]) -> list[dict[str, Any]]:
    return [{"from": origin, "to": target} for origin, target in pairs]


def _object(
    object_id: str,
    name: str,
    kind: str,
    initial_state: str,
    states: list[str],
    capabilities: dict[str, list[dict[str, Any]]],
    *,
    model_node_id: str | None = None,
) -> dict[str, Any]:
    result = {
        "id": object_id,
        "name": name,
        "kind": kind,
        "initial_state": initial_state,
        "states": states,
        "capabilities": capabilities,
    }
    if model_node_id:
        result["model_node_id"] = model_node_id
    return result


def _bind_event_model_objects(package: dict[str, Any]) -> None:
    bindings = {
        node["qualification_object_id"]: node["id"]
        for node in package.get("model", {}).get("nodes", [])
        if node.get("qualification_object_id")
    }
    for definition in package.get("objects", []):
        if definition["id"] in bindings:
            definition["model_node_id"] = bindings[definition["id"]]


def _step(
    step_id: str,
    name: str,
    *,
    after: list[str] | None = None,
    target: str | None = None,
    capability: str | None = None,
    branch: str = "main",
) -> dict[str, Any]:
    return {
        "id": step_id,
        "name": name,
        "after": after or [],
        "target": target,
        "capability": capability,
        "branch": branch,
        "required": True,
    }


def _bpmn(process_id: str, name: str, steps: list[dict[str, Any]]) -> str:
    nodes: list[dict[str, Any]] = [{"node_key": "start", "block_type": "start_event", "name": f"Отримано повідомлення: {process_id}.started", "x": 80, "y": 120, "config": {"event_definition": "message", "event_type": f"{process_id}.started"}}]
    nodes.extend({"node_key": step["id"], "block_type": "service_task" if step.get("target") else "business_rule_task", "name": step["name"], "x": 80 + index * 210, "y": 120, "config": {"target_ref": step.get("target"), "capability": step.get("capability")}} for index, step in enumerate(steps, 1))
    nodes.append({"node_key": "end", "block_type": "end_event", "name": meaningful_end_name(name, steps[-1]["name"] if steps else None), "x": 80 + (len(steps) + 1) * 210, "y": 120, "config": {"event_definition": "none", "outcome": "completed"}})
    step_ids = {step["id"] for step in steps}
    flow_pairs: list[tuple[str, str]] = []
    for step in steps:
        predecessors = step.get("after") or ["start"]
        flow_pairs.extend((source, step["id"]) for source in predecessors)
    predecessor_ids = {
        predecessor
        for step in steps
        for predecessor in (step.get("after") or [])
        if predecessor in step_ids
    }
    flow_pairs.extend((step["id"], "end") for step in steps if step["id"] not in predecessor_ids)
    if not steps:
        flow_pairs.append(("start", "end"))
    transitions = [{"flow_key": f"flow_{index}", "source_key": source, "target_key": target, "condition_code": "True"} for index, (source, target) in enumerate(flow_pairs, 1)]
    return build_bpmn_xml(process_id, name, nodes, transitions)


def _process(process_id: str, name: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": process_id,
        "name": name,
        "format": "BPMN 2.0 XML",
        "steps": steps,
        "bpmn_xml": _bpmn(process_id, name, steps),
    }


def _dmn(name: str, situations: list[dict[str, Any]]) -> str:
    decisions = "".join(
        f'<dmn:decision id="{escape(item["id"])}" name="{escape(item["id"])}">'
        '<dmn:literalExpression expressionLanguage="https://www.omg.org/spec/DMN/20191111/FEEL/">'
        f'<dmn:text>{escape(_feel_rule(item.get("all", [])))}</dmn:text>'
        '</dmn:literalExpression>'
        '</dmn:decision>'
        for item in situations
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<dmn:definitions xmlns:dmn="https://www.omg.org/spec/DMN/20191111/MODEL/" '
        f'id="{escape(name)}" name="{escape(name)}" '
        f'namespace="https://aftertime.local/dmn">{decisions}</dmn:definitions>'
    )


def _feel_rule(conditions: list[dict[str, Any]]) -> str:
    expressions: list[str] = []
    for condition in conditions:
        if "object" in condition:
            expressions.append(
                f'object_states.{condition["object"]} = "{condition.get("state", "")}"'
            )
        elif "fact" in condition:
            expressions.append(f'list contains(facts, "{condition["fact"]}")')
        elif "metric" in condition and "equals" in condition:
            expressions.append(f'metrics.{condition["metric"]} = {condition["equals"]}')
        elif "metric" in condition and "at_least" in condition:
            expressions.append(f'metrics.{condition["metric"]} >= {condition["at_least"]}')
    return " and ".join(expressions) or "false"


def canonicalize_qualification_package(package: dict[str, Any]) -> dict[str, Any]:
    """Regenerate standard interchange XML from the editable structured model."""

    result = deepcopy(package)
    result["dmn_xml"] = _dmn(result["id"], result.get("situations", []))
    for process in result.get("processes", []):
        process["format"] = "BPMN 2.0 XML"
        process["bpmn_xml"] = _bpmn(
            process["id"], process.get("name") or process["id"], process.get("steps", [])
        )
    return result


def _entry(
    entry_id: str,
    at: str,
    *,
    entry_kind: str,
    evidence: str,
    source: str | None = None,
    origin: str | None = None,
    fact: str | None = None,
    action: dict[str, Any] | None = None,
    process: tuple[str, str] | None = None,
    situations: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
    resources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": entry_id,
        "at": at,
        "entry_kind": entry_kind,
        "evidence": evidence,
    }
    if source:
        item["source"] = source
    if origin:
        item["origin"] = origin
    if fact:
        item["fact"] = fact
    if action:
        item["action"] = action
    if process:
        item["process"] = {"id": process[0], "step": process[1]}
    if situations:
        item["confirm_situations"] = situations
    if metrics:
        item["metrics"] = metrics
    if resources:
        item["resource_operations"] = resources
    return item


def _action(target: str, capability: str, state: str) -> dict[str, Any]:
    return {
        "target": target,
        "capability": capability,
        "postcondition": {"state": state},
    }


SAN_BRUNO_PROCESS_STEPS = [
    _step("recognize_break", "Recognize probable transmission break"),
    _step("notify_responders", "Notify operator and public responders", after=["recognize_break"]),
    _step(
        "establish_command",
        "Establish incident command",
        after=["notify_responders"],
        target="incident_command",
        capability="activate",
    ),
    _step(
        "evacuate_search_ems",
        "Evacuate, search and establish medical operations",
        after=["establish_command"],
        target="public_response",
        capability="deploy",
    ),
    _step("identify_valves", "Identify isolation valves", after=["notify_responders"]),
    _step(
        "close_downstream",
        "Close downstream remote valves",
        after=["identify_valves"],
        target="downstream_valves",
        capability="close",
    ),
    _step(
        "close_upstream",
        "Close upstream mainline valve",
        after=["identify_valves"],
        target="upstream_valve",
        capability="close",
    ),
    _step(
        "confirm_zero_flow",
        "Confirm transmission segment isolation",
        after=["close_downstream", "close_upstream"],
        target="line_132",
        capability="confirm_isolated",
    ),
    _step(
        "defensive_firefighting",
        "Continue defensive firefighting",
        after=["establish_command"],
        target="fire_area",
        capability="defensive_operations",
    ),
    _step(
        "isolate_distribution",
        "Isolate gas distribution lines",
        after=["confirm_zero_flow"],
        target="distribution_lines",
        capability="isolate",
    ),
    _step(
        "contain_fire",
        "Reach principal fire containment",
        after=["isolate_distribution", "defensive_firefighting"],
        target="fire_area",
        capability="contain_75_percent",
    ),
    _step(
        "stabilize_site",
        "Stabilize isolated pipeline site",
        after=["contain_fire"],
        target="line_132",
        capability="stabilize",
    ),
    _step(
        "transfer_command",
        "Transfer incident command",
        after=["stabilize_site"],
        target="incident_command",
        capability="transfer",
    ),
]


SAN_BRUNO = {
    "schema_version": 2,
    "id": "san-bruno-2010-l1",
    "scenario_id": "san-bruno-2010",
    "name": "San Bruno, 2010 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "ntsb_par_11_01",
            "url": "https://www.ntsb.gov/investigations/AccidentReports/Reports/PAR1101.pdf",
            "scope": "cause, operating conditions, rupture and emergency response",
            "priority": "final_official",
        },
        {
            "id": "ntsb_timeline",
            "url": "https://data.ntsb.gov/Docket/Document/docBLOB?FileExtension=.PDF&FileName=Exhibit+2DX:+Timeline+of+Events+for+September+9,+2010+Prepared+by+NTSB-Master.PDF&ID=40343828",
            "scope": "minute-level event timeline",
            "priority": "official_evidence",
        },
        {
            "id": "ntsb_accident_summary",
            "url": "https://www.ntsb.gov/investigations/Pages/DCA10MP008.aspx",
            "scope": "official accident synopsis, pipe dimensions, release estimate, physical damage, casualties and probable cause",
            "priority": "official_investigation_summary",
        },
    ],
    "model": {
        "id": "qualification-san-bruno-2010",
        "name": "San Bruno Line 132 rupture · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Causal gas-transmission, release, community-impact and emergency-response topology based on NTSB PAR-11/01; it is not a geographic pipeline map.",
        "event_targets": {"pipeline_rupture": "sb-line132-rupture", "fire": "sb-fire-area"},
        "nodes": [
            {"id": "sb-upstream-gas", "name": "PG&E upstream gas transmission supply", "component_type_id": "gas-supply", "x": 40, "y": 160},
            {"id": "sb-milpitas-terminal", "name": "Milpitas Terminal gas pressure-control path", "component_type_id": "gas-control-terminal", "x": 260, "y": 160, "parameters": {"planned_electrical_work_start": "14:46"}},
            {"id": "sb-control-scada", "name": "Milpitas control and SCADA", "component_type_id": "protection-system", "x": 260, "y": 20, "qualification_object_id": "control_system"},
            {"id": "sb-upstream-valve", "name": "Upstream mainline isolation valve", "component_type_id": "pipeline-valve", "x": 480, "y": 160, "qualification_object_id": "upstream_valve"},
            {"id": "sb-line132-upstream", "name": "Line 132 upstream linepack segment", "component_type_id": "pipeline", "x": 700, "y": 160, "parameters": {"diameter_in": 30}},
            {"id": "sb-defective-seam", "name": "1956 substandard pup with longitudinal seam-weld flaw", "component_type_id": "pipeline-defect", "x": 920, "y": 160, "parameters": {"installation_year": 1956, "defect_visible_at_installation": True, "pressure_tested_after_installation": False}},
            {"id": "sb-line132-rupture", "name": "Line 132 MP 39.28 rupture segment", "component_type_id": "pipeline", "x": 1140, "y": 160, "parameters": {"diameter_in": 30, "rupture_pressure_psig": 386, "released_gas_scf": 47600000, "ejected_segment_length_ft": 28}, "qualification_object_id": "line_132"},
            {"id": "sb-line132-downstream", "name": "Line 132 downstream linepack segment", "component_type_id": "pipeline", "x": 1360, "y": 160},
            {"id": "sb-downstream-valves", "name": "Downstream remote isolation valves", "component_type_id": "pipeline-valve", "x": 1580, "y": 160, "qualification_object_id": "downstream_valves"},
            {"id": "sb-distribution", "name": "Local gas distribution lines", "component_type_id": "gas-distribution-network", "x": 1800, "y": 160, "qualification_object_id": "distribution_lines"},
            {"id": "sb-release-zone", "name": "Escaping-gas release and ignition zone", "component_type_id": "gas-release-zone", "x": 1140, "y": 380, "parameters": {"released_gas_scf": 47600000}},
            {"id": "sb-fire-area", "name": "Glenview residential fire area", "component_type_id": "external-hazard", "x": 1360, "y": 380, "parameters": {"homes_destroyed": 38, "homes_damaged": 70, "fatalities": 8, "crater_length_ft": 72, "crater_width_ft": 26}, "qualification_object_id": "fire_area"},
            {"id": "sb-incident-command", "name": "Unified incident command", "component_type_id": "response-process", "x": 1580, "y": 380, "qualification_object_id": "incident_command"},
            {"id": "sb-public-response", "name": "Evacuation, search and emergency medical response", "component_type_id": "response-process", "x": 1800, "y": 380, "qualification_object_id": "public_response"},
        ],
        "edges": [
            {"id": "sb-edge-supply-terminal", "source": "sb-upstream-gas", "target": "sb-milpitas-terminal", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "sb-edge-terminal-upstream-valve", "source": "sb-milpitas-terminal", "target": "sb-upstream-valve", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "sb-edge-valve-upstream-line", "source": "sb-upstream-valve", "target": "sb-line132-upstream", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "sb-edge-upstream-defect", "source": "sb-line132-upstream", "target": "sb-defective-seam", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "sb-edge-defect-rupture", "source": "sb-defective-seam", "target": "sb-line132-rupture", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "sb-edge-rupture-downstream", "source": "sb-line132-rupture", "target": "sb-line132-downstream", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "sb-edge-downstream-valves", "source": "sb-line132-downstream", "target": "sb-downstream-valves", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "sb-edge-valves-distribution", "source": "sb-downstream-valves", "target": "sb-distribution", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "sb-edge-rupture-release", "source": "sb-line132-rupture", "target": "sb-release-zone", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "sb-edge-fire-command", "source": "sb-fire-area", "target": "sb-incident-command", "flow_type": "control", "domain": "control"},
            {"id": "sb-edge-command-response", "source": "sb-incident-command", "target": "sb-public-response", "flow_type": "control", "domain": "control"},
        ],
    },
    "objects": [
        _object(
            "control_system",
            "Milpitas control and SCADA",
            "control_system",
            "normal",
            ["normal", "planned_work_active", "degraded"],
            {
                "start_ups_work": _transitions(("normal", "planned_work_active")),
                "degrade_control": _transitions(("planned_work_active", "degraded")),
            },
        ),
        _object(
            "line_132",
            "Line 132 transmission segment",
            "gas_pipeline",
            "operating",
            [
                "operating",
                "elevated_pressure",
                "ruptured_releasing",
                "isolated",
                "stabilized_out_of_service",
            ],
            {
                "pressure_increase": _transitions(("operating", "elevated_pressure")),
                "rupture": _transitions(("elevated_pressure", "ruptured_releasing")),
                "confirm_isolated": _transitions(("ruptured_releasing", "isolated")),
                "stabilize": _transitions(("isolated", "stabilized_out_of_service")),
            },
        ),
        _object(
            "downstream_valves",
            "Downstream remote valves",
            "valve_group",
            "open",
            ["open", "closed"],
            {"close": _transitions(("open", "closed"))},
        ),
        _object(
            "upstream_valve",
            "Upstream mainline valve",
            "valve",
            "open",
            ["open", "closed"],
            {"close": _transitions(("open", "closed"))},
        ),
        _object(
            "distribution_lines",
            "Local gas distribution lines",
            "distribution_network",
            "supplying",
            ["supplying", "isolated"],
            {"isolate": _transitions(("supplying", "isolated"))},
        ),
        _object(
            "fire_area",
            "Residential fire area",
            "incident_area",
            "uncontrolled",
            ["uncontrolled", "defensive", "contained_75", "stabilized"],
            {
                "defensive_operations": _transitions(("uncontrolled", "defensive")),
                "contain_75_percent": _transitions(("defensive", "contained_75")),
                "stabilize": _transitions(("contained_75", "stabilized")),
            },
        ),
        _object(
            "incident_command",
            "Unified incident command",
            "command",
            "inactive",
            ["inactive", "active", "transferred"],
            {
                "activate": _transitions(("inactive", "active")),
                "transfer": _transitions(("active", "transferred")),
            },
        ),
        _object(
            "public_response",
            "Evacuation, search and EMS",
            "response_group",
            "standby",
            ["standby", "deployed"],
            {"deploy": _transitions(("standby", "deployed"))},
        ),
    ],
    "situations": [
        {
            "id": "suspected_pipeline_break",
            "all": [{"object": "line_132", "state": "ruptured_releasing"}],
        },
        {
            "id": "confirmed_gas_fed_urban_fire",
            "all": [
                {"object": "line_132", "state": "ruptured_releasing"},
                {"fact": "ignition_confirmed"},
            ],
        },
        {
            "id": "source_isolated",
            "all": [{"object": "line_132", "state": "isolated"}],
        },
        {
            "id": "site_stabilized",
            "all": [
                {"object": "line_132", "state": "stabilized_out_of_service"},
                {"object": "fire_area", "state": "stabilized"},
            ],
        },
    ],
    "processes": [
        _process(
            "gas_pipeline_rupture_response_l1",
            "Gas pipeline rupture response L1",
            SAN_BRUNO_PROCESS_STEPS,
        )
    ],
    "timeline": [
        _entry(
            "ups_work_start",
            "2010-09-09T14:46:00-07:00",
            entry_kind="input",
            origin="planned_process_start",
            evidence="reported",
            source="ntsb_timeline",
            action=_action("control_system", "start_ups_work", "planned_work_active"),
        ),
        _entry(
            "control_disruption",
            "2010-09-09T17:20:00-07:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="ntsb_par_11_01",
            action=_action("control_system", "degrade_control", "degraded"),
        ),
        _entry(
            "pressure_increase",
            "2010-09-09T18:04:00-07:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="ntsb_par_11_01",
            action=_action("line_132", "pressure_increase", "elevated_pressure"),
        ),
        _entry(
            "rupture",
            "2010-09-09T18:11:00-07:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="ntsb_par_11_01",
            fact="ignition_confirmed",
            action=_action("line_132", "rupture", "ruptured_releasing"),
            process=("gas_pipeline_rupture_response_l1", "recognize_break"),
            situations=["suspected_pipeline_break", "confirmed_gas_fed_urban_fire"],
            metrics={"pipe_diameter_in": 30, "rupture_pressure_psig": 386, "released_gas_scf": 47600000, "homes_destroyed": 38, "homes_damaged": 70, "fatalities": 8},
        ),
        _entry(
            "notify",
            "2010-09-09T18:12:00-07:00",
            entry_kind="process_action",
            evidence="reported",
            source="ntsb_par_11_01",
            process=("gas_pipeline_rupture_response_l1", "notify_responders"),
        ),
        _entry(
            "command_active",
            "2010-09-09T18:20:00-07:00",
            entry_kind="process_action",
            evidence="reported",
            source="ntsb_timeline",
            action=_action("incident_command", "activate", "active"),
            process=("gas_pipeline_rupture_response_l1", "establish_command"),
        ),
        _entry(
            "response_deployed",
            "2010-09-09T18:30:00-07:00",
            entry_kind="process_action",
            evidence="reported",
            source="ntsb_timeline",
            action=_action("public_response", "deploy", "deployed"),
            process=("gas_pipeline_rupture_response_l1", "evacuate_search_ems"),
        ),
        _entry(
            "valves_identified",
            "2010-09-09T18:40:00-07:00",
            entry_kind="process_action",
            evidence="derived",
            process=("gas_pipeline_rupture_response_l1", "identify_valves"),
        ),
        _entry(
            "downstream_closed",
            "2010-09-09T19:29:00-07:00",
            entry_kind="process_action",
            evidence="reported",
            source="ntsb_timeline",
            action=_action("downstream_valves", "close", "closed"),
            process=("gas_pipeline_rupture_response_l1", "close_downstream"),
        ),
        _entry(
            "upstream_closed",
            "2010-09-09T19:30:00-07:00",
            entry_kind="process_action",
            evidence="reported",
            source="ntsb_timeline",
            action=_action("upstream_valve", "close", "closed"),
            process=("gas_pipeline_rupture_response_l1", "close_upstream"),
        ),
        _entry(
            "defensive_firefighting",
            "2010-09-09T19:42:00-07:00",
            entry_kind="process_action",
            evidence="reported",
            source="ntsb_timeline",
            action=_action("fire_area", "defensive_operations", "defensive"),
            process=("gas_pipeline_rupture_response_l1", "defensive_firefighting"),
        ),
        _entry(
            "transmission_isolated",
            "2010-09-09T19:46:00-07:00",
            entry_kind="process_action",
            evidence="reported",
            source="ntsb_par_11_01",
            action=_action("line_132", "confirm_isolated", "isolated"),
            process=("gas_pipeline_rupture_response_l1", "confirm_zero_flow"),
            situations=["source_isolated"],
        ),
        _entry(
            "distribution_isolated",
            "2010-09-09T23:32:00-07:00",
            entry_kind="process_action",
            evidence="reported",
            source="ntsb_timeline",
            action=_action("distribution_lines", "isolate", "isolated"),
            process=("gas_pipeline_rupture_response_l1", "isolate_distribution"),
        ),
        _entry(
            "fire_contained_75",
            "2010-09-10T04:24:00-07:00",
            entry_kind="process_action",
            evidence="reported",
            source="ntsb_timeline",
            action=_action("fire_area", "contain_75_percent", "contained_75"),
            process=("gas_pipeline_rupture_response_l1", "contain_fire"),
            metrics={"fire_containment_percent": 75},
        ),
        _entry(
            "site_stabilization",
            "2010-09-11T19:55:00-07:00",
            entry_kind="process_action",
            evidence="derived",
            action=_action("line_132", "stabilize", "stabilized_out_of_service"),
            process=("gas_pipeline_rupture_response_l1", "stabilize_site"),
        ),
        _entry(
            "fire_stabilized",
            "2010-09-11T19:56:00-07:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("fire_area", "stabilize", "stabilized"),
            situations=["site_stabilized"],
        ),
        _entry(
            "command_transferred",
            "2010-09-11T20:00:00-07:00",
            entry_kind="process_action",
            evidence="reported",
            source="ntsb_timeline",
            action=_action("incident_command", "transfer", "transferred"),
            process=("gas_pipeline_rupture_response_l1", "transfer_command"),
        ),
    ],
    "checkpoints": [
        {
            "id": "rupture_1811",
            "after": "rupture",
            "all": [{"object": "line_132", "state": "ruptured_releasing"}],
        },
        {
            "id": "isolation_1946",
            "after": "transmission_isolated",
            "all": [{"object": "line_132", "state": "isolated"}],
        },
        {
            "id": "distribution_isolation",
            "after": "distribution_isolated",
            "all": [{"object": "distribution_lines", "state": "isolated"}],
        },
        {
            "id": "containment_75",
            "after": "fire_contained_75",
            "all": [{"metric": "fire_containment_percent", "equals": 75}],
        },
        {
            "id": "command_transfer",
            "after": "command_transferred",
            "all": [{"object": "incident_command", "state": "transferred"}],
        },
    ],
    "expected_final": {
        "object_states": {
            "line_132": "stabilized_out_of_service",
            "distribution_lines": "isolated",
            "fire_area": "stabilized",
            "incident_command": "transferred",
        },
        "situations": ["source_isolated", "site_stabilized"],
    },
}


_bind_event_model_objects(SAN_BRUNO)


NORTHEAST_CONTAINMENT_STEPS = [
    _step("loss_of_estimator", "Recognize loss of state estimator"),
    _step("loss_of_alarms", "Recognize alarm and logging failure", after=["loss_of_estimator"]),
    _step("recognize_jeopardy", "Recognize transmission jeopardy", after=["loss_of_alarms"]),
    _step(
        "missed_load_shed",
        "Historical branch: sufficient load shedding not executed",
        after=["recognize_jeopardy"],
        target="operator_response",
        capability="record_missed_mitigation",
        branch="historical_missed_mitigation",
    ),
]

NORTHEAST_STABILIZATION_STEPS = [
    _step("detect_uncontrolled_cascade", "Detect uncontrollable cascade"),
    _step(
        "form_islands",
        "Allow protective separation into islands",
        after=["detect_uncontrolled_cascade"],
        target="regional_grid",
        capability="form_islands",
    ),
    _step(
        "stabilize_western_ny",
        "Stabilize surviving western New York island",
        after=["form_islands"],
        target="regional_grid",
        capability="stabilize_island",
    ),
    _step(
        "begin_restoration",
        "Begin staged restoration from stable sources",
        after=["stabilize_western_ny"],
        target="operator_response",
        capability="begin_restoration",
    ),
]


NORTHEAST_BLACKOUT = {
    "schema_version": 2,
    "id": "northeast-blackout-2003-l1",
    "scenario_id": "northeast-2003",
    "name": "Northeast Blackout, 2003 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "us_ca_blackout_ch5",
            "url": "https://www.ferc.gov/sites/default/files/2020-05/ch5.pdf",
            "scope": "events before the cascade",
            "priority": "final_official",
        },
        {
            "id": "us_ca_blackout_ch6",
            "url": "https://www.ferc.gov/sites/default/files/2020-05/ch6.pdf",
            "scope": "cascade, islanding and initial stabilization",
            "priority": "final_official",
        },
        {
            "id": "us_ca_blackout_ch1_3",
            "url": "https://www.ferc.gov/sites/default/files/2020-05/ch1-3_0.pdf",
            "scope": "regional scope, 61,800 MW affected load, approximately 50 million people and restoration duration",
            "priority": "final_official",
        },
    ],
    "model": {
        "id": "qualification-northeast-2003",
        "name": "Northeast Blackout 14 August 2003 · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Causal monitoring–generation–transmission–regional-islanding topology based on the U.S.–Canada Task Force final report; it is not a geographic transmission map.",
        "event_targets": {"vegetation_contact": "ne-harding-chamberlin", "scada_loss": "ne-fe-alarms", "trip": "ne-eastlake-5"},
        "nodes": [
            {"id": "ne-miso-estimator", "name": "MISO state estimator", "component_type_id": "protection-system", "x": 40, "y": 20, "qualification_object_id": "miso_estimator"},
            {"id": "ne-fe-alarms", "name": "FirstEnergy alarms and event logging", "component_type_id": "protection-system", "x": 260, "y": 20, "qualification_object_id": "fe_alarms"},
            {"id": "ne-operator-response", "name": "Reliability operator response", "component_type_id": "response-process", "x": 480, "y": 20, "qualification_object_id": "operator_response"},
            {"id": "ne-eastlake-5", "name": "Eastlake Unit 5", "component_type_id": "thermal-plant", "x": 40, "y": 240, "parameters": {"capacity_evidence": "not_modelled"}, "qualification_object_id": "eastlake_5"},
            {"id": "ne-michigan-grid", "name": "Michigan interconnected system", "component_type_id": "external-grid", "x": 40, "y": 440},
            {"id": "ne-harding-chamberlin", "name": "Harding–Chamberlin 345 kV line", "component_type_id": "transmission-corridor", "x": 260, "y": 180, "parameters": {"trip_time": "15:05:41", "cause": "tree_contact"}, "qualification_object_id": "harding_chamberlin"},
            {"id": "ne-hanna-juniper", "name": "Hanna–Juniper 345 kV line", "component_type_id": "transmission-corridor", "x": 260, "y": 300, "parameters": {"trip_time": "15:32:03", "cause": "tree_contact"}, "qualification_object_id": "hanna_juniper"},
            {"id": "ne-star-south-canton", "name": "Star–South Canton 345 kV line", "component_type_id": "transmission-corridor", "x": 260, "y": 420, "parameters": {"trip_time": "15:41:35", "cause": "tree_contact"}, "qualification_object_id": "star_south_canton"},
            {"id": "ne-fe-ohio-grid", "name": "FirstEnergy northern Ohio transmission system", "component_type_id": "grid-zone", "x": 480, "y": 280},
            {"id": "ne-sammis-star", "name": "Sammis–Star 345 kV line", "component_type_id": "transmission-corridor", "x": 700, "y": 280, "parameters": {"trip_time": "16:05:57", "protection": "zone_3"}, "qualification_object_id": "sammis_star"},
            {"id": "ne-pjm-grid", "name": "PJM interconnected system", "component_type_id": "external-grid", "x": 700, "y": 500},
            {"id": "ne-ontario-grid", "name": "Ontario power system", "component_type_id": "external-grid", "x": 920, "y": 80},
            {"id": "ne-regional-grid", "name": "Northeast interconnected grid", "component_type_id": "grid-zone", "x": 920, "y": 280, "qualification_object_id": "regional_grid"},
            {"id": "ne-new-york-grid", "name": "New York power system", "component_type_id": "grid-zone", "x": 1140, "y": 160},
            {"id": "ne-western-ny-island", "name": "Surviving western New York island", "component_type_id": "grid-zone", "x": 1140, "y": 360, "parameters": {"surviving_island_mw": 5700}},
            {"id": "ne-affected-load", "name": "Affected U.S. and Ontario load", "component_type_id": "customer-group", "x": 1360, "y": 280, "parameters": {"mode": "load", "demand_mw": 61800, "affected_people": 50000000, "evidence_kind": "reported"}, "qualification_object_id": "affected_load"},
        ],
        "edges": [
            {"id": "ne-edge-eastlake-ohio", "source": "ne-eastlake-5", "target": "ne-fe-ohio-grid"},
            {"id": "ne-edge-michigan-harding", "source": "ne-michigan-grid", "target": "ne-harding-chamberlin"},
            {"id": "ne-edge-harding-ohio", "source": "ne-harding-chamberlin", "target": "ne-fe-ohio-grid"},
            {"id": "ne-edge-michigan-hanna", "source": "ne-michigan-grid", "target": "ne-hanna-juniper"},
            {"id": "ne-edge-hanna-ohio", "source": "ne-hanna-juniper", "target": "ne-fe-ohio-grid"},
            {"id": "ne-edge-michigan-star", "source": "ne-michigan-grid", "target": "ne-star-south-canton"},
            {"id": "ne-edge-star-ohio", "source": "ne-star-south-canton", "target": "ne-fe-ohio-grid"},
            {"id": "ne-edge-ohio-sammis", "source": "ne-fe-ohio-grid", "target": "ne-sammis-star"},
            {"id": "ne-edge-sammis-regional", "source": "ne-sammis-star", "target": "ne-regional-grid"},
            {"id": "ne-edge-pjm-regional", "source": "ne-pjm-grid", "target": "ne-regional-grid"},
            {"id": "ne-edge-ontario-regional", "source": "ne-ontario-grid", "target": "ne-regional-grid"},
            {"id": "ne-edge-regional-new-york", "source": "ne-regional-grid", "target": "ne-new-york-grid"},
            {"id": "ne-edge-new-york-island", "source": "ne-new-york-grid", "target": "ne-western-ny-island"},
            {"id": "ne-edge-regional-load", "source": "ne-regional-grid", "target": "ne-affected-load"},
        ],
    },
    "objects": [
        _object(
            "miso_estimator",
            "MISO state estimator",
            "monitoring_system",
            "effective",
            ["effective", "ineffective"],
            {"lose_effectiveness": _transitions(("effective", "ineffective"))},
        ),
        _object(
            "eastlake_5",
            "Eastlake Unit 5",
            "generator",
            "online",
            ["online", "tripped"],
            {"trip": _transitions(("online", "tripped"))},
        ),
        _object(
            "fe_alarms",
            "FirstEnergy alarms and logging",
            "monitoring_system",
            "available",
            ["available", "failed"],
            {"fail": _transitions(("available", "failed"))},
        ),
        *[
            _object(
                corridor_id,
                corridor_name,
                "transmission_corridor",
                "in_service",
                ["in_service", "tripped"],
                {"vegetation_contact_trip": _transitions(("in_service", "tripped"))},
            )
            for corridor_id, corridor_name in [
                ("harding_chamberlin", "Harding–Chamberlin"),
                ("hanna_juniper", "Hanna–Juniper"),
                ("star_south_canton", "Star–South Canton"),
            ]
        ],
        _object(
            "sammis_star",
            "Sammis–Star 345 kV line",
            "transmission_corridor",
            "in_service",
            ["in_service", "zone3_tripped"],
            {"zone3_trip": _transitions(("in_service", "zone3_tripped"))},
        ),
        _object(
            "regional_grid",
            "Northeast interconnected grid",
            "power_system",
            "secure",
            ["secure", "emergency", "cascading", "islanded", "stable_restoration"],
            {
                "enter_emergency": _transitions(("secure", "emergency")),
                "start_cascade": _transitions(("emergency", "cascading")),
                "form_islands": _transitions(("cascading", "islanded")),
                "stabilize_island": _transitions(("islanded", "stable_restoration")),
            },
        ),
        _object(
            "operator_response",
            "Reliability operator response",
            "response_process",
            "monitoring",
            ["monitoring", "jeopardy_recognized", "mitigation_missed", "restoring"],
            {
                "recognize_jeopardy": _transitions(("monitoring", "jeopardy_recognized")),
                "record_missed_mitigation": _transitions(
                    ("jeopardy_recognized", "mitigation_missed")
                ),
                "begin_restoration": _transitions(("mitigation_missed", "restoring")),
            },
        ),
        _object(
            "affected_load",
            "Affected U.S. and Ontario load",
            "customer_group",
            "supplied",
            ["supplied", "outage_61800mw"],
            {"interrupt": _transitions(("supplied", "outage_61800mw"))},
        ),
    ],
    "situations": [
        {
            "id": "awareness_loss",
            "all": [
                {"object": "miso_estimator", "state": "ineffective"},
                {"object": "fe_alarms", "state": "failed"},
            ],
        },
        {
            "id": "transmission_emergency",
            "all": [{"object": "regional_grid", "state": "emergency"}],
        },
        {
            "id": "uncontrollable_cascade",
            "all": [{"object": "regional_grid", "state": "cascading"}],
        },
        {
            "id": "black_system",
            "all": [{"object": "regional_grid", "state": "islanded"}],
        },
        {
            "id": "stable_restoration",
            "all": [{"object": "regional_grid", "state": "stable_restoration"}],
        },
    ],
    "processes": [
        _process(
            "grid_disturbance_containment_l1",
            "Grid disturbance containment L1",
            NORTHEAST_CONTAINMENT_STEPS,
        ),
        _process(
            "wide_area_stabilization_l1",
            "Wide-area stabilization L1",
            NORTHEAST_STABILIZATION_STEPS,
        ),
    ],
    "timeline": [
        _entry(
            "estimator_ineffective",
            "2003-08-14T12:15:00-04:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="us_ca_blackout_ch5",
            action=_action("miso_estimator", "lose_effectiveness", "ineffective"),
            process=("grid_disturbance_containment_l1", "loss_of_estimator"),
        ),
        _entry(
            "eastlake_trip",
            "2003-08-14T13:31:34-04:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="us_ca_blackout_ch5",
            action=_action("eastlake_5", "trip", "tripped"),
        ),
        _entry(
            "alarm_failure",
            "2003-08-14T14:14:00-04:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="us_ca_blackout_ch5",
            action=_action("fe_alarms", "fail", "failed"),
            process=("grid_disturbance_containment_l1", "loss_of_alarms"),
            situations=["awareness_loss"],
        ),
        _entry(
            "harding_contact",
            "2003-08-14T15:05:41-04:00",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="us_ca_blackout_ch5",
            action=_action("harding_chamberlin", "vegetation_contact_trip", "tripped"),
        ),
        _entry(
            "hanna_contact",
            "2003-08-14T15:32:03-04:00",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="us_ca_blackout_ch5",
            action=_action("hanna_juniper", "vegetation_contact_trip", "tripped"),
        ),
        _entry(
            "star_contact",
            "2003-08-14T15:41:35-04:00",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="us_ca_blackout_ch5",
            action=_action("star_south_canton", "vegetation_contact_trip", "tripped"),
        ),
        _entry(
            "jeopardy_recognized",
            "2003-08-14T15:46:00-04:00",
            entry_kind="process_action",
            evidence="reported",
            source="us_ca_blackout_ch5",
            action=_action(
                "operator_response", "recognize_jeopardy", "jeopardy_recognized"
            ),
            process=("grid_disturbance_containment_l1", "recognize_jeopardy"),
        ),
        _entry(
            "grid_emergency",
            "2003-08-14T15:46:01-04:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("regional_grid", "enter_emergency", "emergency"),
            situations=["transmission_emergency"],
        ),
        _entry(
            "load_shed_missed",
            "2003-08-14T15:47:00-04:00",
            entry_kind="process_action",
            evidence="reported",
            source="us_ca_blackout_ch5",
            action=_action(
                "operator_response", "record_missed_mitigation", "mitigation_missed"
            ),
            process=("grid_disturbance_containment_l1", "missed_load_shed"),
        ),
        _entry(
            "sammis_star_trip",
            "2003-08-14T16:05:57-04:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="us_ca_blackout_ch6",
            action=_action("sammis_star", "zone3_trip", "zone3_tripped"),
            process=("wide_area_stabilization_l1", "detect_uncontrolled_cascade"),
        ),
        _entry(
            "cascade_started",
            "2003-08-14T16:05:57.100000-04:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("regional_grid", "start_cascade", "cascading"),
            situations=["uncontrollable_cascade"],
        ),
        _entry(
            "islanding",
            "2003-08-14T16:10:46-04:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("regional_grid", "form_islands", "islanded"),
            process=("wide_area_stabilization_l1", "form_islands"),
            situations=["black_system"],
        ),
        _entry(
            "regional_load_interrupted",
            "2003-08-14T16:10:46.001000-04:00",
            entry_kind="derived",
            evidence="derived",
            fact="The blackout affected an area with 61,800 MW of load and approximately 50 million people",
            action=_action("affected_load", "interrupt", "outage_61800mw"),
            metrics={"affected_load_mw": 61800, "affected_people": 50000000},
        ),
        _entry(
            "western_ny_stable",
            "2003-08-14T16:13:00-04:00",
            entry_kind="process_action",
            evidence="reported",
            source="us_ca_blackout_ch6",
            action=_action("regional_grid", "stabilize_island", "stable_restoration"),
            process=("wide_area_stabilization_l1", "stabilize_western_ny"),
            situations=["stable_restoration"],
            metrics={"surviving_western_ny_island_mw": 5700},
        ),
        _entry(
            "restoration_begun",
            "2003-08-14T16:13:01-04:00",
            entry_kind="process_action",
            evidence="derived",
            action=_action("operator_response", "begin_restoration", "restoring"),
            process=("wide_area_stabilization_l1", "begin_restoration"),
        ),
    ],
    "checkpoints": [
        {
            "id": "eastlake_not_blackout",
            "after": "eastlake_trip",
            "all": [{"object": "regional_grid", "state": "secure"}],
        },
        {
            "id": "awareness_before_lines",
            "after": "alarm_failure",
            "all": [{"fact": "alarm_failure"}],
        },
        {
            "id": "three_distinct_contacts",
            "after": "star_contact",
            "all": [
                {"object": "harding_chamberlin", "state": "tripped"},
                {"object": "hanna_juniper", "state": "tripped"},
                {"object": "star_south_canton", "state": "tripped"},
            ],
        },
        {
            "id": "cascade_derived",
            "after": "cascade_started",
            "all": [{"object": "regional_grid", "state": "cascading"}],
        },
        {
            "id": "stable_island_source",
            "after": "western_ny_stable",
            "all": [
                {"object": "regional_grid", "state": "stable_restoration"},
                {"metric": "surviving_western_ny_island_mw", "equals": 5700},
            ],
        },
    ],
    "expected_final": {
        "object_states": {
            "regional_grid": "stable_restoration",
            "operator_response": "restoring",
            "affected_load": "outage_61800mw",
        },
        "situations": ["awareness_loss", "uncontrollable_cascade", "stable_restoration"],
    },
}


_bind_event_model_objects(NORTHEAST_BLACKOUT)


ARWEN_STEPS = [
    _step(
        "prepare",
        "Prepare for severe weather",
        target="coordination",
        capability="prepare",
    ),
    _step(
        "activate_mutual_aid",
        "Activate NEWSAC mutual aid",
        after=["prepare"],
        target="coordination",
        capability="activate_mutual_aid",
    ),
    _step("assess_damage", "Assess network damage", after=["activate_mutual_aid"]),
    _step(
        "access_available",
        "Confirm safe access for detailed assessment",
        after=["assess_damage"],
        target="site_access",
        capability="restore_access",
    ),
    _step(
        "dispatch_external_crews",
        "Dispatch external mutual-aid crews",
        after=["activate_mutual_aid"],
        branch="crew_shortage",
    ),
    _step(
        "isolate_hv",
        "Isolate damaged HV segment",
        after=["access_available"],
        target="hv_segment",
        capability="isolate",
    ),
    _step(
        "repair_hv",
        "Repair HV segment",
        after=["isolate_hv", "dispatch_external_crews"],
        target="hv_segment",
        capability="start_repair",
    ),
    _step(
        "test_hv",
        "Test HV segment",
        after=["repair_hv"],
        target="hv_segment",
        capability="start_testing",
    ),
    _step(
        "restore_hv",
        "Return HV segment to service",
        after=["test_hv"],
        target="hv_segment",
        capability="return_to_service",
    ),
    _step(
        "isolate_distribution",
        "Isolate distribution segment",
        after=["access_available"],
        target="distribution_segment",
        capability="isolate",
    ),
    _step(
        "repair_distribution",
        "Repair distribution segment",
        after=["isolate_distribution", "dispatch_external_crews"],
        target="distribution_segment",
        capability="start_repair",
    ),
    _step(
        "nested_fault_loop",
        "Return nested fault to safe isolation",
        after=["repair_distribution"],
        target="distribution_segment",
        capability="discover_nested_fault",
        branch="nested_fault",
    ),
    _step(
        "repair_nested_fault",
        "Repair nested distribution fault",
        after=["nested_fault_loop"],
        target="distribution_segment",
        capability="start_repair",
        branch="nested_fault",
    ),
    _step(
        "test_distribution",
        "Test distribution segment",
        after=["repair_nested_fault"],
        target="distribution_segment",
        capability="start_testing",
    ),
    _step(
        "restore_distribution",
        "Return distribution segment to service",
        after=["test_distribution"],
        target="distribution_segment",
        capability="return_to_service",
    ),
    _step(
        "connect_mobile_generation",
        "Connect mobile generation and fuel support",
        after=["access_available"],
        target="mobile_support",
        capability="deploy",
        branch="prolonged_outage",
    ),
    _step(
        "complete_restoration",
        "Complete staged customer restoration",
        after=["restore_hv", "restore_distribution"],
        target="customers",
        capability="complete_restoration",
    ),
    _step(
        "stabilize_response",
        "Close mass outage response",
        after=["complete_restoration"],
        target="coordination",
        capability="stabilize",
    ),
]


def _line_object(object_id: str, name: str) -> dict[str, Any]:
    return _object(
        object_id,
        name,
        "network_segment",
        "in_service",
        ["in_service", "faulted_unsafe", "isolated", "under_repair", "testing"],
        {
            "storm_damage": _transitions(("in_service", "faulted_unsafe")),
            "isolate": _transitions(("faulted_unsafe", "isolated")),
            "start_repair": _transitions(("isolated", "under_repair")),
            "discover_nested_fault": _transitions(("under_repair", "faulted_unsafe")),
            "start_testing": _transitions(("under_repair", "testing")),
            "return_to_service": _transitions(("testing", "in_service")),
        },
    )


STORM_ARWEN = {
    "schema_version": 2,
    "id": "storm-arwen-2021-l1",
    "scenario_id": "storm-arwen-2021",
    "name": "Storm Arwen, 2021 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "e3c_final",
            "url": "https://assets.publishing.service.gov.uk/media/629fa8b1d3bf7f0371a9b0ca/storm-arwen-review-final-report.pdf",
            "scope": "preparation, mutual aid, restoration and national milestones",
            "priority": "final_official",
        },
        {
            "id": "ofgem_ghd",
            "url": "https://www.ofgem.gov.uk/sites/default/files/2022-06/GHD%20-%20Storm%20Arwen%20Review%20Main%20Report.pdf",
            "scope": "operator response and restoration scope",
            "priority": "official_review",
        },
    ],
    "model": {
        "id": "qualification-storm-arwen-2021",
        "name": "Storm Arwen distribution disruption · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Causal severe-weather, tiered distribution-network, customer-impact and resource-restoration topology based on the E3C and Ofgem final reviews; it is not a geographic DNO map.",
        "event_targets": {"line_fault": "ar-hv-segment", "distribution_fault": "ar-distribution-segment"},
        "nodes": [
            {"id": "ar-weather", "name": "Storm Arwen high wind, snow and ice", "component_type_id": "external-hazard", "x": 40, "y": 20, "parameters": {"peak_wind_mph": 100}, "qualification_object_id": "weather_profile"},
            {"id": "ar-upstream-generation", "name": "Upstream generation aggregate", "component_type_id": "generation-aggregate", "x": 40, "y": 240, "parameters": {"capacity_evidence": "not_modelled"}, "qualification_object_id": "generating_plant"},
            {"id": "ar-grid-supply-point", "name": "Representative DNO grid supply point", "component_type_id": "transformer-group", "x": 260, "y": 240},
            {"id": "ar-hv-segment", "name": "Storm-damaged HV overhead segment", "component_type_id": "transmission-corridor", "x": 480, "y": 240, "parameters": {"fault_scope": "representative_hv"}, "qualification_object_id": "hv_segment"},
            {"id": "ar-primary-substation", "name": "Representative primary distribution substation", "component_type_id": "transformer-group", "x": 700, "y": 240},
            {"id": "ar-distribution-segment", "name": "Storm-damaged distribution feeder", "component_type_id": "distribution", "x": 920, "y": 240, "parameters": {"nested_faults": True}, "qualification_object_id": "distribution_segment"},
            {"id": "ar-nested-fault-section", "name": "Initially hidden downstream nested fault", "component_type_id": "distribution", "x": 1140, "y": 240, "parameters": {"discovered_after_first_repair": True}},
            {"id": "ar-customers", "name": "Storm Arwen affected customers", "component_type_id": "customer-group", "x": 1360, "y": 240, "parameters": {"affected_customers_min": 1000000, "restored_within_24h_percent": 83, "without_supply_over_3_days_approx": 40000, "without_supply_over_week_approx": 4000, "maximum_outage_days": 13}, "qualification_object_id": "customers"},
            {"id": "ar-site-access", "name": "Safe access to damaged network", "component_type_id": "system-state", "x": 480, "y": 500, "qualification_object_id": "site_access"},
            {"id": "ar-coordination", "name": "DNO emergency and NEWSAC coordination", "component_type_id": "response-process", "x": 700, "y": 500, "qualification_object_id": "coordination"},
            {"id": "ar-line-crews", "name": "Internal and mutual-aid line crews", "component_type_id": "response-process", "x": 920, "y": 500, "parameters": {"scenario_required_crews": 6, "initial_available_crews": 4, "external_crews": 2, "evidence_kind": "model_assumption"}},
            {"id": "ar-line-materials", "name": "Poles, conductors and line repair kits", "component_type_id": "system-state", "x": 1140, "y": 500, "parameters": {"scenario_line_kits": 8, "evidence_kind": "model_assumption"}},
            {"id": "ar-mobile-generation", "name": "Mobile generation and fuel support", "component_type_id": "distributed-generation", "x": 1140, "y": 660, "parameters": {"national_units_28_nov": 253, "national_units_3_dec": 664, "capacity_evidence": "not_reported"}, "initial_online": False, "qualification_object_id": "mobile_support"},
        ],
        "edges": [
            {"id": "ar-edge-grid-gsp", "source": "ar-upstream-generation", "target": "ar-grid-supply-point"},
            {"id": "ar-edge-gsp-hv", "source": "ar-grid-supply-point", "target": "ar-hv-segment"},
            {"id": "ar-edge-hv-primary", "source": "ar-hv-segment", "target": "ar-primary-substation"},
            {"id": "ar-edge-primary-distribution", "source": "ar-primary-substation", "target": "ar-distribution-segment"},
            {"id": "ar-edge-distribution-nested", "source": "ar-distribution-segment", "target": "ar-nested-fault-section"},
            {"id": "ar-edge-nested-customers", "source": "ar-nested-fault-section", "target": "ar-customers"},
            {"id": "ar-edge-mobile-customers", "source": "ar-mobile-generation", "target": "ar-customers"},
            {"id": "ar-edge-access-coordination", "source": "ar-site-access", "target": "ar-coordination", "flow_type": "control", "domain": "control"},
            {"id": "ar-edge-coordination-crews", "source": "ar-coordination", "target": "ar-line-crews", "flow_type": "control", "domain": "control"},
            {"id": "ar-edge-crews-materials", "source": "ar-line-crews", "target": "ar-line-materials", "flow_type": "control", "domain": "control"},
        ],
    },
    "objects": [
        _object(
            "weather_profile",
            "Storm Arwen weather profile",
            "external_hazard",
            "forecast",
            ["forecast", "warning", "active_peak", "decay", "ended"],
            {
                "issue_warning": _transitions(("forecast", "warning")),
                "arrive": _transitions(("warning", "active_peak")),
                "decay": _transitions(("active_peak", "decay")),
                "end": _transitions(("decay", "ended")),
            },
        ),
        _line_object("hv_segment", "Representative HV segment"),
        _line_object("distribution_segment", "Representative distribution segment"),
        _object(
            "generating_plant",
            "Upstream generating plant",
            "generator",
            "energized",
            ["energized"],
            {"confirm_energized": _transitions(("energized", "energized"))},
        ),
        _object(
            "customers",
            "Downstream customer aggregate",
            "customer_group",
            "supplied",
            ["supplied", "outage", "partially_restored", "restored"],
            {
                "lose_supply": _transitions(("supplied", "outage")),
                "partial_restoration": _transitions(
                    (["outage", "partially_restored"], "partially_restored")
                ),
                "complete_restoration": _transitions(
                    (["outage", "partially_restored"], "restored")
                ),
            },
        ),
        _object(
            "site_access",
            "Access to damaged network",
            "access_condition",
            "open",
            ["open", "constrained", "available"],
            {
                "constrain": _transitions(("open", "constrained")),
                "restore_access": _transitions(("constrained", "available")),
            },
        ),
        _object(
            "coordination",
            "Distribution emergency coordination",
            "response_process",
            "monitoring",
            ["monitoring", "prepared", "mutual_aid_active", "stabilized"],
            {
                "prepare": _transitions(("monitoring", "prepared")),
                "activate_mutual_aid": _transitions(("prepared", "mutual_aid_active")),
                "stabilize": _transitions(("mutual_aid_active", "stabilized")),
            },
        ),
        _object(
            "mobile_support",
            "Mobile generation and fuel support",
            "temporary_supply",
            "standby",
            ["standby", "deployed"],
            {"deploy": _transitions(("standby", "deployed"))},
        ),
    ],
    "resources": {
        "line_crews": {"unit": "crew", "available": 4, "reserved": 0, "consumed": 0},
        "line_kits": {"unit": "kit", "available": 8, "reserved": 0, "consumed": 0},
        "mobile_generators": {
            "unit": "generator",
            "available": 1,
            "reserved": 0,
            "consumed": 0,
        },
        "mobile_fuel": {"unit": "package", "available": 1, "reserved": 0, "consumed": 0},
    },
    "situations": [
        {
            "id": "mass_distribution_outage",
            "all": [{"object": "customers", "state": "outage"}],
        },
        {
            "id": "access_constrained",
            "all": [{"object": "site_access", "state": "constrained"}],
        },
        {
            "id": "crew_shortage",
            "all": [{"metric": "required_line_crews", "at_least": 6}],
        },
        {
            "id": "prolonged_outage",
            "all": [
                {"object": "customers", "state": "partially_restored"},
                {"fact": "nested_fault_discovered"},
            ],
        },
        {
            "id": "outage_resolved",
            "all": [{"object": "customers", "state": "restored"}],
        },
    ],
    "processes": [
        _process("storm_mass_outage_l1", "Storm mass outage response L1", ARWEN_STEPS)
    ],
    "timeline": [
        _entry(
            "operator_preparation",
            "2021-11-24T09:00:00+00:00",
            entry_kind="process_action",
            evidence="reported",
            source="e3c_final",
            action=_action("coordination", "prepare", "prepared"),
            process=("storm_mass_outage_l1", "prepare"),
        ),
        _entry(
            "weather_warning",
            "2021-11-24T12:00:00+00:00",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="e3c_final",
            action=_action("weather_profile", "issue_warning", "warning"),
        ),
        _entry(
            "newsac_call",
            "2021-11-25T09:00:00+00:00",
            entry_kind="process_action",
            evidence="reported",
            source="e3c_final",
            action=_action("coordination", "activate_mutual_aid", "mutual_aid_active"),
            process=("storm_mass_outage_l1", "activate_mutual_aid"),
        ),
        _entry(
            "storm_peak",
            "2021-11-26T18:00:00+00:00",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="e3c_final",
            action=_action("weather_profile", "arrive", "active_peak"),
        ),
        _entry(
            "hv_damage",
            "2021-11-26T18:01:00+00:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("hv_segment", "storm_damage", "faulted_unsafe"),
        ),
        _entry(
            "distribution_damage",
            "2021-11-26T18:02:00+00:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("distribution_segment", "storm_damage", "faulted_unsafe"),
        ),
        _entry(
            "customer_outage",
            "2021-11-26T18:03:00+00:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("customers", "lose_supply", "outage"),
            situations=["mass_distribution_outage"],
        ),
        _entry(
            "plant_stays_energized",
            "2021-11-26T18:04:00+00:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("generating_plant", "confirm_energized", "energized"),
        ),
        _entry(
            "access_lost",
            "2021-11-26T18:05:00+00:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("site_access", "constrain", "constrained"),
            situations=["access_constrained"],
        ),
        _entry(
            "damage_assessment",
            "2021-11-27T08:00:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            process=("storm_mass_outage_l1", "assess_damage"),
            metrics={"required_line_crews": 6},
            situations=["crew_shortage"],
        ),
        _entry(
            "external_crews",
            "2021-11-27T09:00:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            process=("storm_mass_outage_l1", "dispatch_external_crews"),
            resources=[
                {"pool": "line_crews", "operation": "produce", "quantity": 2},
                {"pool": "line_crews", "operation": "reserve", "quantity": 6},
                {"pool": "line_kits", "operation": "reserve", "quantity": 8},
            ],
        ),
        _entry(
            "restored_24h_scope",
            "2021-11-27T18:00:00+00:00",
            entry_kind="process_action",
            evidence="reported",
            source="e3c_final",
            action=_action("customers", "partial_restoration", "partially_restored"),
            metrics={"restored_within_24h_percent_e3c_scope": 83},
        ),
        _entry(
            "weather_decay",
            "2021-11-28T06:00:00+00:00",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="e3c_final",
            action=_action("weather_profile", "decay", "decay"),
        ),
        _entry(
            "access_restored",
            "2021-11-28T09:00:00+00:00",
            entry_kind="process_action",
            evidence="reported",
            source="e3c_final",
            action=_action("site_access", "restore_access", "available"),
            process=("storm_mass_outage_l1", "access_available"),
        ),
        _entry(
            "hv_isolated",
            "2021-11-28T10:00:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            action=_action("hv_segment", "isolate", "isolated"),
            process=("storm_mass_outage_l1", "isolate_hv"),
        ),
        _entry(
            "distribution_isolated",
            "2021-11-28T10:05:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            action=_action("distribution_segment", "isolate", "isolated"),
            process=("storm_mass_outage_l1", "isolate_distribution"),
        ),
        _entry(
            "mobile_generation",
            "2021-11-28T11:00:00+00:00",
            entry_kind="process_action",
            evidence="reported",
            source="e3c_final",
            action=_action("mobile_support", "deploy", "deployed"),
            process=("storm_mass_outage_l1", "connect_mobile_generation"),
            metrics={"national_mobile_generators_28_nov": 253},
            resources=[
                {"pool": "mobile_generators", "operation": "reserve", "quantity": 1},
                {"pool": "mobile_fuel", "operation": "reserve", "quantity": 1},
            ],
        ),
        _entry(
            "hv_repair",
            "2021-11-28T12:00:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            action=_action("hv_segment", "start_repair", "under_repair"),
            process=("storm_mass_outage_l1", "repair_hv"),
        ),
        _entry(
            "distribution_repair",
            "2021-11-28T12:05:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            action=_action("distribution_segment", "start_repair", "under_repair"),
            process=("storm_mass_outage_l1", "repair_distribution"),
        ),
        _entry(
            "nested_fault",
            "2021-11-28T15:00:00+00:00",
            entry_kind="process_action",
            evidence="reported",
            source="e3c_final",
            fact="nested_fault_discovered",
            action=_action("distribution_segment", "discover_nested_fault", "faulted_unsafe"),
            process=("storm_mass_outage_l1", "nested_fault_loop"),
            situations=["prolonged_outage"],
        ),
        _entry(
            "nested_fault_isolated",
            "2021-11-28T15:05:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            action=_action("distribution_segment", "isolate", "isolated"),
        ),
        _entry(
            "nested_fault_repair",
            "2021-11-28T16:00:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            action=_action("distribution_segment", "start_repair", "under_repair"),
            process=("storm_mass_outage_l1", "repair_nested_fault"),
        ),
        _entry(
            "restored_84_1_scope",
            "2021-11-29T09:00:00+00:00",
            entry_kind="process_action",
            evidence="reported",
            source="ofgem_ghd",
            action=_action("customers", "partial_restoration", "partially_restored"),
            metrics={"restored_by_29_nov_percent_ofgem_scope": 84.1},
        ),
        _entry(
            "hv_testing",
            "2021-11-29T10:00:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            action=_action("hv_segment", "start_testing", "testing"),
            process=("storm_mass_outage_l1", "test_hv"),
        ),
        _entry(
            "distribution_testing",
            "2021-11-29T10:05:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            action=_action("distribution_segment", "start_testing", "testing"),
            process=("storm_mass_outage_l1", "test_distribution"),
        ),
        _entry(
            "hv_returned",
            "2021-11-29T11:00:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            action=_action("hv_segment", "return_to_service", "in_service"),
            process=("storm_mass_outage_l1", "restore_hv"),
        ),
        _entry(
            "distribution_returned",
            "2021-11-29T11:05:00+00:00",
            entry_kind="process_action",
            evidence="assumed",
            action=_action("distribution_segment", "return_to_service", "in_service"),
            process=("storm_mass_outage_l1", "restore_distribution"),
            resources=[
                {"pool": "line_kits", "operation": "consume", "quantity": 8},
                {"pool": "line_crews", "operation": "release", "quantity": 6},
            ],
        ),
        _entry(
            "restored_99",
            "2021-12-03T15:00:00+00:00",
            entry_kind="process_action",
            evidence="reported",
            source="e3c_final",
            action=_action("customers", "partial_restoration", "partially_restored"),
            metrics={
                "restored_percent_final_report_scope": 99,
                "national_mobile_generators_3_dec": 664,
            },
        ),
        _entry(
            "restoration_complete",
            "2021-12-10T00:00:00+00:00",
            entry_kind="process_action",
            evidence="reported",
            source="e3c_final",
            action=_action("customers", "complete_restoration", "restored"),
            process=("storm_mass_outage_l1", "complete_restoration"),
            situations=["outage_resolved"],
            metrics={"restored_percent_final_report_scope": 100},
        ),
        _entry(
            "weather_ended",
            "2021-12-10T00:01:00+00:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("weather_profile", "end", "ended"),
        ),
        _entry(
            "response_stabilized",
            "2021-12-10T00:02:00+00:00",
            entry_kind="process_action",
            evidence="derived",
            action=_action("coordination", "stabilize", "stabilized"),
            process=("storm_mass_outage_l1", "stabilize_response"),
        ),
    ],
    "checkpoints": [
        {
            "id": "plant_up_consumer_down",
            "after": "plant_stays_energized",
            "all": [
                {"object": "generating_plant", "state": "energized"},
                {"object": "customers", "state": "outage"},
            ],
        },
        {
            "id": "crew_shortage_branch",
            "after": "external_crews",
            "all": [{"metric": "required_line_crews", "equals": 6}],
            "process_steps": [
                {"process": "storm_mass_outage_l1", "step": "dispatch_external_crews"}
            ],
        },
        {
            "id": "nested_fault_branch",
            "after": "nested_fault",
            "all": [{"fact": "nested_fault_discovered"}],
            "process_steps": [
                {"process": "storm_mass_outage_l1", "step": "nested_fault_loop"}
            ],
        },
        {
            "id": "source_scoped_milestones",
            "after": "restored_99",
            "all": [
                {"metric": "restored_within_24h_percent_e3c_scope", "equals": 83},
                {"metric": "restored_by_29_nov_percent_ofgem_scope", "equals": 84.1},
                {"metric": "restored_percent_final_report_scope", "equals": 99},
            ],
        },
        {
            "id": "full_restoration",
            "after": "restoration_complete",
            "all": [
                {"object": "customers", "state": "restored"},
                {"metric": "restored_percent_final_report_scope", "equals": 100},
            ],
        },
    ],
    "expected_final": {
        "object_states": {
            "weather_profile": "ended",
            "hv_segment": "in_service",
            "distribution_segment": "in_service",
            "generating_plant": "energized",
            "customers": "restored",
            "coordination": "stabilized",
        },
        "situations": [
            "mass_distribution_outage",
            "crew_shortage",
            "prolonged_outage",
            "outage_resolved",
        ],
    },
}


_bind_event_model_objects(STORM_ARWEN)


GB_2019_RESPONSE_STEPS = [
    _step(
        "detect_transmission_fault",
        "Detect Eaton Socon–Wymondley transmission fault",
        target="transmission_circuit",
        capability="fault",
    ),
    _step(
        "clear_transmission_fault",
        "Clear the transmission fault",
        after=["detect_transmission_fault"],
        target="transmission_circuit",
        capability="clear_fault",
    ),
    _step(
        "activate_frequency_response",
        "Activate contracted frequency response",
        after=["detect_transmission_fault"],
        target="eso_response",
        capability="activate",
    ),
    _step(
        "deliver_650mw_response",
        "Deliver at least 650 MW of frequency response",
        after=["activate_frequency_response"],
        target="eso_response",
        capability="deliver_650mw",
    ),
    _step(
        "reenergize_circuit",
        "Automatically re-energize the cleared circuit",
        after=["clear_transmission_fault"],
        target="transmission_circuit",
        capability="reenergize",
    ),
    _step(
        "arrest_frequency_fall",
        "Arrest the frequency fall at 49.1 Hz",
        after=["deliver_650mw_response"],
        target="system_frequency",
        capability="arrest_at_49_1",
    ),
    _step(
        "deliver_900mw_response",
        "Increase frequency response to 900 MW",
        after=["deliver_650mw_response"],
        target="eso_response",
        capability="deliver_900mw",
    ),
    _step(
        "recover_frequency_49_2",
        "Recover system frequency to 49.2 Hz",
        after=["arrest_frequency_fall", "deliver_900mw_response"],
        target="system_frequency",
        capability="recover_to_49_2",
    ),
    _step(
        "deliver_full_response",
        "Deliver all available frequency response",
        after=["recover_frequency_49_2"],
        target="eso_response",
        capability="deliver_full",
    ),
    _step(
        "trigger_lfdd",
        "Trigger low-frequency demand disconnection at 48.8 Hz",
        after=["deliver_full_response"],
        target="system_frequency",
        capability="trigger_lfdd",
    ),
    _step(
        "disconnect_demand",
        "Disconnect 931 MW of demand automatically",
        after=["trigger_lfdd"],
        target="customer_demand",
        capability="shed_931mw",
    ),
    _step(
        "dispatch_control_actions",
        "Dispatch additional generation and reserve actions",
        after=["disconnect_demand"],
        target="eso_response",
        capability="dispatch_control_actions",
    ),
    _step(
        "restore_frequency_50",
        "Restore system frequency to 50 Hz",
        after=["dispatch_control_actions"],
        target="system_frequency",
        capability="restore_to_50",
    ),
    _step(
        "stabilize_response",
        "Confirm the power system is stable and secure",
        after=["restore_frequency_50"],
        target="eso_response",
        capability="stabilize",
    ),
    _step(
        "authorize_demand_restoration",
        "Authorize progressive demand restoration",
        after=["stabilize_response"],
        target="customer_demand",
        capability="begin_restoration",
    ),
    _step(
        "complete_demand_restoration",
        "Confirm all DNO demand restoration is complete",
        after=["authorize_demand_restoration"],
        target="customer_demand",
        capability="complete_restoration",
    ),
]


GB_2019 = {
    "schema_version": 2,
    "id": "gb-power-outage-2019-l1",
    "scenario_id": "gb-2019",
    "name": "Great Britain power outage, 2019 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "ngeso_technical_report",
            "url": "https://www.ofgem.gov.uk/sites/default/files/docs/2019/09/eso_technical_report_-_final.pdf",
            "scope": "millisecond event timeline, generation losses, frequency response and restoration",
            "priority": "primary_operator_report",
        },
        {
            "id": "ofgem_final_report",
            "url": "https://www.ofgem.gov.uk/sites/default/files/docs/9_august_2019_power_outage_report.pdf",
            "scope": "regulatory findings, causes, customer impact and final interpretation",
            "priority": "final_official",
        },
    ],
    "model": {
        "id": "qualification-gb-2019",
        "name": "Great Britain power outage 2019 · event-specific L1 topology",
        "level": 1,
        "topology_revision": 2,
        "scope_note": "Generalized causal topology of the 9 August frequency event from the NGESO and Ofgem final reports.",
        "event_targets": {
            "line_fault": "gb-eaton-wymondley",
            "trip": "gb-little-barford-st1c",
        },
        "nodes": [
            {"id": "gb-external-system", "name": "Remaining Great Britain generation and network", "component_type_id": "external-grid", "x": 40, "y": 220},
            {"id": "gb-eaton-wymondley", "name": "Eaton Socon–Wymondley 400 kV circuit", "component_type_id": "transmission-corridor", "x": 260, "y": 220, "qualification_object_id": "transmission_circuit"},
            {"id": "gb-vector-shift-dg", "name": "Vector-shift distributed generation", "component_type_id": "distributed-generation", "x": 260, "y": 40, "capacity_mw": 150, "qualification_object_id": "vector_shift_generation"},
            {"id": "gb-rocof-dg", "name": "RoCoF distributed generation", "component_type_id": "distributed-generation", "x": 480, "y": 40, "capacity_mw": 350, "qualification_object_id": "rocof_generation"},
            {"id": "gb-hornsea-one", "name": "Hornsea One offshore wind farm", "component_type_id": "wind-plant", "x": 260, "y": 400, "capacity_mw": 799, "parameters": {"availability": 1.0}, "qualification_object_id": "hornsea_one"},
            {"id": "gb-little-barford-st1c", "name": "Little Barford steam turbine ST1C", "component_type_id": "thermal-plant", "x": 480, "y": 400, "capacity_mw": 244, "parameters": {"fuel_kind": "waste_heat_recovery"}, "qualification_object_id": "little_barford_steam"},
            {"id": "gb-little-barford-gt1a", "name": "Little Barford gas turbine GT1A", "component_type_id": "thermal-plant", "x": 700, "y": 400, "capacity_mw": 210, "parameters": {"fuel_kind": "natural_gas"}, "qualification_object_id": "little_barford_gt1a"},
            {"id": "gb-little-barford-gt1b", "name": "Little Barford gas turbine GT1B", "component_type_id": "thermal-plant", "x": 920, "y": 400, "capacity_mw": 187, "parameters": {"fuel_kind": "natural_gas"}, "qualification_object_id": "little_barford_gt1b"},
            {"id": "gb-main-system", "name": "Great Britain synchronous system", "component_type_id": "grid-zone", "x": 700, "y": 220},
            {"id": "gb-frequency", "name": "Great Britain system frequency", "component_type_id": "system-state", "x": 920, "y": 40, "qualification_object_id": "system_frequency"},
            {"id": "gb-eso-response", "name": "ESO frequency response and control-room action", "component_type_id": "response-process", "x": 1140, "y": 40, "qualification_object_id": "eso_response"},
            {
                "id": "gb-customer-demand",
                "name": "Demand connected through distribution networks",
                "component_type_id": "customer-group",
                "x": 1140,
                "y": 220,
                "parameters": {
                    "mode": "load",
                    "demand_mw": 2080,
                    "shed_scope_mw": 931,
                    "evidence_kind": "derived",
                    "model_basis": "L1 equivalent operating-point demand; the reported 931 MW LFDD scope remains a separate sourced metric",
                },
                "qualification_object_id": "customer_demand",
            },
            {"id": "gb-lfdd", "name": "Low-frequency demand disconnection", "component_type_id": "protection-system", "x": 920, "y": 220},
        ],
        "edges": [
            {"id": "gb-edge-external-circuit", "source": "gb-external-system", "target": "gb-eaton-wymondley"},
            {"id": "gb-edge-circuit-grid", "source": "gb-eaton-wymondley", "target": "gb-main-system"},
            {"id": "gb-edge-vector-grid", "source": "gb-vector-shift-dg", "target": "gb-main-system"},
            {"id": "gb-edge-rocof-grid", "source": "gb-rocof-dg", "target": "gb-main-system"},
            {"id": "gb-edge-hornsea-grid", "source": "gb-hornsea-one", "target": "gb-main-system"},
            {"id": "gb-edge-st1c-grid", "source": "gb-little-barford-st1c", "target": "gb-main-system"},
            {"id": "gb-edge-gt1a-grid", "source": "gb-little-barford-gt1a", "target": "gb-main-system"},
            {"id": "gb-edge-gt1b-grid", "source": "gb-little-barford-gt1b", "target": "gb-main-system"},
            {"id": "gb-edge-grid-demand", "source": "gb-main-system", "target": "gb-customer-demand"},
        ],
    },
    "objects": [
        _object(
            "transmission_circuit",
            "Eaton Socon–Wymondley 400 kV circuit",
            "transmission_circuit",
            "energized",
            ["energized", "faulted", "cleared", "reenergized"],
            {
                "fault": _transitions(("energized", "faulted")),
                "clear_fault": _transitions(("faulted", "cleared")),
                "reenergize": _transitions(("cleared", "reenergized")),
            },
        ),
        _object(
            "vector_shift_generation",
            "Distributed generation with vector-shift protection",
            "distributed_generation",
            "online",
            ["online", "tripped_150mw"],
            {"trip_150mw": _transitions(("online", "tripped_150mw"))},
        ),
        _object(
            "rocof_generation",
            "Distributed generation with RoCoF protection",
            "distributed_generation",
            "online",
            ["online", "tripped_350mw"],
            {"trip_350mw": _transitions(("online", "tripped_350mw"))},
        ),
        _object(
            "hornsea_one",
            "Hornsea One offshore wind farm",
            "generator",
            "generating_799mw",
            ["generating_799mw", "deloaded_62mw"],
            {"deload": _transitions(("generating_799mw", "deloaded_62mw"))},
        ),
        _object(
            "little_barford_steam",
            "Little Barford steam turbine ST1C",
            "generator",
            "generating_244mw",
            ["generating_244mw", "tripped"],
            {"trip": _transitions(("generating_244mw", "tripped"))},
        ),
        _object(
            "little_barford_gt1a",
            "Little Barford gas turbine GT1A",
            "generator",
            "generating_210mw",
            ["generating_210mw", "tripped"],
            {"trip": _transitions(("generating_210mw", "tripped"))},
        ),
        _object(
            "little_barford_gt1b",
            "Little Barford gas turbine GT1B",
            "generator",
            "generating_187mw",
            ["generating_187mw", "tripped"],
            {"trip": _transitions(("generating_187mw", "tripped"))},
        ),
        _object(
            "system_frequency",
            "Great Britain system frequency",
            "system_state",
            "nominal_50",
            [
                "nominal_50",
                "falling",
                "arrested_49_1",
                "recovered_49_2",
                "falling_again",
                "lfdd_48_8",
                "restored_50",
            ],
            {
                "begin_fall": _transitions(("nominal_50", "falling")),
                "arrest_at_49_1": _transitions(("falling", "arrested_49_1")),
                "recover_to_49_2": _transitions(("arrested_49_1", "recovered_49_2")),
                "fall_again": _transitions(("recovered_49_2", "falling_again")),
                "trigger_lfdd": _transitions(("falling_again", "lfdd_48_8")),
                "restore_to_50": _transitions(("lfdd_48_8", "restored_50")),
            },
        ),
        _object(
            "eso_response",
            "ESO frequency response and control-room action",
            "response_process",
            "holding_for_1000mw",
            [
                "holding_for_1000mw",
                "activated",
                "delivered_650mw",
                "delivered_900mw",
                "full_delivery",
                "control_actions_dispatched",
                "stable_secure",
            ],
            {
                "activate": _transitions(("holding_for_1000mw", "activated")),
                "deliver_650mw": _transitions(("activated", "delivered_650mw")),
                "deliver_900mw": _transitions(("delivered_650mw", "delivered_900mw")),
                "deliver_full": _transitions(("delivered_900mw", "full_delivery")),
                "dispatch_control_actions": _transitions(
                    ("full_delivery", "control_actions_dispatched")
                ),
                "stabilize": _transitions(
                    ("control_actions_dispatched", "stable_secure")
                ),
            },
        ),
        _object(
            "customer_demand",
            "Demand connected through distribution networks",
            "customer_group",
            "connected",
            ["connected", "shed_931mw", "restoring", "restored"],
            {
                "shed_931mw": _transitions(("connected", "shed_931mw")),
                "begin_restoration": _transitions(("shed_931mw", "restoring")),
                "complete_restoration": _transitions(("restoring", "restored")),
            },
        ),
    ],
    "situations": [
        {
            "id": "transmission_fault",
            "all": [{"object": "transmission_circuit", "state": "faulted"}],
        },
        {
            "id": "generation_loss_exceeds_held_contingency",
            "all": [{"metric": "cumulative_infeed_loss_mw", "at_least": 1481}],
        },
        {
            "id": "low_frequency_emergency",
            "all": [{"object": "system_frequency", "state": "lfdd_48_8"}],
        },
        {
            "id": "automatic_demand_disconnection",
            "all": [{"object": "customer_demand", "state": "shed_931mw"}],
        },
        {
            "id": "system_stabilized",
            "all": [
                {"object": "system_frequency", "state": "restored_50"},
                {"object": "eso_response", "state": "stable_secure"},
                {"object": "customer_demand", "state": "restored"},
            ],
        },
    ],
    "processes": [
        _process(
            "gb_frequency_emergency_response_l1",
            "GB frequency emergency response L1",
            GB_2019_RESPONSE_STEPS,
        )
    ],
    "timeline": [
        _entry(
            "pre_fault_secure_state",
            "2019-08-09T16:52:26+01:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="ngeso_technical_report",
            fact="eso_secured_for_1000mw_loss",
            metrics={"frequency_hz": 50.0, "held_contingency_mw": 1000},
        ),
        _entry(
            "eaton_wymondley_fault",
            "2019-08-09T16:52:33.490+01:00",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("transmission_circuit", "fault", "faulted"),
            process=("gb_frequency_emergency_response_l1", "detect_transmission_fault"),
            situations=["transmission_fault"],
        ),
        _entry(
            "vector_shift_trip",
            "2019-08-09T16:52:33.491+01:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("vector_shift_generation", "trip_150mw", "tripped_150mw"),
            metrics={"cumulative_infeed_loss_mw": 150},
        ),
        _entry(
            "fault_cleared",
            "2019-08-09T16:52:33.564+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("transmission_circuit", "clear_fault", "cleared"),
            process=("gb_frequency_emergency_response_l1", "clear_transmission_fault"),
            metrics={"fault_clearance_ms": 74},
        ),
        _entry(
            "hornsea_deload",
            "2019-08-09T16:52:33.835+01:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("hornsea_one", "deload", "deloaded_62mw"),
            metrics={"cumulative_infeed_loss_mw": 887, "hornsea_loss_mw": 737},
        ),
        _entry(
            "little_barford_steam_trip",
            "2019-08-09T16:52:34+01:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("little_barford_steam", "trip", "tripped"),
            metrics={"cumulative_infeed_loss_mw": 1131},
        ),
        _entry(
            "rocof_generation_trip",
            "2019-08-09T16:52:34.001+01:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("rocof_generation", "trip_350mw", "tripped_350mw"),
            situations=["generation_loss_exceeds_held_contingency"],
            metrics={"cumulative_infeed_loss_mw": 1481},
        ),
        _entry(
            "frequency_falling",
            "2019-08-09T16:52:34.002+01:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("system_frequency", "begin_fall", "falling"),
        ),
        _entry(
            "frequency_response_activated",
            "2019-08-09T16:52:34.003+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("eso_response", "activate", "activated"),
            process=("gb_frequency_emergency_response_l1", "activate_frequency_response"),
        ),
        _entry(
            "response_650mw",
            "2019-08-09T16:52:44+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("eso_response", "deliver_650mw", "delivered_650mw"),
            process=("gb_frequency_emergency_response_l1", "deliver_650mw_response"),
            metrics={"frequency_response_mw": 650},
        ),
        _entry(
            "circuit_reenergized",
            "2019-08-09T16:52:53+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("transmission_circuit", "reenergize", "reenergized"),
            process=("gb_frequency_emergency_response_l1", "reenergize_circuit"),
        ),
        _entry(
            "frequency_arrested",
            "2019-08-09T16:52:58+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("system_frequency", "arrest_at_49_1", "arrested_49_1"),
            process=("gb_frequency_emergency_response_l1", "arrest_frequency_fall"),
            metrics={"frequency_hz": 49.1},
        ),
        _entry(
            "response_900mw",
            "2019-08-09T16:53:04+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("eso_response", "deliver_900mw", "delivered_900mw"),
            process=("gb_frequency_emergency_response_l1", "deliver_900mw_response"),
            metrics={"frequency_response_mw": 900},
        ),
        _entry(
            "frequency_recovered_49_2",
            "2019-08-09T16:53:18+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("system_frequency", "recover_to_49_2", "recovered_49_2"),
            process=("gb_frequency_emergency_response_l1", "recover_frequency_49_2"),
            metrics={"frequency_hz": 49.2},
        ),
        _entry(
            "little_barford_gt1a_trip",
            "2019-08-09T16:53:31+01:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("little_barford_gt1a", "trip", "tripped"),
            metrics={"cumulative_infeed_loss_mw": 1691},
        ),
        _entry(
            "frequency_falling_again",
            "2019-08-09T16:53:31.001+01:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("system_frequency", "fall_again", "falling_again"),
        ),
        _entry(
            "full_frequency_response",
            "2019-08-09T16:53:31.002+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("eso_response", "deliver_full", "full_delivery"),
            process=("gb_frequency_emergency_response_l1", "deliver_full_response"),
        ),
        _entry(
            "lfdd_triggered",
            "2019-08-09T16:53:49.398+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("system_frequency", "trigger_lfdd", "lfdd_48_8"),
            process=("gb_frequency_emergency_response_l1", "trigger_lfdd"),
            situations=["low_frequency_emergency"],
            metrics={"frequency_hz": 48.8},
        ),
        _entry(
            "demand_931mw_disconnected",
            "2019-08-09T16:53:49.399+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("customer_demand", "shed_931mw", "shed_931mw"),
            process=("gb_frequency_emergency_response_l1", "disconnect_demand"),
            situations=["automatic_demand_disconnection"],
            metrics={"disconnected_demand_mw": 931, "affected_customers": 1100000},
        ),
        _entry(
            "little_barford_gt1b_trip",
            "2019-08-09T16:53:58+01:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("little_barford_gt1b", "trip", "tripped"),
            metrics={"cumulative_infeed_loss_mw": 1878},
        ),
        _entry(
            "control_actions_dispatched",
            "2019-08-09T16:54:20+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action(
                "eso_response", "dispatch_control_actions", "control_actions_dispatched"
            ),
            process=("gb_frequency_emergency_response_l1", "dispatch_control_actions"),
            metrics={"additional_control_actions_mw": 1240},
        ),
        _entry(
            "frequency_restored_50",
            "2019-08-09T16:57:15+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("system_frequency", "restore_to_50", "restored_50"),
            process=("gb_frequency_emergency_response_l1", "restore_frequency_50"),
            metrics={"frequency_hz": 50.0},
        ),
        _entry(
            "response_stable_secure",
            "2019-08-09T16:57:16+01:00",
            entry_kind="process_action",
            evidence="derived",
            action=_action("eso_response", "stabilize", "stable_secure"),
            process=("gb_frequency_emergency_response_l1", "stabilize_response"),
        ),
        _entry(
            "demand_restoration_authorized",
            "2019-08-09T16:58:00+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("customer_demand", "begin_restoration", "restoring"),
            process=("gb_frequency_emergency_response_l1", "authorize_demand_restoration"),
        ),
        _entry(
            "demand_restoration_complete",
            "2019-08-09T17:37:00+01:00",
            entry_kind="process_action",
            evidence="reported",
            source="ngeso_technical_report",
            action=_action("customer_demand", "complete_restoration", "restored"),
            process=("gb_frequency_emergency_response_l1", "complete_demand_restoration"),
            situations=["system_stabilized"],
            metrics={"restoration_complete_percent": 100},
        ),
    ],
    "checkpoints": [
        {
            "id": "fault_cleared_74ms",
            "after": "fault_cleared",
            "all": [
                {"object": "transmission_circuit", "state": "cleared"},
                {"metric": "fault_clearance_ms", "equals": 74},
            ],
        },
        {
            "id": "held_contingency_exceeded",
            "after": "rocof_generation_trip",
            "all": [{"metric": "cumulative_infeed_loss_mw", "equals": 1481}],
        },
        {
            "id": "lfdd_931mw",
            "after": "demand_931mw_disconnected",
            "all": [
                {"object": "system_frequency", "state": "lfdd_48_8"},
                {"metric": "disconnected_demand_mw", "equals": 931},
            ],
        },
        {
            "id": "frequency_restored_five_minutes",
            "after": "frequency_restored_50",
            "all": [{"metric": "frequency_hz", "equals": 50.0}],
        },
        {
            "id": "all_dno_demand_restored",
            "after": "demand_restoration_complete",
            "all": [
                {"object": "customer_demand", "state": "restored"},
                {"metric": "restoration_complete_percent", "equals": 100},
            ],
        },
    ],
    "expected_final": {
        "object_states": {
            "transmission_circuit": "reenergized",
            "system_frequency": "restored_50",
            "eso_response": "stable_secure",
            "customer_demand": "restored",
        },
        "situations": [
            "generation_loss_exceeds_held_contingency",
            "low_frequency_emergency",
            "automatic_demand_disconnection",
            "system_stabilized",
        ],
    },
}


_bind_event_model_objects(GB_2019)


SA_2016_CASCADE_STEPS = [
    _step(
        "trip_brinkworth_templers",
        "Trip damaged Brinkworth–Templers West line",
        target="brinkworth_templers",
        capability="damage_trip",
    ),
    _step(
        "first_davenport_belalie_fault",
        "Clear and automatically reclose first Davenport–Belalie fault",
        after=["trip_brinkworth_templers"],
        target="davenport_belalie",
        capability="fault_and_reclose",
    ),
    _step(
        "second_davenport_belalie_fault",
        "Trip Davenport–Belalie after the second fault",
        after=["first_davenport_belalie_fault"],
        target="davenport_belalie",
        capability="damage_trip",
    ),
    _step(
        "trip_davenport_mt_lock",
        "Trip damaged Davenport–Mount Lock line",
        after=["second_davenport_belalie_fault"],
        target="davenport_mt_lock",
        capability="damage_trip",
    ),
    _step(
        "reduce_wind_generation",
        "Apply sustained wind-farm protection reduction",
        after=["trip_davenport_mt_lock"],
        target="wind_fleet",
        capability="protection_reduce",
    ),
    _step(
        "surge_heywood_import",
        "Increase Heywood import after generation loss",
        after=["reduce_wind_generation"],
        target="heywood_interconnector",
        capability="surge",
    ),
    _step(
        "trip_heywood",
        "Trip Heywood interconnector protection scheme",
        after=["surge_heywood_import"],
        target="heywood_interconnector",
        capability="trip",
    ),
    _step(
        "island_sa",
        "Separate South Australia from the NEM",
        after=["trip_heywood"],
        target="sa_power_system",
        capability="island",
    ),
    _step(
        "enter_black_system",
        "Enter Black System after frequency collapse",
        after=["island_sa"],
        target="sa_power_system",
        capability="blackout",
    ),
    _step(
        "disconnect_customers",
        "Record loss of supply to South Australian customers",
        after=["enter_black_system"],
        target="customer_supply",
        capability="lose_supply",
    ),
]


SA_2016_RECOVERY_STEPS = [
    _step(
        "suspend_market",
        "Suspend the NEM market in South Australia",
        target="sa_market",
        capability="suspend",
    ),
    _step(
        "assess_network",
        "Assess transmission network condition",
        target="recovery_coordination",
        capability="begin_assessment",
    ),
    _step(
        "make_network_safe",
        "Confirm damaged network sections are safe",
        after=["assess_network"],
        target="recovery_coordination",
        capability="confirm_safe",
    ),
    _step(
        "activate_restart_plan",
        "Activate the system restart plan",
        after=["make_network_safe"],
        target="recovery_coordination",
        capability="activate_plan",
    ),
    _step(
        "enable_heywood_restart_supply",
        "Use supply from Victoria through Heywood for restart",
        after=["activate_restart_plan"],
        target="heywood_interconnector",
        capability="enable_restart_supply",
    ),
    _step(
        "begin_system_restart",
        "Begin staged energisation of the SA system",
        after=["enable_heywood_restart_supply"],
        target="sa_power_system",
        capability="begin_restart",
    ),
    _step(
        "restore_first_customers",
        "Restore supply to the first customers",
        after=["begin_system_restart"],
        target="customer_supply",
        capability="restore_first",
    ),
    _step(
        "establish_partial_system",
        "Establish a stable partially supplied system",
        after=["restore_first_customers"],
        target="sa_power_system",
        capability="establish_partial_supply",
    ),
    _step(
        "restore_40_percent",
        "Restore 40 percent of restorable load",
        after=["establish_partial_system"],
        target="customer_supply",
        capability="restore_40_percent",
    ),
    _step(
        "restore_85_percent",
        "Restore approximately 80–90 percent of load",
        after=["restore_40_percent"],
        target="customer_supply",
        capability="restore_85_percent",
    ),
    _step(
        "complete_customer_restoration",
        "Restore supply to all customers after network bypass work",
        after=["restore_85_percent"],
        target="customer_supply",
        capability="complete_restoration",
    ),
    _step(
        "stabilize_system",
        "Confirm stable supply after full restoration",
        after=["complete_customer_restoration"],
        target="sa_power_system",
        capability="stabilize_supply",
    ),
    _step(
        "complete_recovery",
        "Complete coordinated system recovery",
        after=["stabilize_system"],
        target="recovery_coordination",
        capability="complete",
    ),
    _step(
        "resume_market",
        "Resume the NEM market in South Australia",
        after=["complete_recovery"],
        target="sa_market",
        capability="resume",
    ),
]


SOUTH_AUSTRALIA_2016 = {
    "schema_version": 2,
    "id": "south-australia-black-system-2016-l1",
    "scenario_id": "south-australia-2016",
    "name": "South Australia Black System, 2016 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "aemo_final_report",
            "url": "https://aemo.com.au/-/media/Files/Electricity/NEM/Market_Notices_and_Events/Power_System_Incident_Reports/2017/Integrated-Final-Report-SA-Black-System-28-September-2016.pdf",
            "scope": "fault sequence, wind response, system separation, black system and restoration milestones",
            "priority": "final_primary_operator_report",
        },
        {
            "id": "aemo_incident_index",
            "url": "https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-events-and-reports/power-system-operating-incident-reports",
            "scope": "publication status and final-report provenance",
            "priority": "official_index",
        },
    ],
    "model": {
        "id": "qualification-south-australia-2016",
        "name": "South Australia black system 2016 · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Causal L1 topology of the South Australian black-system event, based on the AEMO final report; geographic detail is intentionally omitted.",
        "event_targets": {
            "line_fault": "sa-brinkworth-templers",
            "trip": "sa-heywood",
        },
        "nodes": [
            {"id": "sa-severe-weather", "name": "Severe weather and repeated voltage disturbances", "component_type_id": "external-hazard", "x": 40, "y": 40},
            {"id": "sa-brinkworth-templers", "name": "Brinkworth–Templers West 275 kV line", "component_type_id": "transmission-corridor", "x": 260, "y": 40, "qualification_object_id": "brinkworth_templers"},
            {"id": "sa-davenport-belalie", "name": "Davenport–Belalie 275 kV line", "component_type_id": "transmission-corridor", "x": 480, "y": 40, "qualification_object_id": "davenport_belalie"},
            {"id": "sa-davenport-mt-lock", "name": "Davenport–Mount Lock 275 kV line", "component_type_id": "transmission-corridor", "x": 700, "y": 40, "qualification_object_id": "davenport_mt_lock"},
            {"id": "sa-wind-fleet", "name": "South Australian wind-farm aggregate", "component_type_id": "wind-plant", "x": 260, "y": 260, "capacity_mw": 883, "parameters": {"availability": 1.0, "reported_sustained_reduction_mw": 456}, "qualification_object_id": "wind_fleet"},
            {"id": "sa-gas-generation", "name": "South Australian gas-fired synchronous generation", "component_type_id": "thermal-plant", "x": 480, "y": 260, "capacity_mw": 330, "parameters": {"fuel_kind": "natural_gas", "evidence_kind": "reported"}},
            {"id": "sa-victoria-grid", "name": "Victorian power system", "component_type_id": "external-grid", "x": 40, "y": 440, "parameters": {"reported_import_mw": 613}},
            {"id": "sa-heywood", "name": "Victoria–SA Heywood AC interconnector", "component_type_id": "transmission-corridor", "x": 260, "y": 440, "parameters": {"reported_import_mw": 613}, "qualification_object_id": "heywood_interconnector"},
            {"id": "sa-power-system", "name": "South Australian power system", "component_type_id": "grid-zone", "x": 700, "y": 260, "qualification_object_id": "sa_power_system"},
            {"id": "sa-customer-supply", "name": "South Australian customer supply", "component_type_id": "customer-group", "x": 920, "y": 260, "parameters": {"mode": "load", "demand_mw": 1826, "affected_customers": 850000}, "qualification_object_id": "customer_supply"},
            {"id": "sa-voltage-protection", "name": "Wind-farm ride-through and network protection", "component_type_id": "protection-system", "x": 480, "y": 440},
            {"id": "sa-recovery", "name": "AEMO and ElectraNet recovery coordination", "component_type_id": "response-process", "x": 700, "y": 440, "qualification_object_id": "recovery_coordination"},
            {"id": "sa-market", "name": "NEM market operation in South Australia", "component_type_id": "response-process", "x": 920, "y": 440, "qualification_object_id": "sa_market"},
        ],
        "edges": [
            {"id": "sa-edge-victoria-heywood", "source": "sa-victoria-grid", "target": "sa-heywood"},
            {"id": "sa-edge-heywood-system", "source": "sa-heywood", "target": "sa-power-system"},
            {"id": "sa-edge-wind-system", "source": "sa-wind-fleet", "target": "sa-power-system"},
            {"id": "sa-edge-gas-system", "source": "sa-gas-generation", "target": "sa-power-system"},
            {"id": "sa-edge-brinkworth-system", "source": "sa-brinkworth-templers", "target": "sa-power-system"},
            {"id": "sa-edge-belalie-system", "source": "sa-davenport-belalie", "target": "sa-power-system"},
            {"id": "sa-edge-mt-lock-system", "source": "sa-davenport-mt-lock", "target": "sa-power-system"},
            {"id": "sa-edge-system-customers", "source": "sa-power-system", "target": "sa-customer-supply"},
        ],
    },
    "objects": [
        _object(
            "brinkworth_templers",
            "Brinkworth–Templers West 275 kV line",
            "transmission_line",
            "in_service",
            ["in_service", "damaged_tripped"],
            {"damage_trip": _transitions(("in_service", "damaged_tripped"))},
        ),
        _object(
            "davenport_belalie",
            "Davenport–Belalie 275 kV line",
            "transmission_line",
            "in_service",
            ["in_service", "fault_reclosed", "damaged_tripped"],
            {
                "fault_and_reclose": _transitions(("in_service", "fault_reclosed")),
                "damage_trip": _transitions(("fault_reclosed", "damaged_tripped")),
            },
        ),
        _object(
            "davenport_mt_lock",
            "Davenport–Mount Lock 275 kV line",
            "transmission_line",
            "in_service",
            ["in_service", "damaged_tripped"],
            {"damage_trip": _transitions(("in_service", "damaged_tripped"))},
        ),
        _object(
            "wind_fleet",
            "South Australian wind-farm aggregate",
            "generation_fleet",
            "generating_883mw",
            ["generating_883mw", "sustained_reduction_456mw"],
            {
                "protection_reduce": _transitions(
                    ("generating_883mw", "sustained_reduction_456mw")
                )
            },
        ),
        _object(
            "heywood_interconnector",
            "Victoria–SA Heywood interconnector",
            "interconnector",
            "importing",
            ["importing", "surging", "tripped", "restart_supply"],
            {
                "surge": _transitions(("importing", "surging")),
                "trip": _transitions(("surging", "tripped")),
                "enable_restart_supply": _transitions(("tripped", "restart_supply")),
            },
        ),
        _object(
            "sa_power_system",
            "South Australian power system",
            "power_system",
            "interconnected",
            [
                "interconnected",
                "islanded",
                "black_system",
                "restarting",
                "partial_supply",
                "stable_supply",
            ],
            {
                "island": _transitions(("interconnected", "islanded")),
                "blackout": _transitions(("islanded", "black_system")),
                "begin_restart": _transitions(("black_system", "restarting")),
                "establish_partial_supply": _transitions(
                    ("restarting", "partial_supply")
                ),
                "stabilize_supply": _transitions(("partial_supply", "stable_supply")),
            },
        ),
        _object(
            "customer_supply",
            "South Australian customer supply",
            "customer_group",
            "supplied_1826mw",
            [
                "supplied_1826mw",
                "outage",
                "first_customers_restored",
                "restored_40_percent",
                "restored_85_percent",
                "restored_all",
            ],
            {
                "lose_supply": _transitions(("supplied_1826mw", "outage")),
                "restore_first": _transitions(("outage", "first_customers_restored")),
                "restore_40_percent": _transitions(
                    ("first_customers_restored", "restored_40_percent")
                ),
                "restore_85_percent": _transitions(
                    ("restored_40_percent", "restored_85_percent")
                ),
                "complete_restoration": _transitions(
                    ("restored_85_percent", "restored_all")
                ),
            },
        ),
        _object(
            "recovery_coordination",
            "AEMO and ElectraNet recovery coordination",
            "response_process",
            "monitoring",
            [
                "monitoring",
                "assessing",
                "network_safe",
                "restart_plan_active",
                "complete",
            ],
            {
                "begin_assessment": _transitions(("monitoring", "assessing")),
                "confirm_safe": _transitions(("assessing", "network_safe")),
                "activate_plan": _transitions(
                    ("network_safe", "restart_plan_active")
                ),
                "complete": _transitions(("restart_plan_active", "complete")),
            },
        ),
        _object(
            "sa_market",
            "NEM market operation in South Australia",
            "market_operation",
            "normal",
            ["normal", "suspended", "resumed"],
            {
                "suspend": _transitions(("normal", "suspended")),
                "resume": _transitions(("suspended", "resumed")),
            },
        ),
    ],
    "situations": [
        {
            "id": "three_transmission_lines_lost",
            "all": [
                {"object": "brinkworth_templers", "state": "damaged_tripped"},
                {"object": "davenport_belalie", "state": "damaged_tripped"},
                {"object": "davenport_mt_lock", "state": "damaged_tripped"},
            ],
        },
        {
            "id": "sustained_wind_generation_reduction",
            "all": [{"metric": "sustained_wind_reduction_mw", "at_least": 456}],
        },
        {
            "id": "south_australia_islanded",
            "all": [{"object": "sa_power_system", "state": "islanded"}],
        },
        {
            "id": "black_system",
            "all": [{"object": "sa_power_system", "state": "black_system"}],
        },
        {
            "id": "supply_restored_and_stable",
            "all": [
                {"object": "customer_supply", "state": "restored_all"},
                {"object": "sa_power_system", "state": "stable_supply"},
            ],
        },
    ],
    "processes": [
        _process(
            "sa_automatic_cascade_l1",
            "South Australia automatic cascade L1",
            SA_2016_CASCADE_STEPS,
        ),
        _process(
            "sa_system_recovery_l1",
            "South Australia system recovery L1",
            SA_2016_RECOVERY_STEPS,
        ),
    ],
    "timeline": [
        _entry(
            "pre_event_operating_state",
            "2016-09-28T16:16:45+09:30",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="aemo_final_report",
            metrics={
                "sa_demand_mw": 1826,
                "wind_generation_mw": 883,
                "gas_generation_mw": 330,
                "victoria_imports_mw": 613,
            },
        ),
        _entry(
            "northfield_harrow_fault",
            "2016-09-28T16:16:46+09:30",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="aemo_final_report",
            fact="first_of_five_faults_in_87_seconds",
        ),
        _entry(
            "brinkworth_templers_trip",
            "2016-09-28T16:17:33+09:30",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="aemo_final_report",
            action=_action("brinkworth_templers", "damage_trip", "damaged_tripped"),
            process=("sa_automatic_cascade_l1", "trip_brinkworth_templers"),
            metrics={"voltage_disturbance_count": 1},
        ),
        _entry(
            "davenport_belalie_first_fault",
            "2016-09-28T16:17:59+09:30",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="aemo_final_report",
            action=_action(
                "davenport_belalie", "fault_and_reclose", "fault_reclosed"
            ),
            process=("sa_automatic_cascade_l1", "first_davenport_belalie_fault"),
            metrics={"voltage_disturbance_count": 2},
        ),
        _entry(
            "davenport_belalie_reclosed",
            "2016-09-28T16:18:00+09:30",
            entry_kind="derived",
            evidence="derived",
            fact="davenport_belalie_auto_reclose_completed",
        ),
        _entry(
            "davenport_belalie_second_fault",
            "2016-09-28T16:18:08+09:30",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="aemo_final_report",
            action=_action("davenport_belalie", "damage_trip", "damaged_tripped"),
            process=("sa_automatic_cascade_l1", "second_davenport_belalie_fault"),
            metrics={"voltage_disturbance_count": 4},
        ),
        _entry(
            "davenport_mt_lock_trip",
            "2016-09-28T16:18:13+09:30",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="aemo_final_report",
            action=_action("davenport_mt_lock", "damage_trip", "damaged_tripped"),
            process=("sa_automatic_cascade_l1", "trip_davenport_mt_lock"),
            situations=["three_transmission_lines_lost"],
            metrics={"voltage_disturbance_count": 6, "fault_window_seconds": 87},
        ),
        _entry(
            "wind_generation_reduced",
            "2016-09-28T16:18:15.400+09:30",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="aemo_final_report",
            action=_action(
                "wind_fleet", "protection_reduce", "sustained_reduction_456mw"
            ),
            process=("sa_automatic_cascade_l1", "reduce_wind_generation"),
            situations=["sustained_wind_generation_reduction"],
            metrics={
                "sustained_wind_reduction_mw": 456,
                "wind_reduction_window_seconds": 7,
            },
        ),
        _entry(
            "heywood_flow_surge",
            "2016-09-28T16:18:15.500+09:30",
            entry_kind="derived",
            evidence="derived",
            action=_action("heywood_interconnector", "surge", "surging"),
            process=("sa_automatic_cascade_l1", "surge_heywood_import"),
        ),
        _entry(
            "heywood_trip",
            "2016-09-28T16:18:15.802+09:30",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="aemo_final_report",
            action=_action("heywood_interconnector", "trip", "tripped"),
            process=("sa_automatic_cascade_l1", "trip_heywood"),
            metrics={"heywood_trip_delay_ms": 700},
        ),
        _entry(
            "sa_system_islanded",
            "2016-09-28T16:18:15.803+09:30",
            entry_kind="derived",
            evidence="derived",
            action=_action("sa_power_system", "island", "islanded"),
            process=("sa_automatic_cascade_l1", "island_sa"),
            situations=["south_australia_islanded"],
            metrics={"island_supply_demand_imbalance_mw": 1000},
        ),
        _entry(
            "sa_black_system",
            "2016-09-28T16:18:16.200+09:30",
            entry_kind="derived",
            evidence="derived",
            action=_action("sa_power_system", "blackout", "black_system"),
            process=("sa_automatic_cascade_l1", "enter_black_system"),
            situations=["black_system"],
        ),
        _entry(
            "customer_supply_lost",
            "2016-09-28T16:18:16.201+09:30",
            entry_kind="derived",
            evidence="derived",
            action=_action("customer_supply", "lose_supply", "outage"),
            process=("sa_automatic_cascade_l1", "disconnect_customers"),
            metrics={"affected_customers": 850000},
        ),
        _entry(
            "market_suspended",
            "2016-09-28T16:20:00+09:30",
            entry_kind="process_action",
            evidence="derived",
            action=_action("sa_market", "suspend", "suspended"),
            process=("sa_system_recovery_l1", "suspend_market"),
        ),
        _entry(
            "network_assessment_started",
            "2016-09-28T16:21:00+09:30",
            entry_kind="process_action",
            evidence="derived",
            action=_action(
                "recovery_coordination", "begin_assessment", "assessing"
            ),
            process=("sa_system_recovery_l1", "assess_network"),
        ),
        _entry(
            "damaged_network_made_safe",
            "2016-09-28T16:29:00+09:30",
            entry_kind="process_action",
            evidence="derived",
            action=_action("recovery_coordination", "confirm_safe", "network_safe"),
            process=("sa_system_recovery_l1", "make_network_safe"),
        ),
        _entry(
            "restart_plan_activated",
            "2016-09-28T16:30:00+09:30",
            entry_kind="process_action",
            evidence="reported",
            source="aemo_final_report",
            action=_action(
                "recovery_coordination", "activate_plan", "restart_plan_active"
            ),
            process=("sa_system_recovery_l1", "activate_restart_plan"),
        ),
        _entry(
            "heywood_restart_supply_enabled",
            "2016-09-28T16:31:00+09:30",
            entry_kind="process_action",
            evidence="derived",
            action=_action(
                "heywood_interconnector", "enable_restart_supply", "restart_supply"
            ),
            process=("sa_system_recovery_l1", "enable_heywood_restart_supply"),
        ),
        _entry(
            "system_restart_begun",
            "2016-09-28T16:32:00+09:30",
            entry_kind="process_action",
            evidence="derived",
            action=_action("sa_power_system", "begin_restart", "restarting"),
            process=("sa_system_recovery_l1", "begin_system_restart"),
        ),
        _entry(
            "first_customers_restored",
            "2016-09-28T19:00:00+09:30",
            entry_kind="process_action",
            evidence="reported",
            source="aemo_final_report",
            action=_action(
                "customer_supply", "restore_first", "first_customers_restored"
            ),
            process=("sa_system_recovery_l1", "restore_first_customers"),
            metrics={"first_customer_restoration_hours": 2.7},
        ),
        _entry(
            "partial_system_established",
            "2016-09-28T19:01:00+09:30",
            entry_kind="process_action",
            evidence="derived",
            action=_action(
                "sa_power_system", "establish_partial_supply", "partial_supply"
            ),
            process=("sa_system_recovery_l1", "establish_partial_system"),
        ),
        _entry(
            "load_restored_40_percent",
            "2016-09-28T20:30:00+09:30",
            entry_kind="process_action",
            evidence="reported",
            source="aemo_final_report",
            action=_action(
                "customer_supply", "restore_40_percent", "restored_40_percent"
            ),
            process=("sa_system_recovery_l1", "restore_40_percent"),
            metrics={"restoration_percent": 40},
        ),
        _entry(
            "load_restored_85_percent",
            "2016-09-29T00:00:00+09:30",
            entry_kind="process_action",
            evidence="reported",
            source="aemo_final_report",
            action=_action(
                "customer_supply", "restore_85_percent", "restored_85_percent"
            ),
            process=("sa_system_recovery_l1", "restore_85_percent"),
            metrics={"restoration_percent": 85},
        ),
        _entry(
            "all_customer_supply_restored",
            "2016-10-11T17:48:00+10:30",
            entry_kind="process_action",
            evidence="derived",
            action=_action(
                "customer_supply", "complete_restoration", "restored_all"
            ),
            process=("sa_system_recovery_l1", "complete_customer_restoration"),
            metrics={"restoration_percent": 100},
        ),
        _entry(
            "stable_supply_confirmed",
            "2016-10-11T17:49:00+10:30",
            entry_kind="process_action",
            evidence="derived",
            action=_action("sa_power_system", "stabilize_supply", "stable_supply"),
            process=("sa_system_recovery_l1", "stabilize_system"),
            situations=["supply_restored_and_stable"],
        ),
        _entry(
            "coordinated_recovery_complete",
            "2016-10-11T17:50:00+10:30",
            entry_kind="process_action",
            evidence="derived",
            action=_action("recovery_coordination", "complete", "complete"),
            process=("sa_system_recovery_l1", "complete_recovery"),
        ),
        _entry(
            "market_resumed",
            "2016-10-11T22:30:00+10:30",
            entry_kind="process_action",
            evidence="reported",
            source="aemo_final_report",
            action=_action("sa_market", "resume", "resumed"),
            process=("sa_system_recovery_l1", "resume_market"),
        ),
    ],
    "checkpoints": [
        {
            "id": "three_lines_lost_after_six_disturbances",
            "after": "davenport_mt_lock_trip",
            "all": [
                {"metric": "voltage_disturbance_count", "equals": 6},
                {"metric": "fault_window_seconds", "equals": 87},
            ],
        },
        {
            "id": "wind_reduction_456mw",
            "after": "wind_generation_reduced",
            "all": [{"metric": "sustained_wind_reduction_mw", "equals": 456}],
        },
        {
            "id": "black_system_after_separation",
            "after": "sa_black_system",
            "all": [
                {"object": "sa_power_system", "state": "black_system"},
                {"metric": "island_supply_demand_imbalance_mw", "equals": 1000},
            ],
        },
        {
            "id": "restoration_40_percent",
            "after": "load_restored_40_percent",
            "all": [{"metric": "restoration_percent", "equals": 40}],
        },
        {
            "id": "all_supply_and_market_restored",
            "after": "market_resumed",
            "all": [
                {"object": "customer_supply", "state": "restored_all"},
                {"object": "sa_power_system", "state": "stable_supply"},
                {"object": "sa_market", "state": "resumed"},
            ],
        },
    ],
    "expected_final": {
        "object_states": {
            "brinkworth_templers": "damaged_tripped",
            "davenport_belalie": "damaged_tripped",
            "davenport_mt_lock": "damaged_tripped",
            "wind_fleet": "sustained_reduction_456mw",
            "heywood_interconnector": "restart_supply",
            "sa_power_system": "stable_supply",
            "customer_supply": "restored_all",
            "recovery_coordination": "complete",
            "sa_market": "resumed",
        },
        "situations": [
            "three_transmission_lines_lost",
            "sustained_wind_generation_reduction",
            "south_australia_islanded",
            "black_system",
            "supply_restored_and_stable",
        ],
    },
}

_bind_event_model_objects(SOUTH_AUSTRALIA_2016)


HOKKAIDO_CASCADE_STEPS = [
    _step(
        "earthquake_occurs",
        "Record the Hokkaido Eastern Iburi earthquake",
        target="earthquake_hazard",
        capability="occur",
    ),
    _step(
        "trip_tomatoh_units_2_4",
        "Trip Tomatoh-Atsuma Units 2 and 4",
        after=["earthquake_occurs"],
        target="tomatoh_units_2_4",
        capability="trip",
    ),
    _step(
        "disconnect_eastern_routes",
        "Disconnect four eastern Hokkaido transmission routes",
        after=["earthquake_occurs"],
        target="eastern_transmission",
        capability="ground_fault_trip",
    ),
    _step(
        "trip_eastern_hydro",
        "Trip eastern Hokkaido hydro generation",
        after=["disconnect_eastern_routes"],
        target="eastern_hydro",
        capability="trip",
    ),
    _step(
        "trip_wind_generation",
        "Trip wind generation during the initial frequency event",
        after=["trip_tomatoh_units_2_4"],
        target="wind_generation",
        capability="trip",
    ),
    _step(
        "activate_emergency_hvdc",
        "Activate emergency Hokkaido–Honshu HVDC transfer",
        after=["trip_tomatoh_units_2_4"],
        target="hokkaido_honshu_hvdc",
        capability="emergency_transfer",
    ),
    _step(
        "first_load_shedding",
        "Shed approximately 1,300 MW at the first UFR stage",
        after=["trip_eastern_hydro", "trip_wind_generation"],
        target="customer_load",
        capability="shed_1300mw",
    ),
    _step(
        "recover_initial_frequency",
        "Recover frequency after emergency transfer and load shedding",
        after=["activate_emergency_hvdc", "first_load_shedding"],
        target="system_frequency",
        capability="recover_initial",
    ),
    _step(
        "reach_hvdc_limit",
        "Reach the maximum emergency HVDC transfer",
        after=["recover_initial_frequency"],
        target="hokkaido_honshu_hvdc",
        capability="reach_limit",
    ),
    _step(
        "reduce_tomatoh_unit_1",
        "Reduce Tomatoh-Atsuma Unit 1 output",
        after=["reach_hvdc_limit"],
        target="tomatoh_unit_1",
        capability="decrease_output",
    ),
    _step(
        "second_load_shedding",
        "Shed approximately 160 MW at the second UFR stage",
        after=["reduce_tomatoh_unit_1"],
        target="customer_load",
        capability="shed_160mw",
    ),
    _step(
        "trip_tomatoh_unit_1",
        "Trip Tomatoh-Atsuma Unit 1 after boiler damage",
        after=["second_load_shedding"],
        target="tomatoh_unit_1",
        capability="trip",
    ),
    _step(
        "third_load_shedding",
        "Shed the remaining approximately 60 MW at the third UFR stage",
        after=["trip_tomatoh_unit_1"],
        target="customer_load",
        capability="shed_60mw",
    ),
    _step(
        "trip_remaining_thermal",
        "Trip remaining major thermal generation on protection",
        after=["third_load_shedding"],
        target="remaining_thermal",
        capability="protection_trip",
    ),
    _step(
        "disconnect_hvdc",
        "Disconnect Hokkaido–Honshu HVDC on low frequency",
        after=["trip_remaining_thermal"],
        target="hokkaido_honshu_hvdc",
        capability="disconnect",
    ),
    _step(
        "enter_hokkaido_blackout",
        "Enter the Hokkaido-wide Black System",
        after=["disconnect_hvdc"],
        target="hokkaido_system",
        capability="blackout",
    ),
    _step(
        "collapse_frequency",
        "Record the final system-frequency collapse",
        after=["enter_hokkaido_blackout"],
        target="system_frequency",
        capability="collapse",
    ),
    _step(
        "disconnect_all_customers",
        "Record loss of supply to all Hokkaido customers",
        after=["collapse_frequency"],
        target="customer_load",
        capability="blackout",
    ),
]


HOKKAIDO_RECOVERY_STEPS = [
    _step(
        "start_first_black_start",
        "Parallel Takami Unit 1 for the first main-grid black start",
        target="black_start_sequence",
        capability="start_takami_1",
    ),
    _step(
        "fail_first_black_start",
        "Stop Takami Unit 1 after the first restoration attempt fails",
        after=["start_first_black_start"],
        target="black_start_sequence",
        capability="fail_first_attempt",
    ),
    _step(
        "start_second_black_start",
        "Parallel Niikappu Unit 1 for the second black start",
        after=["fail_first_black_start"],
        target="black_start_sequence",
        capability="start_niikappu_1",
    ),
    _step(
        "add_niikappu_2",
        "Parallel Niikappu Unit 2",
        after=["start_second_black_start"],
        target="black_start_sequence",
        capability="add_niikappu_2",
    ),
    _step(
        "begin_main_grid_restoration",
        "Begin customer-load restoration on the main grid",
        after=["add_niikappu_2"],
        target="customer_load",
        capability="begin_restoration",
    ),
    _step(
        "receive_hvdc_300mw",
        "Receive 300 MW through the Hokkaido–Honshu HVDC link",
        after=["begin_main_grid_restoration"],
        target="hokkaido_honshu_hvdc",
        capability="receive_300mw",
    ),
    _step(
        "receive_hvdc_600mw",
        "Increase Hokkaido–Honshu HVDC receipt to 600 MW",
        after=["receive_hvdc_300mw"],
        target="hokkaido_honshu_hvdc",
        capability="receive_600mw",
    ),
    _step(
        "restore_hakodate",
        "Complete customer-load restoration in Hakodate",
        after=["receive_hvdc_600mw"],
        target="customer_load",
        capability="restore_hakodate",
    ),
    _step(
        "restore_sapporo",
        "Complete customer-load restoration in Sapporo",
        after=["restore_hakodate"],
        target="customer_load",
        capability="restore_sapporo",
    ),
    _step(
        "restore_asahikawa",
        "Complete customer-load restoration in Asahikawa",
        after=["restore_sapporo"],
        target="customer_load",
        capability="restore_asahikawa",
    ),
    _step(
        "restore_tomakomai",
        "Complete customer-load restoration in Tomakomai",
        after=["restore_asahikawa"],
        target="customer_load",
        capability="restore_tomakomai",
    ),
    _step(
        "restore_kushiro",
        "Complete customer-load restoration in Kushiro",
        after=["restore_tomakomai"],
        target="customer_load",
        capability="restore_kushiro",
    ),
    _step(
        "restore_system_frequency",
        "Restore a stable nominal-frequency operating state",
        after=["restore_kushiro"],
        target="system_frequency",
        capability="restore_nominal",
    ),
    _step(
        "stabilize_hokkaido_system",
        "Confirm near-complete stable restoration",
        after=["restore_system_frequency"],
        target="hokkaido_system",
        capability="stabilize",
    ),
    _step(
        "complete_black_start_sequence",
        "Complete the coordinated black-start sequence",
        after=["stabilize_hokkaido_system"],
        target="black_start_sequence",
        capability="complete",
    ),
]


HOKKAIDO_2018 = {
    "schema_version": 2,
    "id": "hokkaido-blackout-2018-l1",
    "scenario_id": "hokkaido-2018",
    "name": "Hokkaido Blackout, 2018 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "occto_final_summary_en",
            "url": "https://www.occto.or.jp/iinkai/hokkaido_kensho/files/Final_report_hokkaido_blackout_summarized.pdf",
            "scope": "generation losses, frequency cascade, UFR stages and black-start restoration timeline",
            "priority": "final_primary_operator_report",
        },
        {
            "id": "occto_final_report_index",
            "url": "https://www.occto.or.jp/houkokusho/2018/hokkaidokensho_saishuhoukoku.html",
            "scope": "final-report provenance and supporting data",
            "priority": "official_index",
        },
        {
            "id": "meti_energy_whitepaper_2019",
            "url": "https://www.enecho.meti.go.jp/about/whitepaper/2019html/1-3-1.html",
            "scope": "earthquake time, regional blackout time and affected households",
            "priority": "official_government_summary",
        },
    ],
    "model": {
        "id": "qualification-hokkaido-2018",
        "name": "Hokkaido Blackout 2018 · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Generalized causal topology of generation loss, frequency collapse and black-start restoration from the OCCTO final report.",
        "event_targets": {
            "trip": "hk-tomatoh-2-4",
            "black_start": "hk-takami-1",
        },
        "nodes": [
            {"id": "hk-earthquake", "name": "Hokkaido Eastern Iburi earthquake", "component_type_id": "external-hazard", "x": 40, "y": 40, "qualification_object_id": "earthquake_hazard"},
            {"id": "hk-tomatoh-2-4", "name": "Tomatoh-Atsuma Units 2 and 4", "component_type_id": "thermal-plant", "x": 250, "y": 40, "capacity_mw": 1160, "qualification_object_id": "tomatoh_units_2_4"},
            {"id": "hk-tomatoh-1", "name": "Tomatoh-Atsuma Unit 1", "component_type_id": "thermal-plant", "x": 250, "y": 180, "capacity_mw": 338, "qualification_object_id": "tomatoh_unit_1"},
            {"id": "hk-eastern-hydro", "name": "Eastern Hokkaido hydro generation", "component_type_id": "hydro-plant", "x": 250, "y": 320, "capacity_mw": 430, "qualification_object_id": "eastern_hydro"},
            {"id": "hk-eastern-routes", "name": "Karikachi and eastern transmission routes", "component_type_id": "transmission-corridor", "x": 480, "y": 320, "qualification_object_id": "eastern_transmission"},
            {"id": "hk-wind", "name": "Hokkaido wind generation", "component_type_id": "wind-plant", "x": 250, "y": 460, "capacity_mw": 170, "parameters": {"availability": 1.0}, "qualification_object_id": "wind_generation"},
            {"id": "hk-remaining-thermal", "name": "Shiriuchi 1, Date 2 and Naie 1", "component_type_id": "thermal-plant", "x": 480, "y": 40, "capacity_mw": 923, "parameters": {"capacity_basis": "derived_pre_event_balance"}, "qualification_object_id": "remaining_thermal"},
            {"id": "hk-honshu-grid", "name": "Honshu power system", "component_type_id": "external-grid", "x": 40, "y": 600},
            {"id": "hk-honshu-hvdc", "name": "Hokkaido–Honshu HVDC link", "component_type_id": "hvdc-interconnector", "x": 480, "y": 600, "capacity_mw": 600, "parameters": {"capacity_mw": 72, "rated_capacity_mw": 600}, "qualification_object_id": "hokkaido_honshu_hvdc"},
            {"id": "hk-main-system", "name": "Hokkaido main power grid", "component_type_id": "grid-zone", "x": 750, "y": 250, "qualification_object_id": "hokkaido_system"},
            {"id": "hk-frequency", "name": "Hokkaido system frequency", "component_type_id": "system-state", "x": 750, "y": 40, "qualification_object_id": "system_frequency"},
            {"id": "hk-customers", "name": "Hokkaido customer load", "component_type_id": "customer-group", "x": 1010, "y": 250, "capacity_mw": 3087, "parameters": {"mode": "load", "demand_mw": 3087}, "qualification_object_id": "customer_load"},
            {"id": "hk-takami-1", "name": "Takami Unit 1 black-start hydro", "component_type_id": "hydro-plant", "x": 750, "y": 480, "initial_online": False},
            {"id": "hk-niikappu-1", "name": "Niikappu Unit 1 black-start hydro", "component_type_id": "hydro-plant", "x": 1010, "y": 480, "initial_online": False},
            {"id": "hk-niikappu-2", "name": "Niikappu Unit 2 black-start hydro", "component_type_id": "hydro-plant", "x": 1010, "y": 620, "initial_online": False},
            {"id": "hk-black-start", "name": "Hokkaido black-start sequence", "component_type_id": "response-process", "x": 1250, "y": 480, "qualification_object_id": "black_start_sequence"},
        ],
        "edges": [
            {"id": "hk-edge-tomatoh24-grid", "source": "hk-tomatoh-2-4", "target": "hk-main-system"},
            {"id": "hk-edge-tomatoh1-grid", "source": "hk-tomatoh-1", "target": "hk-main-system"},
            {"id": "hk-edge-remaining-grid", "source": "hk-remaining-thermal", "target": "hk-main-system"},
            {"id": "hk-edge-hydro-routes", "source": "hk-eastern-hydro", "target": "hk-eastern-routes"},
            {"id": "hk-edge-routes-grid", "source": "hk-eastern-routes", "target": "hk-main-system"},
            {"id": "hk-edge-wind-grid", "source": "hk-wind", "target": "hk-main-system"},
            {"id": "hk-edge-honshu-hvdc", "source": "hk-honshu-grid", "target": "hk-honshu-hvdc"},
            {"id": "hk-edge-hvdc-grid", "source": "hk-honshu-hvdc", "target": "hk-main-system"},
            {"id": "hk-edge-takami-grid", "source": "hk-takami-1", "target": "hk-main-system"},
            {"id": "hk-edge-niikappu1-grid", "source": "hk-niikappu-1", "target": "hk-main-system"},
            {"id": "hk-edge-niikappu2-grid", "source": "hk-niikappu-2", "target": "hk-main-system"},
            {"id": "hk-edge-grid-customers", "source": "hk-main-system", "target": "hk-customers"},
        ],
    },
    "objects": [
        _object(
            "earthquake_hazard",
            "Hokkaido Eastern Iburi earthquake",
            "external_hazard",
            "not_occurred",
            ["not_occurred", "occurred"],
            {"occur": _transitions(("not_occurred", "occurred"))},
        ),
        _object(
            "tomatoh_units_2_4",
            "Tomatoh-Atsuma Units 2 and 4",
            "generation_group",
            "generating_1154mw",
            ["generating_1154mw", "tripped_1160mw"],
            {"trip": _transitions(("generating_1154mw", "tripped_1160mw"))},
        ),
        _object(
            "tomatoh_unit_1",
            "Tomatoh-Atsuma Unit 1",
            "generator",
            "generating_338mw",
            ["generating_338mw", "decreasing_200mw", "tripped"],
            {
                "decrease_output": _transitions(
                    ("generating_338mw", "decreasing_200mw")
                ),
                "trip": _transitions(("decreasing_200mw", "tripped")),
            },
        ),
        _object(
            "eastern_transmission",
            "Karikachi and eastern Hokkaido transmission routes",
            "transmission_group",
            "connected",
            ["connected", "four_routes_tripped"],
            {
                "ground_fault_trip": _transitions(
                    ("connected", "four_routes_tripped")
                )
            },
        ),
        _object(
            "eastern_hydro",
            "Eastern Hokkaido hydro generation",
            "generation_group",
            "online_430mw",
            ["online_430mw", "tripped"],
            {"trip": _transitions(("online_430mw", "tripped"))},
        ),
        _object(
            "wind_generation",
            "Hokkaido wind generation affected by frequency",
            "generation_group",
            "online_170mw",
            ["online_170mw", "tripped"],
            {"trip": _transitions(("online_170mw", "tripped"))},
        ),
        _object(
            "hokkaido_honshu_hvdc",
            "Hokkaido–Honshu HVDC link",
            "interconnector",
            "receiving_72mw",
            [
                "receiving_72mw",
                "emergency_500mw",
                "maximum_transfer",
                "disconnected",
                "receiving_300mw",
                "receiving_600mw",
            ],
            {
                "emergency_transfer": _transitions(
                    ("receiving_72mw", "emergency_500mw")
                ),
                "reach_limit": _transitions(
                    ("emergency_500mw", "maximum_transfer")
                ),
                "disconnect": _transitions(("maximum_transfer", "disconnected")),
                "receive_300mw": _transitions(
                    ("disconnected", "receiving_300mw")
                ),
                "receive_600mw": _transitions(
                    ("receiving_300mw", "receiving_600mw")
                ),
            },
        ),
        _object(
            "system_frequency",
            "Hokkaido system frequency",
            "system_state",
            "nominal",
            [
                "nominal",
                "falling_initial",
                "initially_recovered",
                "collapsed",
                "restored_nominal",
            ],
            {
                "begin_initial_fall": _transitions(("nominal", "falling_initial")),
                "recover_initial": _transitions(
                    ("falling_initial", "initially_recovered")
                ),
                "collapse": _transitions(("initially_recovered", "collapsed")),
                "restore_nominal": _transitions(("collapsed", "restored_nominal")),
            },
        ),
        _object(
            "remaining_thermal",
            "Shiriuchi 1, Date 2 and Naie 1 thermal generation",
            "generation_group",
            "online",
            ["online", "protection_tripped"],
            {"protection_trip": _transitions(("online", "protection_tripped"))},
        ),
        _object(
            "customer_load",
            "Hokkaido customer load",
            "customer_group",
            "supplied_3087mw",
            [
                "supplied_3087mw",
                "shed_1300mw",
                "shed_1460mw",
                "shed_1520mw",
                "outage_2950000_households",
                "restoration_started",
                "hakodate_restored",
                "sapporo_restored",
                "asahikawa_restored",
                "tomakomai_restored",
                "nearly_all_restored",
            ],
            {
                "shed_1300mw": _transitions(
                    ("supplied_3087mw", "shed_1300mw")
                ),
                "shed_160mw": _transitions(("shed_1300mw", "shed_1460mw")),
                "shed_60mw": _transitions(("shed_1460mw", "shed_1520mw")),
                "blackout": _transitions(
                    ("shed_1520mw", "outage_2950000_households")
                ),
                "begin_restoration": _transitions(
                    ("outage_2950000_households", "restoration_started")
                ),
                "restore_hakodate": _transitions(
                    ("restoration_started", "hakodate_restored")
                ),
                "restore_sapporo": _transitions(
                    ("hakodate_restored", "sapporo_restored")
                ),
                "restore_asahikawa": _transitions(
                    ("sapporo_restored", "asahikawa_restored")
                ),
                "restore_tomakomai": _transitions(
                    ("asahikawa_restored", "tomakomai_restored")
                ),
                "restore_kushiro": _transitions(
                    ("tomakomai_restored", "nearly_all_restored")
                ),
            },
        ),
        _object(
            "hokkaido_system",
            "Hokkaido main power grid",
            "power_system",
            "operating",
            ["operating", "black_system", "stable_restoration"],
            {
                "blackout": _transitions(("operating", "black_system")),
                "stabilize": _transitions(
                    ("black_system", "stable_restoration")
                ),
            },
        ),
        _object(
            "black_start_sequence",
            "Hokkaido black-start sequence",
            "response_process",
            "standby",
            [
                "standby",
                "takami_1_online",
                "first_attempt_failed",
                "niikappu_1_online",
                "niikappu_2_online",
                "complete",
            ],
            {
                "start_takami_1": _transitions(("standby", "takami_1_online")),
                "fail_first_attempt": _transitions(
                    ("takami_1_online", "first_attempt_failed")
                ),
                "start_niikappu_1": _transitions(
                    ("first_attempt_failed", "niikappu_1_online")
                ),
                "add_niikappu_2": _transitions(
                    ("niikappu_1_online", "niikappu_2_online")
                ),
                "complete": _transitions(("niikappu_2_online", "complete")),
            },
        ),
    ],
    "situations": [
        {
            "id": "initial_generation_and_route_loss",
            "all": [{"metric": "initial_output_curtailed_mw", "at_least": 1760}],
        },
        {
            "id": "initial_frequency_recovery",
            "all": [
                {"object": "system_frequency", "state": "initially_recovered"}
            ],
        },
        {
            "id": "frequency_control_exhausted",
            "all": [
                {"object": "hokkaido_honshu_hvdc", "state": "maximum_transfer"},
                {"object": "tomatoh_unit_1", "state": "decreasing_200mw"},
            ],
        },
        {
            "id": "hokkaido_black_system",
            "all": [{"object": "hokkaido_system", "state": "black_system"}],
        },
        {
            "id": "near_complete_restoration",
            "all": [
                {"object": "customer_load", "state": "nearly_all_restored"},
                {"object": "hokkaido_system", "state": "stable_restoration"},
                {"object": "system_frequency", "state": "restored_nominal"},
            ],
        },
    ],
    "processes": [
        _process(
            "hokkaido_frequency_cascade_l1",
            "Hokkaido frequency cascade L1",
            HOKKAIDO_CASCADE_STEPS,
        ),
        _process(
            "hokkaido_black_start_recovery_l1",
            "Hokkaido black-start recovery L1",
            HOKKAIDO_RECOVERY_STEPS,
        ),
    ],
    "timeline": [
        _entry(
            "pre_event_supply",
            "2018-09-06T03:06:59+09:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="occto_final_summary_en",
            metrics={"demand_mw": 3087, "initial_hvdc_receipt_mw": 72},
        ),
        _entry(
            "earthquake",
            "2018-09-06T03:07:00+09:00",
            entry_kind="input",
            origin="external_event",
            evidence="reported",
            source="meti_energy_whitepaper_2019",
            action=_action("earthquake_hazard", "occur", "occurred"),
            process=("hokkaido_frequency_cascade_l1", "earthquake_occurs"),
            metrics={"earthquake_magnitude": 6.7, "maximum_seismic_intensity": 7},
        ),
        _entry(
            "tomatoh_units_2_4_trip",
            "2018-09-06T03:08:00+09:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action("tomatoh_units_2_4", "trip", "tripped_1160mw"),
            process=("hokkaido_frequency_cascade_l1", "trip_tomatoh_units_2_4"),
            metrics={"tomatoh_units_2_4_loss_mw": 1160},
        ),
        _entry(
            "initial_frequency_fall",
            "2018-09-06T03:08:00.100+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("system_frequency", "begin_initial_fall", "falling_initial"),
        ),
        _entry(
            "eastern_routes_trip",
            "2018-09-06T03:08:10+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action(
                "eastern_transmission", "ground_fault_trip", "four_routes_tripped"
            ),
            process=("hokkaido_frequency_cascade_l1", "disconnect_eastern_routes"),
        ),
        _entry(
            "eastern_hydro_trip",
            "2018-09-06T03:08:20+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("eastern_hydro", "trip", "tripped"),
            process=("hokkaido_frequency_cascade_l1", "trip_eastern_hydro"),
            metrics={"hydro_generation_loss_mw": 430},
        ),
        _entry(
            "wind_generation_trip",
            "2018-09-06T03:08:21+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("wind_generation", "trip", "tripped"),
            process=("hokkaido_frequency_cascade_l1", "trip_wind_generation"),
            metrics={"wind_generation_loss_mw": 170, "initial_output_curtailed_mw": 1760},
            situations=["initial_generation_and_route_loss"],
        ),
        _entry(
            "emergency_hvdc_transfer",
            "2018-09-06T03:08:30+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action(
                "hokkaido_honshu_hvdc", "emergency_transfer", "emergency_500mw"
            ),
            process=("hokkaido_frequency_cascade_l1", "activate_emergency_hvdc"),
            metrics={"emergency_hvdc_transfer_mw": 500, "hvdc_trigger_hz": 49.62},
        ),
        _entry(
            "first_ufr_load_shedding",
            "2018-09-06T03:08:40+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("customer_load", "shed_1300mw", "shed_1300mw"),
            process=("hokkaido_frequency_cascade_l1", "first_load_shedding"),
            metrics={"first_load_shedding_mw": 1300, "ufr_trigger_hz": 48.5},
        ),
        _entry(
            "initial_frequency_recovered",
            "2018-09-06T03:09:00+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action(
                "system_frequency", "recover_initial", "initially_recovered"
            ),
            process=("hokkaido_frequency_cascade_l1", "recover_initial_frequency"),
            situations=["initial_frequency_recovery"],
        ),
        _entry(
            "hvdc_maximum_transfer",
            "2018-09-06T03:19:00+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action(
                "hokkaido_honshu_hvdc", "reach_limit", "maximum_transfer"
            ),
            process=("hokkaido_frequency_cascade_l1", "reach_hvdc_limit"),
        ),
        _entry(
            "tomatoh_unit_1_output_decrease",
            "2018-09-06T03:20:00+09:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "tomatoh_unit_1", "decrease_output", "decreasing_200mw"
            ),
            process=("hokkaido_frequency_cascade_l1", "reduce_tomatoh_unit_1"),
            situations=["frequency_control_exhausted"],
            metrics={"tomatoh_unit_1_decrease_mw": 200},
        ),
        _entry(
            "second_ufr_load_shedding",
            "2018-09-06T03:22:00+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("customer_load", "shed_160mw", "shed_1460mw"),
            process=("hokkaido_frequency_cascade_l1", "second_load_shedding"),
            metrics={"second_load_shedding_mw": 160},
        ),
        _entry(
            "tomatoh_unit_1_trip",
            "2018-09-06T03:24:30+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("tomatoh_unit_1", "trip", "tripped"),
            process=("hokkaido_frequency_cascade_l1", "trip_tomatoh_unit_1"),
        ),
        _entry(
            "third_ufr_load_shedding",
            "2018-09-06T03:24:40+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("customer_load", "shed_60mw", "shed_1520mw"),
            process=("hokkaido_frequency_cascade_l1", "third_load_shedding"),
            metrics={"third_load_shedding_mw": 60},
        ),
        _entry(
            "remaining_thermal_trip",
            "2018-09-06T03:24:50+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action(
                "remaining_thermal", "protection_trip", "protection_tripped"
            ),
            process=("hokkaido_frequency_cascade_l1", "trip_remaining_thermal"),
        ),
        _entry(
            "hvdc_disconnected",
            "2018-09-06T03:24:55+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("hokkaido_honshu_hvdc", "disconnect", "disconnected"),
            process=("hokkaido_frequency_cascade_l1", "disconnect_hvdc"),
        ),
        _entry(
            "hokkaido_blackout",
            "2018-09-06T03:25:00+09:00",
            entry_kind="input",
            origin="observed_internal_fact",
            evidence="reported",
            source="meti_energy_whitepaper_2019",
            action=_action("hokkaido_system", "blackout", "black_system"),
            process=("hokkaido_frequency_cascade_l1", "enter_hokkaido_blackout"),
            situations=["hokkaido_black_system"],
            metrics={"affected_households": 2950000},
        ),
        _entry(
            "frequency_collapsed",
            "2018-09-06T03:25:00.001+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action("system_frequency", "collapse", "collapsed"),
            process=("hokkaido_frequency_cascade_l1", "collapse_frequency"),
        ),
        _entry(
            "all_customer_supply_lost",
            "2018-09-06T03:25:00.002+09:00",
            entry_kind="derived",
            evidence="derived",
            action=_action(
                "customer_load", "blackout", "outage_2950000_households"
            ),
            process=("hokkaido_frequency_cascade_l1", "disconnect_all_customers"),
        ),
        _entry(
            "first_black_start_takami_1",
            "2018-09-06T04:00:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "black_start_sequence", "start_takami_1", "takami_1_online"
            ),
            process=("hokkaido_black_start_recovery_l1", "start_first_black_start"),
        ),
        _entry(
            "first_black_start_failed",
            "2018-09-06T06:21:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "black_start_sequence", "fail_first_attempt", "first_attempt_failed"
            ),
            process=("hokkaido_black_start_recovery_l1", "fail_first_black_start"),
        ),
        _entry(
            "second_black_start_niikappu_1",
            "2018-09-06T06:30:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "black_start_sequence", "start_niikappu_1", "niikappu_1_online"
            ),
            process=("hokkaido_black_start_recovery_l1", "start_second_black_start"),
        ),
        _entry(
            "niikappu_2_parallel",
            "2018-09-06T06:37:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "black_start_sequence", "add_niikappu_2", "niikappu_2_online"
            ),
            process=("hokkaido_black_start_recovery_l1", "add_niikappu_2"),
        ),
        _entry(
            "main_grid_customer_restoration_started",
            "2018-09-06T11:43:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "customer_load", "begin_restoration", "restoration_started"
            ),
            process=("hokkaido_black_start_recovery_l1", "begin_main_grid_restoration"),
        ),
        _entry(
            "hvdc_receipt_300mw",
            "2018-09-07T05:30:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "hokkaido_honshu_hvdc", "receive_300mw", "receiving_300mw"
            ),
            process=("hokkaido_black_start_recovery_l1", "receive_hvdc_300mw"),
            metrics={"restoration_hvdc_receipt_mw": 300},
        ),
        _entry(
            "hvdc_receipt_600mw",
            "2018-09-07T21:00:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "hokkaido_honshu_hvdc", "receive_600mw", "receiving_600mw"
            ),
            process=("hokkaido_black_start_recovery_l1", "receive_hvdc_600mw"),
            metrics={"restoration_hvdc_receipt_mw": 600},
        ),
        _entry(
            "hakodate_restored",
            "2018-09-07T22:24:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action("customer_load", "restore_hakodate", "hakodate_restored"),
            process=("hokkaido_black_start_recovery_l1", "restore_hakodate"),
        ),
        _entry(
            "sapporo_restored",
            "2018-09-07T22:48:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action("customer_load", "restore_sapporo", "sapporo_restored"),
            process=("hokkaido_black_start_recovery_l1", "restore_sapporo"),
        ),
        _entry(
            "asahikawa_restored",
            "2018-09-07T23:17:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "customer_load", "restore_asahikawa", "asahikawa_restored"
            ),
            process=("hokkaido_black_start_recovery_l1", "restore_asahikawa"),
        ),
        _entry(
            "tomakomai_restored",
            "2018-09-08T00:10:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "customer_load", "restore_tomakomai", "tomakomai_restored"
            ),
            process=("hokkaido_black_start_recovery_l1", "restore_tomakomai"),
        ),
        _entry(
            "kushiro_restored",
            "2018-09-08T00:13:00+09:00",
            entry_kind="process_action",
            evidence="reported",
            source="occto_final_summary_en",
            action=_action(
                "customer_load", "restore_kushiro", "nearly_all_restored"
            ),
            process=("hokkaido_black_start_recovery_l1", "restore_kushiro"),
            metrics={"restoration_elapsed_hours": 44.8, "restoration_percent": 99},
        ),
        _entry(
            "frequency_restored_nominal",
            "2018-09-08T00:13:00.500+09:00",
            entry_kind="process_action",
            evidence="derived",
            action=_action(
                "system_frequency", "restore_nominal", "restored_nominal"
            ),
            process=(
                "hokkaido_black_start_recovery_l1",
                "restore_system_frequency",
            ),
        ),
        _entry(
            "hokkaido_stable_restoration",
            "2018-09-08T00:13:01+09:00",
            entry_kind="process_action",
            evidence="derived",
            action=_action(
                "hokkaido_system", "stabilize", "stable_restoration"
            ),
            process=("hokkaido_black_start_recovery_l1", "stabilize_hokkaido_system"),
            situations=["near_complete_restoration"],
        ),
        _entry(
            "black_start_sequence_complete",
            "2018-09-08T00:13:02+09:00",
            entry_kind="process_action",
            evidence="derived",
            action=_action("black_start_sequence", "complete", "complete"),
            process=(
                "hokkaido_black_start_recovery_l1",
                "complete_black_start_sequence",
            ),
        ),
    ],
    "checkpoints": [
        {
            "id": "initial_loss_1760mw",
            "after": "wind_generation_trip",
            "all": [{"metric": "initial_output_curtailed_mw", "equals": 1760}],
        },
        {
            "id": "first_ufr_1300mw",
            "after": "initial_frequency_recovered",
            "all": [
                {"metric": "first_load_shedding_mw", "equals": 1300},
                {"object": "system_frequency", "state": "initially_recovered"},
            ],
        },
        {
            "id": "three_ufr_stages_exhausted",
            "after": "third_ufr_load_shedding",
            "all": [
                {"metric": "second_load_shedding_mw", "equals": 160},
                {"metric": "third_load_shedding_mw", "equals": 60},
            ],
        },
        {
            "id": "blackout_2950000_households",
            "after": "all_customer_supply_lost",
            "all": [
                {"object": "hokkaido_system", "state": "black_system"},
                {"metric": "affected_households", "equals": 2950000},
            ],
        },
        {
            "id": "near_complete_restoration_45h",
            "after": "black_start_sequence_complete",
            "all": [
                {"object": "customer_load", "state": "nearly_all_restored"},
                {"metric": "restoration_percent", "equals": 99},
                {"metric": "restoration_elapsed_hours", "at_least": 44.8},
            ],
        },
    ],
    "expected_final": {
        "object_states": {
            "earthquake_hazard": "occurred",
            "tomatoh_units_2_4": "tripped_1160mw",
            "tomatoh_unit_1": "tripped",
            "eastern_transmission": "four_routes_tripped",
            "eastern_hydro": "tripped",
            "wind_generation": "tripped",
            "hokkaido_honshu_hvdc": "receiving_600mw",
            "system_frequency": "restored_nominal",
            "remaining_thermal": "protection_tripped",
            "customer_load": "nearly_all_restored",
            "hokkaido_system": "stable_restoration",
            "black_start_sequence": "complete",
        },
        "situations": [
            "initial_generation_and_route_loss",
            "initial_frequency_recovery",
            "frequency_control_exhausted",
            "hokkaido_black_system",
            "near_complete_restoration",
        ],
    },
}


_bind_event_model_objects(HOKKAIDO_2018)


INDIA_DAY1_CASCADE_STEPS = [
    _step("record_day1_stress", "Record the stressed 30 July transfer condition"),
    _step("record_day1_corridor_depletion", "Record progressive West-to-North corridor depletion", after=["record_day1_stress"]),
    _step("trip_day1_bina_gwalior", "Trip 400 kV Bina-Gwalior-1 on Zone-3 load encroachment", after=["record_day1_corridor_depletion"], target="west_north_corridor", capability="trip_day1"),
    _step("separate_day1_north", "Separate Northern Region from the remaining NEW grid", after=["trip_day1_bina_gwalior"], target="new_grid", capability="separate_north"),
    _step("fall_day1_frequency", "Allow Northern Region frequency to fall below 47.5 Hz", after=["separate_day1_north"], target="system_frequency", capability="fall_day1"),
    _step("fail_day1_ufr", "Record inadequate UFR and df/dt relief", after=["fall_day1_frequency"], target="ufr_protection", capability="fail_day1"),
    _step("collapse_day1_north", "Collapse nearly the entire Northern Region", after=["fail_day1_ufr"], target="northern_region", capability="collapse_day1"),
    _step("interrupt_day1_load", "Interrupt Northern Region customer load", after=["collapse_day1_north"], target="customer_load", capability="interrupt_day1"),
    _step("retain_day1_pockets", "Retain documented surviving generation-load pockets", after=["interrupt_day1_load"], target="surviving_islands", capability="form_day1"),
]

INDIA_DAY1_RECOVERY_STEPS = [
    _step("start_day1_recovery", "Start 30 July restoration from neighboring grids and hydro", target="restoration", capability="start_day1"),
    _step("restore_day1_emergency", "Restore most railway, metro and airport supply", after=["start_day1_recovery"], target="customer_load", capability="restore_day1_emergency"),
    _step("restore_day1_15000mw", "Restore more than 15,000 MW of antecedent load", after=["restore_day1_emergency"], target="customer_load", capability="restore_day1_partial"),
    _step("restore_day1_north", "Fully restore the Northern Regional system", after=["restore_day1_15000mw"], target="northern_region", capability="restore_day1"),
    _step("restore_day1_load", "Restore Northern Region customer load", after=["restore_day1_north"], target="customer_load", capability="restore_day1_full"),
    _step("restore_day1_corridor", "Restore a West-to-North supply path", after=["restore_day1_load"], target="west_north_corridor", capability="restore_day1"),
    _step("restore_day1_new_grid", "Restore the interconnected NEW grid", after=["restore_day1_corridor"], target="new_grid", capability="restore_day1"),
    _step("stabilize_day1_frequency", "Stabilize frequency after the first restoration", after=["restore_day1_new_grid"], target="system_frequency", capability="stabilize_day1"),
    _step("reintegrate_day1_pockets", "Reintegrate surviving pockets", after=["stabilize_day1_frequency"], target="surviving_islands", capability="reintegrate_day1"),
    _step("complete_day1_recovery", "Complete the 30 July restoration process", after=["reintegrate_day1_pockets"], target="restoration", capability="complete_day1"),
    _step("close_day1_balance", "Record the first-day restored state", after=["complete_day1_recovery"], target="india_grid_balance", capability="restore_day1"),
]

INDIA_DAY2_CASCADE_STEPS = [
    _step("enter_day2_stress", "Enter the stressed 31 July operating state", target="india_grid_balance", capability="stress_day2"),
    _step("set_day2_frequency", "Record pre-disturbance frequency of 49.84 Hz", after=["enter_day2_stress"], target="system_frequency", capability="set_day2"),
    _step("set_day2_demand", "Record approximately 73,000 MW NEW-grid demand", after=["set_day2_frequency"], target="customer_load", capability="set_day2"),
    _step("deplete_day2_corridor", "Record renewed West-to-North corridor depletion", after=["set_day2_demand"], target="west_north_corridor", capability="deplete_day2"),
    _step("reset_day2_ufr", "Return load-shedding protection to service", after=["deplete_day2_corridor"], target="ufr_protection", capability="reset_day2"),
    _step("trip_suratgarh", "Trip Suratgarh Unit 1 and increase interregional transfers", after=["reset_day2_ufr"]),
    _step("trip_day2_bina_gwalior", "Trip 400 kV Bina-Gwalior-1 on Zone-3 protection", after=["trip_suratgarh"], target="west_north_corridor", capability="trip_day2"),
    _step("separate_day2_regions", "Separate Northern, Eastern and North-Eastern regions", after=["trip_day2_bina_gwalior"], target="new_grid", capability="separate_day2"),
    _step("plateau_day2_frequency", "Reach the temporary 48.12 Hz frequency plateau", after=["separate_day2_regions"], target="system_frequency", capability="plateau_day2"),
    _step("fail_day2_ufr", "Record inadequate three-stage UFR and df/dt relief", after=["plateau_day2_frequency"], target="ufr_protection", capability="fail_day2"),
    _step("collapse_day2_regions", "Collapse the separated multi-region system", after=["fail_day2_ufr"], target="new_grid", capability="collapse_day2"),
    _step("collapse_day2_north", "Record Northern Region blackout within the multi-region collapse", after=["collapse_day2_regions"], target="northern_region", capability="collapse_day2"),
    _step("collapse_day2_frequency", "Record final frequency collapse", after=["collapse_day2_north"], target="system_frequency", capability="collapse_day2"),
    _step("interrupt_day2_load", "Interrupt approximately 48,000 MW across 21 states and one union territory", after=["collapse_day2_frequency"], target="customer_load", capability="interrupt_day2"),
    _step("retain_day2_islands", "Retain documented surviving regional islands and generating units", after=["interrupt_day2_load"], target="surviving_islands", capability="form_day2"),
]

INDIA_DAY2_RECOVERY_STEPS = [
    _step("start_day2_recovery", "Start 31 July restoration from Western and Southern regions", target="restoration", capability="start_day2"),
    _step("restore_day2_emergency", "Restore most railway, metro, mine and airport loads", after=["start_day2_recovery"], target="customer_load", capability="restore_day2_emergency"),
    _step("restore_day2_corridor", "Restore interregional supply paths", after=["restore_day2_emergency"], target="west_north_corridor", capability="restore_final"),
    _step("restore_day2_load", "Fully restore affected customer load", after=["restore_day2_corridor"], target="customer_load", capability="restore_day2_full"),
    _step("restore_day2_grid", "Fully restore the NEW grid", after=["restore_day2_load"], target="new_grid", capability="restore_final"),
    _step("restore_day2_north", "Return Northern Region to stable service", after=["restore_day2_grid"], target="northern_region", capability="restore_day2"),
    _step("restore_day2_frequency", "Restore nominal system frequency", after=["restore_day2_north"], target="system_frequency", capability="restore_nominal"),
    _step("reintegrate_day2_islands", "Reintegrate surviving islands", after=["restore_day2_frequency"], target="surviving_islands", capability="reintegrate_day2"),
    _step("mark_ufr_review", "Mark UFR and df/dt performance for corrective review", after=["reintegrate_day2_islands"], target="ufr_protection", capability="require_review"),
    _step("resolve_grid_balance", "Resolve the two-day stressed balance condition", after=["mark_ufr_review"], target="india_grid_balance", capability="resolve"),
    _step("complete_day2_recovery", "Complete the 31 July restoration process", after=["resolve_grid_balance"], target="restoration", capability="complete_day2"),
]

INDIA_2012 = {
    "schema_version": 2,
    "id": "india-grid-disturbances-2012-l1",
    "scenario_id": "india-2012",
    "name": "India Grid Disturbances, 30–31 July 2012 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "india_inquiry_final_report",
            "url": "http://www.cercind.gov.in/2012/orders/Final_Report_Grid_Disturbance.pdf",
            "scope": "official inquiry sequence, relay operations, frequency behavior, load impact and restoration milestones for both days",
            "priority": "final_primary_government_inquiry",
        },
        {
            "id": "cerc_archive_2013",
            "url": "https://cercind.gov.in/Archive13.html",
            "scope": "official report publication provenance",
            "priority": "official_regulator_index",
        },
    ],
    "model": {
        "id": "qualification-india-2012",
        "name": "India grid disturbances 30–31 July 2012 · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Interregional causal topology from the official inquiry report. It represents the NEW-grid separation and restoration boundary, not a geographic one-line diagram.",
        "event_targets": {"overload": "in-west-north-corridor", "line_fault": "in-west-north-corridor"},
        "nodes": [
            {"id": "in-grid-balance", "name": "Interregional load–generation balance", "component_type_id": "system-state", "x": 40, "y": 40, "qualification_object_id": "india_grid_balance"},
            {"id": "in-western-region", "name": "Western Regional power system", "component_type_id": "external-grid", "x": 40, "y": 260},
            {"id": "in-west-north-corridor", "name": "Western-to-Northern transfer corridor including Bina–Gwalior", "component_type_id": "transmission-corridor", "x": 260, "y": 260, "parameters": {"day1_bina_gwalior_flow_mva": 1450, "day2_bina_gwalior_flow_mw": 923}, "qualification_object_id": "west_north_corridor"},
            {"id": "in-suratgarh-1", "name": "Suratgarh thermal generating Unit 1", "component_type_id": "thermal-plant", "x": 260, "y": 460, "parameters": {"fuel_kind": "thermal_fuel", "capacity_evidence": "not_modelled"}},
            {"id": "in-northern-hydro", "name": "Northern hydro generation used for restoration", "component_type_id": "hydro-plant", "x": 480, "y": 460, "parameters": {"capacity_evidence": "not_modelled"}},
            {"id": "in-eastern-region", "name": "Eastern Regional power system", "component_type_id": "grid-zone", "x": 480, "y": 40},
            {"id": "in-northeastern-region", "name": "North-Eastern Regional power system", "component_type_id": "grid-zone", "x": 700, "y": 40},
            {"id": "in-new-grid", "name": "Northern–Western–Eastern–North-Eastern grid", "component_type_id": "grid-zone", "x": 700, "y": 260, "qualification_object_id": "new_grid"},
            {"id": "in-northern-region", "name": "Northern Regional power system", "component_type_id": "grid-zone", "x": 920, "y": 260, "qualification_object_id": "northern_region"},
            {"id": "in-customer-load", "name": "Affected customer and essential load", "component_type_id": "customer-group", "x": 1140, "y": 260, "parameters": {"mode": "load", "demand_mw": 73000, "day1_antecedent_load_mw": 38000, "day2_affected_load_mw": 48000}, "qualification_object_id": "customer_load"},
            {"id": "in-system-frequency", "name": "Affected regional system frequency", "component_type_id": "system-state", "x": 920, "y": 40, "qualification_object_id": "system_frequency"},
            {"id": "in-ufr-protection", "name": "UFR and df/dt load-shedding protection", "component_type_id": "protection-system", "x": 1140, "y": 40, "qualification_object_id": "ufr_protection"},
            {"id": "in-surviving-islands", "name": "Surviving generation–load islands", "component_type_id": "grid-zone", "x": 920, "y": 460, "qualification_object_id": "surviving_islands"},
            {"id": "in-restoration", "name": "Two-day grid restoration coordination", "component_type_id": "response-process", "x": 1140, "y": 460, "qualification_object_id": "restoration"},
        ],
        "edges": [
            {"id": "in-edge-west-corridor", "source": "in-western-region", "target": "in-west-north-corridor"},
            {"id": "in-edge-corridor-new", "source": "in-west-north-corridor", "target": "in-new-grid"},
            {"id": "in-edge-east-new", "source": "in-eastern-region", "target": "in-new-grid"},
            {"id": "in-edge-northeast-new", "source": "in-northeastern-region", "target": "in-new-grid"},
            {"id": "in-edge-new-north", "source": "in-new-grid", "target": "in-northern-region"},
            {"id": "in-edge-suratgarh-north", "source": "in-suratgarh-1", "target": "in-northern-region"},
            {"id": "in-edge-hydro-north", "source": "in-northern-hydro", "target": "in-northern-region"},
            {"id": "in-edge-north-load", "source": "in-northern-region", "target": "in-customer-load"},
            {"id": "in-edge-north-islands", "source": "in-northern-region", "target": "in-surviving-islands"},
        ],
    },
    "objects": [
        _object("india_grid_balance", "India interregional load-generation balance", "system_condition", "stressed_jul30", ["stressed_jul30", "restored_day1", "stressed_jul31", "resolved"], {"restore_day1": _transitions(("stressed_jul30", "restored_day1")), "stress_day2": _transitions(("restored_day1", "stressed_jul31")), "resolve": _transitions(("stressed_jul31", "resolved"))}),
        _object("west_north_corridor", "Western-to-Northern transmission corridor", "transmission_corridor", "depleted_jul30", ["depleted_jul30", "bina_gwalior_tripped_day1", "restored_day1", "depleted_jul31", "bina_gwalior_tripped_day2", "restored_final"], {"trip_day1": _transitions(("depleted_jul30", "bina_gwalior_tripped_day1")), "restore_day1": _transitions(("bina_gwalior_tripped_day1", "restored_day1")), "deplete_day2": _transitions(("restored_day1", "depleted_jul31")), "trip_day2": _transitions(("depleted_jul31", "bina_gwalior_tripped_day2")), "restore_final": _transitions(("bina_gwalior_tripped_day2", "restored_final"))}),
        _object("northern_region", "Northern Regional power system", "power_system", "interconnected", ["interconnected", "blackout_day1", "restored_day1", "blackout_day2", "restored_day2"], {"collapse_day1": _transitions(("interconnected", "blackout_day1")), "restore_day1": _transitions(("blackout_day1", "restored_day1")), "collapse_day2": _transitions(("restored_day1", "blackout_day2")), "restore_day2": _transitions(("blackout_day2", "restored_day2"))}),
        _object("new_grid", "Northern-Western-Eastern-North-Eastern grid", "power_system", "interconnected", ["interconnected", "north_separated_day1", "restored_after_day1", "regions_separated_day2", "collapsed_day2", "restored_final"], {"separate_north": _transitions(("interconnected", "north_separated_day1")), "restore_day1": _transitions(("north_separated_day1", "restored_after_day1")), "separate_day2": _transitions(("restored_after_day1", "regions_separated_day2")), "collapse_day2": _transitions(("regions_separated_day2", "collapsed_day2")), "restore_final": _transitions(("collapsed_day2", "restored_final"))}),
        _object("system_frequency", "Affected regional system frequency", "system_state", "nr_49_68hz", ["nr_49_68hz", "nr_below_47_5hz", "stable_after_day1", "new_49_84hz", "plateau_48_12hz", "collapsed_day2", "nominal"], {"fall_day1": _transitions(("nr_49_68hz", "nr_below_47_5hz")), "stabilize_day1": _transitions(("nr_below_47_5hz", "stable_after_day1")), "set_day2": _transitions(("stable_after_day1", "new_49_84hz")), "plateau_day2": _transitions(("new_49_84hz", "plateau_48_12hz")), "collapse_day2": _transitions(("plateau_48_12hz", "collapsed_day2")), "restore_nominal": _transitions(("collapsed_day2", "nominal"))}),
        _object("ufr_protection", "UFR and df/dt load-shedding protection", "protection_system", "armed_day1", ["armed_day1", "inadequate_day1", "armed_day2", "inadequate_day2", "review_required"], {"fail_day1": _transitions(("armed_day1", "inadequate_day1")), "reset_day2": _transitions(("inadequate_day1", "armed_day2")), "fail_day2": _transitions(("armed_day2", "inadequate_day2")), "require_review": _transitions(("inadequate_day2", "review_required"))}),
        _object("customer_load", "Affected customer and essential load", "customer_group", "nr_38000mw_supplied", ["nr_38000mw_supplied", "nr_blackout_day1", "day1_emergency_restored", "day1_15000mw_restored", "day1_fully_restored", "new_73000mw_supplied", "outage_48000mw_day2", "day2_emergency_restored", "fully_restored"], {"interrupt_day1": _transitions(("nr_38000mw_supplied", "nr_blackout_day1")), "restore_day1_emergency": _transitions(("nr_blackout_day1", "day1_emergency_restored")), "restore_day1_partial": _transitions(("day1_emergency_restored", "day1_15000mw_restored")), "restore_day1_full": _transitions(("day1_15000mw_restored", "day1_fully_restored")), "set_day2": _transitions(("day1_fully_restored", "new_73000mw_supplied")), "interrupt_day2": _transitions(("new_73000mw_supplied", "outage_48000mw_day2")), "restore_day2_emergency": _transitions(("outage_48000mw_day2", "day2_emergency_restored")), "restore_day2_full": _transitions(("day2_emergency_restored", "fully_restored"))}),
        _object("surviving_islands", "Surviving generation-load islands", "island_group", "none", ["none", "day1_pockets", "reintegrated_day1", "day2_pockets", "reintegrated_final"], {"form_day1": _transitions(("none", "day1_pockets")), "reintegrate_day1": _transitions(("day1_pockets", "reintegrated_day1")), "form_day2": _transitions(("reintegrated_day1", "day2_pockets")), "reintegrate_day2": _transitions(("day2_pockets", "reintegrated_final"))}),
        _object("restoration", "Two-day grid restoration coordination", "response_process", "standby", ["standby", "day1_active", "day1_complete", "day2_active", "day2_complete"], {"start_day1": _transitions(("standby", "day1_active")), "complete_day1": _transitions(("day1_active", "day1_complete")), "start_day2": _transitions(("day1_complete", "day2_active")), "complete_day2": _transitions(("day2_active", "day2_complete"))}),
    ],
    "situations": [
        {"id": "day1_corridor_failure", "all": [{"object": "west_north_corridor", "state": "bina_gwalior_tripped_day1"}]},
        {"id": "day1_northern_blackout", "all": [{"object": "northern_region", "state": "blackout_day1"}, {"object": "ufr_protection", "state": "inadequate_day1"}]},
        {"id": "day1_full_restoration", "all": [{"object": "customer_load", "state": "day1_fully_restored"}, {"object": "northern_region", "state": "restored_day1"}]},
        {"id": "day2_multi_region_blackout", "all": [{"object": "new_grid", "state": "collapsed_day2"}, {"object": "customer_load", "state": "outage_48000mw_day2"}]},
        {"id": "two_day_stable_restoration", "all": [{"object": "new_grid", "state": "restored_final"}, {"object": "customer_load", "state": "fully_restored"}, {"object": "restoration", "state": "day2_complete"}]},
    ],
    "processes": [
        _process("india_day1_cascade_l1", "India 30 July cascade L1", INDIA_DAY1_CASCADE_STEPS),
        _process("india_day1_recovery_l1", "India 30 July recovery L1", INDIA_DAY1_RECOVERY_STEPS),
        _process("india_day2_cascade_l1", "India 31 July cascade L1", INDIA_DAY2_CASCADE_STEPS),
        _process("india_day2_recovery_l1", "India 31 July recovery L1", INDIA_DAY2_RECOVERY_STEPS),
    ],
    "timeline": [
        _entry("day1_stressed_dispatch", "2012-07-29T21:10:00+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Heavy Northern demand, Western surplus and depleted transfer network stressed the NEW grid", process=("india_day1_cascade_l1", "record_day1_stress"), metrics={"day1_nr_unscheduled_import_mw": 2000, "day1_wr_unscheduled_export_mw": 3000, "day1_pre_frequency_hz": 49.68}),
        _entry("day1_corridor_depleted", "2012-07-30T01:35:00+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Planned and forced outages progressively depleted the West-to-North corridor", process=("india_day1_cascade_l1", "record_day1_corridor_depletion"), metrics={"bina_gwalior_flow_mva": 1450, "frozen_operator_display_mw": 1000}),
        _entry("day1_bina_gwalior_trip", "2012-07-30T02:33:11.976+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="400 kV Bina-Gwalior-1 tripped on Zone-3 protection during load encroachment", action=_action("west_north_corridor", "trip_day1", "bina_gwalior_tripped_day1"), process=("india_day1_cascade_l1", "trip_day1_bina_gwalior"), situations=["day1_corridor_failure"]),
        _entry("day1_north_separated", "2012-07-30T02:33:15.576+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="East-to-North ties tripped and Northern Region separated from the remaining NEW grid", action=_action("new_grid", "separate_north", "north_separated_day1"), process=("india_day1_cascade_l1", "separate_day1_north")),
        _entry("day1_frequency_below_47_5", "2012-07-30T02:33:22+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Within 6.5 seconds Northern Region frequency fell below 47.5 Hz", action=_action("system_frequency", "fall_day1", "nr_below_47_5hz"), process=("india_day1_cascade_l1", "fall_day1_frequency"), metrics={"day1_frequency_hz_below": 47.5, "day1_frequency_fall_seconds": 6.5}),
        _entry("day1_ufr_inadequate", "2012-07-30T02:33:22.001+05:30", entry_kind="derived", evidence="derived", fact="Available UFR and df/dt shedding did not arrest the decline", action=_action("ufr_protection", "fail_day1", "inadequate_day1"), process=("india_day1_cascade_l1", "fail_day1_ufr"), metrics={"planned_ufr_relief_mw": 10000}),
        _entry("day1_northern_collapse", "2012-07-30T02:33:23+05:30", entry_kind="derived", evidence="derived", fact="Nearly the entire Northern Region collapsed", action=_action("northern_region", "collapse_day1", "blackout_day1"), process=("india_day1_cascade_l1", "collapse_day1_north")),
        _entry("day1_load_interrupted", "2012-07-30T02:33:23.001+05:30", entry_kind="derived", evidence="derived", fact="The system had been serving about 38,000 MW immediately before the near-region-wide blackout", action=_action("customer_load", "interrupt_day1", "nr_blackout_day1"), process=("india_day1_cascade_l1", "interrupt_day1_load"), situations=["day1_northern_blackout"], metrics={"day1_antecedent_nr_demand_mw": 38000}),
        _entry("day1_surviving_pockets", "2012-07-30T02:33:24+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Small pockets at Badarpur, Narora, Bhinmal, Sahupuri and Gwalior survived", action=_action("surviving_islands", "form_day1", "day1_pockets"), process=("india_day1_cascade_l1", "retain_day1_pockets"), metrics={"badarpur_surviving_load_mw": 250, "bhinmal_surviving_load_mw": 100}),
        _entry("day1_recovery_started", "2012-07-30T02:33:25+05:30", entry_kind="input", origin="planned_process_start", evidence="reported", source="india_inquiry_final_report", fact="Restoration began using Eastern and Western grid supply plus self-started hydro units", action=_action("restoration", "start_day1", "day1_active"), process=("india_day1_recovery_l1", "start_day1_recovery")),
        _entry("day1_emergency_loads_restored", "2012-07-30T08:00:00+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Most railway, metro and airport emergency loads had supply", action=_action("customer_load", "restore_day1_emergency", "day1_emergency_restored"), process=("india_day1_recovery_l1", "restore_day1_emergency")),
        _entry("day1_15000mw_restored", "2012-07-30T10:00:00+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="More than 15,000 MW, about 40% of antecedent load, had been restored", action=_action("customer_load", "restore_day1_partial", "day1_15000mw_restored"), process=("india_day1_recovery_l1", "restore_day1_15000mw"), metrics={"day1_restored_load_mw": 15000, "day1_restored_percent": 40}),
        _entry("day1_north_restored", "2012-07-30T16:00:00+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Northern Regional system was fully restored", action=_action("northern_region", "restore_day1", "restored_day1"), process=("india_day1_recovery_l1", "restore_day1_north")),
        _entry("day1_load_fully_restored", "2012-07-30T16:00:00.001+05:30", entry_kind="derived", evidence="derived", fact="First-day load-restoration boundary reached", action=_action("customer_load", "restore_day1_full", "day1_fully_restored"), process=("india_day1_recovery_l1", "restore_day1_load"), situations=["day1_full_restoration"], metrics={"day1_full_restoration_time": "16:00"}),
        _entry("day1_corridor_restored", "2012-07-30T16:00:00.002+05:30", entry_kind="derived", evidence="derived", fact="A stable West-to-North supply path was available", action=_action("west_north_corridor", "restore_day1", "restored_day1"), process=("india_day1_recovery_l1", "restore_day1_corridor")),
        _entry("day1_new_grid_restored", "2012-07-30T16:00:00.003+05:30", entry_kind="derived", evidence="derived", fact="The NEW grid was again interconnected", action=_action("new_grid", "restore_day1", "restored_after_day1"), process=("india_day1_recovery_l1", "restore_day1_new_grid")),
        _entry("day1_frequency_stable", "2012-07-30T16:00:00.004+05:30", entry_kind="derived", evidence="derived", fact="Frequency was stable after restoration", action=_action("system_frequency", "stabilize_day1", "stable_after_day1"), process=("india_day1_recovery_l1", "stabilize_day1_frequency")),
        _entry("day1_pockets_reintegrated", "2012-07-30T16:00:00.005+05:30", entry_kind="derived", evidence="derived", fact="Surviving pockets were reintegrated", action=_action("surviving_islands", "reintegrate_day1", "reintegrated_day1"), process=("india_day1_recovery_l1", "reintegrate_day1_pockets")),
        _entry("day1_recovery_complete", "2012-07-30T16:00:00.006+05:30", entry_kind="derived", evidence="derived", fact="30 July restoration process completed", action=_action("restoration", "complete_day1", "day1_complete"), process=("india_day1_recovery_l1", "complete_day1_recovery")),
        _entry("day1_balance_closed", "2012-07-30T16:00:00.007+05:30", entry_kind="derived", evidence="derived", fact="First disturbance entered its restored state", action=_action("india_grid_balance", "restore_day1", "restored_day1"), process=("india_day1_recovery_l1", "close_day1_balance")),
        _entry("day2_stressed_dispatch", "2012-07-31T12:45:00+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Northern overdrawal and Western underdrawal again stressed depleted corridors", action=_action("india_grid_balance", "stress_day2", "stressed_jul31"), process=("india_day2_cascade_l1", "enter_day2_stress"), metrics={"day2_nr_unscheduled_import_mw": 2500, "day2_wr_unscheduled_export_mw": 3000}),
        _entry("day2_pre_frequency", "2012-07-31T12:45:00.001+05:30", entry_kind="derived", evidence="derived", fact="Pre-disturbance frequency was 49.84 Hz", action=_action("system_frequency", "set_day2", "new_49_84hz"), process=("india_day2_cascade_l1", "set_day2_frequency"), metrics={"day2_pre_frequency_hz": 49.84}),
        _entry("day2_pre_demand", "2012-07-31T12:45:00.002+05:30", entry_kind="derived", evidence="derived", fact="The NEW grid was serving approximately 73,000 MW", action=_action("customer_load", "set_day2", "new_73000mw_supplied"), process=("india_day2_cascade_l1", "set_day2_demand"), metrics={"day2_new_grid_demand_mw": 73000, "day2_all_india_demand_mw": 100500}),
        _entry("day2_corridor_depleted", "2012-07-31T12:45:00.003+05:30", entry_kind="derived", evidence="derived", fact="The West-to-North corridor again operated with planned and forced outages", action=_action("west_north_corridor", "deplete_day2", "depleted_jul31"), process=("india_day2_cascade_l1", "deplete_day2_corridor")),
        _entry("day2_ufr_armed", "2012-07-31T12:45:00.004+05:30", entry_kind="derived", evidence="derived", fact="UFR and df/dt schemes were expected to protect the separated system", action=_action("ufr_protection", "reset_day2", "armed_day2"), process=("india_day2_cascade_l1", "reset_day2_ufr")),
        _entry("suratgarh_unit1_trip", "2012-07-31T12:50:00+05:30", entry_kind="input", origin="external_event", evidence="reported", source="india_inquiry_final_report", fact="Suratgarh Unit 1 tripped, increasing interregional transfers", process=("india_day2_cascade_l1", "trip_suratgarh")),
        _entry("day2_bina_gwalior_trip", "2012-07-31T13:00:13.045+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="400 kV Bina-Gwalior-1 tripped on Main-2 Zone-3 protection", action=_action("west_north_corridor", "trip_day2", "bina_gwalior_tripped_day2"), process=("india_day2_cascade_l1", "trip_day2_bina_gwalior"), metrics={"day2_bina_gwalior_flow_mw": 923}),
        _entry("day2_regions_separated", "2012-07-31T13:00:18.400+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Northern, Eastern and North-Eastern regions separated from Western Region", action=_action("new_grid", "separate_day2", "regions_separated_day2"), process=("india_day2_cascade_l1", "separate_day2_regions"), metrics={"lost_western_infeed_mw": 3912}),
        _entry("day2_frequency_plateau", "2012-07-31T13:00:35+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Frequency fell and stabilized near 48.12 Hz for almost one minute", action=_action("system_frequency", "plateau_day2", "plateau_48_12hz"), process=("india_day2_cascade_l1", "plateau_day2_frequency"), metrics={"day2_frequency_plateau_hz": 48.12, "day2_ufr_flat_mw": 5600, "day2_dfdt_mw": 6020}),
        _entry("day2_ufr_inadequate", "2012-07-31T13:00:35.001+05:30", entry_kind="derived", evidence="derived", fact="All three stages were called but the relief was inadequate", action=_action("ufr_protection", "fail_day2", "inadequate_day2"), process=("india_day2_cascade_l1", "fail_day2_ufr")),
        _entry("day2_multi_region_collapse", "2012-07-31T13:01:29+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="The separated Northern-Eastern-North-Eastern system collapsed", action=_action("new_grid", "collapse_day2", "collapsed_day2"), process=("india_day2_cascade_l1", "collapse_day2_regions")),
        _entry("day2_northern_blackout", "2012-07-31T13:01:29.000500+05:30", entry_kind="derived", evidence="derived", fact="Northern Region entered its second blackout state", action=_action("northern_region", "collapse_day2", "blackout_day2"), process=("india_day2_cascade_l1", "collapse_day2_north")),
        _entry("day2_frequency_collapsed", "2012-07-31T13:01:29.001+05:30", entry_kind="derived", evidence="derived", fact="Frequency collapse completed", action=_action("system_frequency", "collapse_day2", "collapsed_day2"), process=("india_day2_cascade_l1", "collapse_day2_frequency")),
        _entry("day2_48000mw_interrupted", "2012-07-31T13:01:29.002+05:30", entry_kind="derived", evidence="derived", fact="Approximately 48,000 MW across 21 states and one union territory was affected", action=_action("customer_load", "interrupt_day2", "outage_48000mw_day2"), process=("india_day2_cascade_l1", "interrupt_day2_load"), situations=["day2_multi_region_blackout"], metrics={"day2_affected_load_mw": 48000, "affected_states": 21, "affected_union_territories": 1}),
        _entry("day2_surviving_pockets", "2012-07-31T13:01:30+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Western Region and documented generating and regional islands survived", action=_action("surviving_islands", "form_day2", "day2_pockets"), process=("india_day2_cascade_l1", "retain_day2_islands")),
        _entry("day2_recovery_started", "2012-07-31T13:01:31+05:30", entry_kind="input", origin="planned_process_start", evidence="reported", source="india_inquiry_final_report", fact="Restoration began from intact Western and Southern regions and self-started hydro", action=_action("restoration", "start_day2", "day2_active"), process=("india_day2_recovery_l1", "start_day2_recovery")),
        _entry("day2_emergency_loads_restored", "2012-07-31T15:30:00+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="Most railway, metro, mine and airport emergency loads had supply", action=_action("customer_load", "restore_day2_emergency", "day2_emergency_restored"), process=("india_day2_recovery_l1", "restore_day2_emergency")),
        _entry("day2_corridor_restored", "2012-07-31T21:30:00+05:30", entry_kind="derived", evidence="derived", fact="Interregional supply paths supported full system restoration", action=_action("west_north_corridor", "restore_final", "restored_final"), process=("india_day2_recovery_l1", "restore_day2_corridor")),
        _entry("day2_load_fully_restored", "2012-07-31T21:30:00.001+05:30", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="india_inquiry_final_report", fact="The affected system was fully restored by about 21:30", action=_action("customer_load", "restore_day2_full", "fully_restored"), process=("india_day2_recovery_l1", "restore_day2_load"), metrics={"day2_full_restoration_time": "21:30", "restoration_percent": 100}),
        _entry("day2_grid_restored", "2012-07-31T21:30:00.002+05:30", entry_kind="derived", evidence="derived", fact="The NEW grid reached its restored state", action=_action("new_grid", "restore_final", "restored_final"), process=("india_day2_recovery_l1", "restore_day2_grid")),
        _entry("day2_north_restored", "2012-07-31T21:30:00.003+05:30", entry_kind="derived", evidence="derived", fact="Northern Region returned to stable service", action=_action("northern_region", "restore_day2", "restored_day2"), process=("india_day2_recovery_l1", "restore_day2_north")),
        _entry("day2_frequency_restored", "2012-07-31T21:30:00.004+05:30", entry_kind="derived", evidence="derived", fact="System frequency returned to nominal operation", action=_action("system_frequency", "restore_nominal", "nominal"), process=("india_day2_recovery_l1", "restore_day2_frequency")),
        _entry("day2_islands_reintegrated", "2012-07-31T21:30:00.005+05:30", entry_kind="derived", evidence="derived", fact="Surviving islands were reintegrated", action=_action("surviving_islands", "reintegrate_day2", "reintegrated_final"), process=("india_day2_recovery_l1", "reintegrate_day2_islands")),
        _entry("ufr_review_required", "2012-07-31T21:30:00.006+05:30", entry_kind="derived", evidence="derived", fact="Protection performance required corrective review", action=_action("ufr_protection", "require_review", "review_required"), process=("india_day2_recovery_l1", "mark_ufr_review")),
        _entry("india_grid_balance_resolved", "2012-07-31T21:30:00.007+05:30", entry_kind="derived", evidence="derived", fact="Two-day stressed balance condition closed", action=_action("india_grid_balance", "resolve", "resolved"), process=("india_day2_recovery_l1", "resolve_grid_balance")),
        _entry("day2_recovery_complete", "2012-07-31T21:30:00.008+05:30", entry_kind="derived", evidence="derived", fact="31 July L1 recovery process completed", action=_action("restoration", "complete_day2", "day2_complete"), process=("india_day2_recovery_l1", "complete_day2_recovery"), situations=["two_day_stable_restoration"]),
    ],
    "checkpoints": [
        {"id": "day1_frequency_collapse", "after": "day1_load_interrupted", "all": [{"object": "northern_region", "state": "blackout_day1"}, {"metric": "day1_frequency_fall_seconds", "equals": 6.5}]},
        {"id": "day1_15000mw_by_1000", "after": "day1_15000mw_restored", "all": [{"object": "customer_load", "state": "day1_15000mw_restored"}, {"metric": "day1_restored_load_mw", "equals": 15000}]},
        {"id": "day1_full_by_1600", "after": "day1_balance_closed", "all": [{"object": "northern_region", "state": "restored_day1"}, {"object": "restoration", "state": "day1_complete"}]},
        {"id": "day2_48000mw_blackout", "after": "day2_48000mw_interrupted", "all": [{"object": "new_grid", "state": "collapsed_day2"}, {"metric": "day2_affected_load_mw", "equals": 48000}]},
        {"id": "day2_full_by_2130", "after": "day2_recovery_complete", "all": [{"object": "customer_load", "state": "fully_restored"}, {"object": "new_grid", "state": "restored_final"}, {"metric": "restoration_percent", "equals": 100}]},
    ],
    "expected_final": {
        "object_states": {"india_grid_balance": "resolved", "west_north_corridor": "restored_final", "northern_region": "restored_day2", "new_grid": "restored_final", "system_frequency": "nominal", "ufr_protection": "review_required", "customer_load": "fully_restored", "surviving_islands": "reintegrated_final", "restoration": "day2_complete"},
        "situations": ["day1_corridor_failure", "day1_northern_blackout", "day1_full_restoration", "day2_multi_region_blackout", "two_day_stable_restoration"],
    },
}


_bind_event_model_objects(INDIA_2012)


SOUTHWEST_CASCADE_STEPS = [
    _step("record_pre_event_stress", "Record stressed but intact pre-event state"),
    _step("trip_hng", "Trip Hassayampa–North Gila after switching fault", after=["record_pre_event_stress"], target="hng_line", capability="fault_trip"),
    _step("overload_cv", "Overload Coachella Valley transformers", after=["trip_hng"], target="cv_transformers", capability="overload"),
    _step("trip_cv", "Trip both Coachella Valley transformers", after=["overload_cv"], target="cv_transformers", capability="trip"),
    _step("overload_ramon", "Overload Ramon transformer with delayed protection", after=["trip_cv"], target="ramon_transformer", capability="overload"),
    _step("trip_ramon", "Trip Ramon transformer", after=["overload_ramon"], target="ramon_transformer", capability="trip"),
    _step("collapse_iid_north", "Collapse IID northern 92 kV system and shed 444 MW", after=["trip_ramon"], target="iid_north", capability="collapse"),
    _step("isolate_yuma", "Isolate Yuma pocket to one SDG&E tie", after=["collapse_iid_north"], target="yuma_pocket", capability="isolate"),
    _step("overload_path44", "Raise Path 44 current above separation threshold", after=["isolate_yuma"], target="path44", capability="exceed_threshold"),
    _step("trip_s_line", "Operate S Line RAS and trip S Line", after=["overload_path44"], target="s_line", capability="trip"),
    _step("separate_songs", "Operate SONGS separation scheme", after=["trip_s_line"], target="songs_scheme", capability="operate"),
    _step("form_regional_island", "Form SDG&E–CFE–Yuma island", after=["separate_songs"], target="regional_system", capability="island"),
    _step("split_islands", "Split the regional island into three islands", after=["form_regional_island"], target="regional_system", capability="split"),
    _step("collapse_islands", "Collapse all three islands", after=["split_islands"], target="regional_system", capability="collapse"),
    _step("interrupt_customers", "Record approximately 2.7 million customers interrupted", after=["collapse_islands"], target="customer_supply", capability="interrupt"),
]

SOUTHWEST_RECOVERY_STEPS = [
    _step("start_multi_system_restoration", "Start coordinated restoration without black start", target="restoration", capability="start"),
    _step("restore_hng", "Restore H-NG in approximately two hours", after=["start_multi_system_restoration"], target="hng_line", capability="restore"),
    _step("restore_iid_aps_walc_load", "Restore IID, APS and WALC customer load", after=["restore_hng"], target="customer_supply", capability="restore_partial"),
    _step("restore_cfe_load", "Restore all CFE load", after=["restore_iid_aps_walc_load"], target="customer_supply", capability="restore_cfe"),
    _step("restore_sdge_load", "Restore all SDG&E load", after=["restore_cfe_load"], target="customer_supply", capability="restore_all"),
    _step("stabilize_regional_system", "Complete stable load restoration", after=["restore_sdge_load"], target="regional_system", capability="stabilize"),
    _step("complete_restoration", "Complete the L1 restoration process", after=["stabilize_regional_system"], target="restoration", capability="complete"),
]

SOUTHWEST_2011 = {
    "schema_version": 2,
    "id": "southwest-blackout-2011-l1",
    "scenario_id": "southwest-2011",
    "name": "Southwest Blackout, 2011 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "ferc_nerc_final_report",
            "url": "https://www.ferc.gov/sites/default/files/2020-04/Arizona-Southern%20California%20Outages%20on%20September%208,%202011.pdf",
            "scope": "seven-phase cascade, exact disturbance times, affected load and restoration milestones",
            "priority": "final_primary_regulator_report",
        },
        {
            "id": "ferc_staff_reports_index",
            "url": "https://www.ferc.gov/staff-reports-and-papers",
            "scope": "official publication provenance",
            "priority": "official_index",
        },
    ],
    "model": {
        "id": "qualification-southwest-2011",
        "name": "Southwest Blackout 2011 · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Generalized causal topology from the FERC/NERC final report; it is not a reusable reference grid.",
        "event_targets": {
            "operator_error": "sw-hng-line",
            "overload": "sw-cv-transformers",
        },
        "nodes": [
            {"id": "sw-external-west", "name": "Western interconnection sources", "component_type_id": "external-grid", "x": 40, "y": 80, "capacity_mw": 2750},
            {"id": "sw-hng-line", "name": "Hassayampa–North Gila 500 kV", "component_type_id": "transmission-corridor", "x": 250, "y": 80, "qualification_object_id": "hng_line"},
            {"id": "sw-cv-transformers", "name": "Coachella Valley 230/92 kV transformers", "component_type_id": "transformer-group", "x": 470, "y": 40, "qualification_object_id": "cv_transformers"},
            {"id": "sw-ramon-transformer", "name": "Ramon 230/92 kV transformer", "component_type_id": "transformer-group", "x": 690, "y": 40, "qualification_object_id": "ramon_transformer"},
            {"id": "sw-iid-north", "name": "IID northern 92 kV system", "component_type_id": "grid-zone", "x": 910, "y": 40, "qualification_object_id": "iid_north"},
            {"id": "sw-songs-nuclear", "name": "San Onofre Nuclear Generating Station", "component_type_id": "nuclear-plant", "x": 250, "y": 250},
            {"id": "sw-path44", "name": "Path 44 corridor", "component_type_id": "transmission-corridor", "x": 470, "y": 250, "qualification_object_id": "path44"},
            {"id": "sw-sdge-grid", "name": "SDG&E system", "component_type_id": "grid-zone", "x": 690, "y": 250},
            {"id": "sw-regional-system", "name": "SDG&E–CFE–Yuma regional system", "component_type_id": "grid-zone", "x": 910, "y": 250, "qualification_object_id": "regional_system"},
            {"id": "sw-s-line", "name": "El Centro–La Rosita S Line", "component_type_id": "transmission-corridor", "x": 690, "y": 430, "qualification_object_id": "s_line"},
            {"id": "sw-cfe-grid", "name": "CFE Baja California system", "component_type_id": "grid-zone", "x": 910, "y": 430},
            {"id": "sw-yuma-pocket", "name": "Yuma load pocket", "component_type_id": "grid-zone", "x": 1130, "y": 120, "qualification_object_id": "yuma_pocket"},
            {"id": "sw-customer-supply", "name": "Affected customer supply", "component_type_id": "customer-group", "x": 1350, "y": 250, "qualification_object_id": "customer_supply"},
            {"id": "sw-songs-scheme", "name": "SONGS separation scheme", "component_type_id": "protection-system", "x": 470, "y": 430, "qualification_object_id": "songs_scheme"},
            {"id": "sw-restoration", "name": "Multi-system restoration", "component_type_id": "response-process", "x": 1130, "y": 430, "qualification_object_id": "restoration"},
        ],
        "edges": [
            {"id": "sw-edge-west-hng", "source": "sw-external-west", "target": "sw-hng-line"},
            {"id": "sw-edge-hng-cv", "source": "sw-hng-line", "target": "sw-cv-transformers"},
            {"id": "sw-edge-cv-ramon", "source": "sw-cv-transformers", "target": "sw-ramon-transformer"},
            {"id": "sw-edge-ramon-iid", "source": "sw-ramon-transformer", "target": "sw-iid-north"},
            {"id": "sw-edge-songs-path44", "source": "sw-songs-nuclear", "target": "sw-path44"},
            {"id": "sw-edge-path44-sdge", "source": "sw-path44", "target": "sw-sdge-grid"},
            {"id": "sw-edge-sdge-regional", "source": "sw-sdge-grid", "target": "sw-regional-system"},
            {"id": "sw-edge-iid-regional", "source": "sw-iid-north", "target": "sw-regional-system"},
            {"id": "sw-edge-regional-sline", "source": "sw-regional-system", "target": "sw-s-line"},
            {"id": "sw-edge-sline-cfe", "source": "sw-s-line", "target": "sw-cfe-grid"},
            {"id": "sw-edge-regional-yuma", "source": "sw-regional-system", "target": "sw-yuma-pocket"},
            {"id": "sw-edge-iid-customers", "source": "sw-iid-north", "target": "sw-customer-supply"},
            {"id": "sw-edge-yuma-customers", "source": "sw-yuma-pocket", "target": "sw-customer-supply"},
            {"id": "sw-edge-cfe-customers", "source": "sw-cfe-grid", "target": "sw-customer-supply"},
        ],
    },
    "objects": [
        _object("hng_line", "Hassayampa–North Gila 500 kV line", "transmission_line", "in_service", ["in_service", "fault_tripped", "restored"], {"fault_trip": _transitions(("in_service", "fault_tripped")), "restore": _transitions(("fault_tripped", "restored"))}, model_node_id="sw-hng-line"),
        _object("cv_transformers", "Coachella Valley 230/92 kV transformers", "transformer_group", "normal", ["normal", "overloaded", "tripped"], {"overload": _transitions(("normal", "overloaded")), "trip": _transitions(("overloaded", "tripped"))}, model_node_id="sw-cv-transformers"),
        _object("ramon_transformer", "Ramon 230/92 kV transformer", "transformer", "normal", ["normal", "overloaded_delayed", "tripped"], {"overload": _transitions(("normal", "overloaded_delayed")), "trip": _transitions(("overloaded_delayed", "tripped"))}, model_node_id="sw-ramon-transformer"),
        _object("iid_north", "IID northern 92 kV system", "power_system", "supplied", ["supplied", "collapsed_444mw_shed"], {"collapse": _transitions(("supplied", "collapsed_444mw_shed"))}, model_node_id="sw-iid-north"),
        _object("yuma_pocket", "Yuma load pocket", "load_pocket", "interconnected", ["interconnected", "single_sdge_tie"], {"isolate": _transitions(("interconnected", "single_sdge_tie"))}, model_node_id="sw-yuma-pocket"),
        _object("path44", "Path 44 transmission corridor", "transmission_corridor", "below_threshold", ["below_threshold", "above_8000a"], {"exceed_threshold": _transitions(("below_threshold", "above_8000a"))}, model_node_id="sw-path44"),
        _object("s_line", "El Centro–La Rosita S Line", "transmission_line", "in_service", ["in_service", "ras_tripped"], {"trip": _transitions(("in_service", "ras_tripped"))}, model_node_id="sw-s-line"),
        _object("songs_scheme", "SONGS separation scheme", "protection_system", "standby", ["standby", "operated"], {"operate": _transitions(("standby", "operated"))}, model_node_id="sw-songs-scheme"),
        _object("regional_system", "SDG&E–CFE–Yuma regional system", "power_system", "interconnected", ["interconnected", "islanded", "three_islands", "collapsed", "stable_restoration"], {"island": _transitions(("interconnected", "islanded")), "split": _transitions(("islanded", "three_islands")), "collapse": _transitions(("three_islands", "collapsed")), "stabilize": _transitions(("collapsed", "stable_restoration"))}, model_node_id="sw-regional-system"),
        _object("customer_supply", "Affected customer supply", "customer_group", "supplied", ["supplied", "outage_2_7m", "iid_aps_walc_restored", "cfe_restored", "all_load_restored"], {"interrupt": _transitions(("supplied", "outage_2_7m")), "restore_partial": _transitions(("outage_2_7m", "iid_aps_walc_restored")), "restore_cfe": _transitions(("iid_aps_walc_restored", "cfe_restored")), "restore_all": _transitions(("cfe_restored", "all_load_restored"))}, model_node_id="sw-customer-supply"),
        _object("restoration", "Multi-system restoration", "response_process", "standby", ["standby", "active_no_black_start", "complete"], {"start": _transitions(("standby", "active_no_black_start")), "complete": _transitions(("active_no_black_start", "complete"))}, model_node_id="sw-restoration"),
    ],
    "situations": [
        {"id": "hng_single_contingency", "all": [{"object": "hng_line", "state": "fault_tripped"}]},
        {"id": "lower_voltage_cascade", "all": [{"object": "iid_north", "state": "collapsed_444mw_shed"}]},
        {"id": "path44_separation", "all": [{"object": "path44", "state": "above_8000a"}, {"object": "songs_scheme", "state": "operated"}]},
        {"id": "regional_blackout", "all": [{"object": "regional_system", "state": "collapsed"}, {"object": "customer_supply", "state": "outage_2_7m"}]},
        {"id": "stable_load_restoration", "all": [{"object": "regional_system", "state": "stable_restoration"}, {"object": "customer_supply", "state": "all_load_restored"}]},
    ],
    "processes": [
        _process("southwest_cascade_l1", "Southwest seven-phase cascade L1", SOUTHWEST_CASCADE_STEPS),
        _process("southwest_recovery_l1", "Southwest multi-system recovery L1", SOUTHWEST_RECOVERY_STEPS),
    ],
    "timeline": [
        _entry("pre_event_stress", "2011-09-08T15:27:38-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="Southern California imported about 2,750 MW; H-NG loading was 78% and Coachella Valley transformers 83%", process=("southwest_cascade_l1", "record_pre_event_stress"), metrics={"southern_california_import_mw": 2750, "hng_loading_percent": 78, "cv_loading_percent": 83}),
        _entry("hng_fault_trip", "2011-09-08T15:27:39-07:00", entry_kind="input", origin="external_event", evidence="reported", source="ferc_nerc_final_report", fact="Skipped isolation step led to an arc and phase-to-phase fault; protection cleared it in 43 ms", action=_action("hng_line", "fault_trip", "fault_tripped"), process=("southwest_cascade_l1", "trip_hng"), situations=["hng_single_contingency"], metrics={"fault_clearance_ms": 43, "path44_flow_increase_percent": 84}),
        _entry("cv_overload", "2011-09-08T15:27:40-07:00", entry_kind="derived", evidence="derived", fact="Loss of H-NG immediately overloaded the Coachella Valley transformers", action=_action("cv_transformers", "overload", "overloaded"), process=("southwest_cascade_l1", "overload_cv")),
        _entry("cv_trip", "2011-09-08T15:28:16-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="Both Coachella Valley transformers had tripped within 40 seconds of H-NG", action=_action("cv_transformers", "trip", "tripped"), process=("southwest_cascade_l1", "trip_cv"), metrics={"path44_current_a": 6700}),
        _entry("ramon_overload", "2011-09-08T15:28:17-07:00", entry_kind="derived", evidence="derived", fact="Ramon carried excessive load while its relay setting delayed operation", action=_action("ramon_transformer", "overload", "overloaded_delayed"), process=("southwest_cascade_l1", "overload_ramon"), metrics={"ramon_relay_setting_percent": 207, "ramon_design_setting_percent": 120}),
        _entry("ramon_trip", "2011-09-08T15:32:10.621-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="Ramon transformer tripped after approximately four minutes of overload", action=_action("ramon_transformer", "trip", "tripped"), process=("southwest_cascade_l1", "trip_ramon")),
        _entry("iid_north_collapse", "2011-09-08T15:32:11-07:00", entry_kind="derived", evidence="derived", fact="IID northern 92 kV voltage collapsed and 444 MW of load was shed", action=_action("iid_north", "collapse", "collapsed_444mw_shed"), process=("southwest_cascade_l1", "collapse_iid_north"), situations=["lower_voltage_cascade"], metrics={"iid_north_load_shed_mw": 444}),
        _entry("yuma_single_tie", "2011-09-08T15:35:40-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="Transformer trips isolated the Yuma pocket to a single SDG&E tie", action=_action("yuma_pocket", "isolate", "single_sdge_tie"), process=("southwest_cascade_l1", "isolate_yuma"), metrics={"path44_current_a": 7800}),
        _entry("path44_threshold_exceeded", "2011-09-08T15:37:55-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="El Centro–Pilot Knob tripped and Path 44 current rose above the 8,000 A separation threshold", action=_action("path44", "exceed_threshold", "above_8000a"), process=("southwest_cascade_l1", "overload_path44"), metrics={"path44_current_peak_a": 9500, "path44_separation_threshold_a": 8000}),
        _entry("s_line_ras_trip", "2011-09-08T15:38:21-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="The S Line RAS tripped generation and then opened the S Line", action=_action("s_line", "trip", "ras_tripped"), process=("southwest_cascade_l1", "trip_s_line")),
        _entry("songs_scheme_operated", "2011-09-08T15:38:21.200-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="The SONGS separation scheme operated", action=_action("songs_scheme", "operate", "operated"), process=("southwest_cascade_l1", "separate_songs"), situations=["path44_separation"]),
        _entry("regional_island_formed", "2011-09-08T15:38:21.201-07:00", entry_kind="derived", evidence="derived", fact="SDG&E, CFE and Yuma formed an electrical island", action=_action("regional_system", "island", "islanded"), process=("southwest_cascade_l1", "form_regional_island")),
        _entry("three_islands_formed", "2011-09-08T15:38:22-07:00", entry_kind="derived", evidence="derived", fact="The regional island split into SDG&E, CFE and Yuma islands", action=_action("regional_system", "split", "three_islands"), process=("southwest_cascade_l1", "split_islands")),
        _entry("three_islands_collapsed", "2011-09-08T15:38:38-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="Generation-demand imbalance defeated UFLS and all three islands collapsed", action=_action("regional_system", "collapse", "collapsed"), process=("southwest_cascade_l1", "collapse_islands")),
        _entry("customer_interruption", "2011-09-08T15:38:38.001-07:00", entry_kind="derived", evidence="derived", fact="Approximately 2.7 million customers were interrupted", action=_action("customer_supply", "interrupt", "outage_2_7m"), process=("southwest_cascade_l1", "interrupt_customers"), situations=["regional_blackout"], metrics={"affected_customers": 2700000, "cascade_duration_minutes": 11}),
        _entry("restoration_started", "2011-09-08T15:38:39-07:00", entry_kind="input", origin="planned_process_start", evidence="reported", source="ferc_nerc_final_report", fact="Affected entities began restoration using energized internal or neighboring sources; black start was not required", action=_action("restoration", "start", "active_no_black_start"), process=("southwest_recovery_l1", "start_multi_system_restoration"), metrics={"black_start_required": 0}),
        _entry("hng_restored", "2011-09-08T17:27:39-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="APS restored H-NG in approximately two hours", action=_action("hng_line", "restore", "restored"), process=("southwest_recovery_l1", "restore_hng"), metrics={"hng_restoration_hours": 2}),
        _entry("iid_aps_walc_load_restored", "2011-09-08T22:23:00-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="IID, APS and WALC had restored all interrupted customer demand", action=_action("customer_supply", "restore_partial", "iid_aps_walc_restored"), process=("southwest_recovery_l1", "restore_iid_aps_walc_load"), metrics={"iid_restoration_hours": 6, "aps_restoration_hours": 6, "walc_restoration_hours": 6.5}),
        _entry("cfe_load_restored", "2011-09-09T01:37:00-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="CFE restored 100% of interrupted demand", action=_action("customer_supply", "restore_cfe", "cfe_restored"), process=("southwest_recovery_l1", "restore_cfe_load"), metrics={"cfe_restoration_hours": 10}),
        _entry("sdge_load_restored", "2011-09-09T03:23:00-07:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_final_report", fact="SDG&E restored 100% of interrupted demand", action=_action("customer_supply", "restore_all", "all_load_restored"), process=("southwest_recovery_l1", "restore_sdge_load"), metrics={"sdge_restoration_hours": 12, "restoration_percent": 100}),
        _entry("regional_system_stable", "2011-09-09T03:23:00.001-07:00", entry_kind="derived", evidence="derived", fact="Customer-load restoration boundary reached", action=_action("regional_system", "stabilize", "stable_restoration"), process=("southwest_recovery_l1", "stabilize_regional_system"), situations=["stable_load_restoration"]),
        _entry("restoration_complete", "2011-09-09T03:23:00.002-07:00", entry_kind="derived", evidence="derived", fact="L1 restoration process complete", action=_action("restoration", "complete", "complete"), process=("southwest_recovery_l1", "complete_restoration")),
    ],
    "checkpoints": [
        {"id": "hng_trip_43ms", "after": "hng_fault_trip", "all": [{"object": "hng_line", "state": "fault_tripped"}, {"metric": "fault_clearance_ms", "equals": 43}]},
        {"id": "iid_444mw_shed", "after": "iid_north_collapse", "all": [{"object": "iid_north", "state": "collapsed_444mw_shed"}, {"metric": "iid_north_load_shed_mw", "equals": 444}]},
        {"id": "path44_9500a", "after": "songs_scheme_operated", "all": [{"object": "songs_scheme", "state": "operated"}, {"metric": "path44_current_peak_a", "equals": 9500}]},
        {"id": "blackout_2_7m", "after": "customer_interruption", "all": [{"object": "regional_system", "state": "collapsed"}, {"metric": "affected_customers", "equals": 2700000}]},
        {"id": "load_restored_12h", "after": "restoration_complete", "all": [{"object": "customer_supply", "state": "all_load_restored"}, {"metric": "sdge_restoration_hours", "equals": 12}, {"metric": "restoration_percent", "equals": 100}]},
    ],
    "expected_final": {
        "object_states": {"hng_line": "restored", "cv_transformers": "tripped", "ramon_transformer": "tripped", "iid_north": "collapsed_444mw_shed", "yuma_pocket": "single_sdge_tie", "path44": "above_8000a", "s_line": "ras_tripped", "songs_scheme": "operated", "regional_system": "stable_restoration", "customer_supply": "all_load_restored", "restoration": "complete"},
        "situations": ["hng_single_contingency", "lower_voltage_cascade", "path44_separation", "regional_blackout", "stable_load_restoration"],
    },
}


TEXAS_PREPARATION_STEPS = [
    _step("activate_extreme_freeze", "Activate the prolonged extreme cold-weather event", target="cold_weather", capability="freeze"),
    _step("constrain_gas_supply", "Constrain natural-gas production and delivery", after=["activate_extreme_freeze"], target="gas_supply", capability="constrain"),
    _step("accelerate_generation_outages", "Accelerate generation outages, derates and failures to start", after=["constrain_gas_supply"], target="generation_fleet", capability="degrade"),
    _step("deplete_responsive_reserve", "Reduce Physical Responsive Capability below 2,300 MW", after=["accelerate_generation_outages"], target="responsive_capability", capability="fall_below_2300"),
    _step("declare_eea1", "Declare ERCOT EEA 1", after=["deplete_responsive_reserve"], target="ercot_alert", capability="declare_eea1"),
    _step("begin_frequency_decline", "Begin sustained frequency decline", after=["declare_eea1"], target="system_frequency", capability="decline"),
    _step("fall_below_1750", "Reduce responsive capability below the EEA 2 criterion", after=["begin_frequency_decline"], target="responsive_capability", capability="fall_below_1750"),
    _step("declare_eea2", "Declare ERCOT EEA 2 and deploy demand response", after=["fall_below_1750"], target="ercot_alert", capability="declare_eea2"),
    _step("temporarily_recover_frequency", "Temporarily recover frequency above 59.95 Hz", after=["declare_eea2"], target="system_frequency", capability="recover_eea2"),
]

TEXAS_FREQUENCY_EMERGENCY_STEPS = [
    _step("fall_below_1430", "Reduce responsive capability below the EEA 3 criterion", target="responsive_capability", capability="fall_below_1430"),
    _step("declare_eea3", "Declare ERCOT EEA 3", after=["fall_below_1430"], target="ercot_alert", capability="declare_eea3"),
    _step("shed_1000mw", "Order the first 1,000 MW of firm load shed", after=["declare_eea3"], target="firm_load", capability="shed_1000"),
    _step("shed_2000mw", "Increase firm load shed to 2,000 MW", after=["shed_1000mw"], target="firm_load", capability="shed_2000"),
    _step("shed_5000mw", "Increase firm load shed to 5,000 MW", after=["shed_2000mw"], target="firm_load", capability="shed_5000"),
    _step("reach_frequency_nadir", "Reach the event frequency nadir of 59.304 Hz", after=["shed_5000mw"], target="system_frequency", capability="reach_nadir"),
    _step("trip_ufls_276mw", "Trip approximately 276 MW by UFLS", after=["reach_frequency_nadir"], target="ufls", capability="trip"),
    _step("shed_8500mw", "Increase firm load shed to 8,500 MW", after=["trip_ufls_276mw"], target="firm_load", capability="shed_8500"),
    _step("clear_generator_trip_level", "Raise frequency above the 59.4 Hz generator-trip level", after=["shed_8500mw"], target="system_frequency", capability="clear_trip_level"),
    _step("shed_10500mw", "Increase firm load shed to 10,500 MW", after=["clear_generator_trip_level"], target="firm_load", capability="shed_10500"),
    _step("restore_frequency_60", "Restore frequency above 60 Hz", after=["shed_10500mw"], target="system_frequency", capability="stabilize_60"),
    _step("restore_1500mw", "Restore 1,500 MW while keeping 9,000 MW disconnected", after=["restore_frequency_60"], target="firm_load", capability="restore_1500"),
    _step("recover_responsive_capability", "Recover Physical Responsive Capability to 3,017 MW", after=["restore_1500mw"], target="responsive_capability", capability="recover_3017"),
    _step("stabilize_initial_grid", "Declare the immediate frequency emergency stabilized", after=["recover_responsive_capability"], target="ercot_grid", capability="stabilize_initial"),
]

TEXAS_PROLONGED_EMERGENCY_STEPS = [
    _step("start_prolonged_emergency", "Enter prolonged EEA 3 operation", target="restoration", capability="start"),
    _step("record_34000mw_unavailable", "Record average 34,000 MW generation unavailable", after=["start_prolonged_emergency"], target="generation_fleet", capability="record_average"),
    _step("shed_peak_20000mw", "Increase ordered firm load shed to the 20,000 MW peak", after=["record_34000mw_unavailable"], target="firm_load", capability="shed_20000"),
    _step("sustain_emergency_grid", "Sustain the grid under prolonged controlled interruption", after=["shed_peak_20000mw"], target="ercot_grid", capability="sustain_emergency"),
]

TEXAS_RECOVERY_STEPS = [
    _step("moderate_weather", "Record moderating temperatures", target="cold_weather", capability="moderate"),
    _step("recover_generation", "Return unavailable generation progressively to service", after=["moderate_weather"], target="generation_fleet", capability="recover"),
    _step("recover_gas_supply", "Recover natural-gas production and delivery", after=["recover_generation"], target="gas_supply", capability="recover"),
    _step("begin_load_restoration", "Begin reducing the peak firm-load-shed directive", after=["recover_gas_supply"], target="firm_load", capability="begin_restore"),
    _step("restore_all_load", "Issue instructions to restore all remaining firm load", after=["begin_load_restoration"], target="firm_load", capability="restore_all"),
    _step("downgrade_to_eea2", "Downgrade ERCOT from EEA 3 to EEA 2", after=["restore_all_load"], target="ercot_alert", capability="downgrade_eea2"),
    _step("normalize_generation", "Return generation availability to the post-event normal state", after=["downgrade_to_eea2"], target="generation_fleet", capability="normalize"),
    _step("stabilize_gas_supply", "Stabilize natural-gas supply", after=["normalize_generation"], target="gas_supply", capability="stabilize"),
    _step("reset_ufls", "Reset UFLS after the emergency", after=["stabilize_gas_supply"], target="ufls", capability="reset"),
    _step("restore_nominal_frequency", "Return frequency to nominal operation", after=["reset_ufls"], target="system_frequency", capability="restore_nominal"),
    _step("restore_responsive_capability", "Return responsive capability to adequate operation", after=["restore_nominal_frequency"], target="responsive_capability", capability="restore_adequate"),
    _step("end_cold_event", "End the cold-weather event", after=["restore_responsive_capability"], target="cold_weather", capability="end"),
    _step("return_normal_operations", "Return ERCOT to normal operations", after=["end_cold_event"], target="ercot_alert", capability="return_normal"),
    _step("stabilize_recovered_grid", "Complete stable ERCOT grid recovery", after=["return_normal_operations"], target="ercot_grid", capability="stabilize_recovery"),
    _step("complete_recovery", "Complete the Texas L1 recovery process", after=["stabilize_recovered_grid"], target="restoration", capability="complete"),
]

TEXAS_2021 = {
    "schema_version": 2,
    "id": "texas-cold-weather-2021-l1",
    "scenario_id": "texas-2021",
    "name": "Texas Cold Weather Outages, 2021 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "ferc_nerc_cold_weather_final",
            "url": "https://www.ferc.gov/sites/default/files/2021-12/Cold%20Weather%20Report_%202021_120821.pdf",
            "scope": "ERCOT generation losses, EEA sequence, frequency nadir, load-shed orders and restoration milestones",
            "priority": "final_primary_joint_regulator_report",
        },
        {
            "id": "ferc_final_report_release",
            "url": "https://www.ferc.gov/news-events/news/final-report-february-2021-freeze-underscores-winterization-recommendations",
            "scope": "official final-report provenance and causal percentages",
            "priority": "official_regulator_release",
        },
    ],
    "model": {
        "id": "qualification-texas-2021",
        "name": "Texas cold-weather outages 2021 · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Causal ERCOT fuel–generation–frequency topology from the joint FERC/NERC final report; generation capacities are not invented where the L1 package does not source them.",
        "event_targets": {"gas_supply_loss": "tx-gas-pipeline", "trip": "tx-gas-generation"},
        "nodes": [
            {"id": "tx-cold-weather", "name": "February 2021 extreme cold-weather event", "component_type_id": "external-hazard", "x": 40, "y": 40, "qualification_object_id": "cold_weather"},
            {"id": "tx-gas-production", "name": "ERCOT-area natural-gas production", "component_type_id": "well", "x": 40, "y": 260, "parameters": {"gas_decline_freezing_percent": 43.3, "gas_decline_power_loss_percent": 21.5}},
            {"id": "tx-gas-pipeline", "name": "Natural-gas processing and delivery to generators", "component_type_id": "pipeline", "x": 260, "y": 260, "parameters": {"fuel_related_generation_causes_percent": 31.4}, "qualification_object_id": "gas_supply"},
            {"id": "tx-gas-generation", "name": "ERCOT natural-gas generation fleet", "component_type_id": "thermal-plant", "x": 480, "y": 180, "parameters": {"fuel_kind": "natural_gas", "capacity_evidence": "not_modelled"}},
            {"id": "tx-coal-generation", "name": "ERCOT coal generation fleet", "component_type_id": "thermal-plant", "x": 480, "y": 300, "parameters": {"fuel_kind": "coal", "capacity_evidence": "not_modelled"}},
            {"id": "tx-nuclear-generation", "name": "ERCOT nuclear generation fleet", "component_type_id": "nuclear-plant", "x": 480, "y": 420, "parameters": {"capacity_evidence": "not_modelled"}},
            {"id": "tx-wind-generation", "name": "ERCOT wind generation fleet", "component_type_id": "wind-plant", "x": 700, "y": 420, "parameters": {"capacity_evidence": "not_modelled"}},
            {"id": "tx-solar-generation", "name": "ERCOT solar generation fleet", "component_type_id": "solar-plant", "x": 920, "y": 420, "parameters": {"capacity_evidence": "not_modelled"}},
            {"id": "tx-generation-availability", "name": "ERCOT generation fleet availability", "component_type_id": "system-state", "x": 700, "y": 40, "parameters": {"average_unavailable_mw": 34000, "five_hour_generation_loss_mw": 15000}, "qualification_object_id": "generation_fleet"},
            {"id": "tx-hvdc-imports", "name": "ERCOT direct-current ties", "component_type_id": "hvdc-interconnector", "x": 700, "y": 180, "parameters": {"import_limit_note": "slightly_more_than_1000_mw_reported"}},
            {"id": "tx-ercot-grid", "name": "ERCOT interconnection", "component_type_id": "grid-zone", "x": 920, "y": 260, "qualification_object_id": "ercot_grid"},
            {"id": "tx-responsive-capability", "name": "ERCOT Physical Responsive Capability", "component_type_id": "system-state", "x": 920, "y": 40, "parameters": {"eea1_threshold_mw": 2300, "eea2_threshold_mw": 1750, "eea3_threshold_mw": 1430}, "qualification_object_id": "responsive_capability"},
            {"id": "tx-alert", "name": "ERCOT Energy Emergency Alert state", "component_type_id": "response-process", "x": 1140, "y": 40, "qualification_object_id": "ercot_alert"},
            {"id": "tx-frequency", "name": "ERCOT interconnection frequency", "component_type_id": "system-state", "x": 1140, "y": 180, "parameters": {"reported_nadir_hz": 59.304}, "qualification_object_id": "system_frequency"},
            {"id": "tx-firm-load", "name": "ERCOT firm customer load", "component_type_id": "customer-group", "x": 1140, "y": 300, "parameters": {"mode": "load", "demand_mw": 61590, "peak_ordered_shed_mw": 20000}, "qualification_object_id": "firm_load"},
            {"id": "tx-ufls", "name": "ERCOT underfrequency load shedding", "component_type_id": "protection-system", "x": 1360, "y": 180, "parameters": {"reported_trip_mw": 276}, "qualification_object_id": "ufls"},
            {"id": "tx-restoration", "name": "ERCOT prolonged emergency and recovery", "component_type_id": "response-process", "x": 1360, "y": 360, "qualification_object_id": "restoration"},
        ],
        "edges": [
            {"id": "tx-edge-production-pipeline", "source": "tx-gas-production", "target": "tx-gas-pipeline", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "tx-edge-pipeline-gas-generation", "source": "tx-gas-pipeline", "target": "tx-gas-generation", "target_port": "fuel", "flow_type": "gas", "domain": "natural_gas"},
            {"id": "tx-edge-gas-grid", "source": "tx-gas-generation", "target": "tx-ercot-grid"},
            {"id": "tx-edge-coal-grid", "source": "tx-coal-generation", "target": "tx-ercot-grid"},
            {"id": "tx-edge-nuclear-grid", "source": "tx-nuclear-generation", "target": "tx-ercot-grid"},
            {"id": "tx-edge-wind-grid", "source": "tx-wind-generation", "target": "tx-ercot-grid"},
            {"id": "tx-edge-solar-grid", "source": "tx-solar-generation", "target": "tx-ercot-grid"},
            {"id": "tx-edge-hvdc-grid", "source": "tx-hvdc-imports", "target": "tx-ercot-grid"},
            {"id": "tx-edge-grid-load", "source": "tx-ercot-grid", "target": "tx-firm-load"},
        ],
    },
    "objects": [
        _object("cold_weather", "February 2021 extreme cold-weather event", "external_hazard", "forecast_watch", ["forecast_watch", "extreme_freeze", "moderating", "ended"], {"freeze": _transitions(("forecast_watch", "extreme_freeze")), "moderate": _transitions(("extreme_freeze", "moderating")), "end": _transitions(("moderating", "ended"))}),
        _object("gas_supply", "ERCOT natural-gas production and delivery", "fuel_system", "available", ["available", "freeze_power_constrained", "recovering", "stable"], {"constrain": _transitions(("available", "freeze_power_constrained")), "recover": _transitions(("freeze_power_constrained", "recovering")), "stabilize": _transitions(("recovering", "stable"))}),
        _object("generation_fleet", "ERCOT generation fleet availability", "generation_group", "available", ["available", "accelerating_outages", "average_34000mw_unavailable", "returning", "normal"], {"degrade": _transitions(("available", "accelerating_outages")), "record_average": _transitions(("accelerating_outages", "average_34000mw_unavailable")), "recover": _transitions(("average_34000mw_unavailable", "returning")), "normalize": _transitions(("returning", "normal"))}),
        _object("responsive_capability", "ERCOT Physical Responsive Capability", "reserve_state", "adequate", ["adequate", "below_2300mw", "below_1750mw", "below_1430mw", "recovered_3017mw", "adequate_restored"], {"fall_below_2300": _transitions(("adequate", "below_2300mw")), "fall_below_1750": _transitions(("below_2300mw", "below_1750mw")), "fall_below_1430": _transitions(("below_1750mw", "below_1430mw")), "recover_3017": _transitions(("below_1430mw", "recovered_3017mw")), "restore_adequate": _transitions(("recovered_3017mw", "adequate_restored"))}),
        _object("ercot_alert", "ERCOT energy emergency alert", "operator_state", "normal", ["normal", "eea1", "eea2", "eea3", "eea2_recovery", "normal_restored"], {"declare_eea1": _transitions(("normal", "eea1")), "declare_eea2": _transitions(("eea1", "eea2")), "declare_eea3": _transitions(("eea2", "eea3")), "downgrade_eea2": _transitions(("eea3", "eea2_recovery")), "return_normal": _transitions(("eea2_recovery", "normal_restored"))}),
        _object("system_frequency", "ERCOT interconnection frequency", "system_state", "normal_band", ["normal_band", "declining_initial", "recovered_eea2", "nadir_59_304hz", "above_59_4hz", "stable_above_60hz", "nominal"], {"decline": _transitions(("normal_band", "declining_initial")), "recover_eea2": _transitions(("declining_initial", "recovered_eea2")), "reach_nadir": _transitions(("recovered_eea2", "nadir_59_304hz")), "clear_trip_level": _transitions(("nadir_59_304hz", "above_59_4hz")), "stabilize_60": _transitions(("above_59_4hz", "stable_above_60hz")), "restore_nominal": _transitions(("stable_above_60hz", "nominal"))}),
        _object("firm_load", "ERCOT firm customer load", "customer_group", "supplied", ["supplied", "shed_1000mw", "shed_2000mw", "shed_5000mw", "shed_8500mw", "shed_10500mw", "shed_9000mw", "shed_20000mw", "restoring", "all_restored"], {"shed_1000": _transitions(("supplied", "shed_1000mw")), "shed_2000": _transitions(("shed_1000mw", "shed_2000mw")), "shed_5000": _transitions(("shed_2000mw", "shed_5000mw")), "shed_8500": _transitions(("shed_5000mw", "shed_8500mw")), "shed_10500": _transitions(("shed_8500mw", "shed_10500mw")), "restore_1500": _transitions(("shed_10500mw", "shed_9000mw")), "shed_20000": _transitions(("shed_9000mw", "shed_20000mw")), "begin_restore": _transitions(("shed_20000mw", "restoring")), "restore_all": _transitions(("restoring", "all_restored"))}),
        _object("ufls", "ERCOT underfrequency load shedding", "protection_system", "standby", ["standby", "tripped_276mw", "reset"], {"trip": _transitions(("standby", "tripped_276mw")), "reset": _transitions(("tripped_276mw", "reset"))}),
        _object("ercot_grid", "ERCOT interconnection", "power_system", "stable", ["stable", "near_collapse", "stabilized_initial", "sustained_emergency", "stable_recovery"], {"approach_collapse": _transitions(("stable", "near_collapse")), "stabilize_initial": _transitions(("near_collapse", "stabilized_initial")), "sustain_emergency": _transitions(("stabilized_initial", "sustained_emergency")), "stabilize_recovery": _transitions(("sustained_emergency", "stable_recovery"))}),
        _object("restoration", "ERCOT prolonged emergency and recovery", "response_process", "standby", ["standby", "prolonged_eea3", "complete"], {"start": _transitions(("standby", "prolonged_eea3")), "complete": _transitions(("prolonged_eea3", "complete"))}),
    ],
    "situations": [
        {"id": "cold_fuel_generation_loss", "all": [{"object": "cold_weather", "state": "extreme_freeze"}, {"object": "gas_supply", "state": "freeze_power_constrained"}, {"object": "generation_fleet", "state": "accelerating_outages"}]},
        {"id": "eea3_frequency_emergency", "all": [{"object": "ercot_alert", "state": "eea3"}, {"object": "firm_load", "state": "shed_1000mw"}]},
        {"id": "near_ercot_blackout", "all": [{"object": "system_frequency", "state": "nadir_59_304hz"}, {"object": "ercot_grid", "state": "near_collapse"}]},
        {"id": "peak_manual_load_shed", "all": [{"object": "firm_load", "state": "shed_20000mw"}, {"object": "generation_fleet", "state": "average_34000mw_unavailable"}]},
        {"id": "ercot_normal_operations_restored", "all": [{"object": "firm_load", "state": "all_restored"}, {"object": "ercot_alert", "state": "normal_restored"}, {"object": "ercot_grid", "state": "stable_recovery"}]},
    ],
    "processes": [
        _process("texas_cold_preparation_l1", "Texas cold-weather preparation and generation loss L1", TEXAS_PREPARATION_STEPS),
        _process("texas_frequency_emergency_l1", "Texas frequency emergency L1", TEXAS_FREQUENCY_EMERGENCY_STEPS),
        _process("texas_prolonged_emergency_l1", "Texas prolonged load-shed emergency L1", TEXAS_PROLONGED_EMERGENCY_STEPS),
        _process("texas_recovery_l1", "Texas cold-weather recovery L1", TEXAS_RECOVERY_STEPS),
    ],
    "timeline": [
        _entry("extreme_cold_event_begins", "2021-02-08T00:00:00-06:00", entry_kind="input", origin="external_event", evidence="reported", source="ferc_nerc_cold_weather_final", fact="The official event period began as extreme cold spread across the South Central United States", action=_action("cold_weather", "freeze", "extreme_freeze"), process=("texas_cold_preparation_l1", "activate_extreme_freeze")),
        _entry("gas_supply_constrained", "2021-02-14T22:00:00-06:00", entry_kind="derived", evidence="derived", fact="Freezing and electric outages constrained natural-gas production and delivery", action=_action("gas_supply", "constrain", "freeze_power_constrained"), process=("texas_cold_preparation_l1", "constrain_gas_supply"), metrics={"freeze_related_generation_causes_percent": 44.2, "fuel_related_generation_causes_percent": 31.4, "gas_decline_freezing_percent": 43.3, "gas_decline_power_loss_percent": 21.5}),
        _entry("generation_losses_accelerate", "2021-02-14T22:00:00.001-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT began losing about 15,000 MW of generation over the next five hours", action=_action("generation_fleet", "degrade", "accelerating_outages"), process=("texas_cold_preparation_l1", "accelerate_generation_outages"), situations=["cold_fuel_generation_loss"], metrics={"five_hour_generation_loss_mw": 15000}),
        _entry("responsive_reserve_below_2300", "2021-02-15T00:09:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="Physical Responsive Capability fell below the 2,300 MW minimum", action=_action("responsive_capability", "fall_below_2300", "below_2300mw"), process=("texas_cold_preparation_l1", "deplete_responsive_reserve"), metrics={"responsive_reserve_threshold_mw": 2300}),
        _entry("eea1_declared", "2021-02-15T00:15:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT declared EEA 1 and deployed ERS-30", action=_action("ercot_alert", "declare_eea1", "eea1"), process=("texas_cold_preparation_l1", "declare_eea1"), metrics={"ers30_deployed_mw": 847.15, "frequency_hz": 59.958, "physical_responsive_capability_mw": 2269}),
        _entry("frequency_decline_begins", "2021-02-15T00:18:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT frequency began to fall below the normal band", action=_action("system_frequency", "decline", "declining_initial"), process=("texas_cold_preparation_l1", "begin_frequency_decline")),
        _entry("responsive_capability_below_1750", "2021-02-15T01:07:00-06:00", entry_kind="derived", evidence="derived", fact="The EEA 2 reserve or frequency criterion was met", action=_action("responsive_capability", "fall_below_1750", "below_1750mw"), process=("texas_cold_preparation_l1", "fall_below_1750"), metrics={"eea2_prc_threshold_mw": 1750}),
        _entry("eea2_declared", "2021-02-15T01:07:00.001-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT declared EEA 2 and deployed ERS-10 plus load resources", action=_action("ercot_alert", "declare_eea2", "eea2"), process=("texas_cold_preparation_l1", "declare_eea2"), metrics={"ers10_deployed_mw": 51.6}),
        _entry("frequency_temporarily_recovers", "2021-02-15T01:16:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="Demand response temporarily recovered frequency above 59.95 Hz", action=_action("system_frequency", "recover_eea2", "recovered_eea2"), process=("texas_cold_preparation_l1", "temporarily_recover_frequency"), metrics={"demand_response_reduction_mw": 423}),
        _entry("responsive_capability_below_1430", "2021-02-15T01:18:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="Physical Responsive Capability fell to 1,377 MW, below the EEA 3 criterion", action=_action("responsive_capability", "fall_below_1430", "below_1430mw"), process=("texas_frequency_emergency_l1", "fall_below_1430"), metrics={"physical_responsive_capability_mw": 1377}),
        _entry("eea3_declared", "2021-02-15T01:20:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT declared EEA 3", action=_action("ercot_alert", "declare_eea3", "eea3"), process=("texas_frequency_emergency_l1", "declare_eea3")),
        _entry("first_1000mw_shed", "2021-02-15T01:20:00.001-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT ordered the first 1,000 MW of firm load shed", action=_action("firm_load", "shed_1000", "shed_1000mw"), process=("texas_frequency_emergency_l1", "shed_1000mw"), situations=["eea3_frequency_emergency"], metrics={"ordered_firm_load_shed_mw": 1000, "system_load_mw": 64256, "frequency_hz": 59.944}),
        _entry("total_2000mw_shed", "2021-02-15T01:45:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT ordered another 1,000 MW, reaching 2,000 MW total", action=_action("firm_load", "shed_2000", "shed_2000mw"), process=("texas_frequency_emergency_l1", "shed_2000mw"), metrics={"ordered_firm_load_shed_mw": 2000, "frequency_hz": 59.820}),
        _entry("total_5000mw_shed", "2021-02-15T01:50:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT ordered another 3,000 MW, reaching 5,000 MW total", action=_action("firm_load", "shed_5000", "shed_5000mw"), process=("texas_frequency_emergency_l1", "shed_5000mw"), metrics={"ordered_firm_load_shed_mw": 5000, "frequency_hz": 59.496}),
        _entry("frequency_nadir", "2021-02-15T01:54:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="Frequency reached the event nadir after remaining below 59.4 Hz", action=_action("system_frequency", "reach_nadir", "nadir_59_304hz"), process=("texas_frequency_emergency_l1", "reach_frequency_nadir"), metrics={"frequency_nadir_hz": 59.304, "below_59_4_duration_seconds": 263, "generation_at_nadir_mw": 60381, "load_at_nadir_mw": 61590, "generation_at_risk_mw": 17000}),
        _entry("ufls_276mw_trip", "2021-02-15T01:54:00.001-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="Approximately 276 MW tripped through UFLS", action=_action("ufls", "trip", "tripped_276mw"), process=("texas_frequency_emergency_l1", "trip_ufls_276mw"), metrics={"ufls_tripped_mw": 276}),
        _entry("grid_near_collapse", "2021-02-15T01:54:00.002-06:00", entry_kind="derived", evidence="derived", fact="ERCOT entered the documented near-blackout condition", action=_action("ercot_grid", "approach_collapse", "near_collapse"), situations=["near_ercot_blackout"]),
        _entry("total_8500mw_shed", "2021-02-15T01:55:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT ordered another 3,500 MW, reaching 8,500 MW total", action=_action("firm_load", "shed_8500", "shed_8500mw"), process=("texas_frequency_emergency_l1", "shed_8500mw"), metrics={"ordered_firm_load_shed_mw": 8500}),
        _entry("frequency_above_generator_trip_level", "2021-02-15T01:55:00.001-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="Frequency rose above 59.4 Hz after four minutes and 23 seconds below it", action=_action("system_frequency", "clear_trip_level", "above_59_4hz"), process=("texas_frequency_emergency_l1", "clear_generator_trip_level"), metrics={"frequency_hz": 59.401}),
        _entry("total_10500mw_shed", "2021-02-15T02:00:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT ordered another 2,000 MW, reaching 10,500 MW total", action=_action("firm_load", "shed_10500", "shed_10500mw"), process=("texas_frequency_emergency_l1", "shed_10500mw"), metrics={"ordered_firm_load_shed_mw": 10500}),
        _entry("frequency_above_60", "2021-02-15T02:02:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="Frequency rose above 60 Hz", action=_action("system_frequency", "stabilize_60", "stable_above_60hz"), process=("texas_frequency_emergency_l1", "restore_frequency_60"), metrics={"frequency_hz": 60.0}),
        _entry("restore_1500mw", "2021-02-15T02:30:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT ordered 1,500 MW restored, leaving 9,000 MW disconnected", action=_action("firm_load", "restore_1500", "shed_9000mw"), process=("texas_frequency_emergency_l1", "restore_1500mw"), metrics={"remaining_firm_load_shed_mw": 9000}),
        _entry("prc_recovered_3017", "2021-02-15T02:30:00.001-06:00", entry_kind="derived", evidence="derived", fact="Physical Responsive Capability recovered to 3,017 MW", action=_action("responsive_capability", "recover_3017", "recovered_3017mw"), process=("texas_frequency_emergency_l1", "recover_responsive_capability"), metrics={"physical_responsive_capability_mw": 3017}),
        _entry("initial_grid_stabilized", "2021-02-15T02:30:00.002-06:00", entry_kind="derived", evidence="derived", fact="The immediate frequency emergency was considered stable", action=_action("ercot_grid", "stabilize_initial", "stabilized_initial"), process=("texas_frequency_emergency_l1", "stabilize_initial_grid")),
        _entry("prolonged_emergency_started", "2021-02-15T02:30:00.003-06:00", entry_kind="input", origin="planned_process_start", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT remained in prolonged EEA 3 with continuing generation losses", action=_action("restoration", "start", "prolonged_eea3"), process=("texas_prolonged_emergency_l1", "start_prolonged_emergency")),
        _entry("average_34000mw_unavailable", "2021-02-15T07:00:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="The interval averaging 34,000 MW unavailable began and continued for over two days", action=_action("generation_fleet", "record_average", "average_34000mw_unavailable"), process=("texas_prolonged_emergency_l1", "record_34000mw_unavailable"), metrics={"average_generation_unavailable_mw": 34000, "winter_peak_share_percent": 49}),
        _entry("peak_20000mw_shed", "2021-02-15T19:00:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="Ordered firm load shed reached its event peak of 20,000 MW", action=_action("firm_load", "shed_20000", "shed_20000mw"), process=("texas_prolonged_emergency_l1", "shed_peak_20000mw"), situations=["peak_manual_load_shed"], metrics={"peak_firm_load_shed_mw": 20000}),
        _entry("sustained_eea3_grid", "2021-02-15T19:00:00.001-06:00", entry_kind="derived", evidence="derived", fact="Controlled interruptions sustained the grid during the generation shortage", action=_action("ercot_grid", "sustain_emergency", "sustained_emergency"), process=("texas_prolonged_emergency_l1", "sustain_emergency_grid")),
        _entry("weather_moderating", "2021-02-17T13:00:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="Temperatures moderated and the two-day average-unavailability interval ended", action=_action("cold_weather", "moderate", "moderating"), process=("texas_recovery_l1", "moderate_weather")),
        _entry("generation_returning", "2021-02-17T13:00:00.001-06:00", entry_kind="derived", evidence="derived", fact="Unavailable generation began returning progressively", action=_action("generation_fleet", "recover", "returning"), process=("texas_recovery_l1", "recover_generation")),
        _entry("gas_supply_recovering", "2021-02-17T13:00:00.002-06:00", entry_kind="derived", evidence="derived", fact="Natural-gas production and delivery began recovering", action=_action("gas_supply", "recover", "recovering"), process=("texas_recovery_l1", "recover_gas_supply")),
        _entry("load_restoration_begins", "2021-02-17T13:00:00.003-06:00", entry_kind="derived", evidence="derived", fact="ERCOT progressively reduced firm-load-shed directives", action=_action("firm_load", "begin_restore", "restoring"), process=("texas_recovery_l1", "begin_load_restoration")),
        _entry("all_remaining_load_ordered_restored", "2021-02-17T23:55:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT instructed restoration of all remaining firm load", action=_action("firm_load", "restore_all", "all_restored"), process=("texas_recovery_l1", "restore_all_load"), metrics={"firm_load_shed_duration_days": 3}),
        _entry("eea2_recovery", "2021-02-19T09:00:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT downgraded from EEA 3 to EEA 2", action=_action("ercot_alert", "downgrade_eea2", "eea2_recovery"), process=("texas_recovery_l1", "downgrade_to_eea2")),
        _entry("generation_normalized", "2021-02-19T10:34:59.993-06:00", entry_kind="derived", evidence="derived", fact="Generation availability reached the post-event normal state", action=_action("generation_fleet", "normalize", "normal"), process=("texas_recovery_l1", "normalize_generation")),
        _entry("gas_supply_stable", "2021-02-19T10:34:59.994-06:00", entry_kind="derived", evidence="derived", fact="Natural-gas supply stabilized", action=_action("gas_supply", "stabilize", "stable"), process=("texas_recovery_l1", "stabilize_gas_supply")),
        _entry("ufls_reset", "2021-02-19T10:34:59.995-06:00", entry_kind="derived", evidence="derived", fact="UFLS returned to standby readiness", action=_action("ufls", "reset", "reset"), process=("texas_recovery_l1", "reset_ufls")),
        _entry("frequency_nominal", "2021-02-19T10:34:59.996-06:00", entry_kind="derived", evidence="derived", fact="Frequency returned to nominal operation", action=_action("system_frequency", "restore_nominal", "nominal"), process=("texas_recovery_l1", "restore_nominal_frequency")),
        _entry("responsive_capability_adequate", "2021-02-19T10:34:59.997-06:00", entry_kind="derived", evidence="derived", fact="Responsive capability returned to adequate operation", action=_action("responsive_capability", "restore_adequate", "adequate_restored"), process=("texas_recovery_l1", "restore_responsive_capability")),
        _entry("cold_event_ended", "2021-02-19T10:34:59.998-06:00", entry_kind="derived", evidence="derived", fact="The ERCOT cold-weather emergency period ended", action=_action("cold_weather", "end", "ended"), process=("texas_recovery_l1", "end_cold_event")),
        _entry("ercot_normal_operations", "2021-02-19T10:35:00-06:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ferc_nerc_cold_weather_final", fact="ERCOT returned to normal operations, concluding the event", action=_action("ercot_alert", "return_normal", "normal_restored"), process=("texas_recovery_l1", "return_normal_operations")),
        _entry("ercot_grid_stable_recovery", "2021-02-19T10:35:00.001-06:00", entry_kind="derived", evidence="derived", fact="ERCOT reached the L1 stable-recovery boundary", action=_action("ercot_grid", "stabilize_recovery", "stable_recovery"), process=("texas_recovery_l1", "stabilize_recovered_grid")),
        _entry("texas_recovery_complete", "2021-02-19T10:35:00.002-06:00", entry_kind="derived", evidence="derived", fact="Texas L1 recovery process completed", action=_action("restoration", "complete", "complete"), process=("texas_recovery_l1", "complete_recovery"), situations=["ercot_normal_operations_restored"]),
    ],
    "checkpoints": [
        {"id": "eea3_first_1000mw", "after": "first_1000mw_shed", "all": [{"object": "ercot_alert", "state": "eea3"}, {"metric": "ordered_firm_load_shed_mw", "equals": 1000}]},
        {"id": "frequency_nadir_59_304", "after": "grid_near_collapse", "all": [{"object": "ercot_grid", "state": "near_collapse"}, {"metric": "frequency_nadir_hz", "equals": 59.304}, {"metric": "generation_at_risk_mw", "equals": 17000}]},
        {"id": "initial_stability_0230", "after": "initial_grid_stabilized", "all": [{"object": "ercot_grid", "state": "stabilized_initial"}, {"metric": "physical_responsive_capability_mw", "equals": 3017}]},
        {"id": "peak_20000mw_manual_shed", "after": "sustained_eea3_grid", "all": [{"object": "firm_load", "state": "shed_20000mw"}, {"metric": "peak_firm_load_shed_mw", "equals": 20000}, {"metric": "average_generation_unavailable_mw", "equals": 34000}]},
        {"id": "normal_operations_19feb", "after": "texas_recovery_complete", "all": [{"object": "firm_load", "state": "all_restored"}, {"object": "ercot_alert", "state": "normal_restored"}, {"object": "ercot_grid", "state": "stable_recovery"}]},
    ],
    "expected_final": {
        "object_states": {"cold_weather": "ended", "gas_supply": "stable", "generation_fleet": "normal", "responsive_capability": "adequate_restored", "ercot_alert": "normal_restored", "system_frequency": "nominal", "firm_load": "all_restored", "ufls": "reset", "ercot_grid": "stable_recovery", "restoration": "complete"},
        "situations": ["cold_fuel_generation_loss", "eea3_frequency_emergency", "near_ercot_blackout", "peak_manual_load_shed", "ercot_normal_operations_restored"],
    },
}


_bind_event_model_objects(TEXAS_2021)


IBERIA_PREINCIDENT_STEPS = [
    _step("start_local_oscillation", "Start the 0.63 Hz converter-driven oscillation", target="oscillation_state", capability="start_local"),
    _step("damp_local_oscillation", "Apply operational measures and damp the local oscillation", after=["start_local_oscillation"], target="oscillation_state", capability="damp_local"),
    _step("start_interarea_oscillation", "Start the 0.2 Hz inter-area oscillation", after=["damp_local_oscillation"], target="oscillation_state", capability="start_interarea"),
    _step("damp_interarea_oscillation", "Apply cross-border measures and damp the inter-area oscillation", after=["start_interarea_oscillation"], target="oscillation_state", capability="damp_interarea"),
    _step("enter_voltage_sensitive_state", "Enter a voltage-sensitive operating state after the damping measures", after=["damp_interarea_oscillation"], target="voltage_control", capability="sensitize"),
]

IBERIA_CASCADE_STEPS = [
    _step("reduce_large_res_output", "Reduce output from renewable units larger than 5 MW", target="spanish_generation", capability="reduce_500"),
    _step("lose_distributed_generation", "Trip distributed wind and solar generation", after=["reduce_large_res_output"], target="distributed_generation", capability="trip_208"),
    _step("trip_granada_transformer", "Trip the Granada-area transformer on overvoltage", after=["lose_distributed_generation"], target="granada_transformer", capability="trip_overvoltage"),
    _step("trip_badajoz_generation", "Trip two Badajoz generation sets", after=["trip_granada_transformer"], target="badajoz_generation", capability="trip_727"),
    _step("trip_further_generation", "Trip further wind and solar generation across southern and western Spain", after=["trip_badajoz_generation"], target="further_generation", capability="trip_928"),
    _step("record_loss_above_2500", "Record cumulative generation loss and net-load increase above 2.5 GW", after=["trip_further_generation"], target="spanish_generation", capability="exceed_2500"),
    _step("runaway_voltage", "Enter the sharp voltage-rise cascade", after=["record_loss_above_2500"], target="voltage_control", capability="runaway"),
    _step("fall_frequency", "Begin the terminal Iberian frequency decline", after=["runaway_voltage"], target="iberian_frequency", capability="fall"),
    _step("activate_defence", "Activate the Spanish and Portuguese system-defence plans", after=["fall_frequency"], target="system_defence", capability="activate"),
    _step("mark_defence_ineffective", "Record that correctly operating defence plans cannot stop the cascade", after=["activate_defence"], target="system_defence", capability="fail_to_arrest"),
    _step("lose_synchronism", "Begin loss of synchronism with Continental Europe", after=["mark_defence_ineffective"], target="iberian_system", capability="lose_sync"),
    _step("trip_morocco_ac", "Trip the Morocco AC interconnection on underfrequency", after=["lose_synchronism"], target="morocco_interconnection", capability="trip_underfrequency"),
    _step("trip_france_spain_ac", "Trip the France-Spain AC lines on loss of synchronism", after=["trip_morocco_ac"], target="france_spain_interconnection", capability="trip_ac"),
    _step("trip_france_spain_hvdc", "Trip the remaining France-Spain HVDC links", after=["trip_france_spain_ac"], target="france_spain_interconnection", capability="trip_hvdc"),
    _step("collapse_iberian_system", "Collapse all electrical parameters in Spain and Portugal", after=["trip_france_spain_hvdc"], target="iberian_system", capability="collapse"),
    _step("collapse_frequency", "Record the collapse of Iberian frequency", after=["collapse_iberian_system"], target="iberian_frequency", capability="collapse"),
    _step("blackout_portugal", "Record the Portuguese transmission-system blackout", after=["collapse_frequency"], target="portugal_grid", capability="blackout"),
    _step("blackout_spain", "Record the Spanish transmission-system blackout", after=["blackout_portugal"], target="spain_grid", capability="blackout"),
]

IBERIA_RESTORATION_STEPS = [
    _step("activate_restoration_plans", "Activate the Spanish and Portuguese restoration plans", target="restoration", capability="start"),
    _step("energize_france_north", "Energize the Argia-Hernani path from France", after=["activate_restoration_plans"], target="france_spain_interconnection", capability="energize_north"),
    _step("energize_morocco", "Energize the Spain-Morocco interconnection", after=["energize_france_north"], target="morocco_interconnection", capability="energize"),
    _step("energize_france_east", "Energize the Baixas-Vic path from France", after=["energize_morocco"], target="france_spain_interconnection", capability="energize_east"),
    _step("build_black_start_islands", "Build successful black-start islands in Spain and Portugal", after=["energize_france_east"], target="black_start_islands", capability="build"),
    _step("resynchronize_morocco", "Repeat and complete synchronisation with Morocco", after=["build_black_start_islands"], target="morocco_interconnection", capability="resynchronize"),
    _step("supply_nuclear_auxiliaries", "Restore external supply to all Spanish nuclear auxiliaries", after=["resynchronize_morocco"], target="nuclear_auxiliaries", capability="supply"),
    _step("energize_spain_portugal", "Energize Aldeadavila-Pocinho and return continental frequency to Portugal", after=["supply_nuclear_auxiliaries"], target="spain_portugal_interconnection", capability="energize"),
    _step("synchronize_spanish_zones", "Synchronize the southern and northern Spanish restoration zones", after=["energize_spain_portugal"], target="spain_grid", capability="synchronize_zones"),
    _step("restore_portugal", "Complete restoration of the Portuguese transmission grid", after=["synchronize_spanish_zones"], target="portugal_grid", capability="restore"),
    _step("restore_spain", "Complete restoration of the Spanish transmission grid", after=["restore_portugal"], target="spain_grid", capability="restore"),
    _step("restore_voltage", "Return Iberian voltage control to stable operation", after=["restore_spain"], target="voltage_control", capability="restore"),
    _step("restore_frequency", "Return Iberian frequency to stable operation", after=["restore_voltage"], target="iberian_frequency", capability="restore"),
    _step("stabilize_iberian_system", "Reach the stable-restoration boundary", after=["restore_frequency"], target="iberian_system", capability="stabilize"),
    _step("complete_restoration", "Complete the Iberian L1 restoration process", after=["stabilize_iberian_system"], target="restoration", capability="complete"),
]

IBERIA_2025 = {
    "schema_version": 2,
    "id": "iberian-blackout-2025-l1",
    "scenario_id": "iberia-2025",
    "name": "Iberian Blackout, 28 April 2025 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "entsoe_iberian_final_report",
            "url": "https://eepublicdownloads.blob.core.windows.net/public-cdn-container/clean-documents/Publications/2025/iberian-blackout/Final%20Report%20on%20the%20Grid%20Incident%20in%20Spain%20and%20Portugal%20on%2028%20April%202025.pdf",
            "scope": "oscillations, second-by-second cascade, loss of synchronism, blackout and restoration milestones",
            "priority": "final_primary_expert_panel_report",
        },
        {
            "id": "entsoe_final_report_release",
            "url": "https://www.entsoe.eu/news/2026/03/20/entso-e-publishes-expert-panel-final-report-on-28-april-2025-blackout-in-spain-and-portugal/",
            "scope": "official publication provenance, severity classification and report conclusions",
            "priority": "official_tso_association_release",
        },
    ],
    "model": {
        "id": "qualification-iberia-2025",
        "name": "Iberian blackout 28 April 2025 · event-specific L1 topology",
        "level": 1,
        "topology_revision": 2,
        "scope_note": "Causal voltage–generation–interconnection topology based on the ENTSO-E Expert Panel final report; it is not a geographic transmission diagram.",
        "event_targets": {"voltage_excursion": "ib-granada-transformer", "trip": "ib-badajoz-generation"},
        "nodes": [
            {"id": "ib-oscillation-state", "name": "Iberian and Continental European oscillations", "component_type_id": "system-state", "x": 40, "y": 40, "parameters": {"local_hz": 0.63, "interarea_hz": 0.2}, "qualification_object_id": "oscillation_state"},
            {"id": "ib-voltage-control", "name": "Spanish transmission-system voltage control", "component_type_id": "protection-system", "x": 260, "y": 40, "qualification_object_id": "voltage_control"},
            {"id": "ib-spanish-generation", "name": "Spanish generation balance", "component_type_id": "system-state", "x": 480, "y": 40, "parameters": {"large_res_reduction_mw": 500, "cumulative_loss_min_mw": 2500}, "qualification_object_id": "spanish_generation"},
            {"id": "ib-utility-renewables", "name": "Spanish utility-scale wind and solar generation", "component_type_id": "wind-plant", "x": 260, "y": 220, "parameters": {"capacity_evidence": "not_modelled"}},
            {"id": "ib-distributed-generation", "name": "Distributed Spanish wind and solar generation", "component_type_id": "distributed-generation", "x": 480, "y": 220, "parameters": {"reported_loss_mw": 208, "net_load_increase_mw": 317}, "qualification_object_id": "distributed_generation"},
            {"id": "ib-granada-transformer", "name": "Granada-area 400/220 kV transformer", "component_type_id": "transformer-group", "x": 700, "y": 40, "parameters": {"pretrip_active_power_mw": 355, "pretrip_reactive_absorption_mvar": 165, "pretrip_voltage_kv": 417.9}, "qualification_object_id": "granada_transformer"},
            {"id": "ib-badajoz-generation", "name": "Badajoz photovoltaic and solar-thermal sets", "component_type_id": "solar-plant", "x": 700, "y": 220, "parameters": {"reported_loss_mw": 727, "capacity_evidence": "reported_trip_only"}, "qualification_object_id": "badajoz_generation"},
            {"id": "ib-further-generation", "name": "Further southern and western wind and solar generation", "component_type_id": "wind-plant", "x": 920, "y": 220, "parameters": {"reported_loss_mw": 928, "affected_areas": 6}, "qualification_object_id": "further_generation"},
            {"id": "ib-frequency", "name": "Iberian system frequency", "component_type_id": "system-state", "x": 920, "y": 40, "qualification_object_id": "iberian_frequency"},
            {"id": "ib-system-defence", "name": "Spanish and Portuguese system-defence plans", "component_type_id": "protection-system", "x": 1140, "y": 40, "qualification_object_id": "system_defence"},
            {"id": "ib-france-grid", "name": "Continental Europe system via France", "component_type_id": "external-grid", "x": 40, "y": 420},
            {"id": "ib-france-spain-group", "name": "France–Spain AC and HVDC interconnection group", "component_type_id": "grid-zone", "x": 260, "y": 420, "qualification_object_id": "france_spain_interconnection"},
            {"id": "ib-france-spain-ac", "name": "France–Spain 400 kV AC corridors", "component_type_id": "transmission-corridor", "x": 480, "y": 360},
            {"id": "ib-france-spain-hvdc", "name": "France–Spain HVDC links", "component_type_id": "hvdc-interconnector", "x": 480, "y": 480},
            {"id": "ib-morocco-grid", "name": "Moroccan power system", "component_type_id": "external-grid", "x": 40, "y": 620},
            {"id": "ib-morocco-interconnection", "name": "Spain–Morocco AC interconnection", "component_type_id": "transmission-corridor", "x": 260, "y": 620, "qualification_object_id": "morocco_interconnection"},
            {"id": "ib-iberian-system", "name": "Spanish and Portuguese synchronous system", "component_type_id": "grid-zone", "x": 700, "y": 420, "qualification_object_id": "iberian_system"},
            {"id": "ib-spain-grid", "name": "Spanish transmission grid", "component_type_id": "grid-zone", "x": 920, "y": 360, "qualification_object_id": "spain_grid"},
            {"id": "ib-portugal-grid", "name": "Portuguese transmission grid", "component_type_id": "grid-zone", "x": 920, "y": 520, "qualification_object_id": "portugal_grid"},
            {"id": "ib-spain-load", "name": "Continental Spain pre-incident load", "component_type_id": "customer-group", "x": 1140, "y": 300, "parameters": {"mode": "load", "demand_mw": 25200, "evidence_kind": "reported"}},
            {"id": "ib-portugal-load", "name": "Mainland Portugal pre-incident load", "component_type_id": "customer-group", "x": 1140, "y": 560, "parameters": {"mode": "load", "demand_mw": 5900, "evidence_kind": "reported"}},
            {"id": "ib-spain-portugal", "name": "Aldeadavila–Pocinho Spain–Portugal interconnection", "component_type_id": "transmission-corridor", "x": 1140, "y": 440, "qualification_object_id": "spain_portugal_interconnection"},
            {"id": "ib-black-start", "name": "Spanish and Portuguese black-start islands", "component_type_id": "response-process", "x": 700, "y": 620, "qualification_object_id": "black_start_islands"},
            {"id": "ib-black-start-hydro", "name": "Hydropower used for bottom-up black start", "component_type_id": "hydro-plant", "x": 920, "y": 700, "parameters": {"capacity_evidence": "not_modelled"}},
            {"id": "ib-nuclear-auxiliaries", "name": "Spanish nuclear-plant auxiliary supplies", "component_type_id": "customer-group", "x": 1140, "y": 620, "qualification_object_id": "nuclear_auxiliaries"},
            {"id": "ib-restoration", "name": "Iberian system restoration", "component_type_id": "response-process", "x": 1360, "y": 520, "qualification_object_id": "restoration"},
        ],
        "edges": [
            {"id": "ib-edge-renewables-spain", "source": "ib-utility-renewables", "target": "ib-spain-grid"},
            {"id": "ib-edge-distributed-spain", "source": "ib-distributed-generation", "target": "ib-spain-grid"},
            {"id": "ib-edge-granada-spain", "source": "ib-granada-transformer", "target": "ib-spain-grid"},
            {"id": "ib-edge-badajoz-spain", "source": "ib-badajoz-generation", "target": "ib-spain-grid"},
            {"id": "ib-edge-further-spain", "source": "ib-further-generation", "target": "ib-spain-grid"},
            {"id": "ib-edge-france-group", "source": "ib-france-grid", "target": "ib-france-spain-group"},
            {"id": "ib-edge-group-ac", "source": "ib-france-spain-group", "target": "ib-france-spain-ac"},
            {"id": "ib-edge-group-hvdc", "source": "ib-france-spain-group", "target": "ib-france-spain-hvdc"},
            {"id": "ib-edge-ac-system", "source": "ib-france-spain-ac", "target": "ib-iberian-system"},
            {"id": "ib-edge-hvdc-system", "source": "ib-france-spain-hvdc", "target": "ib-iberian-system"},
            {"id": "ib-edge-morocco-link", "source": "ib-morocco-grid", "target": "ib-morocco-interconnection"},
            {"id": "ib-edge-morocco-system", "source": "ib-morocco-interconnection", "target": "ib-iberian-system"},
            {"id": "ib-edge-system-spain", "source": "ib-iberian-system", "target": "ib-spain-grid"},
            {"id": "ib-edge-system-portugal", "source": "ib-iberian-system", "target": "ib-portugal-grid"},
            {"id": "ib-edge-spain-load", "source": "ib-spain-grid", "target": "ib-spain-load"},
            {"id": "ib-edge-portugal-load", "source": "ib-portugal-grid", "target": "ib-portugal-load"},
            {"id": "ib-edge-spain-crossborder", "source": "ib-spain-grid", "target": "ib-spain-portugal"},
            {"id": "ib-edge-crossborder-portugal", "source": "ib-spain-portugal", "target": "ib-portugal-grid"},
            {"id": "ib-edge-hydro-black-start", "source": "ib-black-start-hydro", "target": "ib-black-start"},
            {"id": "ib-edge-spain-nuclear-aux", "source": "ib-spain-grid", "target": "ib-nuclear-auxiliaries"},
        ],
    },
    "objects": [
        _object("oscillation_state", "Iberian and Continental European oscillations", "system_phenomenon", "quiet", ["quiet", "local_0_63hz", "local_damped", "interarea_0_2hz", "damped"], {"start_local": _transitions(("quiet", "local_0_63hz")), "damp_local": _transitions(("local_0_63hz", "local_damped")), "start_interarea": _transitions(("local_damped", "interarea_0_2hz")), "damp_interarea": _transitions(("interarea_0_2hz", "damped"))}),
        _object("voltage_control", "Spanish transmission-system voltage control", "control_system", "normal", ["normal", "sensitive", "runaway_rise", "stable_restored"], {"sensitize": _transitions(("normal", "sensitive")), "runaway": _transitions(("sensitive", "runaway_rise")), "restore": _transitions(("runaway_rise", "stable_restored"))}),
        _object("spanish_generation", "Spanish generation balance", "generation_group", "normal", ["normal", "reduced_500mw", "loss_above_2500mw"], {"reduce_500": _transitions(("normal", "reduced_500mw")), "exceed_2500": _transitions(("reduced_500mw", "loss_above_2500mw"))}),
        _object("distributed_generation", "Distributed Spanish wind and solar generation", "generation_group", "online", ["online", "tripped_208mw"], {"trip_208": _transitions(("online", "tripped_208mw"))}),
        _object("granada_transformer", "Granada-area 400/220 kV transformer", "transformer", "connected_absorbing_165mvar", ["connected_absorbing_165mvar", "overvoltage_tripped"], {"trip_overvoltage": _transitions(("connected_absorbing_165mvar", "overvoltage_tripped"))}),
        _object("badajoz_generation", "Two Badajoz generation sets", "generation_group", "online", ["online", "tripped_727mw"], {"trip_727": _transitions(("online", "tripped_727mw"))}),
        _object("further_generation", "Further southern and western Spanish wind and solar generation", "generation_group", "online", ["online", "tripped_928mw"], {"trip_928": _transitions(("online", "tripped_928mw"))}),
        _object("iberian_frequency", "Iberian system frequency", "system_state", "nominal", ["nominal", "falling", "collapsed", "stable_restored"], {"fall": _transitions(("nominal", "falling")), "collapse": _transitions(("falling", "collapsed")), "restore": _transitions(("collapsed", "stable_restored"))}),
        _object("system_defence", "Spanish and Portuguese system-defence plans", "protection_system", "standby", ["standby", "activated", "unable_to_arrest_cascade"], {"activate": _transitions(("standby", "activated")), "fail_to_arrest": _transitions(("activated", "unable_to_arrest_cascade"))}),
        _object("france_spain_interconnection", "France-Spain interconnections", "interconnection", "synchronized", ["synchronized", "ac_tripped", "fully_separated", "north_energized", "east_energized"], {"trip_ac": _transitions(("synchronized", "ac_tripped")), "trip_hvdc": _transitions(("ac_tripped", "fully_separated")), "energize_north": _transitions(("fully_separated", "north_energized")), "energize_east": _transitions(("north_energized", "east_energized"))}),
        _object("morocco_interconnection", "Spain-Morocco AC interconnection", "interconnection", "connected", ["connected", "underfrequency_tripped", "energized", "resynchronized"], {"trip_underfrequency": _transitions(("connected", "underfrequency_tripped")), "energize": _transitions(("underfrequency_tripped", "energized")), "resynchronize": _transitions(("energized", "resynchronized"))}),
        _object("iberian_system", "Spanish and Portuguese synchronous system", "power_system", "synchronized", ["synchronized", "losing_synchronism", "blackout", "stable_restoration"], {"lose_sync": _transitions(("synchronized", "losing_synchronism")), "collapse": _transitions(("losing_synchronism", "blackout")), "stabilize": _transitions(("blackout", "stable_restoration"))}),
        _object("portugal_grid", "Portuguese transmission grid", "power_system", "supplied", ["supplied", "blackout", "restored"], {"blackout": _transitions(("supplied", "blackout")), "restore": _transitions(("blackout", "restored"))}),
        _object("spain_grid", "Spanish transmission grid", "power_system", "supplied", ["supplied", "blackout", "zones_synchronized", "restored"], {"blackout": _transitions(("supplied", "blackout")), "synchronize_zones": _transitions(("blackout", "zones_synchronized")), "restore": _transitions(("zones_synchronized", "restored"))}),
        _object("black_start_islands", "Spanish and Portuguese black-start islands", "restoration_resource", "standby", ["standby", "built"], {"build": _transitions(("standby", "built"))}),
        _object("nuclear_auxiliaries", "Spanish nuclear-plant auxiliary supplies", "critical_load", "without_external_supply", ["without_external_supply", "externally_supplied"], {"supply": _transitions(("without_external_supply", "externally_supplied"))}),
        _object("spain_portugal_interconnection", "Aldeadavila-Pocinho Spain-Portugal interconnection", "interconnection", "deenergized", ["deenergized", "energized_continental_frequency"], {"energize": _transitions(("deenergized", "energized_continental_frequency"))}),
        _object("restoration", "Iberian system restoration", "response_process", "standby", ["standby", "active", "complete"], {"start": _transitions(("standby", "active")), "complete": _transitions(("active", "complete"))}),
    ],
    "situations": [
        {"id": "preincident_oscillations_damped", "all": [{"object": "oscillation_state", "state": "damped"}, {"object": "voltage_control", "state": "sensitive"}]},
        {"id": "generation_voltage_cascade", "all": [{"object": "spanish_generation", "state": "loss_above_2500mw"}, {"object": "voltage_control", "state": "runaway_rise"}]},
        {"id": "iberian_blackout", "all": [{"object": "iberian_system", "state": "blackout"}, {"object": "spain_grid", "state": "blackout"}, {"object": "portugal_grid", "state": "blackout"}]},
        {"id": "cross_border_restoration", "all": [{"object": "france_spain_interconnection", "state": "east_energized"}, {"object": "morocco_interconnection", "state": "resynchronized"}]},
        {"id": "iberian_stable_restoration", "all": [{"object": "iberian_system", "state": "stable_restoration"}, {"object": "spain_grid", "state": "restored"}, {"object": "portugal_grid", "state": "restored"}]},
    ],
    "processes": [
        _process("iberia_preincident_l1", "Iberian pre-incident oscillations L1", IBERIA_PREINCIDENT_STEPS),
        _process("iberia_cascade_l1", "Iberian voltage and synchronism cascade L1", IBERIA_CASCADE_STEPS),
        _process("iberia_restoration_l1", "Iberian cross-border and black-start restoration L1", IBERIA_RESTORATION_STEPS),
    ],
    "timeline": [
        _entry("local_oscillation_started", "2025-04-28T12:03:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="A converter-driven forced oscillation with dominant frequency 0.63 Hz began", action=_action("oscillation_state", "start_local", "local_0_63hz"), process=("iberia_preincident_l1", "start_local_oscillation"), metrics={"oscillation_frequency_hz": 0.63}),
        _entry("local_oscillation_damped", "2025-04-28T12:08:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="The local oscillatory episode ended after operational measures", action=_action("oscillation_state", "damp_local", "local_damped"), process=("iberia_preincident_l1", "damp_local_oscillation")),
        _entry("interarea_oscillation_started", "2025-04-28T12:19:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="A Continental Europe inter-area oscillation with dominant frequency 0.2 Hz began", action=_action("oscillation_state", "start_interarea", "interarea_0_2hz"), process=("iberia_preincident_l1", "start_interarea_oscillation"), metrics={"oscillation_frequency_hz": 0.2}),
        _entry("interarea_oscillation_damped", "2025-04-28T12:22:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Cross-border and internal measures damped the inter-area oscillation", action=_action("oscillation_state", "damp_interarea", "damped"), process=("iberia_preincident_l1", "damp_interarea_oscillation")),
        _entry("voltage_sensitive_state", "2025-04-28T12:24:00+02:00", entry_kind="derived", evidence="derived", fact="The damping measures and reactive-power configuration left the Spanish system voltage-sensitive", action=_action("voltage_control", "sensitize", "sensitive"), process=("iberia_preincident_l1", "enter_voltage_sensitive_state"), situations=["preincident_oscillations_damped"]),
        _entry("large_res_reduction", "2025-04-28T12:32:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Output from Spanish renewable units larger than 5 MW began falling by approximately 500 MW", action=_action("spanish_generation", "reduce_500", "reduced_500mw"), process=("iberia_cascade_l1", "reduce_large_res_output"), metrics={"large_res_output_reduction_mw": 500, "iberian_400kv_voltage_below_kv": 420}),
        _entry("distributed_generation_trip", "2025-04-28T12:32:57+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Identified distributed wind and solar units had reduced or tripped by 208 MW while distribution net load rose", action=_action("distributed_generation", "trip_208", "tripped_208mw"), process=("iberia_cascade_l1", "lose_distributed_generation"), metrics={"identified_distributed_generation_loss_mw": 208, "distribution_net_load_increase_mw": 317}),
        _entry("granada_transformer_trip", "2025-04-28T12:32:57.100+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="A Granada-area 400/220 kV transformer tripped on 220 kV overvoltage protection", action=_action("granada_transformer", "trip_overvoltage", "overvoltage_tripped"), process=("iberia_cascade_l1", "trip_granada_transformer"), metrics={"pretrip_active_power_mw": 355, "pretrip_reactive_absorption_mvar": 165, "pretrip_400kv_voltage_kv": 417.9}),
        _entry("badajoz_generation_trip", "2025-04-28T12:33:16.820+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Two Badajoz photovoltaic and solar-thermal sets tripped on overvoltage protection", action=_action("badajoz_generation", "trip_727", "tripped_727mw"), process=("iberia_cascade_l1", "trip_badajoz_generation"), metrics={"badajoz_generation_loss_mw": 727, "first_trip_estimated_voltage_kv": 432.4}),
        _entry("further_generation_trip", "2025-04-28T12:33:18.020+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="A further 928 MW of wind and solar generation tripped in six Spanish areas", action=_action("further_generation", "trip_928", "tripped_928mw"), process=("iberia_cascade_l1", "trip_further_generation"), metrics={"further_generation_loss_mw": 928, "affected_areas": 6}),
        _entry("cumulative_loss_above_2500", "2025-04-28T12:33:18.021+02:00", entry_kind="derived", evidence="derived", fact="Cumulative generation loss plus net-load increase exceeded 2.5 GW", action=_action("spanish_generation", "exceed_2500", "loss_above_2500mw"), process=("iberia_cascade_l1", "record_loss_above_2500"), metrics={"cumulative_loss_and_net_load_increase_mw_min": 2500}),
        _entry("sharp_voltage_rise", "2025-04-28T12:33:18.022+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Loss of generation and reactive-power absorption drove a sharp voltage rise in southern Spain and Portugal", action=_action("voltage_control", "runaway", "runaway_rise"), process=("iberia_cascade_l1", "runaway_voltage"), situations=["generation_voltage_cascade"]),
        _entry("frequency_decline", "2025-04-28T12:33:18.023+02:00", entry_kind="derived", evidence="derived", fact="The growing active-power imbalance caused Iberian frequency to fall", action=_action("iberian_frequency", "fall", "falling"), process=("iberia_cascade_l1", "fall_frequency")),
        _entry("defence_plans_activated", "2025-04-28T12:33:19+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Spanish and Portuguese defence plans automatically activated as designed", action=_action("system_defence", "activate", "activated"), process=("iberia_cascade_l1", "activate_defence")),
        _entry("defence_plans_ineffective", "2025-04-28T12:33:19.001+02:00", entry_kind="derived", evidence="derived", fact="Load shedding and pump disconnection could not interrupt the fast cascade", action=_action("system_defence", "fail_to_arrest", "unable_to_arrest_cascade"), process=("iberia_cascade_l1", "mark_defence_ineffective")),
        _entry("loss_of_synchronism", "2025-04-28T12:33:19.002+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="The Iberian system began losing synchronism with Continental Europe", action=_action("iberian_system", "lose_sync", "losing_synchronism"), process=("iberia_cascade_l1", "lose_synchronism")),
        _entry("morocco_ac_trip", "2025-04-28T12:33:20.473+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="The Morocco AC interconnection tripped on underfrequency", action=_action("morocco_interconnection", "trip_underfrequency", "underfrequency_tripped"), process=("iberia_cascade_l1", "trip_morocco_ac")),
        _entry("france_spain_ac_trip", "2025-04-28T12:33:21.535+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="France-Spain AC overhead lines disconnected on loss of synchronism and contained the disturbance", action=_action("france_spain_interconnection", "trip_ac", "ac_tripped"), process=("iberia_cascade_l1", "trip_france_spain_ac")),
        _entry("france_spain_hvdc_trip", "2025-04-28T12:33:23.960+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="The remaining HVDC links tripped and completed electrical separation of Iberia", action=_action("france_spain_interconnection", "trip_hvdc", "fully_separated"), process=("iberia_cascade_l1", "trip_france_spain_hvdc")),
        _entry("iberian_system_collapse", "2025-04-28T12:33:23.961+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="All system parameters of the Spanish and Portuguese systems collapsed", action=_action("iberian_system", "collapse", "blackout"), process=("iberia_cascade_l1", "collapse_iberian_system")),
        _entry("iberian_frequency_collapse", "2025-04-28T12:33:23.962+02:00", entry_kind="derived", evidence="derived", fact="Iberian frequency collapsed with the separated system", action=_action("iberian_frequency", "collapse", "collapsed"), process=("iberia_cascade_l1", "collapse_frequency")),
        _entry("portugal_blackout", "2025-04-28T12:33:23.963+02:00", entry_kind="derived", evidence="derived", fact="Portugal entered a transmission-system blackout", action=_action("portugal_grid", "blackout", "blackout"), process=("iberia_cascade_l1", "blackout_portugal")),
        _entry("spain_blackout", "2025-04-28T12:33:23.964+02:00", entry_kind="derived", evidence="derived", fact="Spain entered a transmission-system blackout", action=_action("spain_grid", "blackout", "blackout"), process=("iberia_cascade_l1", "blackout_spain"), situations=["iberian_blackout"], metrics={"incident_severity_scale": 3}),
        _entry("restoration_plans_activated", "2025-04-28T12:33:24+02:00", entry_kind="input", origin="planned_process_start", evidence="reported", source="entsoe_iberian_final_report", fact="Both affected TSOs immediately activated their system-restoration plans", action=_action("restoration", "start", "active"), process=("iberia_restoration_l1", "activate_restoration_plans")),
        _entry("france_north_energized", "2025-04-28T12:43:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="The 400 kV Argia-Hernani line was energized from France", action=_action("france_spain_interconnection", "energize_north", "north_energized"), process=("iberia_restoration_l1", "energize_france_north")),
        _entry("morocco_interconnection_energized", "2025-04-28T13:04:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="The Spain-Morocco interconnection was energized", action=_action("morocco_interconnection", "energize", "energized"), process=("iberia_restoration_l1", "energize_morocco")),
        _entry("france_east_energized", "2025-04-28T13:35:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="The 400 kV Baixas-Vic line was energized from France", action=_action("france_spain_interconnection", "energize_east", "east_energized"), process=("iberia_restoration_l1", "energize_france_east")),
        _entry("black_start_islands_built", "2025-04-28T14:22:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Successful bottom-up black-start islands complemented top-down restoration", action=_action("black_start_islands", "build", "built"), process=("iberia_restoration_l1", "build_black_start_islands")),
        _entry("morocco_resynchronized", "2025-04-28T14:34:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Synchronization with Morocco was repeated after the first energized path tripped", action=_action("morocco_interconnection", "resynchronize", "resynchronized"), process=("iberia_restoration_l1", "resynchronize_morocco"), situations=["cross_border_restoration"], metrics={"first_path_trip_time": "14:27"}),
        _entry("nuclear_auxiliaries_supplied", "2025-04-28T15:07:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="All Spanish nuclear plants confirmed external supply for auxiliary services", action=_action("nuclear_auxiliaries", "supply", "externally_supplied"), process=("iberia_restoration_l1", "supply_nuclear_auxiliaries")),
        _entry("spain_portugal_interconnector_energized", "2025-04-28T18:36:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Aldeadavila-Pocinho was energized and Portugal again received continental-frequency voltage", action=_action("spain_portugal_interconnection", "energize", "energized_continental_frequency"), process=("iberia_restoration_l1", "energize_spain_portugal")),
        _entry("spanish_zones_synchronized", "2025-04-28T19:32:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="The southern Morocco-connected zone synchronized with the northern Continental Europe-connected zone", action=_action("spain_grid", "synchronize_zones", "zones_synchronized"), process=("iberia_restoration_l1", "synchronize_spanish_zones")),
        _entry("portugal_grid_restored", "2025-04-29T00:22:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Restoration of the Portuguese transmission grid was completed", action=_action("portugal_grid", "restore", "restored"), process=("iberia_restoration_l1", "restore_portugal"), metrics={"portugal_restoration_hours": 12}),
        _entry("spain_grid_restored", "2025-04-29T04:00:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_iberian_final_report", fact="Restoration of the Spanish transmission grid was completed", action=_action("spain_grid", "restore", "restored"), process=("iberia_restoration_l1", "restore_spain"), metrics={"spain_restoration_hours": 16}),
        _entry("voltage_control_restored", "2025-04-29T04:00:00.001+02:00", entry_kind="derived", evidence="derived", fact="Voltage control returned to stable operation", action=_action("voltage_control", "restore", "stable_restored"), process=("iberia_restoration_l1", "restore_voltage")),
        _entry("frequency_restored", "2025-04-29T04:00:00.002+02:00", entry_kind="derived", evidence="derived", fact="Iberian frequency returned to stable operation", action=_action("iberian_frequency", "restore", "stable_restored"), process=("iberia_restoration_l1", "restore_frequency")),
        _entry("iberian_system_stable", "2025-04-29T04:00:00.003+02:00", entry_kind="derived", evidence="derived", fact="Spain and Portugal reached the L1 stable-restoration boundary", action=_action("iberian_system", "stabilize", "stable_restoration"), process=("iberia_restoration_l1", "stabilize_iberian_system"), situations=["iberian_stable_restoration"]),
        _entry("iberian_restoration_complete", "2025-04-29T04:00:00.004+02:00", entry_kind="derived", evidence="derived", fact="The Iberian L1 restoration process completed", action=_action("restoration", "complete", "complete"), process=("iberia_restoration_l1", "complete_restoration"), metrics={"restoration_percent": 100}),
    ],
    "checkpoints": [
        {"id": "oscillations_063_and_02", "after": "voltage_sensitive_state", "all": [{"object": "oscillation_state", "state": "damped"}, {"metric": "oscillation_frequency_hz", "equals": 0.2}]},
        {"id": "generation_loss_above_2500mw", "after": "sharp_voltage_rise", "all": [{"object": "voltage_control", "state": "runaway_rise"}, {"metric": "cumulative_loss_and_net_load_increase_mw_min", "equals": 2500}]},
        {"id": "electrical_separation_123323960", "after": "spain_blackout", "all": [{"object": "france_spain_interconnection", "state": "fully_separated"}, {"object": "iberian_system", "state": "blackout"}, {"metric": "incident_severity_scale", "equals": 3}]},
        {"id": "portugal_restored_12h", "after": "portugal_grid_restored", "all": [{"object": "portugal_grid", "state": "restored"}, {"metric": "portugal_restoration_hours", "equals": 12}]},
        {"id": "spain_restored_16h", "after": "iberian_restoration_complete", "all": [{"object": "spain_grid", "state": "restored"}, {"object": "iberian_system", "state": "stable_restoration"}, {"metric": "spain_restoration_hours", "equals": 16}, {"metric": "restoration_percent", "equals": 100}]},
    ],
    "expected_final": {
        "object_states": {"oscillation_state": "damped", "voltage_control": "stable_restored", "spanish_generation": "loss_above_2500mw", "distributed_generation": "tripped_208mw", "granada_transformer": "overvoltage_tripped", "badajoz_generation": "tripped_727mw", "further_generation": "tripped_928mw", "iberian_frequency": "stable_restored", "system_defence": "unable_to_arrest_cascade", "france_spain_interconnection": "east_energized", "morocco_interconnection": "resynchronized", "iberian_system": "stable_restoration", "portugal_grid": "restored", "spain_grid": "restored", "black_start_islands": "built", "nuclear_auxiliaries": "externally_supplied", "spain_portugal_interconnection": "energized_continental_frequency", "restoration": "complete"},
        "situations": ["preincident_oscillations_damped", "generation_voltage_cascade", "iberian_blackout", "cross_border_restoration", "iberian_stable_restoration"],
    },
}


_bind_event_model_objects(IBERIA_2025)


NORTH_HYDE_FAILURE_STEPS = [
    _step("fail_sgt3_bushing", "Fail the C-phase high-voltage bushing on SGT3", target="sgt3_bushing", capability="short_circuit"),
    _step("isolate_sgt3", "Operate SGT3 protection and isolate the transformer", after=["fail_sgt3_bushing"], target="sgt3", capability="isolate"),
    _step("connect_sgt2", "Automatically connect hot-standby SGT2", after=["isolate_sgt3"], target="sgt2", capability="connect"),
    _step("ignite_sgt3_fire", "Record the major fire on SGT3", after=["connect_sgt2"], target="sgt3", capability="ignite"),
    _step("damage_sgt1", "Damage SGT1 through heat and fire spread", after=["ignite_sgt3_fire"], target="sgt1", capability="damage"),
    _step("trip_sgt1", "Operate SGT1 protection", after=["damage_sgt1"], target="sgt1", capability="trip"),
    _step("disconnect_sgt2", "Lose SGT2's shared transmission connection", after=["trip_sgt1"], target="sgt2", capability="disconnect"),
    _step("blackout_north_hyde", "Lose all supplies at North Hyde 275, 66 and 22 kV", after=["disconnect_sgt2"], target="north_hyde_supply", capability="blackout"),
    _step("interrupt_customers", "Interrupt directly and indirectly supplied customers", after=["blackout_north_hyde"], target="customer_supply", capability="interrupt"),
    _step("lose_heathrow_a", "Lose Heathrow Substation A", after=["interrupt_customers"], target="heathrow_substation_a", capability="lose_supply"),
    _step("start_airfield_generators", "Automatically start airfield-ring generators", after=["lose_heathrow_a"], target="heathrow_safety_supply", capability="start_backup"),
]

NORTH_HYDE_FIRE_RESPONSE_STEPS = [
    _step("receive_fire_call", "Receive the first fire call", target="fire_response", capability="receive_call"),
    _step("deploy_fire_appliances", "Deploy ten fire appliances", after=["receive_fire_call"], target="fire_response", capability="deploy"),
    _step("confirm_site_off_supply", "Confirm the substation site is off supply", after=["deploy_fire_appliances"], target="fire_response", capability="confirm_isolation"),
    _step("declare_major_incident", "Declare a major incident", after=["confirm_site_off_supply"], target="fire_response", capability="declare_major"),
    _step("permit_site_entry", "Issue electrical-safety permits for site entry", after=["declare_major_incident"], target="fire_response", capability="permit_entry"),
    _step("stop_firefighting", "Confirm cessation of firefighting", after=["permit_site_entry"], target="fire_response", capability="stop"),
]

NORTH_HYDE_CUSTOMER_RESTORATION_STEPS = [
    _step("start_distribution_switching", "Start customer restoration through unaffected substations", target="restoration", capability="start"),
    _step("restore_22kv", "Return power to North Hyde 22 kV", after=["start_distribution_switching"], target="north_hyde_supply", capability="restore_22kv"),
    _step("restore_42000", "Restore approximately 42,000 customers", after=["restore_22kv"], target="customer_supply", capability="restore_42000"),
    _step("reach_interconnector_capacity", "Reach available distribution-interconnector capacity", after=["restore_42000"], target="customer_supply", capability="reach_4868"),
    _step("restore_62000", "Restore more than 62,000 customers", after=["reach_interconnector_capacity"], target="customer_supply", capability="restore_62000"),
    _step("restore_66kv_from_iver", "Re-energize North Hyde 66 kV from Iver", after=["restore_62000"], target="north_hyde_supply", capability="restore_66kv"),
    _step("restore_all_but_two", "Restore all directly supplied customers except two on backup", after=["restore_66kv_from_iver"], target="customer_supply", capability="restore_all_but_two"),
    _step("energize_sgt2", "Energize SGT2 from the transmission system", after=["restore_all_but_two"], target="sgt2", capability="energize"),
    _step("supply_66kv_from_sgt2", "Supply North Hyde 66 kV from SGT2", after=["energize_sgt2"], target="sgt2", capability="supply_66kv"),
    _step("switch_to_sgt2_supply", "Switch the North Hyde 66 kV bars to SGT2", after=["supply_66kv_from_sgt2"], target="north_hyde_supply", capability="switch_to_sgt2"),
    _step("reinforce_iver_support", "Return Iver SGT4A and SGT4B and reinforce two 66 kV paths", after=["switch_to_sgt2_supply"], target="north_hyde_supply", capability="reinforce"),
    _step("complete_restoration", "Complete the North Hyde L1 restoration process", after=["reinforce_iver_support"], target="restoration", capability="complete"),
]

NORTH_HYDE_HEATHROW_STEPS = [
    _step("close_airport", "Decide to close Heathrow Airport", target="airport_operation", capability="close"),
    _step("start_internal_reconfiguration", "Start reconfiguration from Heathrow's other two supply points", after=["close_airport"], target="airport_operation", capability="reconfigure"),
    _step("restore_primary_substations", "Re-energize all affected primary 33 kV substations", after=["start_internal_reconfiguration"], target="airport_operation", capability="restore_primary"),
    _step("restore_terminals", "Restore power to all terminals", after=["restore_primary_substations"], target="airport_operation", capability="restore_terminals"),
    _step("restore_internal_network", "Complete re-energization of the wider airport network", after=["restore_terminals"], target="airport_operation", capability="restore_network"),
    _step("operate_limited_flights", "Reopen for repositioning and repatriation flights", after=["restore_internal_network"], target="airport_operation", capability="partial_open"),
    _step("return_normal_operation", "Return Heathrow to business-as-usual operation", after=["operate_limited_flights"], target="airport_operation", capability="normalize"),
]

NORTH_HYDE_2025 = {
    "schema_version": 2,
    "id": "north-hyde-outage-2025-l1",
    "scenario_id": "north-hyde-2025",
    "name": "North Hyde Substation Outage, 2025 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "neso_north_hyde_final",
            "url": "https://www.neso.energy/document/363891/download",
            "scope": "root cause, transformer sequence, fire response, customer and transmission restoration, Heathrow impacts",
            "priority": "final_primary_system_operator_review",
        },
        {
            "id": "neso_north_hyde_release",
            "url": "https://www.neso.energy/news/final-report-review-north-hyde-substation-outage",
            "scope": "official report provenance, consolidated impacts and final conclusions",
            "priority": "official_system_operator_release",
        },
    ],
    "model": {
        "id": "qualification-north-hyde-2025",
        "name": "North Hyde outage 20–21 March 2025 · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Causal asset, supply, customer, airport-continuity and restoration topology based on the NESO final review; it is not a geographic network diagram.",
        "event_targets": {
            "substation_fault": "nh-sgt3-bushing",
            "fire_spread": "nh-sgt1",
            "repair": "nh-sgt3-bushing",
        },
        "nodes": [
            {"id": "nh-transmission-grid", "name": "National transmission system · 275 kV infeed", "component_type_id": "external-grid", "x": 40, "y": 180},
            {"id": "nh-275kv-bus", "name": "North Hyde 275 kV busbars", "component_type_id": "grid-zone", "x": 260, "y": 180},
            {"id": "nh-sgt3-bushing", "name": "SGT3 C-phase high-voltage bushing", "component_type_id": "transformer-bushing", "x": 480, "y": 40, "parameters": {"protection_isolation_ms": 110, "elevated_moisture_sample_year": 2018, "affected_customers": 71655}, "qualification_object_id": "sgt3_bushing"},
            {"id": "nh-sgt3", "name": "Supergrid transformer SGT3", "component_type_id": "transformer-group", "x": 700, "y": 40, "qualification_object_id": "sgt3"},
            {"id": "nh-shared-sgt1-sgt2-circuit", "name": "Shared SGT1 / SGT2 transmission circuit", "component_type_id": "transmission-corridor", "x": 480, "y": 220, "parameters": {"shared_connection": True}},
            {"id": "nh-sgt1", "name": "Supergrid transformer SGT1", "component_type_id": "transformer-group", "x": 700, "y": 180, "parameters": {"fire_spread_trip_delay_minutes": 28}, "qualification_object_id": "sgt1"},
            {"id": "nh-sgt2", "name": "Hot-standby supergrid transformer SGT2", "component_type_id": "transformer-group", "x": 700, "y": 320, "parameters": {"initial_operating_state": "hot_standby"}, "qualification_object_id": "sgt2"},
            {"id": "nh-supply", "name": "North Hyde 275 / 66 / 22 kV supply", "component_type_id": "grid-zone", "x": 920, "y": 180, "parameters": {"affected_customers": 71655, "ssen_direct_customers": 66919, "idno_customers": 4736}, "qualification_object_id": "north_hyde_supply"},
            {"id": "nh-customer-supply", "name": "North Hyde supplied domestic and commercial customers", "component_type_id": "customer-group", "x": 1140, "y": 40, "parameters": {"affected_customers": 71655, "ssen_direct_customers": 66919, "idno_customers": 4736, "restored_within_58_minutes": 42000}, "qualification_object_id": "customer_supply"},
            {"id": "nh-heathrow-a", "name": "Heathrow Substation A", "component_type_id": "transformer-group", "x": 1140, "y": 180, "qualification_object_id": "heathrow_substation_a"},
            {"id": "nh-airport-operation", "name": "Heathrow Airport operational systems", "component_type_id": "customer-group", "x": 1360, "y": 180, "qualification_object_id": "airport_operation"},
            {"id": "nh-airfield-generators", "name": "Heathrow airfield-ring safety generators", "component_type_id": "distributed-generation", "x": 1140, "y": 340, "parameters": {"capacity_evidence": "not_reported"}, "initial_online": False, "qualification_object_id": "heathrow_safety_supply"},
            {"id": "nh-iver-grid", "name": "Iver-area unaffected distribution supply", "component_type_id": "external-grid", "x": 480, "y": 520},
            {"id": "nh-iver-66kv-interconnector", "name": "Iver–North Hyde 66 kV interconnection", "component_type_id": "transmission-corridor", "x": 700, "y": 520, "parameters": {"restoration_role": "reenergize_66kv"}},
            {"id": "nh-fire-hazard", "name": "SGT3 fire and heat spread", "component_type_id": "external-hazard", "x": 700, "y": 680},
            {"id": "nh-fire-response", "name": "London Fire Brigade and site-safety response", "component_type_id": "response-process", "x": 920, "y": 680, "parameters": {"fire_appliances_total": 10}, "qualification_object_id": "fire_response"},
            {"id": "nh-restoration", "name": "Multi-party electrical and airport restoration", "component_type_id": "response-process", "x": 1140, "y": 520, "qualification_object_id": "restoration"},
        ],
        "edges": [
            {"id": "nh-edge-grid-275", "source": "nh-transmission-grid", "target": "nh-275kv-bus"},
            {"id": "nh-edge-275-bushing", "source": "nh-275kv-bus", "target": "nh-sgt3-bushing"},
            {"id": "nh-edge-bushing-sgt3", "source": "nh-sgt3-bushing", "target": "nh-sgt3"},
            {"id": "nh-edge-sgt3-supply", "source": "nh-sgt3", "target": "nh-supply"},
            {"id": "nh-edge-275-shared", "source": "nh-275kv-bus", "target": "nh-shared-sgt1-sgt2-circuit"},
            {"id": "nh-edge-shared-sgt1", "source": "nh-shared-sgt1-sgt2-circuit", "target": "nh-sgt1"},
            {"id": "nh-edge-shared-sgt2", "source": "nh-shared-sgt1-sgt2-circuit", "target": "nh-sgt2"},
            {"id": "nh-edge-sgt1-supply", "source": "nh-sgt1", "target": "nh-supply"},
            {"id": "nh-edge-sgt2-supply", "source": "nh-sgt2", "target": "nh-supply"},
            {"id": "nh-edge-supply-customers", "source": "nh-supply", "target": "nh-customer-supply"},
            {"id": "nh-edge-supply-heathrow-a", "source": "nh-supply", "target": "nh-heathrow-a"},
            {"id": "nh-edge-heathrow-a-airport", "source": "nh-heathrow-a", "target": "nh-airport-operation"},
            {"id": "nh-edge-safety-airport", "source": "nh-airfield-generators", "target": "nh-airport-operation"},
            {"id": "nh-edge-iver-interconnector", "source": "nh-iver-grid", "target": "nh-iver-66kv-interconnector"},
            {"id": "nh-edge-iver-supply", "source": "nh-iver-66kv-interconnector", "target": "nh-supply"},
        ],
    },
    "objects": [
        _object("sgt3_bushing", "SGT3 C-phase high-voltage bushing", "transformer_bushing", "elevated_moisture_unaddressed", ["elevated_moisture_unaddressed", "short_circuit_failed"], {"short_circuit": _transitions(("elevated_moisture_unaddressed", "short_circuit_failed"))}),
        _object("sgt3", "North Hyde supergrid transformer SGT3", "transformer", "in_service", ["in_service", "protection_isolated", "major_fire"], {"isolate": _transitions(("in_service", "protection_isolated")), "ignite": _transitions(("protection_isolated", "major_fire"))}),
        _object("sgt2", "North Hyde supergrid transformer SGT2", "transformer", "hot_standby", ["hot_standby", "automatically_on_load", "disconnected", "energized", "supplying_66kv"], {"connect": _transitions(("hot_standby", "automatically_on_load")), "disconnect": _transitions(("automatically_on_load", "disconnected")), "energize": _transitions(("disconnected", "energized")), "supply_66kv": _transitions(("energized", "supplying_66kv"))}),
        _object("sgt1", "North Hyde supergrid transformer SGT1", "transformer", "in_service", ["in_service", "fire_damaged", "protection_tripped"], {"damage": _transitions(("in_service", "fire_damaged")), "trip": _transitions(("fire_damaged", "protection_tripped"))}),
        _object("north_hyde_supply", "North Hyde 275/66/22 kV supply", "substation_system", "supplied", ["supplied", "blackout", "22kv_restored", "66kv_iver_restored", "sgt2_66kv_supply", "reinforced_iver_support"], {"blackout": _transitions(("supplied", "blackout")), "restore_22kv": _transitions(("blackout", "22kv_restored")), "restore_66kv": _transitions(("22kv_restored", "66kv_iver_restored")), "switch_to_sgt2": _transitions(("66kv_iver_restored", "sgt2_66kv_supply")), "reinforce": _transitions(("sgt2_66kv_supply", "reinforced_iver_support"))}),
        _object("customer_supply", "North Hyde supplied customers", "customer_group", "supplied", ["supplied", "outage_71655", "restored_42000", "4868_ssend_remaining", "restored_over_62000", "all_but_two_backup"], {"interrupt": _transitions(("supplied", "outage_71655")), "restore_42000": _transitions(("outage_71655", "restored_42000")), "reach_4868": _transitions(("restored_42000", "4868_ssend_remaining")), "restore_62000": _transitions(("4868_ssend_remaining", "restored_over_62000")), "restore_all_but_two": _transitions(("restored_over_62000", "all_but_two_backup"))}),
        _object("heathrow_substation_a", "Heathrow Substation A", "customer_supply_point", "supplied", ["supplied", "lost_supply"], {"lose_supply": _transitions(("supplied", "lost_supply"))}),
        _object("heathrow_safety_supply", "Heathrow airfield safety supply", "backup_system", "normal_grid_supply", ["normal_grid_supply", "airfield_generators_running"], {"start_backup": _transitions(("normal_grid_supply", "airfield_generators_running"))}),
        _object("airport_operation", "Heathrow Airport operation", "critical_infrastructure", "normal", ["normal", "closure_decided", "reconfiguring", "primary_33kv_restored", "terminals_power_restored", "internal_network_restored", "limited_flights", "business_as_usual"], {"close": _transitions(("normal", "closure_decided")), "reconfigure": _transitions(("closure_decided", "reconfiguring")), "restore_primary": _transitions(("reconfiguring", "primary_33kv_restored")), "restore_terminals": _transitions(("primary_33kv_restored", "terminals_power_restored")), "restore_network": _transitions(("terminals_power_restored", "internal_network_restored")), "partial_open": _transitions(("internal_network_restored", "limited_flights")), "normalize": _transitions(("limited_flights", "business_as_usual"))}),
        _object("fire_response", "North Hyde fire response", "emergency_response", "standby", ["standby", "call_received", "ten_appliances_deployed", "site_isolation_confirmed", "major_incident", "entry_permitted", "firefighting_stopped"], {"receive_call": _transitions(("standby", "call_received")), "deploy": _transitions(("call_received", "ten_appliances_deployed")), "confirm_isolation": _transitions(("ten_appliances_deployed", "site_isolation_confirmed")), "declare_major": _transitions(("site_isolation_confirmed", "major_incident")), "permit_entry": _transitions(("major_incident", "entry_permitted")), "stop": _transitions(("entry_permitted", "firefighting_stopped"))}),
        _object("restoration", "North Hyde multi-party restoration", "response_process", "standby", ["standby", "distribution_switching", "complete"], {"start": _transitions(("standby", "distribution_switching")), "complete": _transitions(("distribution_switching", "complete"))}),
    ],
    "situations": [
        {"id": "sgt3_protected_fire", "all": [{"object": "sgt3_bushing", "state": "short_circuit_failed"}, {"object": "sgt3", "state": "major_fire"}]},
        {"id": "north_hyde_total_outage", "all": [{"object": "north_hyde_supply", "state": "blackout"}, {"object": "customer_supply", "state": "outage_71655"}]},
        {"id": "heathrow_critical_continuity", "all": [{"object": "heathrow_substation_a", "state": "lost_supply"}, {"object": "heathrow_safety_supply", "state": "airfield_generators_running"}]},
        {"id": "customer_supply_substantially_restored", "all": [{"object": "customer_supply", "state": "all_but_two_backup"}, {"object": "north_hyde_supply", "state": "66kv_iver_restored"}]},
        {"id": "north_hyde_stable_restoration", "all": [{"object": "north_hyde_supply", "state": "reinforced_iver_support"}, {"object": "airport_operation", "state": "business_as_usual"}, {"object": "restoration", "state": "complete"}]},
    ],
    "processes": [
        _process("north_hyde_failure_l1", "North Hyde transformer and supply-loss sequence L1", NORTH_HYDE_FAILURE_STEPS),
        _process("north_hyde_fire_response_l1", "North Hyde fire and site-safety response L1", NORTH_HYDE_FIRE_RESPONSE_STEPS),
        _process("north_hyde_customer_restoration_l1", "North Hyde customer and grid restoration L1", NORTH_HYDE_CUSTOMER_RESTORATION_STEPS),
        _process("north_hyde_heathrow_l1", "Heathrow internal continuity and reopening L1", NORTH_HYDE_HEATHROW_STEPS),
    ],
    "timeline": [
        _entry("sgt3_bushing_short_circuit", "2025-03-20T23:21:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Moisture ingress most likely caused electrical arcing and a C-phase high-voltage bushing short circuit", action=_action("sgt3_bushing", "short_circuit", "short_circuit_failed"), process=("north_hyde_failure_l1", "fail_sgt3_bushing"), metrics={"elevated_moisture_sample_year": 2018}),
        _entry("sgt3_protection_isolated", "2025-03-20T23:21:00.110+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Protection operated as expected and isolated SGT3 from the network", action=_action("sgt3", "isolate", "protection_isolated"), process=("north_hyde_failure_l1", "isolate_sgt3"), metrics={"protection_isolation_ms": 110}),
        _entry("sgt2_automatically_connected", "2025-03-20T23:21:00.111+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Hot-standby SGT2 automatically connected to the SGT1 circuit and maintained two-transformer supply", action=_action("sgt2", "connect", "automatically_on_load"), process=("north_hyde_failure_l1", "connect_sgt2")),
        _entry("sgt3_major_fire", "2025-03-20T23:21:00.112+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="The catastrophic bushing failure ignited a major fire on SGT3", action=_action("sgt3", "ignite", "major_fire"), process=("north_hyde_failure_l1", "ignite_sgt3_fire"), situations=["sgt3_protected_fire"]),
        _entry("first_fire_call", "2025-03-20T23:22:00+00:00", entry_kind="input", origin="external_event", evidence="reported", source="neso_north_hyde_final", fact="London Fire Brigade received the first call about the fire", action=_action("fire_response", "receive_call", "call_received"), process=("north_hyde_fire_response_l1", "receive_fire_call")),
        _entry("ten_fire_appliances_requested", "2025-03-20T23:28:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="The first appliance arrived and nine additional appliances were requested over the following 30 minutes", action=_action("fire_response", "deploy", "ten_appliances_deployed"), process=("north_hyde_fire_response_l1", "deploy_fire_appliances"), metrics={"fire_appliances_total": 10}),
        _entry("sgt1_fire_damage", "2025-03-20T23:48:59.999+00:00", entry_kind="derived", evidence="derived", fact="Heat and fire from SGT3 damaged an SGT1 high-voltage bushing and marshalling kiosk", action=_action("sgt1", "damage", "fire_damaged"), process=("north_hyde_failure_l1", "damage_sgt1")),
        _entry("sgt1_protection_trip", "2025-03-20T23:49:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="SGT1 protection operated 28 minutes after SGT3 tripped", action=_action("sgt1", "trip", "protection_tripped"), process=("north_hyde_failure_l1", "trip_sgt1"), metrics={"fire_spread_trip_delay_minutes": 28}),
        _entry("sgt2_connection_lost", "2025-03-20T23:49:00.001+00:00", entry_kind="derived", evidence="derived", fact="SGT2 lost its direct transmission connection because it shared the SGT1 circuit", action=_action("sgt2", "disconnect", "disconnected"), process=("north_hyde_failure_l1", "disconnect_sgt2")),
        _entry("north_hyde_blackout", "2025-03-20T23:49:00.002+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="North Hyde 275, 66 and 22 kV substations lost all supplies", action=_action("north_hyde_supply", "blackout", "blackout"), process=("north_hyde_failure_l1", "blackout_north_hyde")),
        _entry("customer_outage_71655", "2025-03-20T23:49:00.003+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="66,919 SSEN Distribution and 4,736 IDNO customers lost power", action=_action("customer_supply", "interrupt", "outage_71655"), process=("north_hyde_failure_l1", "interrupt_customers"), situations=["north_hyde_total_outage"], metrics={"ssen_direct_customers_interrupted": 66919, "idno_customers_interrupted": 4736, "total_customers_interrupted": 71655}),
        _entry("heathrow_a_supply_lost", "2025-03-20T23:49:00.004+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Heathrow Substation A lost supply, interrupting terminals and shared operational systems", action=_action("heathrow_substation_a", "lose_supply", "lost_supply"), process=("north_hyde_failure_l1", "lose_heathrow_a")),
        _entry("airfield_generators_started", "2025-03-20T23:49:00.005+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Airfield-ring generators automatically maintained runways and essential safety systems", action=_action("heathrow_safety_supply", "start_backup", "airfield_generators_running"), process=("north_hyde_failure_l1", "start_airfield_generators"), situations=["heathrow_critical_continuity"]),
        _entry("distribution_restoration_started", "2025-03-21T00:06:00+00:00", entry_kind="input", origin="planned_process_start", evidence="reported", source="neso_north_hyde_final", fact="SSEN Distribution began restoration through interconnections with unaffected substations", action=_action("restoration", "start", "distribution_switching"), process=("north_hyde_customer_restoration_l1", "start_distribution_switching")),
        _entry("site_isolation_confirmed", "2025-03-21T00:11:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="The standby engineer confirmed the site was off supply while firefighters contained the fire from the perimeter", action=_action("fire_response", "confirm_isolation", "site_isolation_confirmed"), process=("north_hyde_fire_response_l1", "confirm_site_off_supply")),
        _entry("north_hyde_22kv_restored", "2025-03-21T00:39:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Power returned to North Hyde 22 kV substation", action=_action("north_hyde_supply", "restore_22kv", "22kv_restored"), process=("north_hyde_customer_restoration_l1", "restore_22kv")),
        _entry("major_incident_declared", "2025-03-21T00:42:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="The Metropolitan Police Service declared a major incident", action=_action("fire_response", "declare_major", "major_incident"), process=("north_hyde_fire_response_l1", "declare_major_incident")),
        _entry("customers_42000_restored", "2025-03-21T00:47:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Approximately 42,000 customers had been restored using 22 and 11 kV interconnections", action=_action("customer_supply", "restore_42000", "restored_42000"), process=("north_hyde_customer_restoration_l1", "restore_42000"), metrics={"customers_restored": 42000, "restoration_elapsed_minutes": 58}),
        _entry("airport_closure_decided", "2025-03-21T01:11:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Heathrow Airport Limited decided to close the airport", action=_action("airport_operation", "close", "closure_decided"), process=("north_hyde_heathrow_l1", "close_airport")),
        _entry("airport_reconfiguration_started", "2025-03-21T02:00:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Airport engineers began re-energizing affected systems from the other two intake substations", action=_action("airport_operation", "reconfigure", "reconfiguring"), process=("north_hyde_heathrow_l1", "start_internal_reconfiguration"), metrics={"planned_reconfiguration_hours_min": 10, "planned_reconfiguration_hours_max": 12}),
        _entry("distribution_capacity_reached", "2025-03-21T04:00:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Available distribution-interconnector capacity was fully utilized with 4,868 direct customers still off supply", action=_action("customer_supply", "reach_4868", "4868_ssend_remaining"), process=("north_hyde_customer_restoration_l1", "reach_interconnector_capacity"), metrics={"ssen_customers_remaining": 4868}),
        _entry("site_entry_permitted", "2025-03-21T06:00:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Electrical-safety permits allowed London Fire Brigade to enter the site", action=_action("fire_response", "permit_entry", "entry_permitted"), process=("north_hyde_fire_response_l1", "permit_site_entry")),
        _entry("airport_primary_33kv_restored", "2025-03-21T06:25:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="All affected Heathrow primary 33 kV substations were re-energized", action=_action("airport_operation", "restore_primary", "primary_33kv_restored"), process=("north_hyde_heathrow_l1", "restore_primary_substations")),
        _entry("customers_over_62000_restored", "2025-03-21T08:30:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="More than 62,000 direct customers had been restored", action=_action("customer_supply", "restore_62000", "restored_over_62000"), process=("north_hyde_customer_restoration_l1", "restore_62000"), metrics={"customers_restored_min": 62000}),
        _entry("north_hyde_66kv_restored", "2025-03-21T09:49:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="North Hyde 66 kV busbars were re-energized through the Iver 66 kV interconnection", action=_action("north_hyde_supply", "restore_66kv", "66kv_iver_restored"), process=("north_hyde_customer_restoration_l1", "restore_66kv_from_iver")),
        _entry("airport_terminals_restored", "2025-03-21T10:56:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Power was confirmed restored to all Heathrow terminals", action=_action("airport_operation", "restore_terminals", "terminals_power_restored"), process=("north_hyde_heathrow_l1", "restore_terminals")),
        _entry("all_but_two_customers_restored", "2025-03-21T12:24:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="All except two of 66,919 direct customers had supply; the remaining two used backup generation", action=_action("customer_supply", "restore_all_but_two", "all_but_two_backup"), process=("north_hyde_customer_restoration_l1", "restore_all_but_two"), situations=["customer_supply_substantially_restored"], metrics={"direct_customers_on_backup": 2}),
        _entry("airport_internal_network_restored", "2025-03-21T14:23:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Re-energization of Heathrow's wider internal network was completed", action=_action("airport_operation", "restore_network", "internal_network_restored"), process=("north_hyde_heathrow_l1", "restore_internal_network")),
        _entry("limited_flights_reopened", "2025-03-21T23:59:59.998+00:00", entry_kind="derived", evidence="derived", fact="Following safety checks, Heathrow reopened late on 21 March for repositioning and repatriation flights", action=_action("airport_operation", "partial_open", "limited_flights"), process=("north_hyde_heathrow_l1", "operate_limited_flights")),
        _entry("heathrow_business_as_usual", "2025-03-22T00:00:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_release", fact="Heathrow returned to business-as-usual operation on 22 March", action=_action("airport_operation", "normalize", "business_as_usual"), process=("north_hyde_heathrow_l1", "return_normal_operation")),
        _entry("sgt2_energized", "2025-03-22T00:55:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="SGT2 was energized and connected to the wider transmission system", action=_action("sgt2", "energize", "energized"), process=("north_hyde_customer_restoration_l1", "energize_sgt2")),
        _entry("sgt2_supplies_66kv", "2025-03-22T02:22:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="SGT2 was put on load to supply the North Hyde 66 kV bars", action=_action("sgt2", "supply_66kv", "supplying_66kv"), process=("north_hyde_customer_restoration_l1", "supply_66kv_from_sgt2")),
        _entry("north_hyde_switched_to_sgt2", "2025-03-22T02:22:00.001+00:00", entry_kind="derived", evidence="derived", fact="North Hyde 66 kV was switched to the SGT2 transmission supply", action=_action("north_hyde_supply", "switch_to_sgt2", "sgt2_66kv_supply"), process=("north_hyde_customer_restoration_l1", "switch_to_sgt2_supply")),
        _entry("iver_support_reinforced", "2025-03-22T19:22:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="Iver SGT4A and SGT4B returned, allowing two 66 kV circuits from Iver to support North Hyde", action=_action("north_hyde_supply", "reinforce", "reinforced_iver_support"), process=("north_hyde_customer_restoration_l1", "reinforce_iver_support")),
        _entry("north_hyde_restoration_complete", "2025-03-22T19:22:00.001+00:00", entry_kind="derived", evidence="derived", fact="North Hyde reached the L1 stable-restoration boundary", action=_action("restoration", "complete", "complete"), process=("north_hyde_customer_restoration_l1", "complete_restoration"), situations=["north_hyde_stable_restoration"], metrics={"restoration_stable": 1}),
        _entry("firefighting_stopped", "2025-03-26T17:13:00+00:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="neso_north_hyde_final", fact="London Fire Brigade issued the stop message confirming cessation of firefighting", action=_action("fire_response", "stop", "firefighting_stopped"), process=("north_hyde_fire_response_l1", "stop_firefighting"), metrics={"fire_response_days": 5, "fire_response_hours_additional": 18}),
    ],
    "checkpoints": [
        {"id": "sgt3_isolated_110ms", "after": "sgt3_major_fire", "all": [{"object": "sgt3", "state": "major_fire"}, {"metric": "protection_isolation_ms", "equals": 110}]},
        {"id": "total_outage_71655", "after": "airfield_generators_started", "all": [{"object": "north_hyde_supply", "state": "blackout"}, {"metric": "total_customers_interrupted", "equals": 71655}]},
        {"id": "restore_42000_within_hour", "after": "customers_42000_restored", "all": [{"object": "customer_supply", "state": "restored_42000"}, {"metric": "customers_restored", "equals": 42000}, {"metric": "restoration_elapsed_minutes", "equals": 58}]},
        {"id": "all_but_two_1224", "after": "all_but_two_customers_restored", "all": [{"object": "customer_supply", "state": "all_but_two_backup"}, {"metric": "direct_customers_on_backup", "equals": 2}]},
        {"id": "stable_multi_path_restoration", "after": "firefighting_stopped", "all": [{"object": "north_hyde_supply", "state": "reinforced_iver_support"}, {"object": "airport_operation", "state": "business_as_usual"}, {"object": "fire_response", "state": "firefighting_stopped"}, {"metric": "restoration_stable", "equals": 1}]},
    ],
    "expected_final": {
        "object_states": {"sgt3_bushing": "short_circuit_failed", "sgt3": "major_fire", "sgt2": "supplying_66kv", "sgt1": "protection_tripped", "north_hyde_supply": "reinforced_iver_support", "customer_supply": "all_but_two_backup", "heathrow_substation_a": "lost_supply", "heathrow_safety_supply": "airfield_generators_running", "airport_operation": "business_as_usual", "fire_response": "firefighting_stopped", "restoration": "complete"},
        "situations": ["sgt3_protected_fire", "north_hyde_total_outage", "heathrow_critical_continuity", "customer_supply_substantially_restored", "north_hyde_stable_restoration"],
    },
}


_bind_event_model_objects(NORTH_HYDE_2025)


KLEEN_PREPARATION_STEPS = [
    _step("start_gas_blow_program", "Start the natural-gas pipe-cleaning program", target="gas_blow_operation", capability="start"),
    _step("omit_specific_safety_review", "Proceed without a specific safety meeting or procedure review", after=["start_gas_blow_program"], target="safety_controls", capability="omit_review"),
    _step("configure_congested_vent", "Vent horizontally below 20 feet into a congested equipment area", after=["omit_specific_safety_review"], target="vent_configuration", capability="configure_hazard"),
    _step("retain_ignition_sources", "Retain active ignition sources inside and outside the building", after=["configure_congested_vent"], target="ignition_sources", capability="retain"),
    _step("complete_repeated_blows", "Conduct 15 intermittent high-pressure natural-gas blows", after=["retain_ignition_sources"], target="gas_blow_operation", capability="repeat_15"),
]

KLEEN_EXPLOSION_STEPS = [
    _step("start_final_release", "Enter the final ten-minute high-flow release", target="gas_blow_operation", capability="final_release"),
    _step("exceed_cleaning_force", "Greatly exceed the recommended cleaning force ratio", after=["start_final_release"], target="cleaning_force", capability="exceed"),
    _step("accumulate_gas_cloud", "Accumulate a flammable natural-gas cloud around the generation building", after=["exceed_cleaning_force"], target="gas_cloud", capability="accumulate"),
    _step("expose_workforce", "Leave workers inside the generation building during the gas blow", after=["accumulate_gas_cloud"], target="workforce", capability="expose"),
    _step("ignite_gas_cloud", "Ignite the accumulated natural-gas cloud", after=["expose_workforce"], target="gas_cloud", capability="ignite"),
    _step("explode_power_plant", "Damage the power-generation building in a catastrophic explosion", after=["ignite_gas_cloud"], target="power_plant", capability="explode"),
    _step("record_casualties", "Record six fatalities and at least 50 injuries", after=["explode_power_plant"], target="workforce", capability="record_casualties"),
    _step("terminate_gas_blow", "Terminate the natural-gas blow operation", after=["record_casualties"], target="gas_blow_operation", capability="terminate"),
]

KLEEN_INVESTIGATION_STEPS = [
    _step("start_csb_investigation", "Deploy the CSB investigation team", target="csb_investigation", capability="start"),
    _step("identify_inherently_safer_methods", "Confirm air, nitrogen and pigging as feasible safer alternatives", after=["start_csb_investigation"], target="safety_controls", capability="identify_alternatives"),
    _step("issue_urgent_recommendations", "Approve 18 urgent fuel-gas safety recommendations", after=["identify_inherently_safer_methods"], target="safety_controls", capability="recommend"),
    _step("close_investigation", "Conclude the Kleen Energy investigation", after=["issue_urgent_recommendations"], target="csb_investigation", capability="complete"),
]

KLEEN_ENERGY_2010 = {
    "schema_version": 2,
    "id": "kleen-energy-explosion-2010-l1",
    "scenario_id": "kleen-energy",
    "name": "Kleen Energy Natural Gas Explosion, 2010 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {
            "id": "csb_kleen_final",
            "url": "https://www.csb.gov/file.aspx?DocumentId=5895",
            "scope": "gas-blow setup, released quantities, cleaning-force ratio, workforce exposure, explosion and urgent recommendations",
            "priority": "final_primary_federal_investigation",
        },
        {
            "id": "csb_kleen_case",
            "url": "https://www.csb.gov/kleen-energy-natural-gas-explosion/",
            "scope": "official case provenance, casualties, investigation status and final-report release",
            "priority": "official_investigation_case_page",
        },
    ],
    "model": {
        "id": "qualification-kleen-energy",
        "name": "Kleen Energy gas-blow explosion · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Causal gas-supply, pipe-cleaning, release, workforce-exposure, explosion and investigation topology based on the CSB final investigation; the combined-cycle plant was under construction and is not modelled as operating generation.",
        "event_targets": {
            "gas_accumulation": "ke-gas-cloud",
            "external_damage": "ke-generation-building",
        },
        "nodes": [
            {"id": "ke-gas-supply", "name": "650 psig construction fuel-gas supply", "component_type_id": "gas-supply", "x": 40, "y": 220, "parameters": {"gas_pressure_psig": 650}},
            {"id": "ke-isolation-valve", "name": "Gas-blow isolation valve", "component_type_id": "pipeline-valve", "x": 260, "y": 220, "parameters": {"cleaning_force_initial_estimate": 10}},
            {"id": "ke-cleaning-force", "name": "Fuel-piping cleaning-force condition", "component_type_id": "system-state", "x": 260, "y": 20, "parameters": {"recommended_ratio": 2, "estimated_ratio_after_valve": 10, "estimated_ratio_near_vent_min": 50}, "qualification_object_id": "cleaning_force"},
            {"id": "ke-gas-blow-operation", "name": "Fuel-gas piping cleaning operation", "component_type_id": "gas-control-terminal", "x": 480, "y": 220, "parameters": {"gas_blow_count": 15, "morning_total_release_scf": 2000000, "final_release_scf": 480000}, "qualification_object_id": "gas_blow_operation"},
            {"id": "ke-vent", "name": "Horizontal open vent between HRSG structures", "component_type_id": "gas-release-zone", "x": 700, "y": 220, "parameters": {"vent_height_ft_max": 20, "orientation": "horizontal", "surroundings": "congested"}, "qualification_object_id": "vent_configuration"},
            {"id": "ke-gas-cloud", "name": "Flammable natural-gas cloud beside generation building", "component_type_id": "gas-release-zone", "x": 920, "y": 220, "parameters": {"methane_lel_volume_percent": 4.4, "methane_uel_volume_percent": 16.5, "final_release_scf": 480000}, "qualification_object_id": "gas_cloud"},
            {"id": "ke-ignition-sources", "name": "Electrical, welding and diesel-heater ignition sources", "component_type_id": "external-hazard", "x": 920, "y": 20, "qualification_object_id": "ignition_sources"},
            {"id": "ke-generation-building", "name": "Combined-cycle generation building under construction", "component_type_id": "industrial-facility", "x": 1140, "y": 220, "parameters": {"facility_state": "under_construction", "operating_generation": False}, "qualification_object_id": "power_plant"},
            {"id": "ke-workforce", "name": "Construction workforce in and around generation building", "component_type_id": "workforce-group", "x": 1140, "y": 20, "parameters": {"workers_onsite": 150, "workers_inside_building_min": 50, "workers_involved_in_blow_approx": 15, "fatalities": 6, "injuries_min": 50}, "qualification_object_id": "workforce"},
            {"id": "ke-safety-controls", "name": "Gas-blow planning, exclusion and ignition controls", "component_type_id": "protection-system", "x": 480, "y": 480, "parameters": {"specific_safety_meeting_held": False, "urgent_recommendation_count": 18}, "qualification_object_id": "safety_controls"},
            {"id": "ke-csb-investigation", "name": "CSB investigation and urgent recommendations", "component_type_id": "response-process", "x": 920, "y": 480, "parameters": {"urgent_recommendation_count": 18}, "qualification_object_id": "csb_investigation"},
        ],
        "edges": [
            {"id": "ke-edge-supply-valve", "source": "ke-gas-supply", "target": "ke-isolation-valve", "flow_type": "natural_gas", "domain": "natural_gas"},
            {"id": "ke-edge-valve-operation", "source": "ke-isolation-valve", "target": "ke-gas-blow-operation", "flow_type": "natural_gas", "domain": "natural_gas"},
            {"id": "ke-edge-operation-vent", "source": "ke-gas-blow-operation", "target": "ke-vent", "flow_type": "natural_gas", "domain": "natural_gas"},
            {"id": "ke-edge-vent-cloud", "source": "ke-vent", "target": "ke-gas-cloud", "flow_type": "natural_gas", "domain": "natural_gas"},
            {"id": "ke-edge-cloud-building", "source": "ke-gas-cloud", "target": "ke-generation-building", "flow_type": "hazard", "domain": "control"},
            {"id": "ke-edge-ignition-cloud", "source": "ke-ignition-sources", "target": "ke-gas-cloud", "flow_type": "hazard", "domain": "control"},
            {"id": "ke-edge-force-operation", "source": "ke-cleaning-force", "target": "ke-gas-blow-operation", "flow_type": "control", "domain": "control"},
            {"id": "ke-edge-controls-operation", "source": "ke-safety-controls", "target": "ke-gas-blow-operation", "flow_type": "control", "domain": "control"},
            {"id": "ke-edge-building-workforce", "source": "ke-generation-building", "target": "ke-workforce", "flow_type": "exposure", "domain": "control"},
            {"id": "ke-edge-investigation-controls", "source": "ke-csb-investigation", "target": "ke-safety-controls", "flow_type": "control", "domain": "control"},
        ],
    },
    "objects": [
        _object("gas_blow_operation", "Fuel-gas piping cleaning operation", "commissioning_process", "planned", ["planned", "active", "fifteen_blows_completed", "final_high_flow_release", "terminated_after_explosion"], {"start": _transitions(("planned", "active")), "repeat_15": _transitions(("active", "fifteen_blows_completed")), "final_release": _transitions(("fifteen_blows_completed", "final_high_flow_release")), "terminate": _transitions(("final_high_flow_release", "terminated_after_explosion"))}),
        _object("safety_controls", "Natural-gas blow safety controls", "safety_system", "review_expected", ["review_expected", "specific_review_omitted", "safer_alternatives_identified", "urgent_recommendations_issued"], {"omit_review": _transitions(("review_expected", "specific_review_omitted")), "identify_alternatives": _transitions(("specific_review_omitted", "safer_alternatives_identified")), "recommend": _transitions(("safer_alternatives_identified", "urgent_recommendations_issued"))}),
        _object("vent_configuration", "Open-ended gas vent between the HRSG structures", "vent_path", "not_configured", ["not_configured", "horizontal_below_20ft_congested"], {"configure_hazard": _transitions(("not_configured", "horizontal_below_20ft_congested"))}),
        _object("ignition_sources", "Worksite ignition sources", "hazard_group", "controllable", ["controllable", "active_inside_and_outside"], {"retain": _transitions(("controllable", "active_inside_and_outside"))}),
        _object("cleaning_force", "Fuel-piping cleaning force ratio", "process_parameter", "target_2", ["target_2", "approximately_10_to_over_50"], {"exceed": _transitions(("target_2", "approximately_10_to_over_50"))}),
        _object("gas_cloud", "Released natural-gas cloud", "flammable_atmosphere", "absent", ["absent", "accumulated_flammable", "ignited"], {"accumulate": _transitions(("absent", "accumulated_flammable")), "ignite": _transitions(("accumulated_flammable", "ignited"))}),
        _object("workforce", "Kleen Energy construction workforce", "worker_group", "normal_work", ["normal_work", "exposed_during_blow", "six_fatalities_at_least_50_injured"], {"expose": _transitions(("normal_work", "exposed_during_blow")), "record_casualties": _transitions(("exposed_during_blow", "six_fatalities_at_least_50_injured"))}),
        _object("power_plant", "Kleen Energy combined-cycle power plant", "industrial_facility", "under_construction", ["under_construction", "catastrophic_explosion_damage"], {"explode": _transitions(("under_construction", "catastrophic_explosion_damage"))}),
        _object("csb_investigation", "CSB Kleen Energy investigation", "investigation_process", "not_started", ["not_started", "active", "complete"], {"start": _transitions(("not_started", "active")), "complete": _transitions(("active", "complete"))}),
    ],
    "situations": [
        {"id": "uncontrolled_gas_blow_hazard", "all": [{"object": "safety_controls", "state": "specific_review_omitted"}, {"object": "vent_configuration", "state": "horizontal_below_20ft_congested"}, {"object": "ignition_sources", "state": "active_inside_and_outside"}]},
        {"id": "excessive_final_release", "all": [{"object": "gas_blow_operation", "state": "final_high_flow_release"}, {"object": "cleaning_force", "state": "approximately_10_to_over_50"}, {"object": "gas_cloud", "state": "accumulated_flammable"}]},
        {"id": "kleen_explosion", "all": [{"object": "gas_cloud", "state": "ignited"}, {"object": "power_plant", "state": "catastrophic_explosion_damage"}]},
        {"id": "mass_casualty_incident", "all": [{"object": "workforce", "state": "six_fatalities_at_least_50_injured"}, {"object": "gas_blow_operation", "state": "terminated_after_explosion"}]},
        {"id": "corrective_safety_response", "all": [{"object": "safety_controls", "state": "urgent_recommendations_issued"}, {"object": "csb_investigation", "state": "complete"}]},
    ],
    "processes": [
        _process("kleen_preparation_l1", "Kleen Energy gas-blow preparation L1", KLEEN_PREPARATION_STEPS),
        _process("kleen_explosion_l1", "Kleen Energy release and explosion L1", KLEEN_EXPLOSION_STEPS),
        _process("kleen_investigation_l1", "Kleen Energy investigation and corrective response L1", KLEEN_INVESTIGATION_STEPS),
    ],
    "timeline": [
        _entry("gas_blow_program_started", "2010-02-07T07:15:00-05:00", entry_kind="derived", evidence="derived", fact="The model begins the approximately four-hour intermittent gas-blow period ending at the reported 11:15 explosion", action=_action("gas_blow_operation", "start", "active"), process=("kleen_preparation_l1", "start_gas_blow_program"), metrics={"gas_blow_period_hours": 4, "gas_pressure_psig": 650}),
        _entry("specific_safety_review_omitted", "2010-02-07T07:15:00.001-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="The pipe-cleaning crew had no safety meeting specific to the gas-blow hazards and did not review the procedure", action=_action("safety_controls", "omit_review", "specific_review_omitted"), process=("kleen_preparation_l1", "omit_specific_safety_review")),
        _entry("congested_horizontal_vent", "2010-02-07T07:15:00.002-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="The open-ended vent was horizontal, below 20 feet and between two HRSG structures beside the generation building", action=_action("vent_configuration", "configure_hazard", "horizontal_below_20ft_congested"), process=("kleen_preparation_l1", "configure_congested_vent"), metrics={"vent_height_ft_max": 20}),
        _entry("ignition_sources_remained", "2010-02-07T07:15:00.003-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="Electrical power, active welding, diesel heaters and possible self-ignition sources remained", action=_action("ignition_sources", "retain", "active_inside_and_outside"), process=("kleen_preparation_l1", "retain_ignition_sources"), situations=["uncontrolled_gas_blow_hazard"]),
        _entry("fifteen_gas_blows_completed", "2010-02-07T11:05:00-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="Fifteen natural-gas blows had been conducted intermittently over approximately four hours", action=_action("gas_blow_operation", "repeat_15", "fifteen_blows_completed"), process=("kleen_preparation_l1", "complete_repeated_blows"), metrics={"gas_blow_count": 15, "morning_total_release_scf": 2000000}),
        _entry("final_ten_minute_release", "2010-02-07T11:05:00.001-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="The final ten-minute release began, ultimately releasing approximately 480,000 standard cubic feet", action=_action("gas_blow_operation", "final_release", "final_high_flow_release"), process=("kleen_explosion_l1", "start_final_release"), metrics={"final_release_duration_minutes": 10, "final_release_scf": 480000}),
        _entry("cleaning_force_exceeded", "2010-02-07T11:05:00.002-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="The actual cleaning force ratio was estimated near 10 after the isolation valve and above 50 toward the vent, versus a target of 2", action=_action("cleaning_force", "exceed", "approximately_10_to_over_50"), process=("kleen_explosion_l1", "exceed_cleaning_force"), metrics={"cleaning_force_target": 2, "cleaning_force_initial_estimate": 10, "cleaning_force_vent_min": 50, "actual_flow_rate_lb_per_hour": 470000}),
        _entry("flammable_gas_cloud_accumulated", "2010-02-07T11:14:59.997-05:00", entry_kind="derived", evidence="derived", fact="The congested geometry and horizontal vent impeded dispersion and allowed a flammable cloud to accumulate", action=_action("gas_cloud", "accumulate", "accumulated_flammable"), process=("kleen_explosion_l1", "accumulate_gas_cloud"), situations=["excessive_final_release"], metrics={"methane_lel_volume_percent": 4.4, "methane_uel_volume_percent": 16.5}),
        _entry("workforce_exposed", "2010-02-07T11:14:59.998-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="About 150 workers were onsite and more than 50 were inside the generation building; only about 15 were involved in the gas blow", action=_action("workforce", "expose", "exposed_during_blow"), process=("kleen_explosion_l1", "expose_workforce"), metrics={"workers_onsite": 150, "workers_inside_building_min": 50, "workers_involved_in_blow_approx": 15}),
        _entry("gas_cloud_ignited", "2010-02-07T11:15:00-05:00", entry_kind="input", origin="external_event", evidence="reported", source="csb_kleen_final", fact="The released natural gas found an ignition source", action=_action("gas_cloud", "ignite", "ignited"), process=("kleen_explosion_l1", "ignite_gas_cloud")),
        _entry("power_plant_explosion", "2010-02-07T11:15:00.001-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="A catastrophic natural-gas explosion damaged the power plant under construction", action=_action("power_plant", "explode", "catastrophic_explosion_damage"), process=("kleen_explosion_l1", "explode_power_plant"), situations=["kleen_explosion"]),
        _entry("casualties_recorded", "2010-02-07T11:15:00.002-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="Six workers were killed and at least 50 were injured", action=_action("workforce", "record_casualties", "six_fatalities_at_least_50_injured"), process=("kleen_explosion_l1", "record_casualties"), metrics={"fatalities": 6, "injuries_min": 50}),
        _entry("gas_blow_terminated", "2010-02-07T11:15:00.003-05:00", entry_kind="derived", evidence="derived", fact="The explosion terminated the commissioning gas-blow operation", action=_action("gas_blow_operation", "terminate", "terminated_after_explosion"), process=("kleen_explosion_l1", "terminate_gas_blow"), situations=["mass_casualty_incident"]),
        _entry("csb_investigation_started", "2010-02-08T12:00:00-05:00", entry_kind="input", origin="planned_process_start", evidence="reported", source="csb_kleen_case", fact="The CSB investigation team deployed to the Kleen Energy site", action=_action("csb_investigation", "start", "active"), process=("kleen_investigation_l1", "start_csb_investigation")),
        _entry("safer_methods_identified", "2010-05-19T12:00:00-04:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="The investigation found no scenario requiring natural gas blows and confirmed air, nitrogen and pigging as feasible alternatives", action=_action("safety_controls", "identify_alternatives", "safer_alternatives_identified"), process=("kleen_investigation_l1", "identify_inherently_safer_methods")),
        _entry("urgent_recommendations_approved", "2010-06-28T18:30:00-04:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_final", fact="The Board approved 18 urgent recommendations addressing fuel-gas cleaning and purging", action=_action("safety_controls", "recommend", "urgent_recommendations_issued"), process=("kleen_investigation_l1", "issue_urgent_recommendations"), metrics={"urgent_recommendation_count": 18}),
        _entry("kleen_investigation_complete", "2010-06-28T18:30:00.001-04:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_kleen_case", fact="The CSB concluded its Kleen Energy investigation", action=_action("csb_investigation", "complete", "complete"), process=("kleen_investigation_l1", "close_investigation"), situations=["corrective_safety_response"]),
    ],
    "checkpoints": [
        {"id": "fifteen_blows_two_million_scf", "after": "fifteen_gas_blows_completed", "all": [{"object": "gas_blow_operation", "state": "fifteen_blows_completed"}, {"metric": "gas_blow_count", "equals": 15}, {"metric": "morning_total_release_scf", "equals": 2000000}]},
        {"id": "final_480000_scf_excessive_cfr", "after": "flammable_gas_cloud_accumulated", "all": [{"object": "gas_cloud", "state": "accumulated_flammable"}, {"metric": "final_release_scf", "equals": 480000}, {"metric": "cleaning_force_vent_min", "equals": 50}]},
        {"id": "explosion_at_1115", "after": "power_plant_explosion", "all": [{"object": "gas_cloud", "state": "ignited"}, {"object": "power_plant", "state": "catastrophic_explosion_damage"}]},
        {"id": "six_fatalities_fifty_injuries", "after": "gas_blow_terminated", "all": [{"object": "workforce", "state": "six_fatalities_at_least_50_injured"}, {"metric": "fatalities", "equals": 6}, {"metric": "injuries_min", "equals": 50}]},
        {"id": "eighteen_urgent_recommendations", "after": "kleen_investigation_complete", "all": [{"object": "safety_controls", "state": "urgent_recommendations_issued"}, {"object": "csb_investigation", "state": "complete"}, {"metric": "urgent_recommendation_count", "equals": 18}]},
    ],
    "expected_final": {
        "object_states": {"gas_blow_operation": "terminated_after_explosion", "safety_controls": "urgent_recommendations_issued", "vent_configuration": "horizontal_below_20ft_congested", "ignition_sources": "active_inside_and_outside", "cleaning_force": "approximately_10_to_over_50", "gas_cloud": "ignited", "workforce": "six_fatalities_at_least_50_injured", "power_plant": "catastrophic_explosion_damage", "csb_investigation": "complete"},
        "situations": ["uncontrolled_gas_blow_hazard", "excessive_final_release", "kleen_explosion", "mass_casualty_incident", "corrective_safety_response"],
    },
}


_bind_event_model_objects(KLEEN_ENERGY_2010)


MACONDO_BARRIER_STEPS = [
    _step("interpret_negative_test", "Accept the anomalous negative-pressure test", target="negative_pressure_test", capability="misinterpret"),
    _step("lose_primary_barrier", "Lose the cement and hydrostatic well barriers", after=["interpret_negative_test"], target="well_barrier", capability="fail"),
    _step("miss_hydrocarbon_influx", "Allow an undetected hydrocarbon influx to become a blowout", after=["lose_primary_barrier"], target="well_flow", capability="blowout"),
    _step("overwhelm_mud_gas_system", "Route the flow to and overwhelm the mud-gas separator", after=["miss_hydrocarbon_influx"], target="mud_gas_system", capability="overwhelm"),
]

MACONDO_EMERGENCY_STEPS = [
    _step("fail_annular_seal", "Fail to seal the flowing well with the upper annular", target="bop", capability="annular_fail"),
    _step("fail_blind_shear_ram", "Fail to shear the buckled drillpipe and seal the well", after=["fail_annular_seal"], target="bop", capability="bsr_fail"),
    _step("ignite_rig", "Ignite the hydrocarbon cloud and develop a major rig fire", after=["fail_blind_shear_ram"], target="rig", capability="explode"),
    _step("evacuate_crew", "Evacuate survivors and record casualties", after=["ignite_rig"], target="crew", capability="evacuate"),
    _step("sink_rig", "Lose and sink Deepwater Horizon", after=["evacuate_crew"], target="rig", capability="sink"),
]

MACONDO_RESPONSE_STEPS = [
    _step("activate_spill_response", "Activate the federal spill and well-control response", target="spill_response", capability="activate"),
    _step("cap_well", "Stop the uncontrolled flow after 87 days", after=["activate_spill_response"], target="well_flow", capability="cap"),
    _step("complete_response", "Stabilize the capped-well response", after=["cap_well"], target="spill_response", capability="stabilize"),
    _step("complete_investigation", "Complete the CSB Macondo investigation", after=["complete_response"], target="investigation", capability="complete"),
]

MACONDO_2010 = {
    "schema_version": 2,
    "id": "macondo-blowout-2010-l1",
    "scenario_id": "macondo",
    "name": "Macondo Blowout and Explosion, 2010 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {"id": "csb_macondo_case", "url": "https://www.csb.gov/macondo-blowout-and-explosion/", "scope": "official case, crew, fatalities and investigation status", "priority": "official_investigation_case_page"},
        {"id": "csb_macondo_volume_2", "url": "https://www.csb.gov/assets/1/7/vol_2_final_version.pdf", "scope": "BOP technical failure, effective compression and failed well barriers", "priority": "final_primary_federal_investigation"},
        {"id": "uscg_boemre_jit", "url": "https://www.dco.uscg.mil/Portals/9/OCSNCOE/Casualty-Information/DWH-Macondo/BOEMRE-Macondo-Well-Blowout-Report-Vol-II.pdf", "scope": "blowout, explosions, fire, sinking and 87-day release sequence", "priority": "joint_federal_investigation"},
    ],
    "model": {
        "id": "qualification-macondo",
        "name": "Macondo well blowout · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Causal reservoir, well-barrier, wellbore, BOP, riser, rig, casualty, spill and response topology based on CSB and USCG/BOEMRE investigations; it is not a field-development or geographic spill model.",
        "event_targets": {"barrier_failure": "mc-cement-barrier", "uncontrolled_flow": "mc-wellbore", "fire": "mc-deepwater-horizon"},
        "nodes": [
            {"id": "mc-reservoir", "name": "Macondo high-pressure hydrocarbon reservoir", "component_type_id": "offshore-reservoir", "x": 40, "y": 300, "parameters": {"reservoir_pressure_psi_approx": 11850, "water_depth_ft_approx": 5000}},
            {"id": "mc-cement-barrier", "name": "Production-casing cement and hydrostatic barriers", "component_type_id": "well-barrier", "x": 260, "y": 300, "qualification_object_id": "well_barrier"},
            {"id": "mc-negative-test", "name": "Negative-pressure integrity test", "component_type_id": "system-state", "x": 260, "y": 40, "parameters": {"written_procedure_available": False}, "qualification_object_id": "negative_pressure_test"},
            {"id": "mc-wellbore", "name": "Macondo production casing and wellbore", "component_type_id": "offshore-wellbore", "x": 480, "y": 300, "parameters": {"total_depth_ft": 18360}, "qualification_object_id": "well_flow"},
            {"id": "mc-bop", "name": "Deepwater Horizon blowout preventer", "component_type_id": "blowout-preventer", "x": 700, "y": 300, "parameters": {"failure_mechanism": "effective_compression_drillpipe_buckling"}, "qualification_object_id": "bop"},
            {"id": "mc-riser", "name": "Marine riser to Deepwater Horizon", "component_type_id": "offshore-wellbore", "x": 920, "y": 300},
            {"id": "mc-mud-gas", "name": "Mud-gas separator and vent path", "component_type_id": "mud-gas-separator", "x": 1140, "y": 300, "qualification_object_id": "mud_gas_system"},
            {"id": "mc-deepwater-horizon", "name": "Deepwater Horizon drilling rig", "component_type_id": "offshore-drilling-rig", "x": 1360, "y": 300, "parameters": {"crew_onboard": 126, "burn_duration_days": 2}, "qualification_object_id": "rig"},
            {"id": "mc-crew", "name": "Deepwater Horizon crew", "component_type_id": "workforce-group", "x": 1360, "y": 40, "parameters": {"crew_onboard": 126, "fatalities": 11, "serious_injuries": 17}, "qualification_object_id": "crew"},
            {"id": "mc-spill-zone", "name": "Gulf of Mexico uncontrolled hydrocarbon release", "component_type_id": "marine-spill-zone", "x": 920, "y": 560, "parameters": {"uncontrolled_flow_days": 87, "oil_release_barrels_approx": 4900000}},
            {"id": "mc-spill-response", "name": "Federal spill and well-control response", "component_type_id": "response-process", "x": 1140, "y": 560, "qualification_object_id": "spill_response"},
            {"id": "mc-investigation", "name": "CSB Macondo investigation", "component_type_id": "response-process", "x": 1360, "y": 560, "qualification_object_id": "investigation"},
        ],
        "edges": [
            {"id": "mc-edge-reservoir-barrier", "source": "mc-reservoir", "target": "mc-cement-barrier", "flow_type": "hydrocarbon", "domain": "hydrocarbon"},
            {"id": "mc-edge-barrier-well", "source": "mc-cement-barrier", "target": "mc-wellbore", "flow_type": "hydrocarbon", "domain": "hydrocarbon"},
            {"id": "mc-edge-test-barrier", "source": "mc-negative-test", "target": "mc-cement-barrier", "flow_type": "control", "domain": "control"},
            {"id": "mc-edge-well-bop", "source": "mc-wellbore", "target": "mc-bop", "flow_type": "hydrocarbon", "domain": "hydrocarbon"},
            {"id": "mc-edge-bop-riser", "source": "mc-bop", "target": "mc-riser", "flow_type": "hydrocarbon", "domain": "hydrocarbon"},
            {"id": "mc-edge-riser-mgs", "source": "mc-riser", "target": "mc-mud-gas", "flow_type": "hydrocarbon", "domain": "hydrocarbon"},
            {"id": "mc-edge-mgs-rig", "source": "mc-mud-gas", "target": "mc-deepwater-horizon", "flow_type": "hazard", "domain": "control"},
            {"id": "mc-edge-rig-crew", "source": "mc-deepwater-horizon", "target": "mc-crew", "flow_type": "exposure", "domain": "control"},
            {"id": "mc-edge-well-spill", "source": "mc-wellbore", "target": "mc-spill-zone", "flow_type": "hydrocarbon", "domain": "hydrocarbon"},
            {"id": "mc-edge-response-spill", "source": "mc-spill-response", "target": "mc-spill-zone", "flow_type": "control", "domain": "control"},
            {"id": "mc-edge-investigation-response", "source": "mc-investigation", "target": "mc-spill-response", "flow_type": "control", "domain": "control"},
        ],
    },
    "objects": [
        _object("negative_pressure_test", "Macondo negative-pressure integrity test", "verification_process", "planned", ["planned", "anomalous_misinterpreted"], {"misinterpret": _transitions(("planned", "anomalous_misinterpreted"))}),
        _object("well_barrier", "Cement and hydrostatic well barriers", "well_barrier", "assumed_intact", ["assumed_intact", "failed"], {"fail": _transitions(("assumed_intact", "failed"))}),
        _object("well_flow", "Macondo well hydrocarbon flow", "well_state", "contained", ["contained", "uncontrolled_blowout", "capped"], {"blowout": _transitions(("contained", "uncontrolled_blowout")), "cap": _transitions(("uncontrolled_blowout", "capped"))}),
        _object("mud_gas_system", "Mud-gas separator and vent path", "process_equipment", "available", ["available", "overwhelmed"], {"overwhelm": _transitions(("available", "overwhelmed"))}),
        _object("bop", "Deepwater Horizon blowout preventer", "safety_system", "available", ["available", "upper_annular_failed", "blind_shear_ram_failed"], {"annular_fail": _transitions(("available", "upper_annular_failed")), "bsr_fail": _transitions(("upper_annular_failed", "blind_shear_ram_failed"))}),
        _object("rig", "Deepwater Horizon mobile offshore drilling unit", "offshore_facility", "drilling", ["drilling", "explosion_and_fire", "sunk"], {"explode": _transitions(("drilling", "explosion_and_fire")), "sink": _transitions(("explosion_and_fire", "sunk"))}),
        _object("crew", "Deepwater Horizon crew", "worker_group", "onboard_126", ["onboard_126", "evacuated_with_casualties"], {"evacuate": _transitions(("onboard_126", "evacuated_with_casualties"))}),
        _object("spill_response", "Federal spill and well-control response", "response_process", "standby", ["standby", "active", "stabilized"], {"activate": _transitions(("standby", "active")), "stabilize": _transitions(("active", "stabilized"))}),
        _object("investigation", "CSB Macondo investigation", "investigation_process", "not_started", ["not_started", "complete"], {"complete": _transitions(("not_started", "complete"))}),
    ],
    "situations": [
        {"id": "well_barrier_loss", "all": [{"object": "negative_pressure_test", "state": "anomalous_misinterpreted"}, {"object": "well_barrier", "state": "failed"}]},
        {"id": "macondo_blowout", "all": [{"object": "well_flow", "state": "uncontrolled_blowout"}, {"object": "mud_gas_system", "state": "overwhelmed"}]},
        {"id": "bop_failed_to_seal", "all": [{"object": "bop", "state": "blind_shear_ram_failed"}]},
        {"id": "rig_casualty", "all": [{"object": "rig", "state": "sunk"}, {"object": "crew", "state": "evacuated_with_casualties"}]},
        {"id": "well_stabilized", "all": [{"object": "well_flow", "state": "capped"}, {"object": "spill_response", "state": "stabilized"}]},
    ],
    "processes": [
        _process("macondo_barrier_loss_l1", "Macondo barrier loss and blowout L1", MACONDO_BARRIER_STEPS),
        _process("macondo_emergency_l1", "Macondo BOP, explosion and evacuation L1", MACONDO_EMERGENCY_STEPS),
        _process("macondo_response_l1", "Macondo spill control and investigation L1", MACONDO_RESPONSE_STEPS),
    ],
    "timeline": [
        _entry("negative_test_misinterpreted", "2010-04-20T20:00:00-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_macondo_volume_2", fact="An anomalous negative-pressure test was accepted as confirmation of well integrity", action=_action("negative_pressure_test", "misinterpret", "anomalous_misinterpreted"), process=("macondo_barrier_loss_l1", "interpret_negative_test")),
        _entry("primary_barriers_failed", "2010-04-20T20:00:00.001-05:00", entry_kind="derived", evidence="derived", fact="The cement and hydrostatic barriers did not prevent reservoir hydrocarbons entering the production casing", action=_action("well_barrier", "fail", "failed"), process=("macondo_barrier_loss_l1", "lose_primary_barrier"), situations=["well_barrier_loss"]),
        _entry("blowout_developed", "2010-04-20T21:40:00-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="uscg_boemre_jit", fact="An undetected hydrocarbon influx escalated into loss of well control and blowout", action=_action("well_flow", "blowout", "uncontrolled_blowout"), process=("macondo_barrier_loss_l1", "miss_hydrocarbon_influx")),
        _entry("upper_annular_failed", "2010-04-20T21:43:00-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_macondo_volume_2", fact="The upper annular preventer did not seal the flowing well", action=_action("bop", "annular_fail", "upper_annular_failed"), process=("macondo_emergency_l1", "fail_annular_seal")),
        _entry("mud_gas_separator_overwhelmed", "2010-04-20T21:47:00-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="uscg_boemre_jit", fact="Flow routed to the mud-gas separator overwhelmed it and gas spread across the rig", action=_action("mud_gas_system", "overwhelm", "overwhelmed"), process=("macondo_barrier_loss_l1", "overwhelm_mud_gas_system"), situations=["macondo_blowout"]),
        _entry("blind_shear_ram_failed", "2010-04-20T21:49:00-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_macondo_volume_2", fact="Effective compression buckled the drillpipe outside the blind shear ram cutting surface and the BOP did not seal", action=_action("bop", "bsr_fail", "blind_shear_ram_failed"), process=("macondo_emergency_l1", "fail_blind_shear_ram"), situations=["bop_failed_to_seal"]),
        _entry("rig_explosions_and_fire", "2010-04-20T21:49:10-05:00", entry_kind="input", origin="external_event", evidence="reported", source="uscg_boemre_jit", fact="Two explosions about ten seconds apart ignited a major hydrocarbon-fed fire", action=_action("rig", "explode", "explosion_and_fire"), process=("macondo_emergency_l1", "ignite_rig"), metrics={"explosion_count": 2, "seconds_between_explosions_approx": 10}),
        _entry("crew_evacuated", "2010-04-20T23:30:00-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_macondo_case", fact="Survivors evacuated; eleven workers died and seventeen were seriously injured", action=_action("crew", "evacuate", "evacuated_with_casualties"), process=("macondo_emergency_l1", "evacuate_crew"), metrics={"crew_onboard": 126, "fatalities": 11, "serious_injuries": 17}),
        _entry("spill_response_activated", "2010-04-21T12:00:00-05:00", entry_kind="input", origin="planned_process_start", evidence="reported", source="uscg_boemre_jit", fact="A large-scale federal spill and well-control response began", action=_action("spill_response", "activate", "active"), process=("macondo_response_l1", "activate_spill_response")),
        _entry("deepwater_horizon_sank", "2010-04-22T10:22:00-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="uscg_boemre_jit", fact="Deepwater Horizon sank after burning for two days", action=_action("rig", "sink", "sunk"), process=("macondo_emergency_l1", "sink_rig"), situations=["rig_casualty"], metrics={"rig_fire_days": 2}),
        _entry("well_capped_after_87_days", "2010-07-15T14:25:00-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="uscg_boemre_jit", fact="The uncontrolled Macondo flow was stopped after 87 days", action=_action("well_flow", "cap", "capped"), process=("macondo_response_l1", "cap_well"), metrics={"uncontrolled_flow_days": 87, "oil_release_barrels_approx": 4900000}),
        _entry("response_stabilized", "2010-07-15T14:25:00.001-05:00", entry_kind="derived", evidence="derived", fact="Capping the well stabilized the uncontrolled-flow phase of the response", action=_action("spill_response", "stabilize", "stabilized"), process=("macondo_response_l1", "complete_response"), situations=["well_stabilized"]),
        _entry("csb_investigation_complete", "2016-04-20T12:00:00-05:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="csb_macondo_case", fact="The CSB approved its completed Macondo investigation", action=_action("investigation", "complete", "complete"), process=("macondo_response_l1", "complete_investigation")),
    ],
    "checkpoints": [
        {"id": "barriers_and_bop_failed", "after": "blind_shear_ram_failed", "all": [{"object": "well_barrier", "state": "failed"}, {"object": "bop", "state": "blind_shear_ram_failed"}]},
        {"id": "explosion_casualties", "after": "crew_evacuated", "all": [{"object": "rig", "state": "explosion_and_fire"}, {"metric": "fatalities", "equals": 11}, {"metric": "serious_injuries", "equals": 17}]},
        {"id": "rig_sank", "after": "deepwater_horizon_sank", "all": [{"object": "rig", "state": "sunk"}, {"metric": "rig_fire_days", "equals": 2}]},
        {"id": "flow_stopped_87_days", "after": "response_stabilized", "all": [{"object": "well_flow", "state": "capped"}, {"metric": "uncontrolled_flow_days", "equals": 87}]},
    ],
    "expected_final": {"object_states": {"negative_pressure_test": "anomalous_misinterpreted", "well_barrier": "failed", "well_flow": "capped", "mud_gas_system": "overwhelmed", "bop": "blind_shear_ram_failed", "rig": "sunk", "crew": "evacuated_with_casualties", "spill_response": "stabilized", "investigation": "complete"}, "situations": ["well_barrier_loss", "macondo_blowout", "bop_failed_to_seal", "rig_casualty", "well_stabilized"]},
}


_bind_event_model_objects(MACONDO_2010)


UA_MD_INCIDENT_STEPS = [
    _step("trip_400kv_interconnector", "Trip the Romania–Moldova 400 kV interconnection", target="romania_moldova_line", capability="trip"),
    _step("trip_750kv_corridor", "Trip the western–central Ukraine 750 kV corridor", after=["trip_400kv_interconnector"], target="ukraine_750kv_line", capability="trip"),
    _step("separate_area", "Separate the Ukraine–Moldova area from Continental Europe", after=["trip_750kv_corridor"], target="synchronous_area", capability="separate"),
    _step("activate_protection", "Activate automatic protection and emergency outages", after=["separate_area"], target="automatic_protection", capability="activate"),
    _step("unload_nuclear_units", "Unload nuclear generation units during the disturbance", after=["activate_protection"], target="generation", capability="unload"),
]

UA_MD_RESTORATION_STEPS = [
    _step("start_joint_restoration", "Activate Ukrenergo and Moldelectrica restoration procedures", target="restoration", capability="activate"),
    _step("resynchronise_ce", "Resynchronise with Continental Europe", after=["start_joint_restoration"], target="synchronous_area", capability="resynchronise"),
    _step("restore_consumers", "Coordinate restoration of consumer supply", after=["resynchronise_ce"], target="consumer_supply", capability="restore"),
    _step("stabilize_systems", "Stabilize the interconnected systems", after=["restore_consumers"], target="restoration", capability="stabilize"),
]

UA_MD_2026 = {
    "schema_version": 2,
    "id": "ukraine-moldova-incident-2026-l1",
    "scenario_id": "ua-md-2026",
    "name": "Ukraine–Moldova Power System Incident, 31.01.2026 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {"id": "entsoe_ua_md_notice", "url": "https://www.entsoe.eu/news/2026/02/05/power-system-incident-in-ukraine-and-moldova/", "scope": "incident time, significant outages, CE separation, resynchronisation and coordinated restoration", "priority": "official_tso_association_notice"},
        {"id": "ua_president_incident_address", "url": "https://www.president.gov.ua/en/news/vranci-stalas-tehnologichna-avariya-na-merezhi-zaraz-trivaye-102653", "scope": "affected lines, preliminary weather hypothesis, automatic trips and same-day stabilization", "priority": "official_national_update"},
    ],
    "model": {
        "id": "qualification-ua-md-2026",
        "name": "Ukraine–Moldova 31 January 2026 · event-specific L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "Aggregated two-line, synchronous-area, generation, customer-impact and coordinated-restoration topology. The precise initiating cause remained under analysis; icing is stored only as a preliminary hypothesis.",
        "event_targets": {"interconnector_trip": "um-400kv-interconnector", "corridor_trip": "um-750kv-corridor", "restore": "um-750kv-corridor", "resynchronize": "um-ce-interface"},
        "nodes": [
            {"id": "um-weather", "name": "Severe icing hypothesis (preliminary)", "component_type_id": "external-hazard", "x": 40, "y": 20, "parameters": {"evidence_status": "preliminary_not_final"}},
            {"id": "um-ce-grid", "name": "Continental Europe synchronous system", "component_type_id": "external-grid", "x": 40, "y": 240},
            {"id": "um-400kv-interconnector", "name": "Romania–Moldova 400 kV interconnection", "component_type_id": "transmission-corridor", "x": 260, "y": 240, "parameters": {"voltage_kv": 400}, "qualification_object_id": "romania_moldova_line"},
            {"id": "um-moldova-grid", "name": "Moldovan power system", "component_type_id": "grid-zone", "x": 480, "y": 240},
            {"id": "um-750kv-corridor", "name": "Western–central Ukraine 750 kV corridor", "component_type_id": "transmission-corridor", "x": 700, "y": 240, "parameters": {"voltage_kv": 750}, "qualification_object_id": "ukraine_750kv_line"},
            {"id": "um-ukraine-grid", "name": "Ukrainian power system", "component_type_id": "grid-zone", "x": 920, "y": 240},
            {"id": "um-generation", "name": "Ukrainian generation aggregate including unloaded NPP units", "component_type_id": "generation-aggregate", "x": 920, "y": 20, "parameters": {"nuclear_units_unloaded": True, "capacity_evidence": "not_reported"}, "qualification_object_id": "generation"},
            {"id": "um-protection", "name": "Automatic protection and emergency outage schemes", "component_type_id": "protection-system", "x": 700, "y": 480, "qualification_object_id": "automatic_protection"},
            {"id": "um-ce-interface", "name": "Ukraine–Moldova synchronous interface to CE", "component_type_id": "hvdc-interconnector", "x": 480, "y": 480, "parameters": {"physical_mode": "synchronous_ac_interface"}, "qualification_object_id": "synchronous_area"},
            {"id": "um-consumers", "name": "Affected Ukraine and Moldova consumer supply", "component_type_id": "customer-group", "x": 1140, "y": 240, "parameters": {"affected_scope": "significant_outages_not_quantified"}, "qualification_object_id": "consumer_supply"},
            {"id": "um-restoration", "name": "Ukrenergo–Moldelectrica–neighbouring TSO restoration", "component_type_id": "response-process", "x": 920, "y": 480, "qualification_object_id": "restoration"},
        ],
        "edges": [
            {"id": "um-edge-ce-400", "source": "um-ce-grid", "target": "um-400kv-interconnector"},
            {"id": "um-edge-400-md", "source": "um-400kv-interconnector", "target": "um-moldova-grid"},
            {"id": "um-edge-md-750", "source": "um-moldova-grid", "target": "um-750kv-corridor"},
            {"id": "um-edge-750-ua", "source": "um-750kv-corridor", "target": "um-ukraine-grid"},
            {"id": "um-edge-generation-ua", "source": "um-generation", "target": "um-ukraine-grid"},
            {"id": "um-edge-ua-consumers", "source": "um-ukraine-grid", "target": "um-consumers"},
            {"id": "um-edge-ce-interface", "source": "um-ce-grid", "target": "um-ce-interface"},
            {"id": "um-edge-interface-ua", "source": "um-ce-interface", "target": "um-ukraine-grid"},
            {"id": "um-edge-protection-ua", "source": "um-protection", "target": "um-ukraine-grid", "flow_type": "control", "domain": "control"},
            {"id": "um-edge-restoration-interface", "source": "um-restoration", "target": "um-ce-interface", "flow_type": "control", "domain": "control"},
        ],
    },
    "objects": [
        _object("romania_moldova_line", "Romania–Moldova 400 kV interconnection", "transmission_line", "in_service", ["in_service", "tripped"], {"trip": _transitions(("in_service", "tripped"))}),
        _object("ukraine_750kv_line", "Western–central Ukraine 750 kV corridor", "transmission_line", "in_service", ["in_service", "tripped"], {"trip": _transitions(("in_service", "tripped"))}),
        _object("synchronous_area", "Ukraine–Moldova synchronous area", "power_system", "synchronised_ce", ["synchronised_ce", "separated", "resynchronised"], {"separate": _transitions(("synchronised_ce", "separated")), "resynchronise": _transitions(("separated", "resynchronised"))}),
        _object("automatic_protection", "Automatic protection and emergency outages", "protection_system", "armed", ["armed", "activated"], {"activate": _transitions(("armed", "activated"))}),
        _object("generation", "Ukrainian generation aggregate", "generation_group", "normal_dispatch", ["normal_dispatch", "nuclear_units_unloaded"], {"unload": _transitions(("normal_dispatch", "nuclear_units_unloaded"))}),
        _object("consumer_supply", "Affected Ukraine and Moldova consumer supply", "customer_group", "supplied", ["supplied", "significant_outages", "restored"], {"interrupt": _transitions(("supplied", "significant_outages")), "restore": _transitions(("significant_outages", "restored"))}),
        _object("restoration", "Joint TSO and DSO restoration", "response_process", "standby", ["standby", "active", "stabilized"], {"activate": _transitions(("standby", "active")), "stabilize": _transitions(("active", "stabilized"))}),
    ],
    "situations": [
        {"id": "ua_md_system_separation", "all": [{"object": "romania_moldova_line", "state": "tripped"}, {"object": "ukraine_750kv_line", "state": "tripped"}, {"object": "synchronous_area", "state": "separated"}]},
        {"id": "significant_outages", "all": [{"object": "automatic_protection", "state": "activated"}, {"object": "consumer_supply", "state": "significant_outages"}]},
        {"id": "ua_md_resynchronised", "all": [{"object": "synchronous_area", "state": "resynchronised"}, {"object": "consumer_supply", "state": "restored"}]},
    ],
    "processes": [_process("ua_md_incident_l1", "Ukraine–Moldova separation L1", UA_MD_INCIDENT_STEPS), _process("ua_md_restoration_l1", "Ukraine–Moldova restoration L1", UA_MD_RESTORATION_STEPS)],
    "timeline": [
        _entry("400kv_interconnector_tripped", "2026-01-31T10:42:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ua_president_incident_address", fact="The 400 kV Romania–Moldova interconnection disconnected", action=_action("romania_moldova_line", "trip", "tripped"), process=("ua_md_incident_l1", "trip_400kv_interconnector"), metrics={"line_voltage_kv": 400}),
        _entry("750kv_corridor_tripped", "2026-01-31T10:42:00.001+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ua_president_incident_address", fact="A 750 kV line between western and central Ukraine disconnected", action=_action("ukraine_750kv_line", "trip", "tripped"), process=("ua_md_incident_l1", "trip_750kv_corridor"), metrics={"line_voltage_kv": 750}),
        _entry("area_separated_from_ce", "2026-01-31T10:45:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_ua_md_notice", fact="The Ukraine–Moldova area separated from Continental Europe", action=_action("synchronous_area", "separate", "separated"), process=("ua_md_incident_l1", "separate_area"), situations=["ua_md_system_separation"]),
        _entry("automatic_protection_activated", "2026-01-31T10:45:00.001+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ua_president_incident_address", fact="Automatic protection and emergency outage schedules activated", action=_action("automatic_protection", "activate", "activated"), process=("ua_md_incident_l1", "activate_protection")),
        _entry("consumer_outages", "2026-01-31T10:45:00.002+02:00", entry_kind="derived", evidence="derived", fact="Protection operation and separation produced significant consumer outages", action=_action("consumer_supply", "interrupt", "significant_outages"), situations=["significant_outages"]),
        _entry("nuclear_units_unloaded", "2026-01-31T10:46:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ua_president_incident_address", fact="Nuclear generation units were unloaded during the disturbance", action=_action("generation", "unload", "nuclear_units_unloaded"), process=("ua_md_incident_l1", "unload_nuclear_units")),
        _entry("joint_restoration_started", "2026-01-31T10:46:00.001+02:00", entry_kind="input", origin="planned_process_start", evidence="reported", source="entsoe_ua_md_notice", fact="Ukrenergo and Moldelectrica immediately activated restoration procedures with neighbouring TSOs", action=_action("restoration", "activate", "active"), process=("ua_md_restoration_l1", "start_joint_restoration")),
        _entry("resynchronised_at_1005_cet", "2026-01-31T11:05:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="entsoe_ua_md_notice", fact="The separated area was resynchronised with Continental Europe at 10:05 CET", action=_action("synchronous_area", "resynchronise", "resynchronised"), process=("ua_md_restoration_l1", "resynchronise_ce"), metrics={"separation_duration_minutes_approx": 20}),
        _entry("consumer_supply_restored", "2026-01-31T20:00:00+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ua_president_incident_address", fact="The pre-incident situation was largely restored during the day", action=_action("consumer_supply", "restore", "restored"), process=("ua_md_restoration_l1", "restore_consumers"), situations=["ua_md_resynchronised"]),
        _entry("systems_stabilized", "2026-01-31T20:00:00.001+02:00", entry_kind="derived", evidence="derived", fact="Joint restoration stabilized the interconnected systems", action=_action("restoration", "stabilize", "stabilized"), process=("ua_md_restoration_l1", "stabilize_systems")),
    ],
    "checkpoints": [
        {"id": "two_distinct_lines_tripped", "after": "area_separated_from_ce", "all": [{"object": "romania_moldova_line", "state": "tripped"}, {"object": "ukraine_750kv_line", "state": "tripped"}]},
        {"id": "resynchronised_in_about_20_minutes", "after": "resynchronised_at_1005_cet", "all": [{"object": "synchronous_area", "state": "resynchronised"}, {"metric": "separation_duration_minutes_approx", "equals": 20}]},
        {"id": "consumer_supply_stabilized", "after": "systems_stabilized", "all": [{"object": "consumer_supply", "state": "restored"}, {"object": "restoration", "state": "stabilized"}]},
    ],
    "expected_final": {"object_states": {"romania_moldova_line": "tripped", "ukraine_750kv_line": "tripped", "synchronous_area": "resynchronised", "automatic_protection": "activated", "generation": "nuclear_units_unloaded", "consumer_supply": "restored", "restoration": "stabilized"}, "situations": ["ua_md_system_separation", "significant_outages", "ua_md_resynchronised"]},
}


_bind_event_model_objects(UA_MD_2026)


UKRAINE_ATTACK_STEPS = [
    _step("record_2024_waves", "Record nine coordinated attack waves in 2024", target="attack_campaign", capability="phase_2024"),
    _step("damage_generation", "Reduce national generation capacity", after=["record_2024_waves"], target="generation_capacity", capability="damage"),
    _step("damage_transmission", "Damage main substations and transmission facilities", after=["damage_generation"], target="transmission_system", capability="damage"),
    _step("damage_distribution", "Damage regional distribution facilities", after=["damage_transmission"], target="distribution_system", capability="damage"),
    _step("record_2025_waves", "Record renewed coordinated waves in late 2025", after=["damage_distribution"], target="attack_campaign", capability="phase_2025"),
    _step("record_2026_winter", "Record systematic electricity and heating attacks in winter 2025–2026", after=["record_2025_waves"], target="attack_campaign", capability="phase_2026"),
    _step("damage_heat", "Disrupt combined heat-and-power and district heating", after=["record_2026_winter"], target="heat_supply", capability="damage"),
]

UKRAINE_IMPACT_STEPS = [
    _step("interrupt_consumers", "Apply prolonged emergency and rolling electricity outages", target="consumer_supply", capability="interrupt"),
    _step("interrupt_water", "Disrupt pumped water and sanitation services", after=["interrupt_consumers"], target="water_services", capability="interrupt"),
    _step("affect_critical_services", "Disrupt healthcare, schools and other civilian services", after=["interrupt_water"], target="critical_services", capability="disrupt"),
]

UKRAINE_RESPONSE_STEPS = [
    _step("activate_restoration", "Mobilize energy repair and humanitarian mitigation", target="restoration", capability="activate"),
    _step("deploy_distributed_support", "Deploy distributed and backup generation", after=["activate_restoration"], target="restoration", capability="deploy_support"),
    _step("continue_repair", "Continue multi-year repair and restoration", after=["deploy_distributed_support"], target="restoration", capability="continue_repair"),
]

UKRAINE_ENERGY_ATTACKS = {
    "schema_version": 2,
    "id": "ukraine-energy-attacks-2022-2026-l1",
    "scenario_id": "ukraine-attacks",
    "name": "Attacks on Ukraine's Energy Infrastructure, 2022–2026 · L1",
    "level": 1,
    "boundary": "stabilization",
    "run_policy": "pause",
    "seed": 42,
    "sources": [
        {"id": "ohchr_energy_2024", "url": "https://ukraine.ohchr.org/en/Attacks-on-Ukraines-Energy-Infrastructure-Harm-to-the-Civilian-Population", "scope": "nine 2024 waves, generation/transmission/distribution damage and cascading civilian-service impacts", "priority": "official_un_report"},
        {"id": "ohchr_energy_2026", "url": "https://ukraine.un.org/en/318327-attacks-against-ukraine%E2%80%99s-energy-infrastructure-and-update-human-rights-situation-ukraine-1", "scope": "winter 2025–2026 systematic attacks, electricity deficit, heating and civilian impacts", "priority": "official_un_update"},
        {"id": "ohchr_january_2026", "url": "https://ukraine.ohchr.org/sites/default/files/2026-02/Ukraine%20-%20protection%20of%20civilians%20in%20armed%20conflict%20%28January%202026%29_ENG.pdf", "scope": "January 2026 attack waves, 11 GW availability versus 18 GW peak demand and affected asset classes", "priority": "official_un_monthly_report"},
    ],
    "model": {
        "id": "qualification-ukraine-attacks",
        "name": "Ukraine energy attacks 2022–2026 · event-specific aggregate L1 topology",
        "level": 1,
        "topology_revision": 1,
        "scope_note": "National aggregate multi-wave attack, diverse generation, transmission, distribution, essential-service impact and restoration topology. It intentionally does not expose precise facility coordinates or represent every strike.",
        "event_targets": {"generation_attack": "ua-generation-zone", "substation_attack": "ua-main-substations", "transmission_attack": "ua-transmission-network"},
        "nodes": [
            {"id": "ua-attack-campaign", "name": "Coordinated long-range attack waves 2022–2026", "component_type_id": "external-hazard", "x": 40, "y": 20, "parameters": {"waves_mar_aug_2024": 9, "waves_oct_nov_2025": 8, "large_scale_waves_jan_2026": 5, "electricity_facility_attacks_oct2025_mar2026_min": 423, "heating_infrastructure_strikes_min": 74}, "qualification_object_id": "attack_campaign"},
            {"id": "ua-nuclear-generation", "name": "Nuclear generation aggregate", "component_type_id": "nuclear-plant", "x": 40, "y": 260, "parameters": {"precise_facilities": "not_exposed"}},
            {"id": "ua-chp-generation", "name": "Thermal and combined heat-and-power generation", "component_type_id": "thermal-plant", "x": 40, "y": 420},
            {"id": "ua-hydro-generation", "name": "Hydropower generation aggregate", "component_type_id": "hydro-plant", "x": 40, "y": 580},
            {"id": "ua-generation-zone", "name": "National available generation capacity", "component_type_id": "grid-zone", "x": 300, "y": 340, "parameters": {"capacity_lost_2024_gw_approx": 9, "available_jan_2026_gw": 11, "peak_need_jan_2026_gw": 18}, "qualification_object_id": "generation_capacity"},
            {"id": "ua-npp-grid-connections", "name": "Substations connecting nuclear plants to the grid", "component_type_id": "transformer-group", "x": 520, "y": 180},
            {"id": "ua-main-substations", "name": "Main high-voltage substations", "component_type_id": "transformer-group", "x": 520, "y": 340},
            {"id": "ua-transmission-network", "name": "National high-voltage transmission network", "component_type_id": "transmission-corridor", "x": 740, "y": 340, "qualification_object_id": "transmission_system"},
            {"id": "ua-distribution-network", "name": "Regional electricity distribution facilities", "component_type_id": "distribution", "x": 960, "y": 340, "qualification_object_id": "distribution_system"},
            {"id": "ua-consumers", "name": "Civilian electricity consumers", "component_type_id": "customer-group", "x": 1180, "y": 340, "parameters": {"demand_mw": 18000, "affected_scope": "millions_during_winter_attacks"}, "qualification_object_id": "consumer_supply"},
            {"id": "ua-district-heating", "name": "CHP and centralized district heating", "component_type_id": "industrial-facility", "x": 740, "y": 580, "parameters": {"disrupted_civilians_scope": "hundreds_of_thousands", "temperature_c_min": -20}, "qualification_object_id": "heat_supply"},
            {"id": "ua-water-services", "name": "Pumped water, sewage and sanitation services", "component_type_id": "industrial-facility", "x": 960, "y": 580, "qualification_object_id": "water_services"},
            {"id": "ua-critical-services", "name": "Healthcare, education and other critical civilian services", "component_type_id": "customer-group", "x": 1180, "y": 580, "qualification_object_id": "critical_services"},
            {"id": "ua-restoration", "name": "Energy repair and humanitarian mitigation", "component_type_id": "response-process", "x": 740, "y": 780, "parameters": {"restoration_horizon": "multi_year"}, "qualification_object_id": "restoration"},
            {"id": "ua-distributed-support", "name": "Distributed and emergency backup generation", "component_type_id": "distributed-generation", "x": 960, "y": 780, "parameters": {"capacity_evidence": "not_quantified"}, "initial_online": False},
        ],
        "edges": [
            {"id": "ua-edge-nuclear-zone", "source": "ua-nuclear-generation", "target": "ua-generation-zone"},
            {"id": "ua-edge-chp-zone", "source": "ua-chp-generation", "target": "ua-generation-zone"},
            {"id": "ua-edge-hydro-zone", "source": "ua-hydro-generation", "target": "ua-generation-zone"},
            {"id": "ua-edge-zone-npp-connection", "source": "ua-generation-zone", "target": "ua-npp-grid-connections"},
            {"id": "ua-edge-npp-main", "source": "ua-npp-grid-connections", "target": "ua-main-substations"},
            {"id": "ua-edge-main-transmission", "source": "ua-main-substations", "target": "ua-transmission-network"},
            {"id": "ua-edge-transmission-distribution", "source": "ua-transmission-network", "target": "ua-distribution-network"},
            {"id": "ua-edge-distribution-consumers", "source": "ua-distribution-network", "target": "ua-consumers"},
            {"id": "ua-edge-chp-heating", "source": "ua-chp-generation", "target": "ua-district-heating", "flow_type": "thermal", "domain": "thermal"},
            {"id": "ua-edge-distribution-water", "source": "ua-distribution-network", "target": "ua-water-services"},
            {"id": "ua-edge-distribution-critical", "source": "ua-distribution-network", "target": "ua-critical-services"},
            {"id": "ua-edge-support-critical", "source": "ua-distributed-support", "target": "ua-critical-services"},
            {"id": "ua-edge-restoration-support", "source": "ua-restoration", "target": "ua-distributed-support", "flow_type": "control", "domain": "control"},
        ],
    },
    "objects": [
        _object("attack_campaign", "Multi-wave attacks on energy infrastructure", "external_hazard", "ongoing_since_2022", ["ongoing_since_2022", "nine_waves_2024", "renewed_waves_2025", "systematic_winter_2026"], {"phase_2024": _transitions(("ongoing_since_2022", "nine_waves_2024")), "phase_2025": _transitions(("nine_waves_2024", "renewed_waves_2025")), "phase_2026": _transitions(("renewed_waves_2025", "systematic_winter_2026"))}),
        _object("generation_capacity", "Available national electricity generation", "generation_group", "degraded_pre_2024", ["degraded_pre_2024", "lost_9gw_2024", "available_11gw_jan_2026"], {"damage": _transitions(("degraded_pre_2024", "lost_9gw_2024")), "winter_degrade": _transitions(("lost_9gw_2024", "available_11gw_jan_2026"))}),
        _object("transmission_system", "Main substations and transmission network", "power_network", "operating_degraded", ["operating_degraded", "repeatedly_damaged"], {"damage": _transitions(("operating_degraded", "repeatedly_damaged"))}),
        _object("distribution_system", "Regional distribution facilities", "power_network", "operating_degraded", ["operating_degraded", "repeatedly_damaged"], {"damage": _transitions(("operating_degraded", "repeatedly_damaged"))}),
        _object("consumer_supply", "Civilian electricity supply", "customer_group", "constrained", ["constrained", "prolonged_rolling_outages"], {"interrupt": _transitions(("constrained", "prolonged_rolling_outages"))}),
        _object("heat_supply", "Centralized heating and hot water", "essential_service", "available_degraded", ["available_degraded", "hundreds_thousands_disrupted"], {"damage": _transitions(("available_degraded", "hundreds_thousands_disrupted"))}),
        _object("water_services", "Water and sanitation", "essential_service", "available", ["available", "power_disrupted"], {"interrupt": _transitions(("available", "power_disrupted"))}),
        _object("critical_services", "Healthcare, education and civilian services", "essential_service", "operating", ["operating", "electricity_heat_water_disrupted"], {"disrupt": _transitions(("operating", "electricity_heat_water_disrupted"))}),
        _object("restoration", "Energy repair and mitigation", "response_process", "continuous", ["continuous", "surge_active", "distributed_support_deployed", "multi_year_repair"], {"activate": _transitions(("continuous", "surge_active")), "deploy_support": _transitions(("surge_active", "distributed_support_deployed")), "continue_repair": _transitions(("distributed_support_deployed", "multi_year_repair"))}),
    ],
    "situations": [
        {"id": "widespread_systematic_energy_attacks", "all": [{"object": "attack_campaign", "state": "systematic_winter_2026"}, {"object": "transmission_system", "state": "repeatedly_damaged"}]},
        {"id": "national_energy_deficit", "all": [{"object": "generation_capacity", "state": "available_11gw_jan_2026"}, {"object": "consumer_supply", "state": "prolonged_rolling_outages"}]},
        {"id": "interdependent_civilian_services_disrupted", "all": [{"object": "heat_supply", "state": "hundreds_thousands_disrupted"}, {"object": "water_services", "state": "power_disrupted"}, {"object": "critical_services", "state": "electricity_heat_water_disrupted"}]},
    ],
    "processes": [_process("ukraine_attack_campaign_l1", "Ukraine energy attack campaign L1", UKRAINE_ATTACK_STEPS), _process("ukraine_civilian_impacts_l1", "Ukraine civilian service impacts L1", UKRAINE_IMPACT_STEPS), _process("ukraine_restoration_l1", "Ukraine restoration and mitigation L1", UKRAINE_RESPONSE_STEPS)],
    "timeline": [
        _entry("nine_attack_waves_2024", "2024-03-22T00:00:00+02:00", entry_kind="input", origin="external_event", evidence="reported", source="ohchr_energy_2024", fact="Nine coordinated large-scale waves attacked generation, transmission and distribution facilities between 22 March and 31 August 2024", action=_action("attack_campaign", "phase_2024", "nine_waves_2024"), process=("ukraine_attack_campaign_l1", "record_2024_waves"), metrics={"large_scale_waves_2024": 9}),
        _entry("generation_lost_9gw_2024", "2024-07-31T12:00:00+03:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ohchr_energy_2024", fact="Providers estimated approximately 9 GW of production capacity lost due to 2024 strikes", action=_action("generation_capacity", "damage", "lost_9gw_2024"), process=("ukraine_attack_campaign_l1", "damage_generation"), metrics={"generation_capacity_lost_gw_approx": 9}),
        _entry("transmission_repeatedly_damaged", "2024-08-31T12:00:00+03:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ohchr_energy_2024", fact="Main transmission facilities and substations were repeatedly damaged", action=_action("transmission_system", "damage", "repeatedly_damaged"), process=("ukraine_attack_campaign_l1", "damage_transmission")),
        _entry("distribution_repeatedly_damaged", "2024-08-31T12:00:00.001+03:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ohchr_energy_2024", fact="Distribution facilities across numerous regions were damaged", action=_action("distribution_system", "damage", "repeatedly_damaged"), process=("ukraine_attack_campaign_l1", "damage_distribution")),
        _entry("eight_waves_late_2025", "2025-11-30T12:00:00+02:00", entry_kind="input", origin="external_event", evidence="reported", source="ohchr_energy_2026", fact="Eight major coordinated waves struck multiple regions in October and November 2025", action=_action("attack_campaign", "phase_2025", "renewed_waves_2025"), process=("ukraine_attack_campaign_l1", "record_2025_waves"), metrics={"large_scale_waves_oct_nov_2025": 8}),
        _entry("systematic_winter_attacks_2026", "2026-01-31T23:59:00+02:00", entry_kind="input", origin="external_event", evidence="reported", source="ohchr_january_2026", fact="January 2026 included near-daily attacks and five large-scale waves across at least 17 regions and Kyiv", action=_action("attack_campaign", "phase_2026", "systematic_winter_2026"), process=("ukraine_attack_campaign_l1", "record_2026_winter"), metrics={"large_scale_waves_january_2026": 5, "affected_regions_min": 17}),
        _entry("generation_available_11gw", "2026-01-31T23:59:00.001+02:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ohchr_january_2026", fact="Available generation was assessed at 11 GW versus 18 GW peak need", action=_action("generation_capacity", "winter_degrade", "available_11gw_jan_2026"), metrics={"available_generation_gw": 11, "peak_need_gw": 18, "deficit_gw": 7}),
        _entry("heating_infrastructure_disrupted", "2026-03-31T12:00:00+03:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ohchr_energy_2026", fact="Systematic attacks on CHP and heating infrastructure disrupted heating and hot water for hundreds of thousands", action=_action("heat_supply", "damage", "hundreds_thousands_disrupted"), process=("ukraine_attack_campaign_l1", "damage_heat"), metrics={"electricity_facility_attacks_oct2025_mar2026_min": 423, "heating_infrastructure_strikes_min": 74, "temperature_c_min": -20}),
        _entry("rolling_electricity_outages", "2026-03-31T12:00:00.001+03:00", entry_kind="derived", evidence="derived", fact="The capacity deficit forced prolonged emergency and scheduled rolling outages", action=_action("consumer_supply", "interrupt", "prolonged_rolling_outages"), process=("ukraine_civilian_impacts_l1", "interrupt_consumers"), situations=["national_energy_deficit"]),
        _entry("water_services_disrupted", "2026-03-31T12:00:00.002+03:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ohchr_energy_2026", fact="Electricity outages cut pumped water, sewage and sanitation services", action=_action("water_services", "interrupt", "power_disrupted"), process=("ukraine_civilian_impacts_l1", "interrupt_water")),
        _entry("critical_services_disrupted", "2026-03-31T12:00:00.003+03:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ohchr_energy_2026", fact="Outages disrupted healthcare, schools and other essential civilian services", action=_action("critical_services", "disrupt", "electricity_heat_water_disrupted"), process=("ukraine_civilian_impacts_l1", "affect_critical_services"), situations=["widespread_systematic_energy_attacks", "interdependent_civilian_services_disrupted"]),
        _entry("restoration_surge_active", "2026-04-01T12:00:00+03:00", entry_kind="input", origin="planned_process_start", evidence="reported", source="ohchr_energy_2026", fact="Energy companies, authorities and humanitarian agencies intensified mitigation and repair", action=_action("restoration", "activate", "surge_active"), process=("ukraine_restoration_l1", "activate_restoration")),
        _entry("distributed_support_deployed", "2026-04-01T12:00:00.001+03:00", entry_kind="derived", evidence="derived", fact="Distributed and backup generation was deployed as a mitigation layer", action=_action("restoration", "deploy_support", "distributed_support_deployed"), process=("ukraine_restoration_l1", "deploy_distributed_support")),
        _entry("multi_year_repair_continues", "2026-05-31T23:59:00+03:00", entry_kind="input", origin="observed_internal_fact", evidence="reported", source="ohchr_energy_2026", fact="Full repair and restoration remained a multi-year effort", action=_action("restoration", "continue_repair", "multi_year_repair"), process=("ukraine_restoration_l1", "continue_repair")),
    ],
    "checkpoints": [
        {"id": "diverse_grid_assets_damaged", "after": "distribution_repeatedly_damaged", "all": [{"object": "generation_capacity", "state": "lost_9gw_2024"}, {"object": "transmission_system", "state": "repeatedly_damaged"}, {"object": "distribution_system", "state": "repeatedly_damaged"}]},
        {"id": "eleven_vs_eighteen_gw", "after": "generation_available_11gw", "all": [{"metric": "available_generation_gw", "equals": 11}, {"metric": "peak_need_gw", "equals": 18}, {"metric": "deficit_gw", "equals": 7}]},
        {"id": "essential_services_disrupted", "after": "critical_services_disrupted", "all": [{"object": "heat_supply", "state": "hundreds_thousands_disrupted"}, {"object": "water_services", "state": "power_disrupted"}, {"object": "critical_services", "state": "electricity_heat_water_disrupted"}]},
    ],
    "expected_final": {"object_states": {"attack_campaign": "systematic_winter_2026", "generation_capacity": "available_11gw_jan_2026", "transmission_system": "repeatedly_damaged", "distribution_system": "repeatedly_damaged", "consumer_supply": "prolonged_rolling_outages", "heat_supply": "hundreds_thousands_disrupted", "water_services": "power_disrupted", "critical_services": "electricity_heat_water_disrupted", "restoration": "multi_year_repair"}, "situations": ["widespread_systematic_energy_attacks", "national_energy_deficit", "interdependent_civilian_services_disrupted"]},
}


_bind_event_model_objects(UKRAINE_ENERGY_ATTACKS)


for _package in (
    SAN_BRUNO,
    NORTHEAST_BLACKOUT,
    STORM_ARWEN,
    GB_2019,
    SOUTH_AUSTRALIA_2016,
    HOKKAIDO_2018,
    SOUTHWEST_2011,
    INDIA_2012,
    TEXAS_2021,
    IBERIA_2025,
    NORTH_HYDE_2025,
    KLEEN_ENERGY_2010,
    MACONDO_2010,
    UA_MD_2026,
    UKRAINE_ENERGY_ATTACKS,
):
    _package["dmn_xml"] = _dmn(f'{_package["id"]}_decisions', _package["situations"])


QUALIFICATION_CASES = {
    package["scenario_id"]: package
    for package in (
        SAN_BRUNO,
        NORTHEAST_BLACKOUT,
        STORM_ARWEN,
        GB_2019,
        SOUTH_AUSTRALIA_2016,
        HOKKAIDO_2018,
        SOUTHWEST_2011,
        INDIA_2012,
        TEXAS_2021,
        IBERIA_2025,
        NORTH_HYDE_2025,
        KLEEN_ENERGY_2010,
        MACONDO_2010,
        UA_MD_2026,
        UKRAINE_ENERGY_ATTACKS,
    )
}
