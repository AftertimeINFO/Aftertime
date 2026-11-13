import { createContext, useContext, useSyncExternalStore } from "react";

/**
 * Workspace tabs: every page opens in a tab under the top bar.
 *
 * A tab keeps its own address (path and query) and, for pages that read them, its own
 * scope and period. Balance tabs can be opened many times (one per object); every other
 * page has one tab that is focused again. The tabs survive reloads (localStorage); the
 * address bar always shows the active tab, so a link to it can be shared.
 */
export type TabKind = "balance" | "turnover" | "chart" | "movements" | "world" | "entities" | "energy" | "lab" | "compute" | "promote";

export type Tab = {
  id: string;
  kind: TabKind;
  /** Path and query of the page, without the layer parameter. */
  url: string;
  scope?: string;
  /** Name of the scope, for the tab title (scopes outside the scope tree keep it). */
  scopeName?: string;
  from?: string;
  to?: string;
  /** Bumped when the page must start again from a new address. */
  rev: number;
};

export type TabsState = { tabs: Tab[]; active: string | null };

export const MULTI: ReadonlySet<TabKind> = new Set(["balance", "turnover", "chart", "movements"]);
/** Pages that report on a scope and keep it (with the period) in the tab. */
export const SCOPED: ReadonlySet<TabKind> = new Set(["balance", "turnover", "chart", "movements"]);
const STORAGE_KEY = "aftertime.tabs";
const MAX_TABS = 24;

/** Page kind of an address, or null for an address outside the app. */
export function kindOfPath(path: string): TabKind | null {
  const clean = path.split("?")[0].replace(/\/+$/, "") || "/";
  if (clean === "/" || clean === "/balance") return "balance";
  if (clean === "/report/turnover") return "turnover";
  if (clean === "/report/chart") return "chart";
  if (clean === "/report/movements") return "movements";
  if (clean.startsWith("/world/entities")) return "entities";
  if (clean === "/world" || clean.startsWith("/world/")) return "world";
  if (clean === "/energy" || clean.startsWith("/energy/")) return "energy";
  if (clean.startsWith("/lab")) return "lab";
  if (clean.startsWith("/compute")) return "compute";
  if (clean.startsWith("/promote")) return "promote";
  return null;
}

export const HOME: Record<TabKind, string> = {
  balance: "/",
  turnover: "/report/turnover",
  chart: "/report/chart",
  movements: "/report/movements",
  world: "/world",
  entities: "/world/entities",
  energy: "/energy",
  lab: "/lab",
  compute: "/compute",
  promote: "/promote",
};

/** Address without the layer parameter (the layer belongs to the whole window). */
export function stripLayer(url: string): string {
  const [path, query = ""] = url.split("?");
  const params = new URLSearchParams(query);
  params.delete("layer");
  const search = params.toString();
  return `${path}${search ? `?${search}` : ""}`;
}

export function tabTitle(tab: Tab): string {
  switch (tab.kind) {
    case "balance":
      return `Баланс · ${tab.scopeName || tab.scope || "Earth"}`;
    case "turnover":
    case "chart":
    case "movements": {
      const query = new URLSearchParams(tab.url.split("?")[1] || "");
      const subject = [query.get("name") || query.get("row"), query.get("flow")].filter(Boolean).join(" · ");
      const kind = tab.kind === "chart" ? "Графік" : tab.kind === "turnover" ? "Обороти" : "Рухи";
      return [kind, subject, tab.scopeName || tab.scope || "Earth"].filter(Boolean).join(" · ");
    }
    case "world":
      return "Світ · програвання";
    case "entities":
      return "Сутності";
    case "energy":
      return "Енергосистема";
    case "lab":
      return "Моделі";
    case "compute":
      return "Розрахунок світу";
    case "promote":
      return "Випуск моделей";
  }
}

let counter = 0;
function newId(): string {
  counter += 1;
  return `t${Date.now().toString(36)}${counter.toString(36)}`;
}

// ----- pure transitions (tested) -----

export type OpenRequest = { kind: TabKind; url?: string; scope?: string; scopeName?: string; from?: string; to?: string; forceNew?: boolean };

