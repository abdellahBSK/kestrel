import { WifiOff, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useEffect, useRef, useState } from "react";
import { Toaster } from "sonner";
import { CommandMenu } from "@/components/CommandMenu";
import { Sidebar } from "@/components/Sidebar";
import { Topbar, useStopControls } from "@/components/Topbar";
import { appName } from "@/lib/api";
import { useOverview } from "@/lib/queries";
import { useRoute } from "@/lib/router";
import { useTheme } from "@/lib/theme";
import { OverviewView } from "@/views/OverviewView";
import { ProjectView } from "@/views/ProjectView";

export function App() {
  const route = useRoute();
  const { pref, set: setTheme } = useTheme();
  const { data: ov, isError, failureCount } = useOverview();
  const controls = useStopControls();
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  const page = route.view === "project" ? route.team : "overview";

  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 });
  }, [page]);

  useEffect(() => {
    const running = ov?.running ? `● ${ov.running.team} · ` : "";
    const where = route.view === "project" ? `${route.team} · ` : "";
    document.title = `${running}${where}${appName}`;
  }, [ov?.running, route]);

  const sidebar = (onNavigate?: () => void) => (
    <Sidebar ov={ov} route={route} theme={pref} setTheme={setTheme} onNavigate={onNavigate} />
  );

  return (
    <div className="flex h-full">
      <aside className="border-line bg-page hidden w-[272px] shrink-0 border-r lg:block">{sidebar()}</aside>

      <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="animate-fade-in fixed inset-0 z-50 bg-(--overlay) lg:hidden" />
          <Dialog.Content className="animate-fade-in border-line bg-page shadow-pop fixed inset-y-0 left-0 z-50 w-[288px] max-w-[85vw] border-r outline-none lg:hidden">
            <Dialog.Title className="sr-only">Navigation</Dialog.Title>
            <Dialog.Description className="sr-only">Projects and pages</Dialog.Description>
            <Dialog.Close asChild>
              <button
                className="text-muted hover:bg-surface-2 hover:text-ink absolute top-3.5 right-3 flex size-7 items-center justify-center rounded-md"
                aria-label="Close navigation"
              >
                <X className="size-4" />
              </button>
            </Dialog.Close>
            {sidebar(() => setMenuOpen(false))}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          ov={ov}
          route={route}
          controls={controls}
          onOpenMenu={() => setMenuOpen(true)}
          onOpenSearch={() => setSearchOpen(true)}
        />
        {isError && failureCount > 1 && (
          <div className="border-critical/30 bg-critical/[0.07] text-ink flex items-center gap-2 border-b px-4 py-2 text-[13px] lg:px-8">
            <WifiOff className="text-critical-ink size-4" />
            Can&apos;t reach the {appName} server. Is{" "}
            <code className="font-mono text-[12px]">controlroom watch</code> still running? Retrying…
          </div>
        )}
        <main ref={mainRef} className="min-h-0 flex-1 overflow-y-auto">
          {route.view === "project" ? (
            <ProjectView key={route.team} ov={ov} team={route.team} tab={route.tab} />
          ) : (
            <OverviewView ov={ov} />
          )}
        </main>
      </div>

      <CommandMenu
        open={searchOpen}
        setOpen={setSearchOpen}
        ov={ov}
        setTheme={setTheme}
        onStop={() => controls.setConfirmStop(true)}
        onResume={controls.resume}
      />
      <Toaster
        theme={pref}
        position="bottom-right"
        toastOptions={{
          classNames: {
            toast: "!bg-surface !border-line-strong !text-ink !shadow-pop !rounded-lg !text-[13px]",
            description: "!text-ink-2",
          },
        }}
      />
    </div>
  );
}
