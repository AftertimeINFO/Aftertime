import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from redis import Redis
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.models import (
    LabCheckpoint, LabComponentTest, LabComponentType, LabDashboardDefinition,
    LabEdge, LabFlowSample, LabMetricDefinition, LabModelVersion, LabNode,
    LabProject, LabResourcePool, LabResourceTransaction, LabRun, LabRunEvent,
    LabRunSample, LabScenario, LabScenarioEventTemplate, LabScript,
    LabScriptTestResult, LabScriptVersion, LabUserCommand, LabWorkflow,
    LabWorkflowInstance, LabWorkflowNode, LabWorkflowToken,
    LabWorkflowTransition, LabWorkflowVersion, LabWorkOrder, LabEventType,
    LabCepRule, LabMonitorTemplate, LabRunMonitorSnapshot,
)
from app.services.model_lab import _apply_script_result, execute_script, process_next, replay_scenario, validate_graph
from app.services.model_contracts import connection_diagnostics, normalized_ports, observable_catalog, stable_key

router = APIRouter(prefix="/api/v1/lab")


def row(item):
    return {
        attribute.columns[0].name: getattr(item, attribute.key)
        for attribute in inspect(item).mapper.column_attrs
    }


def editable_version(db: Session, version_id: str) -> LabModelVersion:
    version = db.get(LabModelVersion, version_id)
    if not version:
        raise HTTPException(404, "Model version not found")
    if version.status != "draft":
        raise HTTPException(409, "Published snapshots are immutable")
    return version


def touch(version: LabModelVersion) -> None:
    version.architecture_version = max(2, version.architecture_version or 1)
    version.semantic_revision = (version.semantic_revision or 0) + 1


def graph_catalog(db: Session, version_id: str, *, target_id: str | None = None) -> list[dict[str, Any]]:
    nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == version_id)))
    edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == version_id)))
    components = {item.id: item for item in db.scalars(select(LabComponentType))}
    metrics = list(db.scalars(select(LabMetricDefinition)))
    catalog = observable_catalog(nodes, components, metrics, edges)
    return [item for item in catalog if not target_id or item["target_id"] == target_id]


