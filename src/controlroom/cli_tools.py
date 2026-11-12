"""Command-line ways to report events, for agents written in any language.

  controlroom emit run.started --project shop                 → prints the new run id
  controlroom emit agent.action --project shop --run R --agent dev -d tool=Bash -d detail="npm test"
  controlroom ingest events.jsonl                               (or - for stdin)
  controlroom token                                             → the bearer token for POST /v1/events

`emit` and `ingest` write straight into this computer's store, so no server needs to be running.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

from controlroom import ingest
from controlroom.events import EventError, normalize
from controlroom.store import open_store


def add_parsers(sub) -> None:
    ep = sub.add_parser("emit", help="report one event (see docs/events.md)")
    ep.add_argument("type", help="e.g. run.started, agent.action, agent.tokens, run.finished")
    ep.add_argument("--project", required=True)
    ep.add_argument("--run", help="run id (a new one is made and printed for run.started)")
    ep.add_argument("--agent", help="agent id, for agent.* events")
    ep.add_argument("-d", "--set", action="append", metavar="KEY=VALUE", help="a data field (JSON values allowed)")
    ep.add_argument("--data", help="all data fields as one JSON object")
    ep.add_argument("--ts", help="when it happened (ISO 8601 with timezone, or Unix seconds); default now")
    ep.add_argument("--id", help="an id that makes resending this event harmless")
    ip = sub.add_parser("ingest", help="import events from a JSON or JSON Lines file (- for stdin)")
    ip.add_argument("file")
    sub.add_parser("token", help="print the bearer token for POST /v1/events")


def _value(v: str):
    try:
        return json.loads(v)
    except ValueError:
        return v


def cmd_emit(args) -> int:
    data = {}
    if args.data:
        try:
            data.update(json.loads(args.data))
        except ValueError as e:
            print(f"error: --data is not JSON: {e}", file=sys.stderr)
            return 2
    for kv in args.set or []:
        key, sep, value = kv.partition("=")
        if not sep:
            print(f"error: -d expects KEY=VALUE, got {kv!r}", file=sys.stderr)
            return 2
        data[key] = _value(value)
    run = args.run
    new_run = not run and args.type == "run.started"
    if new_run:
        run = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    raw = {"type": args.type, "project": args.project, "run": run, "agent": args.agent, "data": data}
    if args.ts:
        raw["ts"] = _value(args.ts) if args.ts.replace(".", "", 1).isdigit() else args.ts
    if args.id:
        raw["id"] = args.id
    try:
        event = normalize(raw)
    except EventError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    open_store().add([event])
    if new_run:
        print(run)
    return 0


def cmd_ingest(args) -> int:
    body = sys.stdin.buffer.read() if args.file == "-" else Path(args.file).read_bytes()
    try:
        try:
            items = ingest.parse_body(body, "application/json")
        except EventError:
            items = ingest.parse_body(body, "application/x-ndjson")
        result = ingest.ingest(open_store(), items)
    except EventError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{result['accepted']} accepted, {result['duplicates']} already stored, {len(result['rejected'])} rejected")
    for r in result["rejected"][:20]:
        print(f"  event {r['index']}: {r['error']}", file=sys.stderr)
    return 1 if result["rejected"] else 0


def cmd_token() -> int:
    print(ingest.token())
    return 0
