"""Source-backed participant, asset-model and process-set pilots."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Entity,
    LabAssetActorRole,
    LabEdge,
    LabModelVersion,
    LabNode,
    LabProcessSet,
    LabProcessSetVersion,
    LabProcessSetWorkflow,
    LabProject,
    LabScenario,
    LabScenarioAssemblyLink,
    LabScenarioAssemblyMember,
    LabScenarioAssemblyNodeMap,
    LabScenarioAssemblyVersion,
    LabScenarioProcessBinding,
    LabWorkflow,
    LabWorkflowDefinitionBackup,
    LabWorkflowNode,
    LabWorkflowTransition,
    LabWorkflowVersion,
)
from app.qualification_cases import QUALIFICATION_CASES
from app.services.bpmn_profile import build_bpmn_xml, meaningful_end_name, validate_bpmn


PILOT_PARTICIPANTS = {
    "southwest-2011": {
        "source": "https://www.ferc.gov/sites/default/files/2020-04/Arizona-Southern%20California%20Outages%20on%20September%208,%202011.pdf",
        "actors": [
            {"alias": "aps", "id": "org-aps", "name": "Arizona Public Service", "kind": "company", "role": "transmission_operator", "nodes": ["sw-external-west", "sw-hng-line"], "processes": [
                {"id": "aps-hng-response", "name": "APS H-NG switching and restoration response", "start_events": ["operator_error"], "scope_kind": "asset_instance", "scope_ref": "sw-hng-line", "steps": [("event_trigger", "recognize_fault", "Recognize H-NG fault", "operator_error"), ("component_command", "isolate_line", "Isolate and assess H-NG", "hng.isolation_started"), ("component_command", "restore_line", "Restore H-NG", "hng.restoration_started")], "emit": [("grid.disturbance_notified", "iid"), ("grid.disturbance_notified", "sce"), ("grid.disturbance_notified", "sdge"), ("grid.disturbance_notified", "cfe")]},
            ]},
            {"alias": "iid", "id": "org-iid", "name": "Imperial Irrigation District", "kind": "company", "role": "transmission_operator", "nodes": ["sw-cv-transformers", "sw-ramon-transformer", "sw-iid-north"], "processes": [
                {"id": "iid-overload-response", "name": "IID overload and transformer response", "start_events": ["grid.disturbance_notified", "overload"], "scope_kind": "asset_class", "scope_ref": "transformer-group", "steps": [("event_trigger", "receive_disturbance", "Receive disturbance indication", "grid.disturbance_notified"), ("metric_check", "assess_overload", "Assess transformer loading", "overload"), ("component_command", "protect_assets", "Apply protection and switching", "iid.protection_operated")]},
            ]},
            {"alias": "sce", "id": "org-sce", "name": "Southern California Edison", "kind": "company", "role": "generation_and_transmission_operator", "nodes": ["sw-songs-nuclear", "sw-path44", "sw-songs-scheme"], "processes": [
                {"id": "sce-separation-response", "name": "SCE/SONGS separation response", "start_events": ["grid.disturbance_notified", "overload"], "scope_kind": "asset_class", "scope_ref": "protection-system", "steps": [("event_trigger", "detect_threshold", "Detect separation threshold", "overload"), ("component_command", "operate_scheme", "Operate SONGS separation scheme", "songs.separation_operated")]},
            ]},
            {"alias": "sdge", "id": "org-sdge", "name": "San Diego Gas & Electric", "kind": "company", "role": "distribution_operator", "nodes": ["sw-sdge-grid", "sw-regional-system", "sw-yuma-pocket", "sw-customer-supply", "sw-restoration"], "processes": [
                {"id": "sdge-system-restoration", "name": "SDG&E system restoration", "start_events": ["grid.disturbance_notified", "overload"], "scope_kind": "actor", "scope_ref": None, "steps": [("event_trigger", "declare_disturbance", "Declare regional disturbance", "grid.disturbance_notified"), ("python_action", "assess_islands", "Assess islands and customer impact", "overload"), ("component_command", "coordinate_restoration", "Coordinate staged restoration", "restoration.started")]},
            ]},
            {"alias": "cfe", "id": "org-cfe", "name": "Comisión Federal de Electricidad", "kind": "state_company", "role": "system_operator", "nodes": ["sw-s-line", "sw-cfe-grid"], "processes": [
                {"id": "cfe-separation-restoration", "name": "CFE Baja California separation and restoration", "start_events": ["grid.disturbance_notified", "overload"], "scope_kind": "actor", "scope_ref": None, "steps": [("event_trigger", "detect_separation", "Detect Baja California separation", "overload"), ("component_command", "stabilize_system", "Stabilize isolated system", "cfe.stabilization_started"), ("component_command", "restore_load", "Restore interrupted load", "cfe.restoration_started")]},
            ]},
        ],
    },
    "macondo": {
        "source": "https://www.csb.gov/macondo-blowout-and-explosion/",
        "actors": [
            {"alias": "bp", "id": "org-bp-macondo", "name": "BP Exploration & Production", "kind": "company", "role": "lease_operator", "nodes": ["mc-reservoir", "mc-cement-barrier", "mc-negative-test", "mc-wellbore", "mc-riser", "mc-spill-zone"], "processes": [
                {"id": "bp-well-control", "name": "BP Macondo well-control response", "start_events": ["barrier_failure"], "scope_kind": "asset_instance", "scope_ref": "mc-cement-barrier", "steps": [("event_trigger", "detect_barrier_failure", "Detect loss of well barrier", "barrier_failure"), ("condition", "evaluate_negative_test", "Evaluate negative-pressure test", "well.test_evaluated"), ("component_command", "initiate_well_control", "Initiate well-control response", "well.control_started")], "emit": [("well.control_emergency", "transocean"), ("well.control_emergency", "unified-command")]},
            ]},
            {"alias": "transocean", "id": "org-transocean-dwh", "name": "Transocean / Deepwater Horizon", "kind": "company", "role": "drilling_contractor", "nodes": ["mc-bop", "mc-mud-gas", "mc-deepwater-horizon", "mc-crew"], "processes": [
                {"id": "dwh-emergency-response", "name": "Deepwater Horizon emergency response", "start_events": ["well.control_emergency", "uncontrolled_flow"], "scope_kind": "actor", "scope_ref": None, "steps": [("event_trigger", "receive_well_emergency", "Receive well-control emergency", "well.control_emergency"), ("component_command", "operate_bop", "Attempt BOP isolation", "uncontrolled_flow"), ("component_command", "evacuate_crew", "Evacuate crew", "fire")]},
            ]},
            {"alias": "unified-command", "id": "org-dwh-unified-command", "name": "Deepwater Horizon Unified Command", "kind": "state_response", "role": "incident_coordinator", "nodes": ["mc-spill-response"], "processes": [
                {"id": "federal-spill-response", "name": "Federal spill and well-control response", "start_events": ["well.control_emergency", "fire"], "scope_kind": "jurisdiction", "scope_ref": "US-federal", "steps": [("event_trigger", "activate_command", "Activate incident command", "well.control_emergency"), ("resource_operation", "mobilize_response", "Mobilize spill and well-control resources", "fire"), ("component_command", "stabilize_response", "Coordinate containment and stabilization", "spill.response_active")]},
            ]},
            {"alias": "csb", "id": "org-us-csb", "name": "U.S. Chemical Safety Board", "kind": "state_regulator", "role": "investigator", "nodes": ["mc-investigation"], "processes": [
                {"id": "csb-macondo-investigation", "name": "CSB Macondo investigation", "start_events": ["fire"], "scope_kind": "jurisdiction", "scope_ref": "US-federal", "steps": [("event_trigger", "open_investigation", "Open investigation", "fire"), ("python_action", "collect_evidence", "Collect and analyze evidence", "investigation.started"), ("success", "publish_findings", "Complete investigation", "investigation.completed")]},
            ]},
        ],
    },
    "storm-arwen-2021": {
        "source": "https://assets.publishing.service.gov.uk/media/629fa8b1d3bf7f0371a9b0ca/storm-arwen-review-final-report.pdf",
        "actors": [
            {"alias": "met-office", "id": "org-uk-met-office", "name": "UK Met Office", "kind": "state_agency", "role": "weather_warning_provider", "nodes": ["ar-weather"], "processes": [
                {"id": "storm-warning", "name": "Severe-weather warning process", "start_events": ["severe_weather_arrival"], "scope_kind": "jurisdiction", "scope_ref": "GB", "steps": [("event_trigger", "issue_warning", "Issue severe-weather warning", "severe_weather_arrival"), ("success", "maintain_updates", "Maintain forecast updates", "weather.warning_active")]},
            ]},
            {"alias": "dno", "id": "org-gb-dno-arwen", "name": "Affected Great Britain distribution network operators", "kind": "company_group", "role": "distribution_operator", "nodes": ["ar-upstream-generation", "ar-grid-supply-point", "ar-hv-segment", "ar-primary-substation", "ar-distribution-segment", "ar-nested-fault-section", "ar-customers", "ar-site-access"], "processes": [
                {"id": "dno-storm-restoration", "name": "DNO storm damage and restoration", "start_events": ["line_fault", "distribution_fault"], "scope_kind": "asset_class", "scope_ref": "distribution", "steps": [("event_trigger", "detect_damage", "Detect widespread network damage", "line_fault"), ("python_action", "assess_access", "Assess damage and safe access", "damage_assessment"), ("python_action", "create_work", "Create repair work orders", "work_order_created"), ("component_command", "restore_supply", "Test and restore customer supply", "load_restoration")], "emit": [("mutual_aid.requested", "newsac"), ("prolonged_outage.reported", "ofgem-beis")]},
            ]},
            {"alias": "newsac", "id": "org-newsac", "name": "NEWSAC mutual-aid coordination", "kind": "coordination_body", "role": "mutual_aid_coordinator", "nodes": ["ar-coordination", "ar-line-crews", "ar-line-materials", "ar-mobile-generation"], "processes": [
                {"id": "newsac-mutual-aid", "name": "NEWSAC mutual-aid mobilisation", "start_events": ["mutual_aid.requested"], "scope_kind": "actor", "scope_ref": None, "steps": [("event_trigger", "receive_request", "Receive mutual-aid request", "mutual_aid.requested"), ("resource_operation", "reserve_crews", "Reserve mutual-aid crews", "crew_reserved"), ("resource_operation", "dispatch_support", "Dispatch crews and mobile generation", "crew_departed")]},
            ]},
            {"alias": "ofgem-beis", "id": "org-ofgem-beis", "name": "Ofgem and UK government coordination", "kind": "state_regulator", "role": "oversight_and_coordination", "nodes": [], "processes": [
                {"id": "national-outage-oversight", "name": "National prolonged-outage oversight", "start_events": ["prolonged_outage.reported"], "scope_kind": "jurisdiction", "scope_ref": "GB", "steps": [("event_trigger", "receive_report", "Receive prolonged-outage report", "prolonged_outage.reported"), ("metric_check", "monitor_restoration", "Monitor restoration and vulnerable customers", "restoration_84_1"), ("success", "close_oversight", "Close emergency oversight", "restoration_complete")]},
            ]},
        ],
    },
}


AUTO_PROCESS_OWNERS = {
    "san-bruno-2010": [
        ("pge", "org-pge-san-bruno", "Pacific Gas and Electric Company", "company", "gas_transmission_operator", ["gas_pipeline_rupture_response_l1"]),
    ],
    "northeast-2003": [
        ("firstenergy", "org-firstenergy-2003", "FirstEnergy", "company", "transmission_operator", ["grid_disturbance_containment_l1"]),
        ("regional-ops", "org-regional-ops-2003", "MISO / PJM regional coordination", "coordination_body", "reliability_coordinator", ["wide_area_stabilization_l1"]),
    ],
    "gb-2019": [
        ("ngeso", "org-ngeso-2019", "National Grid Electricity System Operator", "company", "system_operator", ["gb_frequency_emergency_response_l1"]),
    ],
    "south-australia-2016": [
        ("electranet", "org-electranet-2016", "ElectraNet and connected generation", "company_group", "network_operator", ["sa_automatic_cascade_l1"]),
        ("aemo", "org-aemo-2016", "Australian Energy Market Operator", "system_operator", "system_and_market_operator", ["sa_system_recovery_l1"]),
    ],
    "hokkaido-2018": [
        ("hepco", "org-hepco-2018", "Hokkaido Electric Power Company", "company", "system_operator", ["hokkaido_frequency_cascade_l1", "hokkaido_black_start_recovery_l1"]),
    ],
    "india-2012": [
        ("posoco", "org-posoco-2012", "POSOCO / National and Regional Load Despatch Centres", "state_company", "system_operator", ["india_day1_cascade_l1", "india_day2_cascade_l1"]),
        ("powergrid", "org-powergrid-2012", "POWERGRID and regional restoration coordination", "state_company", "transmission_operator", ["india_day1_recovery_l1", "india_day2_recovery_l1"]),
    ],
    "texas-2021": [
        ("generation-gas", "org-texas-generation-gas-2021", "Texas generation and natural-gas operators", "company_group", "asset_operator", ["texas_cold_preparation_l1"]),
        ("ercot", "org-ercot-2021", "Electric Reliability Council of Texas", "system_operator", "system_operator", ["texas_frequency_emergency_l1", "texas_recovery_l1"]),
        ("utilities", "org-texas-utilities-2021", "Texas transmission and distribution utilities", "company_group", "distribution_operator", ["texas_prolonged_emergency_l1"]),
    ],
    "iberia-2025": [
        ("generation", "org-iberian-generation-2025", "Iberian generation operators", "company_group", "generation_operator", ["iberia_preincident_l1"]),
        ("ree", "org-ree-2025", "Red Eléctrica de España", "company", "transmission_system_operator", ["iberia_cascade_l1"]),
        ("ree-ren", "org-ree-ren-2025", "REE / REN restoration coordination", "coordination_body", "cross_border_restoration", ["iberia_restoration_l1"]),
    ],
    "north-hyde-2025": [
        ("nged", "org-national-grid-north-hyde", "National Grid Electricity Transmission", "company", "transmission_operator", ["north_hyde_failure_l1", "north_hyde_customer_restoration_l1"]),
        ("fire-service", "org-london-fire-north-hyde", "London Fire Brigade and site responders", "emergency_service", "incident_response", ["north_hyde_fire_response_l1"]),
        ("heathrow", "org-heathrow-2025", "Heathrow Airport Limited", "company", "critical_infrastructure_operator", ["north_hyde_heathrow_l1"]),
    ],
    "kleen-energy": [
        ("kleen", "org-kleen-energy", "Kleen Energy Systems and construction contractors", "company_group", "facility_operator", ["kleen_preparation_l1", "kleen_explosion_l1"]),
        ("csb", "org-us-csb-kleen", "U.S. Chemical Safety Board", "state_regulator", "investigator", ["kleen_investigation_l1"]),
    ],
    "ua-md-2026": [
        ("moldelectrica", "org-moldelectrica-2026", "Moldelectrica", "state_company", "transmission_system_operator", ["ua_md_incident_l1"]),
        ("ukrenergo", "org-ukrenergo-2026", "NPC Ukrenergo and joint restoration coordination", "state_company", "transmission_system_operator", ["ua_md_restoration_l1"]),
    ],
    "ukraine-attacks": [
        ("energy-operators", "org-ukraine-energy-operators", "Ukrainian electricity and heat operators", "company_group", "energy_operator", ["ukraine_attack_campaign_l1", "ukraine_restoration_l1"]),
        ("civil-services", "org-ukraine-civil-services", "Civilian and critical-service operators", "public_service_group", "essential_service_operator", ["ukraine_civilian_impacts_l1"]),
    ],
}


def _process_event(package: dict, process_id: str, step_id: str) -> str:
    for item in package.get("timeline", []):
        process = item.get("process") or {}
        if process.get("id") == process_id and process.get("step") == step_id:
            return str((item.get("action") or {}).get("capability") or item.get("id") or step_id)
    return step_id


def _workflow_process(package: dict, process: dict) -> dict:
    steps = []
    for index, step in enumerate(process.get("steps", [])):
        name = step.get("name") or step["id"]
        lowered = name.lower()
        if index == 0:
            block = "event_trigger"
        elif step.get("target") and step.get("capability"):
            block = "component_command"
        elif any(word in lowered for word in ("assess", "check", "monitor", "verify", "evaluate", "measure")):
            block = "metric_check"
        elif step.get("branch") not in (None, "", "main"):
            block = "condition"
        elif index == len(process.get("steps", [])) - 1:
            block = "success"
        else:
            block = "python_action"
        steps.append((block, step["id"], name, _process_event(package, process["id"], step["id"])))
    start_event = steps[0][3] if steps else f"{process['id']}.start"
    return {"id": process["id"], "name": process.get("name") or process["id"], "start_events": [start_event], "scope_kind": "actor", "scope_ref": None, "steps": steps}


def _qualification_participants(scenario_id: str) -> dict | None:
    package = QUALIFICATION_CASES.get(scenario_id)
    owners = AUTO_PROCESS_OWNERS.get(scenario_id)
    if not package or not owners:
        return None
    source = (package.get("sources") or [{}])[0].get("url") or f"https://aftertime.local/scenarios/{scenario_id}"
    processes = {item["id"]: item for item in package.get("processes", [])}
    node_by_object = {item.get("qualification_object_id"): item["id"] for item in package.get("model", {}).get("nodes", []) if item.get("qualification_object_id")}
    actors = []
    claimed: set[str] = set()
    for alias, entity_id, name, kind, role, process_ids in owners:
        owned_processes = [processes[item] for item in process_ids if item in processes]
        target_objects = {step.get("target") for process in owned_processes for step in process.get("steps", []) if step.get("target")}
        nodes = [node_by_object[item] for item in target_objects if item in node_by_object and node_by_object[item] not in claimed]
        claimed.update(nodes)
        actors.append({"alias": alias, "id": entity_id, "name": name, "kind": kind, "role": role, "nodes": nodes, "processes": [_workflow_process(package, process) for process in owned_processes]})
    all_nodes = [item["id"] for item in package.get("model", {}).get("nodes", [])]
    if actors:
        actors[0]["nodes"] = list(dict.fromkeys([*actors[0]["nodes"], *(item for item in all_nodes if item not in claimed)]))
    return {"source": source, "actors": actors}


def _generic_participants(scenario: LabScenario, source_nodes: dict[str, LabNode]) -> dict:
    alias = "system-operator"
    source = f"https://aftertime.local/scenarios/{scenario.id}"
    return {"source": source, "actors": [{
        "alias": alias,
        "id": _id("org", scenario.id, alias),
        "name": f"{scenario.name} · system operator",
        "kind": "system_operator",
        "role": "scenario_operator",
        "nodes": list(source_nodes),
        "processes": [{
            "id": f"{scenario.id}-response",
            "name": f"{scenario.name} · monitoring and response",
            "start_events": ["scenario.started"],
            "scope_kind": "actor",
            "scope_ref": None,
            "steps": [
                ("event_trigger", "receive_event", "Receive scenario event", "scenario.started"),
                ("metric_check", "assess_state", "Assess model state", "state.assessed"),
                ("component_command", "coordinate_response", "Coordinate operational response", "response.started"),
                ("success", "close_response", "Complete scenario response", "response.completed"),
            ],
        }],
    }]}


def _checksum(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _id(prefix: str, *parts: object) -> str:
    """Keep deterministic seed identifiers inside the platform's 80-char PK contract."""
    value = "-".join([prefix, *(str(part) for part in parts)])
    if len(value) <= 80:
        return value
    digest = sha256(value.encode()).hexdigest()[:12]
    return f"{value[:67]}-{digest}"


