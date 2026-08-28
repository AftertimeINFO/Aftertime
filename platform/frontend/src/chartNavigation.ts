import type { Row } from "./api";


export function resolveSeriesNodeId(nodes: Row[], series: Row): string | undefined {
  return nodes.find(
    (node) =>
      node.id === series.target_id ||
      node.instance_key === series.target_key ||
      node.component_type_id === series.point_component_type,
  )?.id;
}


export function diagnosticSeriesValue(
  sample: Row,
  nodes: Row[],
  series: Row,
): number {
  const nodeId = resolveSeriesNodeId(nodes, series);
  const metricKey = series.metric_key || series.metric;
  const value = sample.metrics?.node_metrics?.[nodeId || ""]?.[metricKey];
  return value === undefined || value === null ? Number.NaN : Number(value);
}


export type DiagnosticSeriesStats = {
  latest: number;
  min: number;
  max: number;
  count: number;
};


export function diagnosticSeriesStats(
  samples: Row[],
  nodes: Row[],
  series: Row,
): DiagnosticSeriesStats | null {
  const values = samples
    .map((sample) => diagnosticSeriesValue(sample, nodes, series))
    .filter(Number.isFinite);
  if (!values.length) return null;
  return {
    latest: values.at(-1) as number,
    min: Math.min(...values),
    max: Math.max(...values),
    count: values.length,
  };
}


export function formatDiagnosticValue(value: number): string {
  return new Intl.NumberFormat("uk-UA", {
    maximumFractionDigits: Math.abs(value) < 10 ? 3 : 2,
  }).format(value);
}


const SERIES_DASH_PATTERNS = ["", "10 5", "3 4", "14 4 3 4", "2 3 8 3"];


export function diagnosticSeriesDash(index: number): string {
  return SERIES_DASH_PATTERNS[index % SERIES_DASH_PATTERNS.length];
}


export function diagnosticSeriesLaneY(
  value: number,
  domain: [number, number],
  index: number,
  seriesCount: number,
): number {
  const top = 24;
  const bottom = 186;
  const count = Math.max(1, seriesCount);
  const laneHeight = (bottom - top) / count;
  const laneTop = top + laneHeight * index + 5;
  const laneBottom = top + laneHeight * (index + 1) - 5;
  const [min, max] = domain;
  const normalized = (value - min) / Math.max(0.0001, max - min);
  return laneBottom - normalized * Math.max(1, laneBottom - laneTop);
}


export function preferredDiagnosticPoint(
  nodes: Row[],
  catalog: Row[],
  selectedNodeId: string | null,
  currentPoint: string,
): string {
  const available = (nodeId: string | null) =>
    Boolean(
      nodeId &&
        nodes.some((node) => node.id === nodeId) &&
        catalog.some(
          (observable) =>
            observable.target_id === nodeId && observable.value_type === "number",
        ),
    );
  if (available(selectedNodeId)) return selectedNodeId as string;
  if (available(currentPoint)) return currentPoint;
  return nodes.find((node) => available(node.id))?.id || "";
}
