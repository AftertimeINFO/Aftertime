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
ZAPORIZHZHIA_TPP = {"kind": "plant", "name": "Запорізька ТЕС", "alt": "Zaporizhzhia Power Plant", "country": "UA"}
LUHANSK_TPP = {"kind": "plant", "name": "%Луганська%електростанція%", "alt": "Luhansk power station", "country": "UA"}
VUHLEHIRSKA_TPP = {"kind": "plant", "name": "Вуглегірська ТЕС", "alt": "%Vuhlehirska%", "country": "UA"}
KURAKHOVE_TPP = {"kind": "plant", "name": "Курахівська ТЕС", "alt": "Kurakhove Power Station", "country": "UA"}
STAROBESHIVSKA_TPP = {"kind": "plant", "name": "Старобешівська ТЕС", "alt": "Starobeshivska TPP", "country": "UA"}
ZMIIVSKA_TPP = {"kind": "plant", "name": "Зміївська ТЕС", "alt": "Zmiivska power plant", "country": "UA"}
DTEK_TPPS = [
    {"kind": "plant", "name": "Бурштинська ТЕС", "alt": "Burshtyn TES", "country": "UA"},
    {"kind": "plant", "name": "Ладижинська ТЕС", "alt": "Ladyzhyn Thermal Power Plant", "country": "UA"},
    {"kind": "plant", "name": "Добротвірська ТЕС", "alt": "Dobrotvir power station", "country": "UA"},
    {"kind": "plant", "name": "Криворізька ТЕС", "alt": "Kryvoy Rog TEPS", "country": "UA"},
    {"kind": "plant", "name": "Придніпровська ТЕС", "alt": "Prydniprovska power station", "country": "UA"},
]
# Share of thermal and hydro capacity still available after the seven waves of
# 10.10–23.11.2022 (all large plants damaged). Not reported as a number: calibrated so that
# the deficit after the NPPs returned matches Ukrenergo's 27% of 30.11.2022.
WAVES_2022_AVAILABLE = 0.28
ZUIVSKA_TPP = {"kind": "plant", "name": "Зуєвська ТЕС", "alt": "Zuivska power station", "country": "UA"}

SOURCES = {
    "iaea_znpp_shutdown": "https://www.aljazeera.com/news/2022/9/11/last-reactor-at-ukraines-zaporizhzhia-nuclear-plant-shut-down",
    "iaea_20221123": "https://www.globalsecurity.org/wmd/library/news/ukraine/2022/11/ukraine-221123-iaea01.htm",
    "kakhovka": "https://www.pravda.com.ua/eng/news/2023/06/06/7405492/",
    "dnipro_hpp": "https://kyivindependent.com/ukrhydroenergo-zaporizhzhias-dnipro-hydroelectric-power-plant-lost-about-3rd-of-generation-capacity/",
    "trypilska": "https://www.pravda.com.ua/eng/news/2024/04/11/7450746",
    "ohchr_2024": "https://ukraine.ohchr.org/en/Attacks-on-Ukraines-Energy-Infrastructure-Harm-to-the-Civilian-Population",
    "ohchr_2026": "https://ukraine.un.org/en/318327-attacks-against-ukraine%E2%80%99s-energy-infrastructure-and-update-human-rights-situation-ukraine-1",
    "ztpp": "https://kyivindependent.com/ukraines-biggest-thermal-power-plant-stops-due-to-coal-shortage",
    "luhansk_tpp": "https://energo.dtek.com/en/media-center/press/luganska-tes-vidklyuchena-vid-energosistemi-cherez-nestabilnu-situatsiyu-v-regio/",
    "vuhlehirska": "https://www.aljazeera.com/news/2022/7/27/russian-forces-ukraine-both-claim-control-of-vital-power-plant",
    "kurakhove": "https://ceobs.org/ukraine-damage-map-kurakhivska-thermal-power-plant/",
    "starobeshivska": "https://www.unian.info/economics/1839231-donbasenergo-loses-control-of-starobeshivska-tpp-in-occupied-donbas",
    "waves_2022": "https://www.pravda.com.ua/eng/news/2022/11/22/7377445",
    "nov_24_2022": "https://pravda.com.ua/eng/news/2022/11/24/7377862",
    "nov_30_2022": "https://kyivindependent.com/ukrenergo-ukraine-faces-27-electricity-shortage-as-of-11-a-m-on-nov-30",
    "no_deficit_2023": "https://kyivindependent.com/ukrenergo-no-power-dificit-in-ukraine/",
    "dtek_80": "https://www.pravda.com.ua/eng/news/2024/04/3/7449397",
    "centrenergo_100": "https://komersant.ua/en/chornyy-den-tsentrenerho-vtratyla-100-heneratsii-2/",
    "crimea": "https://digitallibrary.un.org/record/767565",
    # Law 2268-VIII: the occupied parts of Donetsk and Luhansk oblasts (2014–2022).
    "ordlo": "https://zakon.rada.gov.ua/laws/show/2268-19",
    # Order of the Ministry for Reintegration No. 309: territories occupied since 2022 with
    # the dates their occupation began and ended, community by community.
    "occupied_2022": "https://zakon.rada.gov.ua/laws/show/z1668-22",
    "kurakhove_2025": "https://kyivindependent.com/russia-claims-to-capture-kurakhove",
    "ohchr_jan_2026": "https://ukraine.ohchr.org/sites/default/files/2026-02/Ukraine%20-%20protection%20of%20civilians%20in%20armed%20conflict%20%28January%202026%29_ENG.pdf",
}


