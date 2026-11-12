import { useCallback, useEffect, useMemo, useState } from "react";
import { request } from "./api";
import { useAppContext } from "./appContext";
import {
  LADDER,
  LAYER_LABEL,
  candidateState,
  filterCandidates,
  type Candidates,
  type PromotionPlan,
} from "./promotion";

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("uk-UA", { dateStyle: "short", timeStyle: "short" }) : "—";
}

/** Promotion of published models to the next layer: DEV → prePROD → PROD. */
export default function PromotePage() {
  const { layer } = useAppContext();
  const [data, setData] = useState<Candidates | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [plan, setPlan] = useState<PromotionPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [planning, setPlanning] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<PromotionPlan | null>(null);

  const load = useCallback(() => {
    request<Candidates>("/promotions")
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((reason) => setError(String(reason?.message || reason)));
  }, []);
  useEffect(load, [load, layer]);

  useEffect(() => {
    setPlan(null);
    setPlanError(null);
    setDone(null);
    if (!selected || !data?.target) return;
    const controller = new AbortController();
    setPlanning(true);
    request<PromotionPlan>(`/promotions/plan?version_id=${encodeURIComponent(selected)}`, { signal: controller.signal }, 120_000)
      .then(setPlan)
      .catch((reason) => !controller.signal.aborted && setPlanError(String(reason?.message || reason)))
      .finally(() => !controller.signal.aborted && setPlanning(false));
    return () => controller.abort();
  }, [selected, data?.target]);

  const items = useMemo(() => filterCandidates(data?.items ?? [], query), [data, query]);
  const target = data?.target ?? null;

  const run = async () => {
    if (!plan || !target) return;
    setBusy(true);
    try {
      const result = await request<PromotionPlan>("/promotions", { method: "POST", body: JSON.stringify({ version_id: plan.version.id, note }) }, 180_000);
      setDone(result);
      setPlan(result);
      setNote("");
      load();
    } catch (reason: any) {
      setPlanError(String(reason?.message || reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="promote-page">
      <header className="promote-head">
        <div>
          <small>ВИПУСК МОДЕЛЕЙ</small>
          <h1>{target ? `${LAYER_LABEL[layer]} → ${LAYER_LABEL[target]}` : `${LAYER_LABEL[layer]}: кінцевий шар`}</h1>
        </div>
        <ol className="promote-ladder" aria-label="Шари">
          {LADDER.map((id) => (
            <li key={id} data-layer={id} className={id === layer ? "current" : id === target ? "next" : ""}>
              {LAYER_LABEL[id]}
            </li>
          ))}
        </ol>
      </header>
      <p className="promote-intro">
        Переноситься опублікована версія моделі з усім, що потрібно для запуску: вузли, зв'язки, сценарії зі збіркою учасників,
        процеси, скрипти й довідники. Прогони не переносяться: кожен шар збирає власні докази. У PROD можна перенести лише версію,
        яка має завершений прогін у prePROD.
      </p>

      {error && <div className="balance-message bad">{error}</div>}

      {data && (
        <div className="promote-body">
          <section className="promote-list">
            <input type="search" placeholder="Пошук: проєкт, версія, сценарій" value={query} onChange={(e) => setQuery(e.target.value)} />
            {!data.items.length && (
              <p className="promote-empty">
                У шарі {LAYER_LABEL[layer]} немає опублікованих версій.{" "}
                {layer === "dev" ? "Опублікуйте версію в розділі «Моделі»." : "Перенесіть їх сюди з попереднього шару."}
              </p>
            )}
            {items.map((item) => {
              const state = candidateState(item, target);
              return (
                <button key={item.id} className={`promote-item ${selected === item.id ? "active" : ""}`} onClick={() => setSelected(item.id)}>
                  <b>{item.project_name}</b>
                  <span>
                    {item.name} · v{item.version}
                  </span>
                  {item.scenarios.length > 0 && <small>Сценарій: {item.scenarios.join(", ")}</small>}
                  <em className={`tone-${state.tone}`}>{state.label}</em>
                  {layer !== "dev" && <small>Завершених прогонів: {item.completed_runs}</small>}
                </button>
              );
            })}
          </section>

          <section className="promote-plan">
            {!target && <p className="promote-empty">PROD — кінцевий шар: моделі сюди потрапляють із prePROD і далі не переносяться.</p>}
            {target && !selected && <p className="promote-empty">Оберіть версію ліворуч, щоб побачити план перенесення.</p>}
            {planning && <p className="promote-empty">Перевірка версії та порівняння з {LAYER_LABEL[target!]}…</p>}
            {planError && <div className="balance-message bad">{planError}</div>}
            {plan && (
              <>
                <h2>
                  {plan.version.project_name}
                  <span>
                    {plan.version.name} · v{plan.version.version}
                  </span>
                </h2>
                {done ? (
                  <div className="promote-result ok">
                    Перенесено в {LAYER_LABEL[plan.target]}: {plan.totals.new} записів.{" "}
                    <a href={`/lab?layer=${plan.target}&project=${encodeURIComponent(plan.version.project_id)}`}>Відкрити модель у {LAYER_LABEL[plan.target]} ↗</a>
                  </div>
                ) : plan.status === "already" ? (
                  <div className="promote-result ok">Версія вже є в {LAYER_LABEL[plan.target]} і не відрізняється: переносити нічого.</div>
                ) : null}

                <ul className="promote-checks">
                  {plan.checks.map((check) => (
                    <li key={check.id} className={check.ok ? "ok" : "bad"}>
                      <i>{check.ok ? "✓" : "✕"}</i>
                      <span>
                        {check.label}
                        {check.detail && <small>{check.detail}</small>}
                      </span>
                    </li>
                  ))}
                </ul>

                <div className="promote-scope">
                  <div>
                    <small>Версії моделей</small>
                    {plan.versions.map((name) => <span key={name}>{name}</span>)}
                  </div>
                  <div>
                    <small>Сценарії</small>
                    {plan.scenarios.length ? plan.scenarios.map((name) => <span key={name}>{name}</span>) : <span>—</span>}
                  </div>
                </div>

                <table className="promote-table">
                  <thead>
                    <tr>
                      <th>Що переноситься</th>
                      <th title="Записів, яких ще немає в цільовому шарі">Нові</th>
                      <th title="Записи вже є і збігаються">Без змін</th>
                      <th title="Сутності світу, які цільовий шар уточнив сам: лишаються як є">Свої в цілі</th>
                      <th title="Записи вже є, але відрізняються: блокують перенесення">Конфлікти</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.tables.map((row) => (
                      <tr key={row.table}>
                        <td>{row.label}</td>
                        <td className={row.new ? "new" : "zero"}>{row.new}</td>
                        <td className="zero">{row.same || ""}</td>
                        <td className="zero">{row.kept || ""}</td>
                        <td className={row.changed ? "bad" : "zero"}>{row.changed || ""}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td>Разом</td>
                      <td>{plan.totals.new}</td>
                      <td>{plan.totals.same}</td>
                      <td>{plan.totals.kept}</td>
                      <td>{plan.totals.changed}</td>
                    </tr>
                  </tfoot>
                </table>

                {plan.conflicts.length > 0 && (
                  <div className="promote-conflicts">
                    <small>Конфлікти: ці записи в {LAYER_LABEL[plan.target]} відрізняються від {LAYER_LABEL[plan.source]}</small>
                    {plan.conflicts.map((c) => (
                      <code key={`${c.table}:${c.id}`}>
                        {c.label} · {c.id} · поля: {c.columns.join(", ")}
                      </code>
                    ))}
                  </div>
                )}

                {plan.status === "ready" && !done && (
                  <div className="promote-action">
                    <textarea placeholder="Коментар до випуску (необов'язково): що перевіряємо, чому переносимо" value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
                    <button data-layer={plan.target} onClick={run} disabled={busy}>
                      {busy ? "Перенесення…" : `Перенести в ${LAYER_LABEL[plan.target]}`}
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}

      {data && data.history.length > 0 && (
        <section className="promote-history">
          <h3>Журнал випусків у шарі {LAYER_LABEL[layer]}</h3>
          <table className="promote-table">
            <thead>
              <tr>
                <th>Коли</th>
                <th>Напрям</th>
                <th>Версія</th>
                <th>Записів</th>
                <th>Коментар</th>
              </tr>
            </thead>
            <tbody>
              {data.history.map((item) => (
                <tr key={`${item.id}`}>
                  <td>{when(item.created_at)}</td>
                  <td>
                    {LAYER_LABEL[item.source]} → {LAYER_LABEL[item.target]}
                  </td>
                  <td>{item.summary.versions?.[0] ?? item.version_id}</td>
                  <td>{item.summary.totals?.new ?? "—"}</td>
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
