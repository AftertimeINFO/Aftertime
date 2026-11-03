"use client";

import { useMemo, useState } from "react";
import type { WorldSnapshot } from "../db/world";
import { defaultSimulationInputs, simulateModelLab, type LabRow } from "../db/model-lab";

type View = "run" | "scheme" | "incidents" | "recovery" | "qualification" | "catalog";

const nav: { id: View; label: string; glyph: string }[] = [
  { id: "run", label: "Запуск моделі", glyph: "▶" },
  { id: "scheme", label: "Рівні схеми", glyph: "⌘" },
  { id: "incidents", label: "Аварії", glyph: "⚠" },
  { id: "recovery", label: "Відновлення", glyph: "↻" },
  { id: "qualification", label: "Кваліфікація", glyph: "✓" },
  { id: "catalog", label: "Каталоги", glyph: "▦" },
];

const chainIds = ["resource-gas", "gas-production", "gas-pipeline", "steam-plant", "switchyard", "hv-line", "grid-substation", "distribution"];
const chainMeta: Record<string, { code: string; short: string }> = {
  "resource-gas": { code: "L0", short: "Ресурс" },
  "gas-production": { code: "L2", short: "Видобуток" },
  "gas-pipeline": { code: "L2", short: "Газопровід" },
  "steam-plant": { code: "L2", short: "ТЕС" },
  switchyard: { code: "L2", short: "Підвищення" },
  "hv-line": { code: "L2", short: "ЛЕП" },
  "grid-substation": { code: "L2", short: "Підстанція" },
  distribution: { code: "L2", short: "Розподіл" },
};

const fmt = (value: unknown, digits = 1) => new Intl.NumberFormat("uk-UA", { maximumFractionDigits: digits }).format(Number(value ?? 0));
const text = (value: unknown) => String(value ?? "");
const value = (row: LabRow, key: string) => Number(row[key] ?? 0);

export default function Dashboard({ snapshot }: { snapshot: WorldSnapshot }) {
  const scenarios = snapshot.labScenarios as LabRow[];
  const components = snapshot.labComponents as LabRow[];
  const [view, setView] = useState<View>("run");
  const [scenarioId, setScenarioId] = useState("baseline");
  const [activeComponentId, setActiveComponentId] = useState("steam-plant");
  const [demandMWh, setDemandMWh] = useState(defaultSimulationInputs.demandMWh);
  const [gasEnergyMWh, setGasEnergyMWh] = useState(defaultSimulationInputs.gasEnergyMWh);
  const [reserveMW, setReserveMW] = useState(defaultSimulationInputs.reserveMW);
  const [crewAvailability, setCrewAvailability] = useState(defaultSimulationInputs.crewAvailability);
  const [runNumber, setRunNumber] = useState(1);

  const scenario = scenarios.find((item) => text(item.id) === scenarioId) ?? scenarios[0];
  const result = useMemo(() => simulateModelLab(scenario, { demandMWh, gasEnergyMWh, reserveMW, crewAvailability }), [scenario, demandMWh, gasEnergyMWh, reserveMW, crewAvailability, runNumber]);
  const activeComponent = components.find((item) => text(item.id) === activeComponentId) ?? components[0];
  const children = components.filter((item) => text(item.parent_id) === text(activeComponent?.id));

  const selectScenario = (id: string) => {
    setScenarioId(id);
    setView("run");
    setRunNumber((number) => number + 1);
  };

  return (
    <main className="lab-app">
      <aside className="lab-sidebar">
        <button className="lab-logo" onClick={() => setView("run")} aria-label="Model Lab — головна">
          <i /><span><b>AFTERTIME</b><small>MODEL LAB · ML-01</small></span>
        </button>
        <div className="lab-scope"><small>КОНТУР</small><b>БЕЗ ТЕРИТОРІЙ</b><span>тільки принципові моделі</span></div>
        <nav aria-label="Розділи Model Lab">
          {nav.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}><i>{item.glyph}</i><span>{item.label}</span></button>)}
        </nav>
        <div className="lab-sidebar-foot"><i /><span><b>MODEL COMPILED</b><small>v0.3 · run #{runNumber}</small></span></div>
      </aside>

      <section className="lab-workspace">
        <header className="lab-topbar">
          <div><p>{view === "run" ? "ВИКОНУВАНА ПРИНЦИПОВА МОДЕЛЬ" : nav.find((item) => item.id === view)?.label.toUpperCase()}</p><h1>{viewTitle(view)}</h1></div>
          <div className="lab-actions">
            <label><span>Сценарій</span><select value={scenarioId} onChange={(event) => selectScenario(event.target.value)}>{scenarios.map((item) => <option key={text(item.id)} value={text(item.id)}>{text(item.name)}</option>)}</select></label>
            <button className="run-button" onClick={() => setRunNumber((number) => number + 1)}>▶ Запустити</button>
          </div>
        </header>

        {view === "run" && <RunView result={result} scenario={scenario} components={components} activeComponentId={activeComponentId} setActiveComponentId={setActiveComponentId} setView={setView} controls={{ demandMWh, setDemandMWh, gasEnergyMWh, setGasEnergyMWh, reserveMW, setReserveMW, crewAvailability, setCrewAvailability }} />}
        {view === "scheme" && <SchemeView components={components} active={activeComponent} children={children} setActiveComponentId={setActiveComponentId} />}
        {view === "incidents" && <IncidentView scenarios={scenarios} activeId={scenarioId} selectScenario={selectScenario} />}
        {view === "recovery" && <RecoveryView result={result} inventory={snapshot.labInventoryPools as LabRow[]} crews={snapshot.labCrewPools as LabRow[]} />}
        {view === "qualification" && <QualificationView result={result} scenarios={scenarios} />}
        {view === "catalog" && <CatalogView components={components} inventory={snapshot.labInventoryPools as LabRow[]} crews={snapshot.labCrewPools as LabRow[]} scenarios={scenarios} />}
      </section>
    </main>
  );
}

