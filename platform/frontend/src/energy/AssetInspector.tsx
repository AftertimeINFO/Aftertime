import { useEffect, useState } from "react";
import { gridApi, type AssetCard, type AssetLink } from "./energyApi";
import { COUNTRY_LABEL, FUEL_LABEL, KIND_LABEL, STATUS_LABEL, assetTitle, fmtDate, fmtKv, fmtMw, fmtNumber, voltageColor } from "./format";

const CAPACITY_SOURCE: Record<string, string> = {
  osm: "з OSM",
  generators: "сума генераторів (OSM)",
  estimated: "оцінка",
  override: "ручна правка",
};

const QUALITY_TEXT: Record<string, string> = {
  voltage_missing: "У OSM не вказано напругу — для розрахунку її буде оцінено за сусідніми об'єктами.",
  capacity_missing: "У OSM не вказано потужність станції — модель використовує оцінку.",
  power_unit_missing: "Потужність записано без одиниць, прочитано як МВт.",
  capacity_from_generators: "Потужність станції обчислено як суму її генераторів.",
  inside_plant: "Генератор розташований у межах станції й рахується в її складі.",
};

type Props = {
  id: number;
  canEdit: boolean;
  onSelect: (id: number) => void;
  onFocus: (card: AssetCard) => void;
  onClose: () => void;
  actions?: (card: AssetCard) => React.ReactNode;
};

