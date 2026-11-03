"""Give both Ukraine-Moldova line trips and restoration distinct targets."""

from collections.abc import Sequence
from copy import deepcopy
import json

import sqlalchemy as sa
from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0044_fix_ua_md_runtime"
down_revision: str | None = "0043_bind_ua_md_2026_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    row = connection.execute(sa.text(
        "SELECT events, expected, configuration FROM lab_scenarios WHERE id='ua-md-2026'"
    )).mappings().first()
    if row:
        events = sorted(deepcopy(row["events"] or []), key=lambda item: item.get("at", ""))
        configuration = deepcopy(row["configuration"] or {})
        scripts = sorted(configuration.get("script_events", []), key=lambda item: item.get("offset_seconds", 0))
        event_types = ["interconnector_trip", "corridor_trip", "restore", "resynchronize"]
        for item, event_type in zip(events, event_types, strict=False):
            item["event_type"] = event_type
        for item, event_type in zip(scripts, event_types, strict=False):
            item["event_type"] = event_type
        configuration["script_events"] = scripts
        expected = deepcopy(row["expected"] or {})
        expected["required_event_types"] = sorted(event_types)
        connection.execute(sa.text(
            "UPDATE lab_scenarios SET events=CAST(:events AS jsonb), expected=CAST(:expected AS jsonb), configuration=CAST(:configuration AS jsonb) WHERE id='ua-md-2026'"
        ), {"events": json.dumps(events), "expected": json.dumps(expected), "configuration": json.dumps(configuration)})
        templates = connection.execute(sa.text(
            "SELECT id FROM lab_scenario_event_templates WHERE scenario_id='ua-md-2026' ORDER BY offset_seconds"
        )).scalars().all()
        for template_id, event_type in zip(templates, event_types, strict=False):
            connection.execute(sa.text(
                "UPDATE lab_scenario_event_templates SET event_type=:event_type WHERE id=:id"
            ), {"id": template_id, "event_type": event_type})
    materialize_event_model(connection, QUALIFICATION_CASES["ua-md-2026"])


def downgrade() -> None:
    pass
