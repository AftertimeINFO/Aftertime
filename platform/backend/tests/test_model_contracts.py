from types import SimpleNamespace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.model_lab import add_edge, start_run
from app.db import SessionLocal
from app.lab_seed import component_ports
from app.models import LabEdge, LabRun
from app.services.model_contracts import (
    connection_diagnostics,
    normalized_ports,
    observable_catalog,
)
from app.services.model_lab import _network_metrics, _ordered_nodes, validate_graph
from app.services.cep import evaluate_rules
from app.services.run_queue import SimulationQueueUnavailable


def component(component_id: str, category: str, output: str):
    return SimpleNamespace(
        id=component_id,
        name=component_id,
        category=category,
        ports=component_ports(component_id, category, output),
    )


def node(node_id: str, component_type_id: str, key: str, x: float = 0):
    return SimpleNamespace(
        id=node_id,
        component_type_id=component_type_id,
        instance_key=key,
        name=key,
        x=x,
        y=0,
        parameters={},
        port_overrides={},
        observable_overrides={},
    )


def edge(source: str, target: str, *, domain: str = "electric.ac"):
    return SimpleNamespace(
        id=f"{source}-{target}",
        source_node_id=source,
        target_node_id=target,
        source_port="out",
        target_port="in",
        flow_type="electricity",
        domain=domain,
        enabled=True,
        connection_key=f"{source}-to-{target}",
        parameters={},
    )


def test_steam_plant_contract_exposes_physics_and_staff_ports():
    ports = normalized_ports(component("steam-plant", "generation", "electric_power_mw"))
    assert {item["domain"] for item in ports} >= {
        "natural_gas", "water_steam", "staff", "electric.ac", "emission"
    }
    electrical = next(item for item in ports if item["domain"] == "electric.ac")
    assert {item["key"] for item in electrical["variables"]} >= {
        "voltage_pu", "frequency_hz", "electric_power_mw", "reactive_power_mvar"
    }


def test_connection_contract_rejects_cross_domain_link():
    gas = component("pipeline", "gas", "gas_flow_mw")
    grid = component("step-up", "substation", "electric_power_mw")
    diagnostics = connection_diagnostics(gas, "out", grid, "in")
    assert "Несумісні середовища: natural_gas → electric.ac" in diagnostics
    assert "Несумісні фізичні величини: gas_energy_flow → three_phase_power" in diagnostics


def test_observables_are_derived_from_selected_graph_element():
    plant_type = component("steam-plant", "generation", "electric_power_mw")
    plant = node("n-plant", "steam-plant", "plant-1")
    plant.parameters = {"output_key": "electric_power_mw"}
    catalog = observable_catalog([plant], {"steam-plant": plant_type}, [], [])
    addresses = {item["address"] for item in catalog}
    assert "component:plant-1:frequency_hz" in addresses
    assert "component:plant-1:electric_power_mw" in addresses
    assert all(item["target_id"] == plant.id for item in catalog)


def test_output_observable_inherits_its_port_unit_without_manual_metric_definition():
    """Regression: generated output series was shown as a unitless number."""
    stock_type = component("gas-stock", "resource", "gas_energy_mw")
    stock = node("n-stock", "gas-stock", "stock-1")
    stock.parameters = {"output_key": "gas_energy_mw"}

    observable = next(
        item for item in observable_catalog([stock], {"gas-stock": stock_type}, [], [])
        if item["metric_key"] == "gas_energy_mw"
    )

    assert observable["unit"] == "MW"


def test_canvas_coordinates_do_not_change_execution_order():
    source = node("source", "source", "a-source", x=900)
    target = node("target", "target", "z-target", x=0)
    ordered = _ordered_nodes([target, source], [edge("source", "target")])
    assert [item.id for item in ordered] == ["source", "target"]


