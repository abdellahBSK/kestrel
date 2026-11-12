"""The `kestrel` command line.

kestrel init | doctor                  set up a home folder; check a setup
kestrel watch                          the live dashboard (http://127.0.0.1:7777)
kestrel demo                           the dashboard with realistic fake data
kestrel emit | ingest | token          report events from any language (see docs/events.md)
kestrel hook install                   report every Claude Code session
kestrel status | setup | run | stop    the optional Claude Code runner
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

if "--home" in sys.argv[:-1]:  # before anything below reads the home folder
    _i = sys.argv.index("--home")
    os.environ["KESTREL_HOME"] = sys.argv[_i + 1]
    del sys.argv[_i : _i + 2]

from kestrel import NAME, __version__, meter  # noqa: E402
from kestrel.cli import events as cli_tools  # noqa: E402
from kestrel.cli import hook as hook_cli  # noqa: E402
from kestrel.cli import setup as setup_cli  # noqa: E402
from kestrel.runner import orchestrator as runner  # noqa: E402

EPILOG = """
Start here:
  kestrel demo                 every state the dashboard knows, with fake data
  kestrel init                 write a commented config;  kestrel doctor  checks a setup
  kestrel watch                the dashboard for your agents (http://127.0.0.1:7777)

Report your agents:
  kestrel hook install         every Claude Code session on this computer
  kestrel emit | ingest        from scripts, any language;  kestrel token  for HTTP

The runner (optional): kestrel setup | run | status | stop | resume | brief | prs | launch

Docs: https://github.com/abdellahBSK/kestrel/tree/main/docs
"""


def cmd_prune(args) -> int:
    from kestrel import retention
    from kestrel.storage.store import open_store

    days = args.days if args.days is not None else meter.load_config()["storage"].get("retention_days", 0)
    if not days or days <= 0:
        print("Nothing to do: pass --days N, or set [storage] retention_days in config.toml.")
        return 1
    st = open_store()
    res = retention.prune(st, days, dry_run=args.dry_run)
    verb = "Would delete" if args.dry_run else "Deleted"
    print(f"{verb} {res['runs']:,} run(s) ({res['events']:,} events) last active more than {days:g} days ago.")
    if res["runs"] and not args.dry_run:
        with st.lock:
            st.db.execute("VACUUM")  # give the space back to the disk
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="kestrel",
        description=f"{NAME}: see what your AI agents are doing, what they cost, and when they get stuck.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--home", metavar="FOLDER", help="the home folder to use (default: $KESTREL_HOME or ~/.kestrel)")
    p.add_argument("--version", action="version", version=f"{NAME} {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="(runner) tokens used today and this week, budget left")
    sub.add_parser("baseline", help="(runner) your own daily Claude Code usage, as JSON")
    sp = sub.add_parser("setup", help="(runner) create or refresh team workspaces")
    sp.add_argument("teams", nargs="*", help="teams to set up (default: all)")
    rp = sub.add_parser("run", help="(runner) today's scheduled run")
    rp.add_argument("--team", help="run only this team")
    rp.add_argument("--force", action="store_true", help="run even if it already ran today or it's before start_hour")
    rp.add_argument("--dry-run", action="store_true", help="show what would run, run nothing")
    rp.add_argument("--allowance", type=int, help="cap each team's allowance (tokens)")
    rp.add_argument("--extra", type=int, default=0, help="one-off tokens on top of today's budget")
    rp.add_argument("--lead-model", help="override the lead model for this run")
    stp = sub.add_parser(
        "stop", help="stop running agents: everything, or one project, run or agent (they halt at their next action)"
    )
    stp.add_argument("project", nargs="?", help="only this project (default: everything, and no new scheduled runs)")
    stp.add_argument("--run", help="only this run of the project")
    stp.add_argument("--agent", help="only this agent of the run")
    sub.add_parser("resume", help="(runner) let scheduled runs start again after `kestrel stop`")
    bp = sub.add_parser("brief", help="(runner) rebuild the daily brief")
    bp.add_argument("day", nargs="?", default=dt.date.today().isoformat())
    dp = sub.add_parser("demo", help="try the dashboard with realistic fake data (or, with a project: same as launch)")
    dp.add_argument("team", nargs="?", help="(launch) project to run locally")
    dp.add_argument("target", nargs="?", help="(launch) PR number or branch (default: main)")
    dp.add_argument("--no-install", action="store_true", help="(launch) skip the install step")
    dp.add_argument("--port", type=int, default=7777)
    dp.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    dp.add_argument("--host", help="address to listen on (default 127.0.0.1, or $KESTREL_HOST)")
    lp = sub.add_parser("launch", help="(runner) run a project's PR or branch locally and open it in the browser")
    lp.add_argument("team")
    lp.add_argument("target", nargs="?", help="PR number or branch (default: main)")
    lp.add_argument("--no-install", action="store_true", help="skip the install step")
    cli_tools.add_parsers(sub)
    hook_cli.add_parsers(sub)
    setup_cli.add_parsers(sub)
    sub.add_parser("prs", help="(runner) list open agent PRs across all projects")
    wp = sub.add_parser("watch", help="open the live dashboard (http://127.0.0.1:7777 by default)")
    wp.add_argument("--port", type=int, default=7777)
    wp.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    wp.add_argument("--host", help="address to listen on (default 127.0.0.1, or $KESTREL_HOST)")
    pp = sub.add_parser("prune", help="delete old runs from the event store")
    pp.add_argument(
        "--days",
        type=float,
        help="delete runs last active more than this many days ago (default: [storage] retention_days)",
    )
    pp.add_argument("--dry-run", action="store_true", help="only say what would be deleted")
    args = p.parse_args()
    if getattr(args, "host", None):
        os.environ["KESTREL_HOST"] = args.host  # also reaches the demo's own process
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
    if args.cmd == "prune":
        sys.exit(cmd_prune(args))
    if args.cmd == "init":
        sys.exit(setup_cli.cmd_init(args))
    if args.cmd == "doctor":
        sys.exit(setup_cli.cmd_doctor(args))
    if args.cmd == "hook":
        sys.exit(hook_cli.run(args))
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
        from kestrel import control
        from kestrel.storage.store import open_store

        if args.project:
            print(control.request(open_store(), args.project, args.run, args.agent, reason="Stopped by the owner"))
        else:
            (runner.HQ / "STOP").write_text("Raised by the owner\n")
            control.request(open_store(), control.ALL, reason="Stop all, by the owner")
            runner.log("Stopping everything: agents halt at their next action; no new scheduled runs.")
    elif args.cmd == "resume":
        (runner.HQ / "STOP").unlink(missing_ok=True)
        runner.log("STOP flag lowered.")
