import { describe, expect, it } from "vitest";

import {
  diagnosticSeriesDash,
  diagnosticSeriesLaneY,
  diagnosticSeriesStats,
  diagnosticSeriesValue,
  formatDiagnosticValue,
  preferredDiagnosticPoint,
  resolveSeriesNodeId,
} from "./chartNavigation";

const nodes = [
  { id: "plant", instance_key: "steam-plant", component_type_id: "tpp" },
  { id: "lamp", instance_key: "led-1", component_type_id: "led" },
];
const catalog = [
  { target_id: "plant", value_type: "number" },
  { target_id: "lamp", value_type: "boolean" },
];

describe("chart-to-graph navigation", () => {
  it("resolves both current and legacy series addresses to a graph node", () => {
    expect(resolveSeriesNodeId(nodes, { target_id: "plant" })).toBe("plant");
    expect(resolveSeriesNodeId(nodes, { target_key: "led-1" })).toBe("lamp");
    expect(resolveSeriesNodeId(nodes, { point_component_type: "tpp" })).toBe("plant");
  });

  it("uses a selected graph node only when it has numeric observables", () => {
    expect(preferredDiagnosticPoint(nodes, catalog, "plant", "")).toBe("plant");
    expect(preferredDiagnosticPoint(nodes, catalog, "lamp", "plant")).toBe("plant");
  });

  it("reads newly recorded component outputs for an added chart series", () => {
    const sample = {
      metrics: { node_metrics: { plant: { gas_energy_mw: 500 } } },
    };
    expect(
      diagnosticSeriesValue(sample, nodes, {
        target_id: "plant",
        metric_key: "gas_energy_mw",
      }),
    ).toBe(500);
    expect(
      diagnosticSeriesValue(sample, nodes, {
        target_id: "lamp",
        metric_key: "gas_energy_mw",
      }),
    ).toBeNaN();
  });

  it("shows numeric summary instead of a name-only chart legend", () => {
    const samples = [
      { metrics: { node_metrics: { plant: { gas_energy_mw: 500 } } } },
      { metrics: { node_metrics: { plant: { gas_energy_mw: 475 } } } },
    ];
    const series = { target_id: "plant", metric_key: "gas_energy_mw" };

    expect(diagnosticSeriesStats(samples, nodes, series)).toEqual({
      latest: 475,
      min: 475,
      max: 500,
      count: 2,
    });
    expect(diagnosticSeriesStats([], nodes, series)).toBeNull();
    expect(formatDiagnosticValue(475.125)).toMatch(/^475(?:[,.])13$/);
  });

  it("keeps three overlapping line series visually distinguishable", () => {
    const patterns = [0, 1, 2].map(diagnosticSeriesDash);

    expect(new Set(patterns).size).toBe(3);
    expect(patterns[0]).toBe("");
    expect(patterns[1]).not.toBe("");
    expect(patterns[2]).not.toBe("");
  });

  it("places equally normalized series in separate vertical lanes", () => {
    const y = [0, 1, 2].map((index) =>
      diagnosticSeriesLaneY(1, [0, 1], index, 3),
    );

    expect(new Set(y).size).toBe(3);
    expect(y[0]).toBeLessThan(y[1]);
    expect(y[1]).toBeLessThan(y[2]);
  });
});
