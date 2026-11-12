import { describe, expect, it } from "vitest";
import { clampPeriod, coveredYears, periodCovered, shiftYears, type Coverage } from "./coverage";
import { buildTimeline, balancesAt } from "./worldModel";

const coverage: Coverage = {
  source: "computation",
  computation_id: "c1",
  from: "2019-01-01",
  to: "2030-12-31",
  history_to: "2025-12-31",
  forecast: true,
  computed_at: null,
  parameters: {},
};

describe("coverage", () => {
  it("accepts only periods inside the computation", () => {
    expect(periodCovered("2023-01-01", "2031-12-31", coverage)).toBe(false);
    expect(periodCovered("2018-12-31", "2019-12-31", coverage)).toBe(false);
    expect(periodCovered("2026-01-01", "2030-12-31", coverage)).toBe(true);
    expect(periodCovered("2026-01-01", "2026-12-31", null)).toBe(false);
  });

  it("moves an uncovered period inside", () => {
    expect(clampPeriod("2023-01-01", "2031-12-31", coverage)).toEqual({ from: "2023-01-01", to: "2030-12-31" });
    expect(clampPeriod("2040-01-01", "2040-12-31", coverage)).toEqual({ from: "2030-01-01", to: "2030-12-31" });
    expect(clampPeriod("2010-01-01", "2010-12-31", coverage)).toEqual({ from: "2030-01-01", to: "2030-12-31" });
    expect(clampPeriod("2023-01-01", "2023-12-31", null)).toBeNull();
  });

  it("lists covered years and shifts horizons within limits", () => {
    expect(coveredYears(coverage)).toHaveLength(12);
    expect(coveredYears(coverage)[0]).toBe(2030);
    expect(shiftYears("2025-12-31", 5, "2019-03-01", "2050-12-31")).toBe("2030-12-31");
    expect(shiftYears("2048-12-31", 5, "2019-03-01", "2050-12-31")).toBe("2050-12-31");
  });
});

describe("playback window", () => {
  it("starts from the balances before the window", () => {
    const timeline = buildTimeline([{ id: "e", t: "2024-01-02T00:00:00Z", type: "type:transfer", provenance: "statistic", attributes: {}, postings: [["a", -5], ["b", 5]] }] as any, ["a", "b"], { a: 100 });
    expect(balancesAt(timeline, Date.parse("2024-01-01T00:00:00Z")).get("a")).toBe(100);
    expect(balancesAt(timeline, Date.parse("2024-01-03T00:00:00Z")).get("a")).toBe(95);
  });
});
