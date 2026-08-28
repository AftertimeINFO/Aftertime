import { describe, expect, it } from "vitest";

import {
  DEFAULT_SCENARIO_ID,
  shouldAutoStartDefaultScenario,
} from "./startup";

const ready = {
  scenarioId: DEFAULT_SCENARIO_ID,
  scenarioModelVersionId: "storm-model",
  loadedModelVersionId: "storm-model",
  timelineReady: true,
  runExists: false,
  alreadyRequested: false,
};

describe("default Storm Arwen startup", () => {
  it("starts only after the matching model and timeline are loaded", () => {
    expect(shouldAutoStartDefaultScenario(ready)).toBe(true);
    expect(
      shouldAutoStartDefaultScenario({ ...ready, loadedModelVersionId: "other-model" }),
    ).toBe(false);
    expect(shouldAutoStartDefaultScenario({ ...ready, timelineReady: false })).toBe(false);
  });

  it("does not create duplicate runs after the first request", () => {
    expect(shouldAutoStartDefaultScenario({ ...ready, alreadyRequested: true })).toBe(false);
    expect(shouldAutoStartDefaultScenario({ ...ready, runExists: true })).toBe(false);
  });
});
