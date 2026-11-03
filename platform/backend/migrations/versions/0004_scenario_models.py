"""Bind every qualification scenario to its own immutable model snapshot."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_scenario_models"
down_revision: str | None = "0003_lab_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Older revisions used current metadata in 0001. On a clean install that may
    # already contain this revision's columns; keep replay safe until 0001 is frozen.
    if "model_version_id" in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("lab_scenarios")}:
        return
    op.add_column("lab_scenarios", sa.Column("model_version_id", sa.String(80), nullable=True))
    op.create_index("ix_lab_scenarios_model_version_id", "lab_scenarios", ["model_version_id"])
    op.create_foreign_key("fk_lab_scenario_model", "lab_scenarios", "lab_model_versions", ["model_version_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_lab_scenario_model", "lab_scenarios", type_="foreignkey")
    op.drop_index("ix_lab_scenarios_model_version_id", table_name="lab_scenarios")
    op.drop_column("lab_scenarios", "model_version_id")
