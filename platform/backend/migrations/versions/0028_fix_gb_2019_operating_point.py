"""Give the GB 2019 event model an explicit L1 demand operating point."""

from collections.abc import Sequence

from alembic import op

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0028_fix_gb_2019_operating_point"
down_revision: str | None = "0027_bind_gb_2019_event_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    materialize_event_model(op.get_bind(), QUALIFICATION_CASES["gb-2019"])


def downgrade() -> None:
    # The preceding migration can rematerialize topology revision 1 when a
    # complete downgrade is requested.  Avoid partially rewriting JSON here.
    pass
