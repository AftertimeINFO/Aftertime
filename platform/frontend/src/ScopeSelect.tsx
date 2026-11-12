import { useEffect, useMemo, useState } from "react";
import { request } from "./api";
import { useAppContext } from "./appContext";
import { firstScope, scopePath, searchScopes, type ScopeNode, type ScopeTree } from "./balance";
import { openTab, updateTab, usePaneTab } from "./tabs";

/**
 * Scope of one balance: shown in the balance itself and chosen in a dialog window.
 * Every balance tab keeps its own scope; changing it here does not touch other tabs.
 */

const KIND_LABEL: Record<string, string> = { place: "місце", asset: "об'єкт", actor: "актор", group: "усі" };

// One scope tree per layer, shared by all balance tabs.
const trees = new Map<string, Promise<ScopeTree>>();
function loadTree(layer: string): Promise<ScopeTree> {
  let tree = trees.get(layer);
  if (!tree) {
    tree = request<ScopeTree>("/world/scopes").catch(() => ({ axes: [] }));
    trees.set(layer, tree);
  }
  return tree;
}

export function ScopeBar() {
  const context = useAppContext();
  const tab = usePaneTab();
  const [tree, setTree] = useState<ScopeTree | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let live = true;
    loadTree(context.layer).then((value) => live && setTree(value));
    return () => {
      live = false;
    };
  }, [context.layer]);

  const found = useMemo(() => scopePath(tree, context.scope), [tree, context.scope]);
  // An object opened from its card may lie outside the scope tree (a vessel): keep it.
  const outside = !!tab?.scopeName && tab.scope === context.scope;
  const apply = (scope: string, scopeName?: string) => {
    if (tab) updateTab(tab.id, { scope, scopeName });
  };
  useEffect(() => {
    // A scope from another layer may not exist here: fall back to the first root.
    if (tree && !found && !outside) {
      const fallback = firstScope(tree);
      if (fallback && fallback !== context.scope) apply(fallback);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree, found, context.scope, outside]);
  // The tab title follows the scope.
  const foundName = found?.path[found.path.length - 1]?.name;
  useEffect(() => {
    if (tab && foundName && tab.scopeName !== foundName && tab.scope === context.scope) updateTab(tab.id, { scopeName: foundName });
  }, [tab, foundName, context.scope]);

  const empty = tree !== null && !tree.axes.some((a) => a.roots.length);

  return (
    <div className="balance-scope">
      <small>SCOPE · {found?.axis.name ?? (outside ? "об'єкт" : "—")}</small>
      <div className="balance-scope-line">
        <span className="balance-scope-path">
          {empty ? (
            <span className="scope-crumb-muted">У шарі ще немає сутностей</span>
          ) : found ? (
            found.path.map((node, index) => (
              <span key={node.id} className={index === found.path.length - 1 ? "scope-crumb-last" : "scope-crumb"}>
                {node.name}
              </span>
            ))
          ) : outside ? (
            <span className="scope-crumb-last">{tab?.scopeName}</span>
          ) : (
            <span className="scope-crumb-muted">…</span>
          )}
        </span>
        <button className="balance-scope-change" onClick={() => setOpen(true)} disabled={!tree || empty}>
          Змінити scope…
        </button>
      </div>
      {open && tree && (
        <ScopeDialog
          tree={tree}
          current={context.scope}
          initialAxis={found?.axis.id ?? "geo"}
          onChoose={(id, name) => {
            apply(id, name);
            setOpen(false);
          }}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}

function ScopeDialog({
  tree,
  current,
  initialAxis,
  onChoose,
  onClose,
}: {
  tree: ScopeTree;
  current: string;
  initialAxis: "geo" | "control";
  onChoose: (id: string, name: string) => void;
  onClose: () => void;
}) {
  const [axis, setAxis] = useState(initialAxis);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const currentAxis = tree.axes.find((a) => a.id === axis);
  const matches = currentAxis && query.trim() ? searchScopes(currentAxis, query) : null;
  const openNew = (id: string, name: string) => {
    openTab({ kind: "balance", scope: id, scopeName: name });
    onClose();
  };

  return (
    <div className="scope-dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="scope-dialog" role="dialog" aria-modal="true" aria-label="Scope балансу">
        <header>
          <div>
            <small>SCOPE БАЛАНСУ</small>
            <b>Оберіть місце, актив або актора</b>
          </div>
          <button className="scope-dialog-close" onClick={onClose} aria-label="Закрити">
            ×
          </button>
        </header>
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
                <ScopeRow
                  key={`${path.map((p) => p.id).join("/")}/${node.id}`}
                  node={node}
                  depth={0}
                  note={path.map((p) => p.name).join(" › ") || "корінь"}
                  current={current}
                  onChoose={onChoose}
                  onOpenNew={openNew}
                />
              ))
            : currentAxis?.roots.map((root) => (
                <ScopeBranch key={root.id} node={root} depth={0} current={current} onChoose={onChoose} onOpenNew={openNew} trail="" />
              ))}
          {matches && !matches.length && <p className="scope-empty">Нічого не знайдено.</p>}
          {currentAxis && !currentAxis.roots.length && <p className="scope-empty">На цій осі ще немає вузлів.</p>}
        </div>
        <footer>
          <span>Клік — показати в цьому балансі · ↗ — відкрити окремий баланс у новій вкладці</span>
          <button onClick={onClose}>Скасувати</button>
        </footer>
      </div>
    </div>
  );
}

type RowProps = {
  node: ScopeNode;
  depth: number;
  current: string;
  onChoose: (id: string, name: string) => void;
  onOpenNew: (id: string, name: string) => void;
};

function ScopeRow({ node, depth, current, onChoose, onOpenNew, note }: RowProps & { note?: string }) {
  return (
    <div className={`scope-row kind-${node.kind} ${node.id === current ? "active" : ""}`}>
      <button className="scope-row-main" style={{ paddingLeft: 10 + depth * 14 }} onClick={() => onChoose(node.id, node.name)}>
        <b>{node.name}</b>
        <span>{note ?? KIND_LABEL[node.kind] ?? node.kind}</span>
      </button>
      <button className="scope-row-new" title={`Відкрити баланс «${node.name}» у новій вкладці`} onClick={() => onOpenNew(node.id, node.name)}>
        ↗
      </button>
    </div>
  );
}

function ScopeBranch(props: RowProps & { trail: string }) {
  const { node, depth, trail } = props;
  const key = `${trail}/${node.id}`;
  return (
    <>
      <ScopeRow {...props} />
      {node.children.map((child) => (
        <ScopeBranch key={`${key}/${child.id}`} {...props} node={child} depth={depth + 1} trail={key} />
      ))}
    </>
  );
}
