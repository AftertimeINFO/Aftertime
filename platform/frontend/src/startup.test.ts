import { describe, expect, it } from "vitest";

import {
  DEFAULT_SCENARIO_ID,
  runModelVersionId,
  shouldAutoStartDefaultScenario,
} from "./startup";

const ready = {
  scenarioId: DEFAULT_SCENARIO_ID,
  scenarioModelVersionId: "southwest-model",
  loadedModelVersionId: "southwest-model",
  timelineReady: true,
  runExists: false,
  alreadyRequested: false,
};

describe("default Southwest Blackout startup", () => {
  it("uses Southwest Blackout 2011 as the landing scenario", () => {
    expect(DEFAULT_SCENARIO_ID).toBe("southwest-2011");
  });
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

  it("starts the scenario against its dedicated model instead of the generic published model", () => {
    expect(runModelVersionId("qualification-southwest-2011", "energy-v1")).toBe(
      "qualification-southwest-2011",
    );
    expect(runModelVersionId(undefined, "energy-v1")).toBe("energy-v1");
  });
});
