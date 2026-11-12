import {
  Ban,
  ChevronRight,
  CircleAlert,
  FilePen,
  FileText,
  GitBranch,
  Hand,
  LoaderCircle,
  MessageSquare,
  Search,
  SquareTerminal,
  TriangleAlert,
  Workflow,
  ListChecks,
  Inbox,
} from "lucide-react";
import { useMemo, useState } from "react";
import type { FeedEvent, Session } from "@/lib/api";
import { clock } from "@/lib/format";
import { humanize } from "@/lib/humanize";
import { cn, roleColor, roleLabel, ROLE_ORDER } from "@/lib/utils";
import { Badge, Card, EmptyState, RoleChip, Tooltip } from "./ui/primitives";

const PAGE = 250;

function EventIcon({ e }: { e: FeedEvent }) {
  const cls = "size-3.5";
  if (e.kind === "say") return <MessageSquare className={cls} />;
  if (e.kind === "budget") return <TriangleAlert className={cls} />;
  if (e.kind === "halt") return <Hand className={cls} />;
  if (e.kind === "delegate") return <Workflow className={cls} />;
  switch (e.tool) {
    case "Bash":
    case "PowerShell":
      return /\bgit\b|\bgh\b/.test(e.text) ? (
        <GitBranch className={cls} />
      ) : (
        <SquareTerminal className={cls} />
      );
    case "Read":
      return <FileText className={cls} />;
    case "Grep":
    case "Glob":
      return <Search className={cls} />;
    case "TodoWrite":
      return <ListChecks className={cls} />;
    default:
      return <FilePen className={cls} />;
  }
}

function Status({ e }: { e: FeedEvent }) {
  if (e.status === "running")
    return (
      <span className="text-muted inline-flex items-center gap-1 text-[11.5px]">
        <LoaderCircle className="size-3 animate-spin" />
        running
      </span>
    );
  if (e.status === "blocked")
    return (
      <Badge tone="critical">
        <Ban />
        Blocked
      </Badge>
    );
  if (e.status === "error")
    return (
      <Badge tone="warning">
        <CircleAlert />
        Error
      </Badge>
    );
  return null;
}

function Row({ e }: { e: FeedEvent }) {
  const [open, setOpen] = useState(false);
  const h = humanize(e);
  const expandable = !!(e.result || (h.detail && h.detail.length > 60));
  const tone =
    e.kind === "halt" || e.status === "blocked"
      ? "bg-critical/[0.05]"
      : e.kind === "budget"
        ? "bg-warning/[0.07]"
        : "";

  return (
    <li className={cn("group border-line border-b last:border-0", tone)}>
      <div
        className={cn(
          "grid grid-cols-[64px_minmax(0,1fr)] gap-x-3 px-4 py-2.5 sm:grid-cols-[72px_112px_minmax(0,1fr)_auto]",
          expandable && "hover:bg-surface-2/50 cursor-pointer",
        )}
        onClick={() => expandable && setOpen((v) => !v)}
      >
        <span className="text-muted tabular pt-px font-mono text-[11.5px]">{clock(e.ts)}</span>
        <span className="hidden sm:block">
          <RoleChip role={e.agent} />
        </span>
        <div className="min-w-0">
          <div className="flex items-start gap-2">
            <span className={cn("text-muted mt-[3px]", e.kind === "delegate" && "text-ink")}>
              <EventIcon e={e} />
            </span>
            <div className="min-w-0 flex-1">
              <p
                className={cn(
                  "text-[13px] leading-snug",
                  e.kind === "say" ? "text-ink-2 italic" : "text-ink",
                  e.kind === "delegate" && "font-medium",
                  !open && e.kind === "say" && "line-clamp-2",
                )}
              >
                <span className="mr-1.5 sm:hidden">
                  <span
                    className="mr-1 inline-block size-1.5 rounded-full align-middle"
                    style={{ background: roleColor(e.agent) }}
                  />
                  <span className="text-[12px] font-medium">{roleLabel(e.agent)}</span>
                </span>
                {h.title}
              </p>
              {h.detail && h.detail !== h.title && (
                <Tooltip content={h.raw ?? h.detail} mono side="bottom">
                  <p
                    className={cn(
                      "text-muted mt-0.5 font-mono text-[11.5px]",
                      open ? "break-all" : "truncate",
                    )}
                  >
                    {h.detail}
                  </p>
                </Tooltip>
              )}
            </div>
          </div>
        </div>
        <div className="col-start-2 mt-1 flex items-center gap-2 sm:col-start-auto sm:mt-0 sm:justify-end">
          <Status e={e} />
          {expandable && (
            <ChevronRight className={cn("text-muted size-3.5 transition-transform", open && "rotate-90")} />
          )}
        </div>
      </div>
      {open && e.result && (
        <div className="px-4 pb-3 sm:pl-[212px]">
          <pre className="border-line bg-surface-2 text-ink-2 max-h-64 overflow-auto rounded-lg border p-3 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap">
            {e.result}
          </pre>
        </div>
      )}
    </li>
  );
}

