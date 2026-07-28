"use client";

import { useMemo, useState } from "react";
import type { WorldSnapshot } from "../db/world";

type View = "overview" | "network" | "ledger" | "scenarios" | "sources";
type Row = Record<string, string | number | null>;

const labels: Record<View, string> = {
  overview: "Состояние",
  network: "Сеть возможностей",
  ledger: "Журнал",
  scenarios: "Будущее",
  sources: "Доказательства",
};

const icons: Record<View, string> = {
  overview: "◉",
  network: "⌘",
  ledger: "≡",
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

  const scenario = snapshot.scenarios.find((item) => item.id === scenarioId) ?? snapshot.scenarios[0];
  const run = snapshot.runs.find((item) => item.scenario_id === scenario?.id) ?? snapshot.runs[0];
  const capacity = n(snapshot.capabilities[0]?.available_capacity);
  const bottleneck = Math.min(
    n(scenario?.gas_availability),
    n(scenario?.grid_availability),
    n(scenario?.rail_availability),
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
    if (view === "network") return "Причинная сеть производства";
    if (view === "ledger") return "Трансформации материи и энергии";
    if (view === "scenarios") return "Прогноз будущих состояний";
    return "Происхождение данных";
  }, [view]);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setView("overview")}>
          <span className="orbital"><span /></span>
          <span><b>ORB</b><small>WORLD MODEL / UA</small></span>
        </button>
        <div className="product-switch">
          <button className="active">N-КОНТУР</button>
          <button title="Следующий контур модели">МИР +</button>
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
          <div><p className="eyebrow">ПИЛОТ · АЗОТ → АММИАК → УРОЖАЙ</p><h1>{title}</h1></div>
          <div className="top-actions">
            <label className="sr-only" htmlFor="scenario">Сценарий</label>
            <select id="scenario" value={scenarioId} onChange={(event) => setScenarioId(event.target.value)}>
              {snapshot.scenarios.map((item) => <option key={String(item.id)} value={String(item.id)}>{item.name}</option>)}
            </select>
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