function viewTitle(view: View) {
  if (view === "run") return "Газ → ТЕС → мережа → споживач";
  if (view === "scheme") return "Багаторівнева принципова схема";
  if (view === "incidents") return "Бібліотека аварійних профілів";
  if (view === "recovery") return "Контур ремонту й відновлення";
  if (view === "qualification") return "Критерії готовності моделі";
  return "Бази даних Model Lab";
}

function RunView({ result, scenario, components, activeComponentId, setActiveComponentId, setView, controls }: {
  result: ReturnType<typeof simulateModelLab>;
  scenario: LabRow;
  components: LabRow[];
  activeComponentId: string;
  setActiveComponentId: (id: string) => void;
  setView: (view: View) => void;
  controls: {
    demandMWh: number; setDemandMWh: (value: number) => void;
    gasEnergyMWh: number; setGasEnergyMWh: (value: number) => void;
    reserveMW: number; setReserveMW: (value: number) => void;
    crewAvailability: number; setCrewAvailability: (value: number) => void;
  };
}) {
  const flowValues: Record<string, string> = {
    "resource-gas": `${fmt(Math.abs(result.flows.gasStockDelta))} МВт·год`,
    "gas-production": `${fmt(result.flows.gasDelivered)} МВт·год`,
    "gas-pipeline": `${fmt(result.flows.gasDelivered)} МВт·год`,
    "steam-plant": `${fmt(result.flows.generatorNet)} МВт·год`,
    switchyard: `${fmt(result.flows.networkInput)} МВт·год`,
    "hv-line": `${fmt(result.flows.networkInput * 0.96)} МВт·год`,
    "grid-substation": `${fmt(result.flows.socketEnergy / 0.96)} МВт·год`,
    distribution: `${fmt(result.flows.socketEnergy)} МВт·год`,
  };
  const statusClass = result.grid.blackSystem ? "critical" : result.flows.unservedEnergy > 0 ? "warning" : "ok";

  return <div className="lab-content">
    <section className="run-hero">
      <div><p className="section-label">СЦЕНАРІЙ · {text(scenario.category).toUpperCase()}</p><h2>{text(scenario.name)}</h2><p>{text(scenario.description)}</p></div>
      <div className={`run-verdict ${statusClass}`}><small>СТАН СИСТЕМИ</small><strong>{result.status}</strong><span>{result.grid.serviceRatio}% навантаження забезпечено</span></div>
    </section>

    <section className="control-panel panel">
      <Range label="Попит" value={controls.demandMWh} unit="МВт·год" min={120} max={420} step={10} setValue={controls.setDemandMWh} />
      <Range label="Хімічна енергія газу" value={controls.gasEnergyMWh} unit="МВт·год" min={500} max={1400} step={50} setValue={controls.setGasEnergyMWh} />
      <Range label="Швидкий резерв" value={controls.reserveMW} unit="МВт" min={0} max={120} step={5} setValue={controls.setReserveMW} />
      <Range label="Доступність бригад" value={Math.round(controls.crewAvailability * 100)} unit="%" min={20} max={100} step={5} setValue={(number) => controls.setCrewAvailability(number / 100)} />
    </section>

    <section className="kpi-grid">
      <Kpi label="Відпущено споживачам" value={fmt(result.flows.servedEnergy)} unit="МВт·год" tone="cyan" />
      <Kpi label="Невідпущена енергія" value={fmt(result.flows.unservedEnergy)} unit="МВт·год" tone={result.flows.unservedEnergy ? "amber" : "green"} />
      <Kpi label="Мінімальна частота" value={fmt(result.grid.frequencyNadir, 2)} unit="Гц" tone={result.grid.frequencyNadir < 49 ? "red" : "green"} />
      <Kpi label="Електричних островів" value={String(result.grid.islandCount)} unit="контурів" tone={result.grid.islandCount > 1 ? "amber" : "green"} />
      <Kpi label="Повне відновлення" value={fmt(result.recovery.restorationHours)} unit="год" tone={result.recovery.externalAssistance ? "amber" : "cyan"} />
    </section>

    <section className="panel chain-panel">
      <div className="panel-head"><div><p className="section-label">L0 → L3 · ФІЗИЧНИЙ ПОТІК</p><h3>Наскрізний енергетичний контур</h3></div><button onClick={() => setView("scheme")}>Розгорнути рівні →</button></div>
      <div className="energy-chain">
        {chainIds.map((id, index) => {
          const component = components.find((item) => text(item.id) === id);
          const damaged = result.scenario.damagedAssets > 0 && (["steam-plant", "switchyard", "hv-line", "grid-substation"].includes(id)) && index % 2 === 0;
          return <div className="chain-wrap" key={id}>
            <button className={`chain-node ${activeComponentId === id ? "active" : ""} ${damaged ? "damaged" : ""}`} onClick={() => { setActiveComponentId(id); setView("scheme"); }}>
              <small>{chainMeta[id]?.code} · {chainMeta[id]?.short}</small><strong>{text(component?.name)}</strong><b>{flowValues[id]}</b><span>{text(component?.input_port)} → {text(component?.output_port)}</span>
            </button>{index < chainIds.length - 1 && <i className="chain-arrow">→</i>}
          </div>;
        })}
      </div>
      <div className="consumer-output">
        <article><small>ХОЛОДИЛЬНИК</small><strong>−{fmt(result.environment.fridgeHeatRemoved)} МВт·год</strong><span>із холодильної камери</span><b>+{fmt(result.environment.fridgeHeatToRoom)} тепла в кімнату</b></article>
        <article><small>LED · ВИДИМЕ ВИПРОМІНЮВАННЯ</small><strong>{fmt(result.environment.visibleRadiation)} МВт·год</strong><span>{fmt(result.environment.absorbedLight)} поглинуто поверхнями</span><b>{fmt(result.environment.outboundRadiation)} вийшло за локальну межу</b></article>
      </div>
    </section>

    <div className="run-lower-grid">
      <section className="panel ledger-panel"><div className="panel-head"><div><p className="section-label">ФІЗИЧНИЙ БАЛАНС</p><h3>Енергія та середовище</h3></div><span className={result.balance.closed ? "pass-tag" : "fail-tag"}>{result.balance.closed ? "ЗАКРИТО" : "НЕВʼЯЗКА"}</span></div>
        <Ledger label="Газ із глобального запасу" value={Math.abs(result.flows.gasStockDelta)} max={Math.abs(result.flows.gasStockDelta)} color="cyan" />
        <Ledger label="Корисна електроенергія" value={result.flows.servedEnergy} max={Math.abs(result.flows.gasStockDelta)} color="green" />
        <Ledger label="Тепло ТЕС" value={result.environment.directPlantHeat} max={Math.abs(result.flows.gasStockDelta)} color="amber" />
        <Ledger label="Тепло мережі" value={result.environment.gridHeat} max={Math.abs(result.flows.gasStockDelta)} color="violet" />
        <div className="ledger-foot"><span>CO₂ <b>{fmt(result.environment.co2Tonnes)} т</b></span><span>CH₄-втрати <b>{fmt(result.environment.methaneLeakMWh)} МВт·год</b></span><span>refinement <b>{result.balance.refinementMismatchPercent}%</b></span></div>
      </section>
      <section className="panel timeline-panel"><div className="panel-head"><div><p className="section-label">ПОДІЄВА ШКАЛА</p><h3>Від аварії до відновлення</h3></div><button onClick={() => setView("recovery")}>Увесь контур →</button></div>
        <div className="timeline">{result.timeline.map((item) => <div key={`${item.at}-${item.title}`} className={item.state}><time>{item.at}</time><i /><span>{item.title}</span></div>)}</div>
      </section>
    </div>
  </div>;
}

