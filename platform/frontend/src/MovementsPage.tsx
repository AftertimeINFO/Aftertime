import { useContext, useEffect, useState } from "react";
import { request } from "./api";
import { periodBounds, useAppContext } from "./appContext";
import { MASS_UNITS, formatAmount, type MassUnit } from "./balance";
import { PROVENANCE_LABEL, PROVENANCE_TONE, periodCovered, useCoverage } from "./coverage";
import { PeriodPicker } from "./PeriodSelect";
import { SourcesBadge, type Source } from "./Sources";
import { PaneContext, openTab, tabParams, updateTab, usePaneTab } from "./tabs";

type MovementColumn = "inflow" | "outflow" | "transform" | "carrier" | "revision" | "internal";
type Movement = {
  at: string;
  event: string | null;
  movement: string;
  material: string;
  material_name: string;
  column: MovementColumn;
  amount: number;
  provenance: string;
  sources: Source[];
};
type Movements = {
  scope: string;
  scope_name: string;
  row: string | null;
  flow: string | null;
  total: number;
  offset: number;
  limit: number;
  totals: Record<MovementColumn, number>;
  rows: Movement[];
};

const COLUMNS: { id: MovementColumn; label: string; signed?: boolean }[] = [
  { id: "inflow", label: "Надходження" },
  { id: "outflow", label: "Вибуття" },
  { id: "transform", label: "Трансформація", signed: true },
  { id: "carrier", label: "З носієм", signed: true },
  { id: "revision", label: "Переоцінка", signed: true },
  { id: "internal", label: "Внутрішній оборот" },
];
const PAGE = 200;

function moment(iso: string): string {
  const date = new Date(iso);
  return `${date.toLocaleDateString("uk-UA", { timeZone: "UTC", day: "2-digit", month: "2-digit", year: "numeric" })} ${date.toLocaleTimeString("uk-UA", { timeZone: "UTC", hour: "2-digit", minute: "2-digit" })}`;
}

/** Movements (events) that make up a balance: of a scope and period, optionally one row and flow. */
export default function MovementsPage() {
  const context = useAppContext();
  const pane = useContext(PaneContext);
  const tab = usePaneTab();
  const [query] = useState(() => tabParams(pane));
  const row = query.get("row") || undefined;
  const name = query.get("name") || row;
  const flow = query.get("flow") || undefined;
  const [data, setData] = useState<Movements | null>(null);
  const [rows, setRows] = useState<Movement[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [unit, setUnit] = useState<MassUnit>("kt");
  const covered = useCoverage();
  const waiting = covered.status === "loading" || (covered.status === "ready" && !periodCovered(context.from, context.to, covered.overview?.coverage ?? null));

  const load = (offset: number, signal?: AbortSignal) => {
    const bounds = periodBounds(context.from, context.to);
    const params = new URLSearchParams({ scope: context.scope, from: bounds.from, to: bounds.to, offset: String(offset), limit: String(PAGE) });
    if (row) params.set("row", row);
    if (flow) params.set("flow", flow);
    setLoading(true);
    return request<Movements>(`/world/balance/movements?${params}`, { signal }, 120_000)
      .then((result) => {
        setData(result);
        setRows((current) => (offset ? [...current, ...result.rows] : result.rows));
        setError(null);
        if (pane && result.scope_name && !tab?.scopeName) updateTab(pane, { scopeName: result.scope_name });
      })
      .catch((reason) => {
        if (!signal?.aborted) setError(String(reason?.message || reason));
      })
      .finally(() => !signal?.aborted && setLoading(false));
  };

  useEffect(() => {
    if (waiting) return;
    const controller = new AbortController();
    setRows([]);
    void load(0, controller.signal);
    return () => controller.abort();
  }, [context.scope, context.from, context.to, context.layer, row, flow, waiting]); // eslint-disable-line react-hooks/exhaustive-deps

  const unitLabel = MASS_UNITS.find((u) => u.id === unit)?.label ?? unit;
  const shown = COLUMNS.filter((column) => data && (data.totals[column.id] || rows.some((r) => r.column === column.id)));

  return (
    <div className="balance-page report-page movements-page">
      <header className="balance-head">
        <div>
          <small>РУХИ · ПОДІЇ, ЩО ФОРМУЮТЬ БАЛАНС</small>
          <h1>
            {name || "Усі матеріали"}
            {flow && <span className="report-flow"> · {flow}</span>}
          </h1>
          <div className="balance-context">
            <div className="balance-scope">
              <small>SCOPE</small>
              <div className="balance-scope-line">
                <span className="scope-crumb-last">{tab?.scopeName || data?.scope_name || context.scope}</span>
              </div>
            </div>
            <PeriodPicker />
          </div>
        </div>
        <div className="balance-controls">
          <button
            className="report-switch"
            onClick={() => openTab({ kind: "balance", scope: context.scope, scopeName: tab?.scopeName, from: context.from, to: context.to })}
          >
            Σ Баланс scope
          </button>
          <label className="balance-unit">
            Одиниці
            <select value={unit} onChange={(e) => setUnit(e.target.value as MassUnit)}>
              {MASS_UNITS.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
            </select>
          </label>
        </div>
      </header>

      {error && <div className="balance-message bad">{error}</div>}
      {!data && !error && <div className="balance-message">Збір рухів…</div>}
      {data && !data.total && <div className="balance-message">За цей період рухів немає.</div>}
      {data && !!data.total && (
        <>
          <p className="balance-note">
            {data.total.toLocaleString("uk-UA")} рухів, маса в {unitLabel}. Кожен рух — частина однієї події, що стосується scope; сума рухів дорівнює оборотам балансу.
          </p>
          <div className={`balance-table-wrap ${loading ? "loading" : ""}`}>
            <table className="balance-table movements-table">
              <thead>
                <tr>
                  <th className="balance-name">Дата, UTC</th>
                  <th className="balance-name">Рух</th>
                  {!row?.includes("#") && <th className="balance-name">Матеріал</th>}
                  {shown.map((column) => <th key={column.id}>{column.label}</th>)}
                  <th className="balance-name">Походження</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item, i) => (
                  <tr key={`${item.event ?? item.movement}:${item.material}:${i}`} className="leaf">
                    <td className="balance-name movement-at">{moment(item.at)}</td>
                    <td className="balance-name">
                      {item.movement}
                      <SourcesBadge sources={item.sources} />
                    </td>
                    {!row?.includes("#") && <td className="balance-name">{item.material_name}</td>}
                    {shown.map((column) => (
                      <td key={column.id} className={item.column === column.id && item.amount < 0 ? "neg" : ""}>
                        {item.column === column.id ? formatAmount(item.amount, unit, column.signed) : ""}
                      </td>
                    ))}
                    <td className="balance-name">
                      <span className={`compute-tag tone-${PROVENANCE_TONE[item.provenance] ?? "assumed"}`}>{PROVENANCE_LABEL[item.provenance] ?? item.provenance}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td className="balance-name">Разом</td>
                  <td className="balance-name" />
                  {!row?.includes("#") && <td className="balance-name" />}
                  {shown.map((column) => (
                    <td key={column.id}>{formatAmount(data.totals[column.id] ?? 0, unit, column.signed)}</td>
                  ))}
                  <td className="balance-name" />
                </tr>
              </tfoot>
            </table>
          </div>
          {rows.length < data.total && (
            <button className="report-switch movements-more" disabled={loading} onClick={() => void load(rows.length)}>
              Показати ще ({Math.min(PAGE, data.total - rows.length)} з {(data.total - rows.length).toLocaleString("uk-UA")})
            </button>
          )}
        </>
      )}
    </div>
  );
}