def _evidence(source: str, *, kind: str = "reported", note: str = "Official investigation or regulator review") -> dict:
    return {"kind": kind, "source_url": source, "source_locator": note, "confidence": 1.0 if kind == "reported" else 0.7}


def _workflow_description(scenario_name: str, actor_name: str, process: dict) -> str:
    """Build a concise, scenario-specific Ukrainian explanation for a BPMN model."""
    triggers = ", ".join(process.get("start_events", [])) or "налаштованої події сценарію"
    step_count = len(process.get("steps", []))
    scope = process.get("scope_ref") or process.get("scope_kind") or "організації-учасника"
    return (
        f"Ця схема BPMN 2.0 описує реагування організації «{actor_name}» у сценарії «{scenario_name}». "
        f"Процес запускається після отримання події «{triggers}» та застосовується до області або об’єкта «{scope}». "
        f"Схема містить {step_count} послідовні операційні кроки, координує дії учасника та формує події, "
        "які використовує середовище виконання сценарію."
    )


def _backup_workflow_definition(db: Session, version: LabWorkflowVersion) -> None:
    """Keep one rollback snapshot before the in-place BPMN 2.0 migration."""
    backup_id = _id("bpmn-backup", version.id)
    if db.get(LabWorkflowDefinitionBackup, backup_id):
        return
    nodes = list(
        db.scalars(
            select(LabWorkflowNode).where(
                LabWorkflowNode.workflow_version_id == version.id
            )
        )
    )
    transitions = list(
        db.scalars(
            select(LabWorkflowTransition).where(
                LabWorkflowTransition.workflow_version_id == version.id
            )
        )
    )
    db.add(
        LabWorkflowDefinitionBackup(
            id=backup_id,
            workflow_version_id=version.id,
            bpmn_xml=version.bpmn_xml or "",
            nodes=[
                {
                    "id": node.id,
                    "node_key": node.node_key,
                    "block_type": node.block_type,
                    "name": node.name,
                    "x": node.x,
                    "y": node.y,
                    "config": deepcopy(node.config),
                    "python_code": node.python_code,
                }
                for node in nodes
            ],
            transitions=[
                {
                    "id": flow.id,
                    "source_node_id": flow.source_node_id,
                    "target_node_id": flow.target_node_id,
                    "condition_code": flow.condition_code,
                    "priority": flow.priority,
                }
                for flow in transitions
            ],
        )
    )


