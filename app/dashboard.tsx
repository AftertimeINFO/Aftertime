"use client";

import { useMemo, useState } from "react";
import type { WorldSnapshot } from "../db/world";
import { baseCircuitInputs, simulateAmmoniaCircuit } from "../db/simulator";

type View = "overview" | "power" | "network" | "ledger" | "lab" | "scenarios" | "sources";
type Row = Record<string, string | number | null>;

const labels: Record<View, string> = {
  overview: "Состояние",
  power: "Електромережа",
  network: "Сеть возможностей",
  ledger: "Журнал",
  lab: "Лаборатория",
  scenarios: "Будущее",
  sources: "Доказательства",
};

const icons: Record<View, string> = {
  overview: "◉",
  power: "ϟ",
  network: "⌘",
  ledger: "≡",
  lab: "⚗",
  scenarios: "⌁",
  sources: "◎",
};

const n = (value: unknown) => Number(value ?? 0);
const fmt = (value: unknown) =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n(value));
const percent = (value: unknown) => `${Math.round(n(value) * 100)}%`;

export default function Dashboard({ snapshot }: { snapshot: WorldSnapshot }) {
  const [view, setView] = useState<View>("overview");
  const [scenarioId, setScenarioId] = useState("scenario-base");
  const [targetKg, setTargetKg] = useState(1000);
  const [gasOverride, setGasOverride] = useState<number | null>(null);
  const [logisticsOverride, setLogisticsOverride] = useState<number | null>(null);
  const [fuelEnergyKwh, setFuelEnergyKwh] = useState(100);
  const [fridgeCount, setFridgeCount] = useState(100);
  const [ledCount, setLedCount] = useState(1000);

  const scenario = snapshot.scenarios.find((item) => item.id === scenarioId) ?? snapshot.scenarios[0];
  const run = snapshot.runs.find((item) => item.scenario_id === scenario?.id) ?? snapshot.runs[0];
  const capacity = n(snapshot.capabilities[0]?.available_capacity);
  const bottleneck = Math.min(
    n(scenario?.gas_availability),
    n(scenario?.grid_availability),
    n(scenario?.logistics_availability),
    n(scenario?.workforce_availability),
  );
  const liveForecast = Math.round(capacity * 365 * bottleneck);
  const atoms = snapshot.entities.filter((item) => item.kind === "atom");
  const molecules = snapshot.entities.filter((item) => item.kind === "molecule");
  const organizations = snapshot.entities.filter((item) =>
    ["state", "company", "person"].includes(String(item.kind)),
  );
  const physicalAssets = snapshot.entities.filter((item) =>
    ["facility", "production_line", "infrastructure", "workforce_pool"].includes(String(item.kind)),
  );

  const title = useMemo(() => {
    if (view === "overview") return "Азотный контур Украины";
    if (view === "power") return "Електроенергія: від генерації до споживання";
    if (view === "network") return "Причинная сеть производства";
    if (view === "ledger") return "Трансформации материи и энергии";
    if (view === "lab") return "Контур одной тонны аммиака";
    if (view === "scenarios") return "Прогноз будущих состояний";
    return "Происхождение данных";
  }, [view]);

  const circuit = useMemo(() => simulateAmmoniaCircuit({
    ...baseCircuitInputs,
    targetDeliveredKg: targetKg,
    gasAvailability: gasOverride ?? n(scenario?.gas_availability),
    gridAvailability: n(scenario?.grid_availability),
    logisticsAvailability: logisticsOverride ?? n(scenario?.logistics_availability),
    workforceAvailability: n(scenario?.workforce_availability),
  }), [targetKg, gasOverride, logisticsOverride, scenario]);

  const power = useMemo(() => {
    const thermalEnergy = fuelEnergyKwh * 0.90;
    const mechanicalEnergy = thermalEnergy * 0.40;
    const generatedPotential = mechanicalEnergy * 0.98;
    const highVoltage = generatedPotential * 0.985;
    const receivingSubstation = highVoltage * 0.96;
    const mediumVoltage = receivingSubstation * 0.985;
    const distributedPotential = mediumVoltage * 0.95;
    const socketPotential = distributedPotential * 0.98 * 0.96;
    const fridgeDemand = fridgeCount * 0.15;
    const ledDemand = ledCount * 0.01;
    const demand = fridgeDemand + ledDemand;
    const served = Math.min(socketPotential, demand);
    const serviceRatio = demand > 0 ? served / demand : 1;
    const fridgeElectricity = fridgeDemand * serviceRatio;
    const ledElectricity = ledDemand * serviceRatio;
    return {
      thermalEnergy,
      mechanicalEnergy,
      generatedPotential,
      highVoltage,
      receivingSubstation,
      mediumVoltage,
      distributedPotential,
      socketPotential,
      demand,
      served,
      surplus: Math.max(0, socketPotential - demand),
      shortfall: Math.max(0, demand - socketPotential),
      fridgeElectricity,
      fridgeHeatRemoved: fridgeElectricity * 3,
      fridgeHeatToRoom: fridgeElectricity * 4,
      ledElectricity,
      ledWaves: ledElectricity * 0.35,
      ledHeat: ledElectricity * 0.65,
      losses: fuelEnergyKwh - socketPotential,
      efficiency: socketPotential / fuelEnergyKwh,
    };
  }, [fuelEnergyKwh, fridgeCount, ledCount]);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setView("overview")}>
          <span className="orbital"><span /></span>
          <span><b>ORB</b><small>WORLD MODEL / UA</small></span>
        </button>
        <div className="product-switch">
          <button className={view === "power" ? "" : "active"} onClick={() => setView("overview")}>N-КОНТУР</button>
          <button className={view === "power" ? "active" : ""} onClick={() => setView("power")}>E-КОНТУР</button>
        </div>
        <nav aria-label="Разделы модели">
          {(Object.keys(labels) as View[]).map((key) => (
            <button key={key} className={view === key ? "active" : ""} onClick={() => setView(key)}>
              <span className="nav-icon">{icons[key]}</span><span>{labels[key]}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <i className="pulse" />
          <span><b>D1 · живая модель</b><small>{snapshot.generatedAt.slice(0, 10)}</small></span>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">{view === "power" ? "ПІЛОТ · ГЕНЕРАЦІЯ → МЕРЕЖА → СПОЖИВАЧІ" : "ПИЛОТ · АЗОТ → АММИАК → УРОЖАЙ"}</p><h1>{title}</h1></div>
          <div className="top-actions">
            {view !== "power" && <><label className="sr-only" htmlFor="scenario">Сценарий</label>
              <select id="scenario" value={scenarioId} onChange={(event) => setScenarioId(event.target.value)}>
                {snapshot.scenarios.map((item) => <option key={String(item.id)} value={String(item.id)}>{item.name}</option>)}
              </select></>}
            <button className="avatar" title="Режим планировщика">PLN</button>
          </div>
        </header>

        {view === "overview" && (
          <div className="content">
            <section className="hero-balance">
              <div><p className="section-label">ПРОГНОЗ ВЫПУСКА · 2027</p><div className="mass-value">{fmt(liveForecast)} <span>т NH₃ / год</span></div></div>
              <div className="balance-state"><i className="state-dot" /><span><b>Материя согласована</b><small>Прогноз ограничен узким местом: {percent(bottleneck)}</small></span></div>
            </section>
            <section className="stats-grid">
              <article><p>Сущностей модели</p><strong>{snapshot.entities.length}</strong><span>узлов</span></article>
              <article><p>Связей</p><strong>{snapshot.relations.length}</strong><span>ребер</span></article>
              <article><p>Критических зависимостей</p><strong>{snapshot.dependencies.length}</strong><span>контуров</span></article>
              <article><p>Доверие прогноза</p><strong className="negative">{percent(run?.confidence)}</strong><span>версия 0.1</span></article>
            </section>
            <section className="panel">
              <div className="panel-head"><div><h2>Один мир — несколько уровней наблюдения</h2><p>Уровни не дублируют материю: они агрегируют одно физическое состояние.</p></div><button className="text-button" onClick={() => setView("network")}>Открыть сеть →</button></div>
              <div className="level-grid">
                <Level code="01" title="Атомарный" value={`${atoms.length} типа`} note="N, H · сохранение элементов" />
                <Level code="02" title="Молекулярный" value={`${molecules.length} типа`} note="N₂, H₂, NH₃ · конфигурации связей" />
                <Level code="03" title="Вещественный" value="Аммиак, карбамид" note="масса, состав, температура, фаза" />
                <Level code="04" title="Объектный" value={`${physicalAssets.length} активов`} note="линия, завод, сеть, персонал" />
                <Level code="05" title="Институциональный" value={`${organizations.length} субъекта`} note="государство, компания, человек" />
              </div>
            </section>
            <section className="panel">
              <div className="panel-head"><div><h2>Доступность производственного контура</h2><p>Итог определяет минимальная доступность обязательной зависимости.</p></div><span className="tag">MIN-OPERATOR</span></div>
              <div className="dependency-bars">
                {snapshot.dependencies.map((item) => <Dependency key={String(item.id)} item={item} />)}
              </div>
            </section>
          </div>
        )}

        {view === "power" && (
          <div className="content power-content">
            <section className="power-hero">
              <div>
                <p className="section-label">ТЕСТОВА МОДЕЛЬ · 1 ГОДИНА · {snapshot.testModels[0]?.model_version}</p>
                <h2>{fmt(power.socketPotential)} <span>кВт·год потенціалу в кінцевій мережі</span></h2>
                <p>Паливо проходить послідовні перетворення на тепло, механічне обертання та електричний потенціал. Після передачі мережею холодильник змінює температурний баланс, а LED-лампа створює електромагнітні хвилі.</p>
              </div>
              <div className={`power-efficiency ${power.shortfall > 0 ? "limited" : ""}`}><small>СТАН ТЕСТУ</small><strong>{power.shortfall > 0 ? "ДЕФІЦИТ" : "ПРАЦЮЄ"}</strong><span>{power.shortfall > 0 ? `не вистачає ${fmt(power.shortfall)} кВт·год` : `резерв ${fmt(power.surplus)} кВт·год`}</span></div>
            </section>

            <section className="panel power-controls">
              <label>Енергія палива <b>{fmt(fuelEnergyKwh)} кВт·год</b><input type="range" min="20" max="500" step="10" value={fuelEnergyKwh} onChange={(event) => setFuelEnergyKwh(Number(event.target.value))} /></label>
              <label>Холодильники <b>{fridgeCount} шт.</b><input type="range" min="0" max="300" step="10" value={fridgeCount} onChange={(event) => setFridgeCount(Number(event.target.value))} /></label>
              <label>LED-лампи <b>{ledCount} шт.</b><input type="range" min="0" max="3000" step="100" value={ledCount} onChange={(event) => setLedCount(Number(event.target.value))} /></label>
            </section>

            <section className="registry-grid" aria-label="Бази даних моделі">
              <RegistryCard title="Технології" count={snapshot.technologies.length} note="перетворення й коефіцієнти" />
              <RegistryCard title="Принципові системи" count={snapshot.principleSystems.length} note="складені функціональні контури" />
              <RegistryCard title="Кінцеві вироби" count={snapshot.endProducts.length} note="споживачі та корисні ефекти" />
              <RegistryCard title="Тестові моделі" count={snapshot.testModels.length} note={`${snapshot.testModelComponents.length} зібраних компонентів`} />
              <RegistryCard title="Реальні системи" count={snapshot.realSystems.length} note="точні й приблизні геоприв’язки" />
              <RegistryCard title="Територіальні одиниці" count={snapshot.territorialUnits.length} note="агреговані користувачі та невизначеність" />
            </section>

            <section className="panel power-model" aria-label="Схема передачі електроенергії">
              <div className="power-backbone">
                <PowerNode code="01 · РЕСУРС" title="Паливо" value={`${fmt(fuelEnergyKwh)} кВт·год`} note="Хімічна енергія · вхід із матеріального балансу" tone="source" />
                <PowerLink label="90%" />
                <PowerNode code="02 · ТЕПЛО" title="Котел / реактор" value={`${fmt(power.thermalEnergy)} кВт·год`} note="Спалювання палива → теплова енергія" />
                <PowerLink label="40%" />
                <PowerNode code="03 · РОБОТА" title="Парова турбіна" value={`${fmt(power.mechanicalEnergy)} кВт·год`} note="Тепло → механічне обертання вала" />
                <PowerLink label="98%" />
                <PowerNode code="04 · ПОТЕНЦІАЛ" title="Генератор" value={`${fmt(power.generatedPotential)} кВт·год`} note="Обертання → електричний потенціал 11–24 кВ" />
                <PowerLink label="−1,5%" />
                <PowerNode code="05 · ПІДВИЩЕННЯ" title="Трансформатор" value={`${fmt(power.highVoltage)} кВт·год`} note="Підвищення до 110–750 кВ" />
                <PowerLink label="−4%" />
                <PowerNode code="06 · ПЕРЕДАЧА" title="Магістральна ЛЕП" value={`${fmt(power.receivingSubstation)} кВт·год`} note="Передача електричного потенціалу на відстань" />
                <PowerLink label="−1,5%" />
                <PowerNode code="07 · ПІДСТАНЦІЯ" title="Приймальна підстанція" value={`${fmt(power.mediumVoltage)} кВт·год`} note="Комутація, захист і зниження напруги" />
                <PowerLink label="−5%" />
                <PowerNode code="08 · РОЗПОДІЛ" title="Мережа 6–35 кВ" value={`${fmt(power.distributedPotential)} кВт·год`} note="Розподіл до локального трансформатора" />
              </div>

              <div className="power-split"><span>ТРАНСФОРМАТОР 0,4 КВ + НИЗЬКОВОЛЬТНА МЕРЕЖА · {fmt(power.socketPotential)} КВТ·ГОД ДОСТУПНО</span></div>

              <div className="consumer-grid">
                <article className="consumer-path">
                  <div className="branch-line"><span>{fmt(power.fridgeElectricity)} кВт·год</span></div>
                  <PowerNode code="09A · КІНЦЕВИЙ ВИРІБ" title={`${fridgeCount} × холодильник`} value="COP 3,0" note="Потенціал → компресор → зміна балансу температури" />
                  <div className="consumer-card civil"><small>ТЕМПЕРАТУРНИЙ БАЛАНС</small><strong>−{fmt(power.fridgeHeatRemoved)} кВт·год</strong><p>Відведено з камер; {fmt(power.fridgeHeatToRoom)} кВт·год тепла передано приміщенню</p></div>
                </article>
                <article className="consumer-path">
                  <div className="branch-line"><span>{fmt(power.ledElectricity)} кВт·год</span></div>
                  <PowerNode code="09B · КІНЦЕВИЙ ВИРІБ" title={`${ledCount} × LED-лампа`} value="35% → хвилі" note="Потенціал → електромагнітні хвилі + тепло" />
                  <div className="consumer-card industry"><small>ЕЛЕКТРОМАГНІТНЕ ВИПРОМІНЮВАННЯ</small><strong>{fmt(power.ledWaves)} кВт·год</strong><p>У хвилях; {fmt(power.ledHeat)} кВт·год розсіяно як тепло</p></div>
                </article>
              </div>
            </section>

            <section className="power-balance-grid">
              <article className="panel"><small>ХІМІЧНА ЕНЕРГІЯ ПАЛИВА</small><strong>{fmt(fuelEnergyKwh)}</strong><span>кВт·год на вході</span></article>
              <article className="panel"><small>ПОТЕНЦІАЛ У РОЗЕТЦІ</small><strong>{fmt(power.socketPotential)}</strong><span>кВт·год після всіх ланок</span></article>
              <article className="panel"><small>ПОПИТ ВИРОБІВ</small><strong>{fmt(power.demand)}</strong><span>кВт·год за одну годину</span></article>
              <article className="panel balance-ok"><small>СУМІСНА РОБОТА</small><strong>{power.shortfall > 0 ? "ОБМЕЖЕНА" : "СТАБІЛЬНА"}</strong><span>спожито {fmt(power.served)} кВт·год</span></article>
            </section>
          </div>
        )}

        {view === "network" && (
          <div className="content">
            <section className="transform-hero">
              <div><p className="section-label">CAUSAL DIGITAL TWIN</p><h2>Прогноз строится из возможностей и ограничений, а не только из запасов.</h2><p>Завод производит аммиак лишь при одновременной доступности сырья, энергии, оборудования, логистики, специалистов и управляющей организации.</p></div>
              <span className="status-good">{snapshot.dependencies.length} зависимости активны</span>
            </section>
            <section className="panel network-canvas">
              <div className="network-column">
                <p>ВХОДЫ И УСЛОВИЯ</p>
                {snapshot.dependencies.map((item) => <Node key={String(item.id)} title={String(item.dependency_name)} subtitle={`${item.role} · ${percent(item.availability)}`} />)}
              </div>
              <div className="network-arrow">→</div>
              <div className="network-column core"><p>ВОЗМОЖНОСТЬ</p><Node title="Линия синтеза аммиака №1" subtitle={`${fmt(capacity)} т/день доступно`} /><small>Haber–Bosch · model v0.1</small></div>
              <div className="network-arrow">→</div>
              <div className="network-column"><p>РЕЗУЛЬТАТЫ</p><Node title="Аммиак NH₃" subtitle={`${fmt(liveForecast)} т/год`} /><Node title="Карбамид" subtitle="следующая трансформация" /><Node title="Урожай зерновых" subtitle="эффект высокого уровня" /></div>
            </section>
            <section className="panel"><div className="panel-head"><div><h2>Критичность и восстановление</h2><p>Эти параметры позволяют моделировать отказ и время возвращения системы.</p></div></div>
              <div className="data-table">
                <div className="table-row table-head"><span>Зависимость</span><span>Роль</span><span>Доступность</span><span>Критичность</span><span>Восстановление</span></div>
                {snapshot.dependencies.map((item) => <div className="table-row" key={String(item.id)}><b>{item.dependency_name}</b><span>{item.role}</span><span>{percent(item.availability)}</span><span>{percent(item.criticality)}</span><span>{item.recovery_days} дней</span></div>)}
              </div>
            </section>
          </div>
        )}

        {view === "ledger" && (
          <div className="content">
            <section className="transform-hero"><div><p className="section-label">EVENT-SOURCED PHYSICS</p><h2>Операция — наблюдаемая трансформация состояния.</h2><p>Двойная запись отражает вход и выход, а проверки сохранения выполняются на выбранном физическом уровне.</p></div><span className="status-good">Сверено</span></section>
            {snapshot.events.map((event) => (
              <section className="panel" key={String(event.id)}>
                <div className="panel-head"><div><h2>{event.name}</h2><p>{event.started_at} · {event.model_version}</p></div><span className="tag">{event.status}</span></div>
                <div className="posting-grid">
                  {snapshot.postings.map((post) => <article key={String(post.id)} className={post.direction === "in" ? "posting in" : "posting out"}><small>{post.direction === "in" ? "ДЕБЕТ · ПОЯВЛЕНИЕ" : "КРЕДИТ · УБЫТИЕ"}</small><b>{post.entity_name}</b><strong>{post.direction === "in" ? "+" : "−"}{fmt(post.quantity)} {post.unit}</strong><span>{post.account} · {post.level}</span></article>)}
                </div>
                <div className="conservation"><span>Атомы N</span><strong>сохранены</strong><i /><span>Атомы H</span><strong>сохранены</strong><i /><span>Энергия</span><strong>8200 GJ → конфигурация + тепло</strong></div>
              </section>
            ))}
          </div>
        )}

        {view === "lab" && (
          <div className="content">
            <section className="lab-hero">
              <div>
                <p className="section-label">TEST CIRCUIT T0–T7 · {circuit.modelVersion}</p>
                <h2>Произвести и доставить <strong>{fmt(targetKg)} кг</strong> аммиака</h2>
                <p>Расчёт проходит от N₂ и H₂ через синтез, резервуар и транспорт до регионального склада. Все потери, ограничения и допуски остаются видимыми.</p>
              </div>
              <div className={`lab-verdict ${circuit.shortfallKg > 0.5 ? "limited" : ""}`}>
                <small>ДОСТИЖИМО В СЦЕНАРИИ</small>
                <b>{fmt(circuit.achievableDeliveredKg)} кг</b>
                <span>{circuit.shortfallKg > 0.5 ? `дефицит ${fmt(circuit.shortfallKg)} кг` : "цель закрыта"}</span>
              </div>
            </section>

            <section className="panel lab-controls">
              <label>Целевая партия <b>{fmt(targetKg)} кг</b><input type="range" min="100" max="5000" step="100" value={targetKg} onChange={(event) => setTargetKg(Number(event.target.value))} /></label>
              <label>Доступность газа <b>{percent(gasOverride ?? scenario?.gas_availability)}</b><input type="range" min="0.1" max="1" step="0.01" value={gasOverride ?? n(scenario?.gas_availability)} onChange={(event) => setGasOverride(Number(event.target.value))} /></label>
              <label>Доступность доставки <b>{percent(logisticsOverride ?? scenario?.logistics_availability)}</b><input type="range" min="0.1" max="1" step="0.01" value={logisticsOverride ?? n(scenario?.logistics_availability)} onChange={(event) => setLogisticsOverride(Number(event.target.value))} /></label>
              <button className="secondary-button" onClick={() => { setGasOverride(null); setLogisticsOverride(null); }}>Вернуть сценарий</button>
            </section>

            <section className="circuit-flow">
              <CircuitNode phase="01 · СЫРЬЁ" title="N₂ + H₂" value={`${fmt(circuit.inputs.nitrogenKg)} + ${fmt(circuit.inputs.hydrogenKg)} кг`} note={`${circuit.inputs.naturalGasGJ} GJ газа · ${circuit.inputs.waterKg} кг воды`} />
              <span>→</span>
              <CircuitNode phase="02 · СИНТЕЗ" title="Линия NH₃" value={`${fmt(circuit.outputs.grossAmmoniaKg)} кг`} note={`выход процесса ${percent(baseCircuitInputs.processYield)}`} />
              <span>→</span>
              <CircuitNode phase="03 · ХРАНЕНИЕ" title="Резервуар R-01" value={`−${circuit.outputs.storageLossKg} кг`} note="технологические потери 0,2%" />
              <span>→</span>
              <CircuitNode phase="04 · ДОСТАВКА" title="Черкассы → Полтава" value={`−${circuit.outputs.transitLossKg} кг`} note={`${circuit.expectedHours} ч с учётом задержки`} />
              <span>→</span>
              <CircuitNode phase="05 · РЕЗУЛЬТАТ" title="Региональный склад" value={`${fmt(circuit.outputs.deliveredKg)} кг`} note={`${fmt(circuit.lowerKg)}–${fmt(circuit.upperKg)} кг`} good={circuit.shortfallKg < 0.5} />
            </section>

            <section className="lab-grid">
              <article className="panel conservation-card">
                <div className="panel-head"><div><h2>Физическая сверка</h2><p>Атомарный уровень после масштабирования доступностью.</p></div><span className="status-good">{circuit.conservation.closed ? "ЗАКРЫТО" : "РАСХОЖДЕНИЕ"}</span></div>
                <BalanceLine label="Азот" input={circuit.conservation.nitrogenInKg} output={circuit.conservation.nitrogenOutKg} />
                <BalanceLine label="Водород" input={circuit.conservation.hydrogenInKg} output={circuit.conservation.hydrogenOutKg} />
                <footer>Ошибка баланса: <b>{circuit.conservation.errorKg} кг</b></footer>
              </article>
              <article className="panel plan-card">
                <p className="section-label">КОМПЕНСИРУЮЩИЙ ПЛАН</p>
                <h2>{circuit.recommendation.action}</h2>
                <p>{circuit.recommendation.effect}. Узкое место: <b>{bottleneckLabel(circuit.bottleneck)}</b>.</p>
                <div><span>Срок включения</span><b>{circuit.recommendation.leadTimeHours} ч</b></div>
                <div><span>Восстановленный объём</span><b>+{fmt(Math.max(0, circuit.recommendation.recoveredKg))} кг</b></div>
                <div><span>После вмешательства</span><b>{fmt(circuit.recommendation.compensatedDeliveredKg)} кг</b></div>
              </article>
            </section>

            <section className="panel">
              <div className="panel-head"><div><h2>Данные контура</h2><p>Процессы, партии и маршруты загружены из D1, а расчёт выполняется воспроизводимой версией модели.</p></div><span className="tag">{snapshot.processFlows.length} потоков</span></div>
              <div className="lab-data">
                <span><b>{snapshot.processModels.length}</b><small>модель процесса</small></span>
                <span><b>{snapshot.inventoryLots.length}</b><small>прослеживаемая партия</small></span>
                <span><b>{snapshot.transportRoutes.length}</b><small>маршрута</small></span>
                <span><b>{percent(circuit.confidence)}</b><small>доверие расчёта</small></span>
              </div>
            </section>
          </div>
        )}

        {view === "scenarios" && (
          <div className="content">
            <section className="forecast-hero">
              <div><p className="section-label">СЦЕНАРИЙ · {scenario?.name}</p><h2>{fmt(run?.expected_output)} <span>т NH₃ / год</span></h2><p>{scenario?.description}</p></div>
              <div className="forecast-range"><small>ДИАПАЗОН С УЧЕТОМ НЕОПРЕДЕЛЕННОСТИ</small><b>{fmt(run?.lower_bound)} — {fmt(run?.upper_bound)} т</b><span>доверие {percent(run?.confidence)}</span></div>
            </section>
            <section className="scenario-grid">
              {snapshot.scenarios.map((item) => {
                const itemRun = snapshot.runs.find((candidate) => candidate.scenario_id === item.id);
                return <button key={String(item.id)} className={`panel scenario-card ${item.id === scenarioId ? "selected" : ""}`} onClick={() => setScenarioId(String(item.id))}><small>{percent(item.probability)} ВЕС СЦЕНАРИЯ</small><h2>{item.name}</h2><p>{item.description}</p><strong>{fmt(itemRun?.expected_output)} <span>т/год</span></strong><footer>Узкое место: {itemRun?.bottleneck}</footer></button>;
              })}
            </section>
            <section className="panel">
              <div className="panel-head"><div><h2>Рычаги сценария</h2><p>Меняются предпосылки, затем модель пересчитывает достижимое состояние.</p></div><span className="tag">{scenario?.model_version}</span></div>
              <div className="lever-grid">
                <Meter label="Газ" value={scenario?.gas_availability} />
                <Meter label="Электросеть" value={scenario?.grid_availability} />
                <Meter label="Железная дорога" value={scenario?.rail_availability} />
                <Meter label="Персонал" value={scenario?.workforce_availability} />
              </div>
            </section>
          </div>
        )}

        {view === "sources" && (
          <div className="content">
            <section className="transform-hero"><div><p className="section-label">EVIDENCE GRAPH</p><h2>Каждое число остается утверждением источника.</h2><p>Модель хранит происхождение, дату получения, лицензию и способ сопоставления. Конфликтующие оценки могут сосуществовать.</p></div><span className="status-good">{snapshot.sources.length} источника</span></section>
            <section className="source-grid">
              {snapshot.sources.map((source) => <article className="panel source-card" key={String(source.id)}><span className="source-mark">◎</span><small>{source.license || "SOURCE TERMS"}</small><h2>{source.name}</h2><p>{source.url}</p><footer><span>{source.retrieved_at}</span><a href={String(source.url)} target="_blank" rel="noreferrer">Открыть ↗</a></footer></article>)}
            </section>
            <section className="panel"><div className="panel-head"><div><h2>Внешние идентичности</h2><p>Связи внутренних сущностей с научными онтологиями.</p></div><span className="tag">{snapshot.externalIdentities.length} mappings</span></div>
              {snapshot.externalIdentities.map((item) => <div className="mapping-row" key={String(item.id)}><span>◎</span><b>{item.namespace}:{item.external_id}</b><code>{item.mapping_type}</code><strong>{percent(item.confidence)}</strong></div>)}
            </section>
          </div>
        )}
      </section>
    </main>
  );
}

function Level({ code, title, value, note }: { code: string; title: string; value: string; note: string }) {
  return <article><small>{code}</small><h3>{title}</h3><b>{value}</b><p>{note}</p></article>;
}

function Dependency({ item }: { item: Row }) {
  return <div><span><b>{item.dependency_name}</b><small>{item.role}</small></span><i><em style={{ width: percent(item.availability) }} /></i><strong>{percent(item.availability)}</strong></div>;
}

function Node({ title, subtitle }: { title: string; subtitle: string }) {
  return <article className="network-node"><i /><span><b>{title}</b><small>{subtitle}</small></span></article>;
}

function Meter({ label, value }: { label: string; value: unknown }) {
  return <article><span><b>{label}</b><strong>{percent(value)}</strong></span><i><em style={{ width: percent(value) }} /></i></article>;
}

function CircuitNode({ phase, title, value, note, good = false }: { phase: string; title: string; value: string; note: string; good?: boolean }) {
  return <article className={`circuit-node ${good ? "complete" : ""}`}><small>{phase}</small><h3>{title}</h3><b>{value}</b><p>{note}</p></article>;
}

function PowerNode({ code, title, value, note, tone = "" }: { code: string; title: string; value: string; note: string; tone?: string }) {
  return <article className={`power-node ${tone}`}><small>{code}</small><h3>{title}</h3><b>{value}</b><p>{note}</p></article>;
}

function PowerLink({ label }: { label: string }) {
  return <div className="power-link" aria-label={`Втрати ${label}`}><i /><span>{label}</span><b>→</b></div>;
}

function RegistryCard({ title, count, note }: { title: string; count: number; note: string }) {
  return <article className="panel registry-card"><small>БАЗА ДАНИХ</small><strong>{count}</strong><h3>{title}</h3><p>{note}</p></article>;
}

function BalanceLine({ label, input, output }: { label: string; input: number; output: number }) {
  return <div className="balance-line"><b>{label}</b><span>Вход {input} кг</span><i>→</i><span>Выход {output} кг</span><strong>{Math.abs(input - output) < 0.001 ? "✓" : "!"}</strong></div>;
}

function bottleneckLabel(value: string) {
  return ({
    gas: "газоснабжение",
    grid: "электроснабжение",
    logistics: "доставка",
    workforce: "персонал",
  } as Record<string, string>)[value] ?? value;
}
