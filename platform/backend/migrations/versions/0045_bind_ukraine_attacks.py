"""Add the strict Ukraine energy-attacks package and its aggregate topology."""

from collections.abc import Sequence
from copy import deepcopy
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0045_bind_ukraine_attacks"
down_revision: str | None = "0044_fix_ua_md_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    package = QUALIFICATION_CASES["ukraine-attacks"]
    model_id = package["model"]["id"]
    tables = set(sa.inspect(connection).get_table_names())
    if "lab_qualification_definitions" not in tables:
        return
    row = connection.execute(sa.text(
        "SELECT events, expected, configuration FROM lab_scenarios WHERE id='ukraine-attacks'"
    )).mappings().first()
    event_types = ["generation_attack", "substation_attack", "transmission_attack"]
    if row:
        events = sorted(deepcopy(row["events"] or []), key=lambda item: item.get("at", ""))
        configuration = deepcopy(row["configuration"] or {})
        scripts = sorted(configuration.get("script_events", []), key=lambda item: item.get("offset_seconds", 0))
        for item, event_type in zip(events, event_types, strict=False):
            item["event_type"] = event_type
        for item, event_type in zip(scripts, event_types, strict=False):
            item["event_type"] = event_type
        configuration["script_events"] = scripts
        expected = deepcopy(row["expected"] or {})
        expected["required_event_types"] = sorted(event_types)
        connection.execute(sa.text(
            "UPDATE lab_scenarios SET events=CAST(:events AS jsonb), expected=CAST(:expected AS jsonb), configuration=CAST(:configuration AS jsonb) WHERE id='ukraine-attacks'"
        ), {"events": json.dumps(events), "expected": json.dumps(expected), "configuration": json.dumps(configuration)})
        templates = connection.execute(sa.text(
            "SELECT id FROM lab_scenario_event_templates WHERE scenario_id='ukraine-attacks' ORDER BY offset_seconds"
        )).scalars().all()
        for template_id, event_type in zip(templates, event_types, strict=False):
            connection.execute(sa.text("UPDATE lab_scenario_event_templates SET event_type=:event_type WHERE id=:id"), {"id": template_id, "event_type": event_type})
    if not connection.scalar(sa.text("SELECT 1 FROM lab_model_versions WHERE id=:id"), {"id": model_id}):
        return
    if not connection.scalar(sa.text("SELECT 1 FROM lab_qualification_definitions WHERE model_version_id=:id"), {"id": model_id}):
        definition = sa.table(
            "lab_qualification_definitions", sa.column("id", sa.String), sa.column("model_version_id", sa.String),
            sa.column("package_id", sa.String), sa.column("scenario_id", sa.String), sa.column("revision", sa.Integer),
            sa.column("document", JSONB),
        )
        op.bulk_insert(definition, [{"id": "qualification-definition-ukraine-attacks", "model_version_id": model_id, "package_id": package["id"], "scenario_id": package["scenario_id"], "revision": 1, "document": package}])
    materialize_event_model(connection, package)


def downgrade() -> None:
    pass
