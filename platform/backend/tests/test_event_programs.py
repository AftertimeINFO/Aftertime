from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.model_lab import (
    clone,
    create_event_action,
    create_event_program,
    create_project,
    create_scenario_event,
    delete_edge,
    delete_event_action,
    delete_event_program,
    delete_node,
    delete_scenario_event,
    event_programs,
    start_run,
    update_event_action,
    update_event_program,
    update_scenario_event,
)
from app.db import SessionLocal
from app.models import (
    LabComponentType,
    LabEdge,
    LabEventAction,
    LabEventProgram,
    LabEventType,
    LabModelVersion,
    LabNode,
    LabProject,
    LabRun,
    LabRunEvent,
    LabScenario,
    LabScenarioEventTemplate,
    LabScript,
    LabScriptVersion,
)
from app.services.model_lab import prepare_run, process_next, validate_graph


@pytest.fixture
def event_model():
    suffix = uuid4().hex[:10]
    project_id = f"event-designer-project-{suffix}"
    version_id = f"event-designer-version-{suffix}"
    source_id = f"event-source-{suffix}"
    target_id = f"event-target-{suffix}"
    edge_id = f"event-edge-{suffix}"
    event_type_ids = {
        "trigger": f"event-trigger-{suffix}",
        "enable": f"event-enable-{suffix}",
        "emitted": f"event-emitted-{suffix}",
    }
    extra_project_ids: list[str] = []
    scenario_ids: list[str] = []
    script_ids: list[str] = []

    with SessionLocal() as db:
        source_type = db.get(LabComponentType, "steam-plant")
        target_type = db.get(LabComponentType, "substation")
        assert source_type and target_type

        project = LabProject(
            id=project_id,
            name="Event Designer test",
            description="",
            active_draft_id=version_id,
        )
        version = LabModelVersion(
            id=version_id,
            project_id=project_id,
            version=1,
            status="draft",
            name="Event Designer test model",
            timezone="Europe/Kyiv",
            settings={},
            architecture_version=2,
        )
        source = LabNode(
            id=source_id,
            model_version_id=version_id,
            component_type_id=source_type.id,
            name="Source",
            instance_key="source",
            x=0,
            y=0,
            parameters=deepcopy(source_type.parameters_schema),
            initial_state={"online": True},
            refinement_contract={"capabilities": ["trip", "repair"]},
            port_overrides={},
            observable_overrides={},
        )
        target = LabNode(
            id=target_id,
            model_version_id=version_id,
            component_type_id=target_type.id,
            name="Target",
            instance_key="target",
            x=200,
            y=0,
            parameters=deepcopy(target_type.parameters_schema),
            initial_state={"online": True},
            refinement_contract={"capabilities": ["trip", "repair"]},
            port_overrides={},
            observable_overrides={},
        )
        edge = LabEdge(
            id=edge_id,
            model_version_id=version_id,
            source_node_id=source_id,
            source_port="out",
            target_node_id=target_id,
            target_port="in",
            flow_type="electricity",
            connection_key="source-to-target",
            domain="electric.ac",
            enabled=True,
            parameters={},
        )
        definitions = [
            LabEventType(
                id=event_type_ids["trigger"],
                name="Designer trigger",
                target_kinds=["component"],
                domains=[],
                required_capabilities=[],
                payload_schema={
                    "type": "object",
                    "required": ["severity"],
                    "properties": {"severity": {"type": "number"}},
                },
                allow_broadcast=False,
            ),
            LabEventType(
                id=event_type_ids["enable"],
                name="Designer enable",
                target_kinds=["component"],
                domains=[],
                required_capabilities=[],
                payload_schema={"type": "object"},
                allow_broadcast=False,
            ),
            LabEventType(
                id=event_type_ids["emitted"],
                name="Designer emitted",
                target_kinds=["component"],
                domains=[],
                required_capabilities=[],
                payload_schema={"type": "object"},
                allow_broadcast=True,
            ),
        ]
        db.add(project)
        db.flush()
        db.add_all([version, *definitions])
        db.flush()
        db.add_all([source, target])
        db.flush()
        db.add(edge)
        db.commit()

        context = {
            "db": db,
            "project": project,
            "version": version,
            "source": source,
            "target": target,
            "edge": edge,
            "event_types": event_type_ids,
            "extra_project_ids": extra_project_ids,
            "scenario_ids": scenario_ids,
            "script_ids": script_ids,
        }
        try:
            yield context
        finally:
            db.rollback()
            versions = list(
                db.scalars(
                    select(LabModelVersion.id).where(
                        LabModelVersion.project_id.in_([project_id, *extra_project_ids])
                    )
                )
            )
            for run in list(
                db.scalars(select(LabRun).where(LabRun.model_version_id.in_(versions)))
            ):
                db.delete(run)
            for scenario_id in scenario_ids:
                scenario = db.get(LabScenario, scenario_id)
                if scenario:
                    db.delete(scenario)
            db.flush()
            for owned_project_id in [project_id, *extra_project_ids]:
                owned_project = db.get(LabProject, owned_project_id)
                if owned_project:
                    db.delete(owned_project)
            db.flush()
            for event_type_id in event_type_ids.values():
                definition = db.get(LabEventType, event_type_id)
                if definition:
                    db.delete(definition)
            for script_id in script_ids:
                script = db.get(LabScript, script_id)
                if script:
                    db.delete(script)
            db.commit()


