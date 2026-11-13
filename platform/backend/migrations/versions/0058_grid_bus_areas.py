"""Grid buses remember the control areas they lie in, so a run can follow occupation and
liberation by date instead of fixing the territory at the snapshot date.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0058_grid_bus_areas"
down_revision: str | None = "0057_grid_control_areas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE odbl.grid_buses ADD COLUMN IF NOT EXISTS areas integer[]")


def downgrade() -> None:
    op.execute("ALTER TABLE odbl.grid_buses DROP COLUMN IF EXISTS areas")
