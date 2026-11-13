import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { tilesUrl } from "./energyApi";
import { INTERACTIVE_LAYERS, POWER_SOURCE, applyFilters, powerLayers, type PowerFilters } from "./mapStyle";

maplibregl.setWorkerUrl(mapWorkerUrl);

/** Quiet dark basemap (OpenFreeMap, OpenMapTiles schema) so the grid stays the subject. */
const BASEMAP: maplibregl.StyleSpecification = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: { omt: { type: "vector", url: "https://tiles.openfreemap.org/planet" } },
  layers: [
    { id: "land", type: "background", paint: { "background-color": "#0d1a16" } },
    { id: "landcover", type: "fill", source: "omt", "source-layer": "landcover", paint: { "fill-color": "#10201a", "fill-opacity": 0.6 } },
    { id: "urban", type: "fill", source: "omt", "source-layer": "landuse", filter: ["in", ["get", "class"], ["literal", ["residential", "industrial", "commercial"]]], minzoom: 6, paint: { "fill-color": "#16271f", "fill-opacity": 0.7 } },
    { id: "water", type: "fill", source: "omt", "source-layer": "water", paint: { "fill-color": "#071722" } },
    { id: "rivers", type: "line", source: "omt", "source-layer": "waterway", minzoom: 6, paint: { "line-color": "#0b2433", "line-width": 1 } },
    { id: "roads", type: "line", source: "omt", "source-layer": "transportation", minzoom: 7, filter: ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary"]]], paint: { "line-color": "#1d3029", "line-width": ["interpolate", ["linear"], ["zoom"], 7, 0.5, 12, 2] } },
    { id: "admin1", type: "line", source: "omt", "source-layer": "boundary", minzoom: 5, filter: ["all", ["==", ["get", "admin_level"], 4], ["!=", ["get", "maritime"], 1]], paint: { "line-color": "#2a453a", "line-width": 0.6, "line-dasharray": [3, 2] } },
    { id: "countries", type: "line", source: "omt", "source-layer": "boundary", filter: ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]], paint: { "line-color": "#4a7464", "line-width": 1.1 } },
    {
      id: "places",
      type: "symbol",
      source: "omt",
      "source-layer": "place",
      filter: ["in", ["get", "class"], ["literal", ["city", "town"]]],
      minzoom: 5,
      layout: { "text-field": ["coalesce", ["get", "name:uk"], ["get", "name"]], "text-font": ["Noto Sans Regular"], "text-size": ["interpolate", ["linear"], ["zoom"], 5, 10, 10, 13] },
      paint: { "text-color": "#6f8a80", "text-halo-color": "#0d1a16", "text-halo-width": 1.2 },
    },
  ],
};

export type FeatureRef = { id: number; layer: string };
export type MapHandle = {
  flyTo: (bbox: [number, number, number, number] | null, point?: [number, number]) => void;
  setStates: (states: Map<number, Record<string, unknown>>, layers: string[]) => void;
  clearStates: (keys: string[]) => void;
  map: () => maplibregl.Map | null;
};

type Props = {
  filters: PowerFilters;
  selected: number | null;
  onSelect: (id: number | null) => void;
  initialView?: { center: [number, number]; zoom: number };
  onReady?: () => void;
};

const SOURCE_LAYERS = ["power_line", "power_substation", "power_substation_area", "power_plant", "power_plant_area", "power_generator"];

