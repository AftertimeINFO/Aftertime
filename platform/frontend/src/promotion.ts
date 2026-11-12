import type { LayerId } from "./appContext";

export type PromotionCandidate = {
  id: string;
  name: string;
  version: number;
  project_id: string;
  project_name: string;
  published_at: string | null;
  scenarios: string[];
  completed_runs: number;
  in_target: boolean;
  last_promotion: { source: LayerId; target: LayerId; at: string | null } | null;
};

export type PromotionCheck = { id: string; label: string; ok: boolean; detail: string };
export type PromotionTable = { table: string; label: string; new: number; same: number; kept: number; changed: number };

export type PromotionPlan = {
  version: { id: string; name: string; version: number; project_id: string; project_name: string };
  source: LayerId;
  target: LayerId;
  status: "ready" | "already" | "blocked" | "promoted";
  checks: PromotionCheck[];
  tables: PromotionTable[];
  totals: { new: number; same: number; kept: number; changed: number };
  conflicts: { table: string; label: string; id: string; columns: string[] }[];
  dangling: string[];
  scenarios: string[];
  versions: string[];
  promotion?: string | null;
};

export type PromotionRecord = {
  id: string;
  version_id: string;
  project_id: string;
  source: LayerId;
  target: LayerId;
  note: string;
  summary: { totals?: PromotionPlan["totals"]; versions?: string[]; scenarios?: string[] };
  created_at: string | null;
};

export type Candidates = { source: LayerId; target: LayerId | null; target_label: string | null; items: PromotionCandidate[]; history: PromotionRecord[] };

export const LAYER_LABEL: Record<LayerId, string> = { dev: "DEV", preprod: "prePROD", prod: "PROD" };
export const LADDER: LayerId[] = ["dev", "preprod", "prod"];

/** Short state of a candidate relative to the next layer. */
export function candidateState(item: PromotionCandidate, target: LayerId | null): { label: string; tone: "done" | "ready" | "wait" } {
  if (!target) return { label: "кінцевий шар", tone: "done" };
  if (item.in_target) return { label: `уже в ${LAYER_LABEL[target]}`, tone: "done" };
  if (target === "prod" && item.completed_runs === 0) return { label: "немає завершеного прогону", tone: "wait" };
  return { label: `можна в ${LAYER_LABEL[target]}`, tone: "ready" };
}

/** Candidates whose project, version name or scenario matches the query. */
export function filterCandidates(items: PromotionCandidate[], query: string): PromotionCandidate[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((item) => [item.project_name, item.name, item.id, ...item.scenarios].some((text) => text.toLowerCase().includes(needle)));
}