def add_program_with_actions(event_model, event_type_key="trigger"):
    db = event_model["db"]
    program = create_event_program(
        event_model["version"].id,
        {
            "event_type_id": event_model["event_types"][event_type_key],
            "name": f"Program {event_type_key}",
            "description": "Deterministic test program",
            "layout": {"zoom": 1},
        },
        db,
    )
    return program


def test_event_program_crud_reordering_immutability_and_reference_guards(event_model):
    db = event_model["db"]
    version = event_model["version"]
    starting_revision = version.semantic_revision
    program = add_program_with_actions(event_model)
    with pytest.raises(HTTPException) as direct_patch_rejected:
        create_event_action(
            program["id"],
            {
                "action_type": "component.patch_state",
                "target_kind": "component",
                "target_id": event_model["source"].id,
                "config": {"patch": {"online": False}},
            },
            db,
        )
    assert direct_patch_rejected.value.status_code == 422

    capability = create_event_action(
        program["id"],
        {
            "action_type": "component.capability",
            "target_kind": "component",
            "target_id": event_model["source"].id,
            "config": {
                "capability": "trip",
                "payload": {"severity": 0.9},
                "forward_payload": True,
            },
            "x": 100,
            "y": 80,
        },
        db,
    )
    disable = create_event_action(
        program["id"],
        {
            "action_type": "connection.disable",
            "target_kind": "connection",
            "target_id": event_model["edge"].id,
            "config": {},
            "sequence": 2,
        },
        db,
    )

    moved = update_event_action(disable["id"], {"sequence": 1}, db)
    listed = event_programs(version.id, db)["items"]
    assert moved["sequence"] == 1
    assert [item["id"] for item in listed[0]["actions"]] == [
        disable["id"],
        capability["id"],
    ]
    assert [item["sequence"] for item in listed[0]["actions"]] == [1, 2]

    updated = update_event_program(
        program["id"],
        {"description": "Updated", "layout": {"zoom": 1.25, "pan": [4, 8]}},
        db,
    )
    assert updated["description"] == "Updated"
    assert updated["layout"]["zoom"] == 1.25
    assert db.get(LabModelVersion, version.id).semantic_revision > starting_revision

    version.status = "published"
    db.commit()
    for mutation in (
        lambda: update_event_program(program["id"], {"name": "No"}, db),
        lambda: update_event_action(capability["id"], {"x": 10}, db),
        lambda: delete_event_program(program["id"], db),
    ):
        with pytest.raises(HTTPException) as rejected:
            mutation()
        assert rejected.value.status_code == 409

    version.status = "draft"
    db.commit()
    with pytest.raises(HTTPException) as node_rejected:
        delete_node(event_model["source"].id, db)
    assert node_rejected.value.status_code == 409
    with pytest.raises(HTTPException) as edge_rejected:
        delete_edge(event_model["edge"].id, db)
    assert edge_rejected.value.status_code == 409

    delete_event_action(disable["id"], db)
    delete_event_action(capability["id"], db)
    delete_event_program(program["id"], db)
    assert db.get(LabEventProgram, program["id"]) is None


