import { Fragment, useEffect, useMemo, useState } from "react";
import { request } from "./api";
import { hrefWithLayer, periodBounds, useAppContext } from "./appContext";
import { PROVENANCE_LABEL, periodCovered, useCoverage } from "./coverage";
import { PeriodPicker } from "./PeriodSelect";
import { ScopeBar } from "./ScopeSelect";
import { ReportMenu, useLongPressMenu, type ReportTarget } from "./ReportMenu";
import { reportUrl } from "./report";
import { openTab, usePaneTab } from "./tabs";
import {
  COLUMNS,
  LEVELS,
  MASS_UNITS,
  collapsedBelow,
  formatAmount,
  suggestUnit,
  visibleRows,
  type Balance,
  type BalanceLevel,
  type BalanceRow,
  type MassUnit,
} from "./balance";

const LAYER_LABEL: Record<string, string> = { dev: "DEV", preprod: "prePROD", prod: "PROD" };

function dateLabel(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("uk-UA", { timeZone: "UTC", day: "2-digit", month: "2-digit", year: "numeric" });
}

/** Main screen: trial balance of matter for the selected layer, scope and period. */
export default function BalancePage() {
  const context = useAppContext();
  const [level, setLevel] = useState<BalanceLevel>("substance");
  const [unit, setUnit] = useState<MassUnit | null>(null);
  const [data, setData] = useState<Balance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);
  const covered = useCoverage();
  const coverage = covered.overview?.coverage ?? null;
  const tab = usePaneTab();
  // Press and hold a row: turnover statement or chart of that row (or flow) in a new tab.
  const menu = useLongPressMenu();
  const openReport = (kind: "turnover" | "chart", target: ReportTarget) =>
    openTab({
      kind,
      scope: context.scope,
      scopeName: tab?.scopeName,
      from: context.from,
      to: context.to,
      url: reportUrl(kind, target.row, level, target.flow),
    });
  // Wait for the coverage: the period picker moves an uncovered period inside it first.
  // Without any computation there is nothing to report: the request is not sent.
  const waiting = covered.status === "loading" || (covered.status === "ready" && !periodCovered(context.from, context.to, coverage));

  useEffect(() => {
    if (waiting) return;
    const controller = new AbortController();
    const bounds = periodBounds(context.from, context.to);
    const params = new URLSearchParams({ scope: context.scope, from: bounds.from, to: bounds.to, level });
    setLoading(true);
    request<Balance>(`/world/balance?${params}`, { signal: controller.signal }, 60_000)
      .then((result) => {
        setData(result);
        setError(null);
        setCollapsed(collapsedBelow(result.rows, 2));
        setExpanded(null);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(String(reason?.message || reason));
          setData(null);
        }
      })
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [context.scope, context.from, context.to, context.layer, level, waiting]);

  const shownUnit = unit ?? (data ? suggestUnit(data.totals) : "t");
  const rows = useMemo(() => (data ? visibleRows(data.rows, collapsed) : []), [data, collapsed]);
  const toggle = (row: BalanceRow) => {
    if (row.group) {
      setCollapsed((current) => {
        const next = new Set(current);
        if (next.has(row.id)) next.delete(row.id);
        else next.add(row.id);
        return next;
      });
    } else if (row.breakdown?.length) {
      setExpanded(expanded === row.id ? null : row.id);
    }
  };
  const columns = COLUMNS.map((column) =>
    column.id === "opening"
      ? { ...column, label: `Сальдо на ${dateLabel(context.from)}` }
      : column.id === "closing"
        ? { ...column, label: `Сальдо на ${dateLabel(context.to)}` }
        : column,
  );

  return (
    <div className="balance-page">
      <header className="balance-head">
        <div>
          <small>БАЛАНС МАТЕРІЇ · ОБОРОТНО-САЛЬДОВА ВІДОМІСТЬ</small>
          <h1>
            {dateLabel(context.from)} — {dateLabel(context.to)}
          </h1>
          <div className="balance-context">
            <ScopeBar />
            <PeriodPicker />
          </div>
        </div>
        <div className="balance-controls">
          <div className="balance-segment" role="radiogroup" aria-label="Рівень матерії">
            {LEVELS.map((item) => {
              const available = data ? data.levels[item.id] : item.id !== "molecular";
              return (
                <button
                  key={item.id}
                  role="radio"
                  aria-checked={level === item.id}
                  className={level === item.id ? "active" : ""}
                  disabled={!available}
                  title={available ? item.hint : `${item.hint}: у шарі ${LAYER_LABEL[context.layer]} немає даних про склад`}
                  onClick={() => setLevel(item.id)}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
          <label className="balance-unit">
            Одиниці
            <select value={shownUnit} onChange={(e) => setUnit(e.target.value as MassUnit)}>
              {MASS_UNITS.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
            </select>
          </label>
        </div>
      </header>

      {data && !data.empty && (
        <div className="balance-status">
          <span className={data.residual_ok ? "ok" : "bad"}>
            {data.residual_ok ? "✓ Баланс зведено: нев'язка 0" : `⚠ Нев'язка ${formatAmount(data.totals.residual, shownUnit, true)} ${MASS_UNITS.find((u) => u.id === shownUnit)?.label}`}
          </span>
          {Object.keys(data.provenance).length > 0 && (
            <span className="balance-provenance" title="Частка обороту за походженням подій">
              Походження:{" "}
              {Object.entries(data.provenance).map(([name, share]) => `${PROVENANCE_LABEL[name] ?? name} ${Math.round(share * 100)}%`).join(" · ")}
            </span>
          )}
          {coverage && (
            <a className="balance-coverage" href={hrefWithLayer("/compute")} title="Налаштувати горизонт розрахунку">
              Розраховано {dateLabel(coverage.from)} — {dateLabel(coverage.to)}
              {coverage.forecast ? ` · прогноз після ${dateLabel(coverage.history_to)}` : ""}
            </a>
          )}
          <span className="balance-note">Маса, {MASS_UNITS.find((u) => u.id === shownUnit)?.label}. Внутрішні переміщення в межах scope в сальдо не впливають. Утримуйте кнопку миші на рядку — оборотна відомість чи графік.</span>
        </div>
      )}

      {error && error.startsWith("Невідомий scope") && (
        <div className="balance-message">
          У шарі {LAYER_LABEL[context.layer]} немає обраного scope. {context.layer === "dev" ? "Оберіть scope у верхній панелі." : "Шар ще не наповнений даними: сутності з'являться після завантаження реальних джерел або перенесення моделей у цей шар."}
        </div>
      )}
      {error && !error.startsWith("Невідомий scope") && <div className="balance-message bad">{error}</div>}
      {!error && data?.empty && (
        <div className="balance-message">
          У шарі {LAYER_LABEL[context.layer]} немає даних про матерію для цього scope і періоду.
          {context.layer !== "dev" && " Дані з'являться після завантаження реальних джерел або перенесення моделей у цей шар."}
        </div>
      )}
      {covered.status === "ready" && !coverage && (
        <div className="balance-message">
          У шарі {LAYER_LABEL[context.layer]} світ ще не розраховано, тому період недоступний.{" "}
          <a href={hrefWithLayer("/compute")}>Розрахунок світу ↗</a>
        </div>
      )}
      {!data && !error && (coverage || covered.status === "loading") && <div className="balance-message">Розрахунок балансу…</div>}

      {data && !data.empty && (
        <div className={`balance-table-wrap ${loading ? "loading" : ""}`}>
          <table className="balance-table">
            <thead>
              <tr>
                <th className="balance-name">{level === "element" ? "Хімічний елемент" : "Матеріал"}</th>
                {columns.map((column) => (
                  <th key={column.id} title={column.hint} className={`col-${column.id}`}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Fragment key={row.id}>
                  <tr
                    className={`${row.group ? "group" : "leaf"} ${row.breakdown?.length ? "has-detail" : ""}`}
                    onClick={() => toggle(row)}
                    title="Утримуйте ліву кнопку миші: оборотна відомість або графік"
                    {...menu.bind({ row: { id: row.id, name: row.name } })}
                  >
                    <td className="balance-name" style={{ paddingLeft: 12 + row.depth * 18 }}>
                      {row.group ? <i className="balance-caret">{collapsed.has(row.id) ? "▸" : "▾"}</i> : row.breakdown?.length ? <i className="balance-caret">{expanded === row.id ? "−" : "+"}</i> : <i className="balance-caret" />}
                      {row.symbol && <span className="balance-symbol">{row.symbol}</span>}
                      {row.name}
                      {!row.group && !row.id.startsWith("element:") && !row.id.startsWith("material:") && (
                        <a className="balance-link" href={hrefWithLayer(`/world/entities?id=${encodeURIComponent(row.id.replace("#own", ""))}`)} onClick={(e) => e.stopPropagation()} title="Відкрити картку типу">↗</a>
                      )}
                    </td>
                    {columns.map((column) => (
                      <td key={column.id} className={`col-${column.id} ${row.values[column.id] < 0 ? "neg" : ""}`}>
                        {formatAmount(row.values[column.id], shownUnit, column.signed)}
                      </td>
                    ))}
                  </tr>
                  {expanded === row.id && row.breakdown?.map((detail) => (
                    <tr
                      key={`${row.id}:${detail.event_type}`}
                      className="detail"
                      title="Утримуйте ліву кнопку миші: оборотна відомість або графік цього потоку"
                      {...menu.bind({ row: { id: row.id, name: row.name }, flow: detail.event_type })}
                    >
                      <td className="balance-name" style={{ paddingLeft: 40 + row.depth * 18 }}>{detail.event_type}</td>
                      {columns.map((column) => (
                        <td key={column.id} className={`col-${column.id}`}>
                          {detail[column.id] ? formatAmount(detail[column.id]!, shownUnit, column.signed) : ""}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {expanded === row.id && row.values.internal > 0 && (
                    <tr className="detail">
                      <td className="balance-name" style={{ paddingLeft: 40 + row.depth * 18 }} colSpan={columns.length + 1}>
                        Внутрішній оборот у межах scope: {formatAmount(row.values.internal, shownUnit)} {MASS_UNITS.find((u) => u.id === shownUnit)?.label}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className="balance-name">Разом</td>
                {columns.map((column) => (
                  <td key={column.id} className={`col-${column.id} ${data.totals[column.id] < 0 ? "neg" : ""}`}>
                    {formatAmount(data.totals[column.id], shownUnit, column.signed)}
                  </td>
                ))}
              </tr>
            </tfoot>
          </table>
        </div>
      )}
      <ReportMenu open={menu.open} close={menu.close} onChoose={openReport} />
    </div>
  );
}
