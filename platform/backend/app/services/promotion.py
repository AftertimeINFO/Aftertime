"""Promotion of model versions between layers: DEV → prePROD → PROD.

A promotion copies a *published* model version from the database of one layer into
the database of the next one, together with everything needed to run it there:

* the version content: nodes, edges, asset/actor roles, event programs and their
  actions, the qualification definition and monitor templates;
* the scenarios bound to the version with their published assembly (participants,
  process bindings, node maps, links), event templates and CEP rules;
* the model versions of the assembly participants (recursively, with their content);
* the process sets and BPMN workflows the assembly binds, and the scripts scenarios
  and dashboards refer to;
* catalogs the runtime reads: component types used by the nodes, event types,
  resource pools, metrics and dashboards; world entities the model refers to.

Rows keep their ids, so the same model is traceable across layers. A row already in
the target must be identical (validation results excepted), otherwise the promotion
is refused as a conflict. World entities are the exception: the target layer owns its
world data, so an existing entity there is kept as it is.

Runs and their results are never copied: each layer produces its own evidence.
Only adjacent promotions are allowed, and PROD additionally requires a completed run
of the version in prePROD.
"""

from collections import defaultdict
from collections.abc import Iterable, Iterator
from typing import Any

from sqlalchemy import Table, func, insert, select, update
from sqlalchemy.orm import Session

from app.db import Base
from app.layers import LAYER_POLICY, Layer
from app.models import (
    LabAssetActorRole,
    LabCepRule,
    LabDashboardDefinition,
    LabEdge,
    LabEventAction,
    LabEventProgram,
    LabEventType,
    LabMetricDefinition,
    LabModelVersion,
    LabMonitorTemplate,
    LabNode,
    LabProcessSet,
    LabProcessSetVersion,
    LabProcessSetWorkflow,
    LabProject,
    LabQualificationDefinition,
    LabResourcePool,
    LabRun,
    LabScenario,
    LabScenarioAssemblyLink,
    LabScenarioAssemblyMember,
    LabScenarioAssemblyNodeMap,
    LabScenarioAssemblyVersion,
    LabScenarioEventTemplate,
    LabScenarioProcessBinding,
    LabScriptDependency,
    LabScriptVersion,
    LabWorkflowNode,
    LabWorkflowTransition,
    LabWorkflowVersion,
    LayerPromotion,
    new_id,
)
from app.services.model_lab import validate_graph

NEXT_LAYER: dict[str, Layer] = {"dev": "preprod", "preprod": "prod"}

# Columns rewritten by validation in any layer: not a change of the model.
VOLATILE = frozenset({"validation", "validated_at"})
# The target layer owns its world data.
TARGET_WINS = frozenset({"entities"})
# Pointers of a project are set by the promotion itself.
POINTERS = {"lab_projects": frozenset({"active_draft_id", "published_version_id"})}
SCRIPT_KEYS = ("scenario_script_version_id", "process_script_version_id", "dashboard_script_version_id")
CHUNK = 500

TABLE_LABELS = {
    "entities": "Сутності світу",
    "lab_projects": "Проєкти",
    "lab_model_versions": "Версії моделей",
    "lab_component_types": "Типи компонентів",
    "lab_nodes": "Вузли",
    "lab_edges": "Зв'язки",
    "lab_asset_actor_roles": "Ролі активів і акторів",
    "lab_event_types": "Типи подій",
    "lab_event_programs": "Програми подій",
    "lab_event_actions": "Дії програм подій",
    "lab_qualification_definitions": "Визначення кваліфікації",
    "lab_monitor_templates": "Шаблони моніторів",
    "lab_scenarios": "Сценарії",
    "lab_scenario_event_templates": "Події сценаріїв",
    "lab_cep_rules": "CEP-правила",
    "lab_scenario_assembly_versions": "Збірки сценаріїв",
    "lab_scenario_assembly_members": "Учасники збірок",
    "lab_scenario_process_bindings": "Прив'язки процесів",
    "lab_scenario_assembly_node_map": "Карта вузлів збірок",
    "lab_scenario_assembly_links": "Зв'язки між учасниками",
    "lab_process_sets": "Набори процесів",
    "lab_process_set_versions": "Версії наборів процесів",
    "lab_process_set_workflows": "Активації процесів",
    "lab_workflows": "Процеси (BPMN)",
    "lab_workflow_versions": "Версії процесів",
    "lab_workflow_nodes": "Кроки процесів",
    "lab_workflow_transitions": "Переходи процесів",
    "lab_scripts": "Скрипти",
    "lab_script_versions": "Версії скриптів",
    "lab_script_dependencies": "Залежності скриптів",
    "lab_resource_pools": "Пули ресурсів",
    "lab_metric_definitions": "Метрики",
    "lab_dashboard_definitions": "Дашборди",
}


