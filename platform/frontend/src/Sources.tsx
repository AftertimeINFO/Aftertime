import { useEffect, useRef, useState } from "react";

/** A source behind an amount: a publication with an optional link. */
export type Source = { title: string; url?: string | null };

/** Small "sources" control: opens the list of publications behind a balance row. */
export function SourcesBadge({ sources }: { sources?: Source[] }) {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<{ left: number; top: number }>({ left: 0, top: 0 });
  const box = useRef<HTMLSpanElement>(null);
  const toggle = (button: HTMLElement) => {
    // Fixed to the window: a table that scrolls does not clip the list.
    const rect = button.getBoundingClientRect();
    const width = Math.min(520, window.innerWidth * 0.7);
    const below = window.innerHeight - rect.bottom > 220;
    setPlace({ left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)), top: below ? rect.bottom + 4 : Math.max(8, rect.top - 224) });
    setOpen(!open);
  };
  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const key = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    // Scrolling the page moves the row away from the list; scrolling the list itself does not.
    const close = (event: Event) => {
      if (!(box.current && box.current.contains(event.target as Node))) setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", key);
    window.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", key);
      window.removeEventListener("scroll", close, true);
    };
  }, [open]);
  if (!sources?.length) return null;
  return (
    <span className="sources" ref={box} onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
      <button className="sources-badge" onClick={(e) => toggle(e.currentTarget)} aria-expanded={open} title="Джерела даних цього руху">
        джерела · {sources.length}
      </button>
      {open && (
        <span className="sources-pop" role="dialog" aria-label="Джерела" style={place}>
          <SourceList sources={sources} />
        </span>
      )}
    </span>
  );
}

export function SourceList({ sources }: { sources: Source[] }) {
  return (
    <ol className="sources-list">
      {sources.map((source) => (
        <li key={`${source.title}|${source.url ?? ""}`}>
          {source.url ? (
            <a href={source.url} target="_blank" rel="noreferrer noopener">
              {source.title}
            </a>
          ) : (
            source.title
          )}
        </li>
      ))}
    </ol>
  );
}
