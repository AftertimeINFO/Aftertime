import { useEffect, useState } from "react";
import { gridApi, type GridSummary, type QualityItem } from "./energyApi";
import { COUNTRY_LABEL, FUEL_COLOR, FUEL_LABEL, KIND_LABEL, STATUS_LABEL, fmtCount, fmtDate, fmtMw, fmtNumber } from "./format";
import { DEFAULT_FILTERS, type PowerFilters } from "./mapStyle";

const VOLTAGE_STEPS = [
  { value: 0, label: "Усі" },
  { value: 35, label: "35+" },
  { value: 110, label: "110+" },
  { value: 220, label: "220+" },
  { value: 330, label: "330+" },
  { value: 500, label: "500+" },
];
const KIND_TOGGLES: { key: keyof PowerFilters["kinds"]; label: string }[] = [
  { key: "lines", label: "Повітряні лінії" },
  { key: "cables", label: "Кабелі" },
  { key: "substations", label: "Підстанції" },
  { key: "plants", label: "Електростанції" },
  { key: "generators", label: "Окремі генератори" },
];
const STATUS_TOGGLES = ["active", "construction", "proposed", "disused", "damaged", "destroyed", "occupied"];

type Props = {
  summary: GridSummary | null;
  filters: PowerFilters;
  onFilters: (filters: PowerFilters) => void;
  onSelect: (id: number) => void;
};

/** Left panel of the Network mode: what to show, what is in the data, and its gaps. */
export default function NetworkPanel({ summary, filters, onFilters, onSelect }: Props) {
  const [quality, setQuality] = useState<QualityItem[] | null>(null);
  const [openFlag, setOpenFlag] = useState<string | null>(null);
  useEffect(() => {
    if (summary?.imported) gridApi.quality().then((r) => setQuality(r.items)).catch(() => setQuality([]));
  }, [summary?.imported]);
  const changed = JSON.stringify(filters) !== JSON.stringify(DEFAULT_FILTERS);
  const totals = (summary?.countries ?? []).reduce(
    (acc, c) => ({ plant_mw: acc.plant_mw + (c.plant_mw ?? 0), line_km: acc.line_km + (c.line_km ?? 0), substation: acc.substation + (c.substation ?? 0), plant: acc.plant + (c.plant ?? 0) }),
    { plant_mw: 0, line_km: 0, substation: 0, plant: 0 },
  );
  const fresh = summary?.batches.filter((b) => b.status === "succeeded").map((b) => b.source_timestamp).filter(Boolean).sort()[0];

  return (
    <div className="en-panel">
      <section className="en-section">
        <div className="en-section-head">
          <h4>Що показувати</h4>
          {changed && <button className="en-link-btn" onClick={() => onFilters(DEFAULT_FILTERS)}>Скинути</button>}
        </div>
        <fieldset className="en-fieldset">
          <legend>Мінімальна напруга</legend>
          <div className="en-segmented small" role="radiogroup" aria-label="Мінімальна напруга">
            {VOLTAGE_STEPS.map((step) => (
              <button key={step.value} role="radio" aria-checked={filters.minVoltage === step.value} className={filters.minVoltage === step.value ? "active" : ""} onClick={() => onFilters({ ...filters, minVoltage: step.value })}>
                {step.label}
              </button>
            ))}
          </div>
        </fieldset>
        <fieldset className="en-fieldset">
          <legend>Об'єкти</legend>
          {KIND_TOGGLES.map((toggle) => (
            <label key={toggle.key} className="en-check">
              <input type="checkbox" checked={filters.kinds[toggle.key]} onChange={(e) => onFilters({ ...filters, kinds: { ...filters.kinds, [toggle.key]: e.target.checked } })} />
              {toggle.label}
            </label>
          ))}
        </fieldset>
        <fieldset className="en-fieldset">
          <legend>Тип станцій</legend>
          <div className="en-chips">
            {Object.keys(FUEL_COLOR).map((fuel) => {
              const on = !filters.fuels || filters.fuels.includes(fuel);
              return (
                <button
                  key={fuel}
                  className={`en-chip ${on ? "on" : ""}`}
                  aria-pressed={on}
                  onClick={() => {
                    const all = Object.keys(FUEL_COLOR).concat("other");
                    const current = filters.fuels ?? all;
                    const next = on ? current.filter((f) => f !== fuel) : [...current, fuel];
                    onFilters({ ...filters, fuels: next.length === all.length ? null : next });
                  }}
                >
                  <i style={{ background: FUEL_COLOR[fuel] }} aria-hidden="true" />
                  {FUEL_LABEL[fuel]}
                </button>
              );
            })}
          </div>
        </fieldset>
        <fieldset className="en-fieldset">
          <legend>Стан</legend>
          <div className="en-chips">
            {STATUS_TOGGLES.map((status) => {
              const on = filters.statuses.includes(status);
              return (
                <button key={status} className={`en-chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => onFilters({ ...filters, statuses: on ? filters.statuses.filter((s) => s !== status) : [...filters.statuses, status] })}>
                  {STATUS_LABEL[status]}
                </button>
              );
            })}
          </div>
        </fieldset>
      </section>

      <section className="en-section">
        <h4>Дані мережі</h4>
        {summary?.imported ? (
          <>
            <div className="en-stat-grid">
              <Stat value={fmtMw(totals.plant_mw)} label={`станцій: ${fmtCount(totals.plant)}`} />
              <Stat value={`${fmtCount(totals.line_km)} км`} label="ЛЕП і кабелів" />
              <Stat value={fmtCount(totals.substation)} label="підстанцій" />
            </div>
            <table className="en-table">
              <thead><tr><th>Країна</th><th>Підст.</th><th>ЛЕП, км</th><th>Станції</th></tr></thead>
              <tbody>
                {summary.countries.map((c) => (
                  <tr key={c.country}>
                    <td>{COUNTRY_LABEL[c.country] ?? c.country}</td>
                    <td>{fmtCount(c.substation)}</td>
                    <td>{fmtCount(c.line_km)}</td>
                    <td title={`${fmtNumber(c.plant ?? 0)} станцій`}>{fmtMw(c.plant_mw ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="en-hint">Дані OpenStreetMap станом на {fresh ? fmtDate(fresh) : "—"}. Потужність — лише там, де її вказано в OSM.</p>
          </>
        ) : (
          <p className="en-hint">Мережу ще не імпортовано.</p>
        )}
      </section>

      {quality && quality.length > 0 && (
        <section className="en-section">
          <h4>Прогалини в даних</h4>
          <p className="en-hint">Що бракує в OSM і як модель це заповнює. Натисніть, щоб побачити приклади.</p>
          <ul className="en-quality">
            {quality.filter((q) => q.flag !== "inside_plant").map((q) => {
              const key = `${q.flag}:${q.kind}`;
              return (
                <li key={key}>
                  <button aria-expanded={openFlag === key} onClick={() => setOpenFlag(openFlag === key ? null : key)}>
                    <span>{q.label}</span>
                    <small>{KIND_LABEL[q.kind] ?? q.kind}</small>
                    <b>{fmtCount(q.n)}</b>
                  </button>
                  {openFlag === key && (
                    <div className="en-quality-sample">
                      {q.sample.map((id, index) => (
                        <button key={id} className="en-link-btn" onClick={() => onSelect(id)}>#{index + 1}</button>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="en-stat">
      <b>{value}</b>
      <small>{label}</small>
    </div>
  );
}