def _semantic_block(block: str, *, is_last: bool) -> tuple[str, str]:
    if block in {"success", "failure"}:
        return "end_event", "error" if block == "failure" else "none"
    mapping = {
        "event_trigger": "intermediate_catch_event",
        "timer": "intermediate_catch_event",
        "wait": "intermediate_catch_event",
        "component_command": "service_task",
        "resource_operation": "service_task",
        "python_action": "script_task",
        "metric_check": "business_rule_task",
        # A decision calculation is work; an exclusive gateway only routes its result.
        "condition": "business_rule_task",
        "manual_command": "manual_task",
    }
    return mapping.get(block, block), "none"


def _replace_seeded_process(
    db: Session,
    *,
    scenario_id: str,
    process: dict,
    version: LabWorkflowVersion,
    source: str,
) -> None:
    """Replace a seeded legacy graph with an explicit executable BPMN path."""
    _backup_workflow_definition(db, version)
    db.execute(
        delete(LabWorkflowTransition).where(
            LabWorkflowTransition.workflow_version_id == version.id
        )
    )
    db.execute(
        delete(LabWorkflowNode).where(LabWorkflowNode.workflow_version_id == version.id)
    )
    db.flush()

    raw_steps = list(process.get("steps", []))
    start_event = (process.get("start_events") or [f"{process['id']}.started"])[0]
    start_name = f"Отримано подію: {start_event}"
    if raw_steps and raw_steps[0][0] == "event_trigger" and raw_steps[0][3] in process.get("start_events", []):
        start_name = raw_steps[0][2]
        raw_steps = raw_steps[1:]
    start_id = _id("workflow-node", scenario_id, process["id"], "start")
    start_node = LabWorkflowNode(
        id=start_id,
        workflow_version_id=version.id,
        node_key="start",
        block_type="start_event",
        name=start_name,
        x=60,
        y=140,
        config={
            "event_definition": "message",
            "event_type": start_event,
            "evidence": _evidence(source),
        },
        python_code="",
    )
    db.add(start_node)
    nodes = [start_node]
    for step_index, (legacy_block, key, name, event_type) in enumerate(raw_steps, 1):
        block, result = _semantic_block(legacy_block, is_last=step_index == len(raw_steps))
        config: dict[str, Any] = {
            "event_type": event_type,
            "evidence": _evidence(
                source,
                kind="derived",
                note="Explicit BPMN reconstruction from the cited sequence",
            ),
        }
        if block == "intermediate_catch_event":
            config["event_definition"] = "timer" if legacy_block in {"timer", "wait"} else "message"
        elif block == "end_event":
            config["event_definition"] = result
        elif block in {"service_task", "script_task", "business_rule_task", "manual_task", "user_task"}:
            config["capability"] = event_type
            if process.get("scope_ref"):
                config["target_ref"] = process["scope_ref"]
        node = LabWorkflowNode(
            id=_id("workflow-node", scenario_id, process["id"], key),
            workflow_version_id=version.id,
            node_key=key,
            block_type=block,
            name=name,
            x=60 + step_index * 220,
            y=140,
            config=config,
            python_code="",
        )
        db.add(node)
        nodes.append(node)
    if len(nodes) == 1 or nodes[-1].block_type != "end_event":
        predecessor_name = nodes[-1].name if len(nodes) > 1 else None
        end_node = LabWorkflowNode(
            id=_id("workflow-node", scenario_id, process["id"], "end"),
            workflow_version_id=version.id,
            node_key="end",
            block_type="end_event",
            name=meaningful_end_name(process["name"], predecessor_name),
            x=60 + len(nodes) * 220,
            y=140,
            config={"event_definition": "none", "outcome": "completed"},
            python_code="",
        )
        db.add(end_node)
        nodes.append(end_node)
    db.flush()
    flows: list[LabWorkflowTransition] = []
    for index, (source_node, target_node) in enumerate(zip(nodes, nodes[1:]), 1):
        flow = LabWorkflowTransition(
            id=_id("workflow-transition", scenario_id, process["id"], index),
            workflow_version_id=version.id,
            source_node_id=source_node.id,
            target_node_id=target_node.id,
            condition_code="True",
            priority=100,
        )
        db.add(flow)
        flows.append(flow)
    db.flush()
    version.bpmn_xml = build_bpmn_xml(process["id"], version.name, nodes, flows)
    version.bpmn_profile = "aftertime-executable-1"
    version.validation = validate_bpmn(version.bpmn_xml)
    version.validated_at = datetime.now(UTC)


