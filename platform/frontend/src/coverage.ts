import { useSyncExternalStore } from "react";
import { request } from "./api";

/** Dates the world is computed for in the current layer (inclusive calendar dates). */
export type Coverage = {
  source: "computation" | "events";
  computation_id: string | null;
  from: string;
  to: string;
  history_to: string;
  forecast: boolean;
  computed_at: string | null;
  parameters: { horizon?: string; growth_pct?: number; method?: string };
};

export type YearFlow = { year: number; bbl_per_day: number; provenance: string; reference: string | null };

export type Computation = {
  id: string;
  status: string;
  from: string;
  to: string;
  history_to: string;
  parameters: Coverage["parameters"];
  summary: { events?: number; cargoes?: number; provenance?: Record<string, number> };
  note: string;
  duration_ms: number;
  created_at: string;
};

export type CoverageOverview = {
  layer: string;
  computable: boolean;
  coverage: Coverage | null;
  limits: { min_horizon: string; max_horizon: string; history_from: string; history_to: string; max_growth_pct: number };
  flows: YearFlow[];
  computations: Computation[];
};

type State = { status: "loading" | "ready" | "error"; overview: CoverageOverview | null; error: string | null };

let state: State = { status: "loading", overview: null, error: null };
let started = false;
const listeners = new Set<() => void>();

function emit(next: State): void {
  state = next;
  listeners.forEach((listener) => listener());
}

/** Fetch (again) how far the world is computed. Every page shares one copy. */
export function refreshCoverage(): Promise<void> {
  started = true;
  return request<CoverageOverview>("/world/coverage")
    .then((overview) => emit({ status: "ready", overview, error: null }))
    .catch((reason) => emit({ status: "error", overview: null, error: String(reason?.message || reason) }));
}

export function setCoverage(overview: CoverageOverview): void {
  emit({ status: "ready", overview, error: null });
}

export function useCoverage(): State {
  if (!started && typeof window !== "undefined") void refreshCoverage();
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => state,
    () => state,
  );
}

/** True when the inclusive period lies inside the coverage. */
export function periodCovered(from: string, to: string, coverage: Coverage | null): boolean {
  return !!coverage && from >= coverage.from && to <= coverage.to && from <= to;
}

/**
 * Bring a period inside the coverage: intersect it, or take the last covered calendar
 * year (cut to the coverage) when the two do not overlap. Null without coverage.
 */
export function clampPeriod(from: string, to: string, coverage: Coverage | null): { from: string; to: string } | null {
  if (!coverage) return null;
  if (periodCovered(from, to, coverage)) return { from, to };
  const lo = from > coverage.from ? from : coverage.from;
  const hi = to < coverage.to ? to : coverage.to;
  if (lo <= hi) return { from: lo, to: hi };
  const year = coverage.to.slice(0, 4);
  const start = `${year}-01-01`;
  return { from: start > coverage.from ? start : coverage.from, to: coverage.to };
}

/** Years with at least one covered day, newest first. */
export function coveredYears(coverage: Coverage | null): number[] {
  if (!coverage) return [];
  const first = Number(coverage.from.slice(0, 4));
  const last = Number(coverage.to.slice(0, 4));
  return Array.from({ length: last - first + 1 }, (_, i) => last - i);
}

/** Inclusive date `years` after `iso`, kept within [min, max]. */
export function shiftYears(iso: string, years: number, min: string, max: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y + years, m - 1, d));
  const shifted = date.toISOString().slice(0, 10);
  return shifted < min ? min : shifted > max ? max : shifted;
}

export const PROVENANCE_LABEL: Record<string, string> = { statistic: "статистика", derived: "похідні дані", assumed: "припущення", forecast: "прогноз" };
export const PROVENANCE_TONE: Record<string, string> = { statistic: "stat", derived: "derived", assumed: "assumed", forecast: "forecast" };
