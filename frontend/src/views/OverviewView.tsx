import { ArrowUpRight, CalendarDays, FolderGit2, GitPullRequest, MessageSquare } from "lucide-react";
import { BacklogBar } from "@/components/BacklogBar";
import { HealthDot, sortTeams, teamSummary } from "@/components/Sidebar";
import { UsageChart } from "@/components/UsageChart";
import {
  Card,
  EmptyState,
  KeyBadge,
  Meter,
  SectionTitle,
  Skeleton,
  Tooltip,
} from "@/components/ui/primitives";
import type { Overview } from "@/lib/api";
import { clock, integer, percent, tokens, usd } from "@/lib/format";
import { href } from "@/lib/router";
import { cn } from "@/lib/utils";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function Kpi({
  label,
  value,
  sub,
  meter,
}: {
  label: string;
  value: string;
  sub: React.ReactNode;
  meter?: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col gap-1 p-4">
      <span className="text-ink-2 text-[12.5px]">{label}</span>
      <span className="text-[26px] leading-tight font-semibold tracking-tight">{value}</span>
      <span className="text-muted text-[12px]">{sub}</span>
      {meter && <div className="mt-2">{meter}</div>}
    </Card>
  );
}

export function OverviewView({ ov }: { ov: Overview | undefined }) {
  if (!ov) return <OverviewSkeleton />;
  const b = ov.budget;
  const { ran, never } = sortTeams(ov.teams);
  const teams = [...ran, ...never];
  const prs = ov.teams.reduce((n, t) => n + t.prs.length, 0);
  const asks = ov.teams.filter((t) => t.questions).length;

  return (
    <div className="mx-auto max-w-[1280px] space-y-6 px-4 py-6 lg:px-8 lg:py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight">Overview</h1>
          <p className="text-ink-2 mt-0.5 text-[13.5px]">
            {ov.teams.length} projects · {prs} open pull request{prs === 1 ? "" : "s"}
            {asks > 0 && ` · ${asks} waiting on your answer`}
          </p>
        </div>
        {ov.generated_at && (
          <span className="text-muted tabular text-[12px]">Updated {clock(ov.generated_at)}</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Kpi
          label="Agents today"
          value={tokens(b.agents_today)}
          sub={
            b.agents_daily
              ? `${percent(b.agents_today, b.agents_daily)} of the ${tokens(b.agents_daily)} daily budget`
              : "No daily budget set"
          }
          meter={
            <Meter
              value={b.agents_today}
              cap={b.agents_daily}
              warnAt={b.warn_at}
              color="var(--series-agents)"
            />
          }
        />
        <Kpi
          label="Agents, last 7 days"
          value={tokens(b.agents_week)}
          sub={
            b.agents_weekly
              ? `${percent(b.agents_week, b.agents_weekly)} of the ${tokens(b.agents_weekly)} weekly budget`
              : "No weekly budget set"
          }
          meter={
            <Meter
              value={b.agents_week}
              cap={b.agents_weekly}
              warnAt={b.warn_at}
              color="var(--series-agents)"
            />
          }
        />
        <Kpi
          label="Est. cost today"
          value={usd(b.usd_today) + (b.usd_partial ? "+" : "")}
          sub={
            <Tooltip
              content={`At Claude API list prices (${b.prices_as_of}), for everything reported to ${ov.name}, your own Claude Code sessions included.${b.usd_partial ? " Some tokens are from models without a price: add them under [prices] in config.toml." : ""} Subscription plans are billed differently.`}
            >
              <span className="cursor-default">{usd(b.usd_week)} over the last 7 days</span>
            </Tooltip>
          }
        />
        {b.agents_daily ? (
          <Kpi label="Left for agents today" value={tokens(b.pool)} sub="After daily and weekly caps" />
        ) : b.you_week > 0 ? (
          <Kpi
            label="Your usage today"
            value={tokens(b.you_today)}
            sub={`${tokens(b.you_week)} over the last 7 days`}
          />
        ) : (
          <Kpi
            label="Live runs"
            value={String(ov.live_runs.length)}
            sub={ov.live_runs.length ? ov.live_runs.map((r) => r.team).join(", ") : "Nothing running"}
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="p-5">
          <SectionTitle>Token usage, last 7 days</SectionTitle>
          <p className="text-muted mb-4 text-[12px]">Opus-equivalent tokens: input + output + cache writes</p>
          {b.daily?.length ? (
            <UsageChart data={b.daily} cap={b.agents_daily} />
          ) : (
            <p className="text-muted py-10 text-center text-[13px]">No usage data yet.</p>
          )}
        </Card>

        <Card className="p-5">
          <SectionTitle>Schedule</SectionTitle>
          <p className="text-muted mb-3 text-[12px]">Projects that run each day, in order</p>
          <ol className="space-y-1">
            {DAYS.map((d) => {
              const isToday = d === ov.today;
              const list = ov.schedule[d] ?? [];
              return (
                <li
                  key={d}
                  className={cn(
                    "flex items-start gap-3 rounded-lg px-2.5 py-2",
                    isToday && "bg-surface-2 ring-line ring-1",
                  )}
                >
                  <span
                    className={cn(
                      "w-9 pt-px text-[12px] capitalize",
                      isToday ? "text-ink font-semibold" : "text-muted",
                    )}
                  >
                    {d}
                  </span>
                  <div className="flex min-w-0 flex-1 flex-wrap gap-1">
                    {list.length ? (
                      list.map((t) => (
                        <a
                          key={t}
                          href={href({ view: "project", team: t, tab: "activity" })}
                          className="border-line-strong bg-surface text-ink hover:border-ink/30 rounded-md border px-1.5 py-px text-[12px] transition-colors"
                        >
                          {t}
                        </a>
                      ))
                    ) : (
                      <span className="text-muted text-[12px]">Rest day</span>
                    )}
                  </div>
                  {isToday && <CalendarDays className="text-muted mt-0.5 size-3.5" />}
                </li>
              );
            })}
          </ol>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <div className="px-5 pt-5 pb-3">
          <SectionTitle>Projects</SectionTitle>
        </div>
        {teams.length === 0 ? (
          <EmptyState icon={<FolderGit2 />} title="No projects configured">
            Add a <code className="font-mono">[teams.&lt;name&gt;]</code> block to your config.toml.
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-[13px]">
              <thead>
                <tr className="border-line bg-surface-2/50 text-muted border-y text-left text-[12px]">
                  <th className="py-2 pr-3 pl-5 font-medium">Project</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 text-right font-medium">Today</th>
                  <th className="px-3 py-2 text-right font-medium">7 days</th>
                  <th className="w-[200px] px-3 py-2 font-medium">Backlog</th>
                  <th className="py-2 pr-5 pl-3 text-right font-medium whitespace-nowrap">Needs you</th>
                </tr>
              </thead>
              <tbody>
                {teams.map((t) => {
                  const summary = teamSummary(t);
                  const total = Object.values(t.backlog).reduce((a, c) => a + c, 0);
                  return (
                    <tr
                      key={t.team}
                      className="group border-line hover:bg-surface-2/50 border-b transition-colors last:border-0"
                    >
                      <td className="py-3 pr-3 pl-5">
                        <a
                          href={href({ view: "project", team: t.team, tab: "activity" })}
                          className="flex items-center gap-2.5"
                        >
                          <HealthDot t={t} ov={ov} />
                          <span className="text-ink font-medium group-hover:underline group-hover:underline-offset-2">
                            {t.team}
                          </span>
                          {t.key && <KeyBadge>{t.key}</KeyBadge>}
                          {t.mode === "advisory" && (
                            <span className="text-muted text-[11.5px]">advisory</span>
                          )}
                        </a>
                        <div className="text-muted mt-0.5 max-w-[360px] truncate pl-[18px] text-[12px]">
                          {t.title}
                        </div>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        {t.running ? (
                          <span className="text-good-ink">Running · {tokens(t.used)} used</span>
                        ) : (
                          <span
                            className={summary.className === "text-muted" ? "text-ink-2" : summary.className}
                          >
                            {summary.text}
                          </span>
                        )}
                        {t.scheduled_today && !t.running && (
                          <span className="text-muted ml-2 text-[11.5px]">· scheduled today</span>
                        )}
                      </td>
                      <td className="text-ink-2 tabular px-3 py-3 text-right">
                        {t.today_tokens ? tokens(t.today_tokens) : "–"}
                        {t.today_usd > 0 && <div className="text-muted text-[12px]">{usd(t.today_usd)}</div>}
                      </td>
                      <td className="text-ink-2 tabular px-3 py-3 text-right">
                        {t.week_tokens ? tokens(t.week_tokens) : "–"}
                        {t.week_usd > 0 && <div className="text-muted text-[12px]">{usd(t.week_usd)}</div>}
                      </td>
                      <td className="px-3 py-3">
                        {total ? (
                          <Tooltip
                            content={`${t.backlog.done} done · ${t.backlog.review} in review · ${t.backlog.doing} in progress · ${t.backlog.blocked} blocked · ${t.backlog.todo} to do`}
                          >
                            <div className="flex items-center gap-2.5">
                              <BacklogBar counts={t.backlog} className="flex-1" />
                              <span className="text-muted tabular text-[12px]">
                                {t.backlog.done}/{total}
                              </span>
                            </div>
                          </Tooltip>
                        ) : (
                          <span className="text-muted text-[12px]">No backlog yet</span>
                        )}
                      </td>
                      <td className="py-3 pr-5 pl-3">
                        <div className="flex items-center justify-end gap-3 text-[12.5px] whitespace-nowrap">
                          {t.prs.length > 0 && (
                            <a
                              href={href({ view: "project", team: t.team, tab: "prs" })}
                              className="text-ink inline-flex items-center gap-1 hover:underline"
                            >
                              <GitPullRequest className="text-muted size-3.5" />
                              {integer(t.prs.length)} PR{t.prs.length > 1 ? "s" : ""}
                            </a>
                          )}
                          {t.questions && (
                            <a
                              href={href({ view: "project", team: t.team, tab: "backlog" })}
                              className="text-ink inline-flex items-center gap-1 hover:underline"
                            >
                              <MessageSquare className="text-muted size-3.5" />
                              Questions
                            </a>
                          )}
                          {!t.prs.length && !t.questions && <span className="text-muted">–</span>}
                          <ArrowUpRight className="text-muted size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="mx-auto max-w-[1280px] space-y-6 px-4 py-6 lg:px-8 lg:py-8">
      <Skeleton className="h-8 w-48" />
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[118px] rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-[320px] rounded-xl" />
      <Skeleton className="h-[260px] rounded-xl" />
    </div>
  );
}
