from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.lab_seed import PROCESS_SCRIPT, SCRIPT
from app.models import LabMonitorTemplate, LabProject, LabScenario, LabScenarioEventTemplate, LabWorkflowNode, LabWorkflowVersion
from app.services.model_lab import execute_script, replay_scenario


def context(mode="generation"):
    return {"time": datetime(2026, 1, 1, tzinfo=UTC).isoformat(), "parameters": {"mode": mode, "capacity_mw": 100, "efficiency": .4, "fuel_mw": 200}, "state": {}, "inputs": {}, "seed": 42}


def test_python_contract_initializes_and_ticks_deterministically():
    initialized = execute_script(SCRIPT, "initialize", context())
    first = execute_script(SCRIPT, "tick", {**context(), "state": initialized["state"]}, dt=3600)
    second = execute_script(SCRIPT, "tick", {**context(), "state": initialized["state"]}, dt=3600)
    assert first == second
    assert first["outputs"]["electric_power_mw"] == pytest.approx(74.088)
    assert first["outputs"]["gas_consumption_mw"] == 200
    assert first["outputs"]["co2_tph"] > 0


def test_failure_and_repair_change_component_state():
    initialized = execute_script(SCRIPT, "initialize", context("transfer"))
    failed = execute_script(SCRIPT, "event", {**context("transfer"), "state": initialized["state"]}, event={"type": "line_fault", "payload": {"severity": .8}})
    assert failed["state"]["online"] is False
    repaired = execute_script(SCRIPT, "event", {**context("transfer"), "state": failed["state"]}, event={"type": "repair", "payload": {}})
    assert repaired["state"]["online"] is True


def test_runaway_python_is_terminated():
    with pytest.raises(RuntimeError, match="exceeded"):
        execute_script("def on_tick(ctx, dt):\n    while True: pass", "tick", context(), dt=1, timeout=.1)


def test_release_gate_replays_all_15_scenarios():
    with SessionLocal() as db:
        project = db.scalar(select(LabProject).where(LabProject.id == "model-lab-energy"))
        scenarios = [
            scenario
            for scenario in db.scalars(
                select(LabScenario).where(LabScenario.id != "baseline")
            )
            if not scenario.configuration.get("deprecated")
        ]
        assert len(scenarios) == 15
        assert len({scenario.model_version_id for scenario in scenarios}) == 15
        reports = [replay_scenario(db, scenario, scenario.model_version_id) for scenario in scenarios]
        assert all(report["passed"] for report in reports)


def test_active_draft_has_a_monitor_template():
    with SessionLocal() as db:
        project = db.get(LabProject, "model-lab-energy")
        assert project.active_draft_id
        monitor = db.scalar(
            select(LabMonitorTemplate).where(
                LabMonitorTemplate.model_version_id == project.active_draft_id
            )
        )
        assert monitor is not None


def test_storm_arwen_is_a_scripted_package_with_24h_lead_in():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "storm-arwen-2021")
        events = list(db.scalars(select(LabScenarioEventTemplate).where(LabScenarioEventTemplate.scenario_id == scenario.id).order_by(LabScenarioEventTemplate.offset_seconds)))
        workflow = db.get(LabWorkflowVersion, scenario.configuration["workflow_version_id"])
        nodes = list(db.scalars(select(LabWorkflowNode).where(LabWorkflowNode.workflow_version_id == workflow.id)))
        assert (scenario.incident_at - scenario.start_at).total_seconds() == 86400
        assert len(events) >= 23
        assert {82, 84.1, 99, 100}.issubset({event.payload.get("percent") for event in events})
        assert workflow.status == "published" and len(nodes) >= 10
        assert scenario.configuration["process_script_version_id"] == "process-resource-v1"


def test_storm_arwen_keeps_plant_energized_when_consumer_point_loses_voltage():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "storm-arwen-2021")
        report = replay_scenario(db, scenario, scenario.model_version_id)
        first_fault = report["trace"][0]["metrics"]
        plant = first_fault["node_metrics"]["ar-upstream-generation"]
        consumer = first_fault["node_metrics"]["ar-customers"]
        assert first_fault["frequency_hz"] == 50
        assert plant["voltage_pu"] > .95 and plant["frequency_hz"] == 50
        assert consumer["voltage_pu"] == 0 and consumer["frequency_hz"] == 0


def test_new_process_behavior_is_defined_only_by_data_and_script():
    parameters = {"process_rules": {"novel_event": [
        {"kind": "resource.reserve", "args": {"resource_id": "novel-part", "quantity": 3, "unit": "kit"}},
        {"kind": "metric.publish", "args": {"metric_id": "novel_metric", "value": 7, "unit": "x"}},
    ]}}
    result = execute_script(PROCESS_SCRIPT, "event", {**context(), "parameters": parameters, "snapshot": {"resources": {"novel-part": {"available": 4}}}}, event={"type": "novel_event", "payload": {}})
    assert [(item["group"], item["action"]) for item in result["operations"]] == [("resources", "reserve"), ("metrics", "publish")]
