import { useEffect, useRef, useState } from "react";
import { gridApi } from "./energyApi";
import { COUNTRY_LABEL, FUEL_LABEL, KIND_LABEL, assetTitle, fmtDateTime } from "./format";
import { runApi, type Scenario, type ScenarioEvent } from "./run";
import type { PickApi } from "./ScenarioPanel";

/**
 * Scenario wizard. Four steps with visible progress, any step reachable again:
 *   1. Рамки — when (date and hour define demand and the network snapshot), how long, where;
 *   2. Події — what happens, to which assets, at what time;
 *   3. Невизначеність — probability of a hit, repair times, number of runs;
 *   4. Запуск — a plain-language summary, save and run.
 * Defaults are sensible so that a first scenario needs only a threat and targets.
 */

type Threat = "strike_substation" | "strike_plant" | "line_failure" | "demand" | "fuel" | "separate";
const THREATS: { id: Threat; title: string; text: string; icon: string }[] = [
  { id: "strike_substation", title: "Ураження підстанцій", text: "Удар, диверсія, пожежа, кібератака на керування", icon: "⚡" },
  { id: "strike_plant", title: "Втрата генерації", text: "Ураження або аварійна зупинка електростанцій", icon: "🏭" },
  { id: "line_failure", title: "Відмова ЛЕП", text: "Ожеледь, шторм, падіння опор", icon: "〰" },
  { id: "demand", title: "Зміна попиту", text: "Морози, спека, масове підключення обігрівачів", icon: "🌡" },
  { id: "fuel", title: "Обмеження ресурсу", text: "Дефіцит газу, вугілля, маловоддя", icon: "⛽" },
  { id: "separate", title: "Відокремлення систем", text: "Аварійне відокремлення від сусідніх енергосистем", icon: "⫽" },
];
const COUNTRIES = ["UA", "MD", "PL", "SK", "HU", "RO"];

type Draft = {
  id: string;
  threat: Threat;
  offsetHours: number;
  targets: { id: number; label: string }[];
  rule: { enabled: boolean; minKv: number; count: number };
  probability: number;
  repair: [number, number, number];
  noRepair: boolean;
  capacityShare: number;
  factor: number;
  fuel: string;
  pair: string[];
  label: string;
};

function newDraft(threat: Threat): Draft {
  return {
    id: `d${Math.random().toString(36).slice(2, 8)}`,
    threat,
    offsetHours: 6,
    targets: [],
    rule: { enabled: false, minKv: 330, count: 3 },
    probability: 1,
    repair: threat === "line_failure" ? [6, 24, 72] : [24, 72, 336],
    noRepair: false,
    capacityShare: 1,
    factor: threat === "demand" ? 1.1 : 0.6,
    fuel: "gas",
    pair: ["UA", "PL"],
    label: "",
  };
}

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Turn a scenario's events back into editable drafts (scenarios made by this wizard). */
function draftsFrom(scenario: Scenario): Draft[] {
  const start = Date.parse(scenario.start_at);
  return scenario.events
    .filter((e) => e.payload?.wizard)
    .map((e) => ({ ...(e.payload!.wizard as Draft), offsetHours: (Date.parse(e.at) - start) / 3_600_000 }));
}

export function eventsFrom(drafts: Draft[], startIso: string): ScenarioEvent[] {
  const start = Date.parse(startIso);
  return drafts.map((d) => {
    const at = new Date(start + d.offsetHours * 3_600_000).toISOString();
    const repair = d.noRepair ? undefined : d.repair;
    const common = { at, label: d.label || defaultLabel(d), payload: { wizard: d } as Record<string, unknown> };
    switch (d.threat) {
      case "strike_substation":
      case "strike_plant":
      case "line_failure": {
        const kind = d.threat === "strike_plant" ? "plant" : d.threat === "line_failure" ? "line" : "substation";
        const payload = { ...common.payload, probability: d.probability, repair_hours: repair, capacity_share: d.threat === "strike_plant" ? d.capacityShare : undefined };
        if (d.rule.enabled) {
          return { ...common, type: "rule_strike", payload: { ...payload, selector: { kind, min_kv: d.rule.minKv, count: d.rule.count, countries: ["UA"] } } };
        }
        return { ...common, type: d.threat === "line_failure" ? "outage" : "strike", targets: d.targets.map((t) => t.id), payload };
      }
      case "demand":
        return { ...common, type: "demand", payload: { ...common.payload, factor: d.factor, countries: ["UA", "MD"] } };
      case "fuel":
        return { ...common, type: "fuel", payload: { ...common.payload, fuel: d.fuel, factor: d.factor } };
      case "separate":
        return { ...common, type: "separate", payload: { ...common.payload, countries: d.pair } };
    }
  });
}

