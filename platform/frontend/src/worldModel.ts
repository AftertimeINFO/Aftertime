// Pure playback helpers for the world pilot: balances and vessel positions at a time.
export type Posting = [string, number];
export type LedgerEvent = { id: string; t: string; type: string; provenance: string; attributes: Record<string, any>; postings: Posting[] };
export type Voyage = { id: string; vessel: string; route: string; direction: "laden" | "ballast"; cargo_kg: number; depart: string; arrive: string };
export type Place = { id: string; name: string; kind: string; type: string | null; geometry: any; z_min_m: number | null; z_max_m: number | null };
export type Portion = { id: string; holder: string; material: string };
export type PilotPayload = {
  run_id: string;
  source: { id: string; name: string; license: string };
  parameters: Record<string, any>;
  places: Place[];
  names: Record<string, string>;
  portions: Portion[];
  voyages: Voyage[];
  events: LedgerEvent[];
  estimate: null | { portion: string; value_kg: number; low_kg: number | null; high_kg: number | null; valid_time: string; evidence: Record<string, any> };
};
export type LngLat = [number, number];

export type Timeline = {
  times: number[];
  portions: string[];
  // cumulative balance per portion after each event: snapshots[i][j]
  snapshots: Float64Array[];
};

export function buildTimeline(events: LedgerEvent[], portions: string[]): Timeline {
  const index = new Map(portions.map((id, i) => [id, i]));
  const sorted = [...events].sort((a, b) => Date.parse(a.t) - Date.parse(b.t));
  const running = new Float64Array(portions.length);
  const snapshots: Float64Array[] = [];
  for (const event of sorted) {
    for (const [entity, delta] of event.postings) {
      const j = index.get(entity);
      if (j !== undefined) running[j] += delta;
    }
    snapshots.push(Float64Array.from(running));
  }
  return { times: sorted.map((e) => Date.parse(e.t)), portions, snapshots };
}

/** Index of the last event at or before t, or -1. */
export function lastIndexAt(times: number[], t: number): number {
  let lo = 0, hi = times.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= t) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found;
}

export function balancesAt(timeline: Timeline, t: number): Map<string, number> {
  const i = lastIndexAt(timeline.times, t);
  const row = i >= 0 ? timeline.snapshots[i] : new Float64Array(timeline.portions.length);
  return new Map(timeline.portions.map((id, j) => [id, row[j]]));
}

function segmentLength(a: LngLat, b: LngLat): number {
  const rad = Math.PI / 180, lat = ((a[1] + b[1]) / 2) * rad;
  const dx = (b[0] - a[0]) * Math.cos(lat), dy = b[1] - a[1];
  return Math.hypot(dx, dy);
}

/** Point at fraction f (0..1) of the line length. */
export function pointAlong(line: LngLat[], f: number): LngLat {
  if (line.length === 1) return line[0];
  const lengths = line.slice(1).map((p, i) => segmentLength(line[i], p));
  let target = Math.min(Math.max(f, 0), 1) * lengths.reduce((s, l) => s + l, 0);
  for (let i = 0; i < lengths.length; i++) {
    if (target <= lengths[i] || i === lengths.length - 1) {
      const k = lengths[i] ? Math.min(target / lengths[i], 1) : 0;
      return [line[i][0] + (line[i + 1][0] - line[i][0]) * k, line[i][1] + (line[i + 1][1] - line[i][1]) * k];
    }
    target -= lengths[i];
  }
  return line[line.length - 1];
}

export type VesselState = { vessel: string; position: LngLat; status: "laden" | "ballast" | "at-origin" | "at-destination"; progress: number; voyage?: Voyage };

/** Where each vessel is at t, interpolated along its route; berth position otherwise. */
export function vesselStates(voyages: Voyage[], routes: Record<string, LngLat[]>, t: number): VesselState[] {
  const byVessel = new Map<string, Voyage[]>();
  for (const v of voyages) byVessel.set(v.vessel, [...(byVessel.get(v.vessel) || []), v]);
  const states: VesselState[] = [];
  for (const [vessel, list] of byVessel) {
    const ordered = [...list].sort((a, b) => Date.parse(a.depart) - Date.parse(b.depart));
    const line = routes[ordered[0].route] || [];
    const origin = line[0], destination = line[line.length - 1];
    let state: VesselState = { vessel, position: origin, status: "at-origin", progress: 0 };
    for (const v of ordered) {
      const d = Date.parse(v.depart), a = Date.parse(v.arrive);
      if (t < d) break;
      const laden = v.direction === "laden";
      if (t < a) {
        const f = (t - d) / (a - d);
        state = { vessel, position: pointAlong(line, laden ? f : 1 - f), status: v.direction, progress: f, voyage: v };
        break;
      }
      state = laden
        ? { vessel, position: destination, status: "at-destination", progress: 1, voyage: v }
        : { vessel, position: origin, status: "at-origin", progress: 1, voyage: v };
    }
    states.push(state);
  }
  return states.sort((a, b) => a.vessel.localeCompare(b.vessel));
}
