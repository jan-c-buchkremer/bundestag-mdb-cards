"""The UI check (scripts/ui_check.py) on the e2e site: every kind of page in Chromium at desktop and phone width,
without a script error, a page wider than the screen, cut-off content, a broken image, a nameless link or a filter
that ignores the URL. Skipped where Chromium cannot start (server-jan lacks its system libraries: run
scripts/ui_check.sh there), except in CI, where it must run."""

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from test_e2e import site  # noqa: F401 (the built e2e site, a module fixture)

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ui_check.py"
_spec = importlib.util.spec_from_file_location("ui_check", SCRIPT)
ui_check = importlib.util.module_from_spec(_spec)
sys.modules["ui_check"] = ui_check  # its dataclass looks itself up there
_spec.loader.exec_module(ui_check)


def need_browser() -> None:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as err:  # not installed, or its system libraries are missing
        if os.environ.get("CI"):
            pytest.fail(f"Chromium does not start, but the CI must run the UI check: {err}")
        pytest.skip(f"Chromium does not start here: {str(err).splitlines()[0][:120]}")


def test_ui_check_finds_no_errors(site, tmp_path):  # noqa: F811
    need_browser()
    results = ui_check.run(site, tmp_path, use_axe=False, shots=False)
    assert {r.page for r in results} >= {"startseite", "vorgaenge", "sachgebiete", "sitzungen", "orte"}
    errors = [f"{r.page} ({r.viewport}): {f[1]} {f[2]} {f[3]}" for r in results for f in r.errors]
    assert not errors, "\n".join(errors[:20])


def test_pick_skips_index_and_stubs(tmp_path):
    (tmp_path / "gremien").mkdir()
    (tmp_path / "gremien" / "index.html").write_text("<p>index</p>")
    (tmp_path / "gremien" / "a.html").write_text('<meta http-equiv="refresh" content="0; url=b.html">')
    (tmp_path / "gremien" / "b.html").write_text("<p>b</p>")
    assert ui_check.pick(tmp_path, "gremien/*.html", 0) == "gremien/b.html"
    assert ui_check.pick(tmp_path, "kompass.html", 0) is None
