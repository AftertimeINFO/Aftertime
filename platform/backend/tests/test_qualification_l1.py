from copy import deepcopy

from sqlalchemy import select

from app.api.model_lab import pilot_qualification
from app.db import SessionLocal
from app.models import LabEdge, LabModelVersion, LabNode, LabQualificationDefinition, LabScenario, LabScenarioEventTemplate
from app.qualification_cases import (
    QUALIFICATION_CASES,
    canonicalize_qualification_package,
)
from app.services.qualification import (
    replay_qualification_package,
    validate_qualification_package,
)
from app.services.model_lab import replay_scenario


def reports():
    return {
        scenario_id: replay_qualification_package(package)
        for scenario_id, package in QUALIFICATION_CASES.items()
    }


def test_all_source_backed_l1_packages_complete_without_errors():
    assert set(QUALIFICATION_CASES) == {
        "san-bruno-2010",
        "northeast-2003",
        "storm-arwen-2021",
        "gb-2019",
        "south-australia-2016",
        "hokkaido-2018",
        "southwest-2011",
        "india-2012",
        "texas-2021",
        "iberia-2025",
        "north-hyde-2025",
        "kleen-energy",
        "macondo",
        "ua-md-2026",
        "ukraine-attacks",
    }
    for scenario_id, report in reports().items():
        assert report["passed"], (scenario_id, report["errors"])
        assert report["run_status"] == "completed"
        assert report["errors"] == []
        assert report["checkpoints"]
        assert all(checkpoint["passed"] for checkpoint in report["checkpoints"])
        assert all(item["status"] == "completed" for item in report["trace"])
        assert all(
            not item["action"] or item["action"]["postcondition_confirmed"]
            for item in report["trace"]
        )


def test_pilot_qualification_endpoint_exposes_all_strict_packages():
    with SessionLocal() as db:
        response = pilot_qualification(db)
    assert response["passed"] is True
    assert response["passed_count"] == response["required_count"] == 15
    assert {item["package_id"] for item in response["results"]} == {
        "san-bruno-2010-l1",
        "northeast-blackout-2003-l1",
        "storm-arwen-2021-l1",
        "gb-power-outage-2019-l1",
        "south-australia-black-system-2016-l1",
        "hokkaido-blackout-2018-l1",
        "southwest-blackout-2011-l1",
        "india-grid-disturbances-2012-l1",
        "texas-cold-weather-2021-l1",
        "iberian-blackout-2025-l1",
        "north-hyde-outage-2025-l1",
        "kleen-energy-explosion-2010-l1",
        "macondo-blowout-2010-l1",
        "ukraine-moldova-incident-2026-l1",
        "ukraine-energy-attacks-2022-2026-l1",
    }


def test_pilot_gate_reads_all_versioned_definitions_from_database():
    with SessionLocal() as db:
        definitions = list(db.scalars(select(LabQualificationDefinition)))
        pilot_definitions = [
            item
            for item in definitions
            if item.model_version_id
            == f"qualification-{item.scenario_id}"
            and item.scenario_id in QUALIFICATION_CASES
        ]
        assert len(pilot_definitions) == 15
        san_bruno = next(
            item for item in pilot_definitions if item.scenario_id == "san-bruno-2010"
        )
        changed = deepcopy(san_bruno.document)
        changed["name"] = "Database-backed San Bruno"
        san_bruno.document = changed
        db.flush()
        response = pilot_qualification(db)
        assert next(
            item for item in response["results"] if item["scenario_id"] == "san-bruno-2010"
        )["name"] == "Database-backed San Bruno"
        db.rollback()


def test_canonicalization_regenerates_bpmn_and_dmn_after_structured_edit():
    package = deepcopy(QUALIFICATION_CASES["san-bruno-2010"])
    package["dmn_xml"] = "stale"
    package["processes"][0]["bpmn_xml"] = "stale"
    package["processes"][0]["steps"][1]["after"] = ["recognize_break"]
    canonical = canonicalize_qualification_package(package)
    assert validate_qualification_package(canonical) == []
    assert 'sourceRef="recognize_break" targetRef="notify_responders"' in canonical["processes"][0]["bpmn_xml"]
    assert 'object_states.line_132 = &quot;ruptured_releasing&quot;' in canonical["dmn_xml"]


def test_packages_have_valid_bpmn_dmn_and_typed_input_provenance():
    for package in QUALIFICATION_CASES.values():
        assert validate_qualification_package(package) == []
        assert package["level"] == 1
        assert package["boundary"] == "stabilization"
        assert package["run_policy"] == "pause"
        assert all(process["format"] == "BPMN 2.0 XML" for process in package["processes"])
        for item in package["timeline"]:
            if item["entry_kind"] == "input":
                assert item["origin"] in {
                    "external_event",
                    "planned_process_start",
                    "observed_internal_fact",
                }
            else:
                assert "origin" not in item
            if item["evidence"] == "reported":
                assert item["source"] in {source["id"] for source in package["sources"]}


def test_replay_is_deterministic_for_same_package_and_seed():
    for package in QUALIFICATION_CASES.values():
        first = replay_qualification_package(package)
        second = replay_qualification_package(deepcopy(package))
        assert first["checksum"] == second["checksum"]
        assert first["trace"] == second["trace"]


