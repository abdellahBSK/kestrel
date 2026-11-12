// Formatting helpers. Every timestamp from the server is UTC; it is shown either in the browser's
// timezone or at a fixed UTC offset (this computer's clock), as the viewer chooses. The two can
// disagree when the browser's timezone data is out of date for a zone (it happens after zone rule changes).

let displayOffsetMin: number | null = null;

/** null = the browser's own timezone; a number = show times at this UTC offset, in minutes. */
export function setDisplayOffset(min: number | null) {
  displayOffsetMin = min;
}

export function browserOffsetMin(at = new Date()): number {
  return -at.getTimezoneOffset();
}

export function offsetLabel(min: number): string {
  const sign = min < 0 ? "−" : "+";
  const a = Math.abs(min);
  return `UTC${sign}${String(Math.floor(a / 60)).padStart(2, "0")}:${String(a % 60).padStart(2, "0")}`;
}

function format(ts: string, opts: Intl.DateTimeFormatOptions): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  if (displayOffsetMin === null) return new Intl.DateTimeFormat([], opts).format(d);
  const shifted = new Date(d.getTime() + displayOffsetMin * 60_000);
  return new Intl.DateTimeFormat([], { ...opts, timeZone: "UTC" }).format(shifted);
}

export function tokens(n: number | null | undefined): string {
  const v = n ?? 0;
  if (v >= 1e6) return `${(v / 1e6).toFixed(v >= 1e7 ? 1 : 2)}M`;
  if (v >= 1e3) return `${Math.round(v / 1e3)}k`;
  return String(Math.round(v));
}

export function integer(n: number): string {
  return new Intl.NumberFormat().format(Math.round(n));
}

export function percent(part: number, whole: number): string {
  if (!whole) return "–";
  return `${Math.round((part / whole) * 100)}%`;
}

export function clock(ts: string | null | undefined, seconds = true): string {
  if (!ts) return "";
  return format(ts, {
    hour: "2-digit",
    minute: "2-digit",
    ...(seconds ? { second: "2-digit" } : {}),
    hourCycle: "h23",
  });
}

export function dateTime(ts: string | null | undefined): string {
  if (!ts) return "";
  return format(ts, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}

export function relative(ts: string | null | undefined, now = Date.now()): string {
  if (!ts) return "";
  const s = (now - new Date(ts).getTime()) / 1000;
  if (s < 0) return "just now";
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  const d = Math.round(s / 86400);
  return d === 1 ? "yesterday" : `${d}d ago`;
}

export function duration(from: string | null | undefined, to: string | null | undefined): string {
  if (!from || !to) return "–";
  const s = Math.max(0, (new Date(to).getTime() - new Date(from).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  if (m < 60)
    return `${m}m ${Math.round(s % 60)
      .toString()
      .padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${(m % 60).toString().padStart(2, "0")}m`;
}

export function weekday(date: string): string {
  return new Date(`${date}T12:00:00`).toLocaleDateString([], { weekday: "short" });
}

export function shortModel(model: string): string {
  return model.replace(/^claude-/, "").replace(/-(\d+)-(\d+)$/, " $1.$2");
}
