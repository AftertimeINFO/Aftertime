"""Promotion of model versions DEV → prePROD → PROD.

The real prePROD and PROD databases are not touched: the test promotes into two
throw-away databases, and every write to DEV (the promotion history) is rolled back.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import models  # noqa: F401 - registers every table
from app.config import settings
from app.db import Base, engines
from app.layers import write_denied
from app.main import app
from app.models import Entity, LabModelVersion, LabNode, LabProject, LabRun, LabScenario, LayerPromotion
from app.services.promotion import PromotionError, collect, plan_promotion, promote

VERSION = "qualification-storm-arwen-2021"


@pytest.fixture(scope="module")
def layer_dbs():
    """Two empty databases with the current schema, standing in for prePROD and PROD."""
    base = make_url(settings.database_url)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    names = {"preprod": f"{base.database}_test_promo_preprod", "prod": f"{base.database}_test_promo_prod"}
    created = {}
    with admin.connect() as connection:
        for layer, name in names.items():
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    for layer, name in names.items():
        engine = create_engine(base.set(database=name))
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            Base.metadata.create_all(connection)
        created[layer] = engine
    yield created
    for engine in created.values():
        engine.dispose()
    with admin.connect() as connection:
        for name in names.values():
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture()
def dev():
    """A DEV session whose commits are rolled back at the end of the test."""
    connection = engines["dev"].connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    outer.rollback()
    connection.close()


def count(session: Session, model, *where) -> int:
    return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


def test_bundle_holds_everything_a_run_needs(dev):
    bundle = collect(dev, VERSION)
    assert VERSION in bundle["lab_model_versions"]
    # Participant models of the assembly come along with the composite model.
    assert len(bundle["lab_model_versions"]) > 1
    assert bundle["lab_scenarios"] == {"storm-arwen-2021"}
    for table in ("lab_nodes", "lab_edges", "lab_scenario_assembly_members", "lab_workflow_versions", "lab_component_types", "entities"):
        assert bundle.get(table), table
    # Runs are evidence of a layer and never travel.
    assert not any(name.startswith("lab_run") for name in bundle)


def test_only_adjacent_layers(dev, layer_dbs):
    with Session(layer_dbs["prod"]) as target:
        with pytest.raises(PromotionError) as error:
            plan_promotion(dev, target, VERSION, "dev", "prod")
        assert error.value.status == 422
    with Session(layer_dbs["preprod"]) as target, pytest.raises(PromotionError):
        plan_promotion(dev, target, "no-such-version", "dev", "preprod")


def test_promotion_ladder(dev, layer_dbs):
    pre = Session(layer_dbs["preprod"])
    prod = Session(layer_dbs["prod"])
    try:
        # The plan writes nothing.
        plan = plan_promotion(dev, pre, VERSION, "dev", "preprod")
        assert plan["status"] == "ready" and plan["totals"]["new"] > 0
        assert count(pre, LabModelVersion) == 0

        result = promote(dev, pre, VERSION, "dev", "preprod", "перша валідація")
        assert result["status"] == "promoted"
        assert count(pre, LabNode, LabNode.model_version_id == VERSION) == count(dev, LabNode, LabNode.model_version_id == VERSION)
        scenario = pre.get(LabScenario, "storm-arwen-2021")
        assert scenario.assembly_version_id == dev.get(LabScenario, "storm-arwen-2021").assembly_version_id
        project = pre.get(LabProject, pre.get(LabModelVersion, VERSION).project_id)
        assert project.published_version_id == VERSION and project.active_draft_id is None
        # Both layers remember the promotion.
        assert count(pre, LayerPromotion, LayerPromotion.version_id == VERSION) == 1
        assert count(dev, LayerPromotion, LayerPromotion.id == result["promotion"]) == 1

        # Promoting again copies nothing.
        assert promote(dev, pre, VERSION, "dev", "preprod")["status"] == "already"

        # Re-validation in prePROD is not a change of the model…
        pre.execute(update(LabModelVersion).where(LabModelVersion.id == VERSION).values(validation={"valid": True, "rerun": 1}))
        # …and the target layer owns its world entities.
        entity_id = next(iter(collect(dev, VERSION)["entities"]))
        pre.execute(update(Entity).where(Entity.id == entity_id).values(name="Уточнено в prePROD"))
        pre.commit()
        plan = plan_promotion(dev, pre, VERSION, "dev", "preprod")
        assert plan["status"] == "already" and plan["totals"]["kept"] == 1

        # A model edited in prePROD is a conflict and blocks the promotion.
        node_id = pre.scalar(select(LabNode.id).where(LabNode.model_version_id == VERSION).limit(1))
        pre.execute(update(LabNode).where(LabNode.id == node_id).values(name="змінено"))
        pre.commit()
        plan = plan_promotion(dev, pre, VERSION, "dev", "preprod")
        assert plan["status"] == "blocked"
        assert plan["conflicts"][0]["id"] == node_id and plan["conflicts"][0]["columns"] == ["name"]
        with pytest.raises(PromotionError) as error:
            promote(dev, pre, VERSION, "dev", "preprod")
        assert error.value.status == 409
        pre.execute(update(LabNode).where(LabNode.id == node_id).values(name=dev.get(LabNode, node_id).name))
        pre.commit()

        # PROD needs a completed run in prePROD.
        plan = plan_promotion(pre, prod, VERSION, "preprod", "prod")
        assert plan["status"] == "blocked"
        assert next(c for c in plan["checks"] if c["id"] == "validated")["ok"] is False
        start = datetime(2021, 11, 26, tzinfo=UTC)
        pre.add(LabRun(id="test-run", model_version_id=VERSION, scenario_id="storm-arwen-2021", status="completed", current_time=start + timedelta(days=1), end_time=start + timedelta(days=1)))
        pre.commit()
        result = promote(pre, prod, VERSION, "preprod", "prod")
        assert result["status"] == "promoted"
        assert count(prod, LabNode, LabNode.model_version_id == VERSION) == count(pre, LabNode, LabNode.model_version_id == VERSION)
        # The run itself stays in prePROD.
        assert count(prod, LabRun) == 0
        # The entity refined in prePROD reaches PROD as refined.
        assert prod.get(Entity, entity_id).name == "Уточнено в prePROD"
    finally:
        pre.close()
        prod.close()


def test_api_and_policy():
    client = TestClient(app)
    assert write_denied("prod", "POST", "/api/v1/promotions") is None
    layers = {item["id"]: item for item in client.get("/api/v1/layers").json()["items"]}
    assert "promote" in layers["dev"]["capabilities"] and "promote" in layers["preprod"]["capabilities"]
    assert "promote" not in layers["prod"]["capabilities"]
    response = client.get("/api/v1/promotions", headers={"X-Aftertime-Layer": "dev"})
    assert response.status_code == 200
    body = response.json()
    assert body["target"] == "preprod"
    assert any(item["id"] == VERSION for item in body["items"])
    assert client.get("/api/v1/promotions", headers={"X-Aftertime-Layer": "prod"}).json()["target"] is None
    assert client.post("/api/v1/promotions", json={"version_id": VERSION}, headers={"X-Aftertime-Layer": "prod"}).status_code == 422
