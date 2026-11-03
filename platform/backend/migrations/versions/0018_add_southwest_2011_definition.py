"""Add the source-backed Southwest Blackout 2011 qualification definition."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0018_add_southwest_2011"
down_revision: str | None = "0017_add_hokkaido_2018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    if "lab_qualification_definitions" not in set(sa.inspect(connection).get_table_names()):
        return
    scenario_id = "southwest-2011"
    model_version_id = "qualification-southwest-2011"
    if not connection.scalar(sa.text("SELECT 1 FROM lab_model_versions WHERE id = :id"), {"id": model_version_id}):
        return
    if connection.scalar(sa.text("SELECT 1 FROM lab_qualification_definitions WHERE model_version_id = :id"), {"id": model_version_id}):
        return

    package = QUALIFICATION_CASES[scenario_id]
    definition = sa.table(
        "lab_qualification_definitions",
        sa.column("id", sa.String),
        sa.column("model_version_id", sa.String),
        sa.column("package_id", sa.String),
        sa.column("scenario_id", sa.String),
        sa.column("revision", sa.Integer),
        sa.column("document", JSONB),
    )
    op.bulk_insert(definition, [{
        "id": "qualification-definition-southwest-2011",
        "model_version_id": model_version_id,
        "package_id": package["id"],
        "scenario_id": scenario_id,
        "revision": 1,
        "document": package,
    }])


def downgrade() -> None:
    connection = op.get_bind()
    if "lab_qualification_definitions" in set(sa.inspect(connection).get_table_names()):
        connection.execute(sa.text("DELETE FROM lab_qualification_definitions WHERE model_version_id = 'qualification-southwest-2011'"))
