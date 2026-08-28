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
