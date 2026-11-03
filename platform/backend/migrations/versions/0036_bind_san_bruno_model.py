"""Bind San Bruno 2010 to its own gas transmission and response model."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0036_bind_san_bruno_model"
down_revision: str | None = "0035_fix_north_hyde_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["san-bruno-2010"])


def downgrade() -> None:
    pass