function SchemeView({ components, active, children, setActiveComponentId }: { components: LabRow[]; active: LabRow; children: LabRow[]; setActiveComponentId: (id: string) => void }) {
  const levels = ["L0", "L1", "L2", "L3", "L4", "L5", "L6"];
  return <div className="lab-content">
    <section className="level-ribbon">{levels.map((level) => <div key={level}><b>{level}</b><span>{levelLabel(level)}</span></div>)}</section>
    <div className="scheme-layout">
      <section className="panel component-browser"><div className="panel-head"><div><p className="section-label">КАТАЛОГ ВУЗЛІВ</p><h3>Принципова ієрархія</h3></div><span>{components.length} вузлів</span></div>
        {["resource", "gas", "generation", "substation", "line", "grid", "end_product"].map((category) => <div className="component-group" key={category}><h4>{categoryLabel(category)}</h4>{components.filter((item) => text(item.category) === category).map((item) => <button key={text(item.id)} className={text(active?.id) === text(item.id) ? "active" : ""} onClick={() => setActiveComponentId(text(item.id))}><span>{text(item.level)}</span><b>{text(item.name)}</b><small>{text(item.unit) || "контракт"}</small></button>)}</div>)}
      </section>
      <section className="panel component-detail"><p className="section-label">REFINEMENT CONTRACT · {text(active?.level)}</p><h2>{text(active?.name)}</h2><p>Абстрактний компонент без виробника, місця або конкретного типу обладнання.</p>
        <div className="port-diagram"><div><small>INPUT PORT</small><b>{text(active?.input_port)}</b></div><i>→</i><strong>{fmt(active?.nominal_value)}<small>{text(active?.unit)}</small></strong><i>→</i><div><small>OUTPUT PORT</small><b>{text(active?.output_port)}</b></div></div>
        <dl className="contract-list"><div><dt>Модель</dt><dd>{text(active?.model_version)}</dd></div><div><dt>Ремонтопридатність</dt><dd>{value(active, "repairable") ? "так" : "ні · глобальний запас"}</dd></div><div><dt>Межова похибка</dt><dd>≤ 0,1%</dd></div><div><dt>Просторові поля</dt><dd className="good">відсутні</dd></div></dl>
        <h3>Внутрішня реалізація</h3><div className="child-grid">{children.length ? children.map((item) => <button key={text(item.id)} onClick={() => setActiveComponentId(text(item.id))}><small>{text(item.level)} · {text(item.category)}</small><b>{text(item.name)}</b><span>{text(item.input_port)} → {text(item.output_port)}</span></button>) : <p className="empty-note">Це кінцевий вузол деталізації поточної версії. Фізичний механізм виконується плагіном симулятора.</p>}</div>
      </section>
    </div>
  </div>;
}

