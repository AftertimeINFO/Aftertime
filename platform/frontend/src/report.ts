import type { BalanceColumn, BalanceLevel, BalanceValues } from "./balance";

/** Reports built from one balance row: a turnover statement and a chart, by sub-period. */
export type ReportKind = "turnover" | "chart";
export type ReportStep = "month" | "quarter" | "year";

export type SeriesPoint = { from: string; to: string; values: BalanceValues };
export type Series = {
  scope: string;
  scope_name?: string;
  row: string;
  name: string;
  flow: string | null;
  flows: string[];
  level: BalanceLevel;
  step: ReportStep;
  unit: "kg";
  points: SeriesPoint[];
  totals: BalanceValues;
  sources?: { title: string; url?: string | null }[];
};

export const STEPS: { id: ReportStep; label: string; months: number }[] = [
  { id: "month", label: "місяць", months: 1 },
  { id: "quarter", label: "квартал", months: 3 },
  { id: "year", label: "рік", months: 12 },
];
export const MAX_POINTS = 120;

/** Flow columns of a series, in the order of the balance. */
export const FLOWS: BalanceColumn[] = ["inflow", "outflow", "transform", "carrier", "revision"];

/** Number of calendar months touched by an inclusive period (YYYY-MM-DD). */
export function monthsIn(from: string, to: string): number {
  const [fy, fm] = from.split("-").map(Number);
  const [ty, tm] = to.split("-").map(Number);
  return (ty - fy) * 12 + (tm - fm) + 1;
}

/** Points a step gives over a period (sub-periods follow calendar boundaries). */
export function pointsFor(from: string, to: string, step: ReportStep): number {
  const months = STEPS.find((s) => s.id === step)!.months;
  const [fy, fm] = from.split("-").map(Number);
  const [ty, tm] = to.split("-").map(Number);
  const first = Math.floor((fy * 12 + fm - 1) / months);
  const last = Math.floor((ty * 12 + tm - 1) / months);
  return last - first + 1;
}

/** The finest step that keeps a readable number of points (at most 36). */
export function defaultStep(from: string, to: string): ReportStep {
  if (pointsFor(from, to, "month") <= 36) return "month";
  if (pointsFor(from, to, "quarter") <= 36) return "quarter";
  return "year";
}

/** The chosen step, or the next coarser one when it would give too many points. */
export function fitStep(from: string, to: string, step: ReportStep): ReportStep {
  const order: ReportStep[] = ["month", "quarter", "year"];
  for (const candidate of order.slice(order.indexOf(step))) {
    if (pointsFor(from, to, candidate) <= MAX_POINTS) return candidate;
  }
  return "year";
}

const MONTHS = ["січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"];

/** Label of a sub-period from its start: "бер 2030", "Q2 2030", "2030". */
export function pointLabel(from: string, step: ReportStep): string {
  const [year, month] = from.slice(0, 10).split("-").map(Number);
  if (step === "year") return `${year}`;
  if (step === "quarter") return `Q${Math.floor((month - 1) / 3) + 1} ${year}`;
  return `${MONTHS[month - 1]} ${year}`;
}

/** Address of a report tab for a balance row (scope and period travel with the tab). */
export function reportUrl(kind: ReportKind, row: { id: string; name: string }, level: BalanceLevel, flow?: string): string {
  const params = new URLSearchParams({ row: row.id, name: row.name, level });
  if (flow) params.set("flow", flow);
  return `/report/${kind}?${params}`;
}

/** Round tick values covering [min, max], about ``count`` of them (with 0 unless told not to). */
export function niceTicks(min: number, max: number, count = 5, zero = true): number[] {
  let lo = zero ? Math.min(0, min) : min;
  let hi = zero ? Math.max(0, max) : max;
  if (hi === lo) {
    if (!zero && hi !== 0) {
      lo -= Math.abs(hi) * 0.01;
      hi += Math.abs(hi) * 0.01;
    } else return [0];
  }
  const raw = (hi - lo) / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? 10 * power;
  const ticks: number[] = [];
  for (let v = Math.floor(lo / step) * step; v <= hi + step * 1e-9; v += step) ticks.push(Number(v.toPrecision(12)));
  if (ticks[ticks.length - 1] < hi) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

/** Axis labels in one style: as many decimals as the tick step needs, no more. */
export function tickLabels(ticks: number[], unitKg: number): string[] {
  const step = ticks.length > 1 ? Math.abs(ticks[1] - ticks[0]) / unitKg : 1;
  const decimals = step > 0 ? Math.max(0, Math.min(3, -Math.floor(Math.log10(step) + 1e-9))) : 0;
  return ticks.map((tick) =>
    (tick / unitKg).toLocaleString("uk-UA", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }),
  );
}

/** Signed value of a flow column as drawn: outflow goes below the baseline. */
export function drawnValue(column: BalanceColumn, values: Partial<BalanceValues>): number {
  const value = values[column] ?? 0;
  return column === "outflow" ? -value : value;
}
