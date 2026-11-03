"""Materialize structured situation rules as FEEL expressions in DMN XML."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.qualification_cases import canonicalize_qualification_package

revision: str = "0014_materialize_dmn_rules"
down_revision: str | None = "0013_fill_draft_monitors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    if "lab_qualification_definitions" not in sa.inspect(connection).get_table_names():
        return
    rows = connection.execute(
        sa.text("SELECT id, document FROM lab_qualification_definitions")
    ).mappings()
    statement = sa.text(
        "UPDATE lab_qualification_definitions SET document = :document WHERE id = :id"
    ).bindparams(sa.bindparam("document", type_=JSONB))
    for row in rows:
        connection.execute(
            statement,
            {
                "id": row["id"],
                "document": canonicalize_qualification_package(row["document"]),
            },
        )


def downgrade() -> None:
    pass
