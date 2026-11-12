"""History of model promotions between layers (DEV → prePROD → PROD)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0052_layer_promotions"
down_revision: str | None = "0051_world_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "layer_promotions",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("version_id", sa.String(80), nullable=False, index=True),
        sa.Column("project_id", sa.String(80), nullable=False, index=True),
        sa.Column("source_layer", sa.String(20), nullable=False),
        sa.Column("target_layer", sa.String(20), nullable=False),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column("summary", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("layer_promotions")
