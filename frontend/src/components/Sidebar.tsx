import {
  ChevronRight,
  Clock3,
  GitPullRequest,
  Globe,
  LayoutDashboard,
  MessageSquare,
  Monitor,
  Moon,
  Sun,
} from "lucide-react";
import { useState } from "react";
import type { Overview, Team } from "@/lib/api";
import { appName } from "@/lib/api";
import { browserOffsetMin, offsetLabel, relative } from "@/lib/format";
import type { TimePref } from "@/lib/theme";
import { HEALTH, HEALTH_ORDER } from "@/lib/health";
import { href, type Route } from "@/lib/router";
import type { ThemePref } from "@/lib/theme";
import { cn, roleLabel } from "@/lib/utils";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "./ui/overlays";
import { StatusDot, Tooltip, type DotStatus } from "./ui/primitives";

export function teamHealth(t: Team, ov: Overview): DotStatus {
  return t.running && ov.stop ? "stopping" : t.health;
}

/** One line on what the project is doing, matching its health. */
export function teamSummary(t: Team): { text: string; className: string } {
  switch (t.health) {
    case "running":
      return {
        text: t.now ? `${roleLabel(t.now.agent)} · working` : "Starting…",
        className: "text-good-ink",
      };
    case "stale":
      return { text: "An agent may be stuck", className: "text-ink" };
    case "lost":
      return { text: `Run lost · last activity ${relative(t.last_run_at)}`, className: "text-critical-ink" };
    case "failed":
      return { text: `Last run failed · ${relative(t.last_run_at)}`, className: "text-critical-ink" };
    case "incomplete":
      return { text: `Ran ${relative(t.last_run_at)} · unfinished work`, className: "text-ink-2" };
    case "idle":
      return { text: `Ran ${relative(t.last_run_at)}`, className: "text-muted" };
    default:
      return { text: "Not run yet", className: "text-muted" };
  }
}

/** What needs attention first (lost, failed, stuck, running), then most recently run. */
export function sortTeams(teams: Team[]) {
  const ran = teams.filter((t) => t.health !== "never");
  const never = teams.filter((t) => t.health === "never");
  const urgency = (t: Team) => Math.min(HEALTH_ORDER.indexOf(t.health), 4);
  ran.sort(
    (a, b) =>
      urgency(a) - urgency(b) ||
      new Date(b.last_run_at ?? 0).getTime() - new Date(a.last_run_at ?? 0).getTime(),
  );
  return { ran, never };
}

export function HealthDot({ t, ov, className }: { t: Team; ov: Overview; className?: string }) {
  const h = HEALTH[t.health];
  return (
    <Tooltip
      content={
        <span>
          <b className="font-semibold">{t.running && ov.stop ? "Stopping" : h.label}.</b> {h.hint}
        </span>
      }
    >
      <span className={cn("inline-flex", className)} aria-label={h.label}>
        <StatusDot status={teamHealth(t, ov)} />
      </span>
    </Tooltip>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8" className="fill-ink" />
      <rect x="7" y="17" width="4" height="8" rx="1.5" fill="var(--role-1)" />
      <rect x="14" y="11" width="4" height="14" rx="1.5" className="fill-page" />
      <rect x="21" y="7" width="4" height="18" rx="1.5" fill="var(--good)" />
    </svg>
  );
}

function ProjectRow({
  t,
  ov,
  active,
  onNavigate,
}: {
  t: Team;
  ov: Overview;
  active: boolean;
  onNavigate?: () => void;
}) {
  const sub = teamSummary(t);
  return (
    <a
      href={href({ view: "project", team: t.team, tab: "activity" })}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group flex items-center gap-2.5 rounded-lg px-2.5 py-2 transition-colors",
        active ? "bg-surface shadow-card ring-line ring-1" : "hover:bg-surface-2/70",
      )}
    >
      <HealthDot t={t} ov={ov} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className={cn("truncate text-[13px] font-medium", active ? "text-ink" : "text-ink/90")}>
            {t.team}
          </span>
          {!t.enabled && <span className="text-muted text-[10.5px]">off</span>}
        </div>
        <div className={cn("truncate text-[11.5px]", sub.className)}>{sub.text}</div>
      </div>
      <div className="text-muted flex items-center gap-1.5">
        {t.questions && (
          <Tooltip content="The team has questions for you">
            <MessageSquare className="text-ink-2 size-3.5" />
          </Tooltip>
        )}
        {t.prs.length > 0 && (
          <Tooltip content={`${t.prs.length} open pull request${t.prs.length > 1 ? "s" : ""}`}>
            <span className="text-ink-2 tabular flex items-center gap-0.5 text-[11px] font-medium">
              <GitPullRequest className="size-3.5" />
              {t.prs.length}
            </span>
          </Tooltip>
        )}
      </div>
    </a>
  );
}