def test_san_bruno_reaches_source_isolation_and_command_transfer():
    report = reports()["san-bruno-2010"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["rupture"]["metrics"]["rupture_pressure_psig"] == 386
    assert by_id["rupture"]["metrics"]["released_gas_scf"] == 47600000
    assert by_id["rupture"]["metrics"]["homes_destroyed"] == 38
    assert by_id["rupture"]["metrics"]["homes_damaged"] == 70
    assert by_id["rupture"]["metrics"]["fatalities"] == 8
    assert report["object_states"]["line_132"] == "stabilized_out_of_service"
    assert report["object_states"]["distribution_lines"] == "isolated"
    assert report["object_states"]["incident_command"] == "transferred"
    assert {item["id"] for item in report["checkpoints"]} == {
        "rupture_1811",
        "isolation_1946",
        "distribution_isolation",
        "containment_75",
        "command_transfer",
    }


def test_san_bruno_uses_its_own_gas_transmission_release_and_response_model():
    package = QUALIFICATION_CASES["san-bruno-2010"]
    assert package["schema_version"] == 2
    assert package["model"]["id"] == "qualification-san-bruno-2010"
    assert {node["component_type_id"] for node in package["model"]["nodes"]} >= {
        "gas-supply", "gas-control-terminal", "pipeline-valve", "pipeline",
        "pipeline-defect", "gas-distribution-network", "gas-release-zone",
        "external-hazard", "response-process",
    }
    assert all(
        edge["flow_type"] == "gas" and edge["domain"] == "natural_gas"
        for edge in package["model"]["edges"][:9]
    )

    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == package["model"]["id"])))
        edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == package["model"]["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in package["model"]["nodes"]}
        assert {edge.id for edge in edges} == {edge["id"] for edge in package["model"]["edges"]}
        by_id = {node.id: node for node in nodes}
        assert by_id["sb-defective-seam"].parameters["installation_year"] == 1956
        assert by_id["sb-defective-seam"].parameters["defect_visible_at_installation"] is True
        assert by_id["sb-line132-rupture"].parameters["rupture_pressure_psig"] == 386
        assert by_id["sb-line132-rupture"].parameters["released_gas_scf"] == 47600000
        assert by_id["sb-fire-area"].parameters["homes_destroyed"] == 38
        assert by_id["sb-fire-area"].parameters["fatalities"] == 8


def test_san_bruno_model_runtime_executes_rupture_and_fire_on_its_own_assets():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "san-bruno-2010")
        report = replay_scenario(db, scenario, scenario.model_version_id)
        assert report["passed"] is True
        assert report["observed"]["processed_event_types"] == ["fire", "pipeline_rupture"]
        assert report["observed"]["failed_assets"] == 2
        assert [item["target_node_id"] for item in report["trace"]] == [
            "sb-line132-rupture", "sb-fire-area",
        ]


def test_northeast_derives_cascade_after_three_distinct_contacts():
    report = reports()["northeast-2003"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["eastlake_trip"]["object_states"]["regional_grid"] == "secure"
    assert by_id["alarm_failure"]["situations"] == ["awareness_loss"]
    assert all(
        by_id["star_contact"]["object_states"][corridor] == "tripped"
        for corridor in ("harding_chamberlin", "hanna_juniper", "star_south_canton")
    )
    assert by_id["cascade_started"]["entry_kind"] == "derived"
    assert report["object_states"]["regional_grid"] == "stable_restoration"
    assert report["metrics"]["surviving_western_ny_island_mw"] == 5700
    assert by_id["regional_load_interrupted"]["metrics"]["affected_load_mw"] == 61800
    assert by_id["regional_load_interrupted"]["metrics"]["affected_people"] == 50000000
    assert report["object_states"]["affected_load"] == "outage_61800mw"


def test_northeast_2003_uses_its_own_monitoring_corridor_and_islanding_model():
    package = QUALIFICATION_CASES["northeast-2003"]
    assert package["schema_version"] == 2
    assert package["model"]["id"] == "qualification-northeast-2003"
    assert {node["component_type_id"] for node in package["model"]["nodes"]} >= {
        "thermal-plant", "transmission-corridor", "protection-system",
        "external-grid", "grid-zone", "customer-group", "response-process",
    }

    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == package["model"]["id"])))
        edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == package["model"]["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in package["model"]["nodes"]}
        assert {edge.id for edge in edges} == {edge["id"] for edge in package["model"]["edges"]}
        by_id = {node.id: node for node in nodes}
        assert by_id["ne-harding-chamberlin"].parameters["cause"] == "tree_contact"
        assert by_id["ne-hanna-juniper"].parameters["trip_time"] == "15:32:03"
        assert by_id["ne-sammis-star"].parameters["protection"] == "zone_3"
        assert by_id["ne-western-ny-island"].parameters["surviving_island_mw"] == 5700
        assert by_id["ne-affected-load"].parameters["demand_mw"] == 61800
        assert by_id["ne-affected-load"].parameters["affected_people"] == 50000000


def test_northeast_model_runtime_targets_awareness_generation_and_tree_contact_assets():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "northeast-2003")
        report = replay_scenario(db, scenario, scenario.model_version_id)
        assert report["passed"] is True
        assert report["observed"]["processed_event_types"] == [
            "scada_loss", "trip", "vegetation_contact",
        ]
        assert [item["target_node_id"] for item in report["trace"]] == [
            "ne-harding-chamberlin", "ne-fe-alarms", "ne-eastlake-5",
        ]