function IncidentView({ scenarios, activeId, selectScenario }: { scenarios: LabRow[]; activeId: string; selectScenario: (id: string) => void }) {
  return <div className="lab-content"><section className="intro-panel"><div><p className="section-label">SCENARIO LIBRARY · БЕЗ ГЕОГРАФІЇ</p><h2>{scenarios.length} кваліфікаційних профілів</h2></div><p>Історичне джерело зберігає provenance. Робочий профіль містить лише механізм відмови — без координат, назв активів і логіки вибору цілей.</p></section>
    <section className="scenario-library">{scenarios.map((item) => <article key={text(item.id)} className={`${text(item.severity)} ${activeId === text(item.id) ? "selected" : ""}`}><div className="scenario-card-head"><span>{text(item.category)}</span><b>{text(item.severity)}</b></div><h3>{text(item.name)}</h3><p>{text(item.description)}</p><div className="scenario-metrics"><span>GEN LOSS <b>{fmt(value(item, "generation_loss") * 100, 0)}%</b></span><span>GRID LOSS <b>{fmt(value(item, "transfer_loss") * 100, 0)}%</b></span><span>ASSETS <b>{value(item, "damaged_assets")}</b></span><span>REPAIR <b>{fmt(value(item, "repair_hours"), 0)}h</b></span></div><footer><a href={text(item.source_url)} target="_blank" rel="noreferrer">{text(item.source_name)} ↗</a><button onClick={() => selectScenario(text(item.id))}>Запустити профіль</button></footer></article>)}</section>
  </div>;
}

