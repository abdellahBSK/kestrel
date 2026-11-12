"""The `kestrel` command line.

kestrel watch                          the live dashboard (http://127.0.0.1:7777)
kestrel demo                           the dashboard with realistic fake data
kestrel emit | ingest | token          report events from any language (see docs/events.md)
kestrel status | setup | run | stop    the optional Claude Code runner
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from kestrel import NAME, meter
from kestrel.cli import events as cli_tools
from kestrel.runner import orchestrator as runner


def main() -> None:
    p = argparse.ArgumentParser(
        prog="kestrel",
        description=f"{NAME}: a live dashboard for AI agent runs, plus a scheduled runner for Claude Code teams.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("baseline")
    sp = sub.add_parser("setup")
    sp.add_argument("teams", nargs="*")
    rp = sub.add_parser("run")
    rp.add_argument("--team")
    rp.add_argument("--force", action="store_true")
    rp.add_argument("--dry-run", action="store_true")
    rp.add_argument("--allowance", type=int, help="cap each team's allowance (tokens)")
    rp.add_argument("--extra", type=int, default=0, help="one-off tokens on top of today's budget")
    rp.add_argument("--lead-model", help="override the lead model for this run")
    sub.add_parser("stop", help="raise the STOP flag: halts running agents, blocks new runs")
    sub.add_parser("resume", help="lower the STOP flag")
    bp = sub.add_parser("brief")
    bp.add_argument("day", nargs="?", default=dt.date.today().isoformat())
    dp = sub.add_parser("demo", help="try the dashboard with realistic fake data (or, with a project: same as launch)")
    dp.add_argument("team", nargs="?", help="(launch) project to run locally")
    dp.add_argument("target", nargs="?", help="(launch) PR number or branch (default: main)")
    dp.add_argument("--no-install", action="store_true", help="(launch) skip the install step")
    dp.add_argument("--port", type=int, default=7777)
    dp.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    lp = sub.add_parser("launch", help="run a project's PR or branch locally and open it in the browser")
    lp.add_argument("team")
    lp.add_argument("target", nargs="?", help="PR number or branch (default: main)")
    lp.add_argument("--no-install", action="store_true", help="skip the install step")
    cli_tools.add_parsers(sub)
    sub.add_parser("prs", help="list open agent PRs across all projects")
    wp = sub.add_parser("watch", help="open the live dashboard (http://127.0.0.1:7777 by default)")
    wp.add_argument("--port", type=int, default=7777)
    wp.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = p.parse_args()
    if args.cmd == "watch":
        from kestrel.api import server

        server.serve(open_browser=not args.no_browser, port=args.port)
        return
    if args.cmd == "demo" and not args.team:
        from kestrel import demo

        sys.exit(demo.launch(port=args.port, open_browser=not args.no_browser))
    if args.cmd in ("demo", "launch"):
        runner.cmd_demo(args, meter.load_config())
        return
    if args.cmd == "emit":
        sys.exit(cli_tools.cmd_emit(args))
    if args.cmd == "ingest":
        sys.exit(cli_tools.cmd_ingest(args))
    if args.cmd == "token":
        sys.exit(cli_tools.cmd_token())
    if args.cmd == "prs":
        for team, t in meter.load_config()["teams"].items():
            for pr in runner.open_prs(t):
                print(
                    f"{team:<22}#{pr['number']:<4}{'draft ' if pr['isDraft'] else 'ready '}{pr['title']}\n{'':<26}{pr['url']}"
                )
        return
    cfg = meter.load_config()
    if args.cmd == "status":
        runner.cmd_status(cfg)
    elif args.cmd == "baseline":
        print(json.dumps(meter.baseline(cfg), indent=2))
    elif args.cmd == "setup":
        for team in args.teams or list(cfg["teams"]):
            try:
                runner.setup_team(team, cfg)
                runner.log(f"{team}: workspace ready")
            except Exception as e:
                runner.log(f"{team}: setup FAILED: {e}")
    elif args.cmd == "run":
        runner.cmd_run(args, cfg)
    elif args.cmd == "brief":
        print(runner.write_brief(args.day, cfg))
    elif args.cmd == "stop":
        (runner.HQ / "STOP").write_text("Raised by the owner\n")
        runner.log("STOP flag raised: agents halt at their next action.")
    elif args.cmd == "resume":
        (runner.HQ / "STOP").unlink(missing_ok=True)
        runner.log("STOP flag lowered.")
