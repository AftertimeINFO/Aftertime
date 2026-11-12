import { useEffect, useState } from "react";
import { hrefWithLayer, quarterPeriod, useAppContext, yearPeriod } from "./appContext";
import { clampPeriod, periodCovered, useCoverage, type Coverage } from "./coverage";
import { updateTab, usePaneTab } from "./tabs";

/** Shape of a period inside its year: the whole year, a quarter, or arbitrary dates. */
export type PeriodMode = "year" | "q1" | "q2" | "q3" | "q4" | "custom";

const MODES: { id: PeriodMode; label: string }[] = [
  { id: "year", label: "увесь рік" },
  { id: "q1", label: "Q1" },
  { id: "q2", label: "Q2" },
  { id: "q3", label: "Q3" },
  { id: "q4", label: "Q4" },
  { id: "custom", label: "довільний" },
];
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export function periodMode(from: string, to: string): PeriodMode {
  const year = Number(from.slice(0, 4));
  if (to.slice(0, 4) !== from.slice(0, 4)) return "custom";
  const full = yearPeriod(year);
  if (full.from === from && full.to === to) return "year";
  for (const q of [1, 2, 3, 4] as const) {
    const quarter = quarterPeriod(year, q);
    if (quarter.from === from && quarter.to === to) return `q${q}`;
  }
  return "custom";
}

/**
 * Period of the given shape in the given year, moved inside the coverage.
 * Null when the year has no computed days at all.
 */
export function periodIn(year: number, mode: PeriodMode, coverage: Coverage | null, current?: { from: string; to: string }): { from: string; to: string } | null {
  if (!Number.isInteger(year) || year < 1000 || year > 9999) return null;
  let period: { from: string; to: string };
  if (mode === "year") period = yearPeriod(year);
  else if (mode === "custom" && current) {
    // Arbitrary dates keep their days and move to the new year.
    const span = Number(current.to.slice(0, 4)) - Number(current.from.slice(0, 4));
    period = { from: `${year}${current.from.slice(4)}`, to: `${year + span}${current.to.slice(4)}` };
    if (period.from.endsWith("-02-29") || period.to.endsWith("-02-29")) period = yearPeriod(year);
  } else if (mode === "custom") period = yearPeriod(year);
  else period = quarterPeriod(year, Number(mode.slice(1)) as 1 | 2 | 3 | 4);
  if (!coverage || period.to < coverage.from || period.from > coverage.to) return null;
  return clampPeriod(period.from, period.to, coverage);
}

