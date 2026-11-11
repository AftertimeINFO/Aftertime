import { useEffect, useState } from "react";
import { request } from "./api";
import VersionBadge from "./VersionBadge";
import EntityCard from "./EntityCard";
import type { EntityList, EntityListItem } from "./worldModel";

const PAGE = 200;

function readParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

/** Browser of every entity in the world model with the entity card on the right. */
export default function WorldEntities() {
  const [query, setQuery] = useState(readParam("q") || "");
  const [kind, setKind] = useState(readParam("kind") || "");
  const [list, setList] = useState<EntityList | null>(null);
  const [items, setItems] = useState<EntityListItem[]>([]);
  const [selected, setSelected] = useState<string | null>(readParam("id"));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({ limit: String(PAGE) });
      if (query.trim()) params.set("q", query.trim());
      if (kind) params.set("kind", kind);
      request<EntityList>(`/world/entities?${params}`, { signal: controller.signal })
        .then((page) => { setList(page); setItems(page.items); setError(null); })
        .catch((reason) => { if (!controller.signal.aborted) setError(String(reason?.message || reason)); });
    }, 200);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query, kind]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (selected) params.set("id", selected);
    if (query.trim()) params.set("q", query.trim());
    if (kind) params.set("kind", kind);
    const search = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${search ? `?${search}` : ""}`);
  }, [selected, query, kind]);

  const loadMore = async () => {
    const params = new URLSearchParams({ limit: String(PAGE), offset: String(items.length) });
    if (query.trim()) params.set("q", query.trim());
    if (kind) params.set("kind", kind);
    const page = await request<EntityList>(`/world/entities?${params}`);
    setItems((rows) => [...rows, ...page.items]);
  };

  const kinds = Object.entries(list?.kinds || {}).sort((a, b) => b[1] - a[1]);
  const grandTotal = kinds.reduce((sum, [, count]) => sum + count, 0);

  return (
    <div className="world-shell entities-shell">
      <header className="world-top">
        <a href="/" className="world-back">← Model Lab</a>
        <div>
          <small>МОДЕЛЬ СВІТУ · УСІ СУТНОСТІ</small>
          <b>Сутності {list ? `· ${list.total}` : ""}</b>
        </div>
        <div className="world-top-right">
          <a href="/world" className="world-back">▶ Програвання пілоту</a>
          <VersionBadge />
        </div>
      </header>
      <div className="entities-body">
        <aside className="entities-list">
          <input type="search" placeholder="Пошук за назвою або id" value={query} onChange={(e) => setQuery(e.target.value)} />
          <div className="entities-kinds">
            <button className={kind === "" ? "active" : ""} onClick={() => setKind("")}>усі · {grandTotal}</button>
            {kinds.map(([name, count]) => <button key={name} className={kind === name ? "active" : ""} onClick={() => setKind(kind === name ? "" : name)}>{name} · {count}</button>)}
          </div>
          {error && <p className="entity-muted">{error}</p>}
          <ul>
            {items.map((item) => (
              <li key={item.id} className={item.id === selected ? "active" : ""} onClick={() => setSelected(item.id)}>
                <b>{item.name}</b>
                <span>{item.kind}{item.type ? ` · ${item.type.replace("type:", "")}` : ""}</span>
              </li>
            ))}
          </ul>
          {list && items.length < list.total && <button className="entity-more" onClick={() => void loadMore()}>Показати ще ({list.total - items.length})</button>}
        </aside>
        <main className="entities-card">
          {selected ? <EntityCard id={selected} onOpen={setSelected} showPlay /> : <div className="entity-empty">Оберіть сутність ліворуч.</div>}
        </main>
      </div>
    </div>
  );
}
