/** Labels and number formatting of the energy section (Ukrainian UI). */

export const KIND_LABEL: Record<string, string> = {
  line: "ЛЕП",
  minor_line: "Розподільна лінія",
  cable: "Кабель",
  substation: "Підстанція",
  converter: "Перетворювальна підстанція",
  plant: "Електростанція",
  generator: "Генератор",
};

export const STATUS_LABEL: Record<string, string> = {
  active: "Діє",
  construction: "Будується",
  proposed: "Проєкт",
  disused: "Не використовується",
  abandoned: "Покинуто",
  demolished: "Демонтовано",
  destroyed: "Зруйновано",
  damaged: "Пошкоджено",
  occupied: "Під окупацією",
};

export const FUEL_LABEL: Record<string, string> = {
  nuclear: "Атомна",
  coal: "Вугільна",
  gas: "Газова",
  oil: "Нафтова / дизель",
  hydro: "Гідро",
  wind: "Вітрова",
  solar: "Сонячна",
  biomass: "Біопаливо",
  waste: "Сміттєспалювальна",
  geothermal: "Геотермальна",
  storage: "Накопичувач",
};

/** Plant colours by fuel: distinct hues, checked against the dark basemap. */
export const FUEL_COLOR: Record<string, string> = {
  nuclear: "#d17bff",
  coal: "#b08968",
  gas: "#ff9f43",
  oil: "#e57373",
  hydro: "#4fc3f7",
  wind: "#aed581",
  solar: "#ffd54f",
  biomass: "#66bb6a",
  waste: "#bdbdbd",
  geothermal: "#ff7043",
  storage: "#4dd0e1",
};
export const FUEL_OTHER = "#9e9e9e";

/**
 * Voltage classes (kV lower bounds) and colours after Open Infrastructure Map, so the map
 * reads like the reference users know. Width grows with voltage as a second cue.
 */
export const VOLTAGE_CLASSES: { min: number; color: string; label: string }[] = [
  { min: 550, color: "#00c2ff", label: "≥ 550 кВ" },
  { min: 310, color: "#c86ac4", label: "310–549 кВ" },
  { min: 220, color: "#e04646", label: "220–309 кВ" },
  { min: 132, color: "#d9741a", label: "132–219 кВ" },
  { min: 52, color: "#c9b21a", label: "52–131 кВ" },
  { min: 25, color: "#55b555", label: "25–51 кВ" },
  { min: 10, color: "#6e97b8", label: "10–24 кВ" },
  { min: 0, color: "#8a8a96", label: "< 10 кВ / невідомо" },
];

export function voltageColor(kv: number | null | undefined): string {
  if (kv == null) return VOLTAGE_CLASSES[VOLTAGE_CLASSES.length - 1].color;
  return (VOLTAGE_CLASSES.find((c) => kv >= c.min) ?? VOLTAGE_CLASSES[VOLTAGE_CLASSES.length - 1]).color;
}

const nf = (digits: number) => new Intl.NumberFormat("uk-UA", { maximumFractionDigits: digits, minimumFractionDigits: 0 });

export function fmtNumber(value: number | null | undefined, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return nf(digits).format(value);
}

export function fmtKv(values: number[] | number | null | undefined): string {
  const list = Array.isArray(values) ? values : values == null ? [] : [values];
  if (!list.length) return "—";
  return list.map((v) => (v >= 1 ? fmtNumber(v) : fmtNumber(v, 2))).join(" / ") + " кВ";
}

/** Power in MW, switching to GW for large values. */
export function fmtMw(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 10_000) return `${fmtNumber(value / 1000, 1)} ГВт`;
  return `${fmtNumber(value, Math.abs(value) < 10 ? 1 : 0)} МВт`;
}

export function fmtEnergy(mwh: number | null | undefined): string {
  if (mwh == null || !Number.isFinite(mwh)) return "—";
  if (Math.abs(mwh) >= 1e6) return `${fmtNumber(mwh / 1e6, 2)} ТВт·год`;
  if (Math.abs(mwh) >= 1e3) return `${fmtNumber(mwh / 1e3, 1)} ГВт·год`;
  return `${fmtNumber(mwh, 0)} МВт·год`;
}

export function fmtCount(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1e6) return `${fmtNumber(value / 1e6, 2)} млн`;
  if (Math.abs(value) >= 1e4) return `${fmtNumber(value / 1e3, 0)} тис.`;
  return fmtNumber(value, 0);
}

export function fmtDateTime(value: string | number | Date | null | undefined): string {
  if (value == null) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("uk-UA", { timeZone: "Europe/Kyiv", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value.length === 10 ? `${value}T12:00:00Z` : value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("uk-UA", { timeZone: "Europe/Kyiv", day: "numeric", month: "long", year: "numeric" });
}

export function assetTitle(asset: { name?: string | null; name_en?: string | null; ref?: string | null; kind: string; max_voltage_kv?: number | null }): string {
  if (asset.name) return asset.name;
  if (asset.ref) return `${KIND_LABEL[asset.kind] ?? asset.kind} ${asset.ref}`;
  if (asset.name_en) return asset.name_en;
  const kv = asset.max_voltage_kv ? ` ${fmtNumber(asset.max_voltage_kv)} кВ` : "";
  return `${KIND_LABEL[asset.kind] ?? asset.kind}${kv} без назви`;
}

export const COUNTRY_LABEL: Record<string, string> = {
  UA: "Україна",
  MD: "Молдова",
  PL: "Польща",
  SK: "Словаччина",
  HU: "Угорщина",
  RO: "Румунія",
  RU: "Росія",
  BY: "Білорусь",
};
