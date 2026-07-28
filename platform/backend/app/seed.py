from datetime import UTC, datetime

from app.db import SessionLocal
from app.models import Entity, ProcessModel, Relation, Route, Scenario, Source

ENTITIES = [
    ("ua", "state", "institutional", "Украина", "UA"),
    ("operator", "company", "institutional", "Aftertime Nitrogen Operator", None),
    ("plant", "facility", "object", "Черкасский азотный узел", None),
    ("line", "production_line", "object", "Линия синтеза аммиака №1", None),
    ("tank", "storage_asset", "object", "Резервуар аммиака R-01", None),
    ("railcar", "transport_asset", "object", "Железнодорожная цистерна C-01", None),
    ("warehouse", "warehouse", "object", "Полтавский региональный склад", None),
    ("gas", "infrastructure", "object", "Газоснабжение", None),
    ("grid", "infrastructure", "object", "Энергосистема", None),
    ("rail", "infrastructure", "object", "Железнодорожная сеть", None),
    ("workforce", "workforce_pool", "agent", "Производственная смена", None),
    ("n", "atom", "atomic", "Азот", "N"),
    ("h", "atom", "atomic", "Водород", "H"),
    ("n2", "molecule", "molecular", "Молекулярный азот", "N₂"),
    ("h2", "molecule", "molecular", "Молекулярный водород", "H₂"),
    ("nh3", "substance", "substance", "Аммиак", "NH₃"),
]


def seed() -> None:
    with SessionLocal() as db:
        sources = [
            Source(
                id="orb",
                name="Aftertime reference model",
                url="https://orb-srp-prototype.neokkv.chatgpt.site",
                license="Project data",
                adapter="bootstrap",
            ),
            Source(
                id="chebi",
                name="ChEBI 2.0",
                url="https://www.ebi.ac.uk/chebi/backend/api/docs/",
                license="CC BY 4.0",
                adapter="chebi",
                configuration={"default_external_ids": ["16134", "18276", "17790"]},
            ),
            Source(
                id="worldbank",
                name="World Bank Indicators API",
                url="https://api.worldbank.org/v2/",
                license="CC BY 4.0",
                adapter="worldbank",
                configuration={"country": "UA", "indicator": "AG.CON.FERT.ZS"},
            ),
        ]
        for source in sources:
            db.merge(source)
        for entity_id, kind, level, name, symbol in ENTITIES:
            if not db.get(Entity, entity_id):
                db.add(
                    Entity(
                        id=entity_id,
                        kind=kind,
                        level=level,
                        name=name,
                        symbol=symbol,
                        jurisdiction="UA"
                        if level in {"object", "institutional", "agent"}
                        else None,
                        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                        attributes={"seed": True},
                    )
                )
        db.flush()
        relations = [
            ("r1", "operator", "operates", "plant"),
            ("r2", "plant", "contains", "line"),
            ("r3", "n2", "composed_of", "n"),
            ("r4", "h2", "composed_of", "h"),
            ("r5", "nh3", "composed_of", "n"),
            ("r6", "nh3", "composed_of", "h"),
            ("r7", "plant", "connected_to", "gas"),
            ("r8", "plant", "connected_to", "grid"),
            ("r9", "plant", "connected_to", "rail"),
        ]
        for relation_id, subject, predicate, object_id in relations:
            if not db.get(Relation, relation_id):
                db.add(
                    Relation(
                        id=relation_id,
                        subject_id=subject,
                        predicate=predicate,
                        object_id=object_id,
                        confidence=1,
                        source_id="orb",
                    )
                )
        db.merge(
            ProcessModel(
                id="ammonia-circuit",
                name="Одна тонна аммиака",
                version="ammonia-circuit-v0.3",
                owner_entity_id="line",
                duration_hours=18,
                yield_factor=0.985,
                specification={
                    "reaction": "N2 + 3H2 -> 2NH3",
                    "energy_intensity_gj_per_t": 28,
                    "electricity_mwh_per_t": 0.7,
                    "water_kg_per_kg": 1.58,
                },
                source_id="orb",
            )
        )
        db.merge(
            Route(
                id="route-rail",
                origin_id="plant",
                destination_id="warehouse",
                mode="rail",
                distance_km=286,
                capacity_per_day=60,
                duration_hours=8,
                availability=0.9,
                loss_factor=0.001,
                recovery_hours=24,
            )
        )
        db.merge(
            Route(
                id="route-road",
                origin_id="plant",
                destination_id="warehouse",
                mode="road",
                distance_km=312,
                capacity_per_day=18,
                duration_hours=6.5,
                availability=0.86,
                loss_factor=0.002,
                recovery_hours=8,
            )
        )
        scenarios = [
            (
                "base",
                "Базовый",
                0.55,
                {"gas": 0.74, "grid": 0.88, "logistics": 0.67, "workforce": 0.91},
            ),
            (
                "resilient",
                "Устойчивый",
                0.25,
                {"gas": 0.92, "grid": 0.94, "logistics": 0.88, "workforce": 0.95},
            ),
            (
                "stress",
                "Логистический стресс",
                0.20,
                {"gas": 0.48, "grid": 0.79, "logistics": 0.42, "workforce": 0.86},
            ),
        ]
        for scenario_id, name, probability, assumptions in scenarios:
            db.merge(
                Scenario(
                    id=scenario_id,
                    name=name,
                    description=f"Пилотный сценарий: {name.lower()}",
                    probability=probability,
                    assumptions=assumptions,
                    model_version="ammonia-circuit-v0.3",
                )
            )
        db.commit()


if __name__ == "__main__":
    seed()
