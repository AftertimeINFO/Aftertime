import { request } from "../api";

/** Grid runs: API types and the mapping from a frame to map feature-states. */

export type Metrics = {
  demand_mw: number; served_mw: number; unserved_mw: number; unserved_share: number;
  generation_mw: number; available_mw: number; islands: number; frequency_hz: number;
  tripped: number; tripped_now: number; out_branches: number; out_buses: number; overloaded: number; occupied_buses?: number;
  ens_mwh: number; by_country: Record<string, { demand_mw: number; served_mw: number }>;
};
export type FrameEvent = { at: string; type: string; label: string; targets: number[]; source_url: string | null; event_id: string | null; origin: string };
export type Frame = {
  sequence: number; at: string; metrics: Metrics;
  state: { load: number[]; br_out: number[]; br_trip: number[]; bus_out: number[]; bus_dead: number[]; gen_out: number[]; trip_new: number[]; bus_occ?: number[]; br_occ?: number[] };
  events: FrameEvent[];
};
export type Band = { p10: number; p50: number; p90: number };
export type Check = { role?: "calibration" | "validation"; metric: string; at?: string; value: number; op?: string; tolerance?: number; label: string; source_url?: string; country?: string; model: number | null; ok: boolean; at_model: string };
export type CriticalAsset = { asset_id: number; unserved_mw: number; tripped: number; islands: number; kind?: string; name?: string | null; max_voltage_kv?: number | null; country?: string };
export type RunSummary = {
  snapshot_id?: number;
  base?: { balancing_mw: Record<string, number>; isolated_load_mw: number; ratings_raised: number; base_unserved_mw: number };
  peak?: { unserved_mw: number; at: string };
  ens_mwh?: number; frames?: number; checks?: Check[]; duration_s?: number;
  ensemble?: { members: number; representative_seed: number; ens_mwh: Band; peak_unserved_mw: Band; bands: { at: string; unserved_mw: Band; ens_mwh: Band }[] };
  criticality?: CriticalAsset[];
};
export type Run = { id: string; scenario_id: string; kind: "single" | "ensemble" | "criticality"; members: number; seed: number; status: string; progress: number; summary: RunSummary; error: string | null; created_at: string; finished_at: string | null; snapshot_id: number | null };
export type SnapshotNetwork = {
  id: number; as_of: string; countries: string[]; stats: Record<string, number>;
  /** [asset_id, kv, country, role, lon, lat] */
  buses: [number | null, number, string | null, string, number, number][];
  /** [kind, asset_ids, kv] */
  branches: [string, number[], number][];
  /** [asset_id, fuel, p_max] */
  generators: [number | null, string | null, number][];
};
export type ScenarioEvent = { id?: string; at: string; type: string; label: string; targets?: number[]; match?: Record<string, unknown>[]; payload?: Record<string, any>; source_url?: string | null };
export type Scenario = {
  id: string; name: string; mode: "historical" | "whatif"; description: string; countries: string[]; as_of: string;
  start_at: string; end_at: string; step_hours: number; events: ScenarioEvent[]; uncertainty: Record<string, any>;
  expected: { checks?: Omit<Check, "model" | "ok" | "at_model">[] }; sources: { title: string; url: string }[]; author: string;
  assets?: Record<string, { id: number; kind: string; name: string | null; max_voltage_kv: number | null; capacity_mw: number | null; fuel: string | null; country: string | null; lon: number; lat: number }>;
};
export type ScenarioListItem = { id: string; name: string; mode: "historical" | "whatif"; description: string; countries: string[]; start_at: string; end_at: string; events: number; author: string; last_run_id: string | null; last_run_status: string | null; last_run_kind: string | null };

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

