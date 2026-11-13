import { COUNTRY_LABEL, KIND_LABEL, assetTitle, fmtCount, fmtDateTime, fmtEnergy, fmtKv, fmtMw, fmtNumber } from "./format";
import type { Frame, Run, Scenario } from "./run";

/** KPI strip over the map: the state of the system at the shown moment. */
export function KpiStrip({ frame, previous }: { frame: Frame; previous?: Frame }) {
  const m = frame.metrics;
  const share = m.unserved_share;
  const tone = share >= 0.2 ? "bad" : share > 0.01 ? "warn" : "ok";
  const delta = previous ? m.unserved_mw - previous.metrics.unserved_mw : 0;
  return (
    <div className="en-kpis" role="status" aria-live="polite">
      <Kpi
        tone={tone}
        label="Дефіцит потужності"
        value={fmtMw(m.unserved_mw)}
        note={`${fmtNumber(share * 100, 1)}% попиту${delta ? ` · ${delta > 0 ? "▲" : "▼"} ${fmtMw(Math.abs(delta))}` : ""}`}
        hint="Скільки потужності не отримують споживачі: вимкнено захистом, острови без генерації, або графіки відключень через брак генерації."
      />
      <Kpi label="Недовідпущено енергії" value={fmtEnergy(m.ens_mwh)} note="з початку сценарію" hint="Накопичена енергія, яку споживачі не отримали (МВт·год)." />
      <Kpi label="Генерація / попит" value={`${fmtMw(m.generation_mw)}`} note={`попит ${fmtMw(m.demand_mw)}`} hint="Фактично вироблено проти потреби в цю годину (профіль доби й сезону)." />
      <Kpi
        tone={m.frequency_hz < 49.5 ? "bad" : m.frequency_hz < 49.9 ? "warn" : "ok"}
        label="Частота (провал)"
        value={`${fmtNumber(m.frequency_hz, 2)} Гц`}
        note={m.frequency_hz < 50 ? "АЧР відключає споживачів" : "норма"}
        hint="Оцінка провалу частоти в момент раптового дефіциту. Тривалий дефіцит покривають графіками, тож частота повертається до 50 Гц."
      />
      <Kpi
        tone={m.tripped + m.out_branches > 0 ? "warn" : "ok"}
        label="Відключено елементів"
        value={fmtCount(m.out_branches + m.tripped + m.out_buses)}
        note={`${m.tripped} захистом · ${m.islands} ${m.islands === 1 ? "острів" : "острови"}`}
        hint="Лінії й підстанції поза роботою: уражені подіями та відключені захистом від перевантаження (каскад)."
      />
    </div>
  );
}

function Kpi({ label, value, note, tone, hint }: { label: string; value: string; note?: string; tone?: "ok" | "warn" | "bad"; hint: string }) {
  return (
    <div className={`en-kpi ${tone ?? ""}`} title={hint}>
      <small>{label}</small>
      <b>{value}</b>
      {note && <span>{note}</span>}
    </div>
  );
}

type SummaryProps = {
  run: Run | null;
  scenario: Scenario | null;
  frame: Frame | null;
  onSelectAsset: (id: number) => void;
  onSeek: (at: string) => void;
};

