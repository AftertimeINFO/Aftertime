"""Historical series of the world pilot, each value with the publications behind it.

* Saudi crude output 1951-2025 and its users (refinery runs, crude burn, exports by
  destination region) come from ``data/saudi_crude.csv`` (OPEC Annual Statistical
  Bulletins, JODI, GASTAT; one source per value).
* Saudi crude to India (the pilot route through Sikka to Jamnagar) starts in 2000, the
  first full year of the Jamnagar refinery: UN Comtrade (India's imports) for 2006-2015,
  OPEC's exports to India for 2016-2025, and an interpolation for 2000-2005.
* Ghawar output is not published year by year. It is reconstructed as a share of Saudi
  output: the share is fixed at the years with a published Ghawar figure and
  interpolated in between (``GHAWAR_ANCHORS``); from 2019 it is Ghawar's part of
  Aramco's capacity (3.8 of 12.0 mb/d). The reconstruction meets the published
  cumulative production (about 66 bn bbl by 2007, about 85 bn bbl by 2018).

Values are barrels per day; provenance follows the ledger's vocabulary: ``statistic``
(published), ``derived`` (computed from published figures), ``assumed`` (interpolated).
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

from app.world_sources import source

DATA = Path(__file__).parent / "data" / "saudi_crude.csv"
BBL_PER_TONNE = 7.33
FIRST_YEAR, LAST_YEAR = 1951, 2025
CARGO_FROM_YEAR = 2000  # Jamnagar refinery: commissioned in 1999, first full year 2000


@dataclass(frozen=True)
class Figure:
    bbl_per_day: float
    provenance: str
    note: str
    sources: list = field(default_factory=list)


def _days(year: int) -> int:
    return 366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365


def _load() -> dict[str, dict[int, Figure]]:
    series: dict[str, dict[int, Figure]] = {}
    with DATA.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            kbd = float(row["kbd"])
            basis = row["basis"]
            ref = source(row["source"])
            series.setdefault(row["series"], {})[int(row["year"])] = Figure(
                kbd * 1000.0, "statistic" if basis == "statistic" else "derived", f"{ref['title']}: {kbd:g} kb/d", [ref]
            )
    return series


_SERIES = _load()

# ----- Saudi Arabia -----

SAUDI_PRODUCTION: dict[int, Figure] = _SERIES["production"]

# Destination regions of OPEC's export statistics -> recipient places of the model.
REGION_RECIPIENT = {
    "china": "place:china",
    "oecd-asia-pacific": "place:oecd-asia-pacific",
    "other-asia": "place:other-asia",
    "asia-pacific": "place:asia-pacific",
    "europe": "place:europe",
    "north-america": "place:north-america",
    "latin-america": "place:latin-america",
    "africa": "place:africa",
    "middle-east": "place:middle-east",
}

# ----- India (pilot route) -----


def _mt(year: int, million_tonnes: float) -> float:
    return million_tonnes * 1e6 * BBL_PER_TONNE / _days(year)


_COMTRADE_MT = {
    1999: 10.96, 2006: 18.52, 2007: 26.29, 2008: 26.26, 2009: 26.45, 2010: 27.70,
    2011: 29.45, 2012: 33.62, 2013: 39.23, 2014: 35.43, 2015: 38.43,
}


def _india() -> dict[int, Figure]:
    rows: dict[int, Figure] = {}
    comtrade = source("un-comtrade-india")
    for year, mt in _COMTRADE_MT.items():
        if year >= CARGO_FROM_YEAR:
            rows[year] = Figure(
                _mt(year, mt), "derived", f"UN Comtrade: India's imports from Saudi Arabia {mt} Mt x 7.33 bbl/t", [comtrade]
            )
    # 2000-2005: no annual figure found; interpolated between 1999 and 2006 (Comtrade).
    lo, hi = _mt(1999, _COMTRADE_MT[1999]), _mt(2006, _COMTRADE_MT[2006])
    for year in range(CARGO_FROM_YEAR, 2006):
        value = lo + (hi - lo) * (year - 1999) / (2006 - 1999)
        rows[year] = Figure(
            value, "assumed", "Interpolated between UN Comtrade 1999 and 2006 (no annual figure found)", [comtrade]
        )
    for year, figure in _SERIES["export:india"].items():
        rows[year] = figure
    return dict(sorted(rows.items()))


INDIA: dict[int, Figure] = _india()

# ----- Ghawar -----

GHAWAR_SHARE_2019 = 3.8 / 12.0
# Years with a published Ghawar output (kb/d), or a share of Saudi output: (value, sources).
GHAWAR_ANCHORS: dict[int, tuple[float, bool, list[str]]] = {
    # year: (kb/d or share, is_share, source keys)
    1951: (126, False, ["geoexpro-2010"]),
    1973: (5000, False, ["aramcoworld-1973"]),
    1975: (4200, False, ["geoexpro-2010"]),
    1980: (5588, False, ["iea-weo-2008"]),
    1981: (5700, False, ["iea-weo-2005"]),
    1986: (2750, False, ["geoexpro-2010"]),  # 2.5-3.0 mb/d in 1982-1990, mid-point
    1997: (5400, False, ["iea-weo-2005", "iea-weo-2008"]),  # "recent peak" 5.3-5.5
    2000: (5000, False, ["afifi-2004", "aapg-2005"]),  # about 5 mb/d in 1993-2003
    2004: (5200, False, ["iea-weo-2005"]),
    2007: (5100, False, ["iea-weo-2008"]),
    2009: (5000, False, ["geoexpro-2010"]),
    2019: (GHAWAR_SHARE_2019, True, ["aramco-prospectus-2019"]),
}


def _anchor_share(year: int) -> float:
    value, is_share, _ = GHAWAR_ANCHORS[year]
    if is_share:
        return value
    if year == 1986:
        # A range over 1982-1990: share of the average Saudi output of those years.
        mean = sum(SAUDI_PRODUCTION[y].bbl_per_day for y in range(1982, 1991)) / 9
        return value * 1000 / mean
    return value * 1000 / SAUDI_PRODUCTION[year].bbl_per_day


def _ghawar() -> dict[int, Figure]:
    years = sorted(GHAWAR_ANCHORS)
    shares = {year: _anchor_share(year) for year in years}
    rows: dict[int, Figure] = {}
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        saudi = SAUDI_PRODUCTION[year]
        if year >= years[-1]:
            share, lo, hi = GHAWAR_SHARE_2019, years[-1], years[-1]
        else:
            lo = max(y for y in years if y <= year)
            hi = min(y for y in years if y >= year)
            share = shares[lo] if lo == hi else shares[lo] + (shares[hi] - shares[lo]) * (year - lo) / (hi - lo)
        anchor = year in GHAWAR_ANCHORS
        keys = GHAWAR_ANCHORS[lo][2] + ([] if lo == hi else GHAWAR_ANCHORS[hi][2])
        refs = saudi.sources + [source(key) for key in dict.fromkeys(keys)]
        if year >= years[-1]:
            note = f"Saudi output x {share:.4f} (Ghawar MSC 3.8 of Aramco's 12.0 mb/d)"
            provenance = "derived"
        elif anchor:
            note = f"Published Ghawar output (share {share:.3f} of Saudi output)"
            provenance = "derived" if lo != 1986 else "assumed"
        else:
            note = f"Share {share:.3f} of Saudi output, interpolated between {lo} and {hi}"
            provenance = "assumed"
        rows[year] = Figure(saudi.bbl_per_day * share, provenance, note, refs)
    return rows


GHAWAR: dict[int, Figure] = _ghawar()


def disposition() -> dict[int, dict[str, Figure]]:
    """Known users of Saudi crude outside the pilot route, by year (bbl/d)."""
    rows: dict[int, dict[str, Figure]] = {}
    for name, values in _SERIES.items():
        if name.startswith("export:") and name != "export:india":
            recipient = REGION_RECIPIENT[name.split(":", 1)[1]]
        elif name == "refinery":
            recipient = "asset:saudi-refineries"
        elif name == "burn":
            recipient = "asset:saudi-crude-burn"
        else:
            continue
        for year, figure in values.items():
            rows.setdefault(year, {})[recipient] = figure
    # Before 2016 OPEC's Asia Pacific region includes India; the pilot route carries
    # India's part from 2000, so it is taken out of the region.
    for year, users in rows.items():
        region = users.get("place:asia-pacific")
        if region and year in INDIA:
            india = INDIA[year]
            users["place:asia-pacific"] = Figure(
                max(region.bbl_per_day - india.bbl_per_day, 0.0),
                "derived",
                f"{region.note} minus Saudi crude to India ({india.bbl_per_day / 1000:.0f} kb/d)",
                region.sources + india.sources,
            )
    return dict(sorted(rows.items()))


DISPOSITION: dict[int, dict[str, Figure]] = disposition()


def cumulative_ghawar_bbl(first: int, last: int) -> float:
    """Ghawar output summed over whole years ``first``..``last`` (barrels)."""
    return sum(GHAWAR[year].bbl_per_day * _days(year) for year in range(first, last + 1))
