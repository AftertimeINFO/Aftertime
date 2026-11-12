import { useContext, useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre 6 runs its worker from a separate module; the bundler must serve that file.
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { request } from "./api";
import { periodBounds, useAppContext } from "./appContext";
import { PaneContext, replaceTabQuery, tabParams } from "./tabs";
import { PeriodPicker } from "./PeriodSelect";
import EntityCard from "./EntityCard";
import { balancesAt, buildTimeline, lastIndexAt, vesselStates, type LedgerEvent, type LngLat, type PilotObject, type PilotPayload } from "./worldModel";

const DAY = 86_400_000;
const SPEEDS = [0.5, 1, 3, 7, 14]; // simulated days per real second
const EVENT_LABELS: Record<string, string> = {
  "type:extract": "Видобуток",
  "type:transfer": "Перекачка",
  "type:load": "Завантаження",
  "type:depart": "Відхід",
  "type:arrive": "Прибуття",
  "type:discharge": "Вивантаження",
  "type:transform": "Переробка",
};
const STATUS_LABELS = { laden: "у рейсі з вантажем", ballast: "у баласті назад", "at-origin": "біля Рас-Тануры", "at-destination": "біля Сікки" };
// Label text and pixel offset from the point, chosen so neighbouring labels do not collide.
const FACILITY_LABELS: Record<string, [string, [number, number]]> = {
  "asset:abqaiq": ["Абкайк", [9, 4]],
  "asset:ras-tanura": ["Рас-Танура", [9, -8]],
  "asset:sikka": ["Сікка", [9, -9]],
  "asset:jamnagar": ["Джамнагар", [9, 9]],
  "place:ghawar": ["Гавар", [0, 0]],
  "place:strait-of-hormuz": ["Ормузька протока", [0, -14]],
};

// Dark basemap from OpenFreeMap vector tiles (OpenMapTiles schema, © OpenStreetMap contributors).
maplibregl.setWorkerUrl(mapWorkerUrl);

const BASEMAP: maplibregl.StyleSpecification = {
  version: 8,
  sources: { omt: { type: "vector", url: "https://tiles.openfreemap.org/planet" } },
  layers: [
    { id: "land", type: "background", paint: { "background-color": "#10211b" } },
    { id: "water", type: "fill", source: "omt", "source-layer": "water", paint: { "fill-color": "#071722" } },
    {
      id: "countries",
      type: "line",
      source: "omt",
      "source-layer": "boundary",
      filter: ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]],
      paint: { "line-color": "#35574a", "line-width": 0.8 },
    },
  ],
};

const KIND_LABELS: Record<string, string> = { place: "Місця", asset: "Об'єкти та судна", portion: "Порції речовини", actor: "Учасники", element: "Хімічні елементи" };
type Tab = "overview" | "objects" | "card";

