from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    LabNode,
    LabProcessSetWorkflow,
    LabProcessSetVersion,
    LabRun,
    LabRunEvent,
    LabScenario,
    LabScenarioAssemblyMember,
    LabScenarioAssemblyNodeMap,
    LabScenarioAssemblyVersion,
    LabScenarioProcessBinding,
    LabWorkflowInstance,
    LabWorkflow,
    LabWorkflowNode,
    LabWorkflowToken,
    LabWorkflowTransition,
    LabWorkflowVersion,
)
from app.participant_catalog import PILOT_PARTICIPANTS
from app.services.bpmn_profile import validate_bpmn
from app.services.model_lab import (
    _advance_workflows,
    _route_event_to_processes,
    complete_manual_workflow_task,
    schedule_timer_start_events,
)


def test_every_scenario_process_has_a_ukrainian_bpmn_description():
    with SessionLocal() as db:
        scenarios = list(db.scalars(select(LabScenario).where(LabScenario.assembly_version_id.is_not(None))))
        described_workflows: set[str] = set()
        for scenario in scenarios:
            bindings = db.scalars(
                select(LabScenarioProcessBinding).where(
                    LabScenarioProcessBinding.assembly_version_id == scenario.assembly_version_id
                )
            )
            for binding in bindings:
                activations = db.scalars(
                    select(LabProcessSetWorkflow).where(
                        LabProcessSetWorkflow.process_set_version_id == binding.process_set_version_id
                    )
                )
                for activation in activations:
                    version = db.get(LabWorkflowVersion, activation.workflow_version_id)
                    assert version is not None
                    assert version.description.startswith("Ця схема BPMN 2.0 описує реагування організації ")
                    assert scenario.name in version.description
                    described_workflows.add(version.id)

        assert len(described_workflows) >= len(scenarios)


def test_every_stored_workflow_has_valid_explicit_bpmn_boundaries():
    with SessionLocal() as db:
        versions = list(db.scalars(select(LabWorkflowVersion)))
        assert versions
        for version in versions:
            report = validate_bpmn(version.bpmn_xml)
            assert report["valid"], (version.name, report["errors"])
            nodes = list(db.scalars(select(LabWorkflowNode).where(LabWorkflowNode.workflow_version_id == version.id)))
            assert any(node.block_type == "start_event" for node in nodes)
            assert any(node.block_type == "end_event" for node in nodes)
            assert all(node.name != "Start by event" for node in nodes)


def test_token_runtime_follows_sequence_flow_to_explicit_end():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "southwest-2011")
        run = LabRun(model_version_id=scenario.model_version_id, scenario_id=scenario.id, assembly_version_id=scenario.assembly_version_id, status="running", current_time=scenario.start_at, end_time=scenario.start_at + timedelta(hours=1), seed=42, state={})
        db.add(run); db.flush()
        trigger = LabRunEvent(run_id=run.id, sequence=1, scheduled_at=run.current_time, event_type="operator_error", target_node_id="sw-hng-line", origin="test", payload={})
        db.add(trigger); db.flush()

        started = _advance_workflows(db, run, trigger, {})
        assert started
        instance = db.scalar(select(LabWorkflowInstance).where(LabWorkflowInstance.run_id == run.id, LabWorkflowInstance.variables["participant_alias"].astext == "aps"))
        current = db.get(LabWorkflowNode, instance.current_node_id)
        assert current.node_key == "isolate_line"

        for event_type in ["hng.isolation_started", "hng.restoration_started"]:
            sequence = (db.scalar(select(func.max(LabRunEvent.sequence)).where(LabRunEvent.run_id == run.id)) or 0) + 1
            event = LabRunEvent(run_id=run.id, sequence=sequence, scheduled_at=run.current_time, event_type=event_type, origin="test", payload={})
            db.add(event); db.flush()
            _advance_workflows(db, run, event, {})

        assert instance.status == "completed"
        assert instance.current_node_id is None
        assert not list(db.scalars(select(LabWorkflowToken).where(LabWorkflowToken.instance_id == instance.id, LabWorkflowToken.status == "active")))
        db.rollback()


def test_operator_can_complete_manual_task_and_reach_end_event():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "southwest-2011")
        workflow = LabWorkflow(name="Manual task test")
        db.add(workflow); db.flush()
        version = LabWorkflowVersion(workflow_id=workflow.id, name="Manual task test", version=1, status="draft")
        db.add(version); db.flush()
        start = LabWorkflowNode(workflow_version_id=version.id, node_key="start", block_type="start_event", name="Message received", config={"event_definition": "message", "event_type": "test.start"})
        task = LabWorkflowNode(workflow_version_id=version.id, node_key="approve", block_type="user_task", name="Approve restoration", config={"manual_completion": True})
        end = LabWorkflowNode(workflow_version_id=version.id, node_key="end", block_type="end_event", name="Restoration approved", config={"event_definition": "none"})
        db.add_all([start, task, end]); db.flush()
        db.add_all([
            LabWorkflowTransition(workflow_version_id=version.id, source_node_id=start.id, target_node_id=task.id),
            LabWorkflowTransition(workflow_version_id=version.id, source_node_id=task.id, target_node_id=end.id),
        ])
        run = LabRun(model_version_id=scenario.model_version_id, scenario_id=scenario.id, status="paused", current_time=scenario.start_at, end_time=scenario.start_at + timedelta(hours=1), seed=42, state={})
        db.add(run); db.flush()
        instance = LabWorkflowInstance(run_id=run.id, workflow_version_id=version.id, status="running", current_node_id=task.id, variables={})
        db.add(instance); db.flush()
        token = LabWorkflowToken(instance_id=instance.id, node_id=task.id, status="active", entered_at=run.current_time, data={})
        db.add(token); db.flush()

        complete_manual_workflow_task(db, run, token, completed_by="dispatcher", result={"approved": True})

        assert token.status == "completed"
        assert token.data["completed_by"] == "dispatcher"
        assert instance.status == "completed"
        assert instance.current_node_id is None
        db.rollback()


