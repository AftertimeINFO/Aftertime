import { describe, expect, it } from "vitest";
import {
  actionTargetKind,
  CREATABLE_EVENT_ACTION_TYPES,
  compatibleEventTargets,
  eventOverlay,
  formatZonedDateTimeLocal,
  orderedActions,
  parseZonedDateTimeLocal,
  payloadDefaults,
  type EventProgram,
} from "./eventDesigner";

const program: EventProgram = {
  id: "program-1",
  model_version_id: "model-1",
  event_type_id: "line_fault",
  name: "Аварія лінії",
  description: "",
  enabled: true,
  layout: { trigger: { x: 10, y: 20 } },
  actions: [
    { id: "b", program_id: "program-1", sequence: 20, action_type: "connection.disable", target_kind: "connection", target_id: "edge-1", config: {}, x: 400, y: 20 },
    { id: "a", program_id: "program-1", sequence: 10, action_type: "component.capability", target_kind: "component", target_id: "node-1", config: { capability: "trip" }, x: 200, y: 20 },
  ],
};

describe("event designer helpers", () => {
  it("orders actions deterministically and resolves target kinds", () => {
    expect(orderedActions(program).map((action) => action.id)).toEqual(["a", "b"]);
    expect(actionTargetKind("component.patch_state")).toBe("component");
    expect(actionTargetKind("connection.disable")).toBe("connection");
    expect(actionTargetKind("event.emit")).toBeNull();
    expect(CREATABLE_EVENT_ACTION_TYPES).not.toContain("component.patch_state");
  });

  it("filters capability targets using the node contract", () => {
    const targets = compatibleEventTargets(
      { action_type: "component.capability", config: { capability: "repair" } },
      [
        { id: "one", name: "One", component_type_id: "line", refinement_contract: { capabilities: ["trip"] } },
        { id: "two", name: "Two", component_type_id: "line", refinement_contract: { capabilities: ["trip", "repair"] } },
      ],
      [],
      [{ id: "line", initial_state: { online: true } }],
    );
    expect(targets.map((target) => target.id)).toEqual(["two"]);
  });

  it("offers only components with editable primitive state for state patches", () => {
    const targets = compatibleEventTargets(
      { action_type: "component.patch_state", config: { patch: {} } },
      [
        { id: "primitive", name: "Primitive", component_type_id: "device", initial_state: { online: true, nested: { value: 1 } } },
        { id: "composite", name: "Composite", component_type_id: "composite" },
      ],
      [],
      [
        { id: "device", initial_state: { load: 1 } },
        { id: "composite", initial_state: { nested: { value: 1 } } },
      ],
    );
    expect(targets).toEqual([
      expect.objectContaining({ id: "primitive", state: { load: 1, online: true } }),
    ]);
  });

  it("creates defaults from an event payload schema", () => {
    expect(payloadDefaults({ properties: { severity: { type: "number", default: 0.7 }, note: { type: "string" }, confirmed: { type: "boolean" } } })).toEqual({ severity: 0.7, note: "", confirmed: false });
  });

  it("round-trips calendar values in the model timezone", () => {
    const winter = new Date("2021-11-25T08:00:00Z");
    expect(formatZonedDateTimeLocal(winter, "Europe/Kyiv")).toBe("2021-11-25T10:00");
    expect(parseZonedDateTimeLocal("2021-11-25T10:00", "Europe/Kyiv")?.toISOString()).toBe("2021-11-25T08:00:00.000Z");
    expect(parseZonedDateTimeLocal("2021-07-25T10:00", "Europe/Kyiv")?.toISOString()).toBe("2021-07-25T07:00:00.000Z");
  });

  it("builds trigger, ordered actions and visible object bindings", () => {
    const overlay = eventOverlay({
      program,
      modelNodes: [
        { id: "node-1", position: { x: 600, y: 20 }, data: {} },
        { id: "node-2", position: { x: 900, y: 20 }, data: {} },
      ],
      modelEdges: [{ id: "edge-1", source: "node-1", target: "node-2" }],
      graphRows: [{ id: "node-1" }, { id: "node-2" }],
      edgeRows: [{ id: "edge-1", source_node_id: "node-1", target_node_id: "node-2", connection_key: "line" }],
    });
    expect(overlay.nodes.map((node) => node.id)).toContain("event-program:program-1");
    expect(overlay.nodes.map((node) => node.id)).toContain("event-connection:edge-1");
    expect(overlay.edges.filter((edge) => edge.id.startsWith("event-target:")).length).toBe(2);
    expect(overlay.edges.find((edge) => edge.id === "event-order:program-1:b")?.source).toBe("event-action:a");
  });
});
