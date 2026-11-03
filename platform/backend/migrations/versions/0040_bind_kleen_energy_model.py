"""Bind Kleen Energy to its own gas-blow and explosion model."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0040_bind_kleen_energy_model"
down_revision: str | None = "0039_fix_storm_arwen_physics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["kleen-energy"])


def downgrade() -> None:
    pass