# Documented permanent losses: dated overrides of the assets, so that every scenario —
# historical or a what-if made in the wizard — starts from the state the grid was in.
LOSSES: list[tuple[dict, str, object, str, str, str]] = [
    (ZNPP, "status", "occupied", "2022-09-11", "ЗАЕС зупинена під окупацією (з 11.09.2022)", "iaea_znpp_shutdown"),
    (KAKHOVKA, "status", "destroyed", "2023-06-06", "Каховська ГЕС зруйнована (06.06.2023)", "kakhovka"),
    (DNIPRO_HPP, "availability", 0.67, "2024-03-22", "ДніпроГЕС втратила близько третини потужності (22.03.2024)", "dnipro_hpp"),
    (TRYPILSKA, "status", "destroyed", "2024-04-11", "Трипільська ТЕС зруйнована (11.04.2024)", "trypilska"),
    # Thermal plants in occupied territory: outside the Ukrainian power system.
    (STAROBESHIVSKA_TPP, "status", "occupied", "2017-03-21", "Старобешівська ТЕС поза контролем України (з 2017)", "starobeshivska"),
    (ZUIVSKA_TPP, "status", "occupied", "2017-03-15", "Зуївська ТЕС поза контролем України (з 2017)", "starobeshivska"),
    (LUHANSK_TPP, "status", "occupied", "2022-02-21", "Луганська ТЕС зупинена й окупована (лютий 2022)", "luhansk_tpp"),
    (ZAPORIZHZHIA_TPP, "status", "occupied", "2022-03-04", "Запорізька ТЕС окупована (04.03.2022)", "ztpp"),
    (VUHLEHIRSKA_TPP, "status", "occupied", "2022-07-26", "Вуглегірська ТЕС окупована (26.07.2022)", "vuhlehirska"),
    (KURAKHOVE_TPP, "status", "destroyed", "2024-03-01", "Курахівська ТЕС непрацездатна (березень 2024)", "kurakhove"),
    # Strikes of March–April 2024 on thermal generation.
    (ZMIIVSKA_TPP, "status", "destroyed", "2024-04-11", "Зміївська ТЕС: Центренерго втратило 100% генерації (11.04.2024)", "centrenergo_100"),
    *[
        (plant, "availability", 0.2, "2024-03-29", "ТЕС ДТЕК: втрачено ~80% потужності (22–29.03.2024)", "dtek_80")
        for plant in DTEK_TPPS
    ],
]


def _waves_2022(at: str) -> dict:
    return {
        "at": at, "type": "fuel",
        "label": f"Сім хвиль ударів 10.10–23.11.2022 пошкодили всі великі ТЕС і ГЕС (доступно ~{round(WAVES_2022_AVAILABLE * 100)}%, калібровано)",
        "payload": {"fuels": ["coal", "gas", "hydro"], "countries": ["UA"], "factor": WAVES_2022_AVAILABLE},
        "source_url": SOURCES["waves_2022"],
    }


def _recovery_2023(at: str) -> dict:
    return {
        "at": at, "type": "fuel", "label": "Дефіциту потужності немає з 12.02.2023 (Укренерго)",
        "payload": {"fuels": ["coal", "gas", "hydro"], "countries": ["UA"], "factor": 1.0},
        "source_url": SOURCES["no_deficit_2023"],
    }

