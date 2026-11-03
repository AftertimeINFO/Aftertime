"""Split San Bruno from the legacy combined San Bruno/Sissonville scenario."""

# ruff: noqa: E501

from collections.abc import Sequence

from alembic import op

revision: str = "0010_split_san_bruno"
down_revision: str | None = "0009_event_designer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Clone first so existing runs can continue to reference the legacy immutable
    # snapshot.  The old rows are then hidden, not deleted.
    op.execute(
        """
        INSERT INTO lab_model_versions (
            id, project_id, version, status, name, timezone, settings,
            validation, architecture_version, semantic_revision, published_at
        )
        SELECT
            'qualification-san-bruno-2010', project_id, 116, status,
            'Кваліфікаційна модель · San Bruno, 2010', timezone,
            (settings - 'deprecated' - 'replaced_by') ||
                jsonb_build_object(
                    'qualification_scenario', 'san-bruno-2010',
                    'immutable', true
                ),
            validation, architecture_version, semantic_revision, published_at
        FROM lab_model_versions
        WHERE id = 'qualification-san-bruno-sissonville'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO lab_nodes (
            id, model_version_id, component_type_id, name, parent_node_id,
            x, y, parameters, initial_state, python_code, refinement_contract,
            instance_key, port_overrides, observable_overrides
        )
        SELECT
            replace(id, 'q13-', 'q-san-bruno-'),
            'qualification-san-bruno-2010', component_type_id, name,
            CASE
                WHEN parent_node_id IS NULL THEN NULL
                ELSE replace(parent_node_id, 'q13-', 'q-san-bruno-')
            END,
            x, y,
            parameters || jsonb_build_object(
                'qualification_scenario', 'san-bruno-2010'
            ),
            initial_state, python_code,
            refinement_contract || jsonb_build_object(
                'scenario_model', 'san-bruno-2010'
            ),
            instance_key, port_overrides, observable_overrides
        FROM lab_nodes
        WHERE model_version_id = 'qualification-san-bruno-sissonville'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO lab_edges (
            id, model_version_id, source_node_id, source_port, target_node_id,
            target_port, flow_type, parameters, connection_key, domain, enabled
        )
        SELECT
            replace(id, 'q13-', 'q-san-bruno-'),
            'qualification-san-bruno-2010',
            replace(source_node_id, 'q13-', 'q-san-bruno-'), source_port,
            replace(target_node_id, 'q13-', 'q-san-bruno-'), target_port,
            flow_type, parameters, connection_key, domain, enabled
        FROM lab_edges
        WHERE model_version_id = 'qualification-san-bruno-sissonville'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO lab_scenarios (
            id, model_version_id, name, description, origin, source_url,
            start_at, duration_seconds, seed, events, expected, incident_at,
            pre_event_seconds, post_event_seconds, configuration
        )
        SELECT
            'san-bruno-2010', 'qualification-san-bruno-2010',
            'San Bruno, 2010', description, origin, source_url, start_at,
            duration_seconds, seed,
            replace(events::text, 'q13-', 'q-san-bruno-')::jsonb,
            expected, incident_at, pre_event_seconds, post_event_seconds,
            (configuration - 'deprecated' - 'replaced_by') ||
                jsonb_build_object(
                    'qualification_package_id', 'san-bruno-2010-l1'
                )
        FROM lab_scenarios
        WHERE id = 'san-bruno-sissonville'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO lab_scenario_event_templates (
            id, scenario_id, offset_seconds, priority, event_type,
            target_node_id, phase, title, payload, evidence_kind,
            source_url, source_note
        )
        SELECT
            replace(id, 'tpl-san-bruno-sissonville-', 'tpl-san-bruno-2010-'),
            'san-bruno-2010', offset_seconds, priority, event_type,
            replace(target_node_id, 'q13-', 'q-san-bruno-'), phase, title,
            payload, evidence_kind, source_url, source_note
        FROM lab_scenario_event_templates
        WHERE scenario_id = 'san-bruno-sissonville'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE lab_scenarios
        SET configuration = configuration || jsonb_build_object(
            'deprecated', true,
            'replaced_by', 'san-bruno-2010'
        )
        WHERE id = 'san-bruno-sissonville'
        """
    )
    op.execute(
        """
        UPDATE lab_model_versions
        SET settings = settings || jsonb_build_object(
            'deprecated', true,
            'replaced_by', 'qualification-san-bruno-2010'
        )
        WHERE id = 'qualification-san-bruno-sissonville'
        """
    )
    op.execute(
        """
        UPDATE lab_scenarios
        SET configuration = configuration || jsonb_build_object(
            'qualification_package_id',
            CASE id
                WHEN 'northeast-2003' THEN 'northeast-blackout-2003-l1'
                WHEN 'storm-arwen-2021' THEN 'storm-arwen-2021-l1'
            END
        )
        WHERE id IN ('northeast-2003', 'storm-arwen-2021')
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM lab_scenario_event_templates WHERE scenario_id = 'san-bruno-2010'"
    )
    op.execute("DELETE FROM lab_scenarios WHERE id = 'san-bruno-2010'")
    op.execute(
        "DELETE FROM lab_model_versions WHERE id = 'qualification-san-bruno-2010'"
    )
    op.execute(
        """
        UPDATE lab_scenarios
        SET configuration = configuration - 'deprecated' - 'replaced_by'
        WHERE id = 'san-bruno-sissonville'
        """
    )
    op.execute(
        """
        UPDATE lab_model_versions
        SET settings = settings - 'deprecated' - 'replaced_by'
        WHERE id = 'qualification-san-bruno-sissonville'
        """
    )
    op.execute(
        """
        UPDATE lab_scenarios
        SET configuration = configuration - 'qualification_package_id'
        WHERE id IN ('northeast-2003', 'storm-arwen-2021')
        """
    )
