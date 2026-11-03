"""Store strict qualification definitions with their model versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.qualification_cases import QUALIFICATION_CASES

revision: str = "0011_qualification_defs"
down_revision: str | None = "0010_split_san_bruno"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "lab_qualification_definitions" not in tables:
        op.create_table(
            "lab_qualification_definitions",
            sa.Column("id", sa.String(80), primary_key=True),
            sa.Column(
                "model_version_id",
                sa.String(80),
                sa.ForeignKey("lab_model_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("package_id", sa.String(100), nullable=False),
            sa.Column("scenario_id", sa.String(100), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("document", JSONB(), nullable=False, server_default="{}"),
            sa.UniqueConstraint("model_version_id"),
            sa.UniqueConstraint(
                "model_version_id",
                "package_id",
                name="uq_lab_qualification_definition_package",
            ),
        )
        op.create_index(
            "ix_lab_qualification_definitions_model_version_id",
            "lab_qualification_definitions",
            ["model_version_id"],
        )
        op.create_index(
            "ix_lab_qualification_definitions_package_id",
            "lab_qualification_definitions",
            ["package_id"],
        )
        op.create_index(
            "ix_lab_qualification_definitions_scenario_id",
            "lab_qualification_definitions",
            ["scenario_id"],
        )

    connection = op.get_bind()
    versions = {
        "san-bruno-2010": "qualification-san-bruno-2010",
        "northeast-2003": "qualification-northeast-2003",
        "storm-arwen-2021": "qualification-storm-arwen-2021",
    }
    definition = sa.table(
        "lab_qualification_definitions",
        sa.column("id", sa.String),
        sa.column("model_version_id", sa.String),
        sa.column("package_id", sa.String),
        sa.column("scenario_id", sa.String),
        sa.column("revision", sa.Integer),
        sa.column("document", JSONB),
    )
    for scenario_id, version_id in versions.items():
        exists = connection.scalar(
            sa.text("SELECT 1 FROM lab_model_versions WHERE id = :id"),
            {"id": version_id},
        )
        already = connection.scalar(
            sa.text(
                "SELECT 1 FROM lab_qualification_definitions "
                "WHERE model_version_id = :id"
            ),
            {"id": version_id},
        )
        if exists and not already:
            package = QUALIFICATION_CASES[scenario_id]
            op.bulk_insert(
                definition,
                [
                    {
                        "id": f"qualification-definition-{scenario_id}",
                        "model_version_id": version_id,
                        "package_id": package["id"],
                        "scenario_id": scenario_id,
                        "revision": 1,
                        "document": package,
                    }
                ],
            )


def downgrade() -> None:
    if "lab_qualification_definitions" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("lab_qualification_definitions")
