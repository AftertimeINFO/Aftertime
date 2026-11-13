import { request } from "../api";
import { getContext } from "../appContext";

const API = import.meta.env.VITE_API_URL || "/api/v1";

export type CountrySummary = { country: string; line?: number; cable?: number; substation?: number; plant?: number; generator?: number; plant_mw?: number; line_km?: number };
export type ImportBatch = { id: number; region: string; source_url: string; source_timestamp: string | null; status: string; counts: Record<string, number>; finished_at: string | null };
export type GridSummary = { imported: boolean; countries: CountrySummary[]; batches: ImportBatch[]; bounds: [number, number, number, number] | null; licence?: string; attribution: string };

export type SearchItem = {
  id: number; kind: string; subkind: string | null; name: string | null; name_en: string | null; ref: string | null;
  max_voltage_kv: number | null; capacity_mw: number | null; fuel: string | null; country: string | null; status: string;
  lon: number; lat: number; bbox: [number, number, number, number];
};

export type AssetLink = { id: number; kind: string; name: string | null; max_voltage_kv: number | null; status: string; circuits?: number | null; length_km?: number | null; side?: string; distance_m?: number; subkind?: string | null };
export type Override = { id: number; asset_id: number; field: string; value: unknown; valid_from: string | null; valid_to: string | null; source_url: string; note: string; author: string; created_at: string };

export type AssetCard = SearchItem & {
  osm_type: string; osm_id: number; operator: string | null; voltages_kv: number[]; frequency_hz: number | null;
  circuits: number | null; cables: number | null; capacity_source: string | null; start_date: string | null;
  length_km: number | null; tags: Record<string, string>; quality: string[]; geometry_type: string; updated_at: string;
  lines?: AssetLink[]; ends?: AssetLink[]; nearby?: AssetLink[]; overrides: Override[];
  source: { url: string; licence: string; attribution: string };
};

export type QualityItem = { flag: string; kind: string; n: number; sample: number[]; label: string };

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

export const gridApi = {
  summary: () => request<GridSummary>("/grid/summary"),
  search: (q: string, signal?: AbortSignal) => request<{ items: SearchItem[] }>(`/grid/search?${new URLSearchParams({ q })}`, { signal }),
  asset: (id: number) => request<AssetCard>(`/grid/assets/${id}`),
  quality: () => request<{ items: QualityItem[] }>("/grid/quality"),
  overrideFields: () => request<{ fields: Record<string, string> }>("/grid/overrides?asset_id=0"),
  createOverride: (body: Record<string, unknown>) => request<Override>("/grid/overrides", json("POST", body)),
  deleteOverride: (id: number) => request<{ deleted: number }>(`/grid/overrides/${id}`, json("DELETE")),
};

/** Absolute tile URL template for MapLibre; the layer travels as a query parameter. */
export function tilesUrl(): string {
  const base = API.startsWith("http") ? API : `${window.location.origin}${API}`;
  return `${base}/grid/tiles/{z}/{x}/{y}.pbf?layer=${getContext().layer}`;
}