def _migrate_legacy_workflow(db: Session, version: LabWorkflowVersion) -> None:
    """Make non-catalog workflows explicit without discarding their business steps."""
    _backup_workflow_definition(db, version)
    nodes = list(
        db.scalars(
            select(LabWorkflowNode)
            .where(LabWorkflowNode.workflow_version_id == version.id)
            .order_by(LabWorkflowNode.x, LabWorkflowNode.y)
        )
    )
    flows = list(
        db.scalars(
            select(LabWorkflowTransition)
            .where(LabWorkflowTransition.workflow_version_id == version.id)
            .order_by(LabWorkflowTransition.priority, LabWorkflowTransition.id)
        )
    )
    if not nodes:
        return
    for node in nodes:
        semantic, result = _semantic_block(node.block_type, is_last=False)
        config = deepcopy(node.config or {})
        if node.block_type in {"start", "start_event"}:
            semantic = "start_event"
            config["event_definition"] = config.get("event_definition") or config.get("start_mode") or "message"
            node.name = node.name if node.name != "Start by event" else f"Отримано подію: {config.get('event_type', 'запуск процесу')}"
        elif semantic == "intermediate_catch_event":
            config["event_definition"] = config.get("event_definition") or "message"
        elif semantic == "end_event":
            config["event_definition"] = config.get("event_definition") or result
        node.block_type = semantic
        node.config = config
    sinks = {node.id for node in nodes} - {flow.source_node_id for flow in flows}
    if not any(node.block_type == "end_event" for node in nodes):
        predecessor = max(
            (node for node in nodes if node.id in sinks),
            key=lambda item: (item.x, item.y),
            default=None,
        )
        end = LabWorkflowNode(
            id=_id("workflow-node", version.id, "end"),
            workflow_version_id=version.id,
            node_key="end",
            block_type="end_event",
            name=meaningful_end_name(version.name, predecessor.name if predecessor else None),
            x=max(node.x for node in nodes) + 220,
            y=sum(node.y for node in nodes) / len(nodes),
            config={"event_definition": "none", "outcome": "completed"},
            python_code="",
        )
        db.add(end)
        db.flush()
        for index, sink in enumerate(sorted(sinks), 1):
            flow = LabWorkflowTransition(
                id=_id("workflow-transition", version.id, "end", index),
                workflow_version_id=version.id,
                source_node_id=sink,
                target_node_id=end.id,
                condition_code="True",
                priority=100,
            )
            db.add(flow)
            flows.append(flow)
        nodes.append(end)
    start_nodes = [node for node in nodes if node.block_type == "start_event"]
    end_nodes = [node for node in nodes if node.block_type == "end_event"]
    outgoing_ids: dict[str, list[str]] = {}
    incoming_ids: dict[str, list[str]] = {}
    for flow in flows:
        outgoing_ids.setdefault(flow.source_node_id, []).append(flow.target_node_id)
        incoming_ids.setdefault(flow.target_node_id, []).append(flow.source_node_id)
    reachable: set[str] = set()
    pending = [node.id for node in start_nodes]
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending.extend(outgoing_ids.get(current, []))
    unreachable = {node.id for node in nodes} - reachable
    # Preserve user-created legacy elements by attaching each disconnected component
    # as an explicit branch instead of silently deleting it during migration.
    if start_nodes and end_nodes and unreachable:
        component_heads = sorted(
            (
                node
                for node in nodes
                if node.id in unreachable
                and not any(source in unreachable for source in incoming_ids.get(node.id, []))
            ),
            key=lambda item: (item.x, item.y, item.node_key),
        )
        for index, head in enumerate(component_heads, 1):
            flow = LabWorkflowTransition(
                id=_id("workflow-transition", version.id, "orphan-start", index),
                workflow_version_id=version.id,
                source_node_id=start_nodes[0].id,
                target_node_id=head.id,
                condition_code="True",
                priority=200 + index,
            )
            db.add(flow)
            flows.append(flow)
        component_sinks = sorted(
            (
                node
                for node in nodes
                if node.id in unreachable and not outgoing_ids.get(node.id)
            ),
            key=lambda item: (item.x, item.y, item.node_key),
        )
        for index, sink in enumerate(component_sinks, 1):
            flow = LabWorkflowTransition(
                id=_id("workflow-transition", version.id, "orphan-end", index),
                workflow_version_id=version.id,
                source_node_id=sink.id,
                target_node_id=end_nodes[0].id,
                condition_code="True",
                priority=300 + index,
            )
            db.add(flow)
            flows.append(flow)
    db.flush()
    version.bpmn_xml = build_bpmn_xml(version.workflow_id, version.name, nodes, flows)
    version.bpmn_profile = "aftertime-executable-1"
    version.validation = validate_bpmn(version.bpmn_xml)
    version.validated_at = datetime.now(UTC)


