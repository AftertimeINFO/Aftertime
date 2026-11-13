import { describe, expect, it } from "vitest";
import { eventFrames, frameAt, frameStates, nextEvent, type Frame, type SnapshotNetwork } from "./run";

const network: SnapshotNetwork = {
  id: 1, as_of: "2024-01-01", countries: ["UA"], stats: {},
  buses: [[101, 330, "UA", "substation", 0, 0], [101, 110, "UA", "substation", 0, 0], [102, 330, "UA", "substation", 1, 1], [301, 330, "UA", "plant", 2, 2]],
  branches: [["line", [201, 202], 330], ["transformer", [101], 330], ["line", [203], 330]],
  generators: [[301, "nuclear", 1000]],
};

function frame(partial: Partial<Frame["state"]>, events: Frame["events"] = [], at = "2024-01-01T00:00:00Z"): Frame {
  return {
    sequence: 0, at, metrics: {} as Frame["metrics"], events,
    state: { load: [50, 10, 120], br_out: [], br_trip: [], bus_out: [], bus_dead: [], gen_out: [], trip_new: [], ...partial },
  };
}

describe("frame states", () => {
  it("spreads branch loading to every OSM way of the branch and skips transformers", () => {
    const s = frameStates(network, frame({}), new Set([301]));
    expect(s.lines.get(201)).toEqual({ off: false, load: 0.5 });
    expect(s.lines.get(202)).toEqual({ off: false, load: 0.5 });
    expect(s.lines.get(203)).toEqual({ off: false, load: 1.2 });
    expect(s.lines.has(101)).toBe(false);
  });
  it("marks tripped lines, substations whose every bus is dead, and lost plants", () => {
    const s = frameStates(network, frame({ load: [-1, 10, 80], br_trip: [0], bus_dead: [0, 1], gen_out: [0] }), new Set([301]));
    expect(s.lines.get(201)?.off).toBe(true);
    expect(s.substations.get(101)?.off).toBe(true);
    expect(s.substations.get(102)?.off).toBe(false);
    expect(s.plants.get(301)?.off).toBe(true);
  });
  it("highlights event targets", () => {
    const s = frameStates(network, frame({}, [{ at: "", type: "outage", label: "", targets: [102, 999], source_url: null, event_id: null, origin: "scenario" }]));
    expect(s.substations.get(102)?.hit).toBe(true);
    expect(s.plants.get(999)?.hit).toBe(true);
  });
});

describe("timeline navigation", () => {
  const frames = [
    frame({}, [], "2024-01-01T00:00:00Z"),
    frame({}, [{ at: "", type: "outage", label: "", targets: [], source_url: null, event_id: "e1", origin: "scenario" }], "2024-01-01T01:00:00Z"),
    frame({}, [{ at: "", type: "restore", label: "", targets: [], source_url: null, event_id: "e1", origin: "repair" }], "2024-01-01T02:00:00Z"),
    frame({}, [], "2024-01-01T03:00:00Z"),
  ];
  it("finds the frame shown at a moment", () => {
    expect(frameAt(frames, Date.parse("2023-12-31T00:00:00Z"))).toBe(0);
    expect(frameAt(frames, Date.parse("2024-01-01T01:30:00Z"))).toBe(1);
    expect(frameAt(frames, Date.parse("2025-01-01T00:00:00Z"))).toBe(3);
  });
  it("jumps between scenario events, not repairs", () => {
    expect(eventFrames(frames)).toEqual([1]);
    expect(nextEvent(frames, 0, 1)).toBe(1);
    expect(nextEvent(frames, 3, -1)).toBe(1);
    expect(nextEvent(frames, 1, 1)).toBe(1);
  });
});
