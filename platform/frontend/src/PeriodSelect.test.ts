import { describe, expect, it } from "vitest";
import type { Coverage } from "./coverage";
import { periodIn, periodMode } from "./PeriodSelect";

const coverage = { from: "2019-01-01", to: "2030-12-31", history_to: "2025-12-31", forecast: true } as Coverage;

describe("period by year", () => {
  it("recognises the shape of a period", () => {
    expect(periodMode("2024-01-01", "2024-12-31")).toBe("year");
    expect(periodMode("2024-04-01", "2024-06-30")).toBe("q2");
    expect(periodMode("2024-02-03", "2024-05-01")).toBe("custom");
    expect(periodMode("2023-01-01", "2024-12-31")).toBe("custom");
  });

  it("moves the same shape to a typed year", () => {
    expect(periodIn(2028, "year", coverage)).toEqual({ from: "2028-01-01", to: "2028-12-31" });
    expect(periodIn(2028, "q4", coverage)).toEqual({ from: "2028-10-01", to: "2028-12-31" });
    expect(periodIn(2027, "custom", coverage, { from: "2024-02-03", to: "2025-05-01" })).toEqual({ from: "2027-02-03", to: "2028-05-01" });
  });

  it("refuses a year without a computation", () => {
    expect(periodIn(2035, "year", coverage)).toBeNull();
    expect(periodIn(2018, "q1", coverage)).toBeNull();
    expect(periodIn(202, "year", coverage)).toBeNull();
  });
});
