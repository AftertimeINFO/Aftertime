"""Add the strict Ukraine-Moldova 2026 package and bind its own model."""

from collections.abc import Sequence
from copy import deepcopy
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0043_bind_ua_md_2026_model"
down_revision: str | None = "0042_fix_macondo_process"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    package = QUALIFICATION_CASES["ua-md-2026"]
    model_id = package["model"]["id"]
    tables = set(sa.inspect(connection).get_table_names())
    if "lab_qualification_definitions" not in tables:
        return
    if not connection.scalar(sa.text(
        "SELECT 1 FROM lab_model_versions WHERE id=:id"
    ), {"id": model_id}):
        connection.execute(sa.text(
            "INSERT INTO lab_model_versions "
            "(id, project_id, version, status, name, timezone, settings, validation, architecture_version, semantic_revision, published_at) "
            "SELECT :id, p.id, COALESCE((SELECT max(version) + 1 FROM lab_model_versions WHERE project_id=p.id), 1), "
            "'published', :name, 'Europe/Kyiv', '{}'::jsonb, '{}'::jsonb, 2, 0, now() "
            "FROM lab_projects p WHERE p.id='model-lab-energy'"
        ), {"id": model_id, "name": "Кваліфікаційна модель · Україна–Молдова, 31.01.2026"})
        connection.execute(sa.text(
            "UPDATE lab_scenarios SET model_version_id=:id WHERE id='ua-md-2026'"
        ), {"id": model_id})
    if not connection.scalar(sa.text(
        "SELECT 1 FROM lab_model_versions WHERE id=:id"
    ), {"id": model_id}):
        return
    row = connection.execute(sa.text(
        "SELECT events, expected, configuration FROM lab_scenarios WHERE id = 'ua-md-2026'"
    )).mappings().first()
    if row:
        events = deepcopy(row["events"] or [])
        trip_index = 0
        for item in events:
            if item.get("event_type") == "trip":
                item["event_type"] = "interconnector_trip" if trip_index == 0 else "corridor_trip"
                trip_index += 1
            elif item.get("event_type") == "black_start":
                item["event_type"] = "restore"
        configuration = deepcopy(row["configuration"] or {})
        trip_index = 0
        for item in configuration.get("script_events", []):
            if item.get("event_type") == "trip":
                item["event_type"] = "interconnector_trip" if trip_index == 0 else "corridor_trip"
                trip_index += 1
            elif item.get("event_type") == "black_start":
                item["event_type"] = "restore"
        expected = deepcopy(row["expected"] or {})
        expected["required_event_types"] = ["corridor_trip", "interconnector_trip", "restore", "resynchronize"]
        connection.execute(sa.text(
            "UPDATE lab_scenarios SET events=CAST(:events AS jsonb), expected=CAST(:expected AS jsonb), configuration=CAST(:configuration AS jsonb) WHERE id='ua-md-2026'"
        ), {"events": json.dumps(events), "expected": json.dumps(expected), "configuration": json.dumps(configuration)})
        connection.execute(sa.text(
            "UPDATE lab_scenario_event_templates SET event_type = CASE "
            "WHEN event_type='trip' AND target_node_id='p-hv-line' THEN 'interconnector_trip' "
            "WHEN event_type='trip' THEN 'corridor_trip' WHEN event_type='black_start' THEN 'restore' ELSE event_type END "
            "WHERE scenario_id='ua-md-2026'"
        ))
    if not connection.scalar(sa.text(
        "SELECT 1 FROM lab_qualification_definitions WHERE model_version_id=:id"
    ), {"id": model_id}):
        definition = sa.table(
            "lab_qualification_definitions", sa.column("id", sa.String),
            sa.column("model_version_id", sa.String), sa.column("package_id", sa.String),
            sa.column("scenario_id", sa.String), sa.column("revision", sa.Integer),
            sa.column("document", JSONB),
        )
        op.bulk_insert(definition, [{"id": "qualification-definition-ua-md-2026", "model_version_id": model_id, "package_id": package["id"], "scenario_id": package["scenario_id"], "revision": 1, "document": package}])
    materialize_event_model(connection, package)


def downgrade() -> None:
    pass