@router.get("/workspace")
def workspace(project_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    project = db.get(LabProject, project_id) if project_id else db.scalar(select(LabProject).order_by(LabProject.created_at).limit(1))
    if not project: raise HTTPException(404, "Model Lab seed is missing")
    version = db.get(LabModelVersion, project.active_draft_id or project.published_version_id)
    components = list(db.scalars(select(LabComponentType).order_by(LabComponentType.category, LabComponentType.name)))
    component_rows = [{**row(item), "ports": normalized_ports(item)} for item in components]
    monitors = [row(x) for x in db.scalars(select(LabMonitorTemplate).where(LabMonitorTemplate.model_version_id == version.id).order_by(LabMonitorTemplate.created_at))]
    return {"project": row(project), "projects": [row(x) for x in db.scalars(select(LabProject).order_by(LabProject.created_at))], "version": row(version), "models": [row(x) for x in db.scalars(select(LabModelVersion).where(LabModelVersion.project_id == project.id).order_by(LabModelVersion.version))], "components": component_rows, "nodes": [row(x) for x in db.scalars(select(LabNode).where(LabNode.model_version_id == version.id))], "edges": [row(x) for x in db.scalars(select(LabEdge).where(LabEdge.model_version_id == version.id))], "scenarios": [row(x) for x in db.scalars(select(LabScenario).order_by(LabScenario.name))], "resources": [row(x) for x in db.scalars(select(LabResourcePool).order_by(LabResourcePool.resource_kind, LabResourcePool.class_name))], "runs": [row(x) for x in db.scalars(select(LabRun).order_by(LabRun.created_at.desc()).limit(20))], "scripts": [row(x) for x in db.scalars(select(LabScriptVersion).order_by(LabScriptVersion.script_id, LabScriptVersion.version))], "workflows": [row(x) for x in db.scalars(select(LabWorkflowVersion).order_by(LabWorkflowVersion.name))], "metrics": [row(x) for x in db.scalars(select(LabMetricDefinition).order_by(LabMetricDefinition.category, LabMetricDefinition.name))], "dashboards": [row(x) for x in db.scalars(select(LabDashboardDefinition).order_by(LabDashboardDefinition.name))], "monitors": monitors, "event_types": [row(x) for x in db.scalars(select(LabEventType).order_by(LabEventType.name))], "observables": graph_catalog(db, version.id)}


@router.post("/projects")
def create_project(body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    project = LabProject(name=body["name"], description=body.get("description", ""))
    db.add(project); db.flush()
    draft = LabModelVersion(project_id=project.id, version=1, status="draft", name=body.get("version_name", "Нова модель"), timezone=body.get("timezone", "Europe/Kyiv"), settings=body.get("settings", {}), architecture_version=2)
    db.add(draft); db.flush(); project.active_draft_id = draft.id
    template_id = body.get("template_version_id")
    if template_id:
        source = db.get(LabModelVersion, template_id)
        if not source: raise HTTPException(404, "Template model version not found")
        mapping: dict[str, str] = {}
        for old in db.scalars(select(LabNode).where(LabNode.model_version_id == source.id)):
            new = LabNode(model_version_id=draft.id, component_type_id=old.component_type_id, name=old.name, instance_key=old.instance_key or old.id, parent_node_id=None, x=old.x, y=old.y, parameters=deepcopy(old.parameters), initial_state=deepcopy(old.initial_state), python_code=old.python_code, refinement_contract=deepcopy(old.refinement_contract), port_overrides=deepcopy(old.port_overrides), observable_overrides=deepcopy(old.observable_overrides))
            db.add(new); db.flush(); mapping[old.id] = new.id
        for old in db.scalars(select(LabEdge).where(LabEdge.model_version_id == source.id)):
            db.add(LabEdge(model_version_id=draft.id, connection_key=old.connection_key or old.id, source_node_id=mapping[old.source_node_id], source_port=old.source_port, target_node_id=mapping[old.target_node_id], target_port=old.target_port, flow_type=old.flow_type, domain=old.domain, enabled=old.enabled, parameters=deepcopy(old.parameters)))
    db.commit(); db.refresh(project); db.refresh(draft)
    return {"project": row(project), "version": row(draft)}


@router.patch("/dashboards/{dashboard_id}")
def update_dashboard(dashboard_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    dashboard = db.get(LabDashboardDefinition, dashboard_id)
    if not dashboard:
        raise HTTPException(404, "Dashboard not found")
    if "name" in body:
        dashboard.name = str(body["name"])
    if "panels" in body:
        if not isinstance(body["panels"], list):
            raise HTTPException(422, "panels must be a list")
        dashboard.panels = body["panels"]
    db.commit(); db.refresh(dashboard)
    return row(dashboard)


@router.get("/versions/{version_id}/graph")
def model_graph(version_id: str, db: Session = Depends(get_db)) -> dict:
    version = db.get(LabModelVersion, version_id)
    if not version: raise HTTPException(404, "Model version not found")
    return {"version": row(version), "nodes": [row(x) for x in db.scalars(select(LabNode).where(LabNode.model_version_id == version_id))], "edges": [row(x) for x in db.scalars(select(LabEdge).where(LabEdge.model_version_id == version_id))], "observables": graph_catalog(db, version_id)}


@router.get("/versions/{version_id}/observables")
def observables(version_id: str, target_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    if not db.get(LabModelVersion, version_id):
        raise HTTPException(404, "Model version not found")
    return {"items": graph_catalog(db, version_id, target_id=target_id)}


@router.get("/versions/{version_id}/ports")
def ports(version_id: str, db: Session = Depends(get_db)) -> dict:
    nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == version_id)))
    components = {item.id: item for item in db.scalars(select(LabComponentType))}
    return {"items": [{"node_id": node.id, "instance_key": node.instance_key or node.id, "ports": normalized_ports(components[node.component_type_id], node.port_overrides)} for node in nodes if node.component_type_id in components]}


@router.post("/versions/{version_id}/monitors")
def create_monitor(version_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    version = editable_version(db, version_id)
    available = {item["address"] for item in graph_catalog(db, version_id)}
    requested = [series.get("address") for panel in body.get("panels", []) for series in panel.get("series", [])]
    missing = sorted({address for address in requested if address not in available})
    if missing:
        raise HTTPException(422, {"message": "Unknown observables", "addresses": missing})
    monitor = LabMonitorTemplate(model_version_id=version_id, name=body.get("name", "Монітор моделі"), panels=body.get("panels", []))
    db.add(monitor); touch(version); db.commit(); db.refresh(monitor)
    return row(monitor)


@router.patch("/monitors/{monitor_id}")
def update_monitor(monitor_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    monitor = db.get(LabMonitorTemplate, monitor_id)
    if not monitor:
        raise HTTPException(404, "Monitor not found")
    version = editable_version(db, monitor.model_version_id)
    if "name" in body: monitor.name = str(body["name"])
    if "panels" in body: monitor.panels = list(body["panels"])
    monitor.revision += 1; touch(version); db.commit(); db.refresh(monitor)
    return row(monitor)


@router.post("/event-types")
def create_event_type(body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    event_id = stable_key(body.get("id") or body["name"], f"event-{uuid.uuid4().hex[:8]}")
    if db.get(LabEventType, event_id):
        raise HTTPException(409, "Event type already exists")
    item = LabEventType(
        id=event_id, name=body["name"], kind=body.get("kind", "stimulus"),
        target_kinds=body.get("target_kinds", ["component"]), domains=body.get("domains", []),
        required_capabilities=body.get("required_capabilities", []), payload_schema=body.get("payload_schema", {}),
        severity=body.get("severity", "info"), allow_broadcast=bool(body.get("allow_broadcast", False)),
    )
    db.add(item); db.commit(); db.refresh(item); return row(item)


def validated_event_target(db: Session, model_version_id: str, event_type_id: str, body: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    definition = db.get(LabEventType, event_type_id)
    target = body.get("target") or ({"kind": "component", "id": body.get("target_node_id")} if body.get("target_node_id") else None)
    if definition and target is None and not definition.allow_broadcast:
        raise HTTPException(422, "This event requires an explicit target")
    if target is None:
        return None, {}
    if target.get("kind") != "component":
        if definition and target.get("kind") not in definition.target_kinds:
            raise HTTPException(422, f"Event cannot target {target.get('kind')}")
        return None, target
    node = db.get(LabNode, target.get("id"))
    if not node:
        node = db.scalar(select(LabNode).where(LabNode.model_version_id == model_version_id, LabNode.instance_key == target.get("key")))
    if not node or node.model_version_id != model_version_id:
        raise HTTPException(422, "Event target does not belong to the run model")
    component = db.get(LabComponentType, node.component_type_id)
    if definition:
        domains = {port["domain"] for port in normalized_ports(component, node.port_overrides)}
        if definition.domains and not domains.intersection(definition.domains):
            raise HTTPException(422, "Event domain is incompatible with the selected component")
        capabilities = set(node.refinement_contract.get("capabilities", []))
        if not set(definition.required_capabilities).issubset(capabilities):
            raise HTTPException(422, "Selected component does not provide the required event capability")
        required = definition.payload_schema.get("required", [])
        missing = [name for name in required if name not in body.get("payload", {})]
        if missing: raise HTTPException(422, {"message": "Missing event payload fields", "fields": missing})
    return node.id, {"kind": "component", "id": node.id, "key": node.instance_key or node.id}


@router.post("/scenarios/{scenario_id}/events")
def create_scenario_event(scenario_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    scenario = db.get(LabScenario, scenario_id)
    if not scenario or not scenario.model_version_id: raise HTTPException(404, "Scenario not found")
    target_id, target = validated_event_target(db, scenario.model_version_id, body["event_type"], body)
    item = LabScenarioEventTemplate(
        scenario_id=scenario.id, offset_seconds=int(body.get("offset_seconds", 0)), priority=int(body.get("priority", 100)),
        event_type=body["event_type"], target_node_id=target_id, phase=body.get("phase", "scenario"),
        title=body.get("title", body["event_type"]), payload={**body.get("payload", {}), "_target": target},
        evidence_kind=body.get("evidence_kind", "assumed"), source_url=body.get("source_url"), source_note=body.get("source_note", ""),
    )
    db.add(item); db.commit(); db.refresh(item); return row(item)


@router.post("/scenarios/{scenario_id}/cep-rules")
def create_cep_rule(scenario_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    if not db.get(LabScenario, scenario_id): raise HTTPException(404, "Scenario not found")
    operators = {"all", "any", "not", "compare", "event", "sequence", "count", "average", "min", "max", "duration", "absence", "trend"}
    operator = body.get("condition", {}).get("operator")
    if operator not in operators: raise HTTPException(422, f"Unsupported CEP operator: {operator}")
    item = LabCepRule(scenario_id=scenario_id, name=body["name"], condition=body["condition"], emit=body["emit"], enabled=bool(body.get("enabled", True)))
    db.add(item); db.commit(); db.refresh(item); return row(item)


@router.get("/scripts")
def scripts(db: Session = Depends(get_db)) -> dict:
    return {"scripts": [row(x) for x in db.scalars(select(LabScript).order_by(LabScript.kind, LabScript.name))], "versions": [row(x) for x in db.scalars(select(LabScriptVersion).order_by(LabScriptVersion.script_id, LabScriptVersion.version))]}


@router.post("/scripts")
def create_script(body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    script = LabScript(id=body.get("id") or f"script-{uuid.uuid4().hex[:12]}", name=body["name"], kind=body["kind"], description=body.get("description", "")); db.add(script); db.flush()
    version = LabScriptVersion(script_id=script.id, version=1, status="draft", code=body.get("code", ""), contract=body.get("contract", {})); db.add(version); db.commit(); db.refresh(version)
    return {"script": row(script), "version": row(version)}


@router.post("/scripts/{script_id}/versions")
def create_script_version(script_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    script = db.get(LabScript, script_id)
    if not script: raise HTTPException(404, "Script not found")
    source = db.scalar(select(LabScriptVersion).where(LabScriptVersion.script_id == script_id).order_by(LabScriptVersion.version.desc()).limit(1))
    version = LabScriptVersion(script_id=script_id, version=(source.version if source else 0) + 1, status="draft", code=body.get("code", source.code if source else ""), contract=body.get("contract", deepcopy(source.contract) if source else {})); db.add(version); db.commit(); db.refresh(version); return row(version)


@router.patch("/scripts/versions/{version_id}")
def update_script(version_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    version = db.get(LabScriptVersion, version_id)
    if not version: raise HTTPException(404, "Script version not found")
    if version.status != "draft": raise HTTPException(409, "Published script versions are immutable")
    for field in ["code", "contract"]:
        if field in body: setattr(version, field, body[field])
    db.commit(); db.refresh(version); return row(version)


@router.post("/scripts/versions/{version_id}/validate")
def validate_script(version_id: str, db: Session = Depends(get_db)) -> dict:
    version = db.get(LabScriptVersion, version_id)
    try:
        compile(version.code, f"<{version.id}>", "exec")
        result = {"valid": True, "errors": []}
    except SyntaxError as exc:
        result = {"valid": False, "errors": [str(exc)]}
    version.validation = result; db.commit(); return result


@router.post("/scripts/versions/{version_id}/test")
def test_script(version_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    version = db.get(LabScriptVersion, version_id)
    try:
        return execute_script(version.code, body.get("action", "event"), {"time": body.get("time", datetime.now(UTC).isoformat()), "parameters": body.get("parameters", {}), "state": body.get("state", {}), "inputs": body.get("inputs", {}), "snapshot": body.get("snapshot", {}), "seed": int(body.get("seed", 42))}, event=body.get("event", {}))
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/scripts/versions/{version_id}/publish")
def publish_script(version_id: str, db: Session = Depends(get_db)) -> dict:
    version = db.get(LabScriptVersion, version_id)
    result = validate_script(version_id, db)
    if not result["valid"]: raise HTTPException(422, result)
    version.status = "published"; version.published_at = datetime.now(UTC); db.commit(); db.refresh(version); return row(version)


@router.get("/workflows/{version_id}")
def workflow(version_id: str, db: Session = Depends(get_db)) -> dict:
    version = db.get(LabWorkflowVersion, version_id)
    if not version: raise HTTPException(404, "Workflow not found")
    return {"version": row(version), "nodes": [row(x) for x in db.scalars(select(LabWorkflowNode).where(LabWorkflowNode.workflow_version_id == version_id))], "transitions": [row(x) for x in db.scalars(select(LabWorkflowTransition).where(LabWorkflowTransition.workflow_version_id == version_id).order_by(LabWorkflowTransition.priority))]}


@router.post("/workflows")
def create_workflow(body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    item = LabWorkflow(id=body.get("id") or f"workflow-{uuid.uuid4().hex[:12]}", name=body["name"], description=body.get("description", "")); db.add(item); db.flush()
    version = LabWorkflowVersion(workflow_id=item.id, version=1, status="draft", name=body.get("version_name", item.name), settings=body.get("settings", {})); db.add(version); db.flush()
    start = LabWorkflowNode(workflow_version_id=version.id, node_key="start", block_type="start", name="Start", x=80, y=120, config={"event_type": body.get("start_event", "workflow.start")}, python_code=""); db.add(start); db.commit()
    return workflow(version.id, db)


@router.post("/workflows/{version_id}/debug")
def debug_workflow(version_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    node = db.get(LabWorkflowNode, body.get("node_id"))
    if not node or node.workflow_version_id != version_id: raise HTTPException(404, "Workflow node not found")
    if not node.python_code.strip(): return {"state": body.get("state", {}), "operations": [], "logs": [], "transition": "no_python_action"}
    return execute_script(node.python_code, body.get("action", "event"), {"time": body.get("time", datetime.now(UTC).isoformat()), "parameters": node.config, "state": body.get("state", {}), "inputs": body.get("inputs", {}), "snapshot": body.get("snapshot", {}), "seed": int(body.get("seed", 42))}, event=body.get("event", {}))


@router.post("/workflows/{version_id}/nodes")
def add_workflow_node(version_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    version = db.get(LabWorkflowVersion, version_id)
    if not version or version.status != "draft": raise HTTPException(409, "Only draft workflows can be edited")
    node = LabWorkflowNode(workflow_version_id=version_id, node_key=body.get("node_key") or f"{body['block_type']}-{uuid.uuid4().hex[:8]}", block_type=body["block_type"], name=body.get("name", body["block_type"]), x=float(body.get("x", 0)), y=float(body.get("y", 0)), config=body.get("config", {}), python_code=body.get("python_code", "")); db.add(node); db.commit(); db.refresh(node); return row(node)


@router.patch("/workflows/nodes/{node_id}")
def update_workflow_node(node_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    node = db.get(LabWorkflowNode, node_id); version = db.get(LabWorkflowVersion, node.workflow_version_id) if node else None
    if not node: raise HTTPException(404, "Workflow node not found")
    if version.status != "draft": raise HTTPException(409, "Published workflow versions are immutable")
    for field in ["name", "block_type", "x", "y", "config", "python_code"]:
        if field in body: setattr(node, field, body[field])
    db.commit(); db.refresh(node); return row(node)


@router.post("/workflows/{version_id}/transitions")
def add_workflow_transition(version_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    version = db.get(LabWorkflowVersion, version_id)
    if not version or version.status != "draft": raise HTTPException(409, "Only draft workflows can be edited")
    transition = LabWorkflowTransition(workflow_version_id=version_id, source_node_id=body["source_node_id"], target_node_id=body["target_node_id"], condition_code=body.get("condition_code", "True"), priority=int(body.get("priority", 100))); db.add(transition); db.commit(); db.refresh(transition); return row(transition)


@router.post("/workflows/{version_id}/clone")
def clone_workflow(version_id: str, db: Session = Depends(get_db)) -> dict:
    source = db.get(LabWorkflowVersion, version_id)
    if not source: raise HTTPException(404, "Workflow not found")
    number = (db.scalar(select(func.max(LabWorkflowVersion.version)).where(LabWorkflowVersion.workflow_id == source.workflow_id)) or 0) + 1
    draft = LabWorkflowVersion(workflow_id=source.workflow_id, version=number, status="draft", name=f"{source.name} · draft", settings=deepcopy(source.settings)); db.add(draft); db.flush()
    mapping = {}
    for old in db.scalars(select(LabWorkflowNode).where(LabWorkflowNode.workflow_version_id == source.id)):
        new = LabWorkflowNode(workflow_version_id=draft.id, node_key=old.node_key, block_type=old.block_type, name=old.name, x=old.x, y=old.y, config=deepcopy(old.config), python_code=old.python_code); db.add(new); db.flush(); mapping[old.id] = new.id
    for old in db.scalars(select(LabWorkflowTransition).where(LabWorkflowTransition.workflow_version_id == source.id)):
        db.add(LabWorkflowTransition(workflow_version_id=draft.id, source_node_id=mapping[old.source_node_id], target_node_id=mapping[old.target_node_id], condition_code=old.condition_code, priority=old.priority))
    db.commit(); db.refresh(draft)
    return workflow(draft.id, db)


@router.post("/workflows/{version_id}/validate")
def validate_workflow(version_id: str, db: Session = Depends(get_db)) -> dict:
    version = db.get(LabWorkflowVersion, version_id)
    if not version: raise HTTPException(404, "Workflow not found")
    nodes = list(db.scalars(select(LabWorkflowNode).where(LabWorkflowNode.workflow_version_id == version_id)))
    transitions = list(db.scalars(select(LabWorkflowTransition).where(LabWorkflowTransition.workflow_version_id == version_id)))
    errors = []
    if not nodes: errors.append("Workflow не містить вузлів")
    if not any(node.block_type == "start" for node in nodes): errors.append("Потрібен блок Start")
    for node in nodes:
        try: compile(node.python_code or "pass", f"<workflow:{node.node_key}>", "exec")
        except SyntaxError as exc: errors.append(f"{node.name}: {exc}")
    result = {"valid": not errors, "errors": errors, "nodes": len(nodes), "transitions": len(transitions)}
    return result


@router.post("/workflows/{version_id}/publish")
def publish_workflow(version_id: str, db: Session = Depends(get_db)) -> dict:
    version = db.get(LabWorkflowVersion, version_id)
    if not version or version.status != "draft": raise HTTPException(409, "Only a draft workflow can be published")
    result = validate_workflow(version_id, db)
    if not result["valid"]: raise HTTPException(422, result)
    version.status = "published"; version.published_at = datetime.now(UTC); db.commit(); db.refresh(version); return row(version)


@router.get("/scenarios/{scenario_id}/timeline")
def scenario_timeline(scenario_id: str, db: Session = Depends(get_db)) -> dict:
    scenario = db.get(LabScenario, scenario_id)
    if not scenario: raise HTTPException(404, "Scenario not found")
    return {"start": scenario.start_at, "incident": scenario.incident_at, "end": scenario.start_at + timedelta(seconds=scenario.duration_seconds), "events": [row(x) for x in db.scalars(select(LabScenarioEventTemplate).where(LabScenarioEventTemplate.scenario_id == scenario_id).order_by(LabScenarioEventTemplate.offset_seconds, LabScenarioEventTemplate.priority))]}


@router.get("/qualification")
def qualification(db: Session = Depends(get_db)) -> dict:
    project = db.scalar(select(LabProject).order_by(LabProject.created_at).limit(1))
    if not project or not project.published_version_id:
        raise HTTPException(409, "Published Model Lab snapshot is missing")
    results = []
    for scenario in db.scalars(select(LabScenario).where(LabScenario.id != "baseline").order_by(LabScenario.name)):
        replay = replay_scenario(db, scenario, scenario.model_version_id)
        model = db.get(LabModelVersion, scenario.model_version_id)
        checks = {"dedicated_model": bool(model and model.status == "published" and model.settings.get("qualification_scenario") == scenario.id), "historical_origin": scenario.origin == "historical", "source": bool(scenario.source_url), "calendar": len(scenario.events) >= int(scenario.expected.get("minimum_events", 1)), **replay["checks"]}
        results.append({"scenario_id": scenario.id, "name": scenario.name, "passed": all(checks.values()), "checks": checks, "outcome_checks": replay["outcome_checks"], "expected": scenario.expected, "observed": replay["observed"], "trace": replay["trace"]})
    return {"passed": all(item["passed"] for item in results) and len(results) == 15, "passed_count": sum(item["passed"] for item in results), "required_count": 15, "results": results}


@router.post("/versions/{version_id}/nodes")
def add_node(version_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    version = editable_version(db, version_id)
    component = db.get(LabComponentType, body.get("component_type_id"))
    if not component: raise HTTPException(404, "Unknown component type")
    name = body.get("name") or component.name
    key = stable_key(body.get("instance_key") or name, f"node-{uuid.uuid4().hex[:8]}")
    if db.scalar(select(LabNode).where(LabNode.model_version_id == version_id, LabNode.instance_key == key)):
        key = f"{key}-{uuid.uuid4().hex[:6]}"
    node = LabNode(model_version_id=version_id, component_type_id=component.id, name=name, instance_key=key, parent_node_id=body.get("parent_node_id"), x=float(body.get("x", 80)), y=float(body.get("y", 80)), parameters=body.get("parameters", deepcopy(component.parameters_schema)), initial_state=body.get("initial_state", deepcopy(component.initial_state)), python_code=body.get("python_code"), refinement_contract=body.get("refinement_contract", {}), port_overrides=body.get("port_overrides", {}), observable_overrides=body.get("observable_overrides", {}))
    db.add(node); touch(version); db.commit(); db.refresh(node); return row(node)


@router.patch("/nodes/{node_id}")
def update_node(node_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    node = db.get(LabNode, node_id)
    if not node: raise HTTPException(404, "Node not found")
    version = db.get(LabModelVersion, node.model_version_id)
    if version.status != "draft": raise HTTPException(409, "Published snapshots are immutable")
    for field in ["name", "x", "y", "parameters", "initial_state", "python_code", "refinement_contract", "parent_node_id", "port_overrides", "observable_overrides"]:
        if field in body: setattr(node, field, body[field])
    if any(field in body for field in ["name", "parameters", "initial_state", "python_code", "refinement_contract", "parent_node_id", "port_overrides", "observable_overrides"]): touch(version)
    db.commit(); db.refresh(node); return row(node)


@router.delete("/nodes/{node_id}", status_code=204)
def delete_node(node_id: str, db: Session = Depends(get_db)):
    node = db.get(LabNode, node_id)
    if not node: raise HTTPException(404, "Node not found")
    version = db.get(LabModelVersion, node.model_version_id)
    if version.status != "draft": raise HTTPException(409, "Published snapshots are immutable")
    for edge in db.scalars(select(LabEdge).where((LabEdge.source_node_id == node_id) | (LabEdge.target_node_id == node_id))): db.delete(edge)
    db.delete(node); touch(version); db.commit()


@router.post("/versions/{version_id}/edges")
def add_edge(version_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    version = editable_version(db, version_id)
    source, target = db.get(LabNode, body["source_node_id"]), db.get(LabNode, body["target_node_id"])
    if not source or not target or source.model_version_id != version_id or target.model_version_id != version_id:
        raise HTTPException(422, "Both connection endpoints must belong to this model version")
    source_type, target_type = db.get(LabComponentType, source.component_type_id), db.get(LabComponentType, target.component_type_id)
    diagnostics = connection_diagnostics(source_type, body["source_port"], target_type, body["target_port"], source_overrides=source.port_overrides, target_overrides=target.port_overrides)
    if diagnostics: raise HTTPException(422, {"message": "Incompatible ports", "errors": diagnostics})
    source_contract = next(port for port in normalized_ports(source_type, source.port_overrides) if port["key"] == body["source_port"])
    key = stable_key(body.get("connection_key") or f"{source.instance_key or source.id}-{source_contract['key']}-{target.instance_key or target.id}-{body['target_port']}", f"connection-{uuid.uuid4().hex[:8]}")
    edge = LabEdge(model_version_id=version_id, connection_key=key, source_node_id=source.id, source_port=body["source_port"], target_node_id=target.id, target_port=body["target_port"], flow_type=body.get("flow_type", source_contract["domain"]), domain=source_contract["domain"], enabled=bool(body.get("enabled", True)), parameters=body.get("parameters", {}))
    db.add(edge); touch(version); db.commit(); db.refresh(edge); return row(edge)


@router.patch("/edges/{edge_id}")
def update_edge(edge_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    edge = db.get(LabEdge, edge_id)
    if not edge: raise HTTPException(404, "Connection not found")
    version = editable_version(db, edge.model_version_id)
    for field in ["parameters", "enabled"]:
        if field in body: setattr(edge, field, body[field])
    touch(version); db.commit(); db.refresh(edge); return row(edge)


@router.delete("/edges/{edge_id}", status_code=204)
def delete_edge(edge_id: str, db: Session = Depends(get_db)):
    edge = db.get(LabEdge, edge_id)
    if not edge: raise HTTPException(404, "Connection not found")
    version = editable_version(db, edge.model_version_id)
    db.delete(edge); touch(version); db.commit()


@router.post("/versions/{version_id}/validate")
def validate(version_id: str, db: Session = Depends(get_db)) -> dict:
    version = db.get(LabModelVersion, version_id)
    result = validate_graph(db, version_id); version.validation = result; db.commit(); return result


@router.post("/versions/{version_id}/publish")
def publish(version_id: str, db: Session = Depends(get_db)) -> dict:
    version = db.get(LabModelVersion, version_id); result = validate_graph(db, version_id)
    if not result["valid"]: raise HTTPException(422, result)
    version.status = "published"; version.validation = result; version.published_at = datetime.now(UTC)
    project = db.get(LabProject, version.project_id); project.published_version_id = version.id; project.active_draft_id = None
    db.commit(); return row(version)


@router.post("/versions/{version_id}/clone")
def clone(version_id: str, db: Session = Depends(get_db)) -> dict:
    source = db.get(LabModelVersion, version_id); project = db.get(LabProject, source.project_id)
    number = (db.scalar(select(func.max(LabModelVersion.version)).where(LabModelVersion.project_id == project.id)) or 0) + 1
    draft = LabModelVersion(project_id=project.id, version=number, status="draft", name=source.name, timezone=source.timezone, settings=deepcopy(source.settings)); db.add(draft); db.flush()
    mapping = {}
    for old in db.scalars(select(LabNode).where(LabNode.model_version_id == source.id)):
        new = LabNode(model_version_id=draft.id, component_type_id=old.component_type_id, name=old.name, instance_key=old.instance_key or old.id, parent_node_id=old.parent_node_id, x=old.x, y=old.y, parameters=deepcopy(old.parameters), initial_state=deepcopy(old.initial_state), python_code=old.python_code, refinement_contract=deepcopy(old.refinement_contract), port_overrides=deepcopy(old.port_overrides), observable_overrides=deepcopy(old.observable_overrides)); db.add(new); db.flush(); mapping[old.id] = new.id
    for old in db.scalars(select(LabEdge).where(LabEdge.model_version_id == source.id)):
        db.add(LabEdge(model_version_id=draft.id, connection_key=old.connection_key or old.id, source_node_id=mapping[old.source_node_id], source_port=old.source_port, target_node_id=mapping[old.target_node_id], target_port=old.target_port, flow_type=old.flow_type, domain=old.domain, enabled=old.enabled, parameters=deepcopy(old.parameters)))
    project.active_draft_id = draft.id; db.commit(); db.refresh(draft); return row(draft)


@router.post("/components/{component_id}/test")
def test_component(component_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    component = db.get(LabComponentType, component_id)
    context = {"time": body.get("time", datetime.now(UTC).isoformat()), "parameters": body.get("parameters", {}), "state": body.get("state", component.initial_state), "inputs": body.get("inputs", {}), "seed": int(body.get("seed", 42))}
    code = body.get("python_code") or component.python_code
    try:
        initialized = execute_script(code, "initialize", context)
        context["state"] = initialized["state"]
        return execute_script(code, body.get("action", "tick"), context, event=body.get("event"), dt=float(body.get("dt", component.tick_seconds)))
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/runs")
def start_run(body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    scenario = db.get(LabScenario, body.get("scenario_id")) if body.get("scenario_id") else None
    requested_version_id = scenario.model_version_id if scenario and scenario.model_version_id else body["model_version_id"]
    version = db.get(LabModelVersion, requested_version_id)
    if not version or version.status != "published": raise HTTPException(409, "Run requires a published snapshot")
    start = datetime.fromisoformat(scenario.start_at.isoformat() if scenario else body.get("start_at") or datetime.now(UTC).isoformat())
    if start.tzinfo is None: start = start.replace(tzinfo=UTC)
    duration = min(int(body.get("duration_seconds") or (scenario.duration_seconds if scenario else 86400)), 366 * 86400)
    idle_speed = max(.001, float(body.get("idle_speed", body.get("speed", 3600))))
    run = LabRun(model_version_id=version.id, scenario_id=scenario.id if scenario else None, status="queued", current_time=start, end_time=start + timedelta(seconds=duration), speed=idle_speed, idle_speed=idle_speed, event_speed=max(.001, float(body.get("event_speed", 60))), event_speed_duration_seconds=max(0, float(body.get("event_speed_duration_seconds", 10))), event_speed_event_types=body.get("event_speed_event_types", []), seed=int(body.get("seed", scenario.seed if scenario else 42)), state={}, summary={})
    db.add(run); db.flush()
    monitor = db.get(LabMonitorTemplate, body.get("monitor_template_id")) if body.get("monitor_template_id") else db.scalar(select(LabMonitorTemplate).where(LabMonitorTemplate.model_version_id == version.id).order_by(LabMonitorTemplate.created_at).limit(1))
    db.add(LabRunMonitorSnapshot(run_id=run.id, template_id=monitor.id if monitor else None, template_revision=monitor.revision if monitor else 1, panels=deepcopy(monitor.panels) if monitor else [], observable_catalog=graph_catalog(db, version.id)))
    scripted = bool(scenario and scenario.configuration.get("scenario_script_version_id"))
    for index, event in enumerate(([] if scripted else scenario.events if scenario else []) + body.get("events", []), 1):
        at = datetime.fromisoformat(event["at"]); at = at.replace(tzinfo=UTC) if at.tzinfo is None else at
        db.add(LabRunEvent(run_id=run.id, sequence=index, scheduled_at=at, priority=int(event.get("priority", 100)), event_type=event["event_type"], target_node_id=event.get("target_node_id"), origin=event.get("origin", "scenario"), payload=event.get("payload", {})))
    db.commit(); Redis.from_url(settings.redis_url, decode_responses=True).rpush("aftertime:simulation", run.id); return row(run)


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.get(LabRun, run_id)
    if not run: raise HTTPException(404, "Run not found")
    scenario = db.get(LabScenario, run.scenario_id) if run.scenario_id else None
    workflow_instances = [row(x) for x in db.scalars(select(LabWorkflowInstance).where(LabWorkflowInstance.run_id == run_id))]
    monitor = db.scalar(select(LabRunMonitorSnapshot).where(LabRunMonitorSnapshot.run_id == run_id))
    return {**row(run), "incident_at": scenario.incident_at if scenario else None, "events": [row(x) for x in db.scalars(select(LabRunEvent).where(LabRunEvent.run_id == run_id).order_by(LabRunEvent.scheduled_at, LabRunEvent.priority, LabRunEvent.sequence))], "checkpoints": [row(x) for x in db.scalars(select(LabCheckpoint).where(LabCheckpoint.run_id == run_id).order_by(LabCheckpoint.model_time.desc()).limit(20))], "work_orders": [row(x) for x in db.scalars(select(LabWorkOrder).where(LabWorkOrder.run_id == run_id))], "workflow_instances": workflow_instances, "resource_transactions": [row(x) for x in db.scalars(select(LabResourceTransaction).where(LabResourceTransaction.run_id == run_id).order_by(LabResourceTransaction.model_time.desc()).limit(100))], "samples": [row(x) for x in db.scalars(select(LabRunSample).where(LabRunSample.run_id == run_id).order_by(LabRunSample.model_time.desc(), LabRunSample.sequence.desc()).limit(240))], "flows": [row(x) for x in db.scalars(select(LabFlowSample).where(LabFlowSample.run_id == run_id, LabFlowSample.model_time == run.current_time))], "monitor": row(monitor) if monitor else None}


@router.get("/runs/{run_id}/timeline")
def run_timeline(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.get(LabRun, run_id)
    if not run: raise HTTPException(404, "Run not found")
    scenario = db.get(LabScenario, run.scenario_id) if run.scenario_id else None
    return {"start": scenario.start_at if scenario else run.current_time, "incident": scenario.incident_at if scenario else None, "end": run.end_time, "current": run.current_time, "events": [row(x) for x in db.scalars(select(LabRunEvent).where(LabRunEvent.run_id == run_id).order_by(LabRunEvent.scheduled_at, LabRunEvent.priority, LabRunEvent.sequence))], "checkpoints": [row(x) for x in db.scalars(select(LabCheckpoint).where(LabCheckpoint.run_id == run_id).order_by(LabCheckpoint.model_time))]}


@router.get("/runs/{run_id}/samples")
def run_samples(run_id: str, db: Session = Depends(get_db)) -> dict:
    return {"samples": [row(x) for x in db.scalars(select(LabRunSample).where(LabRunSample.run_id == run_id).order_by(LabRunSample.model_time, LabRunSample.sequence))], "flows": [row(x) for x in db.scalars(select(LabFlowSample).where(LabFlowSample.run_id == run_id).order_by(LabFlowSample.model_time))]}


@router.get("/runs/{run_id}/workflows")
def run_workflows(run_id: str, db: Session = Depends(get_db)) -> dict:
    instances = list(db.scalars(select(LabWorkflowInstance).where(LabWorkflowInstance.run_id == run_id)))
    return {"instances": [row(x) for x in instances], "tokens": [row(x) for instance in instances for x in db.scalars(select(LabWorkflowToken).where(LabWorkflowToken.instance_id == instance.id).order_by(LabWorkflowToken.entered_at))]}


@router.post("/runs/{run_id}/seek")
def seek(run_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    source = db.get(LabRun, run_id)
    if not source: raise HTTPException(404, "Run not found")
    target = datetime.fromisoformat(body["at"]); target = target.replace(tzinfo=UTC) if target.tzinfo is None else target
    scenario = db.get(LabScenario, source.scenario_id) if source.scenario_id else None
    start = scenario.start_at if scenario else source.current_time
    target = max(start, min(target, source.end_time))
    source.status = "paused"
    if target > source.current_time:
        source.run_until = target; source.status = "running"; db.commit()
        Redis.from_url(settings.redis_url, decode_responses=True).rpush("aftertime:simulation", source.id)
        return get_run(source.id, db)
    checkpoint = db.scalar(select(LabCheckpoint).where(LabCheckpoint.run_id == run_id, LabCheckpoint.model_time <= target).order_by(LabCheckpoint.model_time.desc()).limit(1))
    if not checkpoint: raise HTTPException(409, "Move the run forward once to create the first checkpoint")
    child = LabRun(model_version_id=source.model_version_id, scenario_id=source.scenario_id, parent_run_id=source.id, status="paused", current_time=checkpoint.model_time, end_time=source.end_time, speed=source.speed, idle_speed=source.idle_speed, event_speed=source.event_speed, event_speed_duration_seconds=source.event_speed_duration_seconds, event_speed_event_types=deepcopy(source.event_speed_event_types), seed=source.seed, state=deepcopy(checkpoint.state), summary=deepcopy(checkpoint.metrics))
    db.add(child); db.flush()
    sequence = 1
    for event in db.scalars(select(LabRunEvent).where(LabRunEvent.run_id == source.id, LabRunEvent.scheduled_at > checkpoint.model_time).order_by(LabRunEvent.scheduled_at, LabRunEvent.priority, LabRunEvent.sequence)):
        db.add(LabRunEvent(run_id=child.id, sequence=sequence, scheduled_at=event.scheduled_at, priority=event.priority, event_type=event.event_type, target_node_id=event.target_node_id, origin="branch", payload=deepcopy(event.payload))); sequence += 1
    if scenario and scenario.configuration.get("workflow_version_id"):
        db.add(LabWorkflowInstance(run_id=child.id, workflow_version_id=scenario.configuration["workflow_version_id"], status="ready", variables={"scenario_id": scenario.id, "branched_from": source.id}))
    db.commit()
    while child.current_time < target and child.status not in {"completed", "failed"}:
        process_next(db, child, max_step_seconds=max(.001, (target - child.current_time).total_seconds()))
    child.current_time = target; child.status = "paused"; db.commit()
    return get_run(child.id, db)


@router.post("/runs/{run_id}/user-commands")
def user_command(run_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    run = db.get(LabRun, run_id); scenario = db.get(LabScenario, run.scenario_id) if run else None
    if not run or not scenario: raise HTTPException(404, "Run not found")
    allowed = []
    workflow_version = db.get(LabWorkflowVersion, scenario.configuration.get("workflow_version_id"))
    if workflow_version: allowed = [item["id"] for item in workflow_version.settings.get("commands", [])]
    if body["command_type"] not in allowed: raise HTTPException(422, "Command is not declared by this workflow")
    command = LabUserCommand(run_id=run.id, model_time=run.current_time, command_type=body["command_type"], payload=body.get("payload", {}), status="processing"); db.add(command); db.flush()
    script = db.get(LabScriptVersion, scenario.configuration.get("process_script_version_id"))
    result = execute_script(script.code, "command", {"time": run.current_time.isoformat(), "parameters": scenario.configuration, "state": {}, "inputs": {}, "snapshot": run.state, "seed": run.seed}, event={"type": command.command_type, "payload": command.payload})
    state = deepcopy(run.state); _apply_script_result(db, run, state, result); run.state = state
    command.status = "completed"; command.result = {"operations": result.get("operations", []), "logs": result.get("logs", [])}; db.commit(); db.refresh(command); return row(command)


@router.post("/runs/{run_id}/commands")
def command(run_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    run = db.get(LabRun, run_id); action = body["action"]
    if action in {"pause", "resume", "stop", "step"}:
        if action == "pause": run.status = "paused"
        elif action == "resume": run.status = "running"
        elif action == "stop": run.status = "stopped"
        else: run.status = "paused"; process_next(db, run)
    elif action == "speed": run.speed = max(.001, float(body["value"])); run.idle_speed = run.speed
    elif action == "playback_settings":
        run.idle_speed = max(.001, float(body.get("idle_speed", run.idle_speed))); run.speed = run.idle_speed
        run.event_speed = max(.001, float(body.get("event_speed", run.event_speed)))
        run.event_speed_duration_seconds = max(0, float(body.get("event_speed_duration_seconds", run.event_speed_duration_seconds)))
        run.event_speed_event_types = list(body.get("event_speed_event_types", run.event_speed_event_types))
    else: raise HTTPException(422, "Unknown command")
    db.commit()
    if action == "resume":
        Redis.from_url(settings.redis_url, decode_responses=True).rpush("aftertime:simulation", run.id)
    return row(run)


@router.post("/runs/{run_id}/events")
def inject_event(run_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    run = db.get(LabRun, run_id)
    if not run: raise HTTPException(404, "Run not found")
    at = datetime.fromisoformat(body.get("at") or run.current_time.isoformat()); at = at.replace(tzinfo=UTC) if at.tzinfo is None else at
    if at < run.current_time: raise HTTPException(409, "Past injection requires branching from a checkpoint")
    target, target_ref = validated_event_target(db, run.model_version_id, body["event_type"], body)
    sequence = (db.scalar(select(func.max(LabRunEvent.sequence)).where(LabRunEvent.run_id == run_id)) or 0) + 1
    event = LabRunEvent(run_id=run_id, sequence=sequence, scheduled_at=at, priority=int(body.get("priority", 50)), event_type=body["event_type"], target_node_id=target, origin="manual", payload={**body.get("payload", {}), "_target": target_ref}); db.add(event); db.commit(); db.refresh(event); return row(event)


@router.post("/runs/{run_id}/branch")
def branch_run(run_id: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    source = db.get(LabRun, run_id)
    checkpoint = db.get(LabCheckpoint, body.get("checkpoint_id")) if body.get("checkpoint_id") else db.scalar(select(LabCheckpoint).where(LabCheckpoint.run_id == run_id).order_by(LabCheckpoint.model_time.desc()).limit(1))
    if not checkpoint: raise HTTPException(409, "No checkpoint available")
    child = LabRun(model_version_id=source.model_version_id, scenario_id=source.scenario_id, parent_run_id=source.id, status="paused", current_time=checkpoint.model_time, end_time=source.end_time, speed=source.speed, idle_speed=source.idle_speed, event_speed=source.event_speed, event_speed_duration_seconds=source.event_speed_duration_seconds, event_speed_event_types=deepcopy(source.event_speed_event_types), seed=source.seed, state=deepcopy(checkpoint.state), summary=deepcopy(checkpoint.metrics))
    db.add(child); db.flush()
    for event in body.get("events", []):
        at = datetime.fromisoformat(event["at"]); at = at.replace(tzinfo=UTC) if at.tzinfo is None else at
        db.add(LabRunEvent(run_id=child.id, sequence=int(event.get("sequence", 1)), scheduled_at=at, priority=int(event.get("priority", 50)), event_type=event["event_type"], target_node_id=event.get("target_node_id"), origin="branch", payload=event.get("payload", {})))
    db.commit(); db.refresh(child); return row(child)


@router.get("/runs/{run_id}/stream")
def stream(run_id: str):
    def events():
        import time
        previous = {}
        for _ in range(3600):
            with SessionLocal() as db:
                run = db.get(LabRun, run_id)
                if not run: break
                latest_event = db.scalar(select(LabRunEvent).where(LabRunEvent.run_id == run_id, LabRunEvent.status == "processed").order_by(LabRunEvent.processed_at.desc()).limit(1))
                latest_sample = db.scalar(select(LabRunSample).where(LabRunSample.run_id == run_id).order_by(LabRunSample.model_time.desc()).limit(1))
                instance = db.scalar(select(LabWorkflowInstance).where(LabWorkflowInstance.run_id == run_id).limit(1))
                latest_token = db.scalar(select(LabWorkflowToken).where(LabWorkflowToken.instance_id == instance.id).order_by(LabWorkflowToken.entered_at.desc()).limit(1)) if instance else None
                latest_resource = db.scalar(select(LabResourceTransaction).where(LabResourceTransaction.run_id == run_id).order_by(LabResourceTransaction.model_time.desc(), LabResourceTransaction.id.desc()).limit(1))
                latest_command = db.scalar(select(LabUserCommand).where(LabUserCommand.run_id == run_id).order_by(LabUserCommand.model_time.desc(), LabUserCommand.id.desc()).limit(1))
                latest_checkpoint = db.scalar(select(LabCheckpoint).where(LabCheckpoint.run_id == run_id).order_by(LabCheckpoint.model_time.desc()).limit(1))
                latest_flows = [row(x) for x in db.scalars(select(LabFlowSample).where(LabFlowSample.run_id == run_id, LabFlowSample.model_time == run.current_time).limit(50))]
                channels = {"clock": {"status": run.status, "current_time": run.current_time.isoformat()}, "metric": row(latest_sample) if latest_sample else run.summary, "flow": latest_flows, "event": row(latest_event) if latest_event else None, "workflow_transition": row(latest_token) if latest_token else None, "resource_transaction": row(latest_resource) if latest_resource else None, "command_result": row(latest_command) if latest_command else None, "checkpoint": row(latest_checkpoint) if latest_checkpoint else None, "status": {"status": run.status, "error": run.error}}
                for channel, value in channels.items():
                    payload = json.dumps(value, default=str)
                    if payload != previous.get(channel):
                        yield f"event: {channel}\ndata: {payload}\n\n"; previous[channel] = payload
                if run.status in {"completed", "failed", "stopped"}: break
            time.sleep(.5)
    return StreamingResponse(events(), media_type="text/event-stream")