def test_arwen_runs_shortage_mobile_generation_and_nested_fault_branches():
    report = reports()["storm-arwen-2021"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["plant_stays_energized"]["object_states"]["generating_plant"] == "energized"
    assert by_id["plant_stays_energized"]["object_states"]["customers"] == "outage"
    assert report["resources"]["line_crews"]["available"] == 6
    assert report["resources"]["line_crews"]["reserved"] == 0
    assert report["resources"]["line_kits"]["consumed"] == 8
    assert "crew_shortage" in report["situations"]
    assert "prolonged_outage" in report["situations"]
    assert report["object_states"]["customers"] == "restored"
    assert report["metrics"]["restored_within_24h_percent_e3c_scope"] == 83
    assert report["metrics"]["restored_by_29_nov_percent_ofgem_scope"] == 84.1
    assert report["metrics"]["restored_percent_final_report_scope"] == 100


def test_arwen_uses_its_own_tiered_distribution_resource_and_mobile_supply_model():
    package = QUALIFICATION_CASES["storm-arwen-2021"]
    assert package["schema_version"] == 2
    assert package["model"]["id"] == "qualification-storm-arwen-2021"
    assert {node["component_type_id"] for node in package["model"]["nodes"]} >= {
        "external-hazard", "generation-aggregate", "transformer-group",
        "transmission-corridor", "distribution", "customer-group",
        "response-process", "distributed-generation",
    }

    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == package["model"]["id"])))
        edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == package["model"]["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in package["model"]["nodes"]}
        assert {edge.id for edge in edges} == {edge["id"] for edge in package["model"]["edges"]}
        by_id = {node.id: node for node in nodes}
        assert by_id["ar-distribution-segment"].parameters["nested_faults"] is True
        assert by_id["ar-customers"].parameters["affected_customers_min"] == 1000000
        assert by_id["ar-customers"].parameters["without_supply_over_3_days_approx"] == 40000
        assert by_id["ar-customers"].parameters["without_supply_over_week_approx"] == 4000
        assert by_id["ar-customers"].parameters["maximum_outage_days"] == 13
        assert by_id["ar-mobile-generation"].parameters["national_units_3_dec"] == 664
        assert by_id["ar-mobile-generation"].initial_state["online"] is False
        assert by_id["ar-line-crews"].parameters["evidence_kind"] == "model_assumption"


def test_arwen_model_runtime_fails_hv_and_distribution_assets_separately():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "storm-arwen-2021")
        report = replay_scenario(db, scenario, scenario.model_version_id)
        assert report["passed"] is True
        assert report["observed"]["processed_event_types"] == ["distribution_fault", "line_fault"]
        assert report["observed"]["failed_assets"] == 2
        assert [item["target_node_id"] for item in report["trace"]] == [
            "ar-hv-segment", "ar-distribution-segment",
        ]


def test_gb_2019_replays_generation_loss_lfdd_and_full_restoration():
    report = reports()["gb-2019"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["fault_cleared"]["metrics"]["fault_clearance_ms"] == 74
    assert by_id["rocof_generation_trip"]["metrics"]["cumulative_infeed_loss_mw"] == 1481
    assert by_id["lfdd_triggered"]["object_states"]["system_frequency"] == "lfdd_48_8"
    assert by_id["demand_931mw_disconnected"]["metrics"]["disconnected_demand_mw"] == 931
    assert report["metrics"]["cumulative_infeed_loss_mw"] == 1878
    assert report["object_states"]["system_frequency"] == "restored_50"
    assert report["object_states"]["customer_demand"] == "restored"
    assert report["metrics"]["restoration_complete_percent"] == 100


def test_gb_2019_uses_wind_gas_steam_distributed_generation_and_lfdd_assets():
    package = QUALIFICATION_CASES["gb-2019"]
    expected_nodes = {item["id"] for item in package["model"]["nodes"]}
    expected_edges = {item["id"] for item in package["model"]["edges"]}
    assert package["schema_version"] == 2
    assert {item["component_type_id"] for item in package["model"]["nodes"]} >= {
        "wind-plant",
        "thermal-plant",
        "distributed-generation",
        "transmission-corridor",
        "protection-system",
        "customer-group",
    }
    with SessionLocal() as db:
        model = db.get(LabModelVersion, "qualification-gb-2019")
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == model.id)))
        edges = set(db.scalars(select(LabEdge.id).where(LabEdge.model_version_id == model.id)))
        assert model.settings["event_model_id"] == package["model"]["id"]
        assert {item.id for item in nodes} == expected_nodes
        assert edges == expected_edges
        by_id = {item.id: item for item in nodes}
        assert by_id["gb-hornsea-one"].component_type_id == "wind-plant"
        assert by_id["gb-little-barford-gt1a"].parameters["fuel_kind"] == "natural_gas"
        assert by_id["gb-little-barford-st1c"].parameters["fuel_kind"] == "waste_heat_recovery"
        assert by_id["gb-customer-demand"].parameters["mode"] == "load"
        assert by_id["gb-customer-demand"].parameters["demand_mw"] == 2080
        assert by_id["gb-customer-demand"].parameters["evidence_kind"] == "derived"
        assert by_id["gb-customer-demand"].parameters["shed_scope_mw"] == 931


