import { Bell, BellOff, CircleX, Info, TriangleAlert } from "lucide-react";
import { Popover } from "radix-ui";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import type { Alert, Overview } from "@/lib/api";
import { relative } from "@/lib/format";
import { href } from "@/lib/router";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";

const KEY = "kestrel.dismissed-alerts";

function loadDismissed(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(KEY) || "[]") as string[]);
  } catch {
    return new Set();
  }
}

function saveDismissed(ids: Set<string>) {
  try {
    localStorage.setItem(KEY, JSON.stringify([...ids].slice(-500)));
  } catch {
    // private window or blocked storage: dismissals last until reload
  }
}

/** The level is shown by an icon and a word, never by color alone. */
function LevelIcon({ a }: { a: Alert }) {
  if (a.level === "critical")
    return <CircleX className="text-critical mt-0.5 size-4 shrink-0" aria-label="Critical" />;
  if (a.level === "warning")
    return <TriangleAlert className="text-warning mt-0.5 size-4 shrink-0" aria-label="Warning" />;
  return <Info className="text-info mt-0.5 size-4 shrink-0" aria-label="Info" />;
}

function link(a: Alert): string {
  if (a.project === "*") return "#/";
  return href({
    view: "project",
    team: a.project,
    tab: a.kind === "pr" ? "prs" : a.kind === "stuck" ? "agents" : "activity",
  });
}

/** The bell in the top bar: what needs you now, and a toast when something critical happens. */
export function AlertsMenu({ ov }: { ov: Overview | undefined }) {
  const [dismissed, setDismissed] = useState(loadDismissed);
  const alerts = useMemo(() => (ov?.alerts ?? []).filter((a) => !dismissed.has(a.id)), [ov, dismissed]);
  const critical = alerts.filter((a) => a.level === "critical").length;

  // Toast critical alerts that appear while the page is open (not the ones already there on load).
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!ov) return;
    const ids = new Set(ov.alerts.map((a) => a.id));
    if (seen.current) {
      for (const a of ov.alerts) {
        if (a.level === "critical" && !seen.current.has(a.id) && !dismissed.has(a.id)) {
          toast.error(a.title, {
            description: a.detail || undefined,
            action: { label: "Open", onClick: () => (location.hash = link(a)) },
          });
        }
      }
    }
    seen.current = new Set([...(seen.current ?? []), ...ids]);
  }, [ov, dismissed]);

  const dismiss = (ids: string[]) => {
    const next = new Set([...dismissed, ...ids]);
    setDismissed(next);
    saveDismissed(next);
  };

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={alerts.length ? `${alerts.length} alerts` : "No alerts"}
          disabled={!ov}
        >
          <Bell />
          {alerts.length > 0 && (
            <span
              className={cn(
                "tabular absolute -top-0.5 -right-0.5 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10.5px] font-semibold",
                critical ? "bg-critical text-white" : "bg-ink text-page",
              )}
            >
              {alerts.length}
            </span>
          )}
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="animate-pop-in border-line-strong bg-surface shadow-pop z-50 w-[min(380px,calc(100vw-24px))] rounded-xl border"
        >
          <div className="border-line flex items-center justify-between border-b px-4 py-2.5">
            <span className="text-[13px] font-semibold">Alerts</span>
            {alerts.length > 0 && (
              <button
                className="text-muted hover:text-ink text-[12px] transition-colors"
                onClick={() => dismiss(alerts.map((a) => a.id))}
              >
                Dismiss all
              </button>
            )}
          </div>
          {alerts.length === 0 ? (
            <div className="text-muted flex flex-col items-center gap-2 px-4 py-8 text-center text-[13px]">
              <BellOff className="size-5" />
              Nothing needs you right now.
            </div>
          ) : (
            <ul className="max-h-[420px] overflow-y-auto py-1">
              {alerts.map((a) => (
                <li key={a.id} className="group hover:bg-surface-2/60 flex gap-3 px-4 py-2.5">
                  <LevelIcon a={a} />
                  <Popover.Close asChild>
                    <a href={link(a)} className="min-w-0 flex-1">
                      <div className="text-ink text-[13px] leading-snug font-medium">{a.title}</div>
                      {a.detail && (
                        <div className="text-ink-2 mt-0.5 line-clamp-2 text-[12.5px]">{a.detail}</div>
                      )}
                      <div className="text-muted mt-0.5 text-[11.5px]">{relative(a.ts)}</div>
                    </a>
                  </Popover.Close>
                  <button
                    className="text-muted hover:text-ink h-fit text-[11.5px] opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
                    onClick={() => dismiss([a.id])}
                    aria-label={`Dismiss: ${a.title}`}
                  >
                    Dismiss
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="border-line text-muted border-t px-4 py-2 text-[11.5px]">
            While the dashboard runs, new alerts also go to your desktop and to <code>[alerts] webhook</code>.
          </p>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
