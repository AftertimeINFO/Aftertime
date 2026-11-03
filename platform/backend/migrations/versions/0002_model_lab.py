"""Territory-free Model Lab schema."""

from collections.abc import Sequence
from alembic import op
from app.db import Base
from app import models  # noqa: F401

revision: str = "0002_model_lab"
down_revision: str | None = "0001_initial_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    for table in ["lab_component_tests", "lab_checkpoints", "lab_run_events", "lab_runs", "lab_scenarios", "lab_edges", "lab_nodes", "lab_component_types", "lab_model_versions", "lab_projects"]:
        op.drop_table(table)
