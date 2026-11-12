import { CircleCheck, CircleDashed, Users } from "lucide-react";
import type { Agent, FeedEvent, Session } from "@/lib/api";
import { clock, duration, integer, shortModel, tokens } from "@/lib/format";
import { cn, roleColor } from "@/lib/utils";
import { Card, EmptyState, RoleChip, Tooltip } from "./ui/primitives";

const QUIET_AFTER_MIN = 5;

type State = { key: "working" | "quiet" | "finished" | "unfinished"; label: string; hint: string };

/**
 * What we can honestly say about an agent. The logs only tell us whether an agent wrote a "finished"
 * marker, so an agent without it in a run that is no longer live did NOT finish: it was cut off.
 */
export function agentState(a: Agent, live: boolean, events: FeedEvent[]): State {
  if (a.finished) return { key: "finished", label: "Finished", hint: "Reported back to the lead" };
  if (!live)
    return {
      key: "unfinished",
      label: "Didn't finish",
      hint: "The run ended before this agent reported back, so its last task may be incomplete",
    };
  const last =
    a.role === "lead"
      ? [...events].reverse().find((e) => e.agent === "lead" && e.ts)?.ts
      : (a.end ?? undefined);
  const quietMin = last ? (Date.now() - new Date(last).getTime()) / 60000 : 0;
  if (quietMin > QUIET_AFTER_MIN)
    return {
      key: "quiet",
      label: `Quiet for ${Math.round(quietMin)}m`,
      hint: "No new activity recently: it may be running a long command, or it may be stuck",
    };
  return { key: "working", label: "Working", hint: "Active in the current run" };
}

function StateLabel({ s }: { s: State }) {
  const content = {
    working: (
      <span className="text-good-ink inline-flex items-center gap-1.5">
        <span className="animate-pulse-ring bg-good size-2 rounded-full" />
        {s.label}
      </span>
    ),
    quiet: (
      <span className="text-ink inline-flex items-center gap-1.5">
        <span className="bg-warning size-2 rounded-full" />
        {s.label}
      </span>
    ),
    finished: (
      <span className="text-ink-2 inline-flex items-center gap-1.5">
        <CircleCheck className="text-muted size-3.5" />
        {s.label}
      </span>
    ),
    unfinished: (
      <span className="text-ink inline-flex items-center gap-1.5">
        <CircleDashed className="text-serious size-3.5" />
        {s.label}
      </span>
    ),
  }[s.key];
  return (
    <Tooltip content={s.hint}>
      <span className="cursor-default text-[12.5px] whitespace-nowrap">{content}</span>
    </Tooltip>
  );
}

export function AgentsTable({ session }: { session: Session | undefined }) {
  const agents = session?.agents ?? [];
  if (!agents.length)
    return (
      <Card>
        <EmptyState icon={<Users />} title="No agents yet">
          The lead and the agents it delegates to show up here during a run.
        </EmptyState>
      </Card>
    );
  const events = session?.events ?? [];
  const lead = agents[0]!;
  const subs = [...agents.slice(1)].sort((a, b) => (a.start ?? "").localeCompare(b.start ?? ""));
  const maxTokens = Math.max(...agents.map((a) => a.tokens), 1);
  const leadTimes = events.filter((e) => e.agent === "lead" && e.ts).map((e) => e.ts!);
  const leadSpan = { start: leadTimes[0] ?? null, end: leadTimes[leadTimes.length - 1] ?? null };
  const rows = [
    { a: { ...lead, start: leadSpan.start, end: leadSpan.end }, child: false },
    ...subs.map((a) => ({ a, child: true })),
  ];

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-[13px]">
          <thead>
            <tr className="border-line bg-surface-2/50 text-muted border-b text-left text-[12px]">
              <th className="py-2 pr-3 pl-4 font-medium">Agent</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Model</th>
              <th className="px-3 py-2 text-right font-medium">Actions</th>
              <th className="px-3 py-2 font-medium">Time</th>
              <th className="w-[180px] py-2 pr-4 pl-3 text-right font-medium">Tokens</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ a, child }, i) => {
              const st = agentState(a, !!session?.live, events);
              return (
                <tr key={i} className="border-line hover:bg-surface-2/40 border-b last:border-0">
                  <td className="py-2.5 pr-3 pl-4">
                    <div className={cn("flex items-center gap-2.5", child && "pl-5")}>
                      {child && (
                        <span className="relative -ml-5 h-5 w-3.5 shrink-0" aria-hidden>
                          <span className="border-line-strong absolute top-0 left-1.5 h-2.5 w-2 rounded-bl-md border-b border-l" />
                        </span>
                      )}
                      <RoleChip role={a.role} />
                      <span className="text-ink max-w-[340px] truncate">{a.description || "–"}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <StateLabel s={st} />
                  </td>
                  <td className="text-ink-2 px-3 py-2.5 whitespace-nowrap">
                    {a.model ? shortModel(a.model) : "–"}
                  </td>
                  <td className="text-ink-2 tabular px-3 py-2.5 text-right">{integer(a.actions)}</td>
                  <td className="text-ink-2 tabular px-3 py-2.5 whitespace-nowrap">
                    {a.start ? (
                      <>
                        {clock(a.start, false)}
                        <span className="text-muted">
                          {" "}
                          · {duration(a.start, st.key === "working" ? new Date().toISOString() : a.end)}
                        </span>
                      </>
                    ) : (
                      "–"
                    )}
                  </td>
                  <td className="py-2.5 pr-4 pl-3">
                    <div className="flex items-center justify-end gap-2.5">
                      <div className="bg-surface-3 h-1.5 w-20 overflow-hidden rounded-full">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${(a.tokens / maxTokens) * 100}%`, background: roleColor(a.role) }}
                        />
                      </div>
                      <span className="text-ink tabular w-12 text-right font-medium">{tokens(a.tokens)}</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-line text-muted border-t px-4 py-2.5 text-[12px]">
        Tokens are Opus-equivalent: each model&apos;s tokens are weighted by its price relative to Opus.
      </p>
    </Card>
  );
}
