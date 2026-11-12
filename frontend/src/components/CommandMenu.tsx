import { Command } from "cmdk";
import { LayoutDashboard, Monitor, Moon, OctagonX, Play, Sun } from "lucide-react";
import { Dialog } from "radix-ui";
import { useEffect } from "react";
import type { Overview } from "@/lib/api";
import { relative } from "@/lib/format";
import { navigate } from "@/lib/router";
import type { ThemePref } from "@/lib/theme";
import { teamHealth } from "./Sidebar";
import { StatusDot } from "./ui/primitives";

const item =
  "flex h-9 cursor-default items-center gap-2.5 rounded-md px-2.5 text-[13.5px] text-ink outline-none select-none data-[selected=true]:bg-surface-2 [&_svg]:size-4 [&_svg]:text-muted";
const group =
  "px-1.5 [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pt-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted";

export function CommandMenu({
  open,
  setOpen,
  ov,
  setTheme,
  onStop,
  onResume,
}: {
  open: boolean;
  setOpen: (v: boolean) => void;
  ov: Overview | undefined;
  setTheme: (t: ThemePref) => void;
  onStop: () => void;
  onResume: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const run = (fn: () => void) => {
    setOpen(false);
    fn();
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="animate-fade-in fixed inset-0 z-50 bg-(--overlay) backdrop-blur-[2px]" />
        <Dialog.Content className="animate-pop-in border-line-strong bg-surface shadow-pop fixed top-[14vh] left-1/2 z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-xl border">
          <Dialog.Title className="sr-only">Command menu</Dialog.Title>
          <Dialog.Description className="sr-only">Jump to a project or run an action</Dialog.Description>
          <Command loop>
            <Command.Input
              autoFocus
              placeholder="Jump to a project or run a command…"
              className="border-line text-ink placeholder:text-muted h-12 w-full border-b bg-transparent px-4 text-[14px] outline-none"
            />
            <Command.List className="max-h-[min(380px,60vh)] overflow-y-auto pb-1.5">
              <Command.Empty className="text-muted py-10 text-center text-[13px]">No results.</Command.Empty>
              <Command.Group heading="Projects" className={group}>
                <Command.Item className={item} onSelect={() => run(() => navigate({ view: "overview" }))}>
                  <LayoutDashboard />
                  Overview
                </Command.Item>
                {ov?.teams.map((t) => (
                  <Command.Item
                    key={t.team}
                    value={`${t.team} ${t.key} ${t.title}`}
                    className={item}
                    onSelect={() => run(() => navigate({ view: "project", team: t.team, tab: "activity" }))}
                  >
                    <StatusDot status={teamHealth(t, ov)} className="mx-1" />
                    <span className="font-medium">{t.team}</span>
                    <span className="text-muted truncate">{t.title}</span>
                    <span className="text-muted ml-auto shrink-0 text-[12px]">
                      {t.running ? "running" : t.last_run_at ? relative(t.last_run_at) : ""}
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="Actions" className={group}>
                {ov?.stop ? (
                  <Command.Item className={item} onSelect={() => run(onResume)}>
                    <Play />
                    Resume agents
                  </Command.Item>
                ) : (
                  <Command.Item className={item} onSelect={() => run(onStop)}>
                    <OctagonX />
                    Stop all agents…
                  </Command.Item>
                )}
                <Command.Item className={item} onSelect={() => run(() => setTheme("light"))}>
                  <Sun />
                  Light theme
                </Command.Item>
                <Command.Item className={item} onSelect={() => run(() => setTheme("dark"))}>
                  <Moon />
                  Dark theme
                </Command.Item>
                <Command.Item className={item} onSelect={() => run(() => setTheme("system"))}>
                  <Monitor />
                  System theme
                </Command.Item>
              </Command.Group>
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
