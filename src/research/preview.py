"""research preview [--no-build] [--port 8000]: build the site from the live data on server-jan and serve it on
localhost, to see a change before it goes out (README, "Build"). Served over HTTP, since the Pagefind search does
not work from file://.

Every input the build reads from the environment defaults to what the nightly run uses (`/srv/apps/bundestag`),
when it exists and the variable is not set: the foundation store, its raw folder (portraits) and export, and the
Themenlandschaft's JSON. The store is only read; a preview can run while the nightly run writes."""

from __future__ import annotations

import functools
import http.server
import os
from collections.abc import Callable
from pathlib import Path

LIVE = Path("/srv/apps/bundestag/data")
DEFAULTS = {
    "BDF_DB": LIVE / "foundation" / "bundestag.sqlite",
    "BDF_RAW": LIVE / "foundation" / "raw",
    "FOUNDATION_EXPORT": LIVE / "foundation" / "export",
    "LANDSCAPE_CLUSTERS": LIVE / "landscape" / "out" / "speech_clusters.json",
    "LANDSCAPE_NEIGHBOURS": LIVE / "landscape" / "out" / "speech_neighbours.json",
    "LANDSCAPE_THEMES": LIVE / "landscape" / "out" / "speech_themes.json",
}
# the live site's addresses, so links into the Themenlandschaft go where the public site has it
URLS = {"RESEARCH_URL": "https://plenar-radar.de/", "LANDSCAPE_URL": "https://plenar-radar.de/themenlandschaft/"}


def live_defaults(env: dict[str, str] | None = None) -> dict[str, str]:
    """Set the unset inputs to the live paths that exist (and the live addresses); returns what was set."""
    env = os.environ if env is None else env
    applied = {k: str(v) for k, v in DEFAULTS.items() if k not in env and v.exists()}
    applied |= {k: v for k, v in URLS.items() if k not in env}
    env.update(applied)
    return applied


def serve(out: Path, port: int) -> None:
    """Serve `out` on http://127.0.0.1:<port>/ until Ctrl-C."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    try:
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as err:
        raise SystemExit(f"port {port} is taken ({err.strerror}): try --port <another>") from None
    with httpd:
        print(f"serving {out} at http://127.0.0.1:{port}/ (Ctrl-C stops; scripts/stage.sh shares it on the tailnet)",
              flush=True)  # fmt: skip
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()


def run(out: Path, port: int, build: Callable[[Path], None] | None) -> None:
    """Build (unless `build` is None) and serve."""
    if build is not None:
        for k, v in live_defaults().items():
            print(f"{k}={v}", flush=True)
        build(out)
    if not (out / "index.html").exists():
        raise SystemExit(f"{out}/index.html is missing: run without --no-build first")
    serve(out, port)
