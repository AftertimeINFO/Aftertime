"""Bind Iberia 2025 to its own renewable and interconnection model."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0032_bind_iberia_2025_model"
down_revision: str | None = "0031_bind_texas_2021_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["iberia-2025"])


def downgrade() -> None:
    pass
