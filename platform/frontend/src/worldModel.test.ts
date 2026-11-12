import { describe, expect, it } from "vitest";
import { balancesAt, buildTimeline, lastIndexAt, pointAlong, vesselStates, type LedgerEvent, type Voyage } from "./worldModel";

const events: LedgerEvent[] = [
  { id: "2", t: "2023-01-02T00:00:00Z", type: "type:load", provenance: "derived", attributes: {}, postings: [["store", -10], ["ship", 10]] },
  { id: "1", t: "2023-01-01T00:00:00Z", type: "type:extract", provenance: "derived", attributes: {}, postings: [["field", -10], ["store", 10]] },
];

describe("world playback", () => {
  it("accumulates balances in time order", () => {
    const timeline = buildTimeline(events, ["field", "store", "ship"]);
    expect(lastIndexAt(timeline.times, Date.parse("2022-12-31T00:00:00Z"))).toBe(-1);
    const day1 = balancesAt(timeline, Date.parse("2023-01-01T12:00:00Z"));
    expect(day1.get("store")).toBe(10);
    const day2 = balancesAt(timeline, Date.parse("2023-01-03T00:00:00Z"));
    expect([day2.get("field"), day2.get("store"), day2.get("ship")]).toEqual([-10, 0, 10]);
  });

  it("interpolates along a line and moves vessels both ways", () => {
    const line: [number, number][] = [[0, 0], [10, 0]];
    expect(pointAlong(line, 0.5)[0]).toBeCloseTo(5);
    const voyages: Voyage[] = [
      { id: "a", vessel: "v", route: "r", direction: "laden", cargo_kg: 1, depart: "2023-01-01T00:00:00Z", arrive: "2023-01-03T00:00:00Z" },
      { id: "b", vessel: "v", route: "r", direction: "ballast", cargo_kg: 0, depart: "2023-01-04T00:00:00Z", arrive: "2023-01-06T00:00:00Z" },
    ];
    const at = (iso: string) => vesselStates(voyages, { r: line }, Date.parse(iso))[0];
    expect(at("2022-12-31T00:00:00Z").status).toBe("at-origin");
    expect(at("2023-01-02T00:00:00Z").position[0]).toBeCloseTo(5);
    expect(at("2023-01-03T12:00:00Z").status).toBe("at-destination");
    expect(at("2023-01-05T12:00:00Z").position[0]).toBeCloseTo(2.5);
    expect(at("2023-01-07T00:00:00Z").position).toEqual([0, 0]);
  });
});

describe("formatting", () => {
  it("formats masses and scientific numbers", async () => {
    const { formatMass, scientific } = await import("./worldModel");
    expect(formatMass(0)).toBe("0");
    expect(formatMass(500)).toBe("500 кг");
    expect(formatMass(2.728e8)).toBe("273 тис. т");
    expect(formatMass(-6.58e12)).toBe("−6,58 млрд т");
    expect(scientific(1.16e34)).toEqual(["1,16", 34]);
  });
});