def test_event_programs_clone_with_component_and_connection_target_mapping(event_model):
    db = event_model["db"]
    program = add_program_with_actions(event_model)
    create_event_action(
        program["id"],
        {
            "action_type": "component.capability",
            "target_kind": "component",
            "target_id": event_model["source"].id,
            "config": {"capability": "trip"},
        },
        db,
    )
    create_event_action(
        program["id"],
        {
            "action_type": "connection.disable",
            "target_kind": "connection",
            "target_id": event_model["edge"].id,
            "config": {},
        },
        db,
    )
    create_event_action(
        program["id"],
        {
            "action_type": "event.emit",
            "config": {
                "event_type": event_model["event_types"]["emitted"],
                "delay_seconds": 5,
                "payload": {"derived": True},
            },
        },
        db,
    )

    cloned_version = clone(event_model["version"].id, db)
    cloned_program = db.scalar(
        select(LabEventProgram).where(
            LabEventProgram.model_version_id == cloned_version["id"]
        )
    )
    cloned_nodes = {
        node.instance_key: node
        for node in db.scalars(
            select(LabNode).where(LabNode.model_version_id == cloned_version["id"])
        )
    }
    cloned_edge = db.scalar(
        select(LabEdge).where(LabEdge.model_version_id == cloned_version["id"])
    )
    cloned_actions = list(
        db.scalars(
            select(LabEventAction)
            .where(LabEventAction.program_id == cloned_program.id)
            .order_by(LabEventAction.sequence)
        )
    )
    assert cloned_program.id != program["id"]
    assert cloned_actions[0].target_id == cloned_nodes["source"].id
    assert cloned_actions[0].target_id != event_model["source"].id
    assert cloned_actions[1].target_id == cloned_edge.id
    assert cloned_actions[1].target_id != event_model["edge"].id
    assert validate_graph(db, cloned_version["id"])["valid"] is True

    project_copy = create_project(
        {
            "name": f"Template copy {uuid4().hex[:8]}",
            "template_version_id": event_model["version"].id,
        },
        db,
    )
    event_model["extra_project_ids"].append(project_copy["project"]["id"])
    copied_program = db.scalar(
        select(LabEventProgram).where(
            LabEventProgram.model_version_id == project_copy["version"]["id"]
        )
    )
    copied_actions = list(
        db.scalars(
            select(LabEventAction)
            .where(LabEventAction.program_id == copied_program.id)
            .order_by(LabEventAction.sequence)
        )
    )
    copied_nodes = {
        node.instance_key: node
        for node in db.scalars(
            select(LabNode).where(
                LabNode.model_version_id == project_copy["version"]["id"]
            )
        )
    }
    copied_edge = db.scalar(
        select(LabEdge).where(
            LabEdge.model_version_id == project_copy["version"]["id"]
        )
    )
    assert copied_actions[0].target_id == copied_nodes["source"].id
    assert copied_actions[1].target_id == copied_edge.id


def test_validation_rejects_zero_delay_event_program_cycle(event_model):
    db = event_model["db"]
    program = add_program_with_actions(event_model)
    emitted = create_event_action(
        program["id"],
        {
            "action_type": "event.emit",
            "config": {
                "event_type": event_model["event_types"]["trigger"],
                "delay_seconds": 0,
                "payload": {},
            },
        },
        db,
    )

    invalid = validate_graph(db, event_model["version"].id)
    assert invalid["valid"] is False
    assert any("цикл" in error.lower() for error in invalid["errors"])

    update_event_action(
        emitted["id"],
        {
            "config": {
                "event_type": event_model["event_types"]["trigger"],
                "delay_seconds": 1,
                "payload": {},
            }
        },
        db,
    )
    assert validate_graph(db, event_model["version"].id)["valid"] is True


