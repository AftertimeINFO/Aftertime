"""Grid control areas: territory outside the operator's control from a date (occupation).

Assets inside an area on the snapshot date leave the national demand and supply.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0057_grid_control_areas"
down_revision: str | None = "0056_grid_topology_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS odbl.grid_control_areas (
            id serial PRIMARY KEY,
            name text NOT NULL UNIQUE,
            country varchar(8) NOT NULL,
            controlled_by varchar(16) NOT NULL,
            valid_from date NOT NULL,
            valid_to date,
            geom geometry(Geometry, 4326),
            source_url text NOT NULL,
            note text NOT NULL DEFAULT ''
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_grid_control_areas_geom ON odbl.grid_control_areas "
        "USING gist (geom)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS odbl.grid_control_areas")
