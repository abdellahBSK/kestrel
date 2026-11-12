// Types and calls for the local server's JSON API (src/controlroom/server.py).

export type BacklogCounts = { todo: number; doing: number; review: number; done: number; blocked: number };

export type PullRequest = {
  number: number;
  title: string;
  url: string;
  isDraft: boolean;
  headRefName: string;
  createdAt: string;
  reviewDecision: string;
};

/** Project health, decided by the server (src/controlroom/status.py). */
export type Health = "running" | "stale" | "lost" | "failed" | "incomplete" | "idle" | "never";
export type AgentState = "working" | "waiting" | "idle" | "stale" | "finished" | "lost" | "failed";

export type Run = {
  team: string;
  session: string;
  since: number;
  started_at?: string;
  allowance: number;
  state: "running" | "lost";
  last_heartbeat: number;
};

export type Team = {
  team: string;
  title: string;
  key: string;
  mode: "build" | "advisory";
  pr_mode: "ready" | "draft" | "none";
  enabled: boolean;
  scheduled_today: boolean;
  running: boolean;
  run_state: "running" | "lost" | null;
  health: Health;
  heartbeat_at: string | null;
  now: { agent: string; text: string; ts: string } | null;
  allowance: number;
  used: number;
  started_at: string | null;
  last_run_at: string | null;
  today_tokens: number;
  week_tokens: number;
  backlog: BacklogCounts;
  prs: PullRequest[];
  questions: string;
  previews: string[];
};

export type DailyUsage = { date: string; agents: number; personal: number };

export type Overview = {
  generated_at: string;
  utc_offset_min: number;
  name: string;
  version: string;
  stop: boolean;
  running: Run | null;
  lost_run: Run | null;
  budget: {
    agents_today: number;
    agents_daily: number;
    agents_week: number;
    agents_weekly: number;
    you_today: number;
    you_week: number;
    pool: number;
    warn_at: number;
    daily: DailyUsage[];
  };
  schedule: Record<string, string[]>;
  today: string;
  teams: Team[];
};

export type FeedEvent = {
  ts: string | null;
  agent: string;
  kind: "say" | "tool" | "delegate" | "budget" | "halt";
  tool?: string;
  text: string;
  status?: "running" | "ok" | "error" | "blocked";
  result?: string;
};

export type Agent = {
  role: string;
  description: string;
  state: AgentState;
  finished: boolean;
  last_activity: string;
  tokens: number;
  actions: number;
  model: string;
  start?: string | null;
  end?: string | null;
};

export type Session = {
  team: string;
  session: string | null;
  live: boolean;
  started_at?: string | null;
  sessions: { id: string; started_at: string | null; updated_at: string }[];
  events: FeedEvent[];
  agents: Agent[];
};

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

export const api = {
  overview: () => getJSON<Overview>("/api/overview"),
  session: (team: string, id?: string | null) =>
    getJSON<Session>(
      `/api/session?team=${encodeURIComponent(team)}${id ? `&id=${encodeURIComponent(id)}` : ""}`,
    ),
};

/** Actions need a same-origin request with a custom header (the server rejects anything else). */
export async function action(path: string): Promise<{ ok: boolean; msg: string }> {
  const r = await fetch(path, { method: "POST", headers: { "X-Kingdom": "1" } });
  const body = await r.json().catch(() => ({ ok: false, msg: `Request failed (${r.status})` }));
  return body as { ok: boolean; msg: string };
}

export const appName =
  document.querySelector('meta[name="app-name"]')?.getAttribute("content")?.replace("__APP_NAME__", "") ||
  "Control Room";
