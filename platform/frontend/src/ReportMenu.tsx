import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type MouseEvent as ReactMouseEvent } from "react";

/** What a long press on a balance row asks for: the row and, for a detail row, its flow. */
export type ReportTarget = { row: { id: string; name: string }; flow?: string };
type Open = ReportTarget & { x: number; y: number };

const HOLD_MS = 450;
const SLOP_PX = 6;

/**
 * Press and hold the left button on a row to open a menu at the pointer. The click that
 * ends a long press does not reach the row (no collapse or expand).
 */
export function useLongPressMenu() {
  const [open, setOpen] = useState<Open | null>(null);
  const press = useRef<{ timer: number; x: number; y: number; fired: boolean } | null>(null);
  const cancel = () => {
    if (press.current && !press.current.fired) {
      window.clearTimeout(press.current.timer);
      press.current = null;
    }
  };
  useEffect(() => () => cancel(), []);

  const bind = (target: ReportTarget) => ({
    onPointerDown: (event: ReactPointerEvent) => {
      if (event.button !== 0 || event.pointerType === "touch" && !event.isPrimary) return;
      if ((event.target as HTMLElement).closest("a, button, input, select")) return;
      const { clientX: x, clientY: y } = event;
      cancel();
      press.current = {
        x,
        y,
        fired: false,
        timer: window.setTimeout(() => {
          if (press.current) press.current.fired = true;
          setOpen({ ...target, x, y });
          // The release may land outside the row (on the menu): forget the press after the
          // click it produces, so the next click on a row works again.
          document.addEventListener("pointerup", () => window.setTimeout(() => (press.current = null), 0), { once: true });
        }, HOLD_MS),
      };
    },
    onPointerMove: (event: ReactPointerEvent) => {
      const current = press.current;
      if (current && !current.fired && Math.hypot(event.clientX - current.x, event.clientY - current.y) > SLOP_PX) cancel();
    },
    onPointerUp: cancel,
    onPointerLeave: cancel,
    onPointerCancel: cancel,
    onClickCapture: (event: ReactMouseEvent) => {
      if (press.current?.fired) {
        event.stopPropagation();
        event.preventDefault();
        press.current = null;
      }
    },
    onContextMenu: (event: ReactMouseEvent) => {
      if (press.current?.fired) event.preventDefault();
    },
  });

  return { open, close: () => setOpen(null), bind };
}

export function ReportMenu({ open, close, onChoose }: { open: Open | null; close: () => void; onChoose: (kind: "turnover" | "chart", target: ReportTarget) => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) close();
    };
    const key = (event: KeyboardEvent) => event.key === "Escape" && close();
    // Registered after the press that opened the menu, so its own mouseup does not close it.
    const timer = window.setTimeout(() => document.addEventListener("mousedown", outside), 0);
    document.addEventListener("keydown", key);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    box.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", key);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open, close]);
  if (!open) return null;
  // Keep the menu inside the window.
  const left = Math.min(open.x, window.innerWidth - 270);
  const top = Math.min(open.y, window.innerHeight - 150);
  const choose = (kind: "turnover" | "chart") => {
    onChoose(kind, { row: open.row, flow: open.flow });
    close();
  };
  return (
    <div className="report-menu" ref={box} role="menu" style={{ left, top }} aria-label="Звіт за рядком">
      <small>
        {open.row.name}
        {open.flow ? ` · ${open.flow}` : ""}
      </small>
      <button role="menuitem" onClick={() => choose("turnover")}>
        <span aria-hidden="true">≡</span> Оборотна відомість
      </button>
      <button role="menuitem" onClick={() => choose("chart")}>
        <span aria-hidden="true">↗</span> Графік
      </button>
    </div>
  );
}
