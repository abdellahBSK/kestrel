import { CircleCheck, CircleDashed, CircleX, Hourglass, Users } from "lucide-react";
import type { Agent, Session } from "@/lib/api";
import { clock, duration, integer, relative, shortModel, tokens } from "@/lib/format";
import { AGENT } from "@/lib/health";
import { cn, roleColor } from "@/lib/utils";
import { Card, EmptyState, RoleChip, Tooltip } from "./ui/primitives";

/** The agent's state as decided by the server (status.py), with an icon so color is never alone. */
export function AgentStateLabel({ a }: { a: Agent }) {
  const meta = AGENT[a.state];
  const quiet =
    a.state === "idle" || a.state === "stale" ? ` · ${relative(a.last_activity).replace(" ago", "")}` : "";
  const icon = {
    working: <span className="bg-good animate-pulse-ring size-2 rounded-full" />,
    waiting: <Hourglass className="text-muted size-3.5" />,
    idle: <span className="bg-muted/60 size-2 rounded-full" />,
    stale: <span className="bg-warning ring-warning/30 size-2 rounded-full ring-2" />,
    finished: <CircleCheck className="text-muted size-3.5" />,
    lost: <CircleDashed className="text-serious size-3.5" />,
    failed: <CircleX className="text-critical size-3.5" />,
  }[a.state];
  return (
    <Tooltip content={`${meta.hint} Last activity ${clock(a.last_activity, false)}.`}>
      <span
        className={cn(
          "inline-flex cursor-default items-center gap-1.5 text-[12.5px] whitespace-nowrap",
          a.state === "working" ? "text-good-ink" : a.state === "finished" ? "text-ink-2" : "text-ink",
        )}
      >
        {icon}
        {meta.label}
        {quiet}
      </span>
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
  const [lead, ...rest] = agents;
  const subs = [...rest].sort((a, b) => (a.start ?? "").localeCompare(b.start ?? ""));
  const maxTokens = Math.max(...agents.map((a) => a.tokens), 1);
  const rows = [{ a: lead!, child: false }, ...subs.map((a) => ({ a, child: true }))];

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
              const ongoing = a.state === "working" || a.state === "waiting" || a.state === "idle";
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
                    <AgentStateLabel a={a} />
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
                          · {duration(a.start, ongoing ? new Date().toISOString() : a.end)}
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
