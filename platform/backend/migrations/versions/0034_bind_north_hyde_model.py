"""Bind North Hyde 2025 to its own transformer and restoration model."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0034_bind_north_hyde_model"
down_revision: str | None = "0033_fix_iberia_2025_load"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["north-hyde-2025"])


def downgrade() -> None:
    pass
