import type { BacklogCounts } from "@/lib/api";
import { cn } from "@/lib/utils";

export const BACKLOG_SEGMENTS = [
  { key: "done", label: "Done", color: "var(--good)" },
  { key: "review", label: "In review", color: "var(--info)" },
  { key: "doing", label: "In progress", color: "var(--role-7)" },
  { key: "blocked", label: "Blocked", color: "var(--critical)" },
  { key: "todo", label: "To do", color: "var(--surface-3)" },
] as const;

/** Segmented progress bar; a 2px surface gap separates the fills. */
export function BacklogBar({ counts, className }: { counts: BacklogCounts; className?: string }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className={cn("flex h-1.5 gap-[2px] overflow-hidden rounded-full", className)}>
      {BACKLOG_SEGMENTS.map((s) =>
        counts[s.key] ? (
          <span
            key={s.key}
            className="h-full first:rounded-l-full last:rounded-r-full"
            style={{ width: `${(counts[s.key] / total) * 100}%`, background: s.color }}
          />
        ) : null,
      )}
    </div>
  );
}
