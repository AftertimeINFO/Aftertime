import { useEffect, useState } from "react";
import { COUNTRY_LABEL, fmtDate, fmtDateTime } from "./format";
import { runApi, type Run, type Scenario, type ScenarioListItem } from "./run";
import ScenarioWizard from "./ScenarioWizard";

type Props = {
  mode: "historical" | "whatif";
  canRun: boolean;
  activeRun: Run | null;
  onRun: (run: Run | null, scenario: Scenario | null) => void;
  onSeek: (at: string) => void;
  onFocusAssets: (ids: number[]) => void;
  picking: PickApi;
};

export type PickApi = {
  start: (onPick: (id: number) => void) => void;
  stop: () => void;
};

const STATUS: Record<string, string> = { queued: "у черзі", running: "рахується", completed: "готово", failed: "помилка" };

/** Left panel of Replay (historical) and Scenarios (what-if): pick, read, run. */
export default function ScenarioPanel({ mode, canRun, activeRun, onRun, onSeek, onFocusAssets, picking }: Props) {
  const [items, setItems] = useState<ScenarioListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [editing, setEditing] = useState<Scenario | "new" | null>(null);
  const [members, setMembers] = useState(30);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    runApi
      .scenarios()
      .then((r) => setItems(r.items.filter((s) => s.mode === mode)))
      .catch((reason) => setError(String(reason?.message || reason)));
  }, [mode, version]);

  useEffect(() => {
    if (!selected) {
      setScenario(null);
      return;
    }
    let alive = true;
    runApi.scenario(selected).then((s) => {
      if (!alive) return;
      setScenario(s);
      setMembers(Number(s.uncertainty?.members ?? 30));
    });
    runApi.runs(selected).then((r) => {
      if (!alive) return;
      setRuns(r.items);
      // Open the latest finished run of the scenario right away.
      const last = r.items.find((x) => x.kind !== "criticality" && x.status === "completed") ?? r.items[0];
      if (last && (!activeRun || activeRun.scenario_id !== selected)) runApi.run(last.id).then((full) => alive && onRun(full, null));
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, version]);

  useEffect(() => {
    if (scenario && activeRun?.scenario_id === scenario.id) onRun(activeRun, scenario);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario]);

  const start = (kind: "single" | "ensemble" | "criticality") => {
    if (!scenario) return;
    setBusy(true);
    runApi
      .startRun(scenario.id, { kind, members: kind === "ensemble" ? members : 1 })
      .then((run) => {
        onRun(run, scenario);
        setRuns((current) => [run, ...current]);
      })
      .catch((reason) => setError(String(reason?.message || reason)))
      .finally(() => setBusy(false));
  };

  if (editing) {
    return (
      <ScenarioWizard
        initial={editing === "new" ? null : editing}
        picking={picking}
        onCancel={() => setEditing(null)}
        onSaved={(saved, runKind) => {
          setEditing(null);
          setVersion((v) => v + 1);
          setSelected(saved.id);
          if (runKind) {
            runApi.startRun(saved.id, { kind: runKind, members: Number(saved.uncertainty?.members ?? 30) }).then((run) => onRun(run, saved));
          }
        }}
      />
    );
  }

  if (scenario && selected) {
    const historical = scenario.mode === "historical";
    return (
      <div className="en-panel">
        <button className="en-back" onClick={() => { setSelected(null); onRun(null, null); }}>← Усі {historical ? "інциденти" : "сценарії"}</button>
        <header className="en-scenario-head">
          <span className={`en-badge ${historical ? "hist" : "whatif"}`}>{historical ? "Історичний" : "Що, якщо"}</span>
          <h3>{scenario.name}</h3>
          <small>{fmtDate(scenario.start_at)} — {fmtDate(scenario.end_at)} · {scenario.countries.map((c) => COUNTRY_LABEL[c] ?? c).join(", ")}</small>
        </header>
        <p className="en-description">{scenario.description}</p>

        <div className="en-run-actions">
          <button className="en-btn primary" disabled={!canRun || busy} onClick={() => start("single")} title="Один прогін з фіксованими параметрами">
            {historical ? "▶ Відтворити" : "▶ Розрахувати"}
          </button>
          <div className="en-split">
            <button className="en-btn" disabled={!canRun || busy} onClick={() => start("ensemble")} title="Багато прогонів з різними випадковими параметрами: діапазон результатів P10–P90">
              Оцінити розкид
            </button>
            <label className="en-inline" title="Кількість прогонів ансамблю">
              <input type="number" min={5} max={500} value={members} onChange={(e) => setMembers(Math.max(5, Math.min(500, Number(e.target.value) || 30)))} aria-label="Кількість прогонів" />
              прогонів
            </label>
          </div>
          {!historical && (
            <button className="en-btn ghost" disabled={!canRun || busy} onClick={() => start("criticality")} title="Відключає по черзі кожну підстанцію ≥ 220 кВ і лінію ≥ 330 кВ та ранжує за наслідками">
              Знайти вразливі місця (N-1)
            </button>
          )}
          {!canRun && <p className="en-hint">У цьому шарі розрахунки недоступні.</p>}
        </div>

        <section className="en-section">
          <h4>Події ({scenario.events.length})</h4>
          <ol className="en-journal">
            {scenario.events.map((e) => {
              const targets = (e.targets ?? []).map((t) => scenario.assets?.[t]).filter(Boolean);
              return (
                <li key={e.id}>
                  <button className="en-journal-time" onClick={() => onSeek(e.at)} title="Перейти до цього моменту">{fmtDateTime(e.at)}</button>
                  <div>
                    <b>{e.label || e.type}</b>
                    {targets.length > 0 && (
                      <button className="en-link-btn" onClick={() => onFocusAssets((e.targets ?? []).slice(0, 50))}>
                        {targets.slice(0, 3).map((t) => t!.name ?? `#${t!.id}`).join(", ")}{targets.length > 3 ? ` +${targets.length - 3}` : ""}
                      </button>
                    )}
                    {e.type === "rule_strike" && <span className="en-tag">умовні цілі</span>}
                    {(e.match?.length ?? 0) > 0 && !(e.targets?.length) && <span className="en-tag warn" title="Об'єкт за назвою ще не знайдено в імпортованих даних">не знайдено в OSM</span>}
                    {e.source_url && <a href={e.source_url} target="_blank" rel="noreferrer noopener">джерело ↗</a>}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        {runs.length > 0 && (
          <section className="en-section">
            <h4>Прогони</h4>
            <ul className="en-runs">
              {runs.slice(0, 8).map((r) => (
                <li key={r.id}>
                  <button className={activeRun?.id === r.id ? "active" : ""} onClick={() => runApi.run(r.id).then((full) => onRun(full, scenario))}>
                    <span>{r.kind === "ensemble" ? `Ансамбль · ${r.members}` : r.kind === "criticality" ? "N-1" : "Одиночний"}</span>
                    <small>{fmtDateTime(r.created_at)}</small>
                    <em className={`status-${r.status}`}>{STATUS[r.status] ?? r.status}</em>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <footer className="en-panel-foot">
          {!historical && canRun && (
            <>
              <button className="en-link-btn" onClick={() => setEditing(scenario)}>Редагувати</button>
              <button className="en-link-btn" onClick={() => setEditing({ ...scenario, id: "", name: `${scenario.name} (копія)` })}>Дублювати</button>
              {scenario.author !== "Aftertime" && (
                <button className="en-link-btn danger" onClick={() => {
                  if (window.confirm(`Видалити сценарій «${scenario.name}» з усіма прогонами?`)) runApi.deleteScenario(scenario.id).then(() => { setSelected(null); onRun(null, null); setVersion((v) => v + 1); });
                }}>Видалити</button>
              )}
            </>
          )}
          {historical && scenario.sources.length > 0 && <span className="en-muted">Джерел: {scenario.sources.length}</span>}
        </footer>
        {error && <p className="en-error" role="alert">{error}</p>}
      </div>
    );
  }

  return (
    <div className="en-panel">
      <p className="en-hint">
        {mode === "historical"
          ? "Реальні інциденти, відтворені на реальній мережі. Кожна подія має джерело; модель порівнюється з фактом."
          : "Ймовірні інциденти майбутнього: оберіть готовий сценарій або складіть свій."}
      </p>
      {mode === "whatif" && canRun && (
        <button className="en-btn primary wide" onClick={() => setEditing("new")}>+ Новий сценарій</button>
      )}
      {error && <p className="en-error" role="alert">{error}</p>}
      {!items && !error && <div className="en-skeleton" />}
      {items && !items.length && <p className="en-hint">Поки що немає {mode === "historical" ? "інцидентів" : "сценаріїв"}.</p>}
      <ul className="en-cards">
        {items?.map((s) => (
          <li key={s.id}>
            <button onClick={() => setSelected(s.id)}>
              <b>{s.name}</b>
              <small>{fmtDate(s.start_at)} · {s.countries.map((c) => COUNTRY_LABEL[c] ?? c).join(", ")} · подій: {s.events}</small>
              {s.last_run_status && <em className={`status-${s.last_run_status}`}>{STATUS[s.last_run_status] ?? s.last_run_status}</em>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
