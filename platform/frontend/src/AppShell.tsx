import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { request } from "./api";
import { hrefWithLayer, quarterPeriod, setContext, useAppContext, yearPeriod, type LayerId } from "./appContext";
import { firstScope, scopePath, searchScopes, type ScopeNode, type ScopeTree } from "./balance";
import VersionBadge from "./VersionBadge";

type LayerInfo = { id: LayerId; label: string; description: string; capabilities: string[]; available: boolean };

type NavItem = { href: string; label: string; glyph: string; match: (path: string) => boolean; needs?: string[]; children?: NavItem[] };

const NAV: NavItem[] = [
  { href: "/", label: "Баланс матерії", glyph: "Σ", match: (p) => p === "/" || p === "/balance", needs: ["balance"] },
  {
    href: "/world",
    label: "Світ",
    glyph: "◍",
    match: (p) => p.startsWith("/world"),
    needs: ["world"],
    children: [
      { href: "/world", label: "Програвання", glyph: "", match: (p) => p === "/world" || p === "/world/" },
      { href: "/world/entities", label: "Сутності", glyph: "", match: (p) => p.startsWith("/world/entities") },
    ],
  },
  { href: "/lab", label: "Моделі", glyph: "⌬", match: (p) => p.startsWith("/lab"), needs: ["lab.edit", "lab.run"] },
];

const RAIL_KEY = "aftertime.rail";

