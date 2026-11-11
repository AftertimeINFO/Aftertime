"""Universal world core: PostGIS, entity extents, event ledger and postings.

See docs/en/design/MATTER_FLOW_AND_LOCATIONS.md, section 4.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0051_world_core"
down_revision: str | None = "0050_bpmn_presentation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "events",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("event_type_id", sa.String(80), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("scenario_id", sa.String(80)),
        sa.Column("run_id", sa.String(80)),
        sa.Column("source_id", sa.String(80), sa.ForeignKey("sources.id")),
        sa.Column("provenance", sa.String(20), nullable=False),
        sa.Column("attributes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "provenance IN ('statistic', 'derived', 'assumed')", name="ck_events_provenance"
        ),
    )
    op.create_index("ix_events_event_type_id", "events", ["event_type_id"])
    op.create_index("ix_events_occurred_at", "events", ["occurred_at"])
    op.create_index("ix_events_scenario_id", "events", ["scenario_id"])
    op.create_index("ix_events_run_id", "events", ["run_id"])

    op.create_table(
        "postings",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column(
            "event_id",
            sa.String(80),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            sa.String(80),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("property", sa.String(120), nullable=False),
        sa.Column("delta", sa.Float, nullable=False),
        sa.Column("unit", sa.String(80), nullable=False),
    )
    op.create_index("ix_postings_event_id", "postings", ["event_id"])
    op.create_index("ix_postings_entity_property", "postings", ["entity_id", "property"])

    op.create_table(
        "entity_extents",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column(
            "entity_id",
            sa.String(80),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("z_min_m", sa.Float),
        sa.Column("z_max_m", sa.Float),
        sa.Column("z_surface_ref", sa.Text),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("source_id", sa.String(80), sa.ForeignKey("sources.id")),
        sa.Column("attributes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "z_min_m IS NULL OR z_max_m IS NULL OR z_min_m <= z_max_m",
            name="ck_entity_extents_z_band",
        ),
    )
    op.execute("ALTER TABLE entity_extents ADD COLUMN geom geometry(Geometry, 4326)")
    op.create_index("ix_entity_extents_entity_id", "entity_extents", ["entity_id"])
    op.execute("CREATE INDEX ix_entity_extents_geom ON entity_extents USING gist (geom)")

    for table in ("relations", "observations"):
        op.add_column(
            table,
            sa.Column(
                "cause_event_id",
                sa.String(80),
                sa.ForeignKey("events.id", ondelete="SET NULL"),
            ),
        )
        op.create_index(f"ix_{table}_cause_event_id", table, ["cause_event_id"])

    # Audit view: per event and property, the net of all postings. Conserved
    # quantities must net to zero; the service layer enforces it on write.
    op.execute(
        """
        CREATE VIEW event_balances AS
        SELECT p.event_id, p.property, p.unit, sum(p.delta) AS net, count(*) AS postings
        FROM postings p
        GROUP BY p.event_id, p.property, p.unit
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS event_balances")
    for table in ("relations", "observations"):
        op.drop_index(f"ix_{table}_cause_event_id", table_name=table)
        op.drop_column(table, "cause_event_id")
    op.drop_table("entity_extents")
    op.drop_table("postings")
    op.drop_table("events")
