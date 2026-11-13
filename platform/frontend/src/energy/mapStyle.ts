import type * as maplibregl from "maplibre-gl";
import { FUEL_COLOR, FUEL_OTHER, VOLTAGE_CLASSES } from "./format";

/**
 * Map style of the energy section: a quiet dark basemap and the power layers on top.
 *
 * Power features come from the API as vector tiles (`/grid/tiles`), with the asset id as
 * feature id, so the simulation can recolour lines through feature-state without new tiles:
 *   off: boolean       — de-energised / tripped
 *   load: number       — loading of a branch, 0…1+ (share of its rating)
 *   hit: boolean       — target of an event at the current moment
 *   hover / selected   — interaction
 */

export const POWER_SOURCE = "power";
export const LAYER_IDS = {
  lineCasing: "power-line-casing",
  line: "power-line",
  lineFuture: "power-line-future",
  cable: "power-cable",
  substationArea: "power-substation-area",
  substation: "power-substation",
  substationLabel: "power-substation-label",
  plantArea: "power-plant-area",
  plant: "power-plant",
  plantLabel: "power-plant-label",
  generator: "power-generator",
} as const;

export type PowerFilters = {
  minVoltage: number;
  kinds: { lines: boolean; cables: boolean; substations: boolean; plants: boolean; generators: boolean };
  statuses: string[];
  fuels: string[] | null; // null: every fuel
};

export const DEFAULT_FILTERS: PowerFilters = {
  minVoltage: 0,
  kinds: { lines: true, cables: true, substations: true, plants: true, generators: true },
  statuses: ["active", "construction", "damaged", "destroyed", "occupied"],
  fuels: null,
};

type Expr = maplibregl.ExpressionSpecification;

const voltage: Expr = ["coalesce", ["get", "v"], 0];

/** Colour step over the voltage classes (lowest class first, as `step` requires). */
export function voltageColorExpr(): Expr {
  const classes = [...VOLTAGE_CLASSES].reverse();
  const expr: unknown[] = ["step", voltage, classes[0].color];
  for (const c of classes.slice(1)) expr.push(c.min, c.color);
  return expr as Expr;
}

const widthByVoltage: Expr = ["step", voltage, 0.6, 52, 0.9, 132, 1.2, 220, 1.5, 310, 1.9, 550, 2.4];

/** Width that grows with zoom; `extra` px is added at every stop (zoom must stay top-level). */
function zoomed(base: Expr, low = 0.45, high = 2.6, extra = 0): Expr {
  const stop = (k: number): Expr => (extra ? ["+", ["*", k, base], extra] : ["*", k, base]);
  return ["interpolate", ["linear"], ["zoom"], 3, stop(low), 8, stop(1), 14, stop(high)];
}

/** Line colour: simulation state first (off → grey, loading → green…red), else voltage. */
function lineColor(): Expr {
  return [
    "case",
    ["boolean", ["feature-state", "off"], false], "#5b6763",
    ["!=", ["feature-state", "load"], null],
    ["interpolate", ["linear"], ["to-number", ["feature-state", "load"]], 0, "#3fbf7f", 0.7, "#c9d34a", 0.9, "#f0bd63", 1.0, "#ff6a3d", 1.2, "#ff2d55"],
    voltageColorExpr(),
  ] as Expr;
}

const fuelColor = ["match", ["coalesce", ["get", "fuel"], ""], ...Object.entries(FUEL_COLOR).flat(), FUEL_OTHER] as unknown as Expr;

