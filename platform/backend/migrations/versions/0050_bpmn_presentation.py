"""Repair BPMN Sequence Flow geometry and meaningful completion labels."""

from collections.abc import Sequence
import json
import uuid

import sqlalchemy as sa
from alembic import op

from app.services.bpmn_profile import repair_bpmn_presentation, validate_bpmn


revision: str = "0050_bpmn_presentation"
down_revision: str | None = "0049_executable_bpmn"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    versions = connection.execute(
        sa.text("SELECT id, bpmn_xml FROM lab_workflow_versions WHERE bpmn_xml <> ''")
    ).mappings()
    for version in versions:
        repaired, renamed = repair_bpmn_presentation(version["bpmn_xml"])
        if repaired == version["bpmn_xml"] and not renamed:
            continue
        connection.execute(
            sa.text(
                """INSERT INTO lab_workflow_definition_backups
                   (id, workflow_version_id, reason, bpmn_xml, nodes, transitions)
                   VALUES (:id, :version_id, 'bpmn-presentation-fix', :xml,
                           CAST(:nodes AS jsonb), CAST(:transitions AS jsonb))"""
            ),
            {
                "id": str(uuid.uuid4()),
                "version_id": version["id"],
                "xml": version["bpmn_xml"],
                "nodes": json.dumps([]),
                "transitions": json.dumps([]),
            },
        )
        validation = validate_bpmn(repaired)
        connection.execute(
            sa.text(
                """UPDATE lab_workflow_versions
                   SET bpmn_xml = :xml, validation = CAST(:validation AS jsonb),
                       validated_at = now()
                   WHERE id = :version_id"""
            ),
            {
                "xml": repaired,
                "validation": json.dumps(validation, ensure_ascii=False),
                "version_id": version["id"],
            },
        )
        for node_key, name in renamed.items():
            connection.execute(
                sa.text(
                    """UPDATE lab_workflow_nodes SET name = :name
                       WHERE workflow_version_id = :version_id AND node_key = :node_key"""
                ),
                {"name": name, "version_id": version["id"], "node_key": node_key},
            )


def downgrade() -> None:
    connection = op.get_bind()
    backups = connection.execute(
        sa.text(
            """SELECT DISTINCT ON (workflow_version_id) workflow_version_id, bpmn_xml
               FROM lab_workflow_definition_backups
               WHERE reason = 'bpmn-presentation-fix'
               ORDER BY workflow_version_id, created_at DESC"""
        )
    ).mappings()
    for backup in backups:
        connection.execute(
            sa.text(
                "UPDATE lab_workflow_versions SET bpmn_xml = :xml WHERE id = :version_id"
            ),
            {"xml": backup["bpmn_xml"], "version_id": backup["workflow_version_id"]},
        )
