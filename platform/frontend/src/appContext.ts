import { useSyncExternalStore } from "react";

/** Model layer: each one is a separate database on the API side. */
export type LayerId = "dev" | "preprod" | "prod";
export const LAYER_IDS: LayerId[] = ["dev", "preprod", "prod"];
export const LAYER_HEADER = "X-Aftertime-Layer";

/** What the top bar selects for every page: layer, scope and reporting period. */
export type AppContext = {
  layer: LayerId;
  scope: string;
  /** Inclusive calendar dates, YYYY-MM-DD. */
  from: string;
  to: string;
};

const STORAGE_KEY = "aftertime.context";
export const DEFAULT_CONTEXT: AppContext = { layer: "dev", scope: "place:earth", from: "2023-01-01", to: "2023-12-31" };
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export function parseLayer(value: string | null | undefined): LayerId | null {
  const normalised = (value || "").toLowerCase().replace("-", "");
  return (LAYER_IDS as string[]).includes(normalised) ? (normalised as LayerId) : null;
}

/** Merge URL parameters over stored values over defaults, dropping invalid ones. */
export function resolveContext(search: string, stored: Partial<AppContext> | null): AppContext {
  const params = new URLSearchParams(search);
  const pick = (key: keyof AppContext) => params.get(key) ?? stored?.[key] ?? null;
  const from = pick("from"), to = pick("to");
  const context: AppContext = {
    layer: parseLayer(pick("layer")) ?? DEFAULT_CONTEXT.layer,
    scope: pick("scope") || DEFAULT_CONTEXT.scope,
    from: from && DATE.test(from) ? from : DEFAULT_CONTEXT.from,
    to: to && DATE.test(to) ? to : DEFAULT_CONTEXT.to,
  };
  if (context.to < context.from) context.to = context.from;
  return context;
}

function readStored(): Partial<AppContext> | null {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
  } catch {
    return null;
  }
}

let state: AppContext =
  typeof window === "undefined" ? DEFAULT_CONTEXT : resolveContext(window.location.search, readStored());
const listeners = new Set<() => void>();

export function getContext(): AppContext {
  return state;
}

function persist(): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Storage may be unavailable (private mode); the URL still carries the context.
  }
  const params = new URLSearchParams(window.location.search);
  params.set("layer", state.layer);
  window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
}

/** Update the context. A layer change reloads the page: every view refetches from the new database. */
export function setContext(patch: Partial<AppContext>): void {
  const layerChanged = patch.layer !== undefined && patch.layer !== state.layer;
  state = { ...state, ...patch };
  if (typeof window === "undefined") return;
  persist();
  if (layerChanged) {
    window.location.reload();
    return;
  }
  listeners.forEach((listener) => listener());
}

export function useAppContext(): AppContext {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getContext,
    getContext,
  );
}

/** Link to another page that keeps the current layer in the URL. */
export function hrefWithLayer(path: string, layer: LayerId = state.layer): string {
  const [base, query = ""] = path.split("?");
  const params = new URLSearchParams(query);
  params.set("layer", layer);
  return `${base}?${params}`;
}

/** Inclusive calendar period → API bounds: [from 00:00 UTC, day after `to` 00:00 UTC). */
export function periodBounds(from: string, to: string): { from: string; to: string } {
  const end = new Date(`${to}T00:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 1);
  return { from: `${from}T00:00:00Z`, to: end.toISOString().replace(".000Z", "Z") };
}

/** Preset periods for the period picker. */
export function yearPeriod(year: number): Pick<AppContext, "from" | "to"> {
  return { from: `${year}-01-01`, to: `${year}-12-31` };
}

export function quarterPeriod(year: number, quarter: 1 | 2 | 3 | 4): Pick<AppContext, "from" | "to"> {
  const startMonth = (quarter - 1) * 3;
  const last = new Date(Date.UTC(year, startMonth + 3, 0));
  const pad = (n: number) => String(n).padStart(2, "0");
  return { from: `${year}-${pad(startMonth + 1)}-01`, to: `${year}-${pad(startMonth + 3)}-${pad(last.getUTCDate())}` };
}
