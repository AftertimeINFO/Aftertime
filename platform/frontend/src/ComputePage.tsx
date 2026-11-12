import { useEffect, useMemo, useState } from "react";
import { request } from "./api";
import { hrefWithLayer, useAppContext } from "./appContext";
import {
  PROVENANCE_LABEL,
  PROVENANCE_TONE,
  refreshCoverage,
  setCoverage,
  shiftYears,
  useCoverage,
  type CoverageOverview,
} from "./coverage";
import { LAYER_LABEL } from "./promotion";

function day(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10).split("-").reverse().join(".") : "—";
}

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("uk-UA", { dateStyle: "short", timeStyle: "short" }) : "—";
}

const kbd = (value: number) => `${Math.round(value / 1000).toLocaleString("uk-UA")} тис. бар./добу`;

/** Settings of the world computation: up to which date the ledger (and the balance) is computed. */
export default function ComputePage() {
  const { layer } = useAppContext();
  const covered = useCoverage();
  const overview = covered.overview;
  const coverage = overview?.coverage ?? null;
  const limits = overview?.limits;
  const [horizon, setHorizon] = useState("");
  const [growth, setGrowth] = useState("0");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ duration_ms: number; events: number; cargoes: number } | null>(null);
  const [capabilities, setCapabilities] = useState<string[] | null>(null);

  useEffect(() => {
    request<{ items: { id: string; capabilities: string[] }[] }>("/layers")
      .then((r) => setCapabilities(r.items.find((l) => l.id === layer)?.capabilities ?? []))
      .catch(() => setCapabilities([]));
  }, [layer]);
  useEffect(() => {
    if (!overview || horizon) return;
    setHorizon(coverage?.to ?? overview.limits.history_to);
    setGrowth(String(coverage?.parameters.growth_pct ?? 0));
  }, [overview, coverage, horizon]);

  const allowed = capabilities?.includes("compute") ?? false;
  const growthValue = Number(growth.replace(",", "."));
  const valid =
    !!limits && horizon >= limits.min_horizon && horizon <= limits.max_horizon && Number.isFinite(growthValue) && Math.abs(growthValue) <= limits.max_growth_pct;
  const peak = useMemo(() => Math.max(1, ...(overview?.flows ?? []).map((f) => f.bbl_per_day)), [overview]);

  const run = async () => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const result = await request<CoverageOverview & { duration_ms: number; events: number; cargoes: number }>(
        "/world/compute",
        { method: "POST", body: JSON.stringify({ horizon, growth_pct: growthValue, note }) },
        180_000,
      );
      setCoverage(result);
      setDone(result);
      setNote("");
    } catch (reason: any) {
      setError(String(reason?.message || reason));
      void refreshCoverage();
    } finally {
      setBusy(false);
    }
  };

  const quick = limits
    ? [
        { label: "кінець історії", value: limits.history_to },
        { label: "+1 рік", value: shiftYears(horizon || limits.history_to, 1, limits.min_horizon, limits.max_horizon) },
        { label: "+5 років", value: shiftYears(horizon || limits.history_to, 5, limits.min_horizon, limits.max_horizon) },
        { label: "2035", value: "2035-12-31" },
        { label: "2040", value: "2040-12-31" },
        { label: "2050", value: limits.max_horizon },
      ]
    : [];

  return (
    <div className="compute-page">
      <header className="promote-head">
        <div>
          <small>РОЗРАХУНОК СВІТУ · {LAYER_LABEL[layer as keyof typeof LAYER_LABEL] ?? layer}</small>
          <h1>{coverage ? `Розраховано ${day(coverage.from)} — ${day(coverage.to)}` : "Світ ще не розраховано"}</h1>
        </div>
        <a className="compute-back" href={hrefWithLayer("/")}>До балансу матерії →</a>
      </header>
      <p className="promote-intro">
        Розрахунок записує події світу від початку історії до обраного горизонту. Роки з опублікованими даними — історія; далі прогноз:
        потік останнього історичного року, змінений на заданий відсоток щороку. Баланс матерії можна побудувати лише для періодів
        у межах розрахунку. Кожен перерахунок повністю замінює попередній.
      </p>

      {covered.status === "error" && <div className="balance-message bad">{covered.error}</div>}
      {overview && !overview.computable && (
        <div className="balance-message">
          У шарі {LAYER_LABEL[layer as keyof typeof LAYER_LABEL] ?? layer} немає моделі світу для розрахунку. Пілот Saudi Arabia → India є лише в DEV;
          в інших шарах розрахунок стане доступним після завантаження сутностей і джерел.
        </div>
      )}

      {overview && (
        <div className="compute-body">
          <section className="compute-form">
            <h2>Горизонт розрахунку</h2>
            <label>
              Розрахувати до дати (включно)
              <input type="date" value={horizon} min={limits?.min_horizon} max={limits?.max_horizon} onChange={(e) => setHorizon(e.target.value)} />
            </label>
            <div className="compute-quick">
              {quick.map((item) => (
                <button key={item.label} onClick={() => setHorizon(item.value)} className={horizon === item.value ? "active" : ""}>
                  {item.label}
                </button>
              ))}
            </div>
            <label>
              Зміна потоку в прогнозі, % на рік
              <input type="number" step="0.5" min={-(limits?.max_growth_pct ?? 50)} max={limits?.max_growth_pct ?? 50} value={growth} onChange={(e) => setGrowth(e.target.value)} />
            </label>
            <label>
              Коментар (необов'язково)
              <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Навіщо цей горизонт: сценарій, перевірка, звіт" />
            </label>
            <button className="compute-run" data-layer={layer} disabled={!allowed || !overview.computable || !valid || busy} onClick={run}
              title={allowed ? "" : "Розрахунок недоступний у цьому шарі"}>
              {busy ? "Розрахунок…" : `Розрахувати до ${day(horizon)}`}
            </button>
            {!allowed && capabilities && <p className="compute-hint">У шарі {LAYER_LABEL[layer as keyof typeof LAYER_LABEL] ?? layer} розрахунок лише переглядається: шар доступний тільки для читання.</p>}
            {limits && <p className="compute-hint">Горизонт від {day(limits.min_horizon)} до {day(limits.max_horizon)}. Історія: {day(limits.history_from)} — {day(limits.history_to)}.</p>}
            {error && <div className="balance-message bad">{error}</div>}
            {done && (
              <div className="promote-result ok">
                Готово за {(done.duration_ms / 1000).toLocaleString("uk-UA", { maximumFractionDigits: 1 })} с: {done.events.toLocaleString("uk-UA")} подій,{" "}
                {done.cargoes.toLocaleString("uk-UA")} вантажів. <a href={hrefWithLayer("/")}>Відкрити баланс ↗</a>
              </div>
            )}
          </section>

          <section className="compute-flows">
            <h2>Потік сирої нафти Saudi Arabia → India за роками</h2>
            <div className="compute-legend">
              {["statistic", "derived", "forecast"].map((p) => (
                <span key={p} className={`tone-${PROVENANCE_TONE[p]}`}>{PROVENANCE_LABEL[p]}</span>
              ))}
            </div>
            <table className="compute-table">
              <tbody>
                {overview.flows.map((flow) => (
                  <tr key={flow.year} className={coverage && `${flow.year}` > coverage.to.slice(0, 4) ? "uncomputed" : ""}>
                    <td>{flow.year}</td>
                    <td className="compute-bar">
                      <i className={`tone-${PROVENANCE_TONE[flow.provenance] ?? "assumed"}`} style={{ width: `${(flow.bbl_per_day / peak) * 100}%` }} />
                    </td>
                    <td className="num">{kbd(flow.bbl_per_day)}</td>
                    <td>
                      <span className={`compute-tag tone-${PROVENANCE_TONE[flow.provenance] ?? "assumed"}`}>{PROVENANCE_LABEL[flow.provenance] ?? flow.provenance}</span>
                    </td>
                    <td className="compute-ref">{flow.reference ?? "останній історичний рік × зміна потоку"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="compute-hint">
              Увесь потік у пілоті йде через Ras Tanura → Sikka → Jamnagar; судна, маршрут і час рейсів — припущення. «Похідні дані» обчислено з
              опублікованої частки імпорту або з тоннажу фінансового року (квітень–березень) за 7,33 бар./т.
            </p>
          </section>
        </div>
      )}

      {overview && overview.computations.length > 0 && (
        <section className="promote-history">
          <h3>Журнал розрахунків</h3>
          <table className="promote-table">
            <thead>
              <tr>
                <th>Коли</th>
                <th>Період</th>
                <th>Зміна, %/рік</th>
                <th>Подій</th>
                <th>Тривалість</th>
                <th>Коментар</th>
              </tr>
            </thead>
            <tbody>
              {overview.computations.map((item) => (
                <tr key={item.id}>
                  <td>{when(item.created_at)}</td>
                  <td>
                    {day(item.from)} — {day(item.to)}
                  </td>
                  <td>{item.parameters.growth_pct ?? 0}</td>
                  <td>{item.summary.events?.toLocaleString("uk-UA") ?? "—"}</td>
                  <td>{(item.duration_ms / 1000).toLocaleString("uk-UA", { maximumFractionDigits: 1 })} с</td>
                  <td>{item.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
