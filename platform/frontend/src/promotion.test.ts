import { describe, expect, it } from "vitest";

import { candidateState, filterCandidates, type PromotionCandidate } from "./promotion";

const item = (patch: Partial<PromotionCandidate> = {}): PromotionCandidate => ({
  id: "qualification-texas-2021",
  name: "Кваліфікаційна модель · Texas, 2021",
  version: 112,
  project_id: "energy",
  project_name: "Газ → ТЕС → мережа → споживач",
  published_at: null,
  scenarios: ["Texas, 2021"],
  completed_runs: 0,
  in_target: false,
  last_promotion: null,
  ...patch,
});

describe("promotion candidates", () => {
  it("tells what can move to the next layer", () => {
    expect(candidateState(item(), "preprod")).toEqual({ label: "можна в prePROD", tone: "ready" });
    expect(candidateState(item({ in_target: true }), "preprod").tone).toBe("done");
    // PROD needs a completed run in prePROD.
    expect(candidateState(item(), "prod").tone).toBe("wait");
    expect(candidateState(item({ completed_runs: 2 }), "prod").tone).toBe("ready");
    expect(candidateState(item(), null).label).toBe("кінцевий шар");
  });

  it("searches by project, version and scenario", () => {
    const items = [item(), item({ id: "energy-v1", name: "Базова", scenarios: ["Базовий добовий цикл"] })];
    expect(filterCandidates(items, "texas").map((i) => i.id)).toEqual(["qualification-texas-2021"]);
    expect(filterCandidates(items, "добовий").map((i) => i.id)).toEqual(["energy-v1"]);
    expect(filterCandidates(items, " ")).toHaveLength(2);
  });
});
