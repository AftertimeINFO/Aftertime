import { describe, expect, it } from "vitest";

import {
  diagnosticSeriesValue,
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
});