/** Reporting period of one tab (a balance or the world player), limited to the computed coverage. */
export function PeriodPicker() {
  const context = useAppContext();
  const tab = usePaneTab();
  // The period belongs to this tab only.
  const setPeriod = (period: { from?: string; to?: string }) => {
    if (tab) updateTab(tab.id, period);
  };
  const covered = useCoverage();
  const coverage = covered.overview?.coverage ?? null;
  const ready = covered.status === "ready";
  // A period without a computation is moved inside the coverage.
  useEffect(() => {
    if (!tab || !ready || !coverage || periodCovered(context.from, context.to, coverage)) return;
    const next = clampPeriod(context.from, context.to, coverage);
    if (next) setPeriod(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab?.id, ready, coverage, context.from, context.to]);

  // Typed values stay drafts until they form a computed period.
  const year = context.from.slice(0, 4);
  const [yearDraft, setYearDraft] = useState(year);
  const [fromDraft, setFromDraft] = useState(context.from);
  const [toDraft, setToDraft] = useState(context.to);
  useEffect(() => setYearDraft(year), [year]);
  useEffect(() => setFromDraft(context.from), [context.from]);
  useEffect(() => setToDraft(context.to), [context.to]);

  const mode = periodMode(context.from, context.to);
  const locked = ready && !coverage;
  const firstYear = coverage ? Number(coverage.from.slice(0, 4)) : undefined;
  const lastYear = coverage ? Number(coverage.to.slice(0, 4)) : undefined;
  const yearOk = (value: string) => /^\d{4}$/.test(value) && !!periodIn(Number(value), mode, coverage, context);

  const applyYear = (value: string) => {
    const next = /^\d{4}$/.test(value) ? periodIn(Number(value), mode, coverage, context) : null;
    if (next) setPeriod(next);
    else setYearDraft(year);
  };
  const typeYear = (value: string) => {
    const digits = value.replace(/\D/g, "").slice(0, 4);
    setYearDraft(digits);
    // Four digits of a computed year apply at once.
    if (digits.length === 4 && digits !== year && yearOk(digits)) applyYear(digits);
  };
  const typeDate = (which: "from" | "to", value: string) => {
    (which === "from" ? setFromDraft : setToDraft)(value);
    const from = which === "from" ? value : context.from;
    const to = which === "to" ? value : context.to;
    if (DATE.test(value) && periodCovered(from, to, coverage)) setPeriod({ [which]: value });
  };
  const draftBad = (value: string, which: "from" | "to") => value !== (which === "from" ? context.from : context.to);

  const title = locked
    ? "У шарі ще немає розрахунку світу: період недоступний"
    : coverage
      ? `Доступно ${coverage.from} — ${coverage.to}${coverage.forecast ? ` (прогноз після ${coverage.history_to})` : ""}`
      : "";
  return (
    <div className={`period-picker ${locked ? "locked" : ""}`} title={title}>
      <small>
        ПЕРІОД
        <a href={hrefWithLayer("/compute")} className={`period-coverage ${coverage?.forecast ? "forecast" : ""}`} title="Налаштувати горизонт розрахунку">
          {locked ? "немає розрахунку" : coverage ? `розраховано до ${coverage.to.split("-").reverse().join(".")}` : "…"}
        </a>
      </small>
      <div>
        <input
          className={`period-year ${yearDraft !== year && !yearOk(yearDraft) ? "bad" : ""}`}
          aria-label="Рік"
          inputMode="numeric"
          maxLength={4}
          value={yearDraft}
          disabled={!coverage}
          title={firstYear ? `Рік ${firstYear}–${lastYear}: наберіть цифрами, ↑/↓ — сусідній рік` : undefined}
          onFocus={(e) => e.target.select()}
          onChange={(e) => typeYear(e.target.value)}
          onBlur={() => applyYear(yearDraft)}
          onKeyDown={(e) => {
            if (e.key === "Enter") applyYear(yearDraft);
            else if (e.key === "Escape") setYearDraft(year);
            else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
              e.preventDefault();
              const next = periodIn(Number(year) + (e.key === "ArrowUp" ? 1 : -1), mode, coverage, context);
              if (next) setPeriod(next);
            }
          }}
        />
        <select
          aria-label="Частина року"
          value={mode}
          disabled={!coverage}
          onChange={(e) => {
            const chosen = e.target.value as PeriodMode;
            if (chosen === "custom") return;
            const next = periodIn(Number(year), chosen, coverage);
            if (next) setPeriod(next);
          }}
        >
          {MODES.map((m) => (
            <option key={m.id} value={m.id} disabled={m.id !== "custom" && m.id !== mode && !periodIn(Number(year), m.id, coverage)}>
              {m.label}
            </option>
          ))}
        </select>
        <input type="date" aria-label="Початок періоду" className={draftBad(fromDraft, "from") ? "bad" : ""} value={fromDraft} disabled={!coverage} min={coverage?.from} max={context.to}
          onChange={(e) => typeDate("from", e.target.value)} onBlur={() => setFromDraft(context.from)} />
        <span>—</span>
        <input type="date" aria-label="Кінець періоду" className={draftBad(toDraft, "to") ? "bad" : ""} value={toDraft} disabled={!coverage} min={context.from} max={coverage?.to}
          onChange={(e) => typeDate("to", e.target.value)} onBlur={() => setToDraft(context.to)} />
      </div>
    </div>
  );
}