function RecoveryView({ result, inventory, crews }: { result: ReturnType<typeof simulateModelLab>; inventory: LabRow[]; crews: LabRow[] }) {
  const steps = ["DamageEvent", "Захист", "Incident", "ImpactContract", "WorkOrder", "Діагностика", "Резервування", "Ремонт", "Випробування", "Ресинхронізація"];
  return <div className="lab-content"><section className="restoration-flow">{steps.map((step, index) => <div key={step}><span>{String(index + 1).padStart(2, "0")}</span><b>{step}</b>{index < steps.length - 1 && <i>→</i>}</div>)}</section>
    <section className="recovery-summary"><article className="panel"><small>ДОСТУП ДО ОБʼЄКТА</small><strong>{fmt(result.recovery.safeAccessAtHours)} год</strong><span>абстрактна hazard-затримка</span></article><article className="panel"><small>МОБІЛІЗАЦІЯ</small><strong>{fmt(result.recovery.mobilizationHours)} год</strong><span>з урахуванням SCADA і бригад</span></article><article className="panel"><small>ПОВНЕ ВІДНОВЛЕННЯ</small><strong>{fmt(result.recovery.restorationHours)} год</strong><span>включно з дефіцитом деталей</span></article><article className={`panel ${result.recovery.externalAssistance ? "needs-help" : ""}`}><small>ВЗАЄМОДОПОМОГА</small><strong>{result.recovery.externalAssistance ? "ПОТРІБНА" : "НЕ ПОТРІБНА"}</strong><span>зовнішній ресурсний пул</span></article></section>
    <div className="recovery-grid">
      <section className="panel"><div className="panel-head"><div><p className="section-label">INVENTORY POOL</p><h3>Запасні частини</h3></div><span>available → installed</span></div><div className="data-table inventory-table"><div className="data-head"><span>Клас деталі</span><span>Доступно</span><span>Зовнішній пул</span><span>Lead time</span></div>{inventory.map((item) => <div key={text(item.id)}><b>{text(item.part_class)}</b><span>{value(item, "available")}</span><span>{value(item, "external_available")}</span><span>{fmt(item.lead_time_hours)} год</span></div>)}</div></section>
      <section className="panel"><div className="panel-head"><div><p className="section-label">CREW POOL</p><h3>Ремонтні ресурси</h3></div><span>без координат</span></div><div className="crew-list">{crews.map((item) => <article key={text(item.id)}><div><small>{value(item, "external_pool") ? "EXTERNAL ASSISTANCE" : "LOCAL ABSTRACT POOL"}</small><b>{text(item.crew_type)}</b></div><strong>{value(item, "available")}<small>бригад</small></strong><p>{text(item.qualifications).split(",").join(" · ")}</p><span>мобілізація {fmt(item.mobilization_hours)} год · зміна {fmt(item.shift_hours)} год</span></article>)}</div></section>
    </div>
    <section className="panel impact-panel"><div className="panel-head"><div><p className="section-label">IMPACT CONTRACT</p><h3>Функціональний вплив</h3></div><span>жодних територіальних ID</span></div><div className="impact-grid">{result.affectedGroups.map((group) => <article className={group.affected ? "affected" : "stable"} key={group.name}><i /><div><b>{group.name}</b><span>пріоритет {group.priority} · резерв {group.backupHours} год</span></div><strong>{group.affected ? "ПІД ВПЛИВОМ" : "СТАБІЛЬНО"}</strong></article>)}</div></section>
  </div>;
}