export function ActivityFeed({ session }: { session: Session | undefined }) {
  const [agent, setAgent] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [showMessages, setShowMessages] = useState(true);
  const [limit, setLimit] = useState(PAGE);
  const events = useMemo(() => session?.events ?? [], [session]);

  const roles = useMemo(() => {
    const counts = new Map<string, number>();
    for (const e of events) counts.set(e.agent, (counts.get(e.agent) ?? 0) + 1);
    return [...counts.entries()].sort(
      (a, b) =>
        ((ROLE_ORDER.indexOf(a[0] as never) + 99) % 99) - ((ROLE_ORDER.indexOf(b[0] as never) + 99) % 99),
    );
  }, [events]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return events
      .filter((e) => agent === "all" || e.agent === agent)
      .filter((e) => showMessages || e.kind !== "say")
      .filter((e) => !q || `${e.text} ${humanize(e).title} ${e.result ?? ""}`.toLowerCase().includes(q))
      .reverse();
  }, [events, agent, query, showMessages]);

  if (!session?.session)
    return (
      <Card>
        <EmptyState icon={<Inbox />} title="No runs recorded yet">
          Activity appears here as soon as this project&apos;s team starts a run.
        </EmptyState>
      </Card>
    );

  return (
    <Card className="overflow-hidden">
      <div className="border-line flex flex-wrap items-center gap-2 border-b px-4 py-3">
        <div className="flex flex-wrap gap-1">
          <FilterChip active={agent === "all"} onClick={() => setAgent("all")}>
            All <span className="text-muted tabular">{events.length}</span>
          </FilterChip>
          {roles.map(([r, n]) => (
            <FilterChip key={r} active={agent === r} onClick={() => setAgent(agent === r ? "all" : r)}>
              <span className="size-1.5 rounded-full" style={{ background: roleColor(r) }} />
              {roleLabel(r)} <span className="text-muted tabular">{n}</span>
            </FilterChip>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-3">
          <label className="text-ink-2 flex cursor-pointer items-center gap-1.5 text-[12.5px] select-none">
            <input
              type="checkbox"
              checked={showMessages}
              onChange={(e) => setShowMessages(e.target.checked)}
              className="size-3.5 accent-(--ink)"
            />
            Messages
          </label>
          <div className="relative">
            <Search className="text-muted pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter activity…"
              className="border-line-strong bg-surface text-ink placeholder:text-muted focus:border-ink/40 h-8 w-48 rounded-md border pr-2.5 pl-8 text-[13px] outline-none"
            />
          </div>
        </div>
      </div>

      {session.live && (
        <div className="border-line bg-good/[0.06] text-good-ink flex items-center gap-2 border-b px-4 py-2 text-[12.5px]">
          <span className="animate-pulse-ring bg-good size-2 rounded-full" />
          Live: new activity appears at the top
        </div>
      )}

      {filtered.length === 0 ? (
        <EmptyState icon={<Search />} title="Nothing matches these filters" />
      ) : (
        <ul>
          {filtered.slice(0, limit).map((e, i) => (
            <Row key={`${e.ts}-${i}-${filtered.length - i}`} e={e} />
          ))}
        </ul>
      )}
      {filtered.length > limit && (
        <div className="border-line border-t p-3 text-center">
          <button
            onClick={() => setLimit((l) => l + PAGE)}
            className="text-ink-2 hover:text-ink text-[12.5px] underline-offset-2 hover:underline"
          >
            Show {Math.min(PAGE, filtered.length - limit)} older events
          </button>
        </div>
      )}
    </Card>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-[12.5px] font-medium transition-colors",
        active
          ? "border-ink/25 bg-surface-2 text-ink"
          : "text-ink-2 hover:bg-surface-2/70 hover:text-ink border-transparent",
      )}
    >
      {children}
    </button>
  );
}
