"""Add the strict Macondo package and bind its offshore blowout model."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.event_model_materializer import materialize_event_model
from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0041_bind_macondo_model"
down_revision: str | None = "0040_bind_kleen_energy_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    package = QUALIFICATION_CASES["macondo"]
    model_id = package["model"]["id"]
    tables = set(sa.inspect(connection).get_table_names())
    if "lab_qualification_definitions" not in tables or not connection.scalar(
        sa.text("SELECT 1 FROM lab_model_versions WHERE id = :id"), {"id": model_id}
    ):
        return
    if not connection.scalar(sa.text(
        "SELECT 1 FROM lab_qualification_definitions WHERE model_version_id = :id"
    ), {"id": model_id}):
        definition = sa.table(
            "lab_qualification_definitions",
            sa.column("id", sa.String), sa.column("model_version_id", sa.String),
            sa.column("package_id", sa.String), sa.column("scenario_id", sa.String),
            sa.column("revision", sa.Integer), sa.column("document", JSONB),
        )
        op.bulk_insert(definition, [{
            "id": "qualification-definition-macondo",
            "model_version_id": model_id,
            "package_id": package["id"],
            "scenario_id": package["scenario_id"],
            "revision": 1,
            "document": package,
        }])
    materialize_event_model(connection, package)


def downgrade() -> None:
    pass