export const runApi = {
  scenarios: () => request<{ items: ScenarioListItem[]; event_types: Record<string, string> }>("/grid/scenarios"),
  scenario: (id: string) => request<Scenario>(`/grid/scenarios/${encodeURIComponent(id)}`),
  saveScenario: (body: Record<string, unknown>, id?: string) =>
    id ? request<Scenario>(`/grid/scenarios/${encodeURIComponent(id)}`, json("PUT", body)) : request<Scenario>("/grid/scenarios", json("POST", body)),
  deleteScenario: (id: string) => request<{ deleted: string }>(`/grid/scenarios/${encodeURIComponent(id)}`, json("DELETE")),
  startRun: (id: string, body: { kind: string; members?: number; seed?: number }) => request<Run>(`/grid/scenarios/${encodeURIComponent(id)}/runs`, json("POST", body)),
  runs: (id: string) => request<{ items: Run[] }>(`/grid/scenarios/${encodeURIComponent(id)}/runs`),
  run: (id: string) => request<Run>(`/grid/runs/${id}`),
  frames: (id: string) => request<{ items: Frame[] }>(`/grid/runs/${id}/frames`, undefined, 60_000),
  network: (snapshot: number) => request<SnapshotNetwork>(`/grid/snapshots/${snapshot}/network`, undefined, 60_000),
};

export type FeatureStates = {
  lines: Map<number, Record<string, unknown>>;
  substations: Map<number, Record<string, unknown>>;
  plants: Map<number, Record<string, unknown>>;
};

/** Feature-states of one frame: line loading and outages, dead substations, lost plants, event
 * targets, and territory outside the operator's control (``occ``: not an outage). */
export function frameStates(network: SnapshotNetwork, frame: Frame, plantAssets: Set<number> = new Set()): FeatureStates {
  const lines = new Map<number, Record<string, unknown>>();
  const substations = new Map<number, Record<string, unknown>>();
  const plants = new Map<number, Record<string, unknown>>();
  const down = new Set([...frame.state.br_out, ...frame.state.br_trip]);
  const occupiedBranches = new Set(frame.state.br_occ ?? []);
  const occupiedBuses = new Set(frame.state.bus_occ ?? []);
  frame.state.load.forEach((pct, index) => {
    const branch = network.branches[index];
    if (!branch || branch[0] === "transformer") return;
    for (const asset of branch[1]) {
      const current = lines.get(asset);
      if (occupiedBranches.has(index)) {
        if (!current) lines.set(asset, { off: false, occ: true, load: null });
      } else if (down.has(index) || pct < 0) lines.set(asset, { off: true, load: null });
      else if (!current || (current.load as number) < pct / 100) lines.set(asset, { off: false, load: pct / 100 });
    }
  });
  const deadBuses = new Set([...frame.state.bus_out, ...frame.state.bus_dead]);
  // A substation is off when all of its buses are.
  const busesOf = new Map<number, number[]>();
  network.buses.forEach((bus, index) => {
    if (bus[0] == null) return;
    busesOf.set(bus[0], [...(busesOf.get(bus[0]) ?? []), index]);
  });
  for (const [asset, indices] of busesOf) {
    const occ = indices.every((i) => occupiedBuses.has(i));
    const off = !occ && indices.every((i) => deadBuses.has(i));
    if (plantAssets.has(asset)) plants.set(asset, { off, occ });
    else substations.set(asset, { off, occ });
  }
  for (const index of frame.state.gen_out) {
    const asset = network.generators[index]?.[0];
    if (asset != null && !plants.get(asset)?.occ) plants.set(asset, { off: true, occ: false });
  }
  for (const event of frame.events) {
    for (const target of event.targets) {
      for (const map of [lines, substations, plants]) {
        if (map.has(target)) map.set(target, { ...map.get(target), hit: true });
      }
      if (!lines.has(target) && !substations.has(target) && !plants.has(target)) plants.set(target, { hit: true });
    }
  }
  return { lines, substations, plants };
}

/** Index of the frame shown at a moment: the last frame at or before it. */
export function frameAt(frames: Frame[], time: number): number {
  let lo = 0;
  let hi = frames.length - 1;
  if (hi < 0) return -1;
  if (time <= Date.parse(frames[0].at)) return 0;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (Date.parse(frames[mid].at) <= time) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/** Frames that carry events, for the markers of the timeline. */
export function eventFrames(frames: Frame[]): number[] {
  return frames.flatMap((f, i) => (f.events.some((e) => e.origin !== "repair") ? [i] : []));
}

export function nextEvent(frames: Frame[], index: number, direction: 1 | -1): number {
  const marks = eventFrames(frames);
  if (direction > 0) return marks.find((i) => i > index) ?? index;
  return [...marks].reverse().find((i) => i < index) ?? index;
}
