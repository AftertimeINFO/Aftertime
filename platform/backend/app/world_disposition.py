"""Where Ghawar crude goes: known recipients from published Saudi statistics, else Unknown.

Saudi crude output each year is used at home (refinery runs, crude burned directly) or
exported (destination regions of OPEC's statistics). Ghawar's output outside the pilot
route to India is spread over the same recipients in proportion:

    share     = (Ghawar output - pilot flow) / (Saudi output - Saudi crude to India)
    recipient = share x Saudi crude to that recipient                (derived)
    Unknown   = (Ghawar output - pilot flow) - sum of known recipients

so volumes whose recipient is not published end in "Unknown recipient", and the field
balance always shows the whole production. Before 1996 no recipient is published: all of
it is Unknown. After the data the last year's proportions apply (forecast).
"""

from dataclasses import dataclass, field

from app.world_history import DISPOSITION, Figure

UNKNOWN = "place:unknown-recipient"

# (id, name, kind, type, parent place, operator, description). Importing regions follow the
# destination regions of OPEC's export statistics (their scheme changed in 2009 and 2016);
# domestic users are aggregate assets in Saudi Arabia.
RECIPIENTS: list[tuple[str, str, str, str, str, str | None, str]] = [
    ("place:china", "China", "place", "type:region", "place:land-surface", None, ""),
    (
        "place:oecd-asia-pacific",
        "Japan, South Korea and Oceania (OECD Asia Pacific)",
        "place",
        "type:region",
        "place:land-surface",
        None,
        "",
    ),
    (
        "place:other-asia",
        "Other Asia (Taiwan, Singapore, Thailand and others)",
        "place",
        "type:region",
        "place:land-surface",
        None,
        "",
    ),
    (
        "place:asia-pacific",
        "Asia Pacific, not split by country (OPEC 1996-2015)",
        "place",
        "type:region",
        "place:land-surface",
        None,
        "OPEC's Asia Pacific region before 2016 (China, Japan, Korea and others; India is"
        " taken out from 2000, it is the pilot route).",
    ),
    ("place:europe", "Europe (OECD Europe)", "place", "type:region", "place:land-surface", None, ""),
    (
        "place:north-america",
        "North America (OECD Americas)",
        "place",
        "type:region",
        "place:land-surface",
        None,
        "",
    ),
    ("place:latin-america", "Latin America", "place", "type:region", "place:land-surface", None, ""),
    ("place:africa", "Africa (incl. Egypt)", "place", "type:region", "place:land-surface", None, ""),
    ("place:middle-east", "Other Middle East", "place", "type:region", "place:land-surface", None, ""),
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
        " stock changes, statistical differences, and all years before 1996.",
    ),
]


@dataclass(frozen=True)
class Share:
    recipient: str
    bbl_per_day: float
    provenance: str
    reference: str
    sources: list = field(default_factory=list)


def data_year(year: int) -> int | None:
    """The year whose published recipients apply: the year itself, the last year with data
    after the data, none before it."""
    if year in DISPOSITION:
        return year
    if not DISPOSITION or year < min(DISPOSITION):
        return None
    return max(y for y in DISPOSITION if y <= year)


def allocate(
    rest_bbl: float,
    known: dict[str, Figure],
    base_bbl: float,
    field_provenance: str,
    field_sources: list,
) -> list[Share]:
    """Spread ``rest_bbl`` (Ghawar output outside the pilot, bbl/d) over the recipients.

    ``known`` are the published users of Saudi crude in the data year and ``base_bbl`` the
    Saudi crude of that year outside India, which they are a part of.
    """
    if rest_bbl <= 0:
        return []
    share = rest_bbl / base_bbl if base_bbl > 0 else 0.0
    forecast = field_provenance == "forecast"

    def provenance(figure_provenance: str) -> str:
        if forecast:
            return "forecast"
        return "assumed" if "assumed" in (figure_provenance, field_provenance) else "derived"

    rows = [
        Share(
            recipient,
            share * figure.bbl_per_day,
            provenance(figure.provenance),
            f"{figure.note}; x {share:.4f} (Ghawar part of Saudi crude outside the pilot)",
            _merge(field_sources, figure.sources),
        )
        for recipient, figure in known.items()
    ]
    total = sum(row.bbl_per_day for row in rows)
    if total > rest_bbl:
        # Published uses exceed production (stock draws): scale them to the production.
        rows = [
            Share(r.recipient, r.bbl_per_day * rest_bbl / total, r.provenance, f"{r.reference}; scaled", r.sources)
            for r in rows
        ]
        total = rest_bbl
    rows.append(
        Share(
            UNKNOWN,
            rest_bbl - total,
            "forecast" if forecast else ("assumed" if field_provenance == "assumed" else "derived"),
            "Remainder: Ghawar output not matched to a published recipient",
            list(field_sources),
        )
    )
    return [row for row in rows if row.bbl_per_day > 0]


def _merge(*lists: list) -> list:
    merged: list = []
    for items in lists:
        for item in items:
            if item not in merged:
                merged.append(item)
    return merged
