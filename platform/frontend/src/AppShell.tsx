import { useEffect, useMemo, useRef, useState } from "react";
import { request } from "./api";
import { hrefWithLayer, setContext, useAppContext, type LayerId } from "./appContext";
import { TabPage } from "./pages";
import { HOME, PaneContext, activateTab, closeTab, openTab, openUrl, tabTitle, useTabs, type Tab, type TabKind } from "./tabs";
import VersionBadge from "./VersionBadge";

type LayerInfo = { id: LayerId; label: string; description: string; capabilities: string[]; available: boolean };

type NavItem = { kind: TabKind; label: string; glyph: string; needs?: string[]; children?: NavItem[] };

const NAV: NavItem[] = [
  { kind: "balance", label: "Баланс матерії", glyph: "Σ", needs: ["balance"] },
  {
    kind: "world",
    label: "Світ",
    glyph: "◍",
    needs: ["world"],
    children: [
      { kind: "world", label: "Програвання", glyph: "" },
      { kind: "entities", label: "Сутності", glyph: "" },
    ],
  },
  { kind: "lab", label: "Моделі", glyph: "⌬", needs: ["lab.edit", "lab.run"] },
  // Open in every layer: the page explains when a layer cannot compute.
  { kind: "compute", label: "Розрахунок світу", glyph: "◷" },
  // Open in every layer: PROD shows where its models came from.
  { kind: "promote", label: "Випуск моделей", glyph: "⇪" },
];

const GLYPH: Record<TabKind, string> = { balance: "Σ", world: "◍", entities: "◍", lab: "⌬", compute: "◷", promote: "⇪" };
const RAIL_KEY = "aftertime.rail";
const EARTH = { scope: "place:earth", scopeName: "Earth" };

/** Open a page from the menu: the general balance always in a new tab, other pages focused. */
function openFromMenu(kind: TabKind): void {
  openTab(kind === "balance" ? { kind, ...EARTH } : { kind });
}

/**
 * Common frame: layer, scope and period on top, sections on the left, and the open pages
 * as tabs. Scope and period in the top bar belong to the active tab.
 */
