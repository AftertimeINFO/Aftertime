from app.qualification_cases import QUALIFICATION_CASES
from xml.etree import ElementTree

from app.services.bpmn_profile import (
    DI_NS,
    NS,
    build_bpmn_xml,
    meaningful_end_name,
    parse_bpmn,
    repair_bpmn_presentation,
    validate_bpmn,
)


def _process(event_definition: str = "message") -> tuple[list[dict], list[dict]]:
    nodes = [
        {
            "node_key": "start",
            "block_type": "start_event",
            "name": "Отримано аварійне повідомлення",
            "x": 80,
            "y": 120,
            "config": {
                "event_definition": event_definition,
                "event_type": "grid.fault" if event_definition != "none" else None,
            },
        },
        {
            "node_key": "repair",
            "block_type": "service_task",
            "name": "Виконати ремонт",
            "x": 280,
            "y": 120,
            "config": {"target_ref": "line-1", "capability": "repair.completed"},
        },
        {
            "node_key": "end",
            "block_type": "end_event",
            "name": "Ремонт завершено",
            "x": 500,
            "y": 120,
            "config": {"event_definition": "none"},
        },
    ]
    flows = [
        {"flow_key": "f1", "source_key": "start", "target_key": "repair"},
        {"flow_key": "f2", "source_key": "repair", "target_key": "end"},
    ]
    return nodes, flows


def test_executable_profile_round_trips_typed_start_and_end() -> None:
    nodes, flows = _process()
    xml = build_bpmn_xml("repair-process", "Ремонт ЛЕП", nodes, flows)
    report = validate_bpmn(xml)
    projection = parse_bpmn(xml)

    assert report["valid"] is True
    assert [node["block_type"] for node in projection.nodes] == [
        "start_event",
        "service_task",
        "end_event",
    ]
    assert projection.nodes[0]["config"]["event_definition"] == "message"
    assert projection.nodes[0]["config"]["event_type"] == "grid.fault"


def test_profile_rejects_process_without_explicit_end() -> None:
    nodes, flows = _process()
    xml = build_bpmn_xml("broken", "Незавершений процес", nodes[:-1], flows[:-1])

    report = validate_bpmn(xml)

    assert report["valid"] is False
    assert "явний End Event" in " ".join(report["errors"])


def test_profile_rejects_outgoing_sequence_flow_from_end() -> None:
    nodes, flows = _process()
    flows.append({"flow_key": "invalid", "source_key": "end", "target_key": "repair"})
    xml = build_bpmn_xml("broken-end", "Некоректне завершення", nodes, flows)

    report = validate_bpmn(xml)

    assert report["valid"] is False
    assert "не може мати вихідний" in " ".join(report["errors"])


def test_all_qualification_processes_use_valid_bpmn() -> None:
    reports = [
        (scenario_id, process["id"], validate_bpmn(process["bpmn_xml"]))
        for scenario_id, package in QUALIFICATION_CASES.items()
        for process in package.get("processes", [])
    ]

    assert reports
    assert [
        (scenario_id, process_id, report["errors"])
        for scenario_id, process_id, report in reports
        if not report["valid"]
    ] == []


def test_sequence_flows_connect_shape_borders_not_task_centers() -> None:
    nodes, flows = _process()
    xml = build_bpmn_xml("repair-process", "Ремонт ЛЕП", nodes, flows)
    root = ElementTree.fromstring(xml)
    edges = root.findall(".//bpmndi:BPMNEdge", NS)
    first = edges[0].findall(f"{{{DI_NS}}}waypoint")
    second = edges[1].findall(f"{{{DI_NS}}}waypoint")

    assert float(first[0].get("x")) == 116  # Start Event right border: 80 + 36
    assert float(first[1].get("x")) == 280  # Task left border
    assert float(second[0].get("x")) == 430  # Task right border: 280 + 150
    assert float(second[1].get("x")) == 500  # End Event left border


def test_generic_end_label_is_repaired_from_last_business_action() -> None:
    nodes, flows = _process()
    nodes[-1]["name"] = "Процес завершено"
    xml = build_bpmn_xml("repair-process", "H-NG response", nodes, flows)
    repaired, renamed = repair_bpmn_presentation(xml)
    projection = parse_bpmn(repaired)

    assert meaningful_end_name("APS response", "Restore H-NG") == "H-NG restored"
    assert renamed == {"end": "Ремонт виконано"}
    assert projection.nodes[-1]["name"] == "Ремонт виконано"