const mbbl = (kg: number, kgPerBbl: number) => kg / kgPerBbl / 1e6;
const fmt = (value: number, digits = 1) => value.toLocaleString("uk-UA", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const date = (t: number) => new Date(t).toLocaleString("uk-UA", { timeZone: "UTC", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

/** Years of the playback window, e.g. "2024" or "2024–2025". */
function windowLabel(data: PilotPayload): string {
  if (!data.window) return String(data.parameters.year);
  const first = data.window.from.slice(0, 4);
  const last = new Date(Date.parse(data.window.to) - 1).toISOString().slice(0, 4);
  return first === last ? first : `${first}–${last}`;
}

const SIDE_KEY = "aftertime.world.side";

function readSideOpen(): boolean {
  try {
    return window.localStorage.getItem(SIDE_KEY) !== "closed";
  } catch {
    return true;
  }
}

export default function WorldPlayback() {
  const context = useAppContext();
  const [data, setData] = useState<PilotPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(3);
  const pane = useContext(PaneContext);
  const [initial] = useState(() => tabParams(pane));
  const [selected, setSelected] = useState<string | null>(initial.get("entity"));
  const [tab, setTab] = useState<Tab>(initial.get("entity") ? "card" : "overview");
  const [filter, setFilter] = useState("");
  const [sideOpen, setSideOpen] = useState(readSideOpen);
  const toggleSide = (open: boolean) => {
    setSideOpen(open);
    try {
      window.localStorage.setItem(SIDE_KEY, open ? "open" : "closed");
    } catch {
      // Not persisted when storage is unavailable.
    }
  };
  // Choosing an object shows its card, so the panel opens.
  const select = (id: string) => { setSelected(id); setTab("card"); setSideOpen(true); };
  const selectRef = useRef(select);
  selectRef.current = select;
  const labelMarkers = useRef(new Map<string, HTMLElement>());
  const mapNode = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  useEffect(() => {
    map.current?.resize();
  }, [sideOpen]);
  const vesselMarkers = useRef(new Map<string, maplibregl.Marker>());

  useEffect(() => {
    const bounds = periodBounds(context.from, context.to);
    request<PilotPayload>(`/world/pilot?${new URLSearchParams({ from: bounds.from, to: bounds.to })}`, undefined, 60_000)
      .then((payload) => {
        setData(payload);
        const requested = Date.parse(initial.get("t") || "");
        setT(Number.isFinite(requested) ? requested : Date.parse(payload.events[0]?.t ?? `${payload.parameters.year}-01-01T00:00:00Z`));
      })
      .catch((reason) => setError(String(reason?.message || reason)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context.from, context.to]);

  const model = useMemo(() => {
    if (!data) return null;
    const routes: Record<string, LngLat[]> = {};
    for (const place of data.places) if (place.geometry?.type === "LineString") routes[place.id] = place.geometry.coordinates;
    const timeline = buildTimeline(data.events, data.portions.map((p) => p.id), data.initial);
    const sorted = [...data.events].sort((a, b) => Date.parse(a.t) - Date.parse(b.t));
    const start = timeline.times[0] ?? 0;
    const end = Math.max(timeline.times[timeline.times.length - 1] ?? 0, ...data.voyages.map((v) => Date.parse(v.arrive)));
    return { routes, timeline, sorted, start, end };
  }, [data]);

  // Map with static layers: deposit outline, sea lane, facilities.
  useEffect(() => {
    if (!data || !mapNode.current || map.current) return;
    const instance = new maplibregl.Map({
      container: mapNode.current,
      style: BASEMAP,
      center: [59.5, 24.6],
      zoom: 4.3,
      attributionControl: { compact: true },
    });
    map.current = instance;
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => {
      const features = data.places.filter((p) => p.geometry).map((p) => ({ type: "Feature" as const, geometry: p.geometry, properties: { id: p.id, type: p.type, kind: p.kind } }));
      instance.addSource("pilot", { type: "geojson", data: { type: "FeatureCollection", features } });
      instance.addLayer({ id: "deposit", type: "fill", source: "pilot", filter: ["==", ["get", "type"], "type:deposit"], paint: { "fill-color": "#f0bd63", "fill-opacity": 0.35 } });
      instance.addLayer({ id: "deposit-line", type: "line", source: "pilot", filter: ["==", ["get", "type"], "type:deposit"], paint: { "line-color": "#f0bd63", "line-width": 1.2 } });
      instance.addLayer({ id: "lane", type: "line", source: "pilot", filter: ["==", ["get", "type"], "type:sea-lane"], paint: { "line-color": "#64d8cb", "line-width": 1.6, "line-dasharray": [2, 2], "line-opacity": 0.8 } });
      instance.addLayer({ id: "facilities", type: "circle", source: "pilot", filter: ["==", ["get", "kind"], "asset"], paint: { "circle-radius": 6, "circle-color": "#b7f34a", "circle-stroke-color": "#07110e", "circle-stroke-width": 2 } });
      for (const layer of ["facilities", "deposit", "lane"]) {
        instance.on("click", layer, (event: maplibregl.MapLayerMouseEvent) => { const id = event.features?.[0]?.properties?.id; if (id) selectRef.current(String(id)); });
        instance.on("mouseenter", layer, () => { instance.getCanvas().style.cursor = "pointer"; });
        instance.on("mouseleave", layer, () => { instance.getCanvas().style.cursor = ""; });
      }
      for (const place of data.places) {
        const entry = FACILITY_LABELS[place.id];
        if (!entry || !place.geometry) continue;
        const [label, offset] = entry;
        const position: LngLat = place.geometry.type === "Polygon" ? [49.95, 25.2] : place.geometry.coordinates;
        const element = document.createElement("div");
        element.className = `world-label ${place.kind === "asset" ? "asset" : ""}`;
        element.textContent = label;
        element.addEventListener("click", () => selectRef.current(place.id));
        labelMarkers.current.set(place.id, element);
        new maplibregl.Marker({ element, anchor: "left", offset }).setLngLat(position).addTo(instance);
      }
    });
    return () => {
      instance.remove();
      map.current = null;
      vesselMarkers.current.clear();
    };
  }, [data]);

  // Clock.
  useEffect(() => {
    if (!playing || !model) return;
    let frame = 0, last = performance.now();
    const tick = (now: number) => {
      const elapsed = (now - last) / 1000;
      last = now;
      setT((current) => {
        const next = current + elapsed * speed * DAY;
        if (next >= model.end) { setPlaying(false); return model.end; }
        return next;
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, model]);

  const vessels = useMemo(() => (data && model ? vesselStates(data.voyages, model.routes, t) : []), [data, model, t]);

  // Vessel markers follow the clock.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !data) return;
    for (const state of vessels) {
      let marker = vesselMarkers.current.get(state.vessel);
      if (!marker) {
        const element = document.createElement("div");
        element.className = "world-vessel";
        element.innerHTML = `<i></i><span>${(data.names[state.vessel] || state.vessel).replace("Pilot ", "")}</span>`;
        const vesselId = state.vessel;
        element.addEventListener("click", () => selectRef.current(vesselId));
        marker = new maplibregl.Marker({ element, anchor: "center" }).setLngLat(state.position).addTo(instance);
        vesselMarkers.current.set(state.vessel, marker);
      }
      marker.setLngLat(state.position);
      marker.getElement().dataset.status = state.status;
      marker.getElement().classList.toggle("selected", state.vessel === selected);
    }
    for (const [id, element] of labelMarkers.current) element.classList.toggle("selected", id === selected);
  }, [vessels, data, selected]);

  // Keep the selection in the address so a card can be shared or reopened.
  useEffect(() => {
    const params = tabParams(pane);
    if (selected) params.set("entity", selected); else params.delete("entity");
    params.delete("t");
    replaceTabQuery(pane, params);
  }, [pane, selected]);

  if (error) return <div className="world-shell world-message">Не вдалося завантажити пілот: {error}</div>;
  if (!data || !model) return <div className="world-shell world-message">Завантаження пілоту…</div>;

  const kgPerBbl = data.parameters.kg_per_bbl as number;
  const balances = balancesAt(model.timeline, t);
  const portionOf = (holder: string, material = "type:arab-light") => data.portions.find((p) => p.holder === holder && p.material === material)?.id || "";
  const at = (holder: string, material?: string) => balances.get(portionOf(holder, material)) || 0;
  const produced = -at("place:ghawar");
  const afloat = vessels.reduce((sum, v) => sum + at(v.vessel), 0);
  const products = Object.keys(data.parameters.refinery_yields).map((material) => ({ material, kg: at("asset:jamnagar", material) }));
  const inIndia = at("asset:sikka") + at("asset:jamnagar") + products.reduce((s, p) => s + p.kg, 0);
  const recent: LedgerEvent[] = model.sorted.slice(Math.max(0, lastIndexAt(model.timeline.times, t) - 7), lastIndexAt(model.timeline.times, t) + 1).reverse();
  const estimate = data.estimate;
  const rows: [string, number][] = [
    ["Гавар → видобуто, усього", produced],
    ["Інші напрями (агрегат)", at("place:ghawar-other-offtake")],
    ["Абкайк, сховище", at("asset:abqaiq")],
    ["Рас-Танура, термінал", at("asset:ras-tanura")],
    ["На танкерах", afloat],
    ["Сікка, термінал", at("asset:sikka")],
    ["Джамнагар, сира нафта", at("asset:jamnagar")],
  ];

  return (
    <div className="world-shell">
      <header className="world-top">
        <div>
          <small>ПІЛОТ · БАЛАНС МАТЕРІЇ · НАБЛИЖЕННЯ</small>
          <b>Arab Light: Гавар → Джамнагар, {windowLabel(data)}</b>
        </div>
        <div className="world-top-right">
          <PeriodPicker />
          <a href="/world/entities" className="world-back">Усі сутності</a>
          <div className="world-clock">{date(t)} UTC</div>
        </div>
      </header>
      <div className={`world-body ${sideOpen ? "" : "side-closed"}`}>
        <div className="world-map" ref={mapNode} />
        <button
          className="world-side-toggle"
          onClick={() => toggleSide(!sideOpen)}
          title={sideOpen ? "Згорнути панель" : "Розгорнути панель"}
          aria-label={sideOpen ? "Згорнути панель" : "Розгорнути панель"}
          aria-expanded={sideOpen}
        >
          {sideOpen ? "»" : "«"}
        </button>
        <aside className="world-side" hidden={!sideOpen}>
          <div className="world-tabs">
            <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>Огляд</button>
            <button className={tab === "objects" ? "active" : ""} onClick={() => setTab("objects")}>Об'єкти · {data.objects.length}</button>
            <button className={tab === "card" ? "active" : ""} disabled={!selected} onClick={() => setTab("card")}>Картка</button>
          </div>
          {tab === "card" && selected && <EntityCard id={selected} at={t} onOpen={select} />}
          {tab === "objects" && (
            <div className="world-objects">
              <input type="search" placeholder="Фільтр об'єктів" value={filter} onChange={(e) => setFilter(e.target.value)} />
              {Object.entries(
                data.objects
                  .filter((o) => !filter || `${o.name} ${o.id}`.toLowerCase().includes(filter.toLowerCase()))
                  .reduce<Record<string, PilotObject[]>>((groups, o) => ({ ...groups, [o.kind]: [...(groups[o.kind] || []), o] }), {}),
              ).map(([kind, objects]) => (
                <section key={kind}>
                  <h3>{KIND_LABELS[kind] || kind} · {objects.length}</h3>
                  <ul className="world-list">
                    {objects.map((o) => (
                      <li key={o.id} className={`clickable ${o.id === selected ? "active" : ""}`} onClick={() => select(o.id)}>
                        <b>{o.name}</b>
                        <span>{o.type ? o.type.replace("type:", "") : o.id}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
          {tab === "overview" && <>
          <section>
            <h3>Запаси родовища</h3>
            {estimate ? (
              <p>
                Гавар, оцінка {estimate.evidence.class} ({estimate.evidence.system}) на {new Date(estimate.valid_time).toLocaleDateString("uk-UA")}:{" "}
                <b>{fmt(mbbl(estimate.value_kg, kgPerBbl) / 1000, 2)} млрд бар.</b>
                <br />
                <span className="world-muted">Мінус видобуток моделі: {fmt(mbbl(estimate.value_kg - produced, kgPerBbl) / 1000, 3)} млрд бар. (переоцінки запасів не враховано).</span>
              </p>
            ) : <p className="world-muted">Оцінки немає.</p>}
          </section>
          <section>
            <h3>Де нафта зараз</h3>
            <table className="world-table">
              <thead><tr><th /><th>млн бар.</th><th>млн т</th></tr></thead>
              <tbody>
                {rows.map(([label, kg]) => <tr key={label}><td>{label}</td><td>{fmt(mbbl(kg, kgPerBbl))}</td><td>{fmt(kg / 1e9, 2)}</td></tr>)}
                <tr className="world-total"><td>Доставлено в Індію, усього</td><td>{fmt(mbbl(inIndia, kgPerBbl))}</td><td>{fmt(inIndia / 1e9, 2)}</td></tr>
              </tbody>
            </table>
          </section>
          <section>
            <h3>Продукти Джамнагару, млн т</h3>
            <div className="world-products">
              {products.map((p) => <span key={p.material}><small>{data.names[p.material] || p.material}</small><b>{fmt(p.kg / 1e9, 2)}</b></span>)}
            </div>
          </section>
          <section>
            <h3>Танкери</h3>
            <ul className="world-list">
              {vessels.map((v) => (
                <li key={v.vessel} data-status={v.status} className="clickable" onClick={() => select(v.vessel)}>
                  <b>{data.names[v.vessel] || v.vessel}</b>
                  <span>{STATUS_LABELS[v.status]}{v.status === "laden" || v.status === "ballast" ? ` · ${Math.round(v.progress * 100)}%` : ""}</span>
                  <em>{fmt(mbbl(at(v.vessel), kgPerBbl))} млн бар.</em>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3>Журнал подій</h3>
            <ul className="world-list events">
              {recent.map((e) => {
                const moved = Math.max(0, ...e.postings.map(([, d]) => d));
                return (
                  <li key={e.id}>
                    <b>{EVENT_LABELS[e.type] || e.type}</b>
                    <span>{date(Date.parse(e.t))} · {e.provenance}</span>
                    <em>{moved ? `${fmt(mbbl(moved, kgPerBbl), 2)} млн бар.` : (data.names[e.attributes.vessel] || "").replace("Pilot ", "")}</em>
                  </li>
                );
              })}
            </ul>
          </section>
          <section className="world-notes">
            <h3>Припущення</h3>
            <ul>{(data.parameters.notes as string[]).map((note) => <li key={note}>{note}</li>)}</ul>
          </section>
          </>}
        </aside>
      </div>
      <footer className="world-transport">
        <button onClick={() => { if (t >= model.end) setT(model.start); setPlaying(!playing); }}>{playing ? "❚❚ Пауза" : "▶ Грати"}</button>
        <input type="range" min={model.start} max={model.end} step={3_600_000} value={t} onChange={(e) => setT(Number(e.target.value))} />
        <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
          {SPEEDS.map((s) => <option key={s} value={s}>{s} дн/с</option>)}
        </select>
      </footer>
    </div>
  );
}
