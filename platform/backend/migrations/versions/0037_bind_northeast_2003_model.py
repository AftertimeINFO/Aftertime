"""Bind Northeast 2003 to its own cascade and islanding model."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0037_bind_northeast_2003"
down_revision: str | None = "0036_bind_san_bruno_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["northeast-2003"])


def downgrade() -> None:
    pass
