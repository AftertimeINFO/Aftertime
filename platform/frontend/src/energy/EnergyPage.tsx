import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type * as maplibregl from "maplibre-gl";
import { request } from "../api";
import { useAppContext } from "../appContext";
import { PaneContext, replaceTabQuery, tabParams, useTabs } from "../tabs";
import AssetInspector from "./AssetInspector";
import EnergyMap, { type MapHandle } from "./EnergyMap";
import { gridApi, type GridSummary } from "./energyApi";
import { fmtDate } from "./format";
import Legend from "./Legend";
import { DEFAULT_FILTERS, LAYER_IDS, type PowerFilters } from "./mapStyle";
import NetworkPanel from "./NetworkPanel";
import { frameAt, frameStates, nextEvent, runApi, type Frame, type Run, type Scenario, type SnapshotNetwork } from "./run";
import { KpiStrip, RunSummaryPanel } from "./RunView";
import ScenarioPanel, { type PickApi } from "./ScenarioPanel";
import SearchPalette from "./SearchPalette";
import Timeline from "./Timeline";
import "./energy.css";

type Mode = "network" | "replay" | "scenarios";
const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "network", label: "Мережа", hint: "Реальна інфраструктура: станції, підстанції, ЛЕП" },
  { id: "replay", label: "Відтворення", hint: "Історичні інциденти на реальній мережі" },
  { id: "scenarios", label: "Сценарії", hint: "Ймовірні інциденти майбутнього" },
];
const LINE_OPACITY_NORMAL = ["case", ["boolean", ["feature-state", "off"], false], 0.75, 0.92];
const LINE_OPACITY_SIMULATION = ["case", ["!=", ["feature-state", "load"], null], 0.95, ["boolean", ["feature-state", "off"], false], 0.85, 0.16];
const CAPS_KEY = "aftertime.energy.filters";

function readFilters(): PowerFilters {
  try {
    const stored = JSON.parse(window.localStorage.getItem(CAPS_KEY) || "null");
    return stored ? { ...DEFAULT_FILTERS, ...stored, kinds: { ...DEFAULT_FILTERS.kinds, ...stored.kinds } } : DEFAULT_FILTERS;
  } catch {
    return DEFAULT_FILTERS;
  }
}

/**
 * Energy system workspace. One map and one inspector for three modes, so the user does not
 * relearn the screen: Network (explore real infrastructure), Replay (historical incidents)
 * and Scenarios (future what-ifs). Runs play back on the same map with a timeline.
 */