def test_cep_sequence_emits_once_and_rearms_after_condition_clears():
    rule = SimpleNamespace(
        id="fault-trip",
        condition={
            "operator": "sequence", "event_types": ["line_fault", "trip"],
            "window_seconds": 30, "cooldown_seconds": 60,
        },
        emit={"event_type": "cascade_detected", "payload": {"severity": "high"}},
    )
    state = {}
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert evaluate_rules([rule], state, start, {}, ["line_fault"]) == []
    emitted = evaluate_rules([rule], state, start + timedelta(seconds=10), {}, ["trip"])
    assert emitted == [{"event_type": "cascade_detected", "payload": {"severity": "high"}}]
    assert evaluate_rules([rule], state, start + timedelta(seconds=11), {}, []) == []


def test_cep_duration_and_hysteresis_are_checkpointable():
    rule = SimpleNamespace(
        id="low-frequency",
        condition={
            "operator": "duration", "seconds": 5,
            "condition": {"operator": "compare", "observable": "frequency_hz", "comparison": "lt", "value": 49.5, "hysteresis": 0.05},
        },
        emit={"event_type": "underfrequency"},
    )
    state = {}
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert evaluate_rules([rule], state, start, {"frequency_hz": 49.0}, []) == []
    assert evaluate_rules([rule], state, start + timedelta(seconds=5), {"frequency_hz": 49.0}, []) == [{"event_type": "underfrequency"}]
    assert "root:since" in state["cep"]["rules"]["low-frequency"]


def test_rejected_emission_to_gas_connection_does_not_poison_model():
    """Regression: UI once tried to connect the TPP CO₂ port to a gas input."""
    with SessionLocal() as db:
        before = db.scalar(
            select(func.count()).select_from(LabEdge).where(
                LabEdge.model_version_id == "energy-draft"
            )
        )
        with pytest.raises(HTTPException) as rejected:
            add_edge("energy-draft", {
                "source_node_id": "d-steam-plant",
                "source_port": "emissions",
                "target_node_id": "d-pipeline",
                "target_port": "in",
            }, db)
        after = db.scalar(
            select(func.count()).select_from(LabEdge).where(
                LabEdge.model_version_id == "energy-draft"
            )
        )
        assert rejected.value.status_code == 422
        assert any("emission → natural_gas" in item for item in rejected.value.detail["errors"])
        assert before == after
        assert validate_graph(db, "energy-draft")["valid"] is True


def test_unavailable_simulation_queue_returns_retryable_503(monkeypatch):
    """Regression: a corrupted Redis AOF previously surfaced as an opaque HTTP 500."""
    def unavailable(_run_id: str, _layer: str = "dev") -> None:
        raise SimulationQueueUnavailable("queue offline")

    monkeypatch.setattr("app.api.model_lab.enqueue_simulation", unavailable)
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as rejected:
            start_run({
                "model_version_id": "energy-published",
                "scenario_id": "baseline",
                "duration_seconds": 60,
            }, db)

        detail = rejected.value.detail
        run = db.get(LabRun, detail["run_id"])
        assert rejected.value.status_code == 503
        assert detail["retryable"] is True
        assert run.status == "queue_waiting"
        assert "resume" in run.error
        db.delete(run)
        db.commit()


def test_component_outputs_are_recorded_for_diagnostic_charts():
    """Regression: added gas_energy_mw series had no historical values to draw."""
    stock = node("gas-stock", "gas-stock-type", "gas-stock")
    state = {
        "nodes": {
            stock.id: {
                "state": {"online": True, "resource_mwh": 1000},
                "outputs": {
                    "gas_energy_mw": 500,
                    "gas_flow_mw": 423.55,
                    "alarm": False,
                    "label": "stock",
                },
            }
        }
    }
    metrics = _network_metrics(
        [stock],
        [],
        state,
        {"gas-stock-type": SimpleNamespace(category="resource")},
    )

    recorded = metrics["node_metrics"][stock.id]
    assert recorded["gas_energy_mw"] == 500
    assert recorded["gas_flow_mw"] == 423.55
    assert "alarm" not in recorded and "label" not in recorded
