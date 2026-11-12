"""Model layers: DEV, prePROD and PROD, each backed by its own PostgreSQL database.

* DEV — simplified, restricted modelling and model debugging (the original database);
* prePROD — validation of models on real data before they are promoted to PROD;
* PROD — the global model with real data and structures; read-only for Model Lab.

The active layer of a request comes from the ``X-Aftertime-Layer`` header (or the
``layer`` query parameter) and is kept in a context variable, so ``get_db`` and the
job queues use the database of that layer.
"""

from contextvars import ContextVar
from typing import Literal

from sqlalchemy.engine import make_url

Layer = Literal["dev", "preprod", "prod"]
LAYERS: tuple[Layer, ...] = ("dev", "preprod", "prod")
DEFAULT_LAYER: Layer = "dev"
HEADER = "X-Aftertime-Layer"

current_layer: ContextVar[Layer] = ContextVar("aftertime_layer", default=DEFAULT_LAYER)

# What each layer allows. The frontend reads this through GET /api/v1/layers.
LAYER_POLICY: dict[Layer, dict] = {
    "dev": {
        "label": "DEV",
        "description": "Спрощене моделювання та відладка моделей",
        "capabilities": ["balance", "world", "lab.edit", "lab.run", "qualification", "data"],
    },
    "preprod": {
        "label": "prePROD",
        "description": "Валідація моделей на реальних даних перед PROD",
        "capabilities": ["balance", "world", "lab.run", "qualification", "data"],
    },
    "prod": {
        "label": "PROD",
        "description": "Глобальна модель з реальними даними та структурами",
        "capabilities": ["balance", "world", "data"],
    },
}

# Model Lab writes that are not edits of the model itself: running and validating.
LAB_RUN_PATHS = ("/runs", "/validate", "/qualification", "/debug", "/test")


def parse_layer(value: str | None) -> Layer:
    """Normalise a layer name; raises ValueError for an unknown one."""
    if value is None or value == "":
        return DEFAULT_LAYER
    normalised = value.strip().lower().replace("-", "")
    if normalised not in LAYERS:
        raise ValueError(f"Невідомий шар {value!r}; очікується один із: dev, preprod, prod")
    return normalised  # type: ignore[return-value]


def write_denied(layer: Layer, method: str, path: str) -> str | None:
    """Reason a request is refused in this layer, or None when it is allowed."""
    if method in {"GET", "HEAD", "OPTIONS"} or not path.startswith("/api/v1/lab"):
        return None
    capabilities = LAYER_POLICY[layer]["capabilities"]
    if "lab.edit" in capabilities:
        return None
    if "lab.run" in capabilities and any(part in path for part in LAB_RUN_PATHS):
        return None
    label = LAYER_POLICY[layer]["label"]
    if "lab.run" in capabilities:
        return f"У шарі {label} модель не редагується: доступні лише запуски та перевірки"
    return f"Шар {label} доступний лише для читання"


def database_url_for(base_url: str, layer: Layer) -> str:
    """Default database URL of a layer: DEV keeps the base database, others get a suffix."""
    if layer == "dev":
        return base_url
    url = make_url(base_url)
    return url.set(database=f"{url.database}_{layer}").render_as_string(hide_password=False)


def queue_item(layer: Layer, job_id: str) -> str:
    return job_id if layer == DEFAULT_LAYER else f"{layer}:{job_id}"


def split_queue_item(item: str) -> tuple[Layer, str]:
    """Inverse of queue_item; items without a prefix (older jobs) belong to DEV."""
    head, sep, tail = item.partition(":")
    if sep and head in LAYERS:
        return head, tail  # type: ignore[return-value]
    return DEFAULT_LAYER, item


def ensure_databases() -> None:
    """Create missing layer databases and the PostGIS extension in each. Idempotent."""
    from sqlalchemy import create_engine, text

    from app.config import settings

    for layer, url in settings.layer_urls.items():
        target = make_url(url)
        admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            ).first()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{target.database}"'))
                print(f"created database {target.database} for layer {layer}")
        admin.dispose()
        engine = create_engine(target, isolation_level="AUTOCOMMIT")
        with engine.connect() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        engine.dispose()


EVENT_BALANCES_VIEW = """
CREATE OR REPLACE VIEW event_balances AS
SELECT p.event_id, p.property, p.unit, sum(p.delta) AS net, count(*) AS postings
FROM postings p
GROUP BY p.event_id, p.property, p.unit
"""


def bootstrap_empty(url: str) -> bool:
    """Give an empty layer database the current schema and stamp it at alembic head.

    The historical migration chain cannot build a database from nothing (its first
    revision creates tables from the current models, later ones create them again),
    so a new layer database starts from the models and only later revisions apply.
    Returns True when the database was bootstrapped.
    """
    import os
    import subprocess

    from sqlalchemy import create_engine, inspect, text

    from app import models  # noqa: F401 - registers every table on Base.metadata
    from app.db import Base

    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        if "alembic_version" in tables or "entities" in tables:
            return False
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            Base.metadata.create_all(connection)
            connection.execute(text(EVENT_BALANCES_VIEW))
    finally:
        engine.dispose()
    # migrations/env.py reads the URL from settings, so stamp in a child process.
    subprocess.run(
        ["alembic", "stamp", "head"], env={**os.environ, "DATABASE_URL": url}, check=True
    )
    return True


if __name__ == "__main__":
    import sys

    from app.config import settings

    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "ensure":
        ensure_databases()
        for name, value in settings.layer_urls.items():
            if bootstrap_empty(value):
                print(f"bootstrapped empty database of layer {name} at alembic head")
    elif command == "urls":
        # One "layer url" pair per line, for the shell entrypoint.
        for name, value in settings.layer_urls.items():
            print(name, value)
    else:
        raise SystemExit("usage: python -m app.layers ensure|urls")
