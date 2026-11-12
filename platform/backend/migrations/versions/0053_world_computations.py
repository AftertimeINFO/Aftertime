"""World computations: how far the world ledger is computed, and forecast provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0053_world_computations"
down_revision: str | None = "0052_layer_promotions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_events_provenance", "events", type_="check")
    op.create_check_constraint(
        "ck_events_provenance",
        "events",
        "provenance IN ('statistic', 'derived', 'assumed', 'forecast')",
    )
    op.create_table(
        "world_computations",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("run_id", sa.String(80), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("data_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("history_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parameters", JSONB, nullable=False, server_default="{}"),
        sa.Column("summary", JSONB, nullable=False, server_default="{}"),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("world_computations")
    op.execute("DELETE FROM events WHERE provenance = 'forecast'")
    op.drop_constraint("ck_events_provenance", "events", type_="check")
    op.create_check_constraint(
        "ck_events_provenance", "events", "provenance IN ('statistic', 'derived', 'assumed')"
    )
