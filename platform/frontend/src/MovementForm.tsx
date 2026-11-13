import { useEffect, useState } from "react";
import { request } from "./api";
import { hrefWithLayer } from "./appContext";
import { PROVENANCE_LABEL } from "./coverage";
import { SourceList, type Source } from "./Sources";

export type StoredRef = { table: string; id: string };
/** One line of the movements report, as the API returns it. */
export type MovementLine = {
  at: string;
  event: string | null;
  movement: string;
  material: string;
  material_name: string;
  column: string;
  amount: number;
  provenance: string;
  sources: Source[];
  records: StoredRef[];
};
type Row = Record<string, unknown>;
type StoredRecord = {
  table: string;
  id: string;
  fields: Row;
  postings?: Row[];
  relations?: Row[];
  observations?: Row[];
  entities: Record<string, { name: string; kind: string }>;
  sources: Record<string, { name: string; url: string }>;
};

const COLUMN_LABEL: Record<string, string> = {
  inflow: "Надходження",
  outflow: "Вибуття",
  transform: "Трансформація",
  carrier: "З носієм",
  revision: "Переоцінка",
  internal: "Внутрішній оборот",
};
const TABLE_LABEL: Record<string, string> = {
  events: "Подія",
  observations: "Спостереження (оцінка)",
  relations: "Зв'язок (розміщення носія)",
};
const ENTITY_COLUMNS = new Set(["event_type_id", "entity_id", "subject_id", "object_id", "owner_entity_id"]);

/** A value of a stored field, as it is in the database: ids with the name they point at. */
function Value({ column, value, record }: { column: string; value: unknown; record: StoredRecord }) {
  if (value === null || value === undefined) return <span className="record-null">NULL</span>;
  if (typeof value === "object") return <pre className="record-json">{JSON.stringify(value, null, 2)}</pre>;
  const text = String(value);
  if (ENTITY_COLUMNS.has(column)) {
    const entity = record.entities[text];
    return (
      <span>
        <a className="record-id" href={hrefWithLayer(`/world/entities?id=${encodeURIComponent(text)}`)}>{text}</a>
        {entity && <span className="record-hint"> · {entity.name} ({entity.kind})</span>}
      </span>
    );
  }
  if (column === "source_id") {
    const source = record.sources[text];
    return (
      <span>
        <span className="record-id">{text}</span>
        {source && (
          <span className="record-hint">
            {" · "}
            {source.url ? <a href={source.url} target="_blank" rel="noreferrer noopener">{source.name}</a> : source.name}
          </span>
        )}
      </span>
    );
  }
  if (column === "id" || column.endsWith("_id")) return <span className="record-id">{text}</span>;
  return <span className="record-value">{text}</span>;
}

function Fields({ fields, record }: { fields: Row; record: StoredRecord }) {
  return (
    <dl className="record-fields">
      {Object.entries(fields).map(([column, value]) => (
        <div key={column}>
          <dt>{column}</dt>
          <dd>
            <Value column={column} value={value} record={record} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Rows({ title, rows, record }: { title: string; rows?: Row[]; record: StoredRecord }) {
  if (!rows?.length) return null;
  const columns = Object.keys(rows[0]);
  return (
    <section className="record-rows">
      <h3>
        {title} <small>· {rows.length}</small>
      </h3>
      <div className="record-rows-wrap">
        <table>
          <thead>
            <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={String(row.id ?? i)}>
                {columns.map((c) => (
                  <td key={c} className={typeof row[c] === "number" ? "num" : ""}>
                    <Value column={c} value={row[c]} record={record} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Stored({ reference }: { reference: StoredRef }) {
  const [record, setRecord] = useState<StoredRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    request<StoredRecord>(`/world/records/${reference.table}/${encodeURIComponent(reference.id)}`, { signal: controller.signal })
      .then(setRecord)
      .catch((reason) => !controller.signal.aborted && setError(String(reason?.message || reason)));
    return () => controller.abort();
  }, [reference.table, reference.id]);
  return (
    <section className="record">
      <h2>
        {TABLE_LABEL[reference.table] ?? reference.table}
        <small>
          таблиця <code>{reference.table}</code> · id <code>{reference.id}</code>
        </small>
      </h2>
      {error && <div className="balance-message bad">{error}</div>}
      {!record && !error && <div className="balance-message">Читання запису…</div>}
      {record && (
        <>
          <Fields fields={record.fields} record={record} />
          <Rows title="Проведення (postings)" rows={record.postings} record={record} />
          <Rows title="Зв'язки, створені подією (relations)" rows={record.relations} record={record} />
          <Rows title="Спостереження, створені подією (observations)" rows={record.observations} record={record} />
        </>
      )}
    </section>
  );
}

/** Movement form: the report line and the stored records behind it, field by field. */
export function MovementForm({ line, scope, onClose }: { line: MovementLine; scope: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const derived: Row = {
    at: line.at,
    scope,
    movement: line.movement,
    material: line.material,
    column: line.column,
    amount_kg: line.amount,
    provenance: line.provenance,
  };
  const hints: StoredRecord = { table: "", id: "", fields: {}, entities: { [line.material]: { name: line.material_name, kind: "type" } }, sources: {} };
  return (
    <div className="scope-dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="scope-dialog movement-form" role="dialog" aria-modal="true" aria-label="Форма руху">
        <header>
          <div>
            <small>ФОРМА РУХУ · {COLUMN_LABEL[line.column] ?? line.column}</small>
            <b>{line.movement}</b>
          </div>
          <button className="scope-dialog-close" onClick={onClose} aria-label="Закрити">
            ×
          </button>
        </header>
        <div className="movement-form-body" onClick={(e) => (e.target as HTMLElement).closest("a[href^='/']") && onClose()}>
          <section className="record">
            <h2>
              Рядок звіту
              <small>розраховано зі збережених записів для scope · {PROVENANCE_LABEL[line.provenance] ?? line.provenance}</small>
            </h2>
            <dl className="record-fields">
              {Object.entries(derived).map(([column, value]) => (
                <div key={column}>
                  <dt>{column}</dt>
                  <dd>
                    {column === "material" ? (
                      <Value column="entity_id" value={value} record={hints} />
                    ) : (
                      <Value column={column} value={value} record={hints} />
                    )}
                  </dd>
                </div>
              ))}
            </dl>
            {line.sources.length > 0 && (
              <div className="record-sources">
                <small>Джерела руху</small>
                <SourceList sources={line.sources} />
              </div>
            )}
          </section>
          {line.records.length ? (
            line.records.map((reference) => <Stored key={`${reference.table}/${reference.id}`} reference={reference} />)
          ) : (
            <div className="balance-message">Для цього руху немає збереженого запису.</div>
          )}
        </div>
      </div>
    </div>
  );
}