class PromotionError(Exception):
    def __init__(self, status: int, detail: Any):
        super().__init__(detail if isinstance(detail, str) else "promotion refused")
        self.status = status
        self.detail = detail


def next_layer(layer: str) -> Layer | None:
    return NEXT_LAYER.get(layer)


def _chunks(values: Iterable[str]) -> Iterator[list[str]]:
    values = sorted(v for v in values if v)
    for start in range(0, len(values), CHUNK):
        yield values[start : start + CHUNK]


def _ids(db: Session, column, where, values: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for chunk in _chunks(values):
        found.update(value for value in db.scalars(select(column).where(where.in_(chunk))) if value)
    return found


def _all(db: Session, column) -> set[str]:
    return set(db.scalars(select(column)))


def collect(db: Session, version_id: str) -> dict[str, set[str]]:
    """Ids of every row the version needs, by table name (read from the source layer)."""
    if not db.get(LabModelVersion, version_id):
        raise PromotionError(404, "Версію моделі не знайдено")
    rows: dict[str, set[str]] = defaultdict(set)

    # Versions: the root plus the participant models of its scenario assemblies.
    versions: set[str] = set()
    frontier = {version_id}
    while frontier:
        versions |= frontier
        scenarios = _ids(db, LabScenario.id, LabScenario.model_version_id, frontier)
        rows["lab_scenarios"] |= scenarios
        assemblies = _ids(db, LabScenario.assembly_version_id, LabScenario.id, scenarios)
        rows["lab_scenario_assembly_versions"] |= assemblies
        linked = _ids(db, LabScenarioAssemblyMember.model_version_id, LabScenarioAssemblyMember.assembly_version_id, assemblies)
        linked |= _ids(db, LabScenarioAssemblyVersion.composite_model_version_id, LabScenarioAssemblyVersion.id, assemblies)
        frontier = linked - versions
    rows["lab_model_versions"] = versions
    rows["lab_projects"] = _ids(db, LabModelVersion.project_id, LabModelVersion.id, versions)

    # Version content.
    nodes = _ids(db, LabNode.id, LabNode.model_version_id, versions)
    rows["lab_nodes"] = nodes
    rows["lab_component_types"] = _ids(db, LabNode.component_type_id, LabNode.id, nodes)
    rows["lab_edges"] = _ids(db, LabEdge.id, LabEdge.model_version_id, versions)
    rows["lab_asset_actor_roles"] = _ids(db, LabAssetActorRole.id, LabAssetActorRole.model_version_id, versions)
    programs = _ids(db, LabEventProgram.id, LabEventProgram.model_version_id, versions)
    rows["lab_event_programs"] = programs
    rows["lab_event_actions"] = _ids(db, LabEventAction.id, LabEventAction.program_id, programs)
    rows["lab_qualification_definitions"] = _ids(db, LabQualificationDefinition.id, LabQualificationDefinition.model_version_id, versions)
    rows["lab_monitor_templates"] = _ids(db, LabMonitorTemplate.id, LabMonitorTemplate.model_version_id, versions)

    # Scenarios and their assemblies.
    scenarios = rows["lab_scenarios"]
    rows["lab_scenario_event_templates"] = _ids(db, LabScenarioEventTemplate.id, LabScenarioEventTemplate.scenario_id, scenarios)
    rows["lab_cep_rules"] = _ids(db, LabCepRule.id, LabCepRule.scenario_id, scenarios)
    assemblies = rows["lab_scenario_assembly_versions"]
    members = _ids(db, LabScenarioAssemblyMember.id, LabScenarioAssemblyMember.assembly_version_id, assemblies)
    rows["lab_scenario_assembly_members"] = members
    rows["lab_scenario_process_bindings"] = _ids(db, LabScenarioProcessBinding.id, LabScenarioProcessBinding.assembly_version_id, assemblies)
    rows["lab_scenario_assembly_node_map"] = _ids(db, LabScenarioAssemblyNodeMap.id, LabScenarioAssemblyNodeMap.assembly_version_id, assemblies)
    rows["lab_scenario_assembly_links"] = _ids(db, LabScenarioAssemblyLink.id, LabScenarioAssemblyLink.assembly_version_id, assemblies)

    # Processes bound to the assemblies.
    process_versions = _ids(db, LabScenarioProcessBinding.process_set_version_id, LabScenarioProcessBinding.id, rows["lab_scenario_process_bindings"])
    rows["lab_process_set_versions"] = process_versions
    process_sets = _ids(db, LabProcessSetVersion.process_set_id, LabProcessSetVersion.id, process_versions)
    rows["lab_process_sets"] = process_sets
    activations = _ids(db, LabProcessSetWorkflow.id, LabProcessSetWorkflow.process_set_version_id, process_versions)
    rows["lab_process_set_workflows"] = activations
    workflow_versions = _ids(db, LabProcessSetWorkflow.workflow_version_id, LabProcessSetWorkflow.id, activations)
    rows["lab_workflow_versions"] = workflow_versions
    rows["lab_workflows"] = _ids(db, LabWorkflowVersion.workflow_id, LabWorkflowVersion.id, workflow_versions)
    rows["lab_workflow_nodes"] = _ids(db, LabWorkflowNode.id, LabWorkflowNode.workflow_version_id, workflow_versions)
    rows["lab_workflow_transitions"] = _ids(db, LabWorkflowTransition.id, LabWorkflowTransition.workflow_version_id, workflow_versions)

    # Catalogs the runtime reads as a whole.
    rows["lab_event_types"] = _all(db, LabEventType.id)
    rows["lab_resource_pools"] = _all(db, LabResourcePool.id)
    rows["lab_metric_definitions"] = _all(db, LabMetricDefinition.id)
    rows["lab_dashboard_definitions"] = _all(db, LabDashboardDefinition.id)

    # Scripts referenced by scenarios and dashboards, with their dependencies.
    scripts: set[str] = set()
    for chunk in _chunks(scenarios):
        for configuration in db.scalars(select(LabScenario.configuration).where(LabScenario.id.in_(chunk))):
            scripts.update(str(configuration[key]) for key in SCRIPT_KEYS if (configuration or {}).get(key))
    scripts |= set(db.scalars(select(LabDashboardDefinition.script_version_id).where(LabDashboardDefinition.script_version_id.is_not(None))))
    frontier = scripts
    while frontier:
        dependencies = _ids(db, LabScriptDependency.id, LabScriptDependency.script_version_id, frontier)
        rows["lab_script_dependencies"] |= dependencies
        frontier = _ids(db, LabScriptDependency.dependency_version_id, LabScriptDependency.id, dependencies) - scripts
        scripts |= frontier
    rows["lab_script_versions"] = scripts
    rows["lab_scripts"] = _ids(db, LabScriptVersion.script_id, LabScriptVersion.id, scripts)

    # World entities the model refers to.
    rows["entities"] = (
        _ids(db, LabAssetActorRole.entity_id, LabAssetActorRole.id, rows["lab_asset_actor_roles"])
        | _ids(db, LabScenarioAssemblyMember.entity_id, LabScenarioAssemblyMember.id, members)
        | _ids(db, LabProcessSet.owner_entity_id, LabProcessSet.id, process_sets)
    )
    return {name: ids for name, ids in rows.items() if ids}


def _fetch(db: Session, table: Table, ids: Iterable[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for chunk in _chunks(ids):
        for record in db.execute(select(table).where(table.c.id.in_(chunk))).mappings():
            found[record["id"]] = dict(record)
    return found


def _differing(table: str, source: dict, target: dict) -> list[str]:
    skip = VOLATILE | POINTERS.get(table, frozenset())
    return sorted(column for column in source if column not in skip and source[column] != target.get(column))


def _check(check_id: str, label: str, ok: bool, detail: str = "") -> dict:
    return {"id": check_id, "label": label, "ok": ok, "detail": detail}


def _version_row(db: Session, version: LabModelVersion) -> dict:
    project = db.get(LabProject, version.project_id)
    return {
        "id": version.id,
        "name": version.name,
        "version": version.version,
        "status": version.status,
        "project_id": version.project_id,
        "project_name": project.name if project else version.project_id,
        "published_at": version.published_at.isoformat() if version.published_at else None,
    }


def _plan(source: Session, target: Session, version_id: str, source_layer: str, target_layer: str) -> tuple[dict, dict[str, list[dict]], list[LabModelVersion]]:
    if NEXT_LAYER.get(source_layer) != target_layer:
        allowed = NEXT_LAYER.get(source_layer)
        hint = f"дозволено лише {LAYER_POLICY[source_layer]['label']} → {LAYER_POLICY[allowed]['label']}" if allowed else "з PROD моделі далі не переносяться"
        raise PromotionError(422, f"Перенесення {source_layer} → {target_layer} неможливе: {hint}")
    bundle = collect(source, version_id)
    root = source.get(LabModelVersion, version_id)
    versions = list(source.scalars(select(LabModelVersion).where(LabModelVersion.id.in_(bundle["lab_model_versions"]))))

    tables: list[dict] = []
    conflicts: list[dict] = []
    new_rows: dict[str, list[dict]] = {}
    dangling: list[str] = []
    for table in Base.metadata.sorted_tables:
        ids = bundle.get(table.name)
        if not ids:
            continue
        source_rows = _fetch(source, table, ids)
        target_rows = _fetch(target, table, ids)
        dangling.extend(f"{table.name}:{item}" for item in sorted(ids - source_rows.keys()))
        same = kept = changed = 0
        for item in sorted(source_rows.keys() & target_rows.keys()):
            columns = _differing(table.name, source_rows[item], target_rows[item])
            if not columns:
                same += 1
            elif table.name in TARGET_WINS:
                kept += 1
            else:
                changed += 1
                conflicts.append({"table": table.name, "label": TABLE_LABELS.get(table.name, table.name), "id": item, "columns": columns})
        new = [source_rows[item] for item in sorted(source_rows.keys() - target_rows.keys())]
        new_rows[table.name] = new
        tables.append({"table": table.name, "label": TABLE_LABELS.get(table.name, table.name), "new": len(new), "same": same, "kept": kept, "changed": changed})

    unpublished = [f"{v.name} v{v.version}" for v in versions if v.status != "published"]
    invalid: list[str] = []
    for item in versions:
        result = validate_graph(source, item.id)
        if not result.get("valid"):
            invalid.append(f"{item.name} v{item.version}: {'; '.join(result.get('errors', [])[:2])}")
    checks = [
        _check("published", "Усі версії опубліковані", not unpublished, ", ".join(unpublished)),
        _check("valid", f"Графи моделей валідні в {LAYER_POLICY[source_layer]['label']}", not invalid, " · ".join(invalid[:3])),
    ]
    if target_layer == "prod":
        runs = source.scalar(select(func.count()).select_from(LabRun).where(LabRun.model_version_id == version_id, LabRun.status == "completed")) or 0
        checks.append(_check("validated", "Є завершений прогін у prePROD", runs > 0, f"завершених прогонів: {runs}" if runs else "запустіть сценарій цієї версії в prePROD і дочекайтесь завершення"))
    checks.append(_check("conflicts", f"Немає конфліктів із даними {LAYER_POLICY[target_layer]['label']}", not conflicts, f"рядків, що відрізняються: {len(conflicts)}" if conflicts else ""))

    new_total = sum(item["new"] for item in tables)
    status = "blocked" if not all(check["ok"] for check in checks) else ("ready" if new_total else "already")
    scenario_names = list(source.scalars(select(LabScenario.name).where(LabScenario.id.in_(bundle.get("lab_scenarios", set()))).order_by(LabScenario.name)))
    plan = {
        "version": _version_row(source, root),
        "source": source_layer,
        "target": target_layer,
        "status": status,
        "checks": checks,
        "tables": tables,
        "totals": {"new": new_total, "same": sum(t["same"] for t in tables), "kept": sum(t["kept"] for t in tables), "changed": len(conflicts)},
        "conflicts": conflicts[:50],
        "dangling": dangling[:50],
        "scenarios": scenario_names,
        "versions": [f"{v.name} v{v.version}" for v in sorted(versions, key=lambda v: (v.id != version_id, v.name))],
    }
    return plan, new_rows, versions


def plan_promotion(source: Session, target: Session, version_id: str, source_layer: str, target_layer: str) -> dict:
    """What a promotion would copy and whether it is allowed; writes nothing."""
    return _plan(source, target, version_id, source_layer, target_layer)[0]


def promote(source: Session, target: Session, version_id: str, source_layer: str, target_layer: str, note: str = "") -> dict:
    """Copy the version into the target layer in one transaction and record it in both layers."""
    plan, new_rows, versions = _plan(source, target, version_id, source_layer, target_layer)
    if plan["status"] == "blocked":
        raise PromotionError(409, plan)
    if plan["status"] == "already":
        return {**plan, "promotion": None}

    # Circular references (scenario ↔ assembly) are filled in after both rows exist.
    deferred: list[tuple[Table, str, dict]] = []
    for table in Base.metadata.sorted_tables:
        rows = new_rows.get(table.name)
        if not rows:
            continue
        late = [fk.parent.name for fk in table.foreign_keys if fk.use_alter]
        copies = []
        for row in rows:
            copy = dict(row)
            values = {column: copy[column] for column in late if copy.get(column) is not None}
            for column in values:
                copy[column] = None
            if values:
                deferred.append((table, copy["id"], values))
            if table.name == "lab_projects":
                copy["active_draft_id"] = None
                copy["published_version_id"] = None
            copies.append(copy)
        for start in range(0, len(copies), CHUNK):
            target.execute(insert(table), copies[start : start + CHUNK])
    for table, row_id, values in deferred:
        target.execute(update(table).where(table.c.id == row_id).values(**values))

    # The promoted version becomes the published one of its project; no drafts outside DEV.
    root = plan["version"]
    target.execute(update(LabProject.__table__).where(LabProject.id == root["project_id"]).values(published_version_id=root["id"], active_draft_id=None))
    for version in versions:
        if version.id != root["id"]:
            target.execute(
                update(LabProject.__table__)
                .where(LabProject.id == version.project_id, LabProject.published_version_id.is_(None))
                .values(published_version_id=version.id, active_draft_id=None)
            )

    summary = {"totals": plan["totals"], "tables": [t for t in plan["tables"] if t["new"]], "checks": plan["checks"], "scenarios": plan["scenarios"], "versions": plan["versions"]}
    record = {"id": new_id(), "version_id": root["id"], "project_id": root["project_id"], "source_layer": source_layer, "target_layer": target_layer, "note": note, "summary": summary}
    target.add(LayerPromotion(**record))
    target.commit()
    # The source keeps a copy of the record so it knows where the version went.
    source.add(LayerPromotion(**record))
    source.commit()
    return {**plan, "status": "promoted", "promotion": record["id"]}


def candidates(source: Session, target: Session | None) -> list[dict]:
    """Published versions of the source layer and whether they are already in the target."""
    versions = list(source.scalars(select(LabModelVersion).where(LabModelVersion.status == "published").order_by(LabModelVersion.published_at.desc().nulls_last(), LabModelVersion.name)))
    ids = [v.id for v in versions]
    present = _ids(target, LabModelVersion.id, LabModelVersion.id, ids) if target is not None else set()
    projects = {p.id: p.name for p in source.scalars(select(LabProject))}
    scenarios: dict[str, list[str]] = defaultdict(list)
    for chunk in _chunks(ids):
        for model_version_id, name in source.execute(select(LabScenario.model_version_id, LabScenario.name).where(LabScenario.model_version_id.in_(chunk))):
            scenarios[model_version_id].append(name)
    runs = dict(
        source.execute(
            select(LabRun.model_version_id, func.count()).where(LabRun.status == "completed").group_by(LabRun.model_version_id)
        ).all()
    )
    last: dict[str, dict] = {}
    for item in source.scalars(select(LayerPromotion).order_by(LayerPromotion.created_at)):
        last[item.version_id] = {"source": item.source_layer, "target": item.target_layer, "at": item.created_at.isoformat() if item.created_at else None}
    # Versions with scenarios first: participant models travel along with them anyway.
    versions.sort(key=lambda v: (not scenarios.get(v.id), projects.get(v.project_id, ""), -v.version))
    return [
        {
            "id": v.id,
            "name": v.name,
            "version": v.version,
            "project_id": v.project_id,
            "project_name": projects.get(v.project_id, v.project_id),
            "published_at": v.published_at.isoformat() if v.published_at else None,
            "scenarios": sorted(scenarios.get(v.id, [])),
            "completed_runs": runs.get(v.id, 0),
            "in_target": v.id in present,
            "last_promotion": last.get(v.id),
        }
        for v in versions
    ]


def history(db: Session, version_id: str | None = None, limit: int = 50) -> list[dict]:
    query = select(LayerPromotion).order_by(LayerPromotion.created_at.desc()).limit(limit)
    if version_id:
        query = query.where(LayerPromotion.version_id == version_id)
    return [
        {
            "id": item.id,
            "version_id": item.version_id,
            "project_id": item.project_id,
            "source": item.source_layer,
            "target": item.target_layer,
            "note": item.note,
            "summary": item.summary,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in db.scalars(query)
    ]
