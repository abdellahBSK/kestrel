// How each project health and agent state is shown. The server decides the state (status.py);
// the UI only explains it. Status color always comes with a label and an icon or dot shape.

import type { AgentState, Health } from "./api";

export type Tone = "good" | "warning" | "critical" | "neutral" | "muted";

export const HEALTH: Record<Health, { label: string; tone: Tone; hint: string }> = {
  running: { label: "Running", tone: "good", hint: "A run is in progress and its runner is checking in." },
  stale: {
    label: "May be stuck",
    tone: "warning",
    hint: "The run is alive, but an agent has shown no activity for a long time.",
  },
  lost: {
    label: "Run lost",
    tone: "critical",
    hint: "The runner stopped checking in before the run finished (crash, sleep or closed window). No agent is working.",
  },
  failed: { label: "Last run failed", tone: "critical", hint: "The last run ended with an error." },
  incomplete: {
    label: "Unfinished work",
    tone: "warning",
    hint: "The last run ended while an agent was still mid-task, so part of its work may be missing.",
  },
  idle: { label: "Idle", tone: "neutral", hint: "No run in progress." },
  never: { label: "Never run", tone: "muted", hint: "This project has not run yet." },
};

export const AGENT: Record<AgentState, { label: string; tone: Tone; hint: string }> = {
  working: { label: "Working", tone: "good", hint: "Active in the current run." },
  waiting: { label: "Waiting on agents", tone: "neutral", hint: "Waiting for the agents it delegated to." },
  idle: {
    label: "Idle",
    tone: "neutral",
    hint: "No new activity for a couple of minutes: usually a long command such as an install or a test suite.",
  },
  stale: {
    label: "No activity",
    tone: "warning",
    hint: "Nothing new for a long time while the run is still alive: it may be stuck.",
  },
  finished: { label: "Finished", tone: "muted", hint: "Done, and reported back." },
  lost: {
    label: "Cut off",
    tone: "critical",
    hint: "The run ended before this agent reported back, so its last task may be incomplete.",
  },
  failed: { label: "Failed", tone: "critical", hint: "The run ended with an error." },
};

/** The worst project health first: what deserves attention. */
export const HEALTH_ORDER: Health[] = ["lost", "failed", "stale", "running", "incomplete", "idle", "never"];
