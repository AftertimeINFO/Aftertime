"""Dual playback speed, event slowdown rules and timeline run-until."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006_playback_controls"
down_revision: str | None = "0005_scripted_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "idle_speed" in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("lab_runs")}:
        return
    op.add_column("lab_runs", sa.Column("idle_speed", sa.Float(), nullable=False, server_default="3600"))
    op.add_column("lab_runs", sa.Column("event_speed", sa.Float(), nullable=False, server_default="60"))
    op.add_column("lab_runs", sa.Column("event_speed_duration_seconds", sa.Float(), nullable=False, server_default="10"))
    op.add_column("lab_runs", sa.Column("event_speed_event_types", JSONB(), nullable=False, server_default="[]"))
    op.add_column("lab_runs", sa.Column("event_speed_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lab_runs", sa.Column("run_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for column in ["run_until", "event_speed_until", "event_speed_event_types", "event_speed_duration_seconds", "event_speed", "idle_speed"]:
        op.drop_column("lab_runs", column)