# Territory outside the control of Ukrenergo: while an area is in force its assets leave the
# Ukrainian system. The outlines are coarse polygons (about 5–10 km along the front line,
# after the ISW and DeepState maps), enough to tell which substations and plants lie in the
# area; the dates come from the sources. Only Ukrainian assets are matched, so an outline may
# run into Russia or the sea. Areas may overlap: a bus is outside control while any area
# containing it is in force.
CONTROL_AREAS: list[dict] = [
    {
        "name": "Крим (з 2014)",
        "country": "UA",
        "controlled_by": "UA-OCC",
        "valid_from": "2014-03-18",
        "source": "crimea",
        "note": "Резолюція ГА ООН 68/262; енергосистема Криму відокремлена від України з 2015 року",
        "wkt": (
            "POLYGON((32.40 45.30, 33.40 46.05, 33.60 46.13, 33.80 46.13, 34.30 45.95, "
            "34.80 46.03, 35.10 45.70, 35.40 45.45, 36.70 45.50, 36.70 44.30, 33.30 44.30, "
            "32.40 45.30))"
        ),
    },
    {
        "name": "Окуповані частини Донеччини й Луганщини (з 2015)",
        "country": "UA",
        "controlled_by": "UA-OCC",
        "valid_from": "2015-02-20",
        "source": "ordlo",
        "note": "Лінія розмежування після Дебальцевого (лютий 2015); Закон 2268-VIII",
        "wkt": (
            "POLYGON((41.50 48.80, 39.60 48.62, 39.25 48.70, 38.60 48.66, 38.45 48.58, "
            "38.35 48.45, 38.25 48.38, 38.10 48.37, 37.95 48.30, 37.85 48.20, 37.82 48.15, "
            "37.70 48.05, 37.62 47.97, 37.62 47.85, 37.60 47.78, 37.65 47.65, 37.75 47.50, "
            "37.85 47.30, 37.85 47.05, 41.50 46.80, 41.50 48.80))"
        ),
    },
    {
        "name": "Південь і Приазов’я (з березня 2022)",
        "country": "UA",
        "controlled_by": "UA-OCC",
        "valid_from": "2022-03-04",
        "source": "occupied_2022",
        "note": (
            "Лівобережжя Херсонщини, південь Запоріжжя (Енергодар — 04.03.2022), Приазов’я; "
            "Маріуполь у блокаді з 02.03 й окупований 20.05.2022"
        ),
        "wkt": (
            "POLYGON((31.55 46.50, 32.05 46.50, 32.40 46.56, 32.62 46.605, 32.76 46.66, "
            "32.95 46.70, 33.15 46.74, 33.38 46.79, 33.60 46.93, 33.90 47.12, 34.15 47.33, "
            "34.40 47.53, 34.65 47.57, 35.00 47.60, 35.30 47.52, 35.45 47.48, 35.80 47.46, "
            "36.25 47.57, 36.55 47.70, 36.85 47.78, 37.20 47.72, 37.60 47.78, 37.80 47.80, "
            "41.50 47.80, 41.50 45.80, 36.00 45.80, 32.50 45.90, 31.40 46.20, 31.55 46.50))"
        ),
    },
    {
        "name": "Північ Луганщини (з березня 2022)",
        "country": "UA",
        "controlled_by": "UA-OCC",
        "valid_from": "2022-03-01",
        "source": "occupied_2022",
        "note": "Старобільськ, Сватове, Щастя (Луганська ТЕС — 01.03.2022)",
        "wkt": (
            "POLYGON((38.00 50.50, 38.05 49.25, 38.50 49.15, 38.80 49.05, 38.85 48.95, "
            "39.10 48.75, 39.60 48.60, 41.50 48.60, 41.50 50.50, 38.00 50.50))"
        ),
    },
    {
        "name": "Сєвєродонецьк, Лисичанськ, Попасна (з липня 2022)",
        "country": "UA",
        "controlled_by": "UA-OCC",
        "valid_from": "2022-07-03",
        "source": "occupied_2022",
        "note": "Кремінна, Рубіжне, Попасна, Світлодарськ — квітень–травень, Лисичанськ — 03.07.2022",
        "wkt": (
            "POLYGON((38.05 49.25, 38.15 49.10, 38.28 48.90, 38.25 48.80, 38.20 48.65, "
            "38.15 48.50, 38.20 48.40, 38.60 48.55, 39.20 48.80, 38.85 49.10, 38.50 49.20, "
            "38.05 49.25))"
        ),
    },
    {
        "name": "Херсонщина, правобережжя (березень — листопад 2022)",
        "country": "UA",
        "controlled_by": "UA-OCC",
        "valid_from": "2022-03-02",
        "valid_to": "2022-11-11",
        "source": "occupied_2022",
        "note": "Херсон окуповано 02.03.2022, звільнено 11.11.2022",
        "wkt": (
            "POLYGON((31.90 46.60, 32.05 46.72, 32.45 46.85, 32.70 47.15, 33.10 47.30, "
            "33.45 47.52, 33.60 47.51, 33.62 47.45, 33.80 47.45, 33.95 47.52, 34.05 47.45, 33.90 47.12, 33.60 46.93, 33.38 46.79, "
            "33.15 46.74, 32.95 46.70, 32.76 46.66, 32.62 46.605, 32.40 46.56, 32.05 46.50, "
            "31.90 46.60))"
        ),
    },
    {
        "name": "Схід Харківщини й Лиман (березень — вересень 2022)",
        "country": "UA",
        "controlled_by": "UA-OCC",
        "valid_from": "2022-03-01",
        "valid_to": "2022-09-11",
        "source": "occupied_2022",
        "note": "Куп’янськ, Ізюм, Балаклія, Вовчанськ; звільнено у вересні 2022 (Лиман — 01.10.2022)",
        "wkt": (
            "POLYGON((36.00 50.50, 36.25 50.20, 36.45 50.08, 36.65 49.95, 36.80 49.80, "
            "36.70 49.55, 36.95 49.30, 37.00 49.10, 37.35 49.05, 37.65 48.95, 37.90 48.95, "
            "38.05 49.25, 38.00 50.50, 36.00 50.50))"
        ),
    },
    {
        "name": "Північ Київщини (лютий — квітень 2022)",
        "country": "UA",
        "controlled_by": "UA-OCC",
        "valid_from": "2022-02-25",
        "valid_to": "2022-04-02",
        "source": "occupied_2022",
        "note": "Чорнобильська зона, Іванків, Бородянка, Буча, Гостомель; Чернігівщину й Сумщину не задано",
        "wkt": (
            "POLYGON((29.30 52.50, 29.30 50.55, 29.80 50.42, 30.10 50.48, 30.22 50.54, "
            "30.35 50.58, 30.45 50.70, 30.45 51.10, 30.55 51.30, 30.60 52.50, 29.30 52.50))"
        ),
    },
    {
        "name": "Донеччина: Авдіївка — Курахове (2024 — січень 2025)",
        "country": "UA",
        "controlled_by": "UA-OCC",
        "valid_from": "2025-01-06",
        "source": "kurakhove_2025",
        "note": (
            "Втрачалося поступово: Авдіївка — 17.02.2024, Вугледар — 01.10.2024, Курахове — "
            "06.01.2025 (дата зони); лінію фронту після січня 2025 не відстежено"
        ),
        "wkt": (
            "POLYGON((37.95 48.30, 37.25 48.22, 37.20 48.05, 37.15 47.95, 37.10 47.80, "
            "37.20 47.72, 37.60 47.78, 37.62 47.97, 37.82 48.15, 37.95 48.30))"
        ),
    },
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
            _waves_2022("2022-11-15T00:00:00Z"),
            _recovery_2023("2023-02-12T00:00:00Z"),
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
                {
                    "metric": "available_mw", "at": "2026-01-27T17:00:00Z", "value": 11000,
                    "tolerance": 0.25, "label": "Доступна генерація у пік ~11 ГВт (січень 2026)",
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
        "end_at": "2022-12-01T06:00:00Z",
        "step_hours": 1,
        "events": [
            _waves_2022("2022-11-23T06:00:00Z"),
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
                    "metric": "unserved_share", "at": "2022-11-24T10:00:00Z", "value": 0.5,
                    "tolerance": 0.3, "label": "24.11: власна генерація покриває ~50% потреби",
                    "source_url": SOURCES["nov_24_2022"],
                },
                {
                    "metric": "unserved_share", "at": "2022-11-30T09:00:00Z", "value": 0.27,
                    "tolerance": 0.3, "label": "30.11, 11:00: дефіцит потужності 27% (Укренерго)",
                    "role": "calibration",
                    "source_url": SOURCES["nov_30_2022"],
                },
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


def seed_control_areas(engine: Engine) -> int:
    added = 0
    with engine.begin() as connection:
        for area in CONTROL_AREAS:
            added += connection.execute(
                text(
                    "INSERT INTO odbl.grid_control_areas (name, country, controlled_by, valid_from, "
                    "valid_to, geom, source_url, note) VALUES (:name, :country, :by, :since, :until, "
                    "ST_MakeValid(ST_GeomFromText(:wkt, 4326)), :url, :note) ON CONFLICT (name) DO UPDATE SET "
                    "geom = EXCLUDED.geom, valid_from = EXCLUDED.valid_from, valid_to = EXCLUDED.valid_to, "
                    "source_url = EXCLUDED.source_url, note = EXCLUDED.note"
                ),
                {
                    "name": area["name"], "country": area["country"], "by": area["controlled_by"],
                    "since": area["valid_from"], "until": area.get("valid_to"), "wkt": area["wkt"],
                    "url": SOURCES[area["source"]], "note": area["note"],
                },
            ).rowcount
    return added


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
        seed_control_areas(engine)
        seed_grid_overrides(engine)
    return len(SCENARIOS)
