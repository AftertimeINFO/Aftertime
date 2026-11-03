"""Keep North Hyde runtime failure and repair on the causal SGT3 bushing."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0035_fix_north_hyde_runtime"
down_revision: str | None = "0034_bind_north_hyde_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["north-hyde-2025"])


def downgrade() -> None:
    pass
