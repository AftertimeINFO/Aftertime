/** Material balance of a scope over a period, as returned by GET /world/balance. */

export type BalanceLevel = "substance" | "molecular" | "element";
export type BalanceColumn = "opening" | "inflow" | "outflow" | "transform" | "carrier" | "closing" | "residual" | "internal";
export type BalanceValues = Record<BalanceColumn, number>;

export type BalanceBreakdown = { event_type: string } & Partial<Record<BalanceColumn, number>>;

export type BalanceRow = {
  id: string;
  name: string;
  symbol: string | null;
  depth: number;
  parent: string | null;
  group: boolean;
  values: BalanceValues;
  breakdown?: BalanceBreakdown[];
  molar_mass_g_per_mol?: number | null;
};

export type Balance = {
  scope: string;
  period: { from: string; to: string };
  level: BalanceLevel;
  levels: Record<BalanceLevel, boolean>;
  unit: "kg";
  columns: BalanceColumn[];
  rows: BalanceRow[];
  totals: BalanceValues;
  residual_ok: boolean;
  provenance: Record<string, number>;
  empty: boolean;
};

export type ScopeNode = { id: string; name: string; kind: string; children: ScopeNode[] };
export type ScopeAxis = { id: "geo" | "control"; name: string; roots: ScopeNode[] };
export type ScopeTree = { axes: ScopeAxis[] };

export const LEVELS: { id: BalanceLevel; label: string; hint: string }[] = [
  { id: "substance", label: "Речовини", hint: "Продукти та речовини, згруповані за класифікацією типів" },
  { id: "molecular", label: "Молекули", hint: "Молекулярний склад речовин" },
  { id: "element", label: "Елементи", hint: "Розклад речовин на хімічні елементи" },
];

/** Columns in trial balance order: opening balance, turnover, closing balance, control. */
export const COLUMNS: { id: BalanceColumn; label: string; hint: string; signed?: boolean }[] = [
  { id: "opening", label: "Сальдо на початок", hint: "Запас у межах scope на початок періоду" },
  { id: "inflow", label: "Надходження", hint: "Проведення з контрагентом поза scope, прихід" },
  { id: "outflow", label: "Вибуття", hint: "Проведення з контрагентом поза scope, витрата" },
  { id: "transform", label: "Трансформація", hint: "Перетворення одних матеріалів на інші всередині scope (переробка)", signed: true },
  { id: "carrier", label: "З носієм", hint: "Вантаж, що перетнув межу scope разом із судном, без проведення", signed: true },
  { id: "closing", label: "Сальдо на кінець", hint: "Запас у межах scope на кінець періоду" },
  { id: "residual", label: "Нев'язка", hint: "Те, чого журнал подій не пояснює (наприклад, нова оцінка запасу)", signed: true },
];

/** Rows to render: children of a collapsed group are hidden, at any depth. */
export function visibleRows(rows: BalanceRow[], collapsed: ReadonlySet<string>): BalanceRow[] {
  const hidden = new Set<string>();
  return rows.filter((row) => {
    if (row.parent && (collapsed.has(row.parent) || hidden.has(row.parent))) {
      hidden.add(row.id);
      return false;
    }
    return true;
  });
}

/** Groups deeper than `depth` start collapsed. */
export function collapsedBelow(rows: BalanceRow[], depth: number): Set<string> {
  return new Set(rows.filter((row) => row.group && row.depth >= depth).map((row) => row.id));
}

export type MassUnit = "t" | "kt" | "Mt";
export const MASS_UNITS: { id: MassUnit; label: string; kg: number }[] = [
  { id: "t", label: "т", kg: 1e3 },
  { id: "kt", label: "тис. т", kg: 1e6 },
  { id: "Mt", label: "млн т", kg: 1e9 },
];

/** Amount in the chosen unit, with a real minus sign; tiny float noise shows as 0. */
export function formatAmount(kg: number, unit: MassUnit, signed = false): string {
  const factor = MASS_UNITS.find((u) => u.id === unit)!.kg;
  const value = kg / factor;
  if (Math.abs(value) < 0.0005) return "0";
  const digits = Math.abs(value) >= 1000 ? 0 : Math.abs(value) >= 10 ? 1 : 3;
  const text = Math.abs(value).toLocaleString("uk-UA", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  if (value < 0) return `−${text}`;
  return signed ? `+${text}` : text;
}

/** Unit that keeps the scope total readable. */
export function suggestUnit(totals: BalanceValues): MassUnit {
  const largest = Math.max(Math.abs(totals.opening), Math.abs(totals.closing), Math.abs(totals.inflow), Math.abs(totals.outflow));
  if (largest >= 1e11) return "Mt";
  if (largest >= 1e8) return "kt";
  return "t";
}

/** Path from an axis root to the scope, for breadcrumbs. */
export function scopePath(tree: ScopeTree | null, id: string): { axis: ScopeAxis; path: ScopeNode[] } | null {
  if (!tree) return null;
  for (const axis of tree.axes) {
    const walk = (nodes: ScopeNode[], trail: ScopeNode[]): ScopeNode[] | null => {
      for (const node of nodes) {
        const next = [...trail, node];
        if (node.id === id) return next;
        const found = walk(node.children, next);
        if (found) return found;
      }
      return null;
    };
    const path = walk(axis.roots, []);
    if (path) return { axis, path };
  }
  return null;
}

/** Nodes of an axis whose name or id matches the query, with their paths. */
export function searchScopes(axis: ScopeAxis, query: string): { node: ScopeNode; path: ScopeNode[] }[] {
  const needle = query.trim().toLowerCase();
  const found: { node: ScopeNode; path: ScopeNode[] }[] = [];
  const walk = (nodes: ScopeNode[], trail: ScopeNode[]) => {
    for (const node of nodes) {
      if (!needle || node.name.toLowerCase().includes(needle) || node.id.toLowerCase().includes(needle)) found.push({ node, path: trail });
      walk(node.children, [...trail, node]);
    }
  };
  walk(axis.roots, []);
  return found;
}

export function firstScope(tree: ScopeTree | null): string | null {
  return tree?.axes.find((axis) => axis.roots.length)?.roots[0]?.id ?? null;
}