/** Card of one OSM power asset: facts with their provenance, links, corrections. */
export default function AssetInspector({ id, canEdit, onSelect, onFocus, onClose, actions }: Props) {
  const [card, setCard] = useState<AssetCard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [showTags, setShowTags] = useState(false);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let alive = true;
    setError(null);
    gridApi
      .asset(id)
      .then((value) => alive && setCard(value))
      .catch((reason) => alive && setError(String(reason?.message || reason)));
    return () => {
      alive = false;
    };
  }, [id, version]);

  useEffect(() => {
    setEditing(false);
    setShowTags(false);
  }, [id]);

  if (error) return <div className="en-inspector"><InspectorHead title="Помилка" onClose={onClose} /><p className="en-error" role="alert">{error}</p></div>;
  if (!card || card.id !== id) return <div className="en-inspector" aria-busy="true"><InspectorHead title="Завантаження…" onClose={onClose} /><div className="en-skeleton" /><div className="en-skeleton short" /></div>;

  const isLine = ["line", "cable", "minor_line"].includes(card.kind);
  const isPlant = card.kind === "plant" || card.kind === "generator";
  const links = card.lines ?? card.ends ?? card.nearby ?? [];
  const linkTitle = card.lines ? `Лінії, що заходять (${card.lines.length})` : card.ends ? "Кінці лінії" : "Найближчі підстанції";

  return (
    <div className="en-inspector">
      <InspectorHead
        title={assetTitle(card)}
        subtitle={[KIND_LABEL[card.kind] ?? card.kind, card.subkind && SUBKIND[card.subkind], COUNTRY_LABEL[card.country ?? ""] ?? card.country].filter(Boolean).join(" · ")}
        swatch={isPlant ? undefined : voltageColor(card.max_voltage_kv)}
        onClose={onClose}
      />
      <div className="en-inspector-actions">
        <button className="en-btn" onClick={() => onFocus(card)}>Показати на мапі</button>
        {actions?.(card)}
      </div>
      {card.status !== "active" && <p className={`en-status-banner status-${card.status}`}>{STATUS_LABEL[card.status] ?? card.status}</p>}
      <dl className="en-facts">
        {!isPlant && <Fact label="Напруга" value={fmtKv(card.voltages_kv)} flag={card.quality.includes("voltage_missing") ? "немає в OSM" : undefined} />}
        {isPlant && <Fact label="Потужність" value={fmtMw(card.capacity_mw)} note={card.capacity_source ? CAPACITY_SOURCE[card.capacity_source] ?? card.capacity_source : undefined} flag={card.capacity_mw == null ? "немає в OSM" : undefined} />}
        {isPlant && <Fact label="Тип" value={card.fuel ? FUEL_LABEL[card.fuel] ?? card.fuel : "—"} />}
        {isLine && <Fact label="Довжина" value={card.length_km != null ? `${fmtNumber(card.length_km, card.length_km < 10 ? 1 : 0)} км` : "—"} />}
        {isLine && <Fact label="Кола" value={card.circuits != null ? String(card.circuits) : "—"} note={card.circuits == null ? "прийнято 1" : undefined} />}
        {card.frequency_hz === 0 && <Fact label="Струм" value="Постійний (HVDC)" />}
        <Fact label="Оператор" value={card.operator ?? "—"} />
        {card.ref && <Fact label="Диспетчерська назва" value={card.ref} />}
        {card.start_date && <Fact label="Введено" value={fmtDate(card.start_date)} />}
      </dl>
      {card.quality.filter((q) => QUALITY_TEXT[q]).length > 0 && (
        <ul className="en-quality-notes" aria-label="Примітки щодо даних">
          {card.quality.filter((q) => QUALITY_TEXT[q]).map((q) => <li key={q}>{QUALITY_TEXT[q]}</li>)}
        </ul>
      )}
      {links.length > 0 && (
        <section className="en-section">
          <h4>{linkTitle}</h4>
          <ul className="en-links">
            {links.map((link) => <LinkRow key={`${link.id}-${link.side ?? ""}`} link={link} onSelect={onSelect} />)}
          </ul>
        </section>
      )}
      <section className="en-section">
        <div className="en-section-head">
          <h4>Правки для моделі {card.overrides.length > 0 && <span className="en-count">{card.overrides.length}</span>}</h4>
          {canEdit && !editing && <button className="en-link-btn" onClick={() => setEditing(true)}>+ Додати правку</button>}
        </div>
        {!card.overrides.length && !editing && <p className="en-hint">Немає. Правка змінює об'єкт у моделі на певний період (наприклад, «зруйновано з 10.10.2022») і завжди має джерело.</p>}
        {card.overrides.map((o) => (
          <div className="en-override" key={o.id}>
            <b>{OVERRIDE_LABEL[o.field] ?? o.field}: {String(typeof o.value === "string" ? STATUS_LABEL[o.value] ?? o.value : o.value)}</b>
            <span>{o.valid_from ? `з ${fmtDate(o.valid_from)}` : "завжди"}{o.valid_to ? ` по ${fmtDate(o.valid_to)}` : ""}</span>
            {o.note && <span className="en-muted">{o.note}</span>}
            <a href={o.source_url} target="_blank" rel="noreferrer noopener">джерело ↗</a>
            {canEdit && (
              <button className="en-link-btn danger" onClick={() => gridApi.deleteOverride(o.id).then(() => setVersion((v) => v + 1))} aria-label="Видалити правку">видалити</button>
            )}
          </div>
        ))}
        {editing && <OverrideForm assetId={card.id} onDone={(saved) => { setEditing(false); if (saved) setVersion((v) => v + 1); }} />}
      </section>
      <section className="en-section">
        <button className="en-disclosure" aria-expanded={showTags} onClick={() => setShowTags(!showTags)}>
          {showTags ? "▾" : "▸"} Усі теги OSM ({Object.keys(card.tags).length})
        </button>
        {showTags && (
          <table className="en-tags"><tbody>
            {Object.entries(card.tags).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => <tr key={k}><th>{k}</th><td>{v}</td></tr>)}
          </tbody></table>
        )}
      </section>
      <footer className="en-provenance">
        <a href={card.source.url} target="_blank" rel="noreferrer noopener">Відкрити в OpenStreetMap ↗</a>
        <span>{card.source.attribution}</span>
      </footer>
    </div>
  );
}

const SUBKIND: Record<string, string> = {
  transmission: "магістральна",
  distribution: "розподільна",
  minor_distribution: "ТП",
  industrial: "промислова",
  traction: "тягова",
  generation: "станційна",
  converter: "перетворювальна",
  hvdc: "HVDC",
  underground: "підземний",
  submarine: "підводний",
  combustion: "теплова",
  "run-of-the-river": "руслова",
  "water-storage": "з водосховищем",
  "water-pumped-storage": "ГАЕС",
  fission: "ядерна",
  photovoltaic: "фотоелектрична",
  "wind_turbine": "вітротурбіна",
};