def test_south_australia_2016_replays_cascade_black_system_and_recovery():
    report = reports()["south-australia-2016"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["davenport_mt_lock_trip"]["metrics"]["voltage_disturbance_count"] == 6
    assert by_id["davenport_mt_lock_trip"]["metrics"]["fault_window_seconds"] == 87
    assert by_id["wind_generation_reduced"]["metrics"]["sustained_wind_reduction_mw"] == 456
    assert by_id["heywood_trip"]["metrics"]["heywood_trip_delay_ms"] == 700
    assert by_id["sa_black_system"]["object_states"]["sa_power_system"] == "black_system"
    assert report["object_states"]["customer_supply"] == "restored_all"
    assert report["object_states"]["sa_power_system"] == "stable_supply"
    assert report["object_states"]["sa_market"] == "resumed"
    assert report["metrics"]["restoration_percent"] == 100


def test_south_australia_2016_uses_its_own_wind_gas_and_interconnector_model():
    package = QUALIFICATION_CASES["south-australia-2016"]
    assert package["schema_version"] == 2
    assert package["model"]["id"] == "qualification-south-australia-2016"
    assert {node["component_type_id"] for node in package["model"]["nodes"]} >= {
        "wind-plant",
        "thermal-plant",
        "external-grid",
        "transmission-corridor",
        "customer-group",
        "protection-system",
    }

    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == package["model"]["id"])))
        edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == package["model"]["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in package["model"]["nodes"]}
        assert {edge.id for edge in edges} == {edge["id"] for edge in package["model"]["edges"]}
        by_id = {node.id: node for node in nodes}
        assert by_id["sa-wind-fleet"].parameters["capacity_mw"] == 883
        assert by_id["sa-gas-generation"].parameters["capacity_mw"] == 330
        assert by_id["sa-gas-generation"].parameters["fuel_kind"] == "natural_gas"
        assert by_id["sa-heywood"].parameters["reported_import_mw"] == 613
        assert by_id["sa-customer-supply"].parameters["demand_mw"] == 1826


def test_hokkaido_2018_replays_frequency_cascade_and_second_black_start():
    report = reports()["hokkaido-2018"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["wind_generation_trip"]["metrics"]["initial_output_curtailed_mw"] == 1760
    assert by_id["initial_frequency_recovered"]["object_states"]["system_frequency"] == "initially_recovered"
    assert by_id["third_ufr_load_shedding"]["metrics"]["third_load_shedding_mw"] == 60
    assert by_id["hokkaido_blackout"]["metrics"]["affected_households"] == 2950000
    assert by_id["first_black_start_failed"]["object_states"]["black_start_sequence"] == "first_attempt_failed"
    assert by_id["niikappu_2_parallel"]["object_states"]["black_start_sequence"] == "niikappu_2_online"
    assert report["metrics"]["restoration_elapsed_hours"] == 44.8
    assert report["object_states"]["system_frequency"] == "restored_nominal"
    assert report["object_states"]["customer_load"] == "nearly_all_restored"
    assert report["object_states"]["black_start_sequence"] == "complete"


def test_hokkaido_uses_thermal_hydro_wind_hvdc_and_black_start_assets():
    package = QUALIFICATION_CASES["hokkaido-2018"]
    expected_nodes = {item["id"] for item in package["model"]["nodes"]}
    expected_edges = {item["id"] for item in package["model"]["edges"]}
    assert package["schema_version"] == 2
    assert {item["component_type_id"] for item in package["model"]["nodes"]} >= {
        "thermal-plant",
        "hydro-plant",
        "wind-plant",
        "hvdc-interconnector",
        "grid-zone",
        "customer-group",
    }
    with SessionLocal() as db:
        model = db.get(LabModelVersion, "qualification-hokkaido-2018")
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == model.id)))
        edges = set(db.scalars(select(LabEdge.id).where(LabEdge.model_version_id == model.id)))
        assert model.settings["event_model_id"] == package["model"]["id"]
        assert {item.id for item in nodes} == expected_nodes
        assert edges == expected_edges
        by_id = {item.id: item for item in nodes}
        assert by_id["hk-customers"].parameters["demand_mw"] == 3087
        assert by_id["hk-honshu-hvdc"].parameters["rated_capacity_mw"] == 600
        assert by_id["hk-takami-1"].initial_state["online"] is False
        assert by_id["hk-niikappu-1"].initial_state["online"] is False
        assert by_id["hk-niikappu-2"].initial_state["online"] is False


def test_southwest_2011_replays_seven_phase_cascade_and_load_restoration():
    report = reports()["southwest-2011"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["hng_fault_trip"]["metrics"]["fault_clearance_ms"] == 43
    assert by_id["cv_trip"]["metrics"]["path44_current_a"] == 6700
    assert by_id["iid_north_collapse"]["metrics"]["iid_north_load_shed_mw"] == 444
    assert by_id["path44_threshold_exceeded"]["metrics"]["path44_current_peak_a"] == 9500
    assert by_id["customer_interruption"]["metrics"]["affected_customers"] == 2700000
    assert report["metrics"]["sdge_restoration_hours"] == 12
    assert report["object_states"]["customer_supply"] == "all_load_restored"
    assert report["object_states"]["regional_system"] == "stable_restoration"
    assert report["object_states"]["restoration"] == "complete"


def test_southwest_uses_its_own_model_and_every_process_object_is_bound():
    package = QUALIFICATION_CASES["southwest-2011"]
    model = package["model"]
    assert package["schema_version"] == 2
    assert model["id"] == "qualification-southwest-2011"
    assert model["level"] == 1
    assert {item["model_node_id"] for item in package["objects"]} <= {
        item["id"] for item in model["nodes"]
    }
    assert {item["qualification_object_id"] for item in model["nodes"] if item.get("qualification_object_id")} == {
        item["id"] for item in package["objects"]
    }
    assert {item["component_type_id"] for item in model["nodes"]} >= {
        "external-grid",
        "nuclear-plant",
        "transmission-corridor",
        "transformer-group",
        "grid-zone",
        "customer-group",
        "protection-system",
        "response-process",
    }


def test_southwest_database_graph_contains_no_universal_reference_chain():
    package = QUALIFICATION_CASES["southwest-2011"]
    expected_nodes = {item["id"] for item in package["model"]["nodes"]}
    expected_edges = {item["id"] for item in package["model"]["edges"]}
    with SessionLocal() as db:
        model = db.get(LabModelVersion, "qualification-southwest-2011")
        nodes = set(db.scalars(select(LabNode.id).where(LabNode.model_version_id == model.id)))
        edges = set(db.scalars(select(LabEdge.id).where(LabEdge.model_version_id == model.id)))
        assert model.settings["event_model_id"] == package["model"]["id"]
        assert model.settings["dedicated_topology"] is True
        assert nodes == expected_nodes
        assert edges == expected_edges
        assert "q7-gas-stock" not in nodes


def test_southwest_nuclear_generation_does_not_consume_natural_gas_or_emit_direct_co2():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "southwest-2011")
        report = replay_scenario(db, scenario, scenario.model_version_id)
        metrics = report["trace"][0]["metrics"]
        assert metrics["generation_mw"] == 1000
        assert metrics["gas_consumption_mw"] == 0
        assert metrics["co2_tph"] == 0
        assert metrics["node_metrics"]["sw-songs-nuclear"]["electric_power_mw"] == 1000


