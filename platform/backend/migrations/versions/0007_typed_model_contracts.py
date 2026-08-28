"""Typed model contracts, observability and event architecture v2."""

# ruff: noqa: E501

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0007_typed_model_contracts"
down_revision: str | None = "0006_playback_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "architecture_version" in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("lab_model_versions")}:
        return
    op.add_column("lab_model_versions", sa.Column("architecture_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("lab_model_versions", sa.Column("semantic_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("lab_nodes", sa.Column("instance_key", sa.String(120), nullable=True))
    op.add_column("lab_nodes", sa.Column("port_overrides", JSONB(), nullable=False, server_default="{}"))
    op.add_column("lab_nodes", sa.Column("observable_overrides", JSONB(), nullable=False, server_default="{}"))
    op.execute("UPDATE lab_nodes SET instance_key = id WHERE instance_key IS NULL")
    op.create_index("ix_lab_nodes_instance_key", "lab_nodes", ["instance_key"])
    op.create_unique_constraint("uq_lab_node_instance_key", "lab_nodes", ["model_version_id", "instance_key"])

    op.add_column("lab_edges", sa.Column("connection_key", sa.String(120), nullable=True))
    op.add_column("lab_edges", sa.Column("domain", sa.String(60), nullable=False, server_default="legacy.energy"))
    op.add_column("lab_edges", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("UPDATE lab_edges SET connection_key = id WHERE connection_key IS NULL")
    op.create_index("ix_lab_edges_connection_key", "lab_edges", ["connection_key"])
    op.create_index("ix_lab_edges_domain", "lab_edges", ["domain"])
    op.create_unique_constraint("uq_lab_edge_connection_key", "lab_edges", ["model_version_id", "connection_key"])

    op.create_table(
        "lab_observable_definitions",
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column("component_type_id", sa.String(80), sa.ForeignKey("lab_component_types.id", ondelete="CASCADE"), nullable=True),
        sa.Column("scope", sa.String(30), nullable=False, server_default="component"),
        sa.Column("port_key", sa.String(80), nullable=True),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False, server_default=""),
        sa.Column("value_type", sa.String(30), nullable=False, server_default="number"),
        sa.Column("path", sa.String(240), nullable=False),
        sa.Column("aggregation", sa.String(30), nullable=False, server_default="last"),
        sa.Column("recording", sa.String(30), nullable=False, server_default="aggregate"),
        sa.Column("metadata", JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_lab_observable_definitions_component_type_id", "lab_observable_definitions", ["component_type_id"])
    op.create_index("ix_lab_observable_definitions_scope", "lab_observable_definitions", ["scope"])
    op.create_index("ix_lab_observable_definitions_metric_key", "lab_observable_definitions", ["metric_key"])

    op.create_table(
        "lab_monitor_templates",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("model_version_id", sa.String(80), sa.ForeignKey("lab_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("panels", JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_lab_monitor_templates_model_version_id", "lab_monitor_templates", ["model_version_id"])

    op.create_table(
        "lab_run_monitor_snapshots",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("run_id", sa.String(80), sa.ForeignKey("lab_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.String(80), nullable=True),
        sa.Column("template_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("panels", JSONB(), nullable=False, server_default="[]"),
        sa.Column("observable_catalog", JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", name="uq_lab_run_monitor_snapshot_run"),
    )
    op.create_index("ix_lab_run_monitor_snapshots_run_id", "lab_run_monitor_snapshots", ["run_id"])

    op.create_table(
        "lab_event_types",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False, server_default="stimulus"),
        sa.Column("target_kinds", JSONB(), nullable=False, server_default="[]"),
        sa.Column("domains", JSONB(), nullable=False, server_default="[]"),
        sa.Column("required_capabilities", JSONB(), nullable=False, server_default="[]"),
        sa.Column("payload_schema", JSONB(), nullable=False, server_default="{}"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("allow_broadcast", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_lab_event_types_kind", "lab_event_types", ["kind"])

    op.create_table(
        "lab_cep_rules",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("scenario_id", sa.String(80), sa.ForeignKey("lab_scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("condition", JSONB(), nullable=False, server_default="{}"),
        sa.Column("emit", JSONB(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_lab_cep_rules_scenario_id", "lab_cep_rules", ["scenario_id"])


def downgrade() -> None:
    op.drop_table("lab_cep_rules")
    op.drop_table("lab_event_types")
    op.drop_table("lab_run_monitor_snapshots")
    op.drop_table("lab_monitor_templates")
    op.drop_table("lab_observable_definitions")
    op.drop_constraint("uq_lab_edge_connection_key", "lab_edges", type_="unique")
    op.drop_index("ix_lab_edges_domain", table_name="lab_edges")
    op.drop_index("ix_lab_edges_connection_key", table_name="lab_edges")
    for column in ["enabled", "domain", "connection_key"]:
        op.drop_column("lab_edges", column)
    op.drop_constraint("uq_lab_node_instance_key", "lab_nodes", type_="unique")
    op.drop_index("ix_lab_nodes_instance_key", table_name="lab_nodes")
    for column in ["observable_overrides", "port_overrides", "instance_key"]:
        op.drop_column("lab_nodes", column)
    for column in ["semantic_revision", "architecture_version"]:
        op.drop_column("lab_model_versions", column)
