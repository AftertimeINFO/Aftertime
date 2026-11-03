"""Add versioned event programs and ordered event actions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0009_event_designer"
down_revision: str | None = "0008_adopt_v2_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "lab_event_programs" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "lab_event_programs",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column(
            "model_version_id",
            sa.String(80),
            sa.ForeignKey("lab_model_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_type_id",
            sa.String(100),
            sa.ForeignKey("lab_event_types.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("layout", JSONB(), nullable=False, server_default="{}"),
        sa.UniqueConstraint(
            "model_version_id", "event_type_id", name="uq_lab_event_program_type"
        ),
    )
    op.create_index(
        "ix_lab_event_programs_model_version_id",
        "lab_event_programs",
        ["model_version_id"],
    )
    op.create_index(
        "ix_lab_event_programs_event_type_id",
        "lab_event_programs",
        ["event_type_id"],
    )

    op.create_table(
        "lab_event_actions",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column(
            "program_id",
            sa.String(80),
            sa.ForeignKey("lab_event_programs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(60), nullable=False),
        sa.Column("target_kind", sa.String(30), nullable=True),
        sa.Column("target_id", sa.String(80), nullable=True),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("x", sa.Float(), nullable=False, server_default="0"),
        sa.Column("y", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "program_id", "sequence", name="uq_lab_event_action_sequence"
        ),
    )
    op.create_index(
        "ix_lab_event_actions_program_id", "lab_event_actions", ["program_id"]
    )
    op.create_index(
        "ix_lab_event_actions_action_type", "lab_event_actions", ["action_type"]
    )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "lab_event_actions" in tables:
        op.drop_table("lab_event_actions")
    if "lab_event_programs" in tables:
        op.drop_table("lab_event_programs")
