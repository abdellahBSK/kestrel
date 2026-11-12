import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  ChevronDown,
  Ellipsis,
  FolderSearch,
  GitPullRequest,
  ListChecks,
  MonitorPlay,
  Play,
} from "lucide-react";
import { Tabs } from "radix-ui";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ActivityFeed } from "@/components/ActivityFeed";
import { AgentsTable, agentState } from "@/components/AgentsTable";
import { BacklogPanel } from "@/components/BacklogPanel";
import { PullRequestsPanel } from "@/components/PullRequestsPanel";
import { Button } from "@/components/ui/button";
import {
  ConfirmDialog,
  Menu,
  MenuContent,
  MenuItem,
  MenuLabel,
  MenuSeparator,
  MenuTrigger,
} from "@/components/ui/overlays";
import { Badge, Card, EmptyState, KeyBadge, Meter, Skeleton, StatusDot } from "@/components/ui/primitives";
import { action, type Overview, type Session } from "@/lib/api";
import { dateTime, duration, integer, relative, tokens } from "@/lib/format";
import { useSession } from "@/lib/queries";
import { navigate, type Tab } from "@/lib/router";
import { cn } from "@/lib/utils";

function Stat({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0 px-4 py-3.5", className)}>
      <div className="text-muted text-[12px]">{label}</div>
      <div className="mt-1 truncate text-[15px] font-semibold tracking-tight">{children}</div>
    </div>
  );
}

function sessionSpan(s: Session | undefined) {
  const times = (s?.events ?? []).map((e) => e.ts).filter(Boolean) as string[];
  if (!times.length) return { start: null, end: null };
  return { start: times[0]!, end: times[times.length - 1]! };
}

