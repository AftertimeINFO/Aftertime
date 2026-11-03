"""Give event-specific generation technologies distinct physical behavior."""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.lab_seed import EVENT_COMPONENT_PARAMETERS, EVENT_GENERATION_SCRIPT

revision: str = "0025_event_generation_physics"
down_revision: str | None = "0024_bind_southwest_event_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    if "lab_component_types" not in tables:
        return
    for component_id, parameters in EVENT_COMPONENT_PARAMETERS.items():
        current = connection.scalar(
            sa.text("SELECT parameters_schema FROM lab_component_types WHERE id = :id"),
            {"id": component_id},
        ) or {}
        connection.execute(
            sa.text(
                "UPDATE lab_component_types "
                "SET parameters_schema = CAST(:parameters AS jsonb), python_code = :code, version = 3 "
                "WHERE id = :id"
            ),
            {
                "id": component_id,
                "parameters": json.dumps({**current, **parameters}),
                "code": EVENT_GENERATION_SCRIPT,
            },
        )
    if "lab_nodes" in tables:
        connection.execute(
            sa.text(
                "UPDATE lab_nodes SET parameters = parameters || CAST(:parameters AS jsonb) "
                "WHERE model_version_id = 'qualification-southwest-2011' "
                "AND component_type_id = 'nuclear-plant'"
            ),
            {"parameters": json.dumps(EVENT_COMPONENT_PARAMETERS["nuclear-plant"])},
        )


def downgrade() -> None:
    connection = op.get_bind()
    if "lab_component_types" in set(sa.inspect(connection).get_table_names()):
        connection.execute(
            sa.text(
                "UPDATE lab_component_types SET version = 2 "
                "WHERE id IN ('nuclear-plant', 'hydro-plant', 'thermal-plant', 'wind-plant', 'solar-plant')"
            )
        )
