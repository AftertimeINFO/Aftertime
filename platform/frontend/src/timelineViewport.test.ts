import { describe, expect, it } from "vitest";
import { timelineViewport } from "./timelineViewport";

const hour = 3600_000;

describe("timelineViewport", () => {
  it("zooms from current time toward the next dynamically scheduled event", () => {
    const result = timelineViewport(0, 48 * hour, 24 * hour, [
      { scheduled_at: new Date(24 * hour + 30 * 60_000).toISOString(), status: "scheduled" },
      { scheduled_at: new Date(25 * hour).toISOString(), status: "scheduled" },
    ], "auto");
    expect(result.start).toBeGreaterThan(23 * hour);
    expect(result.end).toBeLessThan(26 * hour);
    expect(result.next).toBe(24 * hour + 30 * 60_000);
  });

  it("keeps the complete scenario when full scale is selected", () => {
    expect(timelineViewport(0, 48 * hour, 24 * hour, [{ scheduled_at: new Date(25 * hour).toISOString() }], "full")).toEqual({ start: 0, end: 48 * hour, next: null });
  });

  it("extends the complete range to a process event scheduled after the original end", () => {
    expect(timelineViewport(0, hour, 0, [{ scheduled_at: new Date(2 * hour).toISOString() }], "full").end).toBe(2 * hour);
  });
});
