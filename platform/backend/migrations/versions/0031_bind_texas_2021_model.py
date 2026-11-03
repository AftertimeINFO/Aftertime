"""Bind Texas 2021 to its own fuel and power event model."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0031_bind_texas_2021_model"
down_revision: str | None = "0030_bind_india_2012_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["texas-2021"])


def downgrade() -> None:
    pass