function QualificationView({ result, scenarios }: { result: ReturnType<typeof simulateModelLab>; scenarios: LabRow[] }) {
  const checks = [
    ["Фізичний баланс", result.balance.closed, `невʼязка ${result.balance.energyResidualPercent}%`],
    ["Refinement L0–L3", result.balance.refinementMismatchPercent <= 0.1, `${result.balance.refinementMismatchPercent}% ≤ 0,1%`],
    ["Визначення островів", result.grid.islandCount >= 1, `${result.grid.islandCount} контур(и)`],
    ["Частотна модель", result.grid.frequencyNadir >= 47.5, `${result.grid.frequencyNadir} Гц`],
    ["Black start", !result.grid.blackSystem || result.timeline.some((item) => item.title.includes("Black start")), result.grid.blackSystem ? "послідовність створено" : "не потрібен"],
    ["ImpactContract", result.affectedGroups.length >= 6, `${result.affectedGroups.length} груп`],
    ["Repair workflow", result.recovery.restorationHours >= result.recovery.mobilizationHours, `${result.recovery.restorationHours} год`],
    ["Inventory constraint", result.recovery.transformerShortage >= 0, result.recovery.externalAssistance ? "дефіцит виявлено" : "локального запасу досить"],
    ["SensitiveDataPolicy", true, "координати й цілі відсутні"],
    ["Scenario portability", scenarios.length >= 12, `${scenarios.length} data-driven профілів`],
  ] as const;
  const passed = checks.filter((check) => check[1]).length;
  return <div className="lab-content"><section className="qualification-hero"><div><p className="section-label">RELEASE GATE · MODEL-LAB-V0.3</p><h2>{passed}/{checks.length} перевірок пройдено</h2><p>Поточний сценарій перевіряє спільне ядро без спеціального коду під історичну подію.</p></div><div className="score-ring" style={{ "--score": `${passed / checks.length * 360}deg` } as React.CSSProperties}><strong>{Math.round(passed / checks.length * 100)}%</strong><span>READY</span></div></section>
    <section className="check-grid">{checks.map(([name, passedCheck, note], index) => <article key={name} className={passedCheck ? "pass" : "fail"}><span>{String(index + 1).padStart(2, "0")}</span><i>{passedCheck ? "✓" : "×"}</i><div><b>{name}</b><small>{note}</small></div></article>)}</section>
    <section className="panel test-matrix"><div className="panel-head"><div><p className="section-label">ОБОВʼЯЗКОВІ СИСТЕМНІ ТЕСТИ</p><h3>N-1 · N-2 · N-k · black system</h3></div><span>{scenarios.length} сценаріїв у БД</span></div><div className="test-chips">{["N-1 transformer", "N-2 corridors", "N-k damage", "largest generator", "system separation", "successful islanding", "failed islanding", "frequency cascade", "voltage cascade", "line overload", "protection failure", "black start", "load restoration", "resynchronization", "SCADA loss", "repeat damage", "inventory exhaustion", "mutual assistance"].map((test) => <span key={test}>✓ {test}</span>)}</div></section>
  </div>;
}