def test_timer_start_event_is_registered_on_run_creation():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "southwest-2011")
        binding = db.scalar(select(LabScenarioProcessBinding).where(LabScenarioProcessBinding.assembly_version_id == scenario.assembly_version_id))
        activation = db.scalar(select(LabProcessSetWorkflow).where(LabProcessSetWorkflow.process_set_version_id == binding.process_set_version_id))
        start = db.scalar(select(LabWorkflowNode).where(LabWorkflowNode.workflow_version_id == activation.workflow_version_id, LabWorkflowNode.block_type == "start_event"))
        start.config = {**(start.config or {}), "event_definition": "timer", "timer_kind": "timeDuration", "timer_value": "PT5M"}
        run = LabRun(model_version_id=scenario.model_version_id, scenario_id=scenario.id, assembly_version_id=scenario.assembly_version_id, status="paused", current_time=scenario.start_at, end_time=scenario.start_at + timedelta(hours=1), seed=42, state={})
        db.add(run); db.flush()

        assert schedule_timer_start_events(db, run) == 1
        timer = db.scalar(select(LabRunEvent).where(LabRunEvent.run_id == run.id, LabRunEvent.origin == "workflow_timer_start"))
        assert timer.scheduled_at == run.current_time + timedelta(minutes=5)
        assert timer.payload["_timer_start_node"] == start.node_key
        db.rollback()


@pytest.mark.parametrize("scenario_id", ["southwest-2011", "macondo", "storm-arwen-2021"])
def test_pilot_composition_partitions_assets_between_participants(scenario_id):
    with SessionLocal() as db:
        scenario = db.get(LabScenario, scenario_id)
        assembly = db.get(LabScenarioAssemblyVersion, scenario.assembly_version_id)
        members = list(db.scalars(select(LabScenarioAssemblyMember).where(LabScenarioAssemblyMember.assembly_version_id == assembly.id)))
        mappings = list(db.scalars(select(LabScenarioAssemblyNodeMap).where(LabScenarioAssemblyNodeMap.assembly_version_id == assembly.id)))
        composite_nodes = set(db.scalars(select(LabNode.id).where(LabNode.model_version_id == assembly.composite_model_version_id)))
        bindings = list(db.scalars(select(LabScenarioProcessBinding).where(LabScenarioProcessBinding.assembly_version_id == assembly.id)))

        assert assembly.status == "published"
        assert assembly.validation["cross_organization_policy"] == "roles_and_messages"
        assert {member.alias for member in members} == {actor["alias"] for actor in PILOT_PARTICIPANTS[scenario_id]["actors"]}
        assert {mapping.composite_node_id for mapping in mappings} == composite_nodes
        assert len(bindings) == len(members)
        assert all(db.get(LabProcessSetVersion, item.process_set_version_id).status == "published" for item in bindings)
        assert all(member.evidence.get("source_url") for member in members)


@pytest.mark.parametrize(
    ("scenario_id", "event_type", "target", "expected_aliases"),
    [
        ("southwest-2011", "operator_error", "sw-hng-line", {"aps", "iid", "sce", "sdge", "cfe"}),
        ("macondo", "barrier_failure", "mc-cement-barrier", {"bp", "transocean", "unified-command"}),
        ("storm-arwen-2021", "distribution_fault", "ar-distribution-segment", {"dno", "newsac", "ofgem-beis"}),
    ],
)
def test_event_routes_to_owner_process_then_role_addressed_messages(scenario_id, event_type, target, expected_aliases):
    with SessionLocal() as db:
        scenario = db.get(LabScenario, scenario_id)
        run = LabRun(model_version_id=scenario.model_version_id, scenario_id=scenario.id, assembly_version_id=scenario.assembly_version_id, status="running", current_time=scenario.start_at, end_time=scenario.start_at + timedelta(hours=1), seed=42, state={})
        db.add(run); db.flush()
        trigger = LabRunEvent(run_id=run.id, sequence=1, scheduled_at=run.current_time, event_type=event_type, target_node_id=target, origin="test", payload={})
        db.add(trigger); db.flush()

        first = _route_event_to_processes(db, run, trigger)
        assert len(first) == 1
        messages = list(db.scalars(select(LabRunEvent).where(LabRunEvent.run_id == run.id, LabRunEvent.origin == "workflow")))
        for message in messages:
            _route_event_to_processes(db, run, message)

        instances = list(db.scalars(select(LabWorkflowInstance).where(LabWorkflowInstance.run_id == run.id)))
        aliases = {instance.variables["participant_alias"] for instance in instances}
        assert aliases == expected_aliases
        assert len({instance.correlation_id for instance in instances}) == 1
        db.rollback()
