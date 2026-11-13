import { useMemo, useRef } from "react";
import { fmtDateTime, fmtMw } from "./format";
import { eventFrames, type Frame, type RunSummary } from "./run";

const SPEEDS = [1, 2, 4, 8];

type Props = {
  frames: Frame[];
  index: number;
  onIndex: (index: number) => void;
  playing: boolean;
  onPlaying: (playing: boolean) => void;
  speed: number;
  onSpeed: (speed: number) => void;
  bands?: RunSummary["ensemble"];
};

/**
 * Playback of a run: the deficit over time as the background of the scrubber (so the user
 * sees where the trouble is before scrubbing), event markers, transport and speed.
 */
export default function Timeline({ frames, index, onIndex, playing, onPlaying, speed, onSpeed, bands }: Props) {
  const track = useRef<HTMLDivElement>(null);
  const marks = useMemo(() => eventFrames(frames), [frames]);
  const t0 = Date.parse(frames[0]?.at ?? "");
  const t1 = Date.parse(frames[frames.length - 1]?.at ?? "");
  const span = Math.max(1, t1 - t0);
  const x = (at: string) => ((Date.parse(at) - t0) / span) * 100;
  const peak = Math.max(1, ...frames.map((f) => f.metrics.unserved_mw), ...(bands?.bands.map((b) => b.unserved_mw.p90) ?? []));
  const path = useMemo(() => {
    if (!frames.length) return "";
    const pts = frames.map((f) => `${x(f.at).toFixed(2)},${(100 - (f.metrics.unserved_mw / peak) * 92).toFixed(2)}`);
    return `M0,100 L${pts.join(" L")} L100,100 Z`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frames, peak]);
  const band = useMemo(() => {
    if (!bands?.bands.length) return "";
    const upper = bands.bands.map((b) => `${x(b.at).toFixed(2)},${(100 - (b.unserved_mw.p90 / peak) * 92).toFixed(2)}`);
    const lower = [...bands.bands].reverse().map((b) => `${x(b.at).toFixed(2)},${(100 - (b.unserved_mw.p10 / peak) * 92).toFixed(2)}`);
    return `M${upper.join(" L")} L${lower.join(" L")} Z`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bands, peak]);
  const current = frames[index];
  if (!current) return null;

  const seekFromPointer = (clientX: number) => {
    const rect = track.current?.getBoundingClientRect();
    if (!rect) return;
    const at = t0 + ((clientX - rect.left) / rect.width) * span;
    let best = 0;
    for (let i = 0; i < frames.length; i++) if (Math.abs(Date.parse(frames[i].at) - at) < Math.abs(Date.parse(frames[best].at) - at)) best = i;
    onIndex(best);
  };
  const prev = [...marks].reverse().find((i) => i < index);
  const next = marks.find((i) => i > index);

  return (
    <div className="en-timeline" role="group" aria-label="Програвання прогону">
      <div className="en-transport">
        <button className="en-icon-btn" onClick={() => prev != null && onIndex(prev)} disabled={prev == null} title="Попередня подія (←)" aria-label="Попередня подія">⏮</button>
        <button className="en-play" onClick={() => onPlaying(!playing)} title={playing ? "Пауза (пробіл)" : "Відтворити (пробіл)"} aria-label={playing ? "Пауза" : "Відтворити"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <button className="en-icon-btn" onClick={() => next != null && onIndex(next)} disabled={next == null} title="Наступна подія (→)" aria-label="Наступна подія">⏭</button>
        <div className="en-clock">
          <b>{fmtDateTime(current.at)}</b>
          <small>крок {index + 1} з {frames.length}</small>
        </div>
      </div>
      <div
        className="en-track"
        ref={track}
        onPointerDown={(e) => { (e.target as HTMLElement).setPointerCapture?.(e.pointerId); seekFromPointer(e.clientX); }}
        onPointerMove={(e) => e.buttons === 1 && seekFromPointer(e.clientX)}
        role="slider"
        tabIndex={0}
        aria-valuemin={0}
        aria-valuemax={frames.length - 1}
        aria-valuenow={index}
        aria-valuetext={`${fmtDateTime(current.at)}, дефіцит ${fmtMw(current.metrics.unserved_mw)}`}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") { e.preventDefault(); onIndex(Math.max(0, index - 1)); }
          if (e.key === "ArrowRight") { e.preventDefault(); onIndex(Math.min(frames.length - 1, index + 1)); }
          if (e.key === "Home") onIndex(0);
          if (e.key === "End") onIndex(frames.length - 1);
        }}
      >
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="en-track-chart" aria-hidden="true">
          {band && <path d={band} className="en-band" />}
          <path d={path} className="en-area" />
        </svg>
        {marks.map((i) => (
          <button
            key={i}
            className={`en-mark ${i === index ? "active" : ""}`}
            style={{ left: `${x(frames[i].at)}%` }}
            title={`${fmtDateTime(frames[i].at)}: ${frames[i].events.filter((e) => e.origin !== "repair").map((e) => e.label).join("; ")}`}
            aria-label={`Подія: ${frames[i].events.map((e) => e.label).join("; ")}`}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => onIndex(i)}
          />
        ))}
        <i className="en-cursor" style={{ left: `${x(current.at)}%` }} aria-hidden="true" />
        <span className="en-track-label">Дефіцит потужності · пік {fmtMw(peak)}{bands ? " · смуга P10–P90" : ""}</span>
      </div>
      <div className="en-segmented small" role="radiogroup" aria-label="Швидкість відтворення">
        {SPEEDS.map((s) => (
          <button key={s} role="radio" aria-checked={speed === s} className={speed === s ? "active" : ""} onClick={() => onSpeed(s)} title={`${s} кроки за секунду`}>
            ×{s}
          </button>
        ))}
      </div>
    </div>
  );
}