/** MapLibre map with the power layers; selection and hover via feature-state. */
const EnergyMap = forwardRef<MapHandle, Props>(function EnergyMap({ filters, selected, onSelect, initialView, onReady }, ref) {
  const node = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const hover = useRef<number | null>(null);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const stateKeys = useRef<Map<number, string[]>>(new Map());

  const setOn = (id: number, state: Record<string, unknown>, layers = SOURCE_LAYERS) => {
    const instance = map.current;
    if (!instance || !ready.current) return;
    for (const sourceLayer of layers) instance.setFeatureState({ source: POWER_SOURCE, sourceLayer, id }, state);
  };

  useEffect(() => {
    if (!node.current || map.current) return;
    const instance = new maplibregl.Map({
      container: node.current,
      style: BASEMAP,
      center: initialView?.center ?? [31.2, 48.6],
      zoom: initialView?.zoom ?? 5.3,
      minZoom: 2,
      maxZoom: 17,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    });
    instance.touchZoomRotate.disableRotation();
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    instance.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    map.current = instance;
    instance.on("load", () => {
      const { source, layers } = powerLayers(tilesUrl());
      instance.addSource(POWER_SOURCE, source);
      for (const layer of layers) instance.addLayer(layer);
      ready.current = true;
      applyFilters(instance, filtersRef.current);
      onReady?.();
    });
    const pick = (point: maplibregl.Point): maplibregl.MapGeoJSONFeature | null => {
      // Thin lines need a generous hit area (8 px), points still win over lines below.
      const box: [maplibregl.PointLike, maplibregl.PointLike] = [[point.x - 8, point.y - 8], [point.x + 8, point.y + 8]];
      const layers = INTERACTIVE_LAYERS.filter((id) => instance.getLayer(id) && instance.getLayoutProperty(id, "visibility") !== "none");
      const features = instance.queryRenderedFeatures(box, { layers });
      // Points beat lines, lines beat areas: the order of INTERACTIVE_LAYERS.
      features.sort((a, b) => INTERACTIVE_LAYERS.indexOf(a.layer.id as never) - INTERACTIVE_LAYERS.indexOf(b.layer.id as never));
      return features[0] ?? null;
    };
    instance.on("mousemove", (event) => {
      const feature = pick(event.point);
      const id = feature ? Number(feature.id) : null;
      instance.getCanvas().style.cursor = id != null ? "pointer" : "";
      if (id === hover.current) return;
      if (hover.current != null) setOn(hover.current, { hover: false });
      hover.current = id;
      if (id != null) setOn(id, { hover: true });
    });
    instance.on("mouseout", () => {
      if (hover.current != null) setOn(hover.current, { hover: false });
      hover.current = null;
    });
    instance.on("click", (event) => {
      const feature = pick(event.point);
      selectRef.current(feature ? Number(feature.id) : null);
    });
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(node.current);
    return () => {
      observer.disconnect();
      instance.remove();
      map.current = null;
      ready.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (map.current && ready.current) applyFilters(map.current, filters);
  }, [filters]);

  const previous = useRef<number | null>(null);
  useEffect(() => {
    if (previous.current != null) setOn(previous.current, { selected: false });
    if (selected != null) setOn(selected, { selected: true });
    previous.current = selected;
  }, [selected]);

  useImperativeHandle(ref, () => ({
    flyTo(bbox, point) {
      const instance = map.current;
      if (!instance) return;
      if (bbox && (bbox[2] - bbox[0] > 0.01 || bbox[3] - bbox[1] > 0.01)) {
        instance.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 80, maxZoom: 13, duration: 900 });
      } else if (point) {
        instance.flyTo({ center: point, zoom: Math.max(instance.getZoom(), 12), duration: 900 });
      }
    },
    setStates(states, layers) {
      for (const [id, state] of states) {
        setOn(id, state, layers);
        stateKeys.current.set(id, [...new Set([...(stateKeys.current.get(id) ?? []), ...Object.keys(state)])]);
      }
    },
    clearStates(keys) {
      const instance = map.current;
      if (!instance || !ready.current) return;
      for (const [id, has] of stateKeys.current) {
        for (const key of has.filter((k) => keys.includes(k))) {
          for (const sourceLayer of SOURCE_LAYERS) instance.removeFeatureState({ source: POWER_SOURCE, sourceLayer, id }, key);
        }
        const left = has.filter((k) => !keys.includes(k));
        if (left.length) stateKeys.current.set(id, left);
        else stateKeys.current.delete(id);
      }
    },
    map: () => map.current,
  }));

  return <div className="en-map-canvas" ref={node} />;
});

export default EnergyMap;