export function powerLayers(tilesUrl: string): { source: maplibregl.SourceSpecification; layers: maplibregl.LayerSpecification[] } {
  const source: maplibregl.SourceSpecification = {
    type: "vector",
    tiles: [tilesUrl],
    minzoom: 2,
    maxzoom: 14,
    attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> (ODbL) · стиль за <a href="https://openinframap.org" target="_blank" rel="noreferrer">Open Infrastructure Map</a>',
  };
  const s = POWER_SOURCE;
  const layers: maplibregl.LayerSpecification[] = [
    {
      id: LAYER_IDS.plantArea,
      type: "fill",
      source: s,
      "source-layer": "power_plant_area",
      paint: { "fill-color": fuelColor, "fill-opacity": 0.12, "fill-outline-color": fuelColor },
    },
    {
      id: LAYER_IDS.substationArea,
      type: "fill",
      source: s,
      "source-layer": "power_substation_area",
      paint: { "fill-color": voltageColorExpr(), "fill-opacity": 0.14, "fill-outline-color": voltageColorExpr() },
    },
    {
      id: LAYER_IDS.lineCasing,
      type: "line",
      source: s,
      "source-layer": "power_line",
      filter: ["!=", ["get", "kind"], "cable"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": ["case", ["boolean", ["feature-state", "hit"], false], "#ff2d55", "#ffffff"],
        "line-width": zoomed(widthByVoltage, 0.45, 2.6, 6),
        "line-opacity": [
          "case",
          ["boolean", ["feature-state", "selected"], false], 0.55,
          ["boolean", ["feature-state", "hit"], false], 0.6,
          ["boolean", ["feature-state", "hover"], false], 0.28,
          0,
        ],
        "line-blur": 1.5,
      },
    },
    {
      id: LAYER_IDS.line,
      type: "line",
      source: s,
      "source-layer": "power_line",
      filter: ["all", ["!=", ["get", "kind"], "cable"], ["==", ["get", "status"], "active"]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": lineColor(),
        "line-width": zoomed(widthByVoltage),
        "line-opacity": ["case", ["boolean", ["feature-state", "off"], false], 0.75, 0.92],
      },
    },
    {
      id: LAYER_IDS.lineFuture,
      type: "line",
      source: s,
      "source-layer": "power_line",
      filter: ["all", ["!=", ["get", "kind"], "cable"], ["!=", ["get", "status"], "active"]],
      paint: { "line-color": voltageColorExpr(), "line-width": zoomed(widthByVoltage), "line-opacity": 0.6, "line-dasharray": [2, 2] },
    },
    {
      id: LAYER_IDS.cable,
      type: "line",
      source: s,
      "source-layer": "power_line",
      filter: ["==", ["get", "kind"], "cable"],
      paint: { "line-color": lineColor(), "line-width": zoomed(widthByVoltage), "line-opacity": 0.85, "line-dasharray": [1, 1.5] },
    },
    {
      id: LAYER_IDS.generator,
      type: "circle",
      source: s,
      "source-layer": "power_generator",
      paint: { "circle-color": fuelColor, "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 1.5, 16, 4], "circle-opacity": 0.85 },
    },
    {
      id: LAYER_IDS.substation,
      type: "circle",
      source: s,
      "source-layer": "power_substation",
      paint: {
        "circle-color": ["case", ["boolean", ["feature-state", "off"], false], "#5b6763", voltageColorExpr()],
        "circle-radius": zoomed(["step", voltage, 1.6, 110, 2.2, 220, 2.8, 330, 3.4, 550, 4.2] as Expr, 0.6, 2.2),
        "circle-stroke-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.5, ["boolean", ["feature-state", "hit"], false], 2.5, 0.8],
        "circle-stroke-color": ["case", ["boolean", ["feature-state", "hit"], false], "#ff2d55", ["boolean", ["feature-state", "selected"], false], "#ffffff", "#07110e"],
      },
    },
    {
      id: LAYER_IDS.plant,
      type: "circle",
      source: s,
      "source-layer": "power_plant",
      paint: {
        "circle-color": ["case", ["boolean", ["feature-state", "off"], false], "#5b6763", fuelColor],
        "circle-radius": [
          "interpolate", ["linear"], ["zoom"],
          3, ["+", 1.5, ["*", 0.05, ["sqrt", ["coalesce", ["get", "cap"], 1]]]],
          8, ["+", 3, ["*", 0.18, ["sqrt", ["coalesce", ["get", "cap"], 1]]]],
          13, ["+", 5, ["*", 0.35, ["sqrt", ["coalesce", ["get", "cap"], 1]]]],
        ],
        "circle-opacity": 0.9,
        "circle-stroke-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.5, ["boolean", ["feature-state", "hit"], false], 2.5, 1],
        "circle-stroke-color": ["case", ["boolean", ["feature-state", "hit"], false], "#ff2d55", ["boolean", ["feature-state", "selected"], false], "#ffffff", ["case", ["get", "est"], "#6b7a74", "#07110e"]],
      },
    },
    {
      id: LAYER_IDS.substationLabel,
      type: "symbol",
      source: s,
      "source-layer": "power_substation",
      minzoom: 8,
      filter: ["any", [">=", voltage, 220], [">=", ["zoom"], 11]],
      layout: {
        "text-field": ["coalesce", ["get", "name"], ""],
        "text-font": ["Noto Sans Regular"],
        "text-size": 10.5,
        "text-offset": [0, 0.9],
        "text-anchor": "top",
        "text-optional": true,
      },
      paint: { "text-color": "#c9d7d1", "text-halo-color": "#07110e", "text-halo-width": 1.4 },
    },
    {
      id: LAYER_IDS.plantLabel,
      type: "symbol",
      source: s,
      "source-layer": "power_plant",
      minzoom: 5,
      filter: ["any", [">=", ["coalesce", ["get", "cap"], 0], 1000], [">=", ["zoom"], 7.5]],
      layout: {
        "text-field": ["coalesce", ["get", "name"], ""],
        "text-font": ["Noto Sans Bold"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 5, 10, 10, 12],
        "text-offset": [0, 1.1],
        "text-anchor": "top",
        "text-max-width": 10,
        "text-optional": true,
      },
      paint: { "text-color": "#eef5f2", "text-halo-color": "#07110e", "text-halo-width": 1.6 },
    },
  ];
  return { source, layers };
}

/** Layers that answer clicks and hovers, top-most first. */
export const INTERACTIVE_LAYERS = [
  LAYER_IDS.plant,
  LAYER_IDS.substation,
  LAYER_IDS.generator,
  LAYER_IDS.line,
  LAYER_IDS.lineFuture,
  LAYER_IDS.cable,
  LAYER_IDS.plantArea,
  LAYER_IDS.substationArea,
];

const VISIBILITY: Record<keyof PowerFilters["kinds"], string[]> = {
  lines: [LAYER_IDS.line, LAYER_IDS.lineFuture, LAYER_IDS.lineCasing],
  cables: [LAYER_IDS.cable],
  substations: [LAYER_IDS.substation, LAYER_IDS.substationArea, LAYER_IDS.substationLabel],
  plants: [LAYER_IDS.plant, LAYER_IDS.plantArea, LAYER_IDS.plantLabel],
  generators: [LAYER_IDS.generator],
};

/** Base filter of each layer as defined in `powerLayers`, before the user's filters. */
const BASE_FILTERS = new Map<string, unknown>();

export function applyFilters(map: maplibregl.Map, filters: PowerFilters): void {
  for (const [kind, ids] of Object.entries(VISIBILITY) as [keyof PowerFilters["kinds"], string[]][]) {
    for (const id of ids) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", filters.kinds[kind] ? "visible" : "none");
  }
  const status: Expr = ["in", ["coalesce", ["get", "status"], "active"], ["literal", filters.statuses]];
  const byVoltage: Expr | true = filters.minVoltage > 0 ? [">=", voltage, filters.minVoltage] : true;
  const byFuel: Expr | true = filters.fuels ? ["in", ["coalesce", ["get", "fuel"], "other"], ["literal", filters.fuels]] : true;
  const targets: [string, (Expr | true)[]][] = [
    [LAYER_IDS.line, [status, byVoltage]],
    [LAYER_IDS.lineFuture, [status, byVoltage]],
    [LAYER_IDS.lineCasing, [byVoltage]],
    [LAYER_IDS.cable, [status, byVoltage]],
    [LAYER_IDS.substation, [status, byVoltage]],
    [LAYER_IDS.substationArea, [status, byVoltage]],
    [LAYER_IDS.substationLabel, [status, byVoltage]],
    [LAYER_IDS.plant, [status, byFuel]],
    [LAYER_IDS.plantArea, [status, byFuel]],
    [LAYER_IDS.plantLabel, [status, byFuel]],
    [LAYER_IDS.generator, [byFuel]],
  ];
  for (const [id, parts] of targets) {
    const layer = map.getLayer(id);
    if (!layer) continue;
    if (!BASE_FILTERS.has(id)) BASE_FILTERS.set(id, (layer as { filter?: unknown }).filter ?? null);
    const base = BASE_FILTERS.get(id);
    const all = [base, ...parts].filter((p) => p !== null && p !== true);
    map.setFilter(id, all.length ? (["all", ...all] as maplibregl.FilterSpecification) : null);
  }
}
