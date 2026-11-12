import { describe, expect, it } from "vitest";
import type { FeedEvent } from "./api";
import { humanize, shortenPaths } from "./humanize";

const bash = (text: string): FeedEvent => ({
  ts: null,
  agent: "developer",
  kind: "tool",
  tool: "Bash",
  text,
});

describe("humanize", () => {
  it.each([
    ["npm test", "Ran the tests"],
    ["cd /c/Users/me/cr/teams/tells/repo; npx expo export --platform web", "Ran a script"],
    ["cd repo && pytest -q", "Ran the tests"],
    ["git -C repo switch -c feat/TEL-006-web-demo origin/main", "Created branch feat/TEL-006-web-demo"],
    ["git -C repo push -u origin feat/TEL-006-web-demo", "Pushed the branch"],
    ["gh pr create --repo a/b --title x", "Opened a pull request"],
    ["until [ -s out.txt ]; do sleep 3; done", "Waited for a condition"],
    ["python C:/x/runner/shoot.py http://localhost:8081 previews/a.png", "Took a screenshot"],
    ["some-unknown-tool --flag", "Ran a command"],
  ])("%s → %s", (cmd, title) => {
    expect(humanize(bash(cmd)).title).toBe(title);
  });

  it("keeps the raw command for the tooltip and shows a shortened one", () => {
    const h = humanize(bash("cd /c/Users/me/cr/teams/tells/repo; cat src/app.ts"));
    expect(h.raw).toBe("cd /c/Users/me/cr/teams/tells/repo; cat src/app.ts");
    expect(h.detail).toBe("cat src/app.ts");
  });

  it("names files and delegations", () => {
    expect(humanize({ ...bash("repo/src/app.ts"), tool: "Edit" }).title).toBe("Edited app.ts");
    const d = humanize({
      ts: null,
      agent: "lead",
      kind: "delegate",
      tool: "Agent",
      text: "→ tester: Run tests",
    });
    expect(d).toEqual({ title: "Delegated to tester", detail: "Run tests" });
  });
});

describe("shortenPaths", () => {
  it("makes paths relative to the team folder and hides the run's temp folder", () => {
    expect(shortenPaths("ls C:/Users/me/cr/teams/tells/repo/src")).toBe("ls repo/src");
    expect(
      shortenPaths(
        "cat C:/Users/me/AppData/Local/Temp/claude/2b9a818d/4b68352a-d536-4cbd-abcf-0f578b5f979a/tasks/x.output",
      ),
    ).toBe("cat tmp/tasks/x.output");
  });
});
