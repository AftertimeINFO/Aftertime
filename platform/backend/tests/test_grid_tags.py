"""OSM power tag parsing (no database)."""

from app.grid.osm_tags import (
    classify,
    keep_generator,
    lifecycle,
    parse_count,
    parse_power_mw,
    parse_voltages_kv,
)


def test_voltages_in_volts_and_kv_largest_first_without_duplicates():
    assert parse_voltages_kv("330000;110000;110000") == [330.0, 110.0]
    assert parse_voltages_kv("750 kV") == [750.0]
    assert parse_voltages_kv("400") == [0.4]
    assert parse_voltages_kv("yes;;abc") == []
    assert parse_voltages_kv(None) == []


def test_power_units_and_missing_unit():
    assert parse_power_mw("1000 MW") == (1000.0, False)
    assert parse_power_mw("1,5 GW") == (1500.0, False)
    assert parse_power_mw("800 kW") == (0.8, False)
    assert parse_power_mw("6000") == (6000.0, True)
    assert parse_power_mw("2500000") == (2.5, True)
    assert parse_power_mw("yes") == (None, False)


def test_counts():
    assert parse_count("2") == 2
    assert parse_count("x;3") == 3
    assert parse_count("0") is None


def test_lifecycle_prefixes():
    assert lifecycle({"power": "line"}) == ("line", "active")
    assert lifecycle({"power": "construction", "construction": "line"}) == ("line", "construction")
    assert lifecycle({"disused:power": "substation"}) == ("substation", "disused")
    assert lifecycle({"abandoned:power": "line"}) == ("line", "abandoned")


def test_retired_objects_are_disused():
    from datetime import date

    chornobyl = {"power": "plant", "status": "disused", "end_date": "2000-12-15", "plant:source": "nuclear"}
    assert lifecycle(chornobyl) == ("plant", "disused")
    reactor = {"power": "generator", "disused:power": "generator", "generator:source": "nuclear"}
    assert lifecycle(reactor) == ("generator", "disused")
    closed = {"power": "plant", "end_date": "2019-06"}
    assert lifecycle(closed, today=date(2026, 1, 1)) == ("plant", "disused")
    assert lifecycle({"power": "plant", "end_date": "2030"}, today=date(2026, 1, 1)) == ("plant", "active")
    assert lifecycle({"power": "line", "operational_status": "decommissioned"}) == ("line", "disused")


def test_classify_plant_and_line():
    plant = classify(
        {"power": "plant", "plant:source": "nuclear", "plant:output:electricity": "6000 MW",
         "name": "Запорізька АЕС"}
    )
    assert plant.kind == "plant" and plant.fuel == "nuclear" and plant.capacity_mw == 6000
    assert plant.capacity_source == "osm" and plant.quality == []
    line = classify({"power": "line", "voltage": "750000", "circuits": "1"})
    assert line.kind == "line" and line.max_voltage_kv == 750 and line.circuits == 1
    bare = classify({"power": "line"})
    assert "voltage_missing" in bare.quality
    hvdc = classify({"power": "cable", "voltage": "450000", "frequency": "0"})
    assert hvdc.subkind == "hvdc"
    assert classify({"power": "tower"}) is None
    assert classify({"building": "yes"}) is None


def test_small_rooftop_solar_is_skipped():
    rooftop = classify({"power": "generator", "generator:source": "solar"})
    farm = classify(
        {"power": "generator", "generator:source": "solar",
         "generator:output:electricity": "5 MW"}
    )
    turbine = classify({"power": "generator", "generator:source": "wind"})
    assert not keep_generator(rooftop)
    assert keep_generator(farm) and keep_generator(turbine)
