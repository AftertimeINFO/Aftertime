import { useEffect, useRef, useState } from "react";

/** A source behind an amount: a publication with an optional link. */
export type Source = { title: string; url?: string | null };

/** Small "sources" control: opens the list of publications behind a balance row. */
export function SourcesBadge({ sources }: { sources?: Source[] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const key = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  if (!sources?.length) return null;
  return (
    <span className="sources" ref={box} onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
      <button className="sources-badge" onClick={() => setOpen(!open)} aria-expanded={open} title="Джерела даних цього руху">
        джерела · {sources.length}
      </button>
      {open && (
        <span className="sources-pop" role="dialog" aria-label="Джерела">
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
