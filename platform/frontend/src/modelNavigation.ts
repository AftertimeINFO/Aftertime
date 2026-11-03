import type { Row } from "./api";


export function selectableModels(models: Row[]): Row[] {
  return models.filter((model) => !model.settings?.deprecated).sort((left, right) =>
    String(left.name || "").localeCompare(String(right.name || ""), "uk"),
  );
}


export function scenarioForModel(scenarios: Row[], modelVersionId: string): Row | undefined {
  return scenarios.find(
    (scenario) =>
      !scenario.configuration?.deprecated && scenario.model_version_id === modelVersionId,
  );
}