/** Open a page: a new tab for balances (or forceNew), else focus the single tab of that page. */
export function openIn(state: TabsState, request: OpenRequest, id: string = newId()): TabsState {
  const { kind, url, forceNew, ...params } = request;
  const existing = !forceNew && !MULTI.has(kind) ? state.tabs.find((t) => t.kind === kind) : undefined;
  if (existing) {
    const target = url ? stripLayer(url) : existing.url;
    const tabs = state.tabs.map((t) =>
      t.id === existing.id ? { ...t, ...definedOnly(params), url: target, rev: target !== t.url ? t.rev + 1 : t.rev } : t,
    );
    return { tabs, active: existing.id };
  }
  const tab: Tab = { id, kind, url: url ? stripLayer(url) : HOME[kind], rev: 0, ...definedOnly(params) };
  const at = state.tabs.findIndex((t) => t.id === state.active);
  const tabs = [...state.tabs];
  tabs.splice(at < 0 ? tabs.length : at + 1, 0, tab);
  // Too many tabs: drop the oldest inactive balance tabs first.
  while (tabs.length > MAX_TABS) {
    const drop = tabs.findIndex((t) => t.id !== id && t.id !== state.active);
    if (drop < 0) break;
    tabs.splice(drop, 1);
  }
  return { tabs, active: id };
}

/** Close a tab; the neighbour on the right (else left) becomes active. */
export function closeIn(state: TabsState, id: string): TabsState {
  const index = state.tabs.findIndex((t) => t.id === id);
  if (index < 0) return state;
  const tabs = state.tabs.filter((t) => t.id !== id);
  if (state.active !== id) return { tabs, active: state.active };
  const next = tabs[index] ?? tabs[index - 1] ?? null;
  return { tabs, active: next?.id ?? null };
}

/** Tabs after loading an address: reuse the active tab of that page, else open one. */
export function restoreFor(state: TabsState, url: string, defaults: Partial<Tab> = {}): TabsState {
  const kind = kindOfPath(url);
  if (!kind) return state;
  const clean = stripLayer(url);
  const active = state.tabs.find((t) => t.id === state.active);
  const linkedScope = new URLSearchParams(clean.split("?")[1] || "").get("scope");
  const sameScope = !SCOPED.has(kind) || !linkedScope || linkedScope === active?.scope;
  const sameReport = kind === "balance" || !MULTI.has(kind) || (!!active && reportKey(clean) === reportKey(active.url));
  if (active && active.kind === kind && sameScope && sameReport) {
    return { ...state, tabs: state.tabs.map((t) => (t.id === active.id ? { ...t, url: clean } : t)) };
  }
  const params = new URLSearchParams(clean.split("?")[1] || "");
  const scope = params.get("scope") || undefined;
  return openIn(state, {
    kind,
    url: clean,
    scope: SCOPED.has(kind) ? scope ?? defaults.scope : undefined,
    from: params.get("from") || defaults.from,
    to: params.get("to") || defaults.to,
  });
}

/** What a report shows (page, row, flow, level); scope, period and step may differ. */
function reportKey(url: string): string {
  const [path, query = ""] = url.split("?");
  const params = new URLSearchParams(query);
  return [path, params.get("row"), params.get("flow"), params.get("level")].join("|");
}

function definedOnly<T extends object>(value: T): Partial<T> {
  return Object.fromEntries(Object.entries(value).filter(([, v]) => v !== undefined)) as Partial<T>;
}

// ----- store -----

function read(): TabsState {
  try {
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
    if (stored && Array.isArray(stored.tabs)) {
      const tabs = (stored.tabs as Tab[]).filter((t) => t && t.id && kindOfPath(HOME[t.kind] ?? "x"));
      return { tabs: tabs.map((t) => ({ ...t, rev: 0 })), active: tabs.some((t) => t.id === stored.active) ? stored.active : tabs[0]?.id ?? null };
    }
  } catch {
    // Unreadable storage: start with no tabs.
  }
  return { tabs: [], active: null };
}

let state: TabsState = { tabs: [], active: null };
// Scope and period of the window when a tab opens: each tab keeps its own copy.
let defaults: { scope?: string; from?: string; to?: string } = {};
export function setTabDefaults(next: typeof defaults): void {
  defaults = next;
}
const listeners = new Set<() => void>();

function layerQuery(url: string): string {
  const layer = new URLSearchParams(window.location.search).get("layer");
  if (!layer) return url;
  const [path, query = ""] = url.split("?");
  const params = new URLSearchParams(query);
  params.set("layer", layer);
  return `${path}?${params}`;
}

