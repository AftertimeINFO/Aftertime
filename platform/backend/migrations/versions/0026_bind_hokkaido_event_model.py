"""Bind Hokkaido 2018 to its own event-specific L1 model."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0026_bind_hokkaido_event_model"
down_revision: str | None = "0025_event_generation_physics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["hokkaido-2018"])


def downgrade() -> None:
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    if "lab_edges" in tables:
        connection.execute(sa.text("DELETE FROM lab_edges WHERE model_version_id = 'qualification-hokkaido-2018'"))
    if "lab_nodes" in tables:
        connection.execute(sa.text("DELETE FROM lab_nodes WHERE model_version_id = 'qualification-hokkaido-2018'"))
