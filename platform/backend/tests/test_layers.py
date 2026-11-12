"""Model layers: request routing to the layer database and per-layer write policy."""

import pytest
from fastapi.testclient import TestClient

from app.db import engines, layer_session, session_layer
from app.layers import (
    database_url_for,
    parse_layer,
    queue_item,
    split_queue_item,
    write_denied,
)
from app.main import app

client = TestClient(app)


def test_layer_names():
    assert parse_layer(None) == "dev"
    assert parse_layer("prePROD") == "preprod"
    assert parse_layer("pre-prod") == "preprod"
    with pytest.raises(ValueError):
        parse_layer("qa")


def test_layer_databases_are_separate():
    base = "postgresql+psycopg://u:p@postgres:5432/aftertime"
    assert database_url_for(base, "dev") == base
    assert database_url_for(base, "prod").endswith("/aftertime_prod")
    assert len({str(engine.url) for engine in engines.values()}) == 3
    with layer_session("prod") as session:
        assert session_layer(session) == "prod"


def test_queue_items_carry_the_layer():
    assert split_queue_item(queue_item("dev", "run-1")) == ("dev", "run-1")
    assert split_queue_item(queue_item("preprod", "run-1")) == ("preprod", "run-1")
    assert split_queue_item("legacy-id") == ("dev", "legacy-id")


def test_write_policy():
    assert write_denied("dev", "POST", "/api/v1/lab/projects") is None
    assert write_denied("prod", "GET", "/api/v1/lab/workspace") is None
    assert write_denied("prod", "POST", "/api/v1/lab/projects")
    assert write_denied("preprod", "POST", "/api/v1/lab/runs") is None
    assert write_denied("preprod", "PATCH", "/api/v1/lab/nodes/x")


def test_requests_use_the_layer_header():
    assert client.get("/api/v1/world/version", headers={"X-Aftertime-Layer": "qa"}).status_code == 400
    refused = client.post("/api/v1/lab/projects", json={}, headers={"X-Aftertime-Layer": "prod"})
    assert refused.status_code == 403
    response = client.get("/api/v1/layers", headers={"X-Aftertime-Layer": "prod"})
    assert response.headers["X-Aftertime-Layer"] == "prod"
    assert [item["id"] for item in response.json()["items"]] == ["dev", "preprod", "prod"]