export function ProjectView({ ov, team, tab }: { ov: Overview | undefined; team: string; tab: Tab }) {
  const qc = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [confirmRun, setConfirmRun] = useState(false);
  const t = ov?.teams.find((x) => x.team === team);
  const { data: s, isLoading } = useSession(team, sessionId, !!t?.running);
  const [prevTeam, setPrevTeam] = useState(team);
  if (prevTeam !== team) {
    setPrevTeam(team);
    setSessionId(null);
  }

  const span = useMemo(() => sessionSpan(s), [s]);
  const runTokens = useMemo(() => (s?.agents ?? []).reduce((a, x) => a + x.tokens, 0), [s]);
  const working = useMemo(
    () => (s?.agents ?? []).filter((a) => agentState(a, !!s?.live, s?.events ?? []).key === "working").length,
    [s],
  );

  if (!ov) return <ProjectSkeleton />;
  if (!t)
    return (
      <EmptyState icon={<FolderSearch />} title={`No project called “${team}”`}>
        It may have been removed from the config.{" "}
        <a className="text-ink underline" href="#/">
          Back to the overview
        </a>
      </EmptyState>
    );

  const doAction = async (path: string) => {
    const res = await action(path);
    if (res.ok) toast.success(res.msg);
    else toast.error(res.msg);
    qc.invalidateQueries();
  };
  const actions = (s?.events ?? []).filter((e) => e.kind === "tool" || e.kind === "delegate").length;
  const isLatest = !sessionId || sessionId === s?.sessions[0]?.id;
  const current = s?.sessions.find((x) => x.id === s.session);
  const blockedRun = !!ov.running || ov.stop;

  return (
    <div className="mx-auto max-w-[1280px] px-4 py-6 lg:px-8 lg:py-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[22px] font-semibold tracking-tight">{t.team}</h1>
            <KeyBadge>{t.key}</KeyBadge>
            {t.mode === "advisory" && <Badge tone="outline">Advisory · read-only</Badge>}
            {t.pr_mode === "draft" && <Badge tone="outline">Draft PRs</Badge>}
            {!t.enabled && <Badge tone="outline">Disabled</Badge>}
            {t.scheduled_today && <Badge>Scheduled today</Badge>}
          </div>
          <p className="text-ink-2 mt-1 max-w-2xl text-[13.5px]">{t.title}</p>
        </div>

        <div className="flex items-center gap-2">
          {s && s.sessions.length > 0 && (
            <Menu>
              <MenuTrigger asChild>
                <Button variant="secondary">
                  <span className="text-muted">Run</span>
                  {current?.updated_at ? dateTime(current.updated_at) : current?.when}
                  <ChevronDown className="text-muted" />
                </Button>
              </MenuTrigger>
              <MenuContent>
                <MenuLabel>Past runs (last activity)</MenuLabel>
                {s.sessions.map((x, i) => (
                  <MenuItem key={x.id} checked={x.id === s.session} onSelect={() => setSessionId(x.id)}>
                    {x.updated_at ? dateTime(x.updated_at) : x.when}
                    {i === 0 && <span className="text-muted ml-2 text-[11.5px]">latest</span>}
                  </MenuItem>
                ))}
              </MenuContent>
            </Menu>
          )}
          <Button variant="primary" disabled={blockedRun} onClick={() => setConfirmRun(true)}>
            <Play />
            Run now
          </Button>
          <Menu>
            <MenuTrigger asChild>
              <Button variant="secondary" size="icon" aria-label="More actions">
                <Ellipsis />
              </Button>
            </MenuTrigger>
            <MenuContent>
              <MenuItem
                icon={<MonitorPlay />}
                onSelect={() => doAction(`/api/demo?team=${encodeURIComponent(team)}&pr=`)}
              >
                Demo the default branch
              </MenuItem>
              <MenuSeparator />
              <MenuItem
                icon={<GitPullRequest />}
                onSelect={() => navigate({ view: "project", team, tab: "prs" })}
              >
                Open pull requests
              </MenuItem>
            </MenuContent>
          </Menu>
        </div>
      </div>

      <Card className="divide-line [&>*]:border-line mt-5 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 lg:divide-x max-lg:[&>*]:border-b">
        <Stat label="Status">
          <span className="inline-flex items-center gap-2">
            <StatusDot
              status={t.running ? (ov.stop ? "stopped" : "working") : t.last_run_at ? "idle" : "never"}
            />
            {t.running ? (ov.stop ? "Stopping" : "Running") : t.last_run_at ? "Idle" : "Never run"}
          </span>
        </Stat>
        <Stat label={t.running && isLatest ? "This run" : "Run tokens"}>
          {t.running && isLatest ? (
            <div>
              <span className="tabular">
                {tokens(t.used)} <span className="text-muted font-normal">/ {tokens(t.allowance)}</span>
              </span>
              <Meter value={t.used} cap={t.allowance} warnAt={ov.budget.warn_at} className="mt-1.5" />
            </div>
          ) : (
            <span className="tabular">{s?.session ? tokens(runTokens) : "–"}</span>
          )}
        </Stat>
        <Stat label="Agents">
          <span className="tabular">
            {s?.agents.length ? (
              <>
                {integer(s.agents.length)}
                {working > 0 && <span className="text-good-ink font-normal"> · {working} working</span>}
              </>
            ) : (
              "–"
            )}
          </span>
        </Stat>
        <Stat label="Actions">
          <span className="tabular">{s?.session ? integer(actions) : "–"}</span>
        </Stat>
        <Stat label="Duration">
          <span className="tabular">
            {duration(span.start, s?.live ? new Date().toISOString() : span.end)}
          </span>
        </Stat>
        <Stat label="Last activity">
          <span className="text-ink-2 font-normal">{span.end ? relative(span.end) : "–"}</span>
        </Stat>
      </Card>

      <Tabs.Root
        value={tab}
        onValueChange={(v) => navigate({ view: "project", team, tab: v as Tab })}
        className="mt-6"
      >
        <Tabs.List className="border-line flex gap-1 border-b" aria-label="Project sections">
          {(
            [
              ["activity", "Activity", <Activity key="i" />, s?.events.length],
              ["agents", "Agents", <Bot key="i" />, s?.agents.length],
              ["prs", "Pull requests", <GitPullRequest key="i" />, t.prs.length],
              ["backlog", "Backlog & questions", <ListChecks key="i" />, undefined],
            ] as const
          ).map(([value, label, icon, count]) => (
            <Tabs.Trigger
              key={value}
              value={value}
              className="text-muted hover:text-ink data-[state=active]:border-ink data-[state=active]:text-ink relative -mb-px flex h-10 items-center gap-2 border-b-2 border-transparent px-3 text-[13px] font-medium transition-colors [&_svg]:size-4"
            >
              {icon}
              <span className="hidden sm:inline">{label}</span>
              {count !== undefined && count > 0 && (
                <span className="bg-surface-2 text-ink-2 tabular rounded-full px-1.5 text-[11px]">
                  {count}
                </span>
              )}
              {value === "backlog" && t.questions && <span className="bg-warning size-1.5 rounded-full" />}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <div className="pt-5">
          <Tabs.Content value="activity" className="outline-none">
            {isLoading ? <Skeleton className="h-96 rounded-xl" /> : <ActivityFeed session={s} />}
          </Tabs.Content>
          <Tabs.Content value="agents" className="outline-none">
            {isLoading ? <Skeleton className="h-64 rounded-xl" /> : <AgentsTable session={s} />}
          </Tabs.Content>
          <Tabs.Content value="prs" className="outline-none">
            <PullRequestsPanel
              team={t}
              onDemo={(pr) => doAction(`/api/demo?team=${encodeURIComponent(team)}&pr=${pr}`)}
            />
          </Tabs.Content>
          <Tabs.Content value="backlog" className="outline-none">
            <BacklogPanel team={t} />
          </Tabs.Content>
        </div>
      </Tabs.Root>

      <ConfirmDialog
        open={confirmRun}
        onOpenChange={setConfirmRun}
        title={`Run ${t.team} now?`}
        description={
          <>
            The team starts immediately and can use up to <b className="text-ink">{tokens(ov.budget.pool)}</b>{" "}
            tokens, the agent budget still available today.
          </>
        }
        confirm="Start run"
        onConfirm={() => doAction(`/api/run?team=${encodeURIComponent(team)}`)}
      />
    </div>
  );
}

function ProjectSkeleton() {
  return (
    <div className="mx-auto max-w-[1280px] space-y-5 px-4 py-6 lg:px-8 lg:py-8">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-[74px] rounded-xl" />
      <Skeleton className="h-10 w-96" />
      <Skeleton className="h-96 rounded-xl" />
    </div>
  );
}