def test_event_model_binding_rejects_a_foreign_node():
    package = deepcopy(QUALIFICATION_CASES["southwest-2011"])
    package["objects"][0]["model_node_id"] = "node-from-another-event"
    errors = validate_qualification_package(package)
    assert any("binds an unknown model node" in error for error in errors)


def test_india_2012_replays_both_grid_collapses_and_recoveries():
    report = reports()["india-2012"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["day1_frequency_below_47_5"]["metrics"]["day1_frequency_fall_seconds"] == 6.5
    assert by_id["day1_15000mw_restored"]["metrics"]["day1_restored_load_mw"] == 15000
    assert by_id["day2_regions_separated"]["metrics"]["lost_western_infeed_mw"] == 3912
    assert by_id["day2_frequency_plateau"]["metrics"]["day2_frequency_plateau_hz"] == 48.12
    assert by_id["day2_48000mw_interrupted"]["metrics"]["day2_affected_load_mw"] == 48000
    assert report["object_states"]["customer_load"] == "fully_restored"
    assert report["object_states"]["new_grid"] == "restored_final"
    assert report["object_states"]["ufr_protection"] == "review_required"
    assert report["object_states"]["restoration"] == "day2_complete"


def test_india_2012_uses_its_own_interregional_generation_and_load_model():
    package = QUALIFICATION_CASES["india-2012"]
    assert package["schema_version"] == 2
    assert package["model"]["id"] == "qualification-india-2012"
    assert {node["component_type_id"] for node in package["model"]["nodes"]} >= {
        "external-grid",
        "transmission-corridor",
        "thermal-plant",
        "hydro-plant",
        "grid-zone",
        "customer-group",
        "protection-system",
    }

    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == package["model"]["id"])))
        edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == package["model"]["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in package["model"]["nodes"]}
        assert {edge.id for edge in edges} == {edge["id"] for edge in package["model"]["edges"]}
        by_id = {node.id: node for node in nodes}
        assert by_id["in-west-north-corridor"].parameters["day1_bina_gwalior_flow_mva"] == 1450
        assert by_id["in-west-north-corridor"].parameters["day2_bina_gwalior_flow_mw"] == 923
        assert by_id["in-customer-load"].parameters["demand_mw"] == 73000
        assert by_id["in-customer-load"].parameters["day2_affected_load_mw"] == 48000
        assert by_id["in-northern-hydro"].component_type_id == "hydro-plant"


def test_texas_2021_replays_frequency_emergency_and_prolonged_recovery():
    report = reports()["texas-2021"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["first_1000mw_shed"]["metrics"]["ordered_firm_load_shed_mw"] == 1000
    assert by_id["frequency_nadir"]["metrics"]["frequency_nadir_hz"] == 59.304
    assert by_id["frequency_nadir"]["metrics"]["generation_at_risk_mw"] == 17000
    assert by_id["prc_recovered_3017"]["metrics"]["physical_responsive_capability_mw"] == 3017
    assert by_id["peak_20000mw_shed"]["metrics"]["peak_firm_load_shed_mw"] == 20000
    assert by_id["average_34000mw_unavailable"]["metrics"]["average_generation_unavailable_mw"] == 34000
    assert report["object_states"]["firm_load"] == "all_restored"
    assert report["object_states"]["ercot_alert"] == "normal_restored"
    assert report["object_states"]["ercot_grid"] == "stable_recovery"
    assert report["object_states"]["restoration"] == "complete"


def test_texas_2021_uses_its_own_fuel_generation_and_load_model():
    package = QUALIFICATION_CASES["texas-2021"]
    assert package["schema_version"] == 2
    assert package["model"]["id"] == "qualification-texas-2021"
    assert {node["component_type_id"] for node in package["model"]["nodes"]} >= {
        "well", "pipeline", "thermal-plant", "nuclear-plant", "wind-plant",
        "solar-plant", "hvdc-interconnector", "customer-group", "protection-system",
    }

    gas_edges = [edge for edge in package["model"]["edges"] if edge.get("flow_type") == "gas"]
    assert len(gas_edges) == 2
    assert gas_edges[-1]["target_port"] == "fuel"

    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == package["model"]["id"])))
        edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == package["model"]["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in package["model"]["nodes"]}
        assert {edge.id for edge in edges} == {edge["id"] for edge in package["model"]["edges"]}
        by_id = {node.id: node for node in nodes}
        edge_by_id = {edge.id: edge for edge in edges}
        assert by_id["tx-gas-generation"].parameters["fuel_kind"] == "natural_gas"
        assert by_id["tx-coal-generation"].parameters["fuel_kind"] == "coal"
        assert by_id["tx-firm-load"].parameters["demand_mw"] == 61590
        assert by_id["tx-firm-load"].parameters["peak_ordered_shed_mw"] == 20000
        assert edge_by_id["tx-edge-production-pipeline"].flow_type == "gas"
        assert edge_by_id["tx-edge-pipeline-gas-generation"].target_port == "fuel"


def test_iberia_2025_replays_oscillations_cascade_and_cross_border_restoration():
    report = reports()["iberia-2025"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["local_oscillation_started"]["metrics"]["oscillation_frequency_hz"] == 0.63
    assert by_id["interarea_oscillation_started"]["metrics"]["oscillation_frequency_hz"] == 0.2
    assert by_id["granada_transformer_trip"]["metrics"]["pretrip_reactive_absorption_mvar"] == 165
    assert by_id["badajoz_generation_trip"]["metrics"]["badajoz_generation_loss_mw"] == 727
    assert by_id["further_generation_trip"]["metrics"]["further_generation_loss_mw"] == 928
    assert by_id["france_spain_hvdc_trip"]["at"] == "2025-04-28T12:33:23.960+02:00"
    assert report["metrics"]["portugal_restoration_hours"] == 12
    assert report["metrics"]["spain_restoration_hours"] == 16
    assert report["object_states"]["portugal_grid"] == "restored"
    assert report["object_states"]["spain_grid"] == "restored"
    assert report["object_states"]["iberian_system"] == "stable_restoration"
    assert report["object_states"]["restoration"] == "complete"


def test_iberia_2025_uses_its_own_renewable_interconnection_and_restoration_model():
    package = QUALIFICATION_CASES["iberia-2025"]
    assert package["schema_version"] == 2
    assert package["model"]["id"] == "qualification-iberia-2025"
    assert {node["component_type_id"] for node in package["model"]["nodes"]} >= {
        "wind-plant", "solar-plant", "distributed-generation", "transformer-group",
        "transmission-corridor", "hvdc-interconnector", "hydro-plant",
        "customer-group", "protection-system",
    }

    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == package["model"]["id"])))
        edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == package["model"]["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in package["model"]["nodes"]}
        assert {edge.id for edge in edges} == {edge["id"] for edge in package["model"]["edges"]}
        by_id = {node.id: node for node in nodes}
        assert by_id["ib-badajoz-generation"].parameters["reported_loss_mw"] == 727
        assert by_id["ib-further-generation"].parameters["reported_loss_mw"] == 928
        assert by_id["ib-granada-transformer"].parameters["pretrip_reactive_absorption_mvar"] == 165
        assert by_id["ib-france-spain-hvdc"].component_type_id == "hvdc-interconnector"
        assert by_id["ib-black-start-hydro"].component_type_id == "hydro-plant"
        assert by_id["ib-spain-load"].parameters["demand_mw"] == 25200
        assert by_id["ib-portugal-load"].parameters["demand_mw"] == 5900


def test_north_hyde_2025_replays_transformer_fire_customer_and_airport_recovery():
    report = reports()["north-hyde-2025"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["sgt3_protection_isolated"]["metrics"]["protection_isolation_ms"] == 110
    assert by_id["sgt1_protection_trip"]["metrics"]["fire_spread_trip_delay_minutes"] == 28
    assert by_id["customer_outage_71655"]["metrics"]["total_customers_interrupted"] == 71655
    assert by_id["customers_42000_restored"]["metrics"]["restoration_elapsed_minutes"] == 58
    assert by_id["distribution_capacity_reached"]["metrics"]["ssen_customers_remaining"] == 4868
    assert by_id["all_but_two_customers_restored"]["metrics"]["direct_customers_on_backup"] == 2
    assert report["object_states"]["airport_operation"] == "business_as_usual"
    assert report["object_states"]["north_hyde_supply"] == "reinforced_iver_support"
    assert report["object_states"]["fire_response"] == "firefighting_stopped"
    assert report["object_states"]["restoration"] == "complete"


def test_north_hyde_2025_uses_its_own_transformer_customer_and_restoration_model():
    package = QUALIFICATION_CASES["north-hyde-2025"]
    assert package["schema_version"] == 2
    assert package["model"]["id"] == "qualification-north-hyde-2025"
    assert {node["component_type_id"] for node in package["model"]["nodes"]} >= {
        "transformer-bushing", "transformer-group", "transmission-corridor",
        "customer-group", "distributed-generation", "response-process",
    }

    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == package["model"]["id"])))
        edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == package["model"]["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in package["model"]["nodes"]}
        assert {edge.id for edge in edges} == {edge["id"] for edge in package["model"]["edges"]}
        by_id = {node.id: node for node in nodes}
        edge_ids = {edge.id for edge in edges}
        assert by_id["nh-sgt3-bushing"].component_type_id == "transformer-bushing"
        assert by_id["nh-sgt3-bushing"].parameters["affected_customers"] == 71655
        assert by_id["nh-supply"].parameters["affected_customers"] == 71655
        assert by_id["nh-customer-supply"].parameters["ssen_direct_customers"] == 66919
        assert by_id["nh-customer-supply"].parameters["idno_customers"] == 4736
        assert by_id["nh-airfield-generators"].initial_state["online"] is False
        assert {"nh-edge-shared-sgt1", "nh-edge-shared-sgt2", "nh-edge-iver-supply"} <= edge_ids


def test_north_hyde_model_runtime_uses_reported_customer_impact_without_invented_mw():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "north-hyde-2025")
        report = replay_scenario(db, scenario, scenario.model_version_id)
        assert report["passed"] is True
        assert report["observed"]["max_affected_customers"] == 71655
        assert report["observed"]["restored_assets"] >= 1
        assert "demand_mw" not in next(
            node.parameters
            for node in db.scalars(select(LabNode).where(LabNode.model_version_id == scenario.model_version_id))
            if node.id == "nh-customer-supply"
        )


