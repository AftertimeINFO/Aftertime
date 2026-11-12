import { useContext, useEffect, useMemo, useState } from "react";
import { request } from "./api";
import { hrefWithLayer, periodBounds, useAppContext } from "./appContext";
import { COLUMNS, MASS_UNITS, formatAmount, type BalanceColumn, type BalanceLevel, type BalanceValues, type MassUnit } from "./balance";
import { periodCovered, useCoverage } from "./coverage";
import { PeriodPicker } from "./PeriodSelect";
import { SourceList } from "./Sources";
import {
  FLOWS,
  STEPS,
  defaultStep,
  drawnValue,
  fitStep,
  niceTicks,
  pointLabel,
  reportUrl,
  type ReportKind,
  type ReportStep,
  type Series,
  type SeriesPoint,
  tickLabels,
} from "./report";
import { PaneContext, openTab, replaceTabQuery, tabParams, updateTab, usePaneTab } from "./tabs";

// Categorical slots (validated on the dark panel: lightness band, CVD and contrast pass).
const FLOW_COLOR: Record<string, string> = {
  inflow: "#3987e5",
  outflow: "#d95926",
  transform: "#199e70",
  carrier: "#c98500",
  revision: "#d55181",
};
const STOCK_COLOR = "#9085e9";
const LABEL: Record<string, string> = Object.fromEntries(COLUMNS.map((c) => [c.id, c.label]));

function dateLabel(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("uk-UA", { timeZone: "UTC", day: "2-digit", month: "2-digit", year: "numeric" });
}

function unitFor(points: SeriesPoint[]): MassUnit {
  const peak = Math.max(0, ...points.flatMap((p) => Object.values(p.values).map(Math.abs)));
  return peak >= 1e10 ? "Mt" : peak >= 1e7 ? "kt" : "t";
}

