"""Material balance and scopes over the Saudi Arabia to India pilot (DEV layer)."""

from datetime import UTC, datetime

import pytest

from app.db import SessionLocal
from app.services.world_balance import BalanceError, balance, balance_series
from app.services.world_scope import CONTROL_ROOT, scope_roots, scope_tree
from app.world_pilot import generate_pilot_events, seed_pilot_world
from app.world_core import seed_world_core

START = datetime(2023, 1, 1, tzinfo=UTC)
END = datetime(2024, 1, 1, tzinfo=UTC)
FLOWS = ("opening", "inflow", "outflow", "transform", "carrier", "closing")


@pytest.fixture(scope="module")
def db():
    with SessionLocal() as session:
        seed_world_core(session)
        seed_pilot_world(session)
        generate_pilot_events(session)
        try:
            yield session
        finally:
            session.rollback()


def leaves(result: dict) -> dict[str, dict]:
    return {row["id"]: row["values"] for row in result["rows"] if not row["group"]}


def close(a: float, b: float, scale: float = 1.0) -> bool:
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b), scale)


@pytest.mark.parametrize(
    "scope", ["place:earth", "place:saudi-arabia", "asset:jamnagar", "actor:reliance", CONTROL_ROOT]
)
def test_every_scope_balances(db, scope):
    result = balance(db, scope, START, END, "substance")
    assert not result["empty"]
    assert result["residual_ok"], result["totals"]
    for values in leaves(result).values():
        explained = (
            values["opening"]
            + values["inflow"]
            - values["outflow"]
            + values["transform"]
            + values["carrier"]
        )
        assert close(explained, values["closing"], values["opening"])


def test_earth_is_closed_and_refining_conserves_mass(db):
    totals = balance(db, "place:earth", START, END, "substance")["totals"]
    assert totals["inflow"] == pytest.approx(0, abs=1e-3)
    assert totals["outflow"] == pytest.approx(0, abs=1e-3)
    assert totals["carrier"] == pytest.approx(0, abs=1e-3)
    assert close(totals["transform"], 0.0, totals["opening"])


def test_refinery_takes_crude_in_and_turns_it_into_products(db):
    rows = leaves(balance(db, "asset:jamnagar", START, END, "substance"))
    assert rows["type:arab-light"]["inflow"] > 0
    assert rows["type:arab-light"]["transform"] < 0
    for product in ("type:gasoline", "type:diesel", "type:jet-fuel", "type:fuel-oil"):
        assert rows[product]["transform"] > 0
        assert rows[product]["closing"] > 0


def test_groups_are_subtotals_of_their_children(db):
    result = balance(db, "place:earth", START, END, "substance")
    by_id = {row["id"]: row for row in result["rows"]}
    for row in result["rows"]:
        if not row["group"]:
            continue
        kids = [r for r in result["rows"] if r["parent"] == row["id"]]
        for column in FLOWS:
            assert close(sum(k["values"][column] for k in kids), row["values"][column])
    assert by_id["type:substance"]["group"]


def test_company_scope_equals_its_assets(db):
    company = balance(db, "actor:reliance", START, END, "substance")["totals"]
    assert scope_roots(db, "actor:reliance") >= {"asset:jamnagar", "asset:sikka"}
    refinery = balance(db, "asset:jamnagar", START, END, "substance")["totals"]
    terminal = balance(db, "asset:sikka", START, END, "substance")["totals"]
    assert close(company["closing"], refinery["closing"] + terminal["closing"])


def test_country_exports_crude_with_its_carriers(db):
    totals = balance(db, "place:saudi-arabia", START, END, "substance")["totals"]
    assert totals["carrier"] < 0
    assert totals["closing"] < totals["opening"]


def test_element_level_keeps_the_total_mass(db):
    substance = balance(db, "asset:jamnagar", START, END, "substance")["totals"]
    element = balance(db, "asset:jamnagar", START, END, "element")
    assert {row["symbol"] for row in element["rows"]} >= {"C", "H", "S"}
    for column in FLOWS:
        assert close(element["totals"][column], substance[column])
        assert close(sum(row["values"][column] for row in element["rows"]), substance[column])


def test_scope_tree_has_both_axes(db):
    tree = scope_tree(db)
    geo, control = tree["axes"]
    assert geo["roots"][0]["id"] == "place:earth"
    states = {node["id"]: node for node in control["roots"][0]["children"]}
    assert "actor:india" in states
    companies = {node["id"] for node in states["actor:india"]["children"]}
    assert "actor:reliance" in companies


def test_bad_requests_are_refused(db):
    with pytest.raises(BalanceError):
        balance(db, "place:earth", END, START, "substance")
    with pytest.raises(BalanceError):
        balance(db, "place:nowhere", START, END, "substance")
    with pytest.raises(BalanceError):
        balance(db, "place:earth", START, END, "quark")


def test_extraction_is_broken_down_by_direction(db):
    result = balance(db, "place:ghawar", START, END, "substance")
    crude = next(row for row in result["rows"] if row["id"] == "type:arab-light")
    labels = {row["event_type"]: row for row in crude["breakdown"]}
    assert set(labels) == {
        "Видобуток → Abqaiq processing and storage",
        "Видобуток → Other Ghawar off-take (aggregate)",
    }
    out = sum(row["outflow"] for row in labels.values())
    assert close(out, crude["values"]["outflow"])
    # Most of Ghawar's crude goes elsewhere than the pilot route to India.
    assert labels["Видобуток → Other Ghawar off-take (aggregate)"]["outflow"] > 2 * (
        labels["Видобуток → Abqaiq processing and storage"]["outflow"]
    )


def test_series_adds_up_to_the_balance_of_the_period(db):
    whole = balance(db, "place:ghawar", START, END, "substance")
    crude = next(row for row in whole["rows"] if row["id"] == "type:arab-light")
    series = balance_series(db, "place:ghawar", START, END, "substance", "type:arab-light", "month")
    points = series["points"]
    assert len(points) == 12 and points[0]["from"].startswith("2023-01-01")
    assert points[-1]["to"].startswith("2024-01-01")
    # Each month opens with the closing of the previous one.
    for before, after in zip(points, points[1:]):
        assert close(before["values"]["closing"], after["values"]["opening"])
    for column in ("opening", "outflow", "closing"):
        assert close(series["totals"][column], crude["values"][column], scale=1e9), column
    assert set(series["flows"]) == {row["event_type"] for row in crude["breakdown"]}

    # One flow of the breakdown, by quarter.
    flow = "Видобуток → Other Ghawar off-take (aggregate)"
    quarters = balance_series(
        db, "place:ghawar", START, END, "substance", "type:arab-light", "quarter", flow
    )
    assert len(quarters["points"]) == 4
    expected = next(row for row in crude["breakdown"] if row["event_type"] == flow)["outflow"]
    assert close(quarters["totals"]["outflow"], expected, scale=1e9)
    assert all(p["values"]["opening"] == 0 for p in quarters["points"])


def test_series_refuses_too_many_points(db):
    with pytest.raises(BalanceError):
        balance_series(
            db, "place:earth", datetime(2019, 1, 1, tzinfo=UTC), datetime(2040, 1, 1, tzinfo=UTC),
            "substance", "type:arab-light", "month",
        )
