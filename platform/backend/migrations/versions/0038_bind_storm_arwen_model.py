"""Bind Storm Arwen to its own tiered distribution and restoration model."""

from collections.abc import Sequence
from copy import deepcopy
import json

import sqlalchemy as sa
from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0038_bind_storm_arwen_model"
down_revision: str | None = "0037_bind_northeast_2003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    row = connection.execute(sa.text(
        "SELECT events, expected, configuration FROM lab_scenarios WHERE id = 'storm-arwen-2021'"
    )).mappings().first()
    if row:
        events = deepcopy(row["events"] or [])
        line_faults = [item for item in events if item.get("event_type") == "line_fault"]
        if len(line_faults) > 1:
            line_faults[1]["event_type"] = "distribution_fault"
        expected = deepcopy(row["expected"] or {})
        expected["required_event_types"] = ["distribution_fault", "line_fault"]
        configuration = deepcopy(row["configuration"] or {})
        script_faults = [item for item in configuration.get("script_events", []) if item.get("event_type") == "line_fault"]
        if len(script_faults) > 1:
            script_faults[1]["event_type"] = "distribution_fault"
        connection.execute(sa.text(
            "UPDATE lab_scenarios SET events = CAST(:events AS jsonb), expected = CAST(:expected AS jsonb), configuration = CAST(:configuration AS jsonb) WHERE id = 'storm-arwen-2021'"
        ), {"events": json.dumps(events), "expected": json.dumps(expected), "configuration": json.dumps(configuration)})
        connection.execute(sa.text(
            "UPDATE lab_scenario_event_templates SET event_type = 'distribution_fault' WHERE scenario_id = 'storm-arwen-2021' AND target_node_id LIKE '%distribution' AND event_type = 'line_fault'"
        ))
    materialize_event_model(connection, QUALIFICATION_CASES["storm-arwen-2021"])


def downgrade() -> None:
    pass
