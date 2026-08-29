import { describe, expect, it } from "vitest";

import { scenarioForModel, selectableModels } from "./modelNavigation";


describe("model navigation", () => {
  it("keeps every model version visible instead of collapsing them into one project", () => {
    const models = [
      { id: "draft", name: "Робоча чернетка", status: "draft", version: 2 },
      { id: "storm", name: "Storm Arwen", status: "published", version: 11 },
      { id: "base", name: "Еталонний контур", status: "published", version: 1 },
    ];

    expect(selectableModels(models).map((model) => model.id).sort()).toEqual([
      "base",
      "draft",
      "storm",
    ]);
  });

  it("opens the scenario linked to a selected qualification model", () => {
    const scenarios = [
      { id: "baseline", model_version_id: "base" },
      { id: "storm-arwen-2021", model_version_id: "storm" },
    ];

    expect(scenarioForModel(scenarios, "storm")?.id).toBe("storm-arwen-2021");
    expect(scenarioForModel(scenarios, "draft")).toBeUndefined();
  });
});
