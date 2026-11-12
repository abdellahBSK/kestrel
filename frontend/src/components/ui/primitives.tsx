import { Tooltip as T } from "radix-ui";
import type { HTMLAttributes, ReactNode } from "react";
import { cn, roleColor, roleLabel } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border-line bg-surface shadow-card rounded-xl border", className)} {...props} />;
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-ink text-[13px] font-semibold tracking-tight">{children}</h2>
      {action}
    </div>
  );
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "border-line-strong bg-surface-2 text-muted inline-flex h-5 min-w-5 items-center justify-center rounded border px-1 font-sans text-[11px] font-medium",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

export function Badge({
  children,
  className,
  tone = "neutral",
}: {
  children: ReactNode;
  className?: string;
  tone?: "neutral" | "outline" | "good" | "warning" | "critical" | "info";
}) {
  const tones = {
    neutral: "bg-surface-2 text-ink-2",
    outline: "border border-line-strong text-ink-2",
    good: "bg-good/12 text-good-ink",
    warning: "bg-warning/15 text-ink",
    critical: "bg-critical/12 text-critical-ink",
    info: "bg-info/12 text-info",
  } as const;
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-md px-1.5 text-[11px] font-medium whitespace-nowrap [&_svg]:size-3",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function KeyBadge({ children }: { children: ReactNode }) {
  return (
    <span className="border-line-strong text-ink-2 inline-flex h-5 items-center rounded border px-1.5 font-mono text-[10.5px] font-medium tracking-wide">
      {children}
    </span>
  );
}

export function Tooltip({
  content,
  children,
  side = "top",
  mono,
}: {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  mono?: boolean;
}) {
  if (!content) return <>{children}</>;
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content
          side={side}
          sideOffset={6}
          collisionPadding={12}
          className={cn(
            "animate-fade-in border-line-strong bg-surface text-ink shadow-pop z-50 max-w-[min(560px,90vw)] rounded-md border px-2.5 py-1.5 text-[12px] leading-snug",
            mono && "font-mono text-[11.5px] break-all whitespace-pre-wrap",
          )}
        >
          {content}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}

/** A role chip: colored dot carries identity, the label stays in ink. */
export function RoleChip({ role, className }: { role: string; className?: string }) {
  return (
    <span
      className={cn(
        "bg-surface-2 text-ink inline-flex h-5 items-center gap-1.5 rounded-md px-1.5 text-[11.5px] font-medium whitespace-nowrap",
        className,
      )}
    >
      <span className="size-1.5 rounded-full" style={{ background: roleColor(role) }} />
      {roleLabel(role)}
    </span>
  );
}

export type Health = "working" | "idle" | "stopped" | "finished" | "never" | "attention";

export function StatusDot({ status, className }: { status: Health; className?: string }) {
  const color = {
    working: "bg-good animate-pulse-ring",
    attention: "bg-warning",
    stopped: "bg-critical",
    idle: "bg-muted/60",
    finished: "bg-muted/60",
    never: "border border-muted/70 bg-transparent",
  }[status];
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", color, className)} />;
}

/** A thin usage meter with an optional warning tick. Without a cap it renders nothing. */
export function Meter({
  value,
  cap,
  warnAt,
  className,
  color = "var(--ink)",
}: {
  value: number;
  cap: number;
  warnAt?: number;
  className?: string;
  color?: string;
}) {
  if (!cap) return null;
  const pct = Math.min(100, (value / cap) * 100);
  const over = pct >= 100;
  const warn = warnAt !== undefined && pct >= warnAt * 100;
  const fill = over ? "var(--critical)" : warn ? "var(--warning)" : color;
  return (
    <div
      className={cn("bg-surface-3 relative h-1.5 overflow-hidden rounded-full", className)}
      role="meter"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={cap}
    >
      <div
        className="h-full rounded-full transition-[width] duration-500 ease-out"
        style={{ width: `${pct}%`, background: fill }}
      />
      {warnAt !== undefined && (
        <span className="bg-ink/35 absolute inset-y-0 w-px" style={{ left: `${warnAt * 100}%` }} />
      )}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("bg-surface-3/70 animate-pulse rounded-md", className)} />;
}

export function EmptyState({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      <div className="border-line bg-surface-2 text-muted mb-1 flex size-10 items-center justify-center rounded-xl border [&_svg]:size-5">
        {icon}
      </div>
      <p className="text-ink text-[13.5px] font-medium">{title}</p>
      {children && <div className="text-muted max-w-sm text-[13px]">{children}</div>}
    </div>
  );
}
