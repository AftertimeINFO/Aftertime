"""Give Storm Arwen distinct feeder failures and an energized upstream source."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0039_fix_storm_arwen_physics"
down_revision: str | None = "0038_bind_storm_arwen_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["storm-arwen-2021"])


def downgrade() -> None:
    pass
