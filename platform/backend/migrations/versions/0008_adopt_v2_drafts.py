"""Adopt editable legacy drafts into the typed v2 adapter."""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_adopt_v2_drafts"
down_revision: str | None = "0007_typed_model_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE lab_nodes SET instance_key = id WHERE instance_key IS NULL")
    op.execute("UPDATE lab_edges SET connection_key = id WHERE connection_key IS NULL")
    op.execute(
        """
        UPDATE lab_edges
        SET domain = CASE
            WHEN flow_type = 'gas' THEN 'natural_gas'
            WHEN flow_type = 'electricity' THEN 'electric.ac'
            ELSE domain
        END
        """
    )
    op.execute("UPDATE lab_model_versions SET architecture_version = 2 WHERE status = 'draft'")


def downgrade() -> None:
    op.execute("UPDATE lab_model_versions SET architecture_version = 1 WHERE status = 'draft'")
