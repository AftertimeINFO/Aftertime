import type { Edge, Node } from "@xyflow/react";
import type { Row } from "./api";

export type EventActionType =
  | "component.capability"
  | "component.patch_state"
  | "connection.disable"
  | "connection.enable"
  | "event.emit";

export type EventAction = {
  id: string;
  program_id: string;
  sequence: number;
  action_type: EventActionType;
  target_kind?: "component" | "connection" | null;
  target_id?: string | null;
  config: Row;
  x: number;
  y: number;
};

export type EventProgram = {
  id: string;
  model_version_id: string;
  event_type_id: string;
  name: string;
  description: string;
  enabled: boolean;
  layout: { trigger?: { x: number; y: number } };
  actions: EventAction[];
};

export type EventTarget = {
  id: string;
  kind: "component" | "connection";
  name: string;
  capabilities: string[];
  state: Row;
};

export const EVENT_ACTION_LABELS: Record<EventActionType, string> = {
  "component.capability": "Виклик capability",
  "component.patch_state": "Legacy: пряма зміна стану",
  "connection.disable": "Розімкнути зв’язок",
  "connection.enable": "Відновити зв’язок",
  "event.emit": "Запустити наступну подію",
};

export const CREATABLE_EVENT_ACTION_TYPES: EventActionType[] = [
  "component.capability",
  "connection.disable",
  "connection.enable",
  "event.emit",
];

export function orderedActions(program?: EventProgram | null): EventAction[] {
  return [...(program?.actions || [])].sort(
    (a, b) => a.sequence - b.sequence || a.id.localeCompare(b.id),
  );
}

export function actionTargetKind(type: EventActionType): EventTarget["kind"] | null {
  if (type.startsWith("component.")) return "component";
  if (type.startsWith("connection.")) return "connection";
  return null;
}

export function eventTargets(
  actionType: EventActionType,
  rows: Row[],
  edges: Row[],
  components: Row[],
): EventTarget[] {
  const kind = actionTargetKind(actionType);
  if (kind === "component") {
    return rows.map((node) => {
      const component = components.find((item) => item.id === node.component_type_id);
      const declaredState = { ...(component?.initial_state || {}), ...(node.initial_state || {}) };
      return {
        id: node.id,
        kind,
        name: node.name,
        capabilities: node.refinement_contract?.capabilities || [],
        state: Object.fromEntries(
          Object.entries(declaredState).filter(([, value]) =>
            ["boolean", "number", "string"].includes(typeof value),
          ),
        ),
      };
    });
  }
  if (kind === "connection") {
    return edges.map((edge) => ({
      id: edge.id,
      kind,
      name: edge.connection_key || edge.flow_type || edge.id,
      capabilities: ["enable", "disable"],
      state: { enabled: edge.enabled !== false },
    }));
  }
  return [];
}

export function compatibleEventTargets(
  action: Pick<EventAction, "action_type" | "config">,
  rows: Row[],
  edges: Row[],
  components: Row[],
): EventTarget[] {
  const targets = eventTargets(action.action_type, rows, edges, components);
  if (action.action_type === "component.patch_state") {
    return targets.filter((target) => Object.keys(target.state).length > 0);
  }
  if (action.action_type !== "component.capability") return targets;
  const capability = String(action.config?.capability || "");
  return capability
    ? targets.filter((target) => target.capabilities.includes(capability))
    : targets;
}

export function payloadDefaults(schema?: Row): Row {
  return Object.fromEntries(
    Object.entries(schema?.properties || {}).map(([key, property]: [string, any]) => {
      if (property.default !== undefined) return [key, property.default];
      if (property.type === "boolean") return [key, false];
      if (property.type === "number" || property.type === "integer") return [key, 0];
      return [key, ""];
    }),
  );
}

export function coerceSchemaValue(value: string | boolean, schema: Row): unknown {
  if (schema.type === "boolean") return Boolean(value);
  if (schema.type === "integer") return Math.trunc(Number(value || 0));
  if (schema.type === "number") return Number(value || 0);
  return String(value);
}

function datePartsInZone(date: Date, timeZone: string): Record<string, string> {
  return Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).formatToParts(date).map((part) => [part.type, part.value]),
  );
}

