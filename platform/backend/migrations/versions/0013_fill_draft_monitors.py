"""Give existing active drafts a monitor template when cloning omitted it."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_fill_draft_monitors"
down_revision: str | None = "0012_repair_qualification_xml"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    if not {"lab_model_versions", "lab_monitor_templates"}.issubset(tables):
        return
    connection.execute(
        sa.text(
            """
            INSERT INTO lab_monitor_templates
                (id, model_version_id, name, revision, panels)
            SELECT
                'monitor-' || substr(md5(version.id), 1, 24),
                version.id,
                'Монітор робочої моделі',
                1,
                COALESCE(
                    (SELECT panels FROM lab_monitor_templates ORDER BY created_at LIMIT 1),
                    '[]'::jsonb
                )
            FROM lab_model_versions AS version
            WHERE version.status = 'draft'
              AND NOT EXISTS (
                  SELECT 1 FROM lab_monitor_templates AS monitor
                  WHERE monitor.model_version_id = version.id
              )
            """
        )
    )


def downgrade() -> None:
    pass
