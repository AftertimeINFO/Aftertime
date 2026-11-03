export type TimelineScale = "auto" | "full";

export type TimelineEventPoint = {
  scheduled_at: string;
  status?: string;
};

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

export function timelineViewport(fullStart: number, fullEnd: number, current: number, events: TimelineEventPoint[], scale: TimelineScale) {
  const eventTimes = events.map((event) => new Date(event.scheduled_at).getTime()).filter(Number.isFinite).sort((a, b) => a - b);
  const safeEnd = Math.max(fullEnd, eventTimes.at(-1) || fullEnd, fullStart + 1);
  if (scale === "full" || !eventTimes.length) return { start: fullStart, end: safeEnd, next: null as number | null };

  const next = eventTimes.find((time) => time > current + 1000) ?? null;
  if (next === null) {
    const last = eventTimes.filter((time) => time <= current).at(-1);
    if (last === undefined || current >= safeEnd) return { start: fullStart, end: safeEnd, next };
    const span = clamp(Math.max(current - last, 30 * 60_000), 30 * 60_000, 6 * 3600_000);
    return { start: Math.max(fullStart, last - span * .15), end: Math.min(safeEnd, current + span * .2), next };
  }

  const gap = Math.max(60_000, next - current);
  const span = clamp(gap, 15 * 60_000, 12 * 3600_000);
  let start = Math.max(fullStart, current - span * .18);
  let end = Math.min(safeEnd, next + span * .28);
  const minimum = Math.min(safeEnd - fullStart, 15 * 60_000);
  if (end - start < minimum) {
    const missing = minimum - (end - start);
    start = Math.max(fullStart, start - missing / 2);
    end = Math.min(safeEnd, end + missing / 2);
  }
  return { start, end, next };
}
