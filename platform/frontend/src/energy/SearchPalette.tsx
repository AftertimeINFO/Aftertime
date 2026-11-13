import { useEffect, useRef, useState } from "react";
import { gridApi, type SearchItem } from "./energyApi";
import { COUNTRY_LABEL, FUEL_COLOR, FUEL_LABEL, FUEL_OTHER, KIND_LABEL, assetTitle, fmtKv, fmtMw, voltageColor } from "./format";

type Props = { open: boolean; onClose: () => void; onPick: (item: SearchItem) => void };

/** Ctrl+K palette: find a plant, substation or line by name or dispatch name. */
export default function SearchPalette({ open, onClose, onPick }: Props) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SearchItem[]>([]);
  const [cursor, setCursor] = useState(0);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setCursor(0);
      window.setTimeout(() => input.current?.select(), 0);
    }
  }, [open]);

  useEffect(() => {
    if (query.trim().length < 2) {
      setItems([]);
      setState("idle");
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setState("loading");
      gridApi
        .search(query.trim(), controller.signal)
        .then((r) => { setItems(r.items); setCursor(0); setState("idle"); })
        .catch(() => !controller.signal.aborted && setState("error"));
    }, 220);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query]);

  if (!open) return null;
  const pick = (item: SearchItem | undefined) => {
    if (!item) return;
    onPick(item);
    onClose();
  };
  return (
    <div className="en-palette-backdrop" onMouseDown={onClose}>
      <div className="en-palette" role="dialog" aria-modal="true" aria-label="Пошук об'єкта мережі" onMouseDown={(e) => e.stopPropagation()}>
        <input
          ref={input}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Назва станції, підстанції чи ЛЕП…"
          aria-label="Пошук"
          role="combobox"
          aria-expanded={items.length > 0}
          aria-controls="en-palette-list"
          aria-activedescendant={items[cursor] ? `en-opt-${items[cursor].id}` : undefined}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            else if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(c + 1, items.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
            else if (e.key === "Enter") pick(items[cursor]);
          }}
        />
        <ul id="en-palette-list" role="listbox" className="en-palette-list">
          {items.map((item, index) => {
            const isPlant = item.kind === "plant";
            const color = isPlant ? FUEL_COLOR[item.fuel ?? ""] ?? FUEL_OTHER : voltageColor(item.max_voltage_kv);
            return (
              <li
                key={item.id}
                id={`en-opt-${item.id}`}
                role="option"
                aria-selected={index === cursor}
                className={index === cursor ? "active" : ""}
                onMouseEnter={() => setCursor(index)}
                onClick={() => pick(item)}
              >
                <i className={`en-swatch ${isPlant ? "round" : ""}`} style={{ background: color }} aria-hidden="true" />
                <span className="en-palette-name">{assetTitle(item)}</span>
                <small>
                  {[KIND_LABEL[item.kind], isPlant ? [FUEL_LABEL[item.fuel ?? ""], fmtMw(item.capacity_mw)].filter(Boolean).join(", ") : fmtKv(item.max_voltage_kv), COUNTRY_LABEL[item.country ?? ""] ?? item.country]
                    .filter(Boolean)
                    .join(" · ")}
                </small>
              </li>
            );
          })}
        </ul>
        <p className="en-palette-foot">
          {state === "loading" ? "Пошук…" : state === "error" ? "Пошук не вдався — спробуйте ще раз" : query.trim().length < 2 ? "Введіть щонайменше 2 літери" : items.length ? "↑↓ вибір · Enter відкрити · Esc закрити" : "Нічого не знайдено"}
        </p>
      </div>
    </div>
  );
}
