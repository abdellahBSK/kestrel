// Turns raw agent actions into a short, human-readable line. The raw command stays available on hover.

import type { FeedEvent } from "./api";

type Rule = [RegExp, string | ((m: RegExpMatchArray) => string)];

const COMMANDS: Rule[] = [
  [/\bshoot\.py\b/, "Took a screenshot"],
  [/\bpreview\.py\b/, "Published screenshots to the PR"],
  [/\bgh\s+pr\s+create\b/, "Opened a pull request"],
  [/\bgh\s+pr\s+comment\b/, "Commented on a pull request"],
  [/\bgh\s+pr\s+(view|list|status|checks|diff)\b/, "Checked pull requests"],
  [/\bgh\s+pr\s+edit\b/, "Edited a pull request"],
  [/\bgit\b.*\bpush\b/, "Pushed the branch"],
  [/\bgit\b.*\bcommit\b/, "Committed changes"],
  [/\bgit\b.*\b(switch|checkout)\s+(-c|-b)\s+(\S+)/, (m) => `Created branch ${m[3]}`],
  [/\bgit\b.*\b(switch|checkout)\b/, "Switched branch"],
  [/\bgit\b.*\b(fetch|pull)\b/, "Fetched the latest code"],
  [/\bgit\b.*\b(status|diff|log|show|branch)\b/, "Inspected the repository"],
  [/\bgit\b.*\b(add|restore|stash)\b/, "Staged changes"],
  [/\b(pytest|vitest|jest|mocha|go test|cargo test|mvn test|gradle test)\b/, "Ran the tests"],
  [/\b(npm|pnpm|yarn|bun)\s+(run\s+)?test\b/, "Ran the tests"],
  [
    /\b(npm|pnpm|yarn|bun)\s+(ci|install|i|add)\b|\bpip\s+install\b|\buv\s+(sync|pip)\b/,
    "Installed dependencies",
  ],
  [/\b(npm|pnpm|yarn|bun)\s+run\s+build\b|\btsc\b|\bvite\s+build\b|\bcargo\s+build\b/, "Built the project"],
  [/\b(eslint|ruff|flake8|prettier|black|mypy|pyright)\b|\b(npm|pnpm|yarn)\s+run\s+lint\b/, "Ran linters"],
  [/\b(npm|pnpm|yarn)\s+(run\s+)?(dev|start)\b|\buvicorn\b|\bexpo\s+start\b/, "Started the app"],
  [/\b(npm|pip)\s+audit\b|\bpip-audit\b/, "Audited dependencies"],
  [/^\s*(cat|type|head|tail|less|more|Get-Content|gc)\b/i, "Read a file"],
  [/^\s*(ls|dir|tree|find|Get-ChildItem|gci)\b/i, "Listed files"],
  [/^\s*(grep|rg|Select-String|findstr)\b/i, "Searched the code"],
  [/^\s*(mkdir|New-Item)\b/i, "Created a folder"],
  [/^\s*(rm|del|Remove-Item)\b/i, "Deleted files"],
  [/^\s*(mv|cp|Move-Item|Copy-Item)\b/i, "Moved files"],
  [/^\s*(curl|wget|Invoke-WebRequest|iwr)\b/i, "Made an HTTP request"],
  [/^\s*(sleep|Start-Sleep|timeout)\b/i, "Waited"],
  [/^\s*(until|while)\b[\s\S]*\bsleep\b/i, "Waited for a condition"],
  [/^\s*(python|node|npx)\b/i, "Ran a script"],
];

function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

const STOP = `[^\\s'"\`;|&]`;
const TEAM_PREFIX = new RegExp(`(?:[A-Za-z]:)?[\\\\/](?:${STOP}*?[\\\\/])?teams[\\\\/][\\w.-]+[\\\\/]?`, "g");
const TEMP_PREFIX = new RegExp(
  `(?:[A-Za-z]:)?[\\\\/]${STOP}*?[\\\\/]Temp[\\\\/]claude[\\\\/]${STOP}*?[\\\\/][0-9a-f-]{36}[\\\\/]`,
  "gi",
);

/** Shows paths relative to the team folder, and the run's temp folder as `tmp/`. */
export function shortenPaths(s: string): string {
  return s.replace(TEMP_PREFIX, "tmp/").replace(TEAM_PREFIX, "");
}

/** Drops leading `cd <dir> &&` / `cd <dir>;` so the real command is what gets named. */
function stripCd(cmd: string): string {
  let s = cmd;
  for (let i = 0; i < 3; i++)
    s = s.replace(/^\s*(cd|Set-Location|pushd)\s+("[^"]*"|'[^']*'|\S+)\s*(&&|;)\s*/i, "");
  return s;
}

export type Humanized = { title: string; detail?: string; raw?: string };

export function humanize(e: FeedEvent): Humanized {
  if (e.kind === "say" || e.kind === "notice") return { title: e.text };
  if (e.kind === "budget" || e.kind === "halt") return { title: e.text };
  if (e.title) return { title: e.title, detail: shortenPaths(e.text), raw: e.text };
  const t = e.text ?? "";
  const short = shortenPaths(t);
  switch (e.tool) {
    case "Bash":
    case "PowerShell": {
      const cmd = stripCd(short);
      for (const [re, out] of COMMANDS) {
        const m = cmd.match(re);
        if (m) return { title: typeof out === "string" ? out : out(m), detail: cmd, raw: t };
      }
      return { title: "Ran a command", detail: cmd, raw: t };
    }
    case "Read":
      return { title: `Read ${basename(t)}`, detail: short, raw: t };
    case "Write":
      return { title: `Wrote ${basename(t)}`, detail: short, raw: t };
    case "Edit":
    case "MultiEdit":
    case "NotebookEdit":
      return { title: `Edited ${basename(t)}`, detail: short, raw: t };
    case "Grep":
      return { title: `Searched for “${t.split("  ")[0]}”`, detail: short, raw: t };
    case "Glob":
      return { title: `Looked for ${t.split("  ")[0]}`, detail: short, raw: t };
    case "TodoWrite":
      return { title: t.replace(/^plan:\s*/, "Plan: "), detail: undefined };
    case "Agent":
    case "Task": {
      const m = t.match(/^→\s*([\w-]+):\s*(.*)$/);
      return m ? { title: `Delegated to ${m[1]}`, detail: m[2] } : { title: t };
    }
    default:
      return { title: e.tool ? `Used ${e.tool}` : t, detail: t };
  }
}