/** Common frame of every page: layer, scope and period on top, sections on the left. */
export default function AppShell({ children, usesScope = false }: { children: ReactNode; usesScope?: boolean }) {
  const context = useAppContext();
  const [layers, setLayers] = useState<LayerInfo[]>([]);
  const [narrow, setNarrow] = useState(() => {
    try {
      return window.localStorage.getItem(RAIL_KEY) === "narrow";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    request<{ items: LayerInfo[] }>("/layers").then((r) => setLayers(r.items)).catch(() => setLayers([]));
  }, []);
  const current = layers.find((l) => l.id === context.layer);
  const capabilities = new Set(current?.capabilities ?? ["balance", "world", "lab.edit", "lab.run"]);
  const path = window.location.pathname;
  const toggleRail = () => {
    setNarrow((value) => {
      try {
        window.localStorage.setItem(RAIL_KEY, value ? "wide" : "narrow");
      } catch {
        // Not persisted when storage is unavailable.
      }
      return !value;
    });
  };

  return (
    <div className={`shell ${narrow ? "shell-narrow" : ""}`} data-layer={context.layer}>
      <header className="shell-top">
        <a className="shell-brand" href={hrefWithLayer("/")}>
          <i />
          <span>
            <b>AFTERTIME</b>
            <small>WORLD MODEL</small>
          </span>
        </a>
        <LayerSwitch layers={layers} active={context.layer} />
        <ScopePicker active={usesScope} />
        <PeriodPicker active={usesScope} />
        <div className="shell-top-right">
          <VersionBadge />
        </div>
      </header>
      <nav className="shell-rail" aria-label="Головне меню">
        {NAV.map((item) => {
          const allowed = !item.needs || item.needs.some((need) => capabilities.has(need));
          const active = item.match(path);
          return (
            <div key={item.href} className="shell-rail-group">
              <a
                className={`shell-rail-item ${active ? "active" : ""} ${allowed ? "" : "blocked"}`}
                href={allowed ? hrefWithLayer(item.href) : undefined}
                title={allowed ? item.label : `${item.label}: недоступно в шарі ${current?.label ?? context.layer}`}
                aria-disabled={!allowed}
              >
                <span className="shell-glyph" aria-hidden="true">{item.glyph}</span>
                <span className="shell-label">{item.label}</span>
              </a>
              {active && allowed && !narrow && item.children?.map((child) => (
                <a key={child.href} className={`shell-rail-sub ${child.match(path) ? "active" : ""}`} href={hrefWithLayer(child.href)}>
                  {child.label}
                </a>
              ))}
            </div>
          );
        })}
        <button className="shell-rail-toggle" onClick={toggleRail} title={narrow ? "Розгорнути меню" : "Згорнути меню"}>
          {narrow ? "»" : "«"}
        </button>
      </nav>
      <div className="shell-content">{children}</div>
    </div>
  );
}

function LayerSwitch({ layers, active }: { layers: LayerInfo[]; active: LayerId }) {
  const items: LayerInfo[] = layers.length
    ? layers
    : (["dev", "preprod", "prod"] as LayerId[]).map((id) => ({ id, label: id === "preprod" ? "prePROD" : id.toUpperCase(), description: "", capabilities: [], available: true }));
  return (
    <div className="layer-switch" role="radiogroup" aria-label="Шар моделі">
      {items.map((layer) => (
        <button
          key={layer.id}
          role="radio"
          aria-checked={layer.id === active}
          data-layer={layer.id}
          className={layer.id === active ? "active" : ""}
          title={`${layer.description}${layer.available ? "" : " · база даних недоступна"}`}
          onClick={() => layer.id !== active && setContext({ layer: layer.id })}
        >
          {layer.label}
          {!layer.available && <em>!</em>}
        </button>
      ))}
    </div>
  );
}

function ScopePicker({ active }: { active: boolean }) {
  const context = useAppContext();
  const [tree, setTree] = useState<ScopeTree | null>(null);
  const [open, setOpen] = useState(false);
  const [axis, setAxis] = useState<"geo" | "control">("geo");
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    request<ScopeTree>("/world/scopes").then(setTree).catch(() => setTree({ axes: [] }));
  }, []);
  const found = useMemo(() => scopePath(tree, context.scope), [tree, context.scope]);
  useEffect(() => {
    // A scope from another layer may not exist here: fall back to the first root.
    if (tree && !found) {
      const fallback = firstScope(tree);
      if (fallback && fallback !== context.scope) setContext({ scope: fallback });
    }
  }, [tree, found, context.scope]);
  useEffect(() => {
    if (found) setAxis(found.axis.id);
  }, [found]);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const empty = tree !== null && !tree.axes.some((a) => a.roots.length);
  const currentAxis = tree?.axes.find((a) => a.id === axis);
  const matches = currentAxis && query.trim() ? searchScopes(currentAxis, query) : null;
  const choose = (id: string) => {
    setContext({ scope: id });
    setOpen(false);
    setQuery("");
  };

  return (
    <div className={`scope-picker ${active ? "" : "inactive"}`} ref={box} title={active ? "" : "Scope застосовується до балансу матерії"}>
      <small>SCOPE · {found?.axis.name ?? "—"}</small>
      <button className="scope-current" onClick={() => setOpen(!open)} disabled={empty}>
        {empty ? (
          <span className="scope-crumb-muted">У шарі ще немає сутностей</span>
        ) : found ? (
          found.path.map((node, index) => (
            <span key={node.id} className={index === found.path.length - 1 ? "scope-crumb-last" : "scope-crumb"}>
              {node.name}
            </span>
          ))
        ) : (
          <span className="scope-crumb-muted">…</span>
        )}
        <i aria-hidden="true">▾</i>
      </button>
      {open && tree && (
        <div className="scope-panel">
          <div className="scope-axes">
            {tree.axes.map((a) => (
              <button key={a.id} className={a.id === axis ? "active" : ""} onClick={() => setAxis(a.id)}>
                {a.name}
              </button>
            ))}
          </div>
          <input type="search" autoFocus placeholder="Пошук: країна, регіон, компанія, об'єкт" value={query} onChange={(e) => setQuery(e.target.value)} />
          <div className="scope-tree">
            {matches
              ? matches.map(({ node, path }) => (
                  <button key={`${path.map((p) => p.id).join("/")}/${node.id}`} className={node.id === context.scope ? "active" : ""} onClick={() => choose(node.id)}>
                    <b>{node.name}</b>
                    <span>{path.map((p) => p.name).join(" › ") || "корінь"}</span>
                  </button>
                ))
              : currentAxis?.roots.map((root) => <ScopeBranch key={root.id} node={root} depth={0} active={context.scope} choose={choose} trail="" />)}
            {currentAxis && !currentAxis.roots.length && <p className="scope-empty">На цій осі ще немає вузлів.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

function ScopeBranch({ node, depth, active, choose, trail }: { node: ScopeNode; depth: number; active: string; choose: (id: string) => void; trail: string }) {
  const key = `${trail}/${node.id}`;
  return (
    <>
      <button key={key} className={`scope-node kind-${node.kind} ${node.id === active ? "active" : ""}`} style={{ paddingLeft: 10 + depth * 14 }} onClick={() => choose(node.id)}>
        <b>{node.name}</b>
        <span>{KIND_LABEL[node.kind] ?? node.kind}</span>
      </button>
      {node.children.map((child) => (
        <ScopeBranch key={`${key}/${child.id}`} node={child} depth={depth + 1} active={active} choose={choose} trail={key} />
      ))}
    </>
  );
}

const KIND_LABEL: Record<string, string> = { place: "місце", asset: "об'єкт", actor: "актор", group: "усі" };

function PeriodPicker({ active }: { active: boolean }) {
  const context = useAppContext();
  const thisYear = new Date().getUTCFullYear();
  const years = Array.from({ length: thisYear - 2019 }, (_, i) => thisYear - i);
  const presets = years.flatMap((year) => [
    { id: `${year}`, label: `${year} рік`, ...yearPeriod(year) },
    ...([1, 2, 3, 4] as const).map((q) => ({ id: `${year}-q${q}`, label: `${year} · Q${q}`, ...quarterPeriod(year, q) })),
  ]);
  const preset = presets.find((p) => p.from === context.from && p.to === context.to)?.id ?? "";
  return (
    <div className={`period-picker ${active ? "" : "inactive"}`} title={active ? "" : "Період застосовується до балансу матерії"}>
      <small>ПЕРІОД</small>
      <div>
        <select aria-label="Готовий період" value={preset} onChange={(e) => {
          const chosen = presets.find((p) => p.id === e.target.value);
          if (chosen) setContext({ from: chosen.from, to: chosen.to });
        }}>
          <option value="">довільний</option>
          {presets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        <input type="date" aria-label="Початок періоду" value={context.from} max={context.to} onChange={(e) => e.target.value && setContext({ from: e.target.value })} />
        <span>—</span>
        <input type="date" aria-label="Кінець періоду" value={context.to} min={context.from} onChange={(e) => e.target.value && setContext({ to: e.target.value })} />
      </div>
    </div>
  );
}
