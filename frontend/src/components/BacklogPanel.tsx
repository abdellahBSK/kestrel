import { ListChecks, MessageSquare } from "lucide-react";
import type { Team } from "@/lib/api";
import { tokens } from "@/lib/format";
import { BACKLOG_SEGMENTS, BacklogBar } from "./BacklogBar";
import { Card, EmptyState, SectionTitle } from "./ui/primitives";

export function BacklogPanel({ team }: { team: Team }) {
  const total = Object.values(team.backlog).reduce((a, b) => a + b, 0);
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
      <div className="space-y-3">
        <Card className="p-5">
          <SectionTitle>Backlog</SectionTitle>
          {total === 0 ? (
            <EmptyState icon={<ListChecks />} title="No backlog yet">
              The lead builds it from the spec on the first run.
            </EmptyState>
          ) : (
            <>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="tabular text-[26px] font-semibold tracking-tight">
                  {Math.round((team.backlog.done / total) * 100)}%
                </span>
                <span className="text-muted text-[12.5px]">
                  {team.backlog.done} of {total} tasks merged
                </span>
              </div>
              <BacklogBar counts={team.backlog} className="mt-3 h-2" />
              <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2">
                {BACKLOG_SEGMENTS.map((s) => (
                  <li key={s.key} className="flex items-center gap-2 text-[12.5px]">
                    <span
                      className="ring-line size-2.5 rounded-[3px] ring-1"
                      style={{ background: s.color }}
                    />
                    <span className="text-ink-2">{s.label}</span>
                    <span className="text-ink tabular ml-auto font-medium">{team.backlog[s.key]}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
        <Card className="p-5">
          <SectionTitle>Token usage</SectionTitle>
          <dl className="mt-3 grid grid-cols-2 gap-4">
            <div>
              <dt className="text-muted text-[12px]">Today</dt>
              <dd className="tabular text-[18px] font-semibold tracking-tight">
                {tokens(team.today_tokens)}
              </dd>
            </div>
            <div>
              <dt className="text-muted text-[12px]">Last 7 days</dt>
              <dd className="tabular text-[18px] font-semibold tracking-tight">{tokens(team.week_tokens)}</dd>
            </div>
          </dl>
        </Card>
      </div>

      <Card className="p-5">
        <SectionTitle>Questions for you</SectionTitle>
        {team.questions ? (
          <>
            <div className="border-warning/40 bg-warning/[0.07] text-ink mt-3 rounded-lg border p-4 text-[13.5px] leading-relaxed whitespace-pre-wrap">
              {team.questions}
            </div>
            <p className="text-muted mt-3 text-[12px]">
              Answer by editing the team&apos;s STATE.md or BACKLOG.md, or its{" "}
              <code className="font-mono">focus</code> line in config.toml. The lead reads them at the start
              of the next run.
            </p>
          </>
        ) : (
          <EmptyState icon={<MessageSquare />} title="No open questions">
            Decisions the team can&apos;t make alone show up here after a run.
          </EmptyState>
        )}
      </Card>
    </div>
  );
}
