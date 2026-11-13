"""Pure parsers for OpenStreetMap power tags.

The rules follow the OSM wiki (Key:power, Key:voltage, Key:plant:output:electricity) and
the conventions of Open Infrastructure Map (lifecycle prefixes, unit parsing, multi-value
fields separated by ``;``). They return ``None`` instead of guessing; whatever is guessed
is recorded as a quality flag by the caller.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

LIFECYCLE_PREFIXES = {
    "construction": "construction",
    "proposed": "proposed",
    "planned": "proposed",
    "disused": "disused",
    "abandoned": "abandoned",
    "demolished": "demolished",
    "removed": "demolished",
    "razed": "demolished",
    "destroyed": "destroyed",
}

# power=* values we keep; towers, poles, portals, switches and the like are not assets
# of the network model and would only multiply the row count.
KINDS = {
    "line": "line",
    "minor_line": "minor_line",
    "cable": "cable",
    "substation": "substation",
    "sub_station": "substation",
    "plant": "plant",
    "generator": "generator",
    "converter": "converter",
}

FUELS = {
    "nuclear": "nuclear",
    "coal": "coal",
    "lignite": "coal",
    "gas": "gas",
    "oil": "oil",
    "diesel": "oil",
    "hydro": "hydro",
    "water": "hydro",
    "wind": "wind",
    "solar": "solar",
    "biomass": "biomass",
    "biofuel": "biomass",
    "biogas": "biomass",
    "waste": "waste",
    "geothermal": "geothermal",
    "battery": "storage",
    "pumped_storage": "storage",
    "peat": "coal",
    "tidal": "hydro",
}

_NUMBER = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*([a-zA-Z]*)\s*$")
_POWER_UNITS = {"w": 1e-6, "kw": 1e-3, "mw": 1.0, "gw": 1e3, "kwp": 1e-3, "mwp": 1.0, "gwp": 1e3}


def _values(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def parse_voltages_kv(value: str | None) -> list[float]:
    """``voltage`` in volts (``"330000;110000"``) or with a kV suffix, as kV, largest first.

    Duplicates (one value per circuit) collapse; unparseable parts are dropped.
    """
    result: set[float] = set()
    for part in _values(value):
        match = _NUMBER.match(part)
        if not match:
            continue
        number = float(match.group(1).replace(",", "."))
        unit = match.group(2).lower()
        if unit == "kv":
            kv = number
        elif unit in {"", "v"}:
            kv = number / 1000
        else:
            continue
        if kv > 0:
            result.add(round(kv, 3))
    return sorted(result, reverse=True)


def parse_power_mw(value: str | None) -> tuple[float | None, bool]:
    """``plant:output:electricity`` style value as MW, plus whether the unit was missing.

    Values such as ``yes`` give ``None``. A bare number is read as MW when below 50 000
    (the usual mistake is a missing ``MW``) and as watts otherwise.
    """
    total = 0.0
    found = False
    unit_missing = False
    for part in _values(value):
        match = _NUMBER.match(part)
        if not match:
            continue
        number = float(match.group(1).replace(",", "."))
        unit = match.group(2).lower()
        if unit in _POWER_UNITS:
            total += number * _POWER_UNITS[unit]
        elif unit == "":
            unit_missing = True
            total += number if number < 50_000 else number / 1e6
        else:
            continue
        found = True
    return (round(total, 4) if found and total > 0 else None), unit_missing


def parse_count(value: str | None) -> int | None:
    """``circuits`` / ``cables``: the first positive integer of a ``;`` list."""
    for part in _values(value):
        if part.isdigit() and int(part) > 0:
            return int(part)
    return None


def parse_frequency(value: str | None) -> float | None:
    for part in _values(value):
        try:
            return float(part.replace(",", "."))
        except ValueError:
            continue
    return None


STATUS_VALUES = {
    "disused": "disused", "abandoned": "abandoned", "construction": "construction",
    "proposed": "proposed", "planned": "proposed", "decommissioned": "disused",
    "demolished": "demolished", "destroyed": "destroyed", "dismantled": "demolished",
}


def lifecycle(tags: Mapping[str, str], today: date | None = None) -> tuple[str | None, str]:
    """``(power value, status)`` honouring lifecycle prefixes, ``power=construction``,
    ``status`` / ``operational_status`` and a past ``end_date``.

    An object tagged both ``power=*`` and ``disused:power=*`` (a common way to keep a
    decommissioned plant visible) is disused.
    """
    power = tags.get("power")
    if power == "construction" and tags.get("construction"):
        return tags["construction"], "construction"
    if power in {"proposed", "planned"} and tags.get(power):
        return tags[power], "proposed"
    if power:
        status = "active"
        for key in ("status", "operational_status", "plant:status"):
            if tags.get(key) in STATUS_VALUES:
                status = STATUS_VALUES[tags[key]]
                break
        if status == "active":
            if tags.get("disused") == "yes":
                status = "disused"
            for prefix, prefixed_status in LIFECYCLE_PREFIXES.items():
                if tags.get(f"{prefix}:power"):
                    status = prefixed_status
                    break
        end = _date_prefix(tags.get("end_date"))
        if status == "active" and end is not None and end <= (today or date.today()):
            status = "disused"
        return power, status
    for prefix, status in LIFECYCLE_PREFIXES.items():
        value = tags.get(f"{prefix}:power")
        if value:
            return value, status
    return None, "active"


def _date_prefix(value: str | None) -> date | None:
    """Leading ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD`` of an OSM date, as the first day."""
    if not value:
        return None
    match = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", value.strip())
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return date(int(year), int(month or 1), int(day or 1))
    except ValueError:
        return None


def fuel_of(tags: Mapping[str, str], kind: str) -> str | None:
    key = "plant:source" if kind == "plant" else "generator:source"
    for part in _values(tags.get(key)):
        fuel = FUELS.get(part.lower())
        if fuel:
            return fuel
    method = tags.get("generator:method") or tags.get("plant:method")
    if method == "fission":
        return "nuclear"
    return None


@dataclass
class PowerFeature:
    kind: str
    subkind: str | None
    status: str
    name: str | None
    name_en: str | None
    operator: str | None
    ref: str | None
    voltages_kv: list[float]
    frequency_hz: float | None
    circuits: int | None
    cables: int | None
    capacity_mw: float | None
    capacity_source: str | None
    fuel: str | None
    start_date: str | None
    quality: list[str] = field(default_factory=list)

    @property
    def max_voltage_kv(self) -> float | None:
        return self.voltages_kv[0] if self.voltages_kv else None


def classify(tags: Mapping[str, str]) -> PowerFeature | None:
    """Turn the tags of one OSM object into a power feature, or ``None`` if it is not one."""
    power, status = lifecycle(tags)
    kind = KINDS.get(power or "")
    if kind is None:
        return None
    quality: list[str] = []
    voltages = parse_voltages_kv(tags.get("voltage"))
    if kind in {"line", "cable", "substation", "converter"} and not voltages:
        quality.append("voltage_missing")
    capacity = None
    capacity_source = None
    fuel = None
    subkind = None
    if kind == "plant":
        capacity, unit_missing = parse_power_mw(tags.get("plant:output:electricity"))
        fuel = fuel_of(tags, kind)
        subkind = tags.get("plant:method")
    elif kind == "generator":
        capacity, unit_missing = parse_power_mw(tags.get("generator:output:electricity"))
        fuel = fuel_of(tags, kind)
        subkind = tags.get("generator:type") or tags.get("generator:method")
    else:
        unit_missing = False
        if kind == "substation":
            subkind = tags.get("substation")
        elif kind == "cable":
            subkind = tags.get("location") or ("submarine" if tags.get("submarine") else None)
        elif kind == "line":
            subkind = tags.get("line")
    if capacity is not None:
        capacity_source = "osm"
    if unit_missing:
        quality.append("power_unit_missing")
    if kind == "plant" and capacity is None:
        quality.append("capacity_missing")
    frequency = parse_frequency(tags.get("frequency"))
    if frequency == 0 and kind in {"line", "cable"}:
        subkind = "hvdc"
    return PowerFeature(
        kind=kind,
        subkind=subkind,
        status=status,
        name=tags.get("name"),
        name_en=tags.get("name:en"),
        operator=tags.get("operator"),
        ref=tags.get("ref"),
        voltages_kv=voltages,
        frequency_hz=frequency,
        circuits=parse_count(tags.get("circuits")),
        cables=parse_count(tags.get("cables")),
        capacity_mw=capacity,
        capacity_source=capacity_source,
        fuel=fuel,
        start_date=tags.get("start_date"),
        quality=quality,
    )


def keep_generator(feature: PowerFeature) -> bool:
    """Small rooftop solar and unknown generators add rows but not network capacity."""
    if feature.capacity_mw is not None:
        return feature.capacity_mw >= 0.5 or feature.fuel not in {None, "solar"}
    return feature.fuel not in {None, "solar"}
