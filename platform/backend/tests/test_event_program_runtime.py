from datetime import UTC, datetime
from types import SimpleNamespace

from app.services import model_lab


class FakeSession:
    def __init__(self, program, scalar_batches):
        self.program = program
        self.scalar_batches = list(scalar_batches)
        self.added = []

    def scalar(self, _statement):
        return self.program

    def scalars(self, _statement):
        return iter(self.scalar_batches.pop(0))

    def add(self, value):
        self.added.append(value)


def component_fixture():
    component = SimpleNamespace(
        id="type-1",
        initial_state={"online": True, "level": 1.0, "nested": {}},
        python_code="",
    )
    node = SimpleNamespace(
        id="node-1",
        name="Pump",
        component_type_id=component.id,
        refinement_contract={"capabilities": ["trip"]},
        initial_state={"online": True},
        parameters={},
        python_code=None,
    )
    return node, component


def test_effective_connections_use_run_state_even_for_initially_disabled_edges():
    first = SimpleNamespace(id="edge-1", enabled=True)
    second = SimpleNamespace(id="edge-2", enabled=False)
    state = {
        "connections": {
            "edge-1": {"enabled": False},
            "edge-2": {"enabled": True},
        }
    }

    assert model_lab._effective_edges([first, second], state) == [second]


def test_action_diagnostics_enforce_declared_capabilities_and_primitive_patches():
    node, component = component_fixture()
    nodes = {node.id: node}
    types = {component.id: component}

    assert model_lab.event_action_diagnostics(
        {
            "action_type": "component.capability",
            "target_kind": "component",
            "target_id": node.id,
            "config": {"capability": "trip", "payload": {}, "forward_payload": True},
        },
        nodes,
        {},
        types,
    ) == []
    assert model_lab.event_action_diagnostics(
        {
            "action_type": "component.patch_state",
            "target_kind": "component",
            "target_id": node.id,
            "config": {"patch": {"online": 1}},
        },
        nodes,
        {},
        types,
    )
    assert model_lab.event_action_diagnostics(
        {
            "action_type": "component.patch_state",
            "target_kind": "component",
            "target_id": node.id,
            "config": {"patch": {"nested": {"value": 1}}},
        },
        nodes,
        {},
        types,
    )


def test_zero_delay_emission_cycle_is_detected_but_delayed_recursion_is_allowed():
    first = SimpleNamespace(id="program-a", event_type_id="event.a", enabled=True)
    second = SimpleNamespace(id="program-b", event_type_id="event.b", enabled=True)
    immediate = {
        first.id: [
            SimpleNamespace(
                action_type="event.emit",
                config={"event_type": "event.b", "delay_seconds": 0},
            )
        ],
        second.id: [
            SimpleNamespace(
                action_type="event.emit",
                config={"event_type": "event.a", "delay_seconds": 0},
            )
        ],
    }

    assert model_lab._zero_delay_emit_cycle([first, second], immediate) == [
        "event.a",
        "event.b",
        "event.a",
    ]
    immediate[second.id][0].config["delay_seconds"] = 1
    assert model_lab._zero_delay_emit_cycle([first, second], immediate) is None


def test_event_emit_requires_a_registered_event_type_when_catalog_is_supplied():
    errors = model_lab.event_action_diagnostics(
        {
            "action_type": "event.emit",
            "target_kind": None,
            "target_id": None,
            "config": {"event_type": "unknown", "delay_seconds": 0, "payload": {}},
        },
        {},
        {},
        {},
        {"known"},
    )

    assert any("невідомий тип події" in item for item in errors)


def test_program_capability_filters_metadata_and_fixed_payload_wins(monkeypatch):
    node, component = component_fixture()
    program = SimpleNamespace(id="program-1")
    action = SimpleNamespace(
        id="action-1",
        sequence=1,
        action_type="component.capability",
        target_kind="component",
        target_id=node.id,
        config={
            "capability": "trip",
            "forward_payload": True,
            "payload": {"severity": 0.8, "fixed": True},
        },
    )
    db = FakeSession(program, [[action], [7], ["trigger"]])
    run = SimpleNamespace(
        id="run-1",
        model_version_id="version-1",
        current_time=datetime(2026, 1, 1, tzinfo=UTC),
        seed=42,
    )
    event = SimpleNamespace(
        event_type="trigger",
        payload={"severity": 0.2, "source": "sensor", "_phase": "incident"},
        sequence=7,
        status="scheduled",
        processed_at=None,
        result={},
    )
    state = {
        "nodes": {
            node.id: {"state": {"online": True}, "outputs": {}, "logs": []}
        }
    }
    captured = {}

    def execute(_code, action_name, _context, *, event=None, **_kwargs):
        captured.update(action=action_name, event=event)
        return {"state": {"online": False}, "outputs": {}, "logs": ["trip"]}

    monkeypatch.setattr(model_lab, "execute_script", execute)

    assert model_lab._execute_event_program(
        db, run, event, state, [node], [], {component.id: component}
    ) is True
    assert captured == {
        "action": "event",
        "event": {
            "type": "trip",
            "payload": {"severity": 0.8, "source": "sensor", "fixed": True},
        },
    }
    assert state["nodes"][node.id]["state"]["online"] is False
    assert event.status == "processed"
    assert event.result["program_id"] == program.id
    assert event.result["actions"][0]["status"] == "completed"


def test_invalid_program_action_fails_only_the_event():
    node, component = component_fixture()
    program = SimpleNamespace(id="program-1")
    action = SimpleNamespace(
        id="action-1",
        sequence=1,
        action_type="component.patch_state",
        target_kind="component",
        target_id=node.id,
        config={"patch": {"missing": True}},
    )
    db = FakeSession(program, [[action], [1], ["trigger"]])
    run = SimpleNamespace(
        id="run-1",
        model_version_id="version-1",
        current_time=datetime(2026, 1, 1, tzinfo=UTC),
        seed=42,
    )
    event = SimpleNamespace(
        event_type="trigger",
        payload={},
        sequence=1,
        status="scheduled",
        processed_at=None,
        result={},
    )
    state = {
        "nodes": {
            node.id: {"state": {"online": True}, "outputs": {}, "logs": []}
        }
    }

    assert model_lab._execute_event_program(
        db, run, event, state, [node], [], {component.id: component}
    ) is True
    assert event.status == "failed"
    assert event.processed_at is not None
    assert event.result["actions"][0]["status"] == "failed"
    assert state["nodes"][node.id]["state"] == {"online": True}