def test_event_program_runtime_and_legacy_fallback(event_model):
    db = event_model["db"]
    trigger_program = add_program_with_actions(event_model)
    create_event_action(
        trigger_program["id"],
        {
            "action_type": "component.capability",
            "target_kind": "component",
            "target_id": event_model["source"].id,
            "config": {
                "capability": "trip",
                "payload": {"fixed": "wins"},
                "forward_payload": True,
            },
        },
        db,
    )
    create_event_action(
        trigger_program["id"],
        {
            "action_type": "connection.disable",
            "target_kind": "connection",
            "target_id": event_model["edge"].id,
            "config": {},
        },
        db,
    )
    create_event_action(
        trigger_program["id"],
        {
            "action_type": "event.emit",
            "config": {
                "event_type": event_model["event_types"]["emitted"],
                "delay_seconds": 30,
                "payload": {"derived": True},
            },
        },
        db,
    )
    enable_program = add_program_with_actions(event_model, "enable")
    create_event_action(
        enable_program["id"],
        {
            "action_type": "connection.enable",
            "target_kind": "connection",
            "target_id": event_model["edge"].id,
            "config": {},
        },
        db,
    )
    event_model["version"].status = "published"
    db.commit()

    start = datetime(2026, 8, 29, 12, tzinfo=UTC)
    run = LabRun(
        model_version_id=event_model["version"].id,
        status="paused",
        current_time=start,
        end_time=start + timedelta(minutes=5),
        speed=1,
        idle_speed=1,
        event_speed=1,
        event_speed_duration_seconds=0,
        event_speed_event_types=[],
        seed=42,
        state={},
        summary={},
    )
    db.add(run)
    db.flush()
    trigger = LabRunEvent(
        run_id=run.id,
        sequence=1,
        scheduled_at=start,
        event_type=event_model["event_types"]["trigger"],
        payload={"severity": 0.8, "forwarded": True},
    )
    enable = LabRunEvent(
        run_id=run.id,
        sequence=2,
        scheduled_at=start + timedelta(seconds=10),
        event_type=event_model["event_types"]["enable"],
        payload={},
    )
    db.add_all([trigger, enable])
    db.commit()

    process_next(db, run, max_step_seconds=20)
    db.refresh(trigger)
    db.refresh(run)
    assert trigger.status == "processed"
    assert trigger.result["program_id"] == trigger_program["id"]
    assert [item["type"] for item in trigger.result["actions"]] == [
        "component.capability",
        "connection.disable",
        "event.emit",
    ]
    assert run.state["nodes"][event_model["source"].id]["state"]["online"] is False
    assert run.state["connections"][event_model["edge"].id]["enabled"] is False
    emitted = db.scalar(
        select(LabRunEvent).where(
            LabRunEvent.run_id == run.id,
            LabRunEvent.origin == "program",
        )
    )
    assert emitted.event_type == event_model["event_types"]["emitted"]
    assert emitted.scheduled_at == start + timedelta(seconds=30)
    assert emitted.payload == {"derived": True}
    assert db.get(LabEdge, event_model["edge"].id).enabled is True

    process_next(db, run, max_step_seconds=20)
    db.refresh(enable)
    db.refresh(run)
    assert enable.result["program_id"] == enable_program["id"]
    assert run.state["connections"][event_model["edge"].id]["enabled"] is True

    legacy_run = LabRun(
        model_version_id=event_model["version"].id,
        status="paused",
        current_time=start,
        end_time=start + timedelta(minutes=1),
        speed=1,
        idle_speed=1,
        event_speed=1,
        event_speed_duration_seconds=0,
        event_speed_event_types=[],
        seed=43,
        state={},
        summary={},
    )
    db.add(legacy_run)
    db.flush()
    legacy_event = LabRunEvent(
        run_id=legacy_run.id,
        sequence=1,
        scheduled_at=start,
        event_type="line_fault",
        target_node_id=event_model["source"].id,
        payload={"severity": 0.7},
    )
    db.add(legacy_event)
    db.commit()
    process_next(db, legacy_run, max_step_seconds=1)
    db.refresh(legacy_event)
    db.refresh(legacy_run)
    assert legacy_event.status == "processed"
    assert legacy_event.result == {"targets": 1}
    assert legacy_run.state["nodes"][event_model["source"].id]["state"]["online"] is False