def test_kleen_energy_replays_gas_blows_explosion_and_safety_response():
    report = reports()["kleen-energy"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert by_id["gas_blow_program_started"]["metrics"]["gas_pressure_psig"] == 650
    assert by_id["fifteen_gas_blows_completed"]["metrics"]["gas_blow_count"] == 15
    assert by_id["fifteen_gas_blows_completed"]["metrics"]["morning_total_release_scf"] == 2000000
    assert by_id["final_ten_minute_release"]["metrics"]["final_release_scf"] == 480000
    assert by_id["cleaning_force_exceeded"]["metrics"]["cleaning_force_target"] == 2
    assert by_id["cleaning_force_exceeded"]["metrics"]["cleaning_force_vent_min"] == 50
    assert by_id["workforce_exposed"]["metrics"]["workers_onsite"] == 150
    assert by_id["casualties_recorded"]["metrics"]["fatalities"] == 6
    assert by_id["casualties_recorded"]["metrics"]["injuries_min"] == 50
    assert by_id["urgent_recommendations_approved"]["metrics"]["urgent_recommendation_count"] == 18
    assert report["object_states"]["gas_blow_operation"] == "terminated_after_explosion"
    assert report["object_states"]["safety_controls"] == "urgent_recommendations_issued"
    assert report["object_states"]["csb_investigation"] == "complete"


def test_kleen_energy_uses_its_own_gas_blow_exposure_and_investigation_model():
    package = QUALIFICATION_CASES["kleen-energy"]
    model = package["model"]
    assert package["schema_version"] == 2
    assert model["id"] == "qualification-kleen-energy"
    assert {node["component_type_id"] for node in model["nodes"]} >= {
        "gas-supply", "pipeline-valve", "gas-control-terminal", "gas-release-zone",
        "industrial-facility", "workforce-group", "protection-system", "response-process",
    }
    assert {item["model_node_id"] for item in package["objects"]} <= {
        item["id"] for item in model["nodes"]
    }
    assert {item["qualification_object_id"] for item in model["nodes"] if item.get("qualification_object_id")} == {
        item["id"] for item in package["objects"]
    }

    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == model["id"])))
        edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == model["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in model["nodes"]}
        assert {edge.id for edge in edges} == {edge["id"] for edge in model["edges"]}
        by_id = {node.id: node for node in nodes}
        assert by_id["ke-gas-supply"].parameters["gas_pressure_psig"] == 650
        assert by_id["ke-gas-blow-operation"].parameters["gas_blow_count"] == 15
        assert by_id["ke-gas-blow-operation"].parameters["morning_total_release_scf"] == 2000000
        assert by_id["ke-gas-blow-operation"].parameters["final_release_scf"] == 480000
        assert by_id["ke-vent"].parameters["vent_height_ft_max"] == 20
        assert by_id["ke-generation-building"].parameters["operating_generation"] is False
        assert by_id["ke-workforce"].parameters["workers_onsite"] == 150
        assert by_id["ke-workforce"].parameters["fatalities"] == 6
        assert by_id["ke-workforce"].parameters["injuries_min"] == 50


def test_kleen_energy_runtime_targets_cloud_and_construction_building_separately():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "kleen-energy")
        report = replay_scenario(db, scenario, scenario.model_version_id)
        assert report["passed"] is True
        assert report["observed"]["processed_event_types"] == ["external_damage", "gas_accumulation"]
        assert report["observed"]["failed_assets"] == 2
        assert [item["target_node_id"] for item in report["trace"]] == [
            "ke-gas-cloud", "ke-generation-building",
        ]