/** Turnover statement or chart of one balance row, by month, quarter or year. */
export default function ReportPage({ kind }: { kind: ReportKind }) {
  const context = useAppContext();
  const pane = useContext(PaneContext);
  const tab = usePaneTab();
  const [query] = useState(() => tabParams(pane));
  const row = query.get("row") || "";
  const name = query.get("name") || row;
  const flow = query.get("flow") || undefined;
  const level = (query.get("level") || "substance") as BalanceLevel;
  const [chosen, setChosen] = useState<ReportStep | null>((query.get("step") as ReportStep) || null);
  const step = fitStep(context.from, context.to, chosen ?? defaultStep(context.from, context.to));
  const [data, setData] = useState<Series | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [unit, setUnit] = useState<MassUnit | null>(null);
  const covered = useCoverage();
  const waiting = covered.status === "loading" || (covered.status === "ready" && !periodCovered(context.from, context.to, covered.overview?.coverage ?? null));

  useEffect(() => {
    if (waiting || !row) return;
    const controller = new AbortController();
    const bounds = periodBounds(context.from, context.to);
    const params = new URLSearchParams({ scope: context.scope, row, from: bounds.from, to: bounds.to, level, step });
    if (flow) params.set("flow", flow);
    setLoading(true);
    request<Series>(`/world/balance/series?${params}`, { signal: controller.signal }, 120_000)
      .then((result) => {
        setData(result);
        setError(null);
        // A tab opened from an address knows only the scope id: name it for the tab title.
        if (pane && result.scope_name && result.scope === context.scope && !tab?.scopeName) updateTab(pane, { scopeName: result.scope_name });
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(String(reason?.message || reason));
          setData(null);
        }
      })
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [context.scope, context.from, context.to, context.layer, row, flow, level, step, waiting]);

  const chooseStep = (next: ReportStep) => {
    setChosen(next);
    const params = tabParams(pane);
    params.set("step", next);
    replaceTabQuery(pane, params);
  };
  const shownUnit = unit ?? (data ? unitFor(data.points) : "Mt");
  const unitLabel = MASS_UNITS.find((u) => u.id === shownUnit)?.label ?? shownUnit;
  const other: ReportKind = kind === "chart" ? "turnover" : "chart";
  const openOther = () =>
    openTab({ kind: other, scope: context.scope, scopeName: tab?.scopeName, from: context.from, to: context.to, url: reportUrl(other, { id: row, name }, level, flow) });

  return (
    <div className="balance-page report-page">
      <header className="balance-head">
        <div>
          <small>{kind === "chart" ? "ГРАФІК" : "ОБОРОТНА ВІДОМІСТЬ"} · {flow ? "ПОТІК" : "РЯДОК БАЛАНСУ"}</small>
          <h1>
            {name}
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
            <label className="report-step">
              <small>КРОК</small>
              <select value={step} onChange={(e) => chooseStep(e.target.value as ReportStep)}>
                {STEPS.map((s) => (
                  <option key={s.id} value={s.id} disabled={fitStep(context.from, context.to, s.id) !== s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <div className="balance-controls">
          <button className="report-switch" onClick={openOther}>
            {other === "chart" ? "↗ Графік" : "≡ Оборотна відомість"}
          </button>
          <label className="balance-unit">
            Одиниці
            <select value={shownUnit} onChange={(e) => setUnit(e.target.value as MassUnit)}>
              {MASS_UNITS.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
            </select>
          </label>
        </div>
      </header>

      {!row && <div className="balance-message">У вкладці не вказано рядок балансу.</div>}
      {error && <div className="balance-message bad">{error}</div>}
      {!data && !error && row && <div className="balance-message">Розрахунок…</div>}
      {data && (
        <div className={loading ? "loading" : ""}>
          {kind === "turnover" ? (
            <TurnoverTable data={data} unit={shownUnit} unitLabel={unitLabel} />
          ) : (
            <Charts data={data} unit={shownUnit} unitLabel={unitLabel} />
          )}
          <p className="balance-note report-note">
            Маса, {unitLabel}. Крок — {STEPS.find((s) => s.id === step)?.label}; межі підперіодів за календарем, період{" "}
            {dateLabel(context.from)} — {dateLabel(context.to)}.{" "}
            <a className="balance-coverage" href={hrefWithLayer("/")} onClick={(e) => {
              e.preventDefault();
              openTab({ kind: "balance", scope: context.scope, scopeName: tab?.scopeName, from: context.from, to: context.to });
            }}>Баланс scope ↗</a>
          </p>
          {!!data.sources?.length && (
            <section className="report-sources">
              <h2>Джерела даних</h2>
              <SourceList sources={data.sources} />
            </section>
          )}
        </div>
      )}
    </div>
  );
}

/** Columns a report shows: the whole row, or only the flows that moved. */
function shownColumns(data: Series): BalanceColumn[] {
  if (!data.flow) return ["opening", ...FLOWS, "closing", "residual"];
  const moved = FLOWS.filter((column) => data.points.some((p) => Math.abs(p.values[column] ?? 0) > 0));
  return moved.length ? moved : ["outflow"];
}

function TurnoverTable({ data, unit, unitLabel }: { data: Series; unit: MassUnit; unitLabel: string }) {
  const columns = shownColumns(data);
  const signed = (column: BalanceColumn) => !!COLUMNS.find((c) => c.id === column)?.signed;
  return (
    <div className="balance-table-wrap">
      <table className="balance-table report-table" aria-label={`Оборотна відомість, ${unitLabel}`}>
        <thead>
          <tr>
            <th className="balance-name">Період</th>
            {columns.map((column) => (
              <th key={column} className={`col-${column}`}>{LABEL[column]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.points.map((point) => (
            <tr key={point.from} className="leaf">
              <td className="balance-name">{pointLabel(point.from, data.step)}</td>
              {columns.map((column) => (
                <td key={column} className={`col-${column} ${point.values[column] < 0 ? "neg" : ""}`}>
                  {formatAmount(point.values[column] ?? 0, unit, signed(column))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td className="balance-name">Разом</td>
            {columns.map((column) => (
              <td key={column} className={`col-${column}`}>
                {formatAmount(data.totals[column] ?? 0, unit, signed(column))}
              </td>
            ))}
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

// ----- charts -----

const W = 960;
const H = 260;
const PAD = { left: 64, right: 16, top: 12, bottom: 30 };

function Charts({ data, unit, unitLabel }: { data: Series; unit: MassUnit; unitLabel: string }) {
  const series = FLOWS.filter((column) => data.points.some((p) => Math.abs(p.values[column] ?? 0) > 0));
  return (
    <div className="report-charts">
      {!data.flow && (
        <section className="report-chart">
          <h2>Сальдо на кінець підперіоду, {unitLabel}</h2>
          <StockChart data={data} unit={unit} />
        </section>
      )}
      <section className="report-chart">
        <h2>Обороти за підперіод, {unitLabel}</h2>
        {series.length > 1 && (
          <div className="report-legend">
            {series.map((column) => (
              <span key={column}>
                <i style={{ background: FLOW_COLOR[column] }} />
                {LABEL[column]}
              </span>
            ))}
          </div>
        )}
        {series.length ? <FlowChart data={data} unit={unit} series={series} /> : <p className="balance-note">Оборотів за період немає.</p>}
      </section>
    </div>
  );
}

function scaleOf(values: number[], zero = true) {
  const ticks = niceTicks(Math.min(...values), Math.max(...values), 5, zero);
  const lo = ticks[0];
  const hi = ticks[ticks.length - 1];
  const y = (v: number) => PAD.top + ((hi - v) / (hi - lo || 1)) * (H - PAD.top - PAD.bottom);
  return { ticks, y };
}

function Axis({ ticks, y, unit, data }: { ticks: number[]; y: (v: number) => number; unit: MassUnit; data: Series }) {
  const band = (W - PAD.left - PAD.right) / data.points.length;
  const every = Math.max(1, Math.ceil(data.points.length / 12));
  const labels = tickLabels(ticks, MASS_UNITS.find((u) => u.id === unit)?.kg ?? 1);
  return (
    <g className="report-axis">
      {ticks.map((tick, i) => (
        <g key={tick}>
          <line x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} className={tick === 0 ? "zero" : ""} />
          <text x={PAD.left - 8} y={y(tick)} dy="0.32em" textAnchor="end">{labels[i]}</text>
        </g>
      ))}
      {data.points.map((point, i) =>
        i % every === 0 ? (
          <text key={point.from} x={PAD.left + band * (i + 0.5)} y={H - 8} textAnchor="middle">
            {pointLabel(point.from, data.step)}
          </text>
        ) : null,
      )}
    </g>
  );
}

/** Hover layer: one hit band per sub-period, a tooltip with every value of it. */
function useHover() {
  const [hover, setHover] = useState<number | null>(null);
  return { hover, setHover };
}

function Tooltip({ data, index, rows, unit }: { data: Series; index: number; rows: { label: string; color: string; value: number; signed?: boolean }[]; unit: MassUnit }) {
  const left = ((PAD.left + ((W - PAD.left - PAD.right) / data.points.length) * (index + 0.5)) / W) * 100;
  return (
    <div className="report-tooltip" style={{ left: `${left}%`, transform: `translateX(${left > 70 ? "-100%" : left < 20 ? "0" : "-50%"})` }}>
      <b>{pointLabel(data.points[index].from, data.step)}</b>
      {rows.map((row) => (
        <span key={row.label}>
          <i style={{ background: row.color }} />
          {row.label}
          <em>{formatAmount(row.value, unit, row.signed)}</em>
        </span>
      ))}
    </div>
  );
}

function HitBands({ data, setHover }: { data: Series; setHover: (i: number | null) => void }) {
  const band = (W - PAD.left - PAD.right) / data.points.length;
  return (
    <g onMouseLeave={() => setHover(null)}>
      {data.points.map((point, i) => (
        <rect key={point.from} x={PAD.left + band * i} y={PAD.top} width={band} height={H - PAD.top - PAD.bottom} fill="transparent" onMouseEnter={() => setHover(i)} />
      ))}
    </g>
  );
}

function StockChart({ data, unit }: { data: Series; unit: MassUnit }) {
  const { hover, setHover } = useHover();
  const closing = data.points.map((p) => p.values.closing ?? 0);
  // A stock line reads its change: the axis spans the values, not down to zero.
  const { ticks, y } = useMemo(() => scaleOf([...closing, data.points[0]?.values.opening ?? 0], false), [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const band = (W - PAD.left - PAD.right) / data.points.length;
  const x = (i: number) => PAD.left + band * (i + 0.5);
  const line = closing.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <div className="report-plot">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Сальдо на кінець кожного підперіоду">
        <Axis ticks={ticks} y={y} unit={unit} data={data} />
        <path d={line} fill="none" stroke={STOCK_COLOR} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {hover !== null && <line className="report-crosshair" x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={H - PAD.bottom} />}
        {hover !== null && <circle cx={x(hover)} cy={y(closing[hover])} r={4} fill={STOCK_COLOR} stroke="var(--panel)" strokeWidth={2} />}
        <circle cx={x(closing.length - 1)} cy={y(closing[closing.length - 1])} r={4} fill={STOCK_COLOR} stroke="var(--panel)" strokeWidth={2} />
        <HitBands data={data} setHover={setHover} />
      </svg>
      {hover !== null && (
        <Tooltip
          data={data}
          index={hover}
          unit={unit}
          rows={[
            { label: "Сальдо на початок", color: "transparent", value: data.points[hover].values.opening ?? 0 },
            { label: "Сальдо на кінець", color: STOCK_COLOR, value: closing[hover] },
          ]}
        />
      )}
    </div>
  );
}

/** Column with a 4px rounded end away from the baseline. */
function barPath(x: number, base: number, end: number, width: number): string {
  const r = Math.min(4, Math.abs(end - base), width / 2);
  if (Math.abs(end - base) < 0.5) return "";
  const up = end < base;
  const s = up ? 1 : -1;
  return [
    `M${x},${base}`,
    `L${x},${end + s * r}`,
    `Q${x},${end} ${x + r},${end}`,
    `L${x + width - r},${end}`,
    `Q${x + width},${end} ${x + width},${end + s * r}`,
    `L${x + width},${base}`,
    "Z",
  ].join(" ");
}

function FlowChart({ data, unit, series }: { data: Series; unit: MassUnit; series: BalanceColumn[] }) {
  const { hover, setHover } = useHover();
  const values = data.points.flatMap((p) => series.map((column) => drawnValue(column, p.values)));
  const { ticks, y } = useMemo(() => scaleOf(values), [data, series]); // eslint-disable-line react-hooks/exhaustive-deps
  const band = (W - PAD.left - PAD.right) / data.points.length;
  const gap = 2;
  const inner = band * 0.72;
  const width = Math.max(2, Math.min(24, (inner - gap * (series.length - 1)) / series.length));
  const group = width * series.length + gap * (series.length - 1);
  return (
    <div className="report-plot">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Обороти за кожен підперіод">
        <Axis ticks={ticks} y={y} unit={unit} data={data} />
        {hover !== null && <rect className="report-hover-band" x={PAD.left + band * hover} y={PAD.top} width={band} height={H - PAD.top - PAD.bottom} />}
        {data.points.map((point, i) => {
          const left = PAD.left + band * i + (band - group) / 2;
          return series.map((column, k) => (
            <path key={`${point.from}:${column}`} d={barPath(left + k * (width + gap), y(0), y(drawnValue(column, point.values)), width)} fill={FLOW_COLOR[column]} />
          ));
        })}
        <HitBands data={data} setHover={setHover} />
      </svg>
      {hover !== null && (
        <Tooltip
          data={data}
          index={hover}
          unit={unit}
          rows={series.map((column) => ({
            label: LABEL[column],
            color: FLOW_COLOR[column],
            value: data.points[hover].values[column as keyof BalanceValues] ?? 0,
            signed: column === "transform" || column === "carrier" || column === "revision",
          }))}
        />
      )}
    </div>
  );
}
