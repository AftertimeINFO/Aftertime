"""Seed scenarios of the grid section: historical replays and a what-if example.

Events name their targets by ``match`` rules (kind + name pattern), because asset ids
belong to a particular import. Only facts with a public source are events; where the
exact targets of an attack are not public, ``rule_strike`` picks conditional targets and
says so in its label, so the replay never claims more than its sources do.
"""

from __future__ import annotations

import json

from sqlalchemy import Engine, text

ZNPP = {"kind": "plant", "name": "%Запорізька АЕС%", "alt": "%Zaporizhzhia%Nuclear%", "country": "UA"}
RIVNE = {"kind": "plant", "name": "%Рівненська АЕС%", "alt": "%Rivne%Nuclear%", "country": "UA"}
KHMELNYTSKYI = {"kind": "plant", "name": "%Хмельницька АЕС%", "alt": "%Khmelnytskyi%Nuclear%", "country": "UA"}
SOUTH_UKRAINE = {"kind": "plant", "name": "%Південноукраїнська АЕС%", "alt": "%South Ukraine%Nuclear%", "country": "UA"}
KAKHOVKA = {"kind": "plant", "name": "%Каховськ%ГЕС%", "alt": "%Kakhovka%", "country": "UA"}
DNIPRO_HPP = {"kind": "plant", "name": "%ДніпроГЕС%", "alt": "%Дніпровськ%ГЕС%", "country": "UA"}
TRYPILSKA = {"kind": "plant", "name": "%Трипільськ%ТЕС%", "alt": "%Trypil%", "country": "UA"}

SOURCES = {
    "iaea_znpp_shutdown": "https://www.aljazeera.com/news/2022/9/11/last-reactor-at-ukraines-zaporizhzhia-nuclear-plant-shut-down",
    "iaea_20221123": "https://www.globalsecurity.org/wmd/library/news/ukraine/2022/11/ukraine-221123-iaea01.htm",
    "kakhovka": "https://www.pravda.com.ua/eng/news/2023/06/06/7405492/",
    "dnipro_hpp": "https://kyivindependent.com/ukrhydroenergo-zaporizhzhias-dnipro-hydroelectric-power-plant-lost-about-3rd-of-generation-capacity/",
    "trypilska": "https://www.pravda.com.ua/eng/news/2024/04/11/7450746",
    "ohchr_2024": "https://ukraine.ohchr.org/en/Attacks-on-Ukraines-Energy-Infrastructure-Harm-to-the-Civilian-Population",
    "ohchr_2026": "https://ukraine.un.org/en/318327-attacks-against-ukraine%E2%80%99s-energy-infrastructure-and-update-human-rights-situation-ukraine-1",
    "ohchr_jan_2026": "https://ukraine.ohchr.org/sites/default/files/2026-02/Ukraine%20-%20protection%20of%20civilians%20in%20armed%20conflict%20%28January%202026%29_ENG.pdf",
}


# Documented permanent losses: dated overrides of the assets, so that every scenario —
# historical or a what-if made in the wizard — starts from the state the grid was in.
LOSSES: list[tuple[dict, str, object, str, str, str]] = [
    (ZNPP, "status", "occupied", "2022-09-11", "ЗАЕС зупинена під окупацією (з 11.09.2022)", "iaea_znpp_shutdown"),
    (KAKHOVKA, "status", "destroyed", "2023-06-06", "Каховська ГЕС зруйнована (06.06.2023)", "kakhovka"),
    (DNIPRO_HPP, "availability", 0.67, "2024-03-22", "ДніпроГЕС втратила близько третини потужності (22.03.2024)", "dnipro_hpp"),
    (TRYPILSKA, "status", "destroyed", "2024-04-11", "Трипільська ТЕС зруйнована (11.04.2024)", "trypilska"),
]