/** Address a tab shows in the address bar: a balance carries its scope and period. */
export function addressOf(tab: Tab): string {
  if (!SCOPED.has(tab.kind)) return tab.url;
  const [path, query = ""] = tab.url.split("?");
  const params = new URLSearchParams(query);
  if (tab.scope) params.set("scope", tab.scope);
  if (tab.from) params.set("from", tab.from);
  if (tab.to) params.set("to", tab.to);
  const search = params.toString();
  return `${path || "/"}${search ? `?${search}` : ""}`;
}

function commit(next: TabsState): void {
  const before = state.tabs.find((t) => t.id === state.active);
  const after = next.tabs.find((t) => t.id === next.active);
  state = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Not persisted when storage is unavailable.
  }
  if (after && (after.id !== before?.id || addressOf(after) !== stripLayer(window.location.pathname + window.location.search))) {
    window.history.replaceState(null, "", layerQuery(addressOf(after)));
  }
  listeners.forEach((listener) => listener());
}

/** Load the stored tabs and match them to the address the page was opened with. */
export function initTabs(initial: Partial<Tab>): void {
  defaults = { scope: initial.scope, from: initial.from, to: initial.to };
  state = restoreFor(read(), window.location.pathname + window.location.search, initial);
  if (!state.tabs.length) state = openIn(state, { kind: "balance", ...initial });
  commit(state);
}

export function getTabs(): TabsState {
  return state;
}

export function useTabs(): TabsState {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => state,
    () => state,
  );
}

/** Remember the address of the active page before another tab takes the window. */
function captureActive(current: TabsState): TabsState {
  const url = stripLayer(window.location.pathname + window.location.search);
  return { ...current, tabs: current.tabs.map((t) => (t.id === current.active && kindOfPath(url) === t.kind ? { ...t, url } : t)) };
}

export function openTab(request: OpenRequest): void {
  // A new tab takes the period of the tab it is opened from.
  const from = state.tabs.find((t) => t.id === state.active);
  const pinned: OpenRequest = { ...request, from: request.from ?? from?.from ?? defaults.from, to: request.to ?? from?.to ?? defaults.to };
  if (SCOPED.has(request.kind)) pinned.scope = request.scope ?? from?.scope ?? defaults.scope;
  commit(openIn(captureActive(state), pinned));
}

export function activateTab(id: string): void {
  if (id === state.active) return;
  commit({ ...captureActive(state), active: id });
}

export function closeTab(id: string): void {
  commit(closeIn(captureActive(state), id));
}

export function updateTab(id: string, patch: Partial<Omit<Tab, "id" | "kind">>): void {
  if (!state.tabs.some((t) => t.id === id)) return;
  commit({ ...state, tabs: state.tabs.map((t) => (t.id === id ? { ...t, ...patch } : t)) });
}

/** Open an in-app link in a tab. Returns false for an address outside the app. */
export function openUrl(url: string): boolean {
  const kind = kindOfPath(url);
  if (!kind) return false;
  // A link into another layer reloads the window in that layer.
  const layer = new URLSearchParams(url.split("?")[1] || "").get("layer");
  if (layer && layer !== new URLSearchParams(window.location.search).get("layer")) return false;
  const query = new URLSearchParams(url.split("?")[1] || "");
  openTab({ kind, url, scope: SCOPED.has(kind) ? query.get("scope") || undefined : undefined });
  return true;
}

// ----- per-pane access -----

/** Id of the tab a page is rendered in (null outside the tab host). */
export const PaneContext = createContext<string | null>(null);

export function usePaneTab(): Tab | null {
  const id = useContext(PaneContext);
  const { tabs } = useTabs();
  return tabs.find((t) => t.id === id) ?? null;
}

/** Query of the tab's address at the time the page mounted. */
export function tabParams(id: string | null): URLSearchParams {
  const tab = state.tabs.find((t) => t.id === id);
  return new URLSearchParams((tab?.url ?? window.location.pathname + window.location.search).split("?")[1] || "");
}

/** Replace the query of a tab's address; the address bar follows only for the active tab. */
export function replaceTabQuery(id: string | null, params: URLSearchParams): void {
  const tab = state.tabs.find((t) => t.id === id);
  if (!tab) {
    const search = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${search ? `?${search}` : ""}`);
    return;
  }
  params.delete("layer");
  const search = params.toString();
  const url = `${tab.url.split("?")[0]}${search ? `?${search}` : ""}`;
  if (url !== tab.url) updateTab(tab.id, { url });
}
