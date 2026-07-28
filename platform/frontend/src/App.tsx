import { useEffect, useMemo, useState } from "react";
import { getScenarios, getSummary, Scenario, simulate, SimulationResult, Summary } from "./api";

const pct = (value: number) => `${Math.round(value * 100)}%`;
const fmt = (value: number) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value);
const names: Record<string, string> = {
  gas: "Газоснабжение",
  grid: "Электроснабжение",
  logistics: "Логистика",
  workforce: "Персонал",
};

function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState("base");
  const [target, setTarget] = useState(1000);
  const [gas, setGas] = useState(0.74);
  const [logistics, setLogistics] = useState(0.67);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const scenario = useMemo(
    () => scenarios.find((item) => item.id === scenarioId),
    [scenarioId, scenarios],
  );

  useEffect(() => {
    Promise.all([getSummary(), getScenarios()])
      .then(([nextSummary, nextScenarios]) => {
        setSummary(nextSummary);
        setScenarios(nextScenarios);
      })
      .catch((reason) => setError(String(reason)));
  }, []);

  useEffect(() => {
    if (!scenario) return;
    setGas(scenario.assumptions.gas);
    setLogistics(scenario.assumptions.logistics);
  }, [scenario]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setBusy(true);
      simulate({
        target_delivered_kg: target,
        gas_availability: gas,
        grid_availability: scenario?.assumptions.grid ?? 0.88,
        logistics_availability: logistics,
        workforce_availability: scenario?.assumptions.workforce ?? 0.91,
        scenario_id: scenarioId,
        persist: true,
      })
        .then(setResult)
        .catch((reason) => setError(String(reason)))
        .finally(() => setBusy(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [target, gas, logistics, scenario, scenarioId]);

  return (
    <div className="shell">
      <aside>
        <div className="brand"><i /><span><b>AFTERTIME</b><small>WORLD MODEL · LOCAL</small></span></div>
        <nav>
          <button className="active">◉ Операционный контур</button>
          <button>⌘ Граф мира</button>
          <button>≡ События</button>
          <button>◎ Источники</button>
        </nav>
        <div className="services"><span /><div><b>Система активна</b><small>API · DB · WORKER</small></div></div>
      </aside>

      <main>
        <header>
          <div><p>PRODUCT PLATFORM · NITROGEN PILOT</p><h1>Контур одной тонны аммиака</h1></div>
          <select value={scenarioId} onChange={(event) => setScenarioId(event.target.value)}>
            {scenarios.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
          </select>
        </header>

        <div className="content">
          {error && <div className="error">{error}</div>}
          <section className="hero">
            <div><p>ДОСТИЖИМАЯ ДОСТАВКА</p><strong>{result ? fmt(result.achievable_delivered_kg) : "—"} <small>кг NH₃</small></strong><span>{result ? `${fmt(result.lower_kg)}–${fmt(result.upper_kg)} кг · доверие ${pct(result.confidence)}` : "Расчёт модели"}</span></div>
            <div className={result?.shortfall_kg ? "verdict limited" : "verdict"}><i /><span><b>{busy ? "Пересчёт…" : result?.shortfall_kg ? `Дефицит ${fmt(result.shortfall_kg)} кг` : "Цель закрыта"}</b><small>Узкое место: {result ? names[result.bottleneck] : "—"}</small></span></div>
          </section>

          <section className="stats">
            <article><small>Сущности</small><b>{summary?.entities ?? "—"}</b></article>
            <article><small>Связи</small><b>{summary?.relations ?? "—"}</b></article>
            <article><small>Источники</small><b>{summary?.sources ?? "—"}</b></article>
            <article><small>Маршруты</small><b>{summary?.routes ?? "—"}</b></article>
          </section>

          <section className="panel controls">
            <Control label="Целевая партия" value={`${fmt(target)} кг`} min={100} max={5000} step={100} current={target} set={setTarget} />
            <Control label="Доступность газа" value={pct(gas)} min={0.1} max={1} step={0.01} current={gas} set={setGas} />
            <Control label="Доступность доставки" value={pct(logistics)} min={0.1} max={1} step={0.01} current={logistics} set={setLogistics} />
          </section>

          <section className="flow">
            <Node phase="01 · СЫРЬЁ" title="N₂ + H₂" value={result ? `${fmt(result.inputs.nitrogen_kg)} + ${fmt(result.inputs.hydrogen_kg)} кг` : "—"} />
            <em>→</em><Node phase="02 · СИНТЕЗ" title="Линия NH₃" value={result ? `${fmt(result.outputs.produced_ammonia_kg)} кг` : "—"} />
            <em>→</em><Node phase="03 · ХРАНЕНИЕ" title="Резервуар R-01" value={result ? `−${fmt(result.outputs.storage_loss_kg)} кг` : "—"} />
            <em>→</em><Node phase="04 · ДОСТАВКА" title="Черкассы → Полтава" value={result ? `${fmt(result.expected_hours)} ч` : "—"} />
            <em>→</em><Node phase="05 · РЕЗУЛЬТАТ" title="Региональный склад" value={result ? `${fmt(result.outputs.delivered_kg)} кг` : "—"} />
          </section>

          <section className="lower">
            <article className="panel">
              <div className="panel-title"><div><p>ФИЗИЧЕСКАЯ СВЕРКА</p><h2>Сохранение элементов</h2></div><span className="ok">{result?.conservation.closed ? "ЗАКРЫТО" : "—"}</span></div>
              <Balance label="Азот" input={result?.conservation.nitrogen_in_kg} output={result?.conservation.nitrogen_out_kg} />
              <Balance label="Водород" input={result?.conservation.hydrogen_in_kg} output={result?.conservation.hydrogen_out_kg} />
            </article>
            <article className="panel plan">
              <p>КОМПЕНСИРУЮЩИЙ ПЛАН</p>
              <h2>{result?.recommendation.action ?? "Ожидание расчёта"}</h2>
              <span>{result?.recommendation.effect}</span>
              <dl><div><dt>Срок</dt><dd>{result?.recommendation.lead_time_hours ?? "—"} ч</dd></div><div><dt>Восстановление</dt><dd>+{fmt(result?.recommendation.recovered_kg ?? 0)} кг</dd></div><div><dt>После действия</dt><dd>{fmt(result?.recommendation.compensated_delivered_kg ?? 0)} кг</dd></div></dl>
            </article>
          </section>
        </div>
      </main>
    </div>
  );
}

function Control({ label, value, current, min, max, step, set }: { label: string; value: string; current: number; min: number; max: number; step: number; set: (value: number) => void }) {
  return <label><span>{label}<b>{value}</b></span><input type="range" value={current} min={min} max={max} step={step} onChange={(event) => set(Number(event.target.value))} /></label>;
}
function Node({ phase, title, value }: { phase: string; title: string; value: string }) {
  return <article><small>{phase}</small><h3>{title}</h3><b>{value}</b></article>;
}
function Balance({ label, input, output }: { label: string; input?: number; output?: number }) {
  return <div className="balance"><b>{label}</b><span>Вход {fmt(input ?? 0)} кг</span><em>→</em><span>Выход {fmt(output ?? 0)} кг</span><i>✓</i></div>;
}

export default App;