function defaultLabel(d: Draft): string {
  const t = THREATS.find((x) => x.id === d.threat)!.title;
  if (d.threat === "demand") return `${t}: ${d.factor >= 1 ? "+" : ""}${Math.round((d.factor - 1) * 100)}%`;
  if (d.threat === "fuel") return `${t}: ${FUEL_LABEL[d.fuel] ?? d.fuel}, доступно ${Math.round(d.factor * 100)}%`;
  if (d.threat === "separate") return `${t}: ${d.pair.map((c) => COUNTRY_LABEL[c] ?? c).join(" ↔ ")}`;
  if (d.rule.enabled) return `${t}: ${d.rule.count} довільних ≥ ${d.rule.minKv} кВ (умовні цілі)`;
  return `${t}: ${d.targets.length ? d.targets.slice(0, 2).map((x) => x.label).join(", ") + (d.targets.length > 2 ? ` +${d.targets.length - 2}` : "") : "без цілей"}`;
}

type Props = {
  initial: Scenario | null;
  picking: PickApi;
  onCancel: () => void;
  onSaved: (scenario: Scenario, run: "single" | "ensemble" | null) => void;
};

const STEPS = ["Рамки", "Події", "Невизначеність", "Запуск"];

export default function ScenarioWizard({ initial, picking, onCancel, onSaved }: Props) {
  const now = new Date();
  now.setMinutes(0, 0, 0);
  const [step, setStep] = useState(0);
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [start, setStart] = useState(initial ? toLocalInput(initial.start_at) : toLocalInput(new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1, 4)).toISOString()));
  const [hours, setHours] = useState(initial ? Math.round((Date.parse(initial.end_at) - Date.parse(initial.start_at)) / 3_600_000) : 72);
  const [countries, setCountries] = useState<string[]>(initial?.countries ?? ["UA", "MD"]);
  const [drafts, setDrafts] = useState<Draft[]>(initial ? draftsFrom(initial) : []);
  const [open, setOpen] = useState<string | null>(null);
  const [members, setMembers] = useState(Number(initial?.uncertainty?.members ?? 30));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => () => picking.stop(), [picking]);

  const update = (id: string, patch: Partial<Draft>) => setDrafts((list) => list.map((d) => (d.id === id ? { ...d, ...patch } : d)));
  const startIso = new Date(start).toISOString();
  const issues = [
    !name.trim() && "Дайте сценарію назву",
    !drafts.length && "Додайте хоча б одну подію",
    ...drafts.map((d, i) =>
      ["strike_substation", "strike_plant", "line_failure"].includes(d.threat) && !d.rule.enabled && !d.targets.length ? `Подія ${i + 1}: оберіть цілі на мапі або задайте правило` : null,
    ),
    ...drafts.map((d, i) => (d.offsetHours > hours ? `Подія ${i + 1} пізніше за кінець сценарію` : null)),
  ].filter(Boolean) as string[];

  const save = (run: "single" | "ensemble" | null) => {
    setSaving(true);
    setError(null);
    const end = new Date(Date.parse(startIso) + hours * 3_600_000).toISOString();
    runApi
      .saveScenario(
        {
          name: name.trim(),
          mode: "whatif",
          description,
          countries,
          start_at: startIso,
          end_at: end,
          step_hours: hours > 24 * 14 ? 6 : 1,
          events: eventsFrom(drafts, startIso),
          uncertainty: { members },
        },
        initial?.id || undefined,
      )
      .then((saved) => onSaved(saved, run))
      .catch((reason) => setError(String(reason?.message || reason)))
      .finally(() => setSaving(false));
  };

  return (
    <div className="en-panel en-wizard">
      <div className="en-wizard-head">
        <h3>{initial?.id ? "Редагування сценарію" : "Новий сценарій"}</h3>
        <button className="en-icon-btn" onClick={onCancel} aria-label="Скасувати">×</button>
      </div>
      <ol className="en-steps" aria-label="Кроки">
        {STEPS.map((s, i) => (
          <li key={s} className={i === step ? "active" : i < step ? "done" : ""}>
            <button onClick={() => setStep(i)} aria-current={i === step ? "step" : undefined}>
              <i>{i < step ? "✓" : i + 1}</i>{s}
            </button>
          </li>
        ))}
      </ol>

      {step === 0 && (
        <div className="en-form">
          <label>Назва <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Наприклад: ожеледь на заході, лютий" autoFocus /></label>
          <label>Опис (необов'язково) <textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
          <div className="en-form-row">
            <label>Початок <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} /></label>
            <label>Тривалість, год <input type="number" min={1} max={24 * 365} value={hours} onChange={(e) => setHours(Math.max(1, Number(e.target.value) || 1))} /></label>
          </div>
          <p className="en-hint">Дата й година визначають попит (доба, сезон) і стан мережі на той момент.</p>
          <fieldset className="en-fieldset">
            <legend>Енергосистеми в моделі</legend>
            <div className="en-chips">
              {COUNTRIES.map((c) => {
                const on = countries.includes(c);
                return (
                  <button key={c} className={`en-chip ${on ? "on" : ""}`} aria-pressed={on} disabled={c === "UA"} onClick={() => setCountries(on ? countries.filter((x) => x !== c) : [...countries, c])}>
                    {COUNTRY_LABEL[c]}
                  </button>
                );
              })}
            </div>
            <p className="en-hint">Сусідні системи дають перетоки допомоги, але збільшують час розрахунку.</p>
          </fieldset>
        </div>
      )}

      {step === 1 && (
        <div className="en-form">
          {drafts.map((d, i) => (
            <EventEditor
              key={d.id}
              index={i}
              draft={d}
              open={open === d.id}
              onToggle={() => setOpen(open === d.id ? null : d.id)}
              onChange={(patch) => update(d.id, patch)}
              onRemove={() => setDrafts(drafts.filter((x) => x.id !== d.id))}
              startIso={startIso}
              picking={picking}
            />
          ))}
          <p className="en-subhead">{drafts.length ? "Додати ще подію" : "Що відбувається?"}</p>
          <div className="en-threats">
            {THREATS.map((t) => (
              <button key={t.id} onClick={() => { const d = newDraft(t.id); setDrafts([...drafts, d]); setOpen(d.id); }}>
                <i aria-hidden="true">{t.icon}</i>
                <b>{t.title}</b>
                <small>{t.text}</small>
              </button>
            ))}
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="en-form">
          <p className="en-hint">Майбутнє невизначене: ансамбль повторює сценарій багато разів із різними випадковими значеннями (влучання, час ремонту) і показує діапазон наслідків P10–P90.</p>
          <label>Кількість прогонів ансамблю
            <input type="range" min={10} max={200} step={10} value={members} onChange={(e) => setMembers(Number(e.target.value))} />
            <span className="en-range-value">{members}</span>
          </label>
          {drafts.filter((d) => ["strike_substation", "strike_plant", "line_failure"].includes(d.threat)).map((d) => (
            <fieldset key={d.id} className="en-fieldset">
              <legend>{d.label || defaultLabel(d)}</legend>
              <label>Ймовірність ураження кожної цілі
                <input type="range" min={0.1} max={1} step={0.05} value={d.probability} onChange={(e) => update(d.id, { probability: Number(e.target.value) })} />
                <span className="en-range-value">{Math.round(d.probability * 100)}%</span>
              </label>
              <label className="en-check"><input type="checkbox" checked={d.noRepair} onChange={(e) => update(d.id, { noRepair: e.target.checked })} /> Без відновлення в межах сценарію</label>
              {!d.noRepair && (
                <div className="en-form-row three">
                  <label>Ремонт, мін. год <input type="number" min={0} value={d.repair[0]} onChange={(e) => update(d.id, { repair: [Number(e.target.value), d.repair[1], d.repair[2]] })} /></label>
                  <label>найімовірніше <input type="number" min={0} value={d.repair[1]} onChange={(e) => update(d.id, { repair: [d.repair[0], Number(e.target.value), d.repair[2]] })} /></label>
                  <label>макс. <input type="number" min={0} value={d.repair[2]} onChange={(e) => update(d.id, { repair: [d.repair[0], d.repair[1], Number(e.target.value)] })} /></label>
                </div>
              )}
            </fieldset>
          ))}
        </div>
      )}

      {step === 3 && (
        <div className="en-form">
          <div className="en-review">
            <p><b>{name || "Без назви"}</b></p>
            <p>З {fmtDateTime(startIso)} протягом {hours} год · {countries.map((c) => COUNTRY_LABEL[c]).join(", ")}</p>
            <ol>
              {eventsFrom(drafts, startIso).map((e, i) => <li key={i}><span>{fmtDateTime(e.at)}</span> {e.label}</li>)}
            </ol>
            <p>Ансамбль: {members} прогонів</p>
          </div>
          {issues.length > 0 && (
            <ul className="en-issues" role="alert">
              {issues.map((issue) => <li key={issue}>{issue}</li>)}
            </ul>
          )}
          {error && <p className="en-error" role="alert">{error}</p>}
        </div>
      )}

      <div className="en-wizard-nav">
        {step > 0 ? <button className="en-btn ghost" onClick={() => setStep(step - 1)}>← Назад</button> : <button className="en-btn ghost" onClick={onCancel}>Скасувати</button>}
        {step < STEPS.length - 1 ? (
          <button className="en-btn primary" onClick={() => setStep(step + 1)} disabled={step === 0 && !name.trim()}>Далі →</button>
        ) : (
          <div className="en-split">
            <button className="en-btn" disabled={!!issues.length || saving} onClick={() => save(null)}>Зберегти</button>
            <button className="en-btn primary" disabled={!!issues.length || saving} onClick={() => save("ensemble")}>{saving ? "Збереження…" : "Зберегти й розрахувати"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

function EventEditor({ index, draft, open, onToggle, onChange, onRemove, startIso, picking }: {
  index: number; draft: Draft; open: boolean; onToggle: () => void; onChange: (patch: Partial<Draft>) => void; onRemove: () => void; startIso: string; picking: PickApi;
}) {
  const threat = THREATS.find((t) => t.id === draft.threat)!;
  const targetsKind = draft.threat === "strike_plant" ? "plant" : draft.threat === "line_failure" ? "line" : draft.threat === "strike_substation" ? "substation" : null;
  const [pickingThis, setPickingThis] = useState(false);
  // The map calls back long after this render: read the latest draft through a ref.
  const latest = useRef({ draft, onChange });
  latest.current = { draft, onChange };
  const togglePick = () => {
    if (pickingThis) {
      picking.stop();
      setPickingThis(false);
      return;
    }
    setPickingThis(true);
    picking.start((id) => {
      gridApi.asset(id).then((card) => {
        if (targetsKind === "line" ? !["line", "cable"].includes(card.kind) : card.kind !== targetsKind && !(targetsKind === "substation" && card.kind === "converter")) return;
        const { draft: current, onChange: change } = latest.current;
        const exists = current.targets.some((t) => t.id === id);
        change({ targets: exists ? current.targets.filter((t) => t.id !== id) : [...current.targets, { id, label: assetTitle(card) }] });
      });
    });
  };
  useEffect(() => () => { if (pickingThis) picking.stop(); }, [pickingThis, picking]);

  return (
    <div className={`en-event-editor ${open ? "open" : ""}`}>
      <button className="en-event-summary" onClick={onToggle} aria-expanded={open}>
        <i aria-hidden="true">{threat.icon}</i>
        <span>
          <b>{index + 1}. {draft.label || defaultLabel(draft)}</b>
          <small>+{draft.offsetHours} год · {fmtDateTime(new Date(Date.parse(startIso) + draft.offsetHours * 3_600_000).toISOString())}</small>
        </span>
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="en-event-body">
          <label>Коли: через, год від початку <input type="number" min={0} step={0.5} value={draft.offsetHours} onChange={(e) => onChange({ offsetHours: Math.max(0, Number(e.target.value) || 0) })} /></label>
          {targetsKind && (
            <>
              <div className="en-segmented small" role="radiogroup" aria-label="Спосіб вибору цілей">
                <button role="radio" aria-checked={!draft.rule.enabled} className={!draft.rule.enabled ? "active" : ""} onClick={() => onChange({ rule: { ...draft.rule, enabled: false } })}>Конкретні об'єкти</button>
                <button role="radio" aria-checked={draft.rule.enabled} className={draft.rule.enabled ? "active" : ""} onClick={() => onChange({ rule: { ...draft.rule, enabled: true } })}>За правилом</button>
              </div>
              {!draft.rule.enabled ? (
                <div>
                  <button className={`en-btn ${pickingThis ? "primary" : ""} wide`} onClick={togglePick}>
                    {pickingThis ? "✓ Готово — завершити вибір" : `◎ Обрати на мапі (${KIND_LABEL[targetsKind === "line" ? "line" : targetsKind]})`}
                  </button>
                  {pickingThis && <p className="en-hint">Клацайте об'єкти на мапі: перше клацання додає, повторне — прибирає.</p>}
                  <ul className="en-target-list">
                    {draft.targets.map((t) => (
                      <li key={t.id}>{t.label}<button className="en-icon-btn" aria-label={`Прибрати ${t.label}`} onClick={() => onChange({ targets: draft.targets.filter((x) => x.id !== t.id) })}>×</button></li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="en-form-row">
                  <label>Скільки <input type="number" min={1} max={100} value={draft.rule.count} onChange={(e) => onChange({ rule: { ...draft.rule, count: Math.max(1, Number(e.target.value) || 1) } })} /></label>
                  {targetsKind !== "plant" && (
                    <label>Напруга від, кВ
                      <select value={draft.rule.minKv} onChange={(e) => onChange({ rule: { ...draft.rule, minKv: Number(e.target.value) } })}>
                        {[110, 220, 330, 750].map((v) => <option key={v} value={v}>{v}</option>)}
                      </select>
                    </label>
                  )}
                </div>
              )}
              {draft.threat === "strike_plant" && (
                <label>Втрачена частка потужності
                  <input type="range" min={0.1} max={1} step={0.05} value={draft.capacityShare} onChange={(e) => onChange({ capacityShare: Number(e.target.value) })} />
                  <span className="en-range-value">{Math.round(draft.capacityShare * 100)}%</span>
                </label>
              )}
            </>
          )}
          {draft.threat === "demand" && (
            <label>Зміна попиту
              <input type="range" min={0.7} max={1.3} step={0.01} value={draft.factor} onChange={(e) => onChange({ factor: Number(e.target.value) })} />
              <span className="en-range-value">{draft.factor >= 1 ? "+" : ""}{Math.round((draft.factor - 1) * 100)}%</span>
            </label>
          )}
          {draft.threat === "fuel" && (
            <div className="en-form-row">
              <label>Ресурс
                <select value={draft.fuel} onChange={(e) => onChange({ fuel: e.target.value })}>
                  {["gas", "coal", "hydro", "nuclear", "oil"].map((f) => <option key={f} value={f}>{FUEL_LABEL[f]}</option>)}
                </select>
              </label>
              <label>Доступно
                <input type="range" min={0} max={1} step={0.05} value={draft.factor} onChange={(e) => onChange({ factor: Number(e.target.value) })} />
                <span className="en-range-value">{Math.round(draft.factor * 100)}%</span>
              </label>
            </div>
          )}
          {draft.threat === "separate" && (
            <div className="en-form-row">
              {[0, 1].map((k) => (
                <label key={k}>{k ? "від" : "Відокремити"}
                  <select value={draft.pair[k]} onChange={(e) => onChange({ pair: k ? [draft.pair[0], e.target.value] : [e.target.value, draft.pair[1]] })}>
                    {COUNTRIES.map((c) => <option key={c} value={c}>{COUNTRY_LABEL[c]}</option>)}
                  </select>
                </label>
              ))}
            </div>
          )}
          <label>Підпис події (необов'язково) <input value={draft.label} placeholder={defaultLabel(draft)} onChange={(e) => onChange({ label: e.target.value })} /></label>
          <button className="en-link-btn danger" onClick={onRemove}>Видалити подію</button>
        </div>
      )}
    </div>
  );
}