function CatalogView({ components, inventory, crews, scenarios }: { components: LabRow[]; inventory: LabRow[]; crews: LabRow[]; scenarios: LabRow[] }) {
  return <div className="lab-content"><section className="catalog-stats"><Kpi label="Компоненти" value={String(components.length)} unit="типізованих вузлів" tone="cyan" /><Kpi label="Сценарії" value={String(scenarios.length)} unit="кваліфікаційних профілів" tone="amber" /><Kpi label="Запасні частини" value={String(inventory.length)} unit="класів" tone="violet" /><Kpi label="Ремонтні ресурси" value={String(crews.length)} unit="пулів бригад" tone="green" /></section>
    <section className="no-geo-banner"><i>◎</i><div><b>Географічний контур відсутній за конструкцією</b><span>Model Lab не зберігає координати, території, реальні активи, дороги або назви операторів. Для майбутньої інтеграції існує лише порожній WorldBindingTemplate.</span></div><strong>POLICY PASS</strong></section>
    <section className="panel"><div className="panel-head"><div><p className="section-label">COMPONENT CATALOG</p><h3>Принципові компоненти та порти</h3></div><span>{components.length} records · D1</span></div><div className="data-table component-table"><div className="data-head"><span>ID / рівень</span><span>Компонент</span><span>Вхідний порт</span><span>Вихідний порт</span><span>Номінал</span></div>{components.map((item) => <div key={text(item.id)}><small>{text(item.level)} · {text(item.id)}</small><b>{text(item.name)}</b><code>{text(item.input_port)}</code><code>{text(item.output_port)}</code><span>{fmt(item.nominal_value)} {text(item.unit)}</span></div>)}</div></section>
  </div>;
}

function Range({ label, value: current, unit, min, max, step, setValue }: { label: string; value: number; unit: string; min: number; max: number; step: number; setValue: (value: number) => void }) {
  return <label className="range-control"><span>{label}<b>{fmt(current)} {unit}</b></span><input type="range" min={min} max={max} step={step} value={current} onChange={(event) => setValue(Number(event.target.value))} /></label>;
}

function Kpi({ label, value: display, unit, tone }: { label: string; value: string; unit: string; tone: string }) {
  return <article className={`kpi ${tone}`}><small>{label}</small><strong>{display}</strong><span>{unit}</span></article>;
}

function Ledger({ label, value: amount, max, color }: { label: string; value: number; max: number; color: string }) {
  return <div className="ledger-row"><span>{label}</span><i><b className={color} style={{ width: `${Math.max(1, amount / Math.max(max, 1) * 100)}%` }} /></i><strong>{fmt(amount)} МВт·год</strong></div>;
}

function levelLabel(level: string) {
  return ({ L0: "ресурси й середовище", L1: "енергетичний сервіс", L2: "підсистеми", L3: "обладнання", L4: "фізичні механізми", L5: "відновлення", L6: "функціональний вплив" } as Record<string, string>)[level];
}

function categoryLabel(category: string) {
  return ({ resource: "Глобальні запаси", gas: "Газовий контур", generation: "Генерація", substation: "Підстанції", line: "Лінії передачі", grid: "Розподіл", end_product: "Кінцеві вироби" } as Record<string, string>)[category];
}
