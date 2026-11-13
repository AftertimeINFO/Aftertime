"""ODbL grid layer: OSM power assets, overrides, topology snapshots, scenarios and runs.

The tables live in the separate ``odbl`` schema (docs/en/design/MATTER_FLOW_AND_LOCATIONS.md
section 7.1). They are created from app.grid.models with ``checkfirst``; later revisions
that change these tables must use ``IF NOT EXISTS`` / ``IF EXISTS`` forms so that a database
which reaches this revision late still upgrades cleanly.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0055_odbl_grid"
down_revision: str | None = "0054_extract_event_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from app.db import Base
    from app.grid import models as grid  # noqa: F401 - registers the tables

    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE SCHEMA IF NOT EXISTS odbl")
    tables = [t for t in Base.metadata.sorted_tables if t.schema == "odbl"]
    Base.metadata.create_all(op.get_bind(), tables=tables, checkfirst=True)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_grid_assets_name_trgm ON odbl.grid_assets "
        "USING gin (lower(coalesce(name, '') || ' ' || coalesce(name_en, '') || ' ' "
        "|| coalesce(ref, '')) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS odbl CASCADE")
