"""Refresh Macondo after removing an invalid cross-process predecessor."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0042_fix_macondo_process"
down_revision: str | None = "0041_bind_macondo_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["macondo"])


def downgrade() -> None:
    pass
