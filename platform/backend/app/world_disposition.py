"""Where Ghawar crude goes: known recipients from published Saudi statistics, else Unknown.

Saudi crude output each year is used at home (refinery runs, crude burned in power
plants) or exported (to countries with published import figures). Ghawar's output
outside the pilot route to India is spread over the same recipients in proportion:

    share     = (Ghawar output - pilot flow) / (Saudi output - Saudi crude to India)
    recipient = share x Saudi crude to that recipient                (derived)
    Unknown   = (Ghawar output - pilot flow) - sum of known recipients

so volumes whose recipient is not published end in "Unknown recipient", and the field
balance always shows the whole production. Years after the data repeat the last year's
proportions (forecast).
"""

from dataclasses import dataclass

UNKNOWN = "place:unknown-recipient"

# (id, name, kind, type, parent place, operator, description). Importing regions follow the
# destination regions of OPEC's export statistics; domestic users are aggregate assets in
# Saudi Arabia.
RECIPIENTS: list[tuple[str, str, str, str, str, str | None, str]] = [
    ('place:china', 'China', "place", "type:region", "place:land-surface", None, ""),
    ('place:oecd-asia-pacific', 'Japan, South Korea and Oceania (OECD Asia Pacific)', "place", "type:region", "place:land-surface", None, ""),
    ('place:other-asia', 'Other Asia (Taiwan, Singapore, Thailand and others)', "place", "type:region", "place:land-surface", None, ""),
    ('place:europe', 'Europe (OECD Europe)', "place", "type:region", "place:land-surface", None, ""),
    ('place:north-america', 'North America (OECD Americas)', "place", "type:region", "place:land-surface", None, ""),
    ('place:africa', 'Africa (incl. Egypt)', "place", "type:region", "place:land-surface", None, ""),
    ('place:middle-east', 'Other Middle East', "place", "type:region", "place:land-surface", None, ""),
    (
        "asset:saudi-refineries",
        "Saudi refineries (aggregate)",
        "asset",
        "type:process-unit",
        "place:saudi-arabia",
        "actor:saudi-aramco",
        "Crude runs of all refineries in Saudi Arabia, aggregated.",
    ),
    (
        "asset:saudi-crude-burn",
        "Saudi power plants, crude burn (aggregate)",
        "asset",
        "type:process-unit",
        "place:saudi-arabia",
        None,
        "Crude oil used directly (mostly burned for power) in Saudi Arabia, aggregated.",
    ),
    (
        UNKNOWN,
        "Unknown recipient",
        "place",
        "type:aggregate-offtake",
        "place:earth",
        None,
        "Produced volumes whose recipient is not published: other export destinations,"
        " stock changes and statistical differences.",
    ),
]

_ASB22 = "OPEC Annual Statistical Bulletin 2022"
_ASB26 = "OPEC Annual Statistical Bulletin 2026"
_JODI = "JODI Oil World Database (12 monthly values / days)"


def _asb(year: int) -> str:
    return _ASB22 if year <= 2020 else _ASB26


# Saudi crude to each known recipient, thousand barrels per day, by year. Exports by
# destination region are OPEC's exporter-side figures (India is the pilot's own series);
# refinery runs are OPEC refinery throughput; direct use (crude burn) is JODI.
_EXPORTS_KBD: dict[str, list[int]] = {
    'place:china': [1671, 1701, 1758, 1754, 1608, 1495, 1620],
    'place:oecd-asia-pacific': [1866, 1855, 1754, 1978, 1943, 1787, 1858],
    'place:other-asia': [781, 582, 580, 1046, 1010, 907, 1067],
    'place:europe': [797, 756, 517, 759, 678, 721, 660],
    'place:north-america': [561, 549, 422, 530, 347, 320, 322],
    'place:africa': [177, 202, 196, 237, 175, 108, 115],
    'place:middle-east': [266, 212, 209, 151, 135, 30, 39],
}
_REFINERY_KBD = [2484, 2173, 2475, 2702, 2514, 2591, 2750]
_BURN_KBD = [425, 422, 437, 487, 473, 455, 426]
_YEARS = list(range(2019, 2026))

SAUDI_DISPOSITION: dict[int, dict[str, tuple[float, str, str]]] = {
    year: {
        **{
            region: (values[i] * 1000.0, "statistic", f"{_asb(year)}: Saudi crude exports to this region, {values[i]} kb/d")
            for region, values in _EXPORTS_KBD.items()
        },
        "asset:saudi-refineries": (
            _REFINERY_KBD[i] * 1000.0,
            "statistic",
            f"{_asb(year)}: Saudi refinery throughput {_REFINERY_KBD[i]} kb/d",
        ),
        "asset:saudi-crude-burn": (
            _BURN_KBD[i] * 1000.0,
            "derived",
            f"{_JODI}: Saudi crude direct use {_BURN_KBD[i]} kb/d",
        ),
    }
    for i, year in enumerate(_YEARS)
}


@dataclass(frozen=True)
class Share:
    recipient: str
    bbl_per_day: float
    provenance: str
    reference: str


def data_year(year: int) -> int | None:
    """The year whose published recipients apply: the year itself, else the closest one."""
    if year in SAUDI_DISPOSITION:
        return year
    earlier = [y for y in SAUDI_DISPOSITION if y <= year]
    if earlier:
        return max(earlier)
    return min(SAUDI_DISPOSITION) if SAUDI_DISPOSITION else None


def allocate(rest_bbl: float, year: int | None, base_bbl: float, forecast: bool) -> list[Share]:
    """Spread ``rest_bbl`` (Ghawar output outside the pilot, bbl/d) over the recipients.

    ``year`` is the data year (see ``data_year``) and ``base_bbl`` the Saudi crude of that
    year outside India, which the published recipient volumes are a part of.
    """
    if rest_bbl <= 0:
        return []
    known = SAUDI_DISPOSITION.get(year, {}) if year is not None else {}
    share = rest_bbl / base_bbl if base_bbl > 0 else 0.0
    provenance = "forecast" if forecast else "derived"
    rows = [
        Share(
            recipient,
            share * bbl,
            provenance,
            f"{reference}; x {share:.4f} (Ghawar share of Saudi crude outside the pilot)",
        )
        for recipient, (bbl, _, reference) in known.items()
    ]
    total = sum(row.bbl_per_day for row in rows)
    if total > rest_bbl:
        # Published uses exceed production (stock draws): scale them to the production.
        rows = [
            Share(r.recipient, r.bbl_per_day * rest_bbl / total, r.provenance, f"{r.reference}; scaled")
            for r in rows
        ]
        total = rest_bbl
    rows.append(
        Share(
            UNKNOWN,
            rest_bbl - total,
            provenance,
            "Remainder: Ghawar output not matched to a published recipient",
        )
    )
    return [row for row in rows if row.bbl_per_day > 0]
