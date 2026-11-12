from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from conftest import usage_record, write_transcript
from kestrel import NAME
from kestrel.api import server
from kestrel.core import runs
from kestrel.core.events import normalize


@pytest.fixture
def base_url(monkeypatch):
    monkeypatch.setattr(server.orchestrator, "open_prs", lambda t: [])  # never call `gh` in tests
    server.CACHE.data.clear()
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = srv.server_address[1]
    monkeypatch.setattr(server, "HOSTS", {f"127.0.0.1:{port}", f"localhost:{port}"})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def get(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {})) as r:
        return r.status, r.read()


def post(url, headers=None):
    req = urllib.request.Request(url, method="POST", headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def test_page_carries_the_project_name(base_url):
    status, body = get(base_url + "/")
    page = body.decode()
    assert status == 200
    assert f"<title>{NAME}</title>" in page and "__APP_NAME__" not in page


def test_overview_lists_configured_teams(base_url):
    _, body = get(base_url + "/api/overview")
    ov = json.loads(body)
    assert [t["team"] for t in ov["teams"]] == ["sandbox", "todo-api", "docs-site"]
    assert ov["running"] is None and ov["stop"] is False


def test_foreign_host_header_is_rejected(base_url):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(base_url + "/api/overview", headers={"Host": "evil.example:80"})
    assert e.value.code == 403


def test_buttons_need_the_custom_header_and_same_origin(base_url, home):
    assert post(base_url + "/api/stop")[0] == 403
    assert post(base_url + "/api/stop", {"X-Kestrel": "1", "Origin": "https://evil.example"})[0] == 403
    status, res = post(base_url + "/api/stop", {"X-Kestrel": "1"})
    assert status == 200 and res["ok"] and (home / "STOP").exists()
    status, res = post(base_url + "/api/resume", {"X-Kestrel": "1"})
    assert status == 200 and not (home / "STOP").exists()


def test_unknown_team_and_preview_paths(base_url):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(base_url + "/api/session?team=nope")
    assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        get(base_url + "/previews/sandbox/..%2F..%2Fconfig.toml")
    assert e.value.code == 404


def test_claude_code_transcripts_become_the_feed(tmp_path):
    ts = "2026-01-01T10:00:00.000Z"
    path = write_transcript(
        tmp_path / "s.jsonl",
        [
            usage_record(
                ts,
                "m1",
                inp=10,
                out=5,
                content=[
                    {"type": "text", "text": "Starting the run."},
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "npm test"}},
                    {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "git push origin main"}},
                    {
                        "type": "tool_use",
                        "id": "t3",
                        "name": "Agent",
                        "input": {"subagent_type": "tester", "description": "Run tests"},
                    },
                ],
            ),
            {
                "type": "user",
                "timestamp": ts,
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "12 passed"},
                        {
                            "type": "tool_result",
                            "tool_use_id": "t2",
                            "content": "[Kestrel guard] Rule 2: no",
                            "is_error": True,
                        },
                    ]
                },
            },
        ],
    )
    raw, info = server.claude_code.transcript_events(path, "sandbox", "s1", "lead", "/x/teams/sandbox")
    th = {"heartbeat_timeout": 45, "idle_after": 120, "stale_after": 600}
    rows = [(e["ts"], e["type"], e["agent"], e["data"]) for e in (normalize(r, now=2e9) for r in raw)]
    f = runs.fold(rows, heartbeat=None, now=2e9, th=th)
    feed = f["feed"]
    assert [e["kind"] for e in feed] == ["say", "tool", "tool", "delegate"]
    assert feed[1]["status"] == "ok" and feed[1]["result"] == "12 passed" and feed[1]["text"] == "npm test"
    assert feed[2]["status"] == "blocked"
    assert feed[3]["status"] == "running" and feed[3]["text"] == "→ tester: Run tests"
    assert f["agents"][0]["tokens"] == 15 and info["clean_end"] is False


@pytest.fixture
def built_app(tmp_path, monkeypatch):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<title>__APP_NAME__</title><script src=/assets/app-1a2b.js></script>")
    (static / "assets" / "app-1a2b.js").write_text("console.log(1)")
    (static / "favicon.svg").write_text("<svg/>")
    monkeypatch.setattr(server.paths, "STATIC", static)
    return static


def test_built_app_is_served_with_security_headers(base_url, built_app):
    with urllib.request.urlopen(base_url + "/") as r:
        assert f"<title>{NAME}</title>" in r.read().decode()
        assert "default-src 'self'" in r.headers["Content-Security-Policy"]
        assert r.headers["X-Frame-Options"] == "DENY"
    with urllib.request.urlopen(base_url + "/assets/app-1a2b.js") as r:
        assert r.headers["Content-Type"].startswith("text/javascript")
        assert "immutable" in r.headers["Cache-Control"]
    with urllib.request.urlopen(base_url + "/favicon.svg") as r:
        assert r.headers["Content-Type"] == "image/svg+xml"


@pytest.mark.parametrize("path", ["/assets/..%2Findex.html", "/assets/missing.js", "/config.toml", "/assets/x.exe"])
def test_only_known_static_files_are_served(base_url, built_app, path):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(base_url + path)
    assert e.value.code == 404


def test_unbuilt_app_explains_how_to_build(base_url, tmp_path, monkeypatch):
    monkeypatch.setattr(server.paths, "STATIC", tmp_path / "nothing-here")
    _, body = get(base_url + "/")
    assert "npm run build" in body.decode() and f"<title>{NAME}</title>" in body.decode()


def test_overview_has_a_utc_timestamp_and_seven_days_of_usage(base_url):
    _, body = get(base_url + "/api/overview")
    ov = json.loads(body)
    assert ov["generated_at"].endswith("Z") and ov["version"]
    assert [d["date"] for d in ov["budget"]["daily"]] == sorted(d["date"] for d in ov["budget"]["daily"])
    assert len(ov["budget"]["daily"]) == 7


def test_dashboard_owns_its_port_and_explains_a_clash():
    first = server.Server(("127.0.0.1", 0), server.Handler)
    port = first.server_address[1]
    try:
        with pytest.raises(OSError):
            server.Server(("127.0.0.1", port), server.Handler)  # never silently shares the port
        with pytest.raises(SystemExit, match="already in use"):
            server.serve(open_browser=False, port=port)
    finally:
        first.server_close()