const OVERRIDE_LABEL: Record<string, string> = {
  status: "Статус",
  capacity_mw: "Потужність, МВт",
  availability: "Доступність",
  controlled_by: "Під контролем",
  in_service_from: "Введено",
  out_of_service_from: "Виведено",
};

function InspectorHead({ title, subtitle, swatch, onClose }: { title: string; subtitle?: string; swatch?: string; onClose: () => void }) {
  return (
    <header className="en-inspector-head">
      {swatch && <i className="en-swatch" style={{ background: swatch }} aria-hidden="true" />}
      <div>
        <h3>{title}</h3>
        {subtitle && <small>{subtitle}</small>}
      </div>
      <button className="en-icon-btn" onClick={onClose} aria-label="Закрити картку" title="Закрити (Esc)">×</button>
    </header>
  );
}

function Fact({ label, value, note, flag }: { label: string; value: string; note?: string; flag?: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>
        {value}
        {note && <span className="en-prov">{note}</span>}
        {flag && <span className="en-prov warn">{flag}</span>}
      </dd>
    </>
  );
}

function LinkRow({ link, onSelect }: { link: AssetLink; onSelect: (id: number) => void }) {
  const detail = [
    link.max_voltage_kv ? fmtKv(link.max_voltage_kv) : null,
    link.length_km != null ? `${fmtNumber(link.length_km, link.length_km < 10 ? 1 : 0)} км` : null,
    link.distance_m != null ? `${fmtNumber(Number(link.distance_m))} м` : null,
    link.side ? (link.side === "start" ? "початок" : "кінець") : null,
    link.status !== "active" ? STATUS_LABEL[link.status] ?? link.status : null,
  ].filter(Boolean).join(" · ");
  return (
    <li>
      <button onClick={() => onSelect(link.id)}>
        <i className="en-swatch small" style={{ background: voltageColor(link.max_voltage_kv) }} aria-hidden="true" />
        <span>{assetTitle({ ...link, kind: link.kind })}</span>
        <small>{detail}</small>
      </button>
    </li>
  );
}

function OverrideForm({ assetId, onDone }: { assetId: number; onDone: (saved: boolean) => void }) {
  const [field, setField] = useState("status");
  const [value, setValue] = useState("destroyed");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [source, setSource] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const numeric = field === "capacity_mw" || field === "availability";
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    gridApi
      .createOverride({
        asset_id: assetId,
        field,
        value: numeric ? Number(value) : value,
        valid_from: from || null,
        valid_to: to || null,
        source_url: source.trim(),
        note,
      })
      .then(() => onDone(true))
      .catch((reason) => setError(String(reason?.message || reason)))
      .finally(() => setBusy(false));
  };
  return (
    <form className="en-form" onSubmit={submit}>
      <label>Що змінюємо
        <select value={field} onChange={(e) => { setField(e.target.value); setValue(e.target.value === "status" ? "destroyed" : ""); }}>
          {Object.entries(OVERRIDE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <label>Значення
        {field === "status" ? (
          <select value={value} onChange={(e) => setValue(e.target.value)}>
            {["destroyed", "damaged", "occupied", "disused", "active"].map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
        ) : (
          <input value={value} onChange={(e) => setValue(e.target.value)} inputMode={numeric ? "decimal" : "text"} required placeholder={field === "availability" ? "0…1" : ""} />
        )}
      </label>
      <div className="en-form-row">
        <label>Діє з <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label>по <input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
      </div>
      <label>Джерело (посилання) <span className="en-required">обов'язково</span>
        <input type="url" value={source} onChange={(e) => setSource(e.target.value)} required placeholder="https://…" />
      </label>
      <label>Примітка <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} /></label>
      {error && <p className="en-error" role="alert">{error}</p>}
      <div className="en-form-actions">
        <button type="button" className="en-btn ghost" onClick={() => onDone(false)}>Скасувати</button>
        <button type="submit" className="en-btn primary" disabled={busy}>{busy ? "Збереження…" : "Зберегти правку"}</button>
      </div>
    </form>
  );
}