SCENARIOS: list[dict] = [
    {
        "id": "ua-2022-2026-generation-losses",
        "name": "Україна 2022–2026: втрати генерації (хронологія)",
        "mode": "historical",
        "description": (
            "Щотижневий вечірній пік енергосистеми України та Молдови від січня 2022 до січня 2026. "
            "Підтверджені відкритими джерелами втрати (ЗАЕС, Каховська ГЕС, ДніпроГЕС, Трипільська ТЕС) "
            "задано датованими правками об'єктів, тож вони діють і в усіх інших сценаріях; подією "
            "показано також відключення АЕС 23.11.2022. Масові удари по мережі, точні цілі яких "
            "не розкриваються, показано умовними цілями. Порівняння з фактом — дефіцит у січні 2026 "
            "за звітом ООН."
        ),
        "countries": ["UA", "MD"],
        "as_of": "2022-01-01",
        "start_at": "2022-01-04T17:00:00Z",
        "end_at": "2026-01-27T17:00:00Z",
        "step_hours": 168,
        "events": [
            {
                "at": "2022-11-23T13:30:00Z", "type": "rule_strike",
                "label": "Масований удар по мережі (умовні цілі: 8 підстанцій 330–750 кВ)",
                "payload": {"selector": {"kind": "substation", "min_kv": 330, "countries": ["UA"], "count": 8}, "repair_hours": [72, 240, 720]},
                "source_url": SOURCES["iaea_20221123"],
            },
            {
                "at": "2022-11-23T13:40:00Z", "type": "strike", "match": [RIVNE, KHMELNYTSKYI, SOUTH_UKRAINE],
                "label": "АЕС автоматично відключено захистом від мережі", "payload": {"repair_hours": [20, 30, 48]},
                "source_url": SOURCES["iaea_20221123"],
            },
            {
                "at": "2024-06-01T00:00:00Z", "type": "rule_strike",
                "label": "Хвилі ударів березня–серпня 2024 по ТЕС і ГЕС (умовні цілі: 8 станцій ≥ 200 МВт)",
                "payload": {"selector": {"kind": "plant", "countries": ["UA"], "fuels": ["coal", "gas", "hydro"], "min_mw": 200, "count": 8}, "capacity_share": 0.6},
                "source_url": SOURCES["ohchr_2024"],
            },
            {
                "at": "2025-11-30T00:00:00Z", "type": "rule_strike",
                "label": "Хвилі ударів жовтня–листопада 2025 (умовні цілі: 10 станцій ≥ 100 МВт)",
                "payload": {"selector": {"kind": "plant", "countries": ["UA"], "fuels": ["coal", "gas", "hydro"], "min_mw": 100, "count": 10}, "capacity_share": 0.6},
                "source_url": SOURCES["ohchr_2026"],
            },
        ],
        "expected": {
            "checks": [
                {
                    "metric": "unserved_mw", "country": "UA", "at": "2026-01-27T17:00:00Z", "value": 7000,
                    "tolerance": 0.4, "label": "Дефіцит у пік: потреба ~18 ГВт, доступно ~11 ГВт (січень 2026)",
                    "source_url": SOURCES["ohchr_jan_2026"],
                },
            ]
        },
        "sources": [{"title": k, "url": v} for k, v in SOURCES.items()],
    },
    {
        "id": "ua-2022-11-23-blackout",
        "name": "23.11.2022: системна аварія після масованого удару",
        "mode": "historical",
        "description": (
            "Масований ракетний удар 23 листопада 2022 року: захист відключив від мережі всі АЕС на "
            "підконтрольній території, більша частина споживачів залишилася без живлення. МАГАТЕ "
            "повідомило про відновлення приєднання АЕС протягом наступних днів. Конкретні уражені "
            "підстанції публічно не названо — їх показано умовними цілями."
        ),
        "countries": ["UA", "MD"],
        "as_of": "2022-11-01",
        "start_at": "2022-11-23T06:00:00Z",
        "end_at": "2022-11-27T06:00:00Z",
        "step_hours": 1,
        "events": [
            {
                "at": "2022-11-23T13:30:00Z", "type": "rule_strike",
                "label": "Удар по мережі (умовні цілі: 10 підстанцій 330–750 кВ)",
                "payload": {"selector": {"kind": "substation", "min_kv": 330, "countries": ["UA"], "count": 10}, "repair_hours": [12, 48, 240]},
                "source_url": SOURCES["iaea_20221123"],
            },
            {
                "at": "2022-11-23T13:40:00Z", "type": "strike", "match": [RIVNE, KHMELNYTSKYI, SOUTH_UKRAINE],
                "label": "АЕС автоматично відключено захистом від мережі", "payload": {"repair_hours": [20, 30, 48]},
                "source_url": SOURCES["iaea_20221123"],
            },
        ],
        "uncertainty": {"members": 50},
        "expected": {
            "checks": [
                {
                    "metric": "unserved_share", "at": "2022-11-23T15:00:00Z", "value": 0.5, "op": "min",
                    "label": "Знеструмлено більшу частину споживачів (≥ 50%)", "source_url": SOURCES["iaea_20221123"],
                },
            ]
        },
        "sources": [{"title": "IAEA Update 131", "url": SOURCES["iaea_20221123"]}],
    },
    {
        "id": "whatif-cold-spell-gas",
        "name": "Що, якщо: холодна хвиля та обмеження газу (січень 2026)",
        "mode": "whatif",
        "description": (
            "Гіпотетичний сценарій для перевірки стійкості: попит зростає на 12% через морози, "
            "а через добу доступність газової генерації падає до 60%. Стан генерації — з урахуванням "
            "підтверджених втрат 2022–2024 років."
        ),
        "countries": ["UA", "MD"],
        "as_of": "2026-01-01",
        "start_at": "2026-01-20T00:00:00Z",
        "end_at": "2026-01-24T00:00:00Z",
        "step_hours": 1,
        "events": [
            {"at": "2026-01-20T00:00:00Z", "type": "demand", "label": "Морози: попит +12%", "payload": {"countries": ["UA", "MD"], "factor": 1.12}},
            {"at": "2026-01-21T00:00:00Z", "type": "fuel", "label": "Газова генерація: доступно 60%", "payload": {"fuel": "gas", "factor": 0.6}},
        ],
        "uncertainty": {"members": 30},
        "expected": {},
        "sources": [],
    },
]


