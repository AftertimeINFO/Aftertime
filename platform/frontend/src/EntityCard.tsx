import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { formatMass, scientific, type EntityCardData, type Operation, type Operations, type RelationRow } from "./worldModel";

const PREDICATES: Record<string, string> = {
  instance_of: "є екземпляром",
  subclass_of: "підтип",
  part_of: "частина",
  located_in: "знаходиться в",
  composed_of: "складається з",
  operated_by: "оператор",
  owned_by: "власник",
  jurisdiction_of: "юрисдикція",
  connects: "з'єднує",
  passes_through: "проходить через",
  consumes: "споживає",
  produces: "виробляє",
  same_as: "те саме, що",
  contains: "містить",
  operates: "оперує",
  connected_to: "під'єднано до",
};
const MIN_INTERVAL_MS = 500;

const dateTime = (iso: string) => new Date(iso).toLocaleString("uk-UA", { timeZone: "UTC", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

function Sci({ value }: { value: number | null }) {
  if (value === null) return <>—</>;
  const [mantissa, exponent] = scientific(value);
  return <>{mantissa} × 10<sup>{exponent}</sup></>;
}

type Props = {
  id: string;
  /** Moment in ms; omitted means "after all recorded events". */
  at?: number | null;
  onOpen: (id: string) => void;
  /** Link to the playback page when the entity takes part in a run. */
  showPlay?: boolean;
};

/** Card of any world entity: what it is, what it contains (down to atoms) and what happened to it. */
export default function EntityCard({ id, at, onOpen, showPlay }: Props) {
  const [card, setCard] = useState<EntityCardData | null>(null);
  const [more, setMore] = useState<Operation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef({ id, at }), timer = useRef<number | null>(null), last = useRef(0), loadedId = useRef<string | null>(null);
  latest.current = { id, at };

  // Throttled loading: the clock may tick every frame while playing.
  useEffect(() => {
    const load = async () => {
      timer.current = null;
      last.current = Date.now();
      const { id: currentId, at: moment } = latest.current;
      const query = moment != null ? `?at=${encodeURIComponent(new Date(moment).toISOString())}` : "";
      try {
        const next = await request<EntityCardData>(`/world/entities/${encodeURIComponent(currentId)}${query}`);
        if (latest.current.id !== currentId) return;
        // A refreshed card starts a fresh first page of operations.
        setMore([]);
        loadedId.current = currentId;
        setCard(next);
        setError(null);
      } catch (reason: any) {
        setError(String(reason?.message || reason));
      }
    };
    if (loadedId.current !== id) {
      if (timer.current) window.clearTimeout(timer.current);
      void load();
      return;
    }
    if (timer.current) return;
    timer.current = window.setTimeout(load, Math.max(0, MIN_INTERVAL_MS - (Date.now() - last.current)));
  }, [id, at]);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  if (error && !card) return <div className="entity-card entity-empty">Не вдалося завантажити: {error}</div>;
  if (!card) return <div className="entity-card entity-empty">Завантаження…</div>;

  const { entity, contents } = card;
  const types = card.outgoing.filter((r) => r.predicate === "instance_of");
  const outgoing = card.outgoing.filter((r) => r.predicate !== "instance_of");
  const operations = [...card.operations.items, ...more];
  const loadMore = async () => {
    const query = new URLSearchParams({ limit: "100", offset: String(operations.length) });
    if (at != null) query.set("at", new Date(at).toISOString());
    const page = await request<Operations>(`/world/entities/${encodeURIComponent(id)}/operations?${query}`);
    setMore((rows) => [...rows, ...page.items]);
  };
  const playHref = `/world?entity=${encodeURIComponent(entity.id)}${at != null ? `&t=${encodeURIComponent(new Date(at).toISOString())}` : ""}`;

  return (
    <div className="entity-card">
      <header>
        <small>{entity.kind} · {entity.level}</small>
        <h2>{entity.name}{entity.symbol ? <span className="entity-symbol">{entity.symbol}</span> : null}</h2>
        <code>{entity.id}</code>
        {types.length > 0 && <div className="entity-chips">{types.map((t) => <button key={t.entity_id} onClick={() => onOpen(t.entity_id)}>{t.name}</button>)}</div>}
        {entity.description && <p>{entity.description}</p>}
        {showPlay && card.runs.length > 0 && <a className="entity-play" href={playHref}>▶ Відкрити у програванні</a>}
      </header>

      <section>
        <h3>Матерія всередині {card.at ? `на ${dateTime(card.at)}` : "після всіх подій"}</h3>
        {contents.portions.length === 0 ? <p className="entity-muted">Порцій речовини немає.</p> : (
          <>
            <div className="entity-total">{formatMass(contents.total_kg)}</div>
            <table className="entity-table">
              <thead><tr><th>Речовина</th><th>Маса</th></tr></thead>
              <tbody>{contents.materials.map((m) => <tr key={m.id}><td><button onClick={() => onOpen(m.id)}>{m.name}</button></td><td>{formatMass(m.kg)}</td></tr>)}</tbody>
            </table>
            {contents.elements.some((e) => e.kg !== 0) && (
              <table className="entity-table">
                <thead><tr><th>Елемент</th><th>Маса</th><th>моль</th><th>атомів</th></tr></thead>
                <tbody>
                  {contents.elements.filter((e) => e.kg !== 0).map((e) => (
                    <tr key={e.id}>
                      <td><button onClick={() => onOpen(e.id)}><b>{e.symbol}</b> {e.name}</button></td>
                      <td>{formatMass(e.kg)}</td>
                      <td><Sci value={e.mol} /></td>
                      <td><Sci value={e.atoms} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {contents.unresolved_kg > 0 && <p className="entity-muted">Без відомого складу: {formatMass(contents.unresolved_kg)}</p>}
            <details>
              <summary>Порції ({contents.portions.length})</summary>
              <ul className="entity-rows">
                {contents.portions.map((p) => (
                  <li key={p.id}>
                    <button onClick={() => onOpen(p.id)}>{p.name}</button>
                    <span>{formatMass(p.kg)}{p.estimated ? " · оцінка + рух" : ""}</span>
                  </li>
                ))}
              </ul>
            </details>
          </>
        )}
      </section>

      <section>
        <h3>Операції · {card.operations.total}</h3>
        {operations.length === 0 ? <p className="entity-muted">Подій немає.</p> : (
          <ul className="entity-ops">
            {operations.map((op) => {
              const own = op.postings.filter((p) => p.own).reduce((sum, p) => sum + p.delta, 0);
              const others = op.postings.filter((p) => !p.own);
              return (
                <li key={op.id}>
                  <div><b>{op.type_name}</b><span>{dateTime(op.occurred_at)} · {op.provenance}</span></div>
                  {op.postings.length > 0 ? (
                    <em className={own < 0 ? "out" : own > 0 ? "in" : ""}>{own > 0 ? "+" : ""}{formatMass(own)}</em>
                  ) : <em>{op.attributes.direction === "laden" ? "з вантажем" : op.attributes.direction === "ballast" ? "у баласті" : op.attributes.place ? `→ ${String(op.attributes.place).replace(/^[a-z]+:/, "")}` : "рух"}</em>}
                  {others.length > 0 && (
                    <small>{others.map((p) => <button key={p.entity_id} onClick={() => onOpen(p.entity_id)}>{p.entity_id.replace("portion:", "")} {p.delta > 0 ? "+" : ""}{formatMass(p.delta)}</button>)}</small>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {operations.length < card.operations.total && <button className="entity-more" onClick={() => void loadMore()}>Показати ще ({card.operations.total - operations.length})</button>}
      </section>

      <RelationList title="Зв'язки" rows={outgoing} onOpen={onOpen} />
      <RelationList title="Посилаються на цю сутність" rows={card.incoming} onOpen={onOpen} />

      {card.observations.length > 0 && (
        <section>
          <h3>Оцінки та спостереження</h3>
          <ul className="entity-rows">
            {card.observations.map((o, i) => (
              <li key={i}>
                <span>{o.property} · {o.epistemic_status} · {new Date(o.valid_time).toLocaleDateString("uk-UA")}{o.evidence?.class ? ` · ${o.evidence.class}` : ""}</span>
                <b>{o.unit === "kg" ? formatMass(o.value) : `${o.value} ${o.unit}`}</b>
              </li>
            ))}
          </ul>
        </section>
      )}

      {card.extents.length > 0 && (
        <section>
          <h3>Просторова протяжність</h3>
          <ul className="entity-rows">
            {card.extents.map((x, i) => (
              <li key={i}>
                <span>{x.geometry?.type || "без геометрії"}</span>
                <b>{x.z_min_m != null || x.z_max_m != null ? `z ${x.z_min_m ?? "…"} … ${x.z_max_m ?? "…"} м${x.z_surface_ref ? ` від ${x.z_surface_ref}` : ""}` : ""}</b>
              </li>
            ))}
          </ul>
        </section>
      )}

      {Object.keys(entity.attributes || {}).length > 0 && (
        <section>
          <h3>Атрибути</h3>
          <pre className="entity-attributes">{JSON.stringify(entity.attributes, null, 2)}</pre>
        </section>
      )}
    </div>
  );
}

function RelationList({ title, rows, onOpen }: { title: string; rows: RelationRow[]; onOpen: (id: string) => void }) {
  if (rows.length === 0) return null;
  return (
    <section>
      <h3>{title} · {rows.length}</h3>
      <ul className="entity-rows">
        {rows.map((r, i) => (
          <li key={`${r.predicate}-${r.entity_id}-${i}`}>
            <span>{PREDICATES[r.predicate] || r.predicate}{r.coefficient != null ? ` · ${r.coefficient}${r.unit ? ` ${r.unit}` : ""}` : ""}{r.valid_from ? ` · з ${dateTime(r.valid_from)}` : ""}</span>
            <button onClick={() => onOpen(r.entity_id)}>{r.name}</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