/** Right panel during a run: what happened now, how the run compares with the facts, and what the model assumed. */
export function RunSummaryPanel({ run, scenario, frame, onSelectAsset, onSeek }: SummaryProps) {
  if (!run) {
    return (
      <div className="en-inspector">
        <p className="en-hint">Оберіть сценарій ліворуч і запустіть розрахунок. Результат з'явиться тут і на мапі.</p>
      </div>
    );
  }
  if (run.status !== "completed") {
    return (
      <div className="en-inspector">
        <h3>{run.status === "failed" ? "Розрахунок не вдався" : "Розрахунок…"}</h3>
        {run.status === "failed" ? (
          <p className="en-error" role="alert">{run.error}</p>
        ) : (
          <>
            <div className="en-progress" role="progressbar" aria-valuenow={Math.round(run.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
              <i style={{ width: `${Math.max(4, run.progress * 100)}%` }} />
            </div>
            <p className="en-hint">{run.kind === "ensemble" ? `Ансамбль із ${run.members} прогонів` : run.kind === "criticality" ? "Перевірка N-1: відключаємо по одному об'єкту" : "Одиночний прогін"} · {Math.round(run.progress * 100)}%</p>
          </>
        )}
      </div>
    );
  }
  const s = run.summary;
  const assets = scenario?.assets ?? {};
  const events = frame?.events ?? [];
  return (
    <div className="en-inspector">
      {s.criticality && (
        <section className="en-section">
          <h4>Найвразливіші об'єкти (N-1)</h4>
          <p className="en-hint">Скільки потужності недоотримають споживачі, якщо вийде з ладу лише цей об'єкт (з урахуванням каскаду). Для планування захисту та резервування.</p>
          <ol className="en-rank">
            {s.criticality.slice(0, 15).map((c) => (
              <li key={c.asset_id}>
                <button onClick={() => onSelectAsset(c.asset_id)}>
                  <span>{assetTitle({ name: c.name, kind: c.kind ?? "substation", max_voltage_kv: c.max_voltage_kv })}</span>
                  <small>{[KIND_LABEL[c.kind ?? ""], fmtKv(c.max_voltage_kv ?? null), COUNTRY_LABEL[c.country ?? ""]].filter(Boolean).join(" · ")}</small>
                  <b>{fmtMw(c.unserved_mw)}</b>
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}
      {frame && events.length > 0 && (
        <section className="en-section">
          <h4>Зараз відбувається</h4>
          <ul className="en-events">
            {events.map((e, i) => (
              <li key={i} className={`origin-${e.origin}`}>
                <b>{e.label}</b>
                {e.targets.length > 0 && (
                  <span className="en-targets">
                    {e.targets.slice(0, 6).map((t) => (
                      <button key={t} className="en-link-btn" onClick={() => onSelectAsset(t)}>{assets[t]?.name ?? `#${t}`}</button>
                    ))}
                    {e.targets.length > 6 && <span className="en-muted">+{e.targets.length - 6}</span>}
                  </span>
                )}
                {e.source_url && <a href={e.source_url} target="_blank" rel="noreferrer noopener">джерело ↗</a>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {!s.criticality && (
        <section className="en-section">
          <h4>Підсумок прогону</h4>
          <dl className="en-facts">
            <dt>Пік дефіциту</dt>
            <dd>
              {fmtMw(s.peak?.unserved_mw)}
              {s.peak && <button className="en-link-btn" onClick={() => onSeek(s.peak!.at)}>{fmtDateTime(s.peak.at)}</button>}
            </dd>
            <dt>Недовідпущено</dt>
            <dd>{fmtEnergy(s.ens_mwh)}</dd>
            {s.ensemble && (
              <>
                <dt>Ансамбль</dt>
                <dd>{s.ensemble.members} прогонів</dd>
                <dt>Пік, P10–P90</dt>
                <dd>{fmtMw(s.ensemble.peak_unserved_mw.p10)} – {fmtMw(s.ensemble.peak_unserved_mw.p90)}</dd>
                <dt>Енергія, P10–P90</dt>
                <dd>{fmtEnergy(s.ensemble.ens_mwh.p10)} – {fmtEnergy(s.ensemble.ens_mwh.p90)}</dd>
              </>
            )}
            <dt>Розрахунок</dt>
            <dd>{fmtNumber(s.duration_s ?? 0, 1)} с</dd>
          </dl>
        </section>
      )}
      {s.checks && s.checks.length > 0 && (
        <section className="en-section">
          <h4>Модель проти факту</h4>
          <table className="en-table en-checks">
            <thead><tr><th>Показник</th><th>Факт</th><th>Модель</th><th /></tr></thead>
            <tbody>
              {s.checks.map((c, i) => (
                <tr key={i} className={c.ok ? "ok" : "bad"}>
                  <td>
                    <button className="en-link-btn" onClick={() => onSeek(c.at_model)}>{c.label}</button>
                    {c.role === "calibration" && <span className="en-tag" title="За цим фактом підібрано параметр моделі, тож це не незалежна перевірка">калібрування</span>}
                    {c.source_url && <a href={c.source_url} target="_blank" rel="noreferrer noopener" aria-label="Джерело факту"> ↗</a>}
                  </td>
                  <td>{fmtCheck(c.metric, c.value, c.op)}</td>
                  <td>{c.model == null ? "—" : fmtCheck(c.metric, c.model)}</td>
                  <td aria-label={c.ok ? "збігається" : "розходиться"}>{c.ok ? "✓" : "✗"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="en-hint">Розбіжність — не помилка інтерфейсу, а сигнал калібрування: які дані чи припущення моделі слід уточнити (правками об'єктів). Позначка «калібрування» — за цим фактом підібрано параметр, тож незалежною перевіркою є решта рядків.</p>
        </section>
      )}
      {s.base && (
        <section className="en-section">
          <h4>Припущення моделі</h4>
          <ul className="en-assumptions">
            {Object.entries(s.base.balancing_mw).map(([c, mw]) => (
              <li key={c}>{COUNTRY_LABEL[c] ?? c}: {fmtMw(mw)} генерації та імпорту немає в OSM — додано як немодельоване живлення, розподілене по споживачах.</li>
            ))}
            {s.base.isolated_load_mw > 0 && <li>{fmtMw(s.base.isolated_load_mw)} навантаження в частинах мережі, які OSM не з'єднує з генерацією, вважаються живленими локально.</li>}
            {s.base.ratings_raised > 0 && <li>Для {fmtNumber(s.base.ratings_raised)} гілок типову пропускну здатність підвищено, щоб нормальний режим був без перевантажень.</li>}
            <li>Параметри ліній і трансформаторів — типові для класу напруги; попит — профіль доби й сезону за країною.</li>
          </ul>
        </section>
      )}
    </div>
  );
}

function fmtCheck(metric: string, value: number, op?: string): string {
  const prefix = op === "min" ? "≥ " : op === "max" ? "≤ " : op ? "≈ " : "";
  if (metric.endsWith("_share")) return `${prefix}${fmtNumber(value * 100, 0)}%`;
  if (metric.endsWith("_mwh")) return prefix + fmtEnergy(value);
  if (metric.endsWith("_mw")) return prefix + fmtMw(value);
  return prefix + fmtNumber(value, 1);
}