def test_macondo_replays_barrier_loss_blowout_casualties_and_87_day_response():
    report = reports()["macondo"]
    by_id = {item["id"]: item for item in report["trace"]}
    assert report["passed"] is True
    assert by_id["crew_evacuated"]["metrics"]["crew_onboard"] == 126
    assert by_id["crew_evacuated"]["metrics"]["fatalities"] == 11
    assert by_id["crew_evacuated"]["metrics"]["serious_injuries"] == 17
    assert by_id["well_capped_after_87_days"]["metrics"]["uncontrolled_flow_days"] == 87
    assert report["object_states"]["bop"] == "blind_shear_ram_failed"
    assert report["object_states"]["rig"] == "sunk"
    assert report["object_states"]["well_flow"] == "capped"


def test_macondo_uses_its_own_offshore_well_bop_rig_and_spill_model():
    package = QUALIFICATION_CASES["macondo"]
    model = package["model"]
    assert package["schema_version"] == 2
    assert model["id"] == "qualification-macondo"
    assert {node["component_type_id"] for node in model["nodes"]} >= {
        "offshore-reservoir", "offshore-wellbore", "well-barrier",
        "blowout-preventer", "mud-gas-separator", "offshore-drilling-rig",
        "marine-spill-zone", "workforce-group", "response-process",
    }
    assert {item["model_node_id"] for item in package["objects"]} <= {
        item["id"] for item in model["nodes"]
    }
    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == model["id"])))
        edges = list(db.scalars(select(LabEdge).where(LabEdge.model_version_id == model["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in model["nodes"]}
        assert {edge.id for edge in edges} == {edge["id"] for edge in model["edges"]}
        by_id = {node.id: node for node in nodes}
        assert by_id["mc-reservoir"].parameters["reservoir_pressure_psi_approx"] == 11850
        assert by_id["mc-bop"].parameters["failure_mechanism"] == "effective_compression_drillpipe_buckling"
        assert by_id["mc-deepwater-horizon"].parameters["crew_onboard"] == 126
        assert by_id["mc-spill-zone"].parameters["uncontrolled_flow_days"] == 87


def test_macondo_runtime_targets_barrier_well_and_rig_separately():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "macondo")
        report = replay_scenario(db, scenario, scenario.model_version_id)
        assert report["passed"] is True
        assert report["observed"]["processed_event_types"] == [
            "barrier_failure", "fire", "uncontrolled_flow",
        ]
        assert [item["target_node_id"] for item in report["trace"]] == [
            "mc-cement-barrier", "mc-wellbore", "mc-deepwater-horizon",
        ]


def test_ua_md_2026_replays_two_line_trips_separation_and_resynchronisation():
    report = reports()["ua-md-2026"]
    assert report["passed"] is True
    assert report["metrics"]["separation_duration_minutes_approx"] == 20
    assert report["object_states"]["romania_moldova_line"] == "tripped"
    assert report["object_states"]["ukraine_750kv_line"] == "tripped"
    assert report["object_states"]["synchronous_area"] == "resynchronised"
    assert report["object_states"]["consumer_supply"] == "restored"


def test_ua_md_2026_uses_its_own_two_line_generation_and_restoration_model():
    package = QUALIFICATION_CASES["ua-md-2026"]
    model = package["model"]
    assert model["id"] == "qualification-ua-md-2026"
    assert {node["component_type_id"] for node in model["nodes"]} >= {
        "external-grid", "transmission-corridor", "grid-zone", "generation-aggregate",
        "protection-system", "customer-group", "response-process",
    }
    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == model["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in model["nodes"]}
        by_id = {node.id: node for node in nodes}
        assert by_id["um-400kv-interconnector"].parameters["voltage_kv"] == 400
        assert by_id["um-750kv-corridor"].parameters["voltage_kv"] == 750
        assert by_id["um-weather"].parameters["evidence_status"] == "preliminary_not_final"


def test_ua_md_runtime_targets_both_lines_generation_and_ce_interface():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "ua-md-2026")
        report = replay_scenario(db, scenario, scenario.model_version_id)
        assert report["passed"] is True
        assert report["observed"]["processed_event_types"] == [
            "corridor_trip", "interconnector_trip", "restore", "resynchronize",
        ]
        assert [item["target_node_id"] for item in report["trace"]] == [
            "um-400kv-interconnector", "um-750kv-corridor", "um-750kv-corridor", "um-ce-interface",
        ]


def test_ukraine_attacks_replays_multi_wave_energy_and_civilian_service_impacts():
    report = reports()["ukraine-attacks"]
    assert report["passed"] is True
    assert report["metrics"]["large_scale_waves_2024"] == 9
    assert report["metrics"]["generation_capacity_lost_gw_approx"] == 9
    assert report["metrics"]["available_generation_gw"] == 11
    assert report["metrics"]["peak_need_gw"] == 18
    assert report["metrics"]["electricity_facility_attacks_oct2025_mar2026_min"] == 423
    assert report["metrics"]["heating_infrastructure_strikes_min"] == 74
    assert report["object_states"]["restoration"] == "multi_year_repair"


def test_ukraine_attacks_uses_diverse_generation_grid_services_and_response_assets():
    package = QUALIFICATION_CASES["ukraine-attacks"]
    model = package["model"]
    assert model["id"] == "qualification-ukraine-attacks"
    assert {node["component_type_id"] for node in model["nodes"]} >= {
        "nuclear-plant", "thermal-plant", "hydro-plant", "transformer-group",
        "transmission-corridor", "distribution", "customer-group", "distributed-generation",
        "industrial-facility", "response-process",
    }
    with SessionLocal() as db:
        nodes = list(db.scalars(select(LabNode).where(LabNode.model_version_id == model["id"])))
        assert {node.id for node in nodes} == {node["id"] for node in model["nodes"]}
        by_id = {node.id: node for node in nodes}
        assert by_id["ua-generation-zone"].parameters["available_jan_2026_gw"] == 11
        assert by_id["ua-generation-zone"].parameters["peak_need_jan_2026_gw"] == 18
        assert by_id["ua-attack-campaign"].parameters["electricity_facility_attacks_oct2025_mar2026_min"] == 423
        assert by_id["ua-district-heating"].parameters["temperature_c_min"] == -20


def test_ukraine_attacks_runtime_targets_generation_substation_and_transmission_separately():
    with SessionLocal() as db:
        scenario = db.get(LabScenario, "ukraine-attacks")
        report = replay_scenario(db, scenario, scenario.model_version_id)
        assert report["passed"] is True
        assert report["observed"]["processed_event_types"] == [
            "generation_attack", "substation_attack", "transmission_attack",
        ]
        assert [item["target_node_id"] for item in report["trace"]] == [
            "ua-generation-zone", "ua-main-substations", "ua-transmission-network",
        ]
        templates = list(db.scalars(
            select(LabScenarioEventTemplate)
            .where(LabScenarioEventTemplate.scenario_id == "ukraine-attacks")
            .order_by(LabScenarioEventTemplate.offset_seconds)
        ))
        assert [item.title for item in templates] == [
            "Атака на об’єкти генерації",
            "Атака на магістральні підстанції",
            "Атака на мережу передачі",
        ]


def test_every_source_backed_l1_package_has_a_dedicated_bound_model():
    model_ids = [package["model"]["id"] for package in QUALIFICATION_CASES.values()]
    assert len(model_ids) == len(set(model_ids)) == len(QUALIFICATION_CASES)
    for package in QUALIFICATION_CASES.values():
        assert package["schema_version"] == 2
        assert package["model"]["level"] == 1
        assert package["model"]["scope_note"]
        assert {item["model_node_id"] for item in package["objects"]} <= {
            item["id"] for item in package["model"]["nodes"]
        }


def test_invalid_transition_pauses_and_cannot_patch_state_directly():
    package = deepcopy(QUALIFICATION_CASES["san-bruno-2010"])
    package["timeline"][0]["action"] = {
        "target": "line_132",
        "capability": "rupture",
        "postcondition": {"state": "ruptured_releasing"},
    }
    report = replay_qualification_package(package)
    assert not report["passed"]
    assert report["run_status"] == "paused_failed"
    assert report["interrupted"] is True
    assert any("not permitted" in error for error in report["errors"])


def test_bpmn_step_and_executed_timeline_action_cannot_diverge():
    package = deepcopy(QUALIFICATION_CASES["san-bruno-2010"])
    process = package["processes"][0]
    targeted_steps = {step["id"] for step in process["steps"] if step.get("target")}
    item = next(
        entry
        for entry in package["timeline"]
        if entry.get("process", {}).get("id") == process["id"]
        and entry.get("process", {}).get("step") in targeted_steps
        and entry.get("action")
    )
    item["action"] = {
        "target": "public_response",
        "capability": "deploy",
        "postcondition": {"state": "deployed"},
    }
    errors = validate_qualification_package(package)
    assert any("diverges from its BPMN step" in error for error in errors)
