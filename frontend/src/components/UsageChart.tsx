import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { DailyUsage } from "@/lib/api";
import { integer, tokens, weekday } from "@/lib/format";
import { cn } from "@/lib/utils";

const H = 232;
const M = { top: 16, right: 12, bottom: 28, left: 44 };

function niceStep(max: number, target = 4) {
  const raw = max / target;
  const pow = 10 ** Math.floor(Math.log10(raw || 1));
  const n = raw / pow;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * pow;
}

/** A bar whose data-end (top) is rounded and whose baseline end is square. */
function barPath(x: number, y: number, w: number, h: number, r = 4) {
  if (h <= 0) return "";
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

const SERIES = [
  { key: "agents", label: "Agents", color: "var(--series-agents)" },
  { key: "personal", label: "You", color: "var(--series-you)" },
] as const;

export function UsageChart({ data, cap }: { data: DailyUsage[]; cap: number }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => e && setWidth(Math.max(280, e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { ticks, y, max } = useMemo(() => {
    const peak = Math.max(cap, ...data.flatMap((d) => [d.agents, d.personal]), 1);
    const step = niceStep(peak * 1.08);
    const max = Math.ceil((peak * 1.08) / step) * step;
    const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step);
    const innerH = H - M.top - M.bottom;
    return { ticks, max, y: (v: number) => M.top + innerH - (v / max) * innerH };
  }, [data, cap]);

  const innerW = width - M.left - M.right;
  const band = innerW / Math.max(1, data.length);
  const barW = Math.max(6, Math.min(22, band * 0.26));
  const gap = 2;
  const today = data.length - 1;
  const hovered = hover !== null ? data[hover] : undefined;
  // "You" (your own Claude Code usage) only when there is any: other sources have no such logs.
  const series = SERIES.filter((s) => s.key !== "personal" || data.some((d) => d.personal > 0));
  const groupW = series.length * barW + (series.length - 1) * gap;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        {series.map((s) => (
          <span key={s.key} className="text-ink-2 inline-flex items-center gap-1.5 text-[12px]">
            <span className="size-2.5 rounded-[3px]" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
        {cap > 0 && (
          <span className="text-ink-2 inline-flex items-center gap-1.5 text-[12px]">
            <svg width="16" height="2" aria-hidden>
              <line
                x1="0"
                x2="16"
                y1="1"
                y2="1"
                stroke="var(--ink-2)"
                strokeWidth="1.5"
                strokeDasharray="3 3"
              />
            </svg>
            Daily agent budget
          </span>
        )}
        <button
          onClick={() => setAsTable((v) => !v)}
          className="text-muted hover:text-ink ml-auto text-[12px] underline-offset-2 transition-colors hover:underline"
        >
          {asTable ? "Show chart" : "Show table"}
        </button>
      </div>

      {asTable ? (
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-line text-muted border-b text-left text-[12px]">
              <th className="py-2 font-medium">Day</th>
              <th className="py-2 text-right font-medium">Agents</th>
              <th className="py-2 text-right font-medium">You</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.date} className="border-line border-b last:border-0">
                <td className="text-ink-2 py-2">
                  {weekday(d.date)} {d.date.slice(5)}
                </td>
                <td className="tabular py-2 text-right">{integer(d.agents)}</td>
                <td className="tabular py-2 text-right">{integer(d.personal)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div ref={wrap} className="relative" onMouseLeave={() => setHover(null)}>
          <svg
            width={width}
            height={H}
            className="block"
            role="img"
            aria-label="Daily token usage, last 7 days"
          >
            {ticks.map((t) => (
              <g key={t}>
                <line
                  x1={M.left}
                  x2={width - M.right}
                  y1={y(t)}
                  y2={y(t)}
                  stroke={t === 0 ? "var(--axis)" : "var(--grid)"}
                  strokeWidth="1"
                />
                <text
                  x={M.left - 8}
                  y={y(t)}
                  dy="0.32em"
                  textAnchor="end"
                  className="fill-muted tabular text-[11px]"
                >
                  {tokens(t)}
                </text>
              </g>
            ))}
            {data.map((d, i) => {
              const x0 = M.left + i * band;
              const cx = x0 + band / 2;
              return (
                <g key={d.date}>
                  {hover === i && (
                    <rect
                      x={x0 + 2}
                      y={M.top}
                      width={band - 4}
                      height={H - M.top - M.bottom}
                      rx="6"
                      fill="var(--surface-2)"
                    />
                  )}
                  {series.map((s, k) => {
                    const v = d[s.key];
                    const bx = cx - groupW / 2 + k * (barW + gap);
                    return <path key={s.key} d={barPath(bx, y(v), barW, y(0) - y(v))} fill={s.color} />;
                  })}
                  <text
                    x={cx}
                    y={H - 8}
                    textAnchor="middle"
                    className={cn("text-[11px]", i === today ? "fill-ink font-medium" : "fill-muted")}
                  >
                    {i === today ? "Today" : weekday(d.date)}
                  </text>
                  <rect
                    x={x0}
                    y={0}
                    width={band}
                    height={H}
                    fill="transparent"
                    onMouseEnter={() => setHover(i)}
                    onFocus={() => setHover(i)}
                    tabIndex={0}
                    aria-label={`${d.date}: agents ${integer(d.agents)}, you ${integer(d.personal)} tokens`}
                  />
                </g>
              );
            })}
            {cap > 0 && cap <= max && (
              <line
                x1={M.left}
                x2={width - M.right}
                y1={y(cap)}
                y2={y(cap)}
                stroke="var(--ink-2)"
                strokeWidth="1.5"
                strokeDasharray="4 4"
                pointerEvents="none"
              />
            )}
          </svg>
          {hovered && hover !== null && (
            <div
              className="animate-fade-in border-line-strong bg-surface shadow-pop pointer-events-none absolute z-10 min-w-40 rounded-lg border px-3 py-2"
              style={{
                left: Math.min(Math.max(M.left + hover * band + band / 2 - 80, 0), width - 168),
                top: 4,
              }}
            >
              <div className="text-ink mb-1.5 text-[12px] font-medium">
                {new Date(`${hovered.date}T12:00:00`).toLocaleDateString([], {
                  weekday: "long",
                  day: "numeric",
                  month: "short",
                })}
              </div>
              {series.map((s) => (
                <div key={s.key} className="flex items-center gap-2 text-[12px]">
                  <span className="size-2 rounded-[2px]" style={{ background: s.color }} />
                  <span className="text-ink-2">{s.label}</span>
                  <span className="text-ink tabular ml-auto font-medium">{integer(hovered[s.key])}</span>
                </div>
              ))}
              {cap > 0 && (
                <div className="border-line text-muted mt-1.5 border-t pt-1.5 text-[11.5px]">
                  {Math.round((hovered.agents / cap) * 100)}% of the agent budget
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
