const API = import.meta.env.VITE_API_URL || "/api/v1";
export type Row = Record<string, any>;
export type PortContract = { key: string; name: string; direction: "input" | "output" | "bidirectional"; domain: string; role: string; quantity: string; unit: string; required: boolean; multiple: boolean; variables: Row[]; capabilities: string[] };
export type Observable = { address: string; scope: "component" | "port" | "connection" | "system"; target_id: string; target_key: string; target_name: string; metric_key: string; name: string; unit: string; value_type: string; path: string; recording: string; aggregation: string };
export type Workspace = { project: Row; projects: Row[]; version: Row; models: Row[]; components: (Row & { ports: PortContract[] })[]; nodes: Row[]; edges: Row[]; scenarios: Row[]; resources: Row[]; runs: Row[]; scripts: Row[]; workflows: Row[]; metrics: Row[]; dashboards: Row[]; monitors: Row[]; event_types: Row[]; observables: Observable[] };
export async function request<T>(path: string, init?: RequestInit, timeoutMs = 20_000): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, { ...init, signal: init?.signal || timeout, headers: { "Content-Type": "application/json", ...init?.headers } });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") throw new Error("Сервер не відповів за 20 секунд. Перевірте стан API/worker.");
    throw error;
  }
  if (!response.ok) {
    const text = await response.text();
    let payload: any;
    try { payload = JSON.parse(text); } catch { payload = null; }
    const detail = payload?.detail;
    if (typeof detail === "string") throw new Error(detail);
    if (detail?.errors) throw new Error(detail.errors.join(". "));
    if (detail?.message) throw new Error(detail.message);
    throw new Error(text || `${response.status}`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });
export const api = {
  workspace: (project?: string) => request<Workspace>(`/lab/workspace${project ? `?project_id=${encodeURIComponent(project)}` : ""}`),
  createProject: (body: Row) => request<Row>("/lab/projects", json("POST", body)),
  updateDashboard: (id: string, body: Row) => request<Row>(`/lab/dashboards/${id}`, json("PATCH", body)),
  graph: (version: string) => request<Row>(`/lab/versions/${version}/graph`),
  workflow: (version: string) => request<Row>(`/lab/workflows/${version}`),
  addWorkflowNode: (version: string, body: Row) => request<Row>(`/lab/workflows/${version}/nodes`, json("POST", body)),
  updateWorkflowNode: (id: string, body: Row) => request<Row>(`/lab/workflows/nodes/${id}`, json("PATCH", body)),
  addWorkflowTransition: (version: string, body: Row) => request<Row>(`/lab/workflows/${version}/transitions`, json("POST", body)),
  cloneWorkflow: (version: string) => request<Row>(`/lab/workflows/${version}/clone`, json("POST")),
  validateWorkflow: (version: string) => request<Row>(`/lab/workflows/${version}/validate`, json("POST")),
  publishWorkflow: (version: string) => request<Row>(`/lab/workflows/${version}/publish`, json("POST")),
  scenarioTimeline: (id: string) => request<Row>(`/lab/scenarios/${id}/timeline`),
  addNode: (version: string, body: Row) => request<Row>(`/lab/versions/${version}/nodes`, json("POST", body)),
  updateNode: (id: string, body: Row) => request<Row>(`/lab/nodes/${id}`, json("PATCH", body)),
  deleteNode: (id: string) => request<void>(`/lab/nodes/${id}`, json("DELETE")),
  addEdge: (version: string, body: Row) => request<Row>(`/lab/versions/${version}/edges`, json("POST", body)),
  updateEdge: (id: string, body: Row) => request<Row>(`/lab/edges/${id}`, json("PATCH", body)),
  deleteEdge: (id: string) => request<void>(`/lab/edges/${id}`, json("DELETE")),
  observables: (version: string, target?: string) => request<{ items: Observable[] }>(`/lab/versions/${version}/observables${target ? `?target_id=${encodeURIComponent(target)}` : ""}`),
  createMonitor: (version: string, body: Row) => request<Row>(`/lab/versions/${version}/monitors`, json("POST", body)),
  updateMonitor: (id: string, body: Row) => request<Row>(`/lab/monitors/${id}`, json("PATCH", body)),
  createScenarioEvent: (scenario: string, body: Row) => request<Row>(`/lab/scenarios/${scenario}/events`, json("POST", body)),
  createCepRule: (scenario: string, body: Row) => request<Row>(`/lab/scenarios/${scenario}/cep-rules`, json("POST", body)),
  validate: (version: string) => request<Row>(`/lab/versions/${version}/validate`, json("POST")),
  publish: (version: string) => request<Row>(`/lab/versions/${version}/publish`, json("POST")),
  clone: (version: string) => request<Row>(`/lab/versions/${version}/clone`, json("POST")),
  testComponent: (id: string, body: Row) => request<Row>(`/lab/components/${id}/test`, json("POST", body)),
  startRun: (body: Row) => request<Row>("/lab/runs", json("POST", body)),
  getRun: (id: string) => request<Row>(`/lab/runs/${id}`),
  seek: (id: string, body: Row) => request<Row>(`/lab/runs/${id}/seek`, json("POST", body)),
  command: (id: string, body: Row) => request<Row>(`/lab/runs/${id}/commands`, json("POST", body)),
  inject: (id: string, body: Row) => request<Row>(`/lab/runs/${id}/events`, json("POST", body)),
  samples: (id: string) => request<Row>(`/lab/runs/${id}/samples`),
  workflows: (id: string) => request<Row>(`/lab/runs/${id}/workflows`),
  userCommand: (id: string, body: Row) => request<Row>(`/lab/runs/${id}/user-commands`, json("POST", body)),
  testScript: (id: string, body: Row) => request<Row>(`/lab/scripts/versions/${id}/test`, json("POST", body)),
};