export function formatZonedDateTimeLocal(date: Date, timeZone: string): string {
  if (!Number.isFinite(date.getTime())) return "";
  const parts = datePartsInZone(date, timeZone);
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

export function parseZonedDateTimeLocal(value: string, timeZone: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value);
  if (!match) return null;
  const desired = Date.UTC(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
    Number(match[4]),
    Number(match[5]),
    Number(match[6] || 0),
  );
  let instant = desired;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const parts = datePartsInZone(new Date(instant), timeZone);
    const displayed = Date.UTC(
      Number(parts.year),
      Number(parts.month) - 1,
      Number(parts.day),
      Number(parts.hour),
      Number(parts.minute),
      Number(parts.second),
    );
    const correction = desired - displayed;
    instant += correction;
    if (!correction) break;
  }
  const result = new Date(instant);
  return Number.isFinite(result.getTime()) ? result : null;
}

type OverlayInput = {
  program: EventProgram;
  modelNodes: Node[];
  modelEdges: Edge[];
  graphRows: Row[];
  edgeRows: Row[];
};

export function eventOverlay({
  program,
  modelNodes,
  modelEdges,
  graphRows,
  edgeRows,
}: OverlayInput): { nodes: Node[]; edges: Edge[] } {
  const actions = orderedActions(program);
  const targetedNodes = new Set(actions.filter((action) => action.target_kind === "component").map((action) => action.target_id));
  const targetedEdges = new Set(actions.filter((action) => action.target_kind === "connection").map((action) => action.target_id));
  const triggerId = `event-program:${program.id}`;
  const trigger = program.layout?.trigger || { x: 40, y: 40 };
  const nodes: Node[] = modelNodes.map((node) => ({
    ...node,
    draggable: false,
    data: { ...node.data, eventBackground: true },
    className: `event-model-background ${targetedNodes.has(node.id) ? "event-bound-target" : ""}`,
  }));
  nodes.push({
    id: triggerId,
    type: "eventTrigger",
    position: trigger,
    data: { label: program.name, eventType: program.event_type_id, enabled: program.enabled },
  });

  const overlayEdges: Edge[] = [];
  actions.forEach((action, index) => {
    const id = `event-action:${action.id}`;
    nodes.push({
      id,
      type: "eventAction",
      position: {
        x: Number.isFinite(action.x) ? action.x : trigger.x + 230 + index * 200,
        y: Number.isFinite(action.y) ? action.y : trigger.y + 20,
      },
      data: {
        label: EVENT_ACTION_LABELS[action.action_type],
        actionType: action.action_type,
        sequence: action.sequence,
        targetId: action.target_id,
      },
    });
    overlayEdges.push({
      id: `event-order:${program.id}:${action.id}`,
      source: index ? `event-action:${actions[index - 1].id}` : triggerId,
      target: id,
      animated: program.enabled,
      className: "event-order-edge",
      label: index ? String(action.sequence) : "START",
    });

    if (action.target_kind === "component" && graphRows.some((row) => row.id === action.target_id)) {
      overlayEdges.push({
        id: `event-target:${action.id}`,
        source: id,
        sourceHandle: "target-link",
        target: String(action.target_id),
        targetHandle: "event-target",
        className: "event-target-edge",
        label: "дія над об’єктом",
      });
    }
    if (action.target_kind === "connection") {
      const edge = edgeRows.find((row) => row.id === action.target_id);
      const source = modelNodes.find((node) => node.id === edge?.source_node_id);
      const target = modelNodes.find((node) => node.id === edge?.target_node_id);
      if (edge && source && target) {
        const anchorId = `event-connection:${edge.id}`;
        if (!nodes.some((node) => node.id === anchorId)) {
          nodes.push({
            id: anchorId,
            type: "eventConnection",
            draggable: false,
            position: {
              x: (source.position.x + target.position.x) / 2 + 55,
              y: (source.position.y + target.position.y) / 2 + 40,
            },
            data: { label: edge.connection_key || edge.flow_type || edge.id, edgeId: edge.id },
          });
        }
        overlayEdges.push({
          id: `event-target:${action.id}`,
          source: id,
          sourceHandle: "target-link",
          target: anchorId,
          targetHandle: "event-target",
          className: "event-target-edge",
          label: "дія над зв’язком",
        });
      }
    }
  });

  return {
    nodes,
    edges: [
      ...modelEdges.map((edge) => ({ ...edge, animated: false, className: `${edge.className || ""} event-model-edge ${targetedEdges.has(edge.id) ? "event-bound-target" : ""}` })),
      ...overlayEdges,
    ],
  };
}