export default function AppShell() {
  const context = useAppContext();
  const { tabs, active } = useTabs();
  const activeTab = tabs.find((t) => t.id === active) ?? null;
  const [layers, setLayers] = useState<LayerInfo[]>([]);
  const [narrow, setNarrow] = useState(() => {
    try {
      return window.localStorage.getItem(RAIL_KEY) === "narrow";
    } catch {
      return false;
    }
  });
  // Pages are mounted on first view and kept while their tab is open.
  const [mounted, setMounted] = useState<Set<string>>(() => new Set(active ? [active] : []));
  useEffect(() => {
    setMounted((current) => {
      const open = new Set(tabs.map((t) => t.id));
      const next = new Set([...current].filter((id) => open.has(id)));
      if (active) next.add(active);
      return next.size === current.size && [...next].every((id) => current.has(id)) ? current : next;
    });
  }, [tabs, active]);
  useEffect(() => {
    request<{ items: LayerInfo[] }>("/layers").then((r) => setLayers(r.items)).catch(() => setLayers([]));
  }, []);
  // In-app links open in tabs instead of reloading the window.
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as HTMLElement | null)?.closest?.("a");
      if (!anchor || anchor.target || anchor.hasAttribute("download")) return;
      const href = anchor.getAttribute("href");
      if (!href || !href.startsWith("/") || href.startsWith("//") || href.startsWith("/api")) return;
      if (openUrl(href)) event.preventDefault();
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);
  const current = layers.find((l) => l.id === context.layer);
  const capabilities = new Set(current?.capabilities ?? ["balance", "world", "lab.edit", "lab.run"]);
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
  const kind = activeTab?.kind;

  return (
    <div className={`shell ${narrow ? "shell-narrow" : ""}`} data-layer={context.layer}>
      <header className="shell-top">
        <a
          className="shell-brand"
          href={hrefWithLayer("/")}
          onClick={(e) => {
            e.preventDefault();
            openFromMenu("balance");
          }}
        >
          <i />
          <span>
            <b>AFTERTIME</b>
            <small>WORLD MODEL</small>
          </span>
        </a>
        <LayerSwitch layers={layers} active={context.layer} />
        <div className="shell-top-spacer" />
        <div className="shell-top-right">
          <VersionBadge />
        </div>
      </header>
      <nav className="shell-rail" aria-label="Головне меню">
        {NAV.map((item) => {
          const allowed = !item.needs || item.needs.some((need) => capabilities.has(need));
          const isActive = kind === item.kind || !!item.children?.some((c) => c.kind === kind);
          return (
            <div key={item.label} className="shell-rail-group">
              <a
                className={`shell-rail-item ${isActive ? "active" : ""} ${allowed ? "" : "blocked"}`}
                href={allowed ? hrefWithLayer(HOME[item.kind]) : undefined}
                title={
                  !allowed
                    ? `${item.label}: недоступно в шарі ${current?.label ?? context.layer}`
                    : item.kind === "balance"
                      ? "Відкрити загальний баланс у новій вкладці"
                      : item.label
                }
                aria-disabled={!allowed}
                onClick={(e) => {
                  e.preventDefault();
                  if (allowed) openFromMenu(item.kind);
                }}
              >
                <span className="shell-glyph" aria-hidden="true">{item.glyph}</span>
                <span className="shell-label">{item.label}</span>
              </a>
              {isActive && allowed && !narrow && item.children?.map((child) => (
                <a
                  key={child.label}
                  className={`shell-rail-sub ${child.kind === kind ? "active" : ""}`}
                  href={hrefWithLayer(HOME[child.kind])}
                  onClick={(e) => {
                    e.preventDefault();
                    openFromMenu(child.kind);
                  }}
                >
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
      <div className="shell-content">
        <TabBar tabs={tabs} active={active} />
        <div className="shell-panes">
          {tabs.filter((t) => mounted.has(t.id)).map((tab) => (
            <PaneContext.Provider key={`${tab.id}:${tab.rev}`} value={tab.id}>
              <div className={`shell-pane ${tab.id === active ? "" : "inactive"}`} aria-hidden={tab.id !== active}>
                <TabPage kind={tab.kind} />
              </div>
            </PaneContext.Provider>
          ))}
          {!tabs.length && (
            <div className="shell-empty">Усі вкладки закрито. Оберіть розділ у меню ліворуч, щоб відкрити його у вкладці.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function TabBar({ tabs, active }: { tabs: Tab[]; active: string | null }) {
  const strip = useRef<HTMLDivElement>(null);
  useEffect(() => {
    strip.current?.querySelector<HTMLElement>(".shell-tab.active")?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [active]);
  if (!tabs.length) return null;
  return (
    <div className="shell-tabs" role="tablist" aria-label="Відкриті вкладки" ref={strip}>
      {tabs.map((tab) => {
        const title = tabTitle(tab);
        return (
          <div
            key={tab.id}
            role="tab"
            aria-selected={tab.id === active}
            className={`shell-tab kind-${tab.kind} ${tab.id === active ? "active" : ""}`}
            title={title}
            onClick={() => activateTab(tab.id)}
            onAuxClick={(e) => {
              if (e.button === 1) {
                e.preventDefault();
                closeTab(tab.id);
              }
            }}
          >
            <span className="shell-tab-glyph" aria-hidden="true">{GLYPH[tab.kind]}</span>
            <span className="shell-tab-title">{title}</span>
            <button
              className="shell-tab-close"
              aria-label={`Закрити: ${title}`}
              onClick={(e) => {
                e.stopPropagation();
                closeTab(tab.id);
              }}
            >
              ×
            </button>
          </div>
        );
      })}
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
