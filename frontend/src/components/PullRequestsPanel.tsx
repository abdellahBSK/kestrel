import { ExternalLink, GitPullRequest, GitPullRequestDraft, Image, MonitorPlay, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useState } from "react";
import type { PullRequest, Team } from "@/lib/api";
import { relative } from "@/lib/format";
import { Button } from "./ui/button";
import { Badge, Card, EmptyState, SectionTitle } from "./ui/primitives";

function prState(p: PullRequest) {
  if (p.isDraft) return { label: "Draft", tone: "neutral" as const };
  switch (p.reviewDecision) {
    case "APPROVED":
      return { label: "Approved", tone: "good" as const };
    case "CHANGES_REQUESTED":
      return { label: "Changes requested", tone: "critical" as const };
    default:
      return { label: "Ready for review", tone: "info" as const };
  }
}

export function PullRequestsPanel({ team, onDemo }: { team: Team; onDemo: (pr: number) => void }) {
  const [shot, setShot] = useState<string | null>(null);
  return (
    <div className="space-y-6">
      <Card className="overflow-hidden">
        {team.prs.length === 0 ? (
          <EmptyState icon={<GitPullRequest />} title="No open pull requests">
            {team.pr_mode === "none"
              ? "This project is set to never open pull requests."
              : "Each finished backlog task becomes one pull request for you to review."}
          </EmptyState>
        ) : (
          <ul>
            {team.prs.map((p) => {
              const st = prState(p);
              const Icon = p.isDraft ? GitPullRequestDraft : GitPullRequest;
              return (
                <li
                  key={p.number}
                  className="border-line flex flex-wrap items-center gap-4 border-b px-4 py-3.5 last:border-0"
                >
                  <Icon className={p.isDraft ? "text-muted size-4" : "text-good size-4"} />
                  <div className="min-w-0 flex-1">
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-ink text-[13.5px] font-medium hover:underline"
                    >
                      {p.title}
                    </a>
                    <div className="text-muted mt-0.5 flex flex-wrap items-center gap-x-2 text-[12px]">
                      <span className="tabular">#{p.number}</span>
                      <span>·</span>
                      <span className="font-mono text-[11.5px]">{p.headRefName}</span>
                      <span>·</span>
                      <span>opened {relative(p.createdAt)}</span>
                    </div>
                  </div>
                  <Badge tone={st.tone}>{st.label}</Badge>
                  <div className="flex gap-1.5">
                    <Button size="sm" onClick={() => onDemo(p.number)}>
                      <MonitorPlay />
                      Demo
                    </Button>
                    <a href={`${p.url}/files`} target="_blank" rel="noopener noreferrer">
                      <Button size="sm" variant="ghost">
                        Files
                        <ExternalLink />
                      </Button>
                    </a>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <div>
        <SectionTitle>Latest screenshots</SectionTitle>
        {team.previews.length === 0 ? (
          <Card className="mt-3">
            <EmptyState icon={<Image />} title="No screenshots yet">
              Teams capture the screens a change touches and attach them to the pull request.
            </EmptyState>
          </Card>
        ) : (
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {team.previews.map((f) => (
              <button
                key={f}
                onClick={() => setShot(f)}
                className="group border-line bg-surface shadow-card hover:shadow-pop overflow-hidden rounded-xl border text-left transition-shadow"
              >
                <div className="bg-surface-2 aspect-[4/3] overflow-hidden">
                  <img
                    src={`/previews/${encodeURIComponent(team.team)}/${encodeURIComponent(f)}`}
                    alt={f}
                    loading="lazy"
                    className="size-full object-cover object-top transition-transform duration-300 group-hover:scale-[1.02]"
                  />
                </div>
                <div className="text-muted truncate px-3 py-2 font-mono text-[11.5px]">{f}</div>
              </button>
            ))}
          </div>
        )}
      </div>

      <Dialog.Root open={!!shot} onOpenChange={(o) => !o && setShot(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="animate-fade-in fixed inset-0 z-50 bg-black/75 backdrop-blur-sm" />
          <Dialog.Content className="animate-pop-in fixed inset-4 z-50 flex flex-col items-center justify-center outline-none">
            <Dialog.Title className="sr-only">{shot}</Dialog.Title>
            <Dialog.Description className="sr-only">Screenshot preview</Dialog.Description>
            {shot && (
              <img
                src={`/previews/${encodeURIComponent(team.team)}/${encodeURIComponent(shot)}`}
                alt={shot}
                className="shadow-pop max-h-full max-w-full rounded-lg object-contain"
              />
            )}
            <Dialog.Close asChild>
              <button
                className="absolute top-0 right-0 flex size-9 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20"
                aria-label="Close"
              >
                <X className="size-4" />
              </button>
            </Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