def _node_permissions(scenario_id: str, node_id: str) -> list[str]:
    package = QUALIFICATION_CASES.get(scenario_id)
    if not package:
        return ["observe"]
    object_id = next((item.get("qualification_object_id") for item in package["model"]["nodes"] if item["id"] == node_id), None)
    definition = next((item for item in package.get("objects", []) if item["id"] == object_id), None)
    return sorted((definition or {}).get("capabilities", {}).keys()) or ["observe"]


def seed_participant_process_pilots(db: Session) -> None:
    """Idempotently materialize participant models and BPMN process sets for every scenario."""
    scenarios = list(db.scalars(select(LabScenario).order_by(LabScenario.id)))
    seeded_descriptions: dict[str, str] = {}
    for scenario in scenarios:
        scenario_id = scenario.id
        if not scenario.model_version_id:
            continue
        source_model = db.get(LabModelVersion, scenario.model_version_id)
        source_nodes = {item.id: item for item in db.scalars(select(LabNode).where(LabNode.model_version_id == scenario.model_version_id))}
        source_edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == scenario.model_version_id)))
        spec = PILOT_PARTICIPANTS.get(scenario_id) or _qualification_participants(scenario_id) or _generic_participants(scenario, source_nodes)
        source = spec["source"]
        assembly_id = _id("assembly", scenario_id, "v1")
        assembly = db.get(LabScenarioAssemblyVersion, assembly_id)
        if not assembly:
            assembly = LabScenarioAssemblyVersion(id=assembly_id, scenario_id=scenario_id, version=1, status="published", name=f"{scenario.name} · participant composition", composite_model_version_id=scenario.model_version_id, published_at=datetime.now(UTC))
            db.add(assembly)
            db.flush()
        node_members: dict[str, LabScenarioAssemblyMember] = {}
        member_payload: list[dict] = []
        for actor_index, actor in enumerate(spec["actors"]):
            entity = db.get(Entity, actor["id"])
            if not entity:
                entity = Entity(id=actor["id"], kind=actor["kind"], level="organization", name=actor["name"], symbol=None, description=f"Participant in {scenario.name}", jurisdiction=None, valid_from=None, valid_to=None, attributes={"source_url": source})
                db.add(entity)
            project_id = _id("participant-project", scenario_id, actor["alias"])
            project = db.get(LabProject, project_id)
            if not project:
                project = LabProject(id=project_id, name=f"{actor['name']} · {scenario.name}", description="Participant-owned asset model")
                db.add(project)
            model_id = _id("participant-model", scenario_id, actor["alias"], "v1")
            participant_model = db.get(LabModelVersion, model_id)
            if not participant_model:
                participant_model = LabModelVersion(id=model_id, project_id=project_id, version=1, status="published", name=f"{actor['name']} · assets", timezone=source_model.timezone, settings={"scenario_id": scenario_id, "participant_alias": actor["alias"], "source_url": source}, architecture_version=3, semantic_revision=1, published_at=datetime.now(UTC))
                db.add(participant_model)
                db.flush()
                project.published_version_id = model_id
            cloned: dict[str, str] = {}
            for source_node_id in actor["nodes"]:
                original = source_nodes[source_node_id]
                clone_id = _id("pm", scenario_id, actor["alias"], source_node_id)
                clone = db.get(LabNode, clone_id)
                if not clone:
                    clone = LabNode(id=clone_id, model_version_id=model_id, component_type_id=original.component_type_id, name=original.name, parent_node_id=None, x=original.x, y=original.y, parameters=deepcopy(original.parameters), initial_state=deepcopy(original.initial_state), python_code=original.python_code, refinement_contract=deepcopy(original.refinement_contract), instance_key=original.instance_key or source_node_id, port_overrides=deepcopy(original.port_overrides), observable_overrides=deepcopy(original.observable_overrides))
                    db.add(clone)
                    db.flush()
                cloned[source_node_id] = clone_id
                db.merge(LabAssetActorRole(id=_id("role", scenario_id, actor["alias"], source_node_id), model_version_id=model_id, node_id=clone_id, entity_id=actor["id"], role=actor["role"], permissions=_node_permissions(scenario_id, source_node_id), evidence=_evidence(source)))
            for edge in source_edges:
                if edge.source_node_id in cloned and edge.target_node_id in cloned:
                    db.merge(LabEdge(id=_id("pm-edge", scenario_id, actor["alias"], edge.id), model_version_id=model_id, source_node_id=cloned[edge.source_node_id], source_port=edge.source_port, target_node_id=cloned[edge.target_node_id], target_port=edge.target_port, flow_type=edge.flow_type, parameters=deepcopy(edge.parameters), connection_key=edge.connection_key or edge.id, domain=edge.domain, enabled=edge.enabled))
            member_id = _id("member", scenario_id, actor["alias"])
            member = db.get(LabScenarioAssemblyMember, member_id)
            if not member:
                member = LabScenarioAssemblyMember(id=member_id, assembly_version_id=assembly_id, alias=actor["alias"], entity_id=actor["id"], model_version_id=model_id if actor["nodes"] else None, participant_kind=actor["kind"], role=actor["role"], evidence=_evidence(source))
                db.add(member)
                db.flush()
            member_payload.append({"alias": actor["alias"], "entity": actor["id"], "model": member.model_version_id})
            for source_node_id in actor["nodes"]:
                node_members[source_node_id] = member
                db.merge(LabScenarioAssemblyNodeMap(id=_id("map", scenario_id, actor["alias"], source_node_id), assembly_version_id=assembly_id, member_id=member_id, source_node_id=cloned[source_node_id], source_node_key=source_node_id, composite_node_id=source_node_id, qualified_ref=f"{actor['alias']}:{source_node_id}"))
            process_set_id = _id("process-set", scenario_id, actor["alias"])
            db.merge(LabProcessSet(id=process_set_id, owner_entity_id=actor["id"], name=f"{actor['name']} · response processes", description=f"Source-backed processes for {scenario.name}", scope_kind="mixed"))
            process_version_id = _id("process-set-version", scenario_id, actor["alias"], "v1")
            db.merge(LabProcessSetVersion(id=process_version_id, process_set_id=process_set_id, version=1, status="published", name=f"{actor['name']} · {scenario.name} · v1", valid_from=scenario.start_at, valid_to=None, evidence=[_evidence(source)], checksum=_checksum(actor["processes"]), published_at=datetime.now(UTC)))
            db.merge(LabScenarioProcessBinding(id=_id("binding", scenario_id, actor["alias"]), assembly_version_id=assembly_id, member_id=member_id, process_set_version_id=process_version_id))
            for process in actor["processes"]:
                workflow_id = _id("workflow", scenario_id, process["id"])
                workflow_version_id = _id("workflow-version", scenario_id, process["id"], "v1")
                db.merge(LabWorkflow(id=workflow_id, name=process["name"], description=f"BPMN 2.0 participant process owned by {actor['name']}"))
                settings = {"format": "BPMN 2.0", "owner_entity_id": actor["id"], "participant_alias": actor["alias"], "evidence": _evidence(source), "on_start_emit": [{"event_type": event_type, "target_member_alias": target} for event_type, target in process.get("emit", [])]}
                description = process.get("description") or _workflow_description(scenario.name, actor["name"], process)
                seeded_descriptions[workflow_id] = description
                version = db.get(LabWorkflowVersion, workflow_version_id)
                if not version:
                    version = LabWorkflowVersion(id=workflow_version_id, workflow_id=workflow_id, version=1, status="published", name=process["name"], description=description, settings=settings, published_at=datetime.now(UTC))
                    db.add(version)
                else:
                    version.name = process["name"]
                    version.description = description
                    version.settings = settings
                db.flush()
                _replace_seeded_process(
                    db,
                    scenario_id=scenario_id,
                    process=process,
                    version=version,
                    source=source,
                )
                for start_event in process["start_events"]:
                    db.merge(LabProcessSetWorkflow(id=_id("activation", scenario_id, actor["alias"], process["id"], start_event), process_set_version_id=process_version_id, workflow_version_id=workflow_version_id, scope_kind=process["scope_kind"], scope_ref=process["scope_ref"], start_event_type=start_event, start_mode="message", correlation_key="scenario_event", priority=100, evidence=_evidence(source), enabled=True))
        for edge in source_edges:
            source_member = node_members.get(edge.source_node_id)
            target_member = node_members.get(edge.target_node_id)
            if source_member and target_member and source_member.id != target_member.id:
                db.merge(LabScenarioAssemblyLink(id=_id("assembly-link", scenario_id, edge.id), assembly_version_id=assembly_id, source_member_id=source_member.id, source_node_key=edge.source_node_id, source_port=edge.source_port, target_member_id=target_member.id, target_node_key=edge.target_node_id, target_port=edge.target_port, flow_type=edge.flow_type, domain=edge.domain, parameters=deepcopy(edge.parameters)))
        assembly.checksum = _checksum({"scenario": scenario_id, "model": scenario.model_version_id, "members": member_payload})
        assembly.validation = {"valid": True, "members": len(spec["actors"]), "source_backed": True, "cross_organization_policy": "roles_and_messages"}
        scenario.assembly_version_id = assembly_id
    for version in db.scalars(select(LabWorkflowVersion)):
        if version.workflow_id in seeded_descriptions:
            version.description = seeded_descriptions[version.workflow_id]
        elif not version.description or version.description.startswith("This BPMN 2.0"):
            workflow = db.get(LabWorkflow, version.workflow_id)
            version.description = workflow.description if workflow and workflow.description and not workflow.description.startswith("This BPMN 2.0") else f"Ця схема BPMN 2.0 описує операційний процес «{version.name}». Додайте тут його призначення, умову запуску, область дії, відповідального учасника та очікувану послідовність кроків."
        if not version.bpmn_xml or not validate_bpmn(version.bpmn_xml)["valid"]:
            _migrate_legacy_workflow(db, version)
    db.flush()
