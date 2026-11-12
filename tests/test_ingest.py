"""Getting events in: the HTTP endpoint, its token, and the Python client."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from kestrel.api import ingest, server
from kestrel.client import Reporter
from kestrel.core.events import EventError


@pytest.fixture
def base_url(monkeypatch):
    monkeypatch.setattr(server.orchestrator, "open_prs", lambda t: [])
    server.CACHE.data.clear()
    srv = server.Server(("127.0.0.1", 0), server.Handler)
    port = srv.server_address[1]
    monkeypatch.setattr(server, "HOSTS", {f"127.0.0.1:{port}", f"localhost:{port}"})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()
    srv.server_close()


def post(url, body, token=None, ctype="application/json"):
    headers = {"Content-Type": ctype}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


EVENT = {"type": "agent.message", "project": "shop", "run": "r1", "agent": "lead", "data": {"text": "hi"}}


def test_token_is_created_once_and_kept(home):
    first = ingest.token()
    assert len(first) > 30 and ingest.token() == first
    assert ingest.authorized(f"Bearer {first}") and not ingest.authorized("Bearer nope") and not ingest.authorized(None)


def test_events_need_the_token(base_url):
    assert post(base_url + "/v1/events", EVENT)[0] == 401
    assert post(base_url + "/v1/events", EVENT, token="wrong")[0] == 401


def test_events_are_accepted_deduplicated_and_shown(base_url, fresh_store):
    tok = ingest.token()
    status, res = post(base_url + "/v1/events", {"events": [{**EVENT, "id": "e1"}, {**EVENT, "id": "e1"}]}, tok)
    assert status == 200 and res == {"accepted": 1, "duplicates": 1, "rejected": []}
    with urllib.request.urlopen(base_url + "/api/overview") as r:
        ov = json.loads(r.read())
    shop = next(t for t in ov["teams"] if t["team"] == "shop")
    assert shop["runnable"] is False and shop["health"] in ("running", "lost")


def test_a_partly_bad_batch_keeps_the_good_events(base_url, fresh_store):
    tok = ingest.token()
    status, res = post(base_url + "/v1/events", [EVENT, {"type": "bogus"}], tok)
    assert status == 200 and res["accepted"] == 1 and res["rejected"][0]["index"] == 1
    status, res = post(base_url + "/v1/events", [{"type": "bogus"}], tok)
    assert status == 400 and "unknown event type" in res["rejected"][0]["error"]
    status, res = post(base_url + "/v1/events", b"not json", tok)
    assert status == 400 and "not JSON" in res["error"]


def test_ndjson_bodies(base_url, fresh_store):
    body = "\n".join(json.dumps({**EVENT, "id": f"n{i}"}) for i in range(3)).encode()
    status, res = post(base_url + "/v1/events", body, ingest.token(), ctype="application/x-ndjson")
    assert status == 200 and res["accepted"] == 3


def test_health_needs_no_token(base_url):
    with urllib.request.urlopen(base_url + "/v1/health") as r:
        assert json.loads(r.read())["events"] == "v1"


def test_reporter_writes_to_the_local_store(fresh_store):
    with Reporter("api", store=fresh_store).run("Add pagination") as run:
        lead = run.agent("lead", role="lead", model="claude-opus-5-5")
        dev = run.agent("dev", role="developer", parent="lead")
        dev.action("Bash", detail="pytest -q", summary="Ran the tests", result="12 passed")
        dev.tokens(input=100, output=20, model="claude-sonnet-5-5")
        dev.finish()
        lead.finish()
    [r] = fresh_store.runs("api")
    types = [e[1] for e in fresh_store.run_events("api", r["id"])]
    assert types[0] == "run.started" and types[-1] == "run.finished" and types.count("agent.finished") == 2


def test_reporter_marks_a_crashed_run_failed(fresh_store):
    with pytest.raises(RuntimeError), Reporter("api", store=fresh_store).run():
        raise RuntimeError("boom")
    [r] = fresh_store.runs("api")
    last = fresh_store.run_events("api", r["id"])[-1]
    assert last[1] == "run.finished" and last[3]["status"] == "failed" and "boom" in last[3]["error"]


def test_reporter_over_http(base_url, fresh_store):
    rep = Reporter("web", url=base_url)
    run = rep.run("Over the wire")
    run.agent("a1", role="developer").action("Edit", detail="src/app.ts")
    run.finish()
    assert [e[1] for e in fresh_store.run_events("web", run.id)] == [
        "run.started",
        "agent.started",
        "agent.action",
        "run.finished",
    ]


def test_reporter_rejects_bad_events_before_sending(fresh_store):
    with pytest.raises(EventError):
        Reporter("api", store=fresh_store).emit("agent.action", run="r", agent="a")  # no tool
