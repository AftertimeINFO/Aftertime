"""Give the Ukraine attack timeline explicit user-facing action labels."""

from collections.abc import Sequence
from copy import deepcopy
import json

import sqlalchemy as sa
from alembic import op

revision: str = "0046_label_ukraine_attacks"
down_revision: str | None = "0045_bind_ukraine_attacks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    labels = [
        ("generation_attack", "Атака на об’єкти генерації"),
        ("substation_attack", "Атака на магістральні підстанції"),
        ("transmission_attack", "Атака на мережу передачі"),
    ]
    row = connection.execute(sa.text(
        "SELECT configuration FROM lab_scenarios WHERE id='ukraine-attacks'"
    )).mappings().first()
    if row:
        configuration = deepcopy(row["configuration"] or {})
        scripts = sorted(configuration.get("script_events", []), key=lambda item: item.get("offset_seconds", 0))
        for item, (event_type, title) in zip(scripts, labels, strict=False):
            item["event_type"] = event_type
            item["title"] = title
        configuration["script_events"] = scripts
        connection.execute(sa.text(
            "UPDATE lab_scenarios SET configuration=CAST(:configuration AS jsonb) WHERE id='ukraine-attacks'"
        ), {"configuration": json.dumps(configuration)})
        templates = connection.execute(sa.text(
            "SELECT id FROM lab_scenario_event_templates WHERE scenario_id='ukraine-attacks' ORDER BY offset_seconds"
        )).scalars().all()
        for template_id, (event_type, title) in zip(templates, labels, strict=False):
            connection.execute(sa.text(
                "UPDATE lab_scenario_event_templates SET event_type=:event_type, title=:title WHERE id=:id"
            ), {"id": template_id, "event_type": event_type, "title": title})


def downgrade() -> None:
    pass