def seed_grid_overrides(engine: Engine) -> int:
    """Insert the documented losses as overrides once the assets are imported (idempotent)."""
    from app.grid.runner import resolve_targets

    added = 0
    for rule, field, value, since, note, source in LOSSES:
        scenario = resolve_targets(engine, {"events": [{"match": [rule]}]})
        for asset in scenario["events"][0]["targets"]:
            with engine.begin() as connection:
                exists = connection.execute(
                    text(
                        "SELECT 1 FROM odbl.grid_overrides WHERE asset_id = :a AND field = :f "
                        "AND valid_from = :d AND source_url = :u"
                    ),
                    {"a": asset, "f": field, "d": since, "u": SOURCES[source]},
                ).first()
                if exists:
                    continue
                connection.execute(
                    text(
                        "INSERT INTO odbl.grid_overrides (asset_id, field, value, valid_from, "
                        "source_url, note, author) VALUES (:a, :f, CAST(:v AS jsonb), :d, :u, :n, "
                        "'Aftertime')"
                    ),
                    {"a": asset, "f": field, "v": json.dumps(value), "d": since, "u": SOURCES[source], "n": note},
                )
                added += 1
    return added


def seed_grid_scenarios(engine: Engine) -> int:
    """Upsert the seed scenarios (they belong to the system; user scenarios have other ids)."""
    with engine.begin() as connection:
        if not connection.execute(text("SELECT to_regclass('odbl.grid_scenarios') IS NOT NULL")).scalar():
            return 0
        for scenario in SCENARIOS:
            events = [{**e, "id": e.get("id") or f"e{i + 1}"} for i, e in enumerate(scenario["events"])]
            uncertainty = {**scenario.get("uncertainty", {}), "step_hours": scenario["step_hours"]}
            connection.execute(
                text(
                    """
                    INSERT INTO odbl.grid_scenarios (id, name, mode, description, countries, as_of,
                        start_at, end_at, events, uncertainty, expected, sources, author)
                    VALUES (:id, :name, :mode, :description, :countries, :as_of, :start_at, :end_at,
                        CAST(:events AS jsonb), CAST(:uncertainty AS jsonb),
                        CAST(:expected AS jsonb), CAST(:sources AS jsonb), 'Aftertime')
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, mode = EXCLUDED.mode,
                        description = EXCLUDED.description, countries = EXCLUDED.countries,
                        as_of = EXCLUDED.as_of, start_at = EXCLUDED.start_at,
                        end_at = EXCLUDED.end_at, events = EXCLUDED.events,
                        uncertainty = EXCLUDED.uncertainty, expected = EXCLUDED.expected,
                        sources = EXCLUDED.sources, updated_at = now()
                    """
                ),
                {
                    "id": scenario["id"], "name": scenario["name"], "mode": scenario["mode"],
                    "description": scenario["description"], "countries": scenario["countries"],
                    "as_of": scenario["as_of"], "start_at": scenario["start_at"],
                    "end_at": scenario["end_at"], "events": json.dumps(events, ensure_ascii=False),
                    "uncertainty": json.dumps(uncertainty), "expected": json.dumps(scenario["expected"], ensure_ascii=False),
                    "sources": json.dumps(scenario["sources"], ensure_ascii=False),
                },
            )
    if engine.dialect.name == "postgresql":
        seed_grid_overrides(engine)
    return len(SCENARIOS)
