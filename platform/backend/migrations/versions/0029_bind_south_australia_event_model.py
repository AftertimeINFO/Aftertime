"""Bind South Australia 2016 to its own event-specific L1 model."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0029_bind_sa_2016_model"
down_revision: str | None = "0028_fix_gb_2019_operating_point"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["south-australia-2016"])


def downgrade() -> None:
    pass