export function Sidebar({
  ov,
  route,
  theme,
  setTheme,
  tz,
  setTz,
  onNavigate,
}: {
  ov: Overview | undefined;
  route: Route;
  theme: ThemePref;
  setTheme: (t: ThemePref) => void;
  tz: TimePref;
  setTz: (t: TimePref) => void;
  onNavigate?: () => void;
}) {
  const [showNever, setShowNever] = useState(false);
  const clocksDiffer = !!ov && ov.utc_offset_min !== browserOffsetMin();
  const { ran, never } = ov ? sortTeams(ov.teams) : { ran: [], never: [] };
  const current = route.view === "project" ? route.team : null;
  const ThemeIcon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center gap-2.5 px-4">
        <Logo className="size-6" />
        <div className="min-w-0">
          <div className="truncate text-[14px] leading-tight font-semibold tracking-tight">{appName}</div>
          {ov?.version && <div className="text-muted text-[10.5px] leading-tight">v{ov.version}</div>}
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-2.5 pt-1 pb-4">
        <a
          href={href({ view: "overview" })}
          onClick={onNavigate}
          aria-current={route.view === "overview" ? "page" : undefined}
          className={cn(
            "flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[13px] font-medium transition-colors",
            route.view === "overview"
              ? "bg-surface text-ink shadow-card ring-line ring-1"
              : "text-ink-2 hover:bg-surface-2/70 hover:text-ink",
          )}
        >
          <LayoutDashboard className="size-4" />
          Overview
        </a>

        <div>
          <div className="mb-1 flex items-center justify-between px-2.5">
            <span className="text-muted text-[11px] font-medium tracking-wide uppercase">Projects</span>
            <span className="text-muted tabular text-[11px]">{ov?.teams.length ?? ""}</span>
          </div>
          <div className="space-y-0.5">
            {ov &&
              ran.map((t) => (
                <ProjectRow key={t.team} t={t} ov={ov} active={current === t.team} onNavigate={onNavigate} />
              ))}
          </div>
          {ov && never.length > 0 && (
            <div className="mt-2">
              <button
                onClick={() => setShowNever((v) => !v)}
                className="text-muted hover:text-ink flex h-7 w-full items-center gap-1.5 rounded-md px-2.5 text-[12px] transition-colors"
                aria-expanded={showNever}
              >
                <ChevronRight className={cn("size-3.5 transition-transform", showNever && "rotate-90")} />
                Not run yet
                <span className="tabular ml-auto">{never.length}</span>
              </button>
              {(showNever || never.some((t) => t.team === current)) && (
                <div className="mt-0.5 space-y-0.5">
                  {never.map((t) => (
                    <ProjectRow
                      key={t.team}
                      t={t}
                      ov={ov}
                      active={current === t.team}
                      onNavigate={onNavigate}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </nav>

      <div className="border-line flex items-center justify-between border-t px-4 py-3">
        <span className="text-muted text-[11.5px]">Local only · no telemetry</span>
        <Menu>
          <MenuTrigger asChild>
            <button
              className="text-muted hover:bg-surface-2 hover:text-ink relative flex size-7 items-center justify-center rounded-md transition-colors"
              aria-label="Display settings"
            >
              <ThemeIcon className="size-4" />
              {clocksDiffer && <span className="bg-warning absolute top-1 right-1 size-1.5 rounded-full" />}
            </button>
          </MenuTrigger>
          <MenuContent>
            <MenuLabel>Times shown in</MenuLabel>
            <MenuItem icon={<Clock3 />} checked={tz === "computer"} onSelect={() => setTz("computer")}>
              This computer&apos;s clock{ov ? ` (${offsetLabel(ov.utc_offset_min)})` : ""}
            </MenuItem>
            <MenuItem icon={<Globe />} checked={tz === "browser"} onSelect={() => setTz("browser")}>
              The browser&apos;s time zone ({offsetLabel(browserOffsetMin())})
            </MenuItem>
            {clocksDiffer && (
              <p className="text-muted max-w-64 px-2 pt-1 pb-1.5 text-[11.5px] leading-snug">
                These disagree: the browser&apos;s time-zone data may be out of date. The computer&apos;s
                clock is what your taskbar shows.
              </p>
            )}
            <MenuSeparator />
            <MenuLabel>Theme</MenuLabel>
            <MenuItem icon={<Monitor />} checked={theme === "system"} onSelect={() => setTheme("system")}>
              System
            </MenuItem>
            <MenuItem icon={<Sun />} checked={theme === "light"} onSelect={() => setTheme("light")}>
              Light
            </MenuItem>
            <MenuItem icon={<Moon />} checked={theme === "dark"} onSelect={() => setTheme("dark")}>
              Dark
            </MenuItem>
          </MenuContent>
        </Menu>
      </div>
    </div>
  );
}