def test_scenario_event_templates_patch_delete_and_program_targeting(
    event_model, monkeypatch
):
    db = event_model["db"]
    program = add_program_with_actions(event_model)
    create_event_action(
        program["id"],
        {
            "action_type": "component.capability",
            "target_kind": "component",
            "target_id": event_model["source"].id,
            "config": {"capability": "trip"},
        },
        db,
    )
    event_model["version"].status = "published"
    db.commit()
    scenario_id = f"event-scenario-{uuid4().hex[:10]}"
    script_id = f"event-scenario-script-{uuid4().hex[:10]}"
    script_version_id = f"{script_id}-v1"
    event_model["scenario_ids"].append(scenario_id)
    event_model["script_ids"].append(script_id)
    db.add(
        LabScript(
            id=script_id,
            name="Event template test calendar",
            kind="scenario",
            description="",
        )
    )
    db.flush()
    db.add(
        LabScriptVersion(
            id=script_version_id,
            script_id=script_id,
            version=1,
            status="published",
            code="""
def before_start(ctx):
    for event in ctx.parameters.get("script_events", []):
        ctx.clock.schedule(
            event["offset_seconds"], event["event_type"],
            event.get("payload", {}), event.get("target"),
            event.get("priority", 100), phase=event.get("phase", "scenario"),
            title=event.get("title", event["event_type"]),
            evidence=event.get("evidence", "assumed"),
        )
""",
            contract={},
            validation={"valid": True},
        )
    )
    db.commit()
    scenario = LabScenario(
        id=scenario_id,
        model_version_id=event_model["version"].id,
        name="Editable scenario calendar",
        description="",
        origin="test",
        start_at=datetime(2026, 8, 29, tzinfo=UTC),
        duration_seconds=3600,
        seed=42,
        events=[],
        expected={},
        incident_at=datetime(2026, 8, 29, 0, 30, tzinfo=UTC),
        configuration={
            "scenario_script_version_id": script_version_id,
            "timeline": {
                "start": datetime(2026, 8, 29, tzinfo=UTC).isoformat(),
                "incident": datetime(2026, 8, 29, 0, 30, tzinfo=UTC).isoformat(),
                "end": datetime(2026, 8, 29, 1, tzinfo=UTC).isoformat(),
            },
            "script_events": [
                {
                    "offset_seconds": 10,
                    "event_type": event_model["event_types"]["emitted"],
                    "payload": {"stale": True},
                }
            ],
        },
    )
    db.add(scenario)
    db.commit()

    with pytest.raises(HTTPException) as missing_payload:
        create_scenario_event(
            scenario.id,
            {"event_type": event_model["event_types"]["trigger"]},
            db,
        )
    assert missing_payload.value.status_code == 422

    created = create_scenario_event(
        scenario.id,
        {
            "event_type": event_model["event_types"]["trigger"],
            "offset_seconds": 60,
            "title": "Original",
            "payload": {"severity": 0.6},
        },
        db,
    )
    assert created["target_node_id"] is None
    updated = update_scenario_event(
        created["id"],
        {
            "offset_seconds": 90,
            "title": "Updated",
            "payload": {"severity": 0.95},
        },
        db,
    )
    assert updated["title"] == "Updated"
    assert updated["offset_seconds"] == 90
    assert updated["payload"]["severity"] == 0.95

    run = LabRun(
        model_version_id=event_model["version"].id,
        scenario_id=scenario.id,
        status="paused",
        current_time=scenario.start_at,
        end_time=scenario.start_at + timedelta(hours=1),
        speed=1,
        idle_speed=1,
        event_speed=1,
        event_speed_duration_seconds=0,
        event_speed_event_types=[],
        seed=42,
        state={},
        summary={},
    )
    db.add(run)
    db.commit()
    prepare_run(db, run)
    scheduled = db.scalar(
        select(LabRunEvent).where(LabRunEvent.run_id == run.id)
    )
    assert scheduled.event_type == event_model["event_types"]["trigger"]
    assert scheduled.scheduled_at == scenario.start_at + timedelta(seconds=90)
    assert scheduled.payload["severity"] == 0.95
    assert scheduled.payload["_title"] == "Updated"
    assert "stale" not in scheduled.payload

    scenario.configuration = {}
    db.commit()
    monkeypatch.setattr("app.api.model_lab.enqueue_simulation", lambda _run_id: None)
    non_scripted = start_run(
        {
            "model_version_id": event_model["version"].id,
            "scenario_id": scenario.id,
            "duration_seconds": 3600,
        },
        db,
    )
    calendar_event = db.scalar(
        select(LabRunEvent).where(LabRunEvent.run_id == non_scripted["id"])
    )
    assert calendar_event.event_type == event_model["event_types"]["trigger"]
    assert calendar_event.scheduled_at == scenario.start_at + timedelta(seconds=90)
    assert calendar_event.payload["severity"] == 0.95

    processed = LabRunEvent(
        run_id=run.id,
        sequence=2,
        scheduled_at=scenario.start_at,
        processed_at=datetime.now(UTC),
        event_type=event_model["event_types"]["trigger"],
        status="processed",
        payload={"severity": 0.5},
    )
    db.add(processed)
    db.commit()
    with pytest.raises(HTTPException) as run_event_rejected:
        update_scenario_event(processed.id, {"title": "Must stay immutable"}, db)
    assert run_event_rejected.value.status_code == 404

    delete_scenario_event(created["id"], db)
    assert db.get(LabScenarioEventTemplate, created["id"]) is None
