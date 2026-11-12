import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleDashed, CircleX, Hourglass, OctagonX, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { action, stopPath, type Agent, type Session } from "@/lib/api";
import { clock, duration, integer, relative, shortModel, tokens, usd } from "@/lib/format";
import { AGENT } from "@/lib/health";
import { cn, roleColor } from "@/lib/utils";
import { Button } from "./ui/button";
import { ConfirmDialog } from "./ui/overlays";
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

/** Agents as a tree: each under the agent that started it, siblings in start order. */
export function agentTree(agents: Agent[]): { a: Agent; depth: number }[] {
  const ids = new Set(agents.map((a) => a.id));
  const children = new Map<string | null, Agent[]>();
  for (const a of agents) {
    const parent = a.parent && ids.has(a.parent) && a.parent !== a.id ? a.parent : null;
    children.set(parent, [...(children.get(parent) ?? []), a]);
  }
  const rows: { a: Agent; depth: number }[] = [];
  const seen = new Set<string>();
  const walk = (parent: string | null, depth: number) => {
    const kids = [...(children.get(parent) ?? [])].sort((x, y) =>
      (x.start ?? "").localeCompare(y.start ?? ""),
    );
    for (const a of kids) {
      if (seen.has(a.id)) continue; // guards against parent cycles in reported data
      seen.add(a.id);
      rows.push({ a, depth });
      walk(a.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

export function AgentsTable({ session }: { session: Session | undefined }) {
  const qc = useQueryClient();
  const [stopping, setStopping] = useState<Agent | null>(null);
  const agents = session?.agents ?? [];
  if (!agents.length)
    return (
      <Card>
        <EmptyState icon={<Users />} title="No agents yet">
          The lead and the agents it delegates to show up here during a run.
        </EmptyState>
      </Card>
    );
  const maxTokens = Math.max(...agents.map((a) => a.tokens), 1);
  const rows = agentTree(agents);

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
              <th className="px-3 py-2 text-right font-medium">Cost</th>
              <th className="w-[180px] py-2 pr-2 pl-3 text-right font-medium">Tokens</th>
              <th className="w-10 py-2 pr-3" aria-label="Stop" />
            </tr>
          </thead>
          <tbody>
            {rows.map(({ a, depth }, i) => {
              const ongoing = a.state === "working" || a.state === "waiting" || a.state === "idle";
              return (
                <tr key={i} className="border-line hover:bg-surface-2/40 border-b last:border-0">
                  <td className="py-2.5 pr-3 pl-4">
                    <div className="flex items-center gap-2.5" style={{ paddingLeft: depth * 20 }}>
                      {depth > 0 && (
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
                  <td className="text-ink-2 tabular px-3 py-2.5 text-right whitespace-nowrap">
                    {integer(a.actions)}
                    {a.errors > 0 && (
                      <Tooltip content={`${a.errors} action${a.errors > 1 ? "s" : ""} ended in an error`}>
                        <span className="text-critical-ink ml-1.5 cursor-default">· {a.errors} failed</span>
                      </Tooltip>
                    )}
                    {a.retries > 0 && (
                      <Tooltip
                        content={`${a.retries} action${a.retries > 1 ? "s" : ""} repeated one that had failed`}
                      >
                        <span className="ml-1.5 cursor-default">
                          · {a.retries} {a.retries > 1 ? "retries" : "retry"}
                        </span>
                      </Tooltip>
                    )}
                  </td>
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
                  <td className="text-ink-2 tabular px-3 py-2.5 text-right whitespace-nowrap">
                    {a.cost_unknown && a.cost_usd === 0 ? (
                      <Tooltip content="No price is known for this model. Add one under [prices] in config.toml.">
                        <span className="cursor-default">–</span>
                      </Tooltip>
                    ) : (
                      <>
                        {usd(a.cost_usd)}
                        {a.cost_unknown && "+"}
                      </>
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
                  <td className="py-2.5 pr-3">
                    {a.stop_requested ? (
                      <Tooltip content={`Stop requested: ${a.stop_requested}. It ends at its next action.`}>
                        <span className="text-critical-ink cursor-default text-[12px] whitespace-nowrap">
                          Stopping
                        </span>
                      </Tooltip>
                    ) : (
                      session?.live &&
                      (ongoing || a.state === "stale") && (
                        <Tooltip content={a.parent ? "Stop this agent" : "Stop this agent and its run"}>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={`Stop ${a.role}`}
                            onClick={() => setStopping(a)}
                          >
                            <OctagonX />
                          </Button>
                        </Tooltip>
                      )
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ConfirmDialog
        open={stopping !== null}
        onOpenChange={(open) => !open && setStopping(null)}
        title={`Stop the ${stopping?.role ?? ""} agent?`}
        description={
          stopping?.parent
            ? "Its next action is refused and it is told to report what it has done and stop. The rest of the run goes on."
            : "This is the agent the run belongs to: stopping it ends the whole run."
        }
        confirm="Stop the agent"
        danger
        onConfirm={async () => {
          if (!stopping || !session?.session) return;
          const res = await action(stopPath(session.team, session.session, stopping.id));
          if (res.ok) toast.success(res.msg);
          else toast.error(res.msg);
          qc.invalidateQueries();
        }}
      />
      <p className="border-line text-muted border-t px-4 py-2.5 text-[12px]">
        Cost is an estimate at Claude API list prices; subscription plans are billed differently. Tokens are
        weighted by <code className="font-mono">[model_weights]</code> in the config.
      </p>
    </Card>
  );
}
