"""Grid topology: every OSM way of a branch, and the role of a bus.

A transmission line between two substations is usually split in OpenStreetMap into many
ways; the branch keeps all of them so a simulation can colour the whole line on the map.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0056_grid_topology_columns"
down_revision: str | None = "0055_odbl_grid"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE odbl.grid_branches ADD COLUMN IF NOT EXISTS asset_ids bigint[] "
        "NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE odbl.grid_buses ADD COLUMN IF NOT EXISTS role varchar(20) "
        "NOT NULL DEFAULT 'substation'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_grid_branches_asset_ids ON odbl.grid_branches "
        "USING gin (asset_ids)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE odbl.grid_branches DROP COLUMN IF EXISTS asset_ids")
    op.execute("ALTER TABLE odbl.grid_buses DROP COLUMN IF EXISTS role")
