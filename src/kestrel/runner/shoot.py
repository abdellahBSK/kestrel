"""Screenshot a LOCAL page with headless Microsoft Edge (already on Windows; nothing to install).

  python shoot.py <url> <out.png> [--size 390x844] [--wait 5000] [--scale 2]

Only http://localhost / 127.0.0.1 URLs are allowed, and the image must be written inside the
current folder (the team workspace).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


def browser() -> str:
    for c in CANDIDATES:
        if Path(c).exists():
            return c
    found = shutil.which("msedge") or shutil.which("chrome")
    if not found:
        sys.exit("No Edge/Chrome found for screenshots.")
    return found


def _serve(folder: str):
    """Serve `folder` on 127.0.0.1 (random free port) from a background thread."""
    import functools
    import http.server
    import threading

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=folder))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--size", default="390x844", help="WIDTHxHEIGHT in CSS pixels (390x844 phone, 1280x800 desktop)")
    ap.add_argument("--wait", type=int, default=5000, help="ms of page time before capture")
    ap.add_argument("--scale", type=float, default=2.0, help="device pixel ratio")
    a = ap.parse_args()

    host = (urlparse(a.url).hostname or "").lower()
    if host not in ("localhost", "127.0.0.1", "::1"):
        sys.exit("shoot.py only captures local pages (localhost / 127.0.0.1).")
    out = Path(a.out).resolve()
    if not str(out).lower().startswith(str(Path.cwd().resolve()).lower()):
        sys.exit("The screenshot must be saved inside the current workspace.")
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = (int(x) for x in a.size.lower().split("x"))

    if out.exists():
        out.unlink()
    profile = tempfile.mkdtemp(prefix="kestrel-shot-")
    target = a.url
    server = None
    if w < 500:
        # Headless Edge won't lay out narrower than ~480px, so phone sizes are rendered in an
        # exact-size frame at the top-left and the capture is cropped to it.
        frame = Path(profile) / "frame.html"
        frame.write_text(
            "<!doctype html><html><body style='margin:0;overflow:hidden;background:#fff'>"
            f"<iframe src='{a.url}' style='border:0;width:{w}px;height:{h}px;display:block'></iframe>"
            "</body></html>",
            encoding="utf-8",
        )
        # Served over http, not file://: from a file:// wrapper, --virtual-time-budget doesn't
        # cover the iframe, so pages that render after load came out blank.
        server = _serve(profile)
        target = f"http://127.0.0.1:{server.server_address[1]}/frame.html"
    cmd = [
        browser(),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--disable-extensions",
        f"--user-data-dir={profile}",
        f"--window-size={w},{h}",
        f"--force-device-scale-factor={a.scale}",
        f"--virtual-time-budget={a.wait}",
        f"--screenshot={out}",
        target,
    ]
    subprocess.run(cmd, capture_output=True, timeout=120)
    # On Windows the Edge launcher returns before the browser has written the file: wait for it.
    deadline = time.time() + 60
    last = -1
    while time.time() < deadline:
        if out.exists():
            size = out.stat().st_size
            if size > 0 and size == last:
                break
            last = size
        time.sleep(1)
    if server:
        server.shutdown()
    shutil.rmtree(profile, ignore_errors=True)
    if not out.exists() or out.stat().st_size == 0:
        sys.exit(f"Screenshot failed for {a.url} (is the app running?)")
    print(f"saved {out} ({out.stat().st_size // 1024} KB, {w}x{h} @{a.scale}x)")


if __name__ == "__main__":
    main()