export default function EnergyPage() {
  const context = useAppContext();
  const pane = useContext(PaneContext);
  const { active } = useTabs();
  const visible = active === pane || pane == null;
  const [initial] = useState(() => tabParams(pane));
  const [mode, setMode] = useState<Mode>(() => (MODES.some((m) => m.id === initial.get("mode")) ? (initial.get("mode") as Mode) : "network"));
  const [selected, setSelected] = useState<number | null>(() => Number(initial.get("asset")) || null);
  const [filters, setFilters] = useState<PowerFilters>(readFilters);
  const [summary, setSummary] = useState<GridSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [layers, setLayers] = useState<string[]>([]);
  const map = useRef<MapHandle>(null);

  // Runs.
  const [run, setRun] = useState<Run | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [network, setNetwork] = useState<SnapshotNetwork | null>(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);

  // Picking targets on the map for the scenario wizard.
  const pickHandler = useRef<((id: number) => void) | null>(null);
  const [picking, setPicking] = useState(false);
  // Stable for the whole page: effects that stop picking on unmount must not fire on every change.
  const pickApi: PickApi = useMemo(
    () => ({
      start: (onPick) => { pickHandler.current = onPick; setPicking(true); },
      stop: () => { pickHandler.current = null; setPicking(false); },
    }),
    [],
  );

  useEffect(() => {
    gridApi.summary().then(setSummary).catch((reason) => setSummaryError(String(reason?.message || reason)));
    request<{ items: { id: string; capabilities: string[] }[] }>("/layers")
      .then((r) => setLayers(r.items.find((l) => l.id === context.layer)?.capabilities ?? []))
      .catch(() => setLayers([]));
  }, [context.layer]);
  const canRun = layers.includes("grid.run");

  useEffect(() => {
    try {
      window.localStorage.setItem(CAPS_KEY, JSON.stringify(filters));
    } catch {
      // Filters are a convenience; storage may be unavailable.
    }
  }, [filters]);

  // Keep mode and selection in the tab address (shareable link).
  useEffect(() => {
    const params = new URLSearchParams();
    if (mode !== "network") params.set("mode", mode);
    if (selected) params.set("asset", String(selected));
    replaceTabQuery(pane, params);
  }, [mode, selected, pane]);

  const select = useCallback((id: number | null) => {
    if (id != null && pickHandler.current) {
      pickHandler.current(id);
      return;
    }
    setSelected(id);
  }, []);

  const focusAsset = useCallback((id: number) => {
    setSelected(id);
    gridApi.asset(id).then((card) => map.current?.flyTo(card.bbox, [card.lon, card.lat])).catch(() => undefined);
  }, []);

  const focusAssets = useCallback((ids: number[]) => {
    const points = ids.map((id) => scenario?.assets?.[id]).filter(Boolean) as { lon: number; lat: number }[];
    if (!points.length) return;
    const lons = points.map((p) => p.lon);
    const lats = points.map((p) => p.lat);
    map.current?.flyTo([Math.min(...lons) - 0.1, Math.min(...lats) - 0.1, Math.max(...lons) + 0.1, Math.max(...lats) + 0.1]);
  }, [scenario]);

  // Leaving the run modes clears the run from the map.
  const changeMode = (next: Mode) => {
    if (next === mode) return;
    setMode(next);
    pickApi.stop();
    if (next === "network" || (run && scenario && (next === "replay") !== (scenario.mode === "historical"))) {
      setRun(null);
      setScenario(null);
    }
  };

  // Poll a run while it is queued or running.
  const pending = run?.status === "queued" || run?.status === "running";
  useEffect(() => {
    if (!run || !pending) return;
    const timer = window.setInterval(() => runApi.run(run.id).then(setRun).catch(() => undefined), 1000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.id, pending]);

  // A finished run: load its frames and the index of its network.
  useEffect(() => {
    setFrames([]);
    setIndex(0);
    setPlaying(false);
    if (!run || run.status !== "completed" || run.kind === "criticality") return;
    let alive = true;
    Promise.all([runApi.frames(run.id), run.summary.snapshot_id ? runApi.network(run.summary.snapshot_id) : Promise.resolve(null)]).then(([f, n]) => {
      if (!alive) return;
      setFrames(f.items);
      setNetwork(n);
      // Start at the first event, where the story begins.
      const first = f.items.findIndex((x, i) => i > 0 && x.events.some((e) => e.origin === "scenario"));
      setIndex(first > 0 ? Math.max(0, first - 1) : 0);
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.id, run?.status]);

  const simulating = frames.length > 0 && network != null && mode !== "network";
  const plantAssets = useMemo(() => new Set((network?.buses ?? []).filter((b) => b[3] === "plant" && b[0] != null).map((b) => b[0] as number)), [network]);

  // Paint the shown frame onto the map.
  useEffect(() => {
    const handle = map.current;
    const instance = handle?.map();
    if (!handle || !instance || !instance.getLayer(LAYER_IDS.line)) return;
    handle.clearStates(["load", "off", "hit"]);
    instance.setPaintProperty(LAYER_IDS.line, "line-opacity", (simulating ? LINE_OPACITY_SIMULATION : LINE_OPACITY_NORMAL) as maplibregl.ExpressionSpecification);
    if (!simulating) return;
    const frame = frames[index];
    if (!frame) return;
    const states = frameStates(network!, frame, plantAssets);
    handle.setStates(states.lines, ["power_line"]);
    handle.setStates(states.substations, ["power_substation", "power_substation_area"]);
    handle.setStates(states.plants, ["power_plant", "power_plant_area", "power_generator"]);
  }, [simulating, frames, index, network, plantAssets]);

  // Playback clock.
  useEffect(() => {
    if (!playing || !frames.length) return;
    const timer = window.setInterval(() => {
      setIndex((i) => {
        if (i >= frames.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 1000 / speed);
    return () => window.clearInterval(timer);
  }, [playing, speed, frames.length]);

  // Keyboard: Ctrl+K search, Esc closes, Space plays, arrows jump between events.
  useEffect(() => {
    if (!visible) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
        return;
      }
      if (typing || searchOpen) return;
      if (event.key === "Escape") {
        if (pickHandler.current) pickApi.stop();
        else setSelected(null);
      } else if (frames.length && event.key === " ") {
        event.preventDefault();
        setPlaying((p) => !p);
      } else if (frames.length && (event.key === "ArrowRight" || event.key === "ArrowLeft") && !target.closest(".en-track")) {
        setIndex((i) => nextEvent(frames, i, event.key === "ArrowRight" ? 1 : -1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, frames, searchOpen, pickApi]);

  const seek = (at: string) => {
    if (frames.length) setIndex(frameAt(frames, Date.parse(at)));
  };
  const frame = frames[index] ?? null;
  const fresh = summary?.batches.filter((b) => b.status === "succeeded").map((b) => b.source_timestamp).filter(Boolean).sort()[0];
  const showRight = mode !== "network" || selected != null;

  return (
    <div className={`en-shell ${showRight ? "with-right" : ""} ${frames.length && mode !== "network" ? "with-timeline" : ""}`}>
      <header className="en-head">
        <div className="en-title">
          <h2>Енергосистема</h2>
          <small>{!summary ? "завантаження даних мережі…" : summary.imported ? `дані OSM станом на ${fresh ? fmtDate(fresh) : "—"}` : "мережу не імпортовано"}</small>
        </div>
        <div className="en-segmented" role="tablist" aria-label="Режим">
          {MODES.map((m) => (
            <button key={m.id} role="tab" aria-selected={mode === m.id} className={mode === m.id ? "active" : ""} onClick={() => changeMode(m.id)} title={m.hint}>
              {m.label}
            </button>
          ))}
        </div>
        <button className="en-search-trigger" onClick={() => setSearchOpen(true)} aria-label="Пошук об'єкта мережі (Ctrl+K)">
          <span aria-hidden="true">⌕</span> Пошук станції, підстанції, ЛЕП <kbd>Ctrl K</kbd>
        </button>
      </header>

      <aside className="en-left" aria-label="Панель режиму">
        {mode === "network" && <NetworkPanel summary={summary} filters={filters} onFilters={setFilters} onSelect={focusAsset} />}
        {mode !== "network" && (
          <ScenarioPanel
            key={mode}
            mode={mode === "replay" ? "historical" : "whatif"}
            canRun={canRun}
            activeRun={run}
            onRun={(r, s) => { setRun(r); if (s) setScenario(s); if (!r) setScenario(null); }}
            onSeek={seek}
            onFocusAssets={focusAssets}
            picking={pickApi}
          />
        )}
      </aside>

      <main className="en-map">
        <EnergyMap ref={map} filters={filters} selected={selected} onSelect={select} />
        {picking && <div className="en-pick-banner" role="status">Режим вибору цілей: клацніть об'єкт на мапі · Esc — завершити</div>}
        {simulating && frame && <KpiStrip frame={frame} previous={frames[index - 1]} />}
        <Legend simulation={simulating} />
        {summaryError && <div className="en-map-empty"><h3>Не вдалося завантажити дані мережі</h3><p>{summaryError}</p></div>}
        {summary && !summary.imported && (
          <div className="en-map-empty">
            <h3>Реальну мережу ще не імпортовано</h3>
            <p>Імпорт OpenStreetMap (дані як в Open Infrastructure Map) виконує адміністратор однією командою:</p>
            <code>docker compose --profile import run --rm osm-import --region ua,md,pl,sk,hu,ro,ru --fetch</code>
            <p className="en-muted">Після імпорту оновіть сторінку.</p>
          </div>
        )}
      </main>

      {showRight && (
        <aside className="en-right" aria-label="Інспектор">
          {selected != null ? (
            <AssetInspector
              id={selected}
              canEdit={canRun}
              onSelect={focusAsset}
              onFocus={(card) => map.current?.flyTo(card.bbox, [card.lon, card.lat])}
              onClose={() => setSelected(null)}
            />
          ) : (
            <RunSummaryPanel run={run} scenario={scenario} frame={frame} onSelectAsset={focusAsset} onSeek={seek} />
          )}
        </aside>
      )}

      {frames.length > 0 && mode !== "network" && (
        <footer className="en-bottom">
          <Timeline frames={frames} index={index} onIndex={(i) => { setIndex(i); }} playing={playing} onPlaying={setPlaying} speed={speed} onSpeed={setSpeed} bands={run?.summary.ensemble} />
        </footer>
      )}

      <SearchPalette open={searchOpen} onClose={() => setSearchOpen(false)} onPick={(item) => { setSelected(item.id); map.current?.flyTo(item.bbox, [item.lon, item.lat]); }} />
    </div>
  );
}
