"""Scripted workflows, timeline samples and resource ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
# Frozen schema: later revisions own every table added after release 0.4.0-rc.6.
from migrations.schema_0001 import Base

revision: str = "0005_scripted_workflows"
down_revision: str | None = "0004_scenario_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "incident_at" in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("lab_scenarios")}:
        return
    op.add_column("lab_scenarios", sa.Column("incident_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lab_scenarios", sa.Column("pre_event_seconds", sa.Integer(), nullable=False, server_default="86400"))
    op.add_column("lab_scenarios", sa.Column("post_event_seconds", sa.Integer(), nullable=False, server_default="86400"))
    op.add_column("lab_scenarios", sa.Column("configuration", JSONB(), nullable=False, server_default="{}"))
    op.create_index("ix_lab_scenarios_incident_at", "lab_scenarios", ["incident_at"])
    op.add_column("lab_work_orders", sa.Column("workflow_instance_id", sa.String(80), nullable=True))
    op.add_column("lab_work_orders", sa.Column("planned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lab_work_orders", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lab_work_orders", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_lab_work_orders_workflow_instance_id", "lab_work_orders", ["workflow_instance_id"])
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    for name in ["lab_user_commands", "lab_dashboard_definitions", "lab_metric_definitions", "lab_flow_samples", "lab_resource_transactions", "lab_run_samples", "lab_scenario_event_templates", "lab_workflow_tokens", "lab_workflow_instances", "lab_workflow_transitions", "lab_workflow_nodes", "lab_workflow_versions", "lab_workflows", "lab_script_test_results", "lab_script_test_cases", "lab_script_dependencies", "lab_script_versions", "lab_scripts"]:
        op.drop_table(name)
    op.drop_index("ix_lab_work_orders_workflow_instance_id", table_name="lab_work_orders")
    for column in ["workflow_instance_id", "planned_at", "started_at", "completed_at"]:
        op.drop_column("lab_work_orders", column)
    op.drop_index("ix_lab_scenarios_incident_at", table_name="lab_scenarios")
    for column in ["incident_at", "pre_event_seconds", "post_event_seconds", "configuration"]:
        op.drop_column("lab_scenarios", column)
