"use client";

import { useMemo, useState } from "react";

type View = "balance" | "matter" | "transformations" | "inventory";

const matter = [
  { name: "Вода", code: "H₂O", opening: 18500, inflow: 420, outflow: 540, tone: "cyan" },
  { name: "Углерод", code: "C", opening: 3420, inflow: 230, outflow: 196, tone: "lime" },
  { name: "Кислород", code: "O₂", opening: 2100, inflow: 186, outflow: 160, tone: "violet" },
  { name: "Неопределённое", code: "?", opening: 840, inflow: 90, outflow: 98, tone: "amber" },
];

const history = [24860, 24840, 24792, 24818, 24776, 24758, 24792];

const transforms = [
  { id: "TR-0042", date: "28 июл", scheme: "Органика → композит", input: 120, output: 120, status: "Сбалансировано" },
  { id: "TR-0041", date: "24 июл", scheme: "Очистка воды", input: 480, output: 480, status: "Сбалансировано" },
  { id: "TR-0040", date: "19 июл", scheme: "Разделение смеси", input: 215, output: 215, status: "Сбалансировано" },
  { id: "TR-0039", date: "14 июл", scheme: "Термообработка", input: 96, output: 94.8, status: "Требует проверки" },
];

const format = (value: number) =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value);

export default function Home() {
  const [view, setView] = useState<View>("balance");
  const [model, setModel] = useState("Фактическая модель");
  const [range, setRange] = useState("Июль 2026");
  const [selectedMatter, setSelectedMatter] = useState("Вода");
  const [transformAmount, setTransformAmount] = useState(120);

  const total = useMemo(
    () => matter.reduce((sum, item) => sum + item.opening + item.inflow - item.outflow, 0),
    [],
  );
  const selected = matter.find((item) => item.name === selectedMatter) ?? matter[0];
  const maxHistory = Math.max(...history);
  const minHistory = Math.min(...history);
  const points = history
    .map((value, index) => {
      const x = 30 + index * (640 / (history.length - 1));
      const y = 30 + ((maxHistory - value) / (maxHistory - minHistory)) * 150;
      return `${x},${y}`;
    })
    .join(" ");

  const navigate = (next: View) => setView(next);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => navigate("balance")} aria-label="ORB — на главную">
          <span className="orbital"><span /></span>
          <span><b>ORB</b><small>Social Resource Planing</small></span>
        </button>

        <nav aria-label="Основная навигация">
          <button className={view === "balance" ? "active" : ""} onClick={() => navigate("balance")}>
            <span className="nav-icon">◫</span> Баланс
          </button>
          <button className={view === "matter" ? "active" : ""} onClick={() => navigate("matter")}>
            <span className="nav-icon">◉</span> Вещества
          </button>
          <button className={view === "transformations" ? "active" : ""} onClick={() => navigate("transformations")}>
            <span className="nav-icon">⇄</span> Трансформации
          </button>
          <button className={view === "inventory" ? "active" : ""} onClick={() => navigate("inventory")}>
            <span className="nav-icon">⌗</span> Инвентаризация
          </button>
        </nav>

        <div className="sidebar-foot">
          <span className="pulse" />
          <span><b>Система активна</b><small>Демо-среда · API v0.1</small></span>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">ПЛАНЕТАРНЫЙ УЧЁТ МАТЕРИИ</p>
            <h1>{view === "balance" ? "Физический баланс" : view === "matter" ? "Реестр веществ" : view === "transformations" ? "Трансформации" : "Инвентаризация"}</h1>
          </div>
          <div className="top-actions">
            <label>
              <span className="sr-only">Модель данных</span>
              <select value={model} onChange={(event) => setModel(event.target.value)}>
                <option>Фактическая модель</option>
                <option>Прогнозная модель</option>
                <option>Исследовательская модель</option>
              </select>
            </label>
            <button className="avatar" aria-label="Профиль пользователя">AK</button>
          </div>
        </header>

        {view === "balance" && (
          <div className="content">
            <section className="hero-balance">
              <div>
                <p className="section-label">УЧТЁННАЯ МАТЕРИЯ</p>
                <div className="mass-value">{format(total)} <span>кг</span></div>
                <p className="muted">Конечный остаток по всем веществам</p>
              </div>
              <div className="balance-state">
                <span className="state-dot" />
                <span><b>Контур сбалансирован</b><small>Вход = выход + остаток</small></span>
              </div>
            </section>

            <section className="stats-grid">
              <article><p>Начальный остаток</p><strong>24 860</strong><span>кг</span></article>
              <article><p>Приход</p><strong>926</strong><span>кг</span></article>
              <article><p>Расход</p><strong>994</strong><span>кг</span></article>
              <article><p>Изменение</p><strong className="negative">−68</strong><span>кг · −0,27%</span></article>
            </section>

            <section className="panel chart-panel">
              <div className="panel-head">
                <div><h2>Динамика общего остатка</h2><p>{model}</p></div>
                <select value={range} onChange={(event) => setRange(event.target.value)}>
                  <option>Июль 2026</option>
                  <option>Последние 90 дней</option>
                  <option>Текущий год</option>
                </select>
              </div>
              <svg className="line-chart" viewBox="0 0 700 230" role="img" aria-label="Динамика остатка материи за выбранный период">
                <defs>
                  <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--signal)" stopOpacity=".28" />
                    <stop offset="100%" stopColor="var(--signal)" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {[30, 80, 130, 180].map((y) => <line key={y} x1="30" x2="670" y1={y} y2={y} className="gridline" />)}
                <polygon points={`30,180 ${points} 670,180`} fill="url(#area)" />
                <polyline points={points} className="trendline" />
                {history.map((value, index) => {
                  const x = 30 + index * (640 / (history.length - 1));
                  const y = 30 + ((maxHistory - value) / (maxHistory - minHistory)) * 150;
                  return <circle key={index} cx={x} cy={y} r={index === history.length - 1 ? 5 : 3} />;
                })}
                <text x="30" y="218">01 июл</text><text x="350" y="218" textAnchor="middle">15 июл</text><text x="670" y="218" textAnchor="end">31 июл</text>
              </svg>
            </section>

            <section className="panel">
              <div className="panel-head">
                <div><h2>Состав баланса</h2><p>Остатки по веществам</p></div>
                <button className="text-button" onClick={() => navigate("matter")}>Открыть реестр →</button>
              </div>
              <div className="matter-table">
                {matter.map((item) => {
                  const closing = item.opening + item.inflow - item.outflow;
                  return (
                    <button key={item.name} className="matter-row" onClick={() => { setSelectedMatter(item.name); navigate("matter"); }}>
                      <span className={`matter-symbol ${item.tone}`}>{item.code}</span>
                      <span className="matter-name"><b>{item.name}</b><small>{format((closing / total) * 100)}% баланса</small></span>
                      <span className="mini-track"><i style={{ width: `${(closing / total) * 100}%` }} /></span>
                      <span className="row-value"><b>{format(closing)}</b><small>кг</small></span>
                    </button>
                  );
                })}
              </div>
            </section>
          </div>
        )}

        {view === "matter" && (
          <div className="content split-content">
            <section className="panel registry">
              <div className="panel-head"><div><h2>Каталог материи</h2><p>4 типа · уровень L1</p></div><button className="primary-button">+ Добавить вещество</button></div>
              <div className="registry-list">
                {matter.map((item) => {
                  const closing = item.opening + item.inflow - item.outflow;
                  return (
                    <button key={item.name} className={selectedMatter === item.name ? "selected" : ""} onClick={() => setSelectedMatter(item.name)}>
                      <span className={`matter-symbol ${item.tone}`}>{item.code}</span>
                      <span><b>{item.name}</b><small>Материя · L1</small></span>
                      <strong>{format(closing)} кг</strong>
                    </button>
                  );
                })}
              </div>
            </section>
            <aside className="panel detail-panel">
              <span className={`matter-symbol large ${selected.tone}`}>{selected.code}</span>
              <p className="section-label">КАРТОЧКА ВЕЩЕСТВА</p>
              <h2>{selected.name}</h2>
              <p className="muted">Базовый элемент физической модели. Количество рассчитывается по проведённым инвентаризациям и актам трансформации.</p>
              <dl>
                <div><dt>Начальный остаток</dt><dd>{format(selected.opening)} кг</dd></div>
                <div><dt>Приход за период</dt><dd>+{format(selected.inflow)} кг</dd></div>
                <div><dt>Расход за период</dt><dd>−{format(selected.outflow)} кг</dd></div>
                <div><dt>Конечный остаток</dt><dd>{format(selected.opening + selected.inflow - selected.outflow)} кг</dd></div>
              </dl>
            </aside>
          </div>
        )}

        {view === "transformations" && (
          <div className="content">
            <section className="transform-hero">
              <div><p className="section-label">ПРОВЕРКА СОХРАНЕНИЯ</p><h2>Каждый процесс должен сходиться.</h2><p>ORB записывает расход исходных компонентов и приход результатов в единый регистр материи.</p></div>
              <button className="primary-button">+ Новый акт</button>
            </section>
            <section className="panel simulator">
              <div className="panel-head"><div><h2>Органическое сырьё → композит</h2><p>Интерактивный пример схемы трансформации</p></div><span className="status-good">Сбалансировано</span></div>
              <div className="flow">
                <div className="flow-side">
                  <p>ИСХОДНЫЕ КОМПОНЕНТЫ</p>
                  <label>Органическое сырьё <span>{format(transformAmount * .833)} кг</span><input type="range" min="60" max="240" value={transformAmount} onChange={(event) => setTransformAmount(Number(event.target.value))} /></label>
                  <div><span>Вода</span><b>{format(transformAmount * .167)} кг</b></div>
                </div>
                <div className="reactor"><span className="orbital big"><span /></span><small>ТРАНСФОРМАЦИЯ</small></div>
                <div className="flow-side">
                  <p>РЕЗУЛЬТАТЫ</p>
                  <div><span>Готовый материал</span><b>{format(transformAmount * .683)} кг</b></div>
                  <div><span>Вода</span><b>{format(transformAmount * .125)} кг</b></div>
                  <div><span>Неопределённое</span><b>{format(transformAmount * .192)} кг</b></div>
                </div>
              </div>
              <div className="conservation"><span>Вход <b>{format(transformAmount)} кг</b></span><i /><span>Выход <b>{format(transformAmount)} кг</b></span><strong>Δ 0 кг</strong></div>
            </section>
            <section className="panel">
              <div className="panel-head"><div><h2>Последние акты</h2><p>Движения регистра учёта материи</p></div></div>
              <div className="data-table">
                <div className="table-row table-head"><span>Документ</span><span>Дата</span><span>Схема</span><span>Вход / выход</span><span>Состояние</span></div>
                {transforms.map((item) => <div className="table-row" key={item.id}><b>{item.id}</b><span>{item.date}</span><span>{item.scheme}</span><span>{item.input} / {item.output} кг</span><span className={item.status === "Сбалансировано" ? "good" : "warning"}>{item.status}</span></div>)}
              </div>
            </section>
          </div>
        )}

        {view === "inventory" && (
          <div className="content inventory-layout">
            <section className="inventory-intro">
              <p className="section-label">ТОЧКА ОТСЧЁТА</p>
              <h2>Инвентаризация фиксирует наблюдаемую материю.</h2>
              <p>Это первичный документ SRP: он создаёт начальные остатки для выбранной модели данных и сохраняет источник измерения.</p>
            </section>
            <section className="panel inventory-form">
              <div className="form-grid">
                <label>Номер документа<input value="INV-2026-007" readOnly /></label>
                <label>Дата наблюдения<input type="date" defaultValue="2026-07-28" /></label>
                <label className="wide">Модель данных<select value={model} onChange={(event) => setModel(event.target.value)}><option>Фактическая модель</option><option>Прогнозная модель</option><option>Исследовательская модель</option></select></label>
              </div>
              <div className="inventory-lines">
                <div className="table-row table-head"><span>Вещество</span><span>Количество</span><span>Единица</span></div>
                {matter.map((item) => <div className="table-row" key={item.name}><span><i className={`tiny-dot ${item.tone}`} />{item.name}</span><input defaultValue={item.opening} type="number" /><span>кг</span></div>)}
              </div>
              <div className="form-actions"><button className="secondary-button">Сохранить черновик</button><button className="primary-button">Провести инвентаризацию</button></div>
            </section>
          </div>
        )}
      </section>
    </main>
  );
}
