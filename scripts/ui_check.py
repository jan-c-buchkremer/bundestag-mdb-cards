"""The UI check: open one example of every kind of page of a built site in Chromium, at desktop and phone width, and
report what a reader would see broken. Exits 1 when a page has an error; warnings are listed, not fatal.

    uv run python scripts/ui_check.py data/out [--out data/ui] [--baseline data/ui-baseline] [--approve]
                                               [--only NAME …] [--no-axe] [--no-shots]
    scripts/ui_check.sh data/out …     the same in the Playwright container, for a machine without Chromium's
                                       system libraries

Errors: a script error or a failed request; a page wider than the screen; content cut off by a box that hides its
overflow (text, tables, chips; intended truncation with an ellipsis or a line clamp is fine); a broken image; a
button or link without a name; a filter (`[data-f]` buttons, controls.js) whose click does not change the URL
fragment, or whose state the back button does not undo.
Warnings: a box that needs a scroll bar on a wide screen; clickable things that overlap; accessibility findings from
axe-core (contrast, labels; loaded from cdnjs, skipped offline or with --no-axe).

Screenshots of every page and width go to --out (pages cut at MAX_SHOT pixels). With --baseline, each is compared
with the approved one there; a changed page is listed with the share of changed pixels and a diff image, so a
visual regression shows up even where no rule fails. --approve copies the screenshots of this run into the
baseline. The report is --out/report.md.

Stdlib, Playwright and Pillow only, no research imports: it checks any built site."""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

VIEWPORTS = {"desktop": (1440, 900), "phone": (390, 844)}
MAX_SHOT = 6000  # px: long lists are cut, the top of a page is what changes
CHANGED = 0.005  # share of changed pixels above which a page counts as visually changed
AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
AXE_RULES = ["color-contrast", "button-name", "link-name", "label", "image-alt", "duplicate-id-aria",
             "aria-valid-attr-value", "list", "listitem"]  # fmt: skip

# One example of every kind of page: (name, path or glob, which match when a glob has several: 0 first, -1 last).
# A page that the build did not write (no Kompass, no Themenlandschaft) is skipped.
PAGES = [
    ("startseite", "index.html", 0), ("abgeordnete", "abgeordnete.html", 0), ("steckbrief", "[0-9]*.html", 0),
    ("orte", "orte/index.html", 0), ("land", "orte/bayern.html", 0), ("wahlkreis", "orte/wahlkreis-*.html", 0),
    ("gremien", "gremien/index.html", 0), ("gremium", "gremien/*.html", 0),
    ("bundesregierung", "gremien/bundesregierung.html", 0), ("fraktion", "fraktionen/*.html", 0),
    ("vorgaenge", "vorgaenge/index.html", 0), ("vorgang", "vorgaenge/[0-9]*.html", -1),
    ("eu-vorlagen", "vorgaenge/eu-vorlagen.html", 0), ("sachgebiete", "sachgebiete/index.html", 0),
    ("sachgebiet", "sachgebiete/*.html", 0), ("sitzungen", "sitzungen/index.html", 0),
    ("sitzung", "sitzungen/21-*.html", -1), ("woche", "woche/20*.html", -1), ("rede", "reden/*.html", 0),
    ("abstimmungen", "abstimmungen/index.html", 0), ("geschlossenheit", "abstimmungen/geschlossenheit.html", 0),
    ("fragen", "regierung/index.html", 0), ("anfragen", "regierung/anfragen.html", 0),
    ("anfrage", "regierung/anfragen/*.html", -1), ("einzelfragen", "regierung/einzelfragen.html", 0),
    ("frage", "regierung/fragen/*.html", -1), ("befragungen", "regierung/regierungsbefragung.html", 0),
    ("befragung", "regierung/regierungsbefragung/*.html", -1),
    ("debattenkultur", "debatte/index.html", 0), ("daten", "daten.html", 0),
    ("suche", "suche.html", 0), ("impressum", "impressum.html", 0), ("kompass", "kompass.html", 0),
    ("themen", "themen/index.html", 0), ("thema", "themen/[0-9]*.html", 0),
    ("themenlandschaft", "themenlandschaft/index.html", 0), ("landschaft-woche", "themenlandschaft/20*.html", -1),
]  # fmt: skip

# Runs in the page, returns [[severity, kind, where, detail]]. `phone` is true at phone width.
AUDIT = r"""
(phone) => {
  const out = [];
  const W = innerWidth;
  const where = (el) => {
    const parts = [];
    for (let e = el, i = 0; e && e.nodeType === 1 && i < 3; e = e.parentElement, i++) {
      let s = e.tagName.toLowerCase();
      if (e.id) { s += '#' + e.id; parts.unshift(s); break; }
      const cls = [...e.classList].slice(0, 2);
      if (cls.length) s += '.' + cls.join('.');
      parts.unshift(s);
    }
    return parts.join(' > ');
  };
  const text = (el) => (el.innerText || el.textContent || el.getAttribute('aria-label') || '')
    .trim().replace(/\s+/g, ' ').slice(0, 60);
  // rendered and not inside a closed <details> (Chromium hides those with content-visibility, which keeps a box)
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    return el.checkVisibility ? el.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true }) : true;
  };
  const placed = (el) => ['absolute', 'fixed'].includes(getComputedStyle(el).position);
  if (document.documentElement.scrollWidth > W + 1)
    out.push(['error', 'page-wider-than-screen', 'html', `${document.documentElement.scrollWidth}px on a ${W}px screen`]);
  for (const el of document.body.querySelectorAll('*')) {
    if (!visible(el)) continue;
    const cs = getComputedStyle(el);
    const clamped = cs.webkitLineClamp && cs.webkitLineClamp !== 'none';
    const ellipsis = cs.textOverflow === 'ellipsis';
    const masked = (cs.maskImage && cs.maskImage !== 'none') || (cs.webkitMaskImage && cs.webkitMaskImage !== 'none');
    const xHidden = cs.overflowX === 'hidden' || cs.overflowX === 'clip';
    const xScroll = cs.overflowX === 'auto' || cs.overflowX === 'scroll';
    const over = el.scrollWidth - el.clientWidth;
    if (xHidden && over > 2 && !ellipsis && !masked && !clamped && el.clientWidth > 0)
      out.push(['error', 'cut-off', where(el), `${over}px of ${el.scrollWidth}px hidden: "${text(el)}"`]);
    if (xScroll && over > 2 && !phone && !el.closest('nav.site, .tabs-in'))
      out.push(['warning', 'scrolls-on-desktop', where(el), `${el.scrollWidth}px in ${el.clientWidth}px`]);
    const yHidden = cs.overflowY === 'hidden' || cs.overflowY === 'clip';
    const down = el.scrollHeight - el.clientHeight;
    if (yHidden && down > 2 && !clamped && !masked && cs.display !== 'inline' && el.clientHeight > 0 && !el.closest('.tabs-in'))
      out.push(['warning', 'cut-off-below', where(el), `${down}px hidden: "${text(el)}"`]);
  }
  for (const img of document.images)
    if (img.complete && img.naturalWidth === 0 && img.getAttribute('src') && visible(img))
      out.push(['error', 'broken-image', where(img), img.getAttribute('src')]);
  for (const el of document.querySelectorAll('a[href], button'))
    if (visible(el) && !text(el) && !el.getAttribute('title') && !el.querySelector('img[alt]:not([alt=""])'))
      out.push(['error', 'no-name', where(el), el.outerHTML.slice(0, 80)]);
  // clickable things that overlap: compare boxes of siblings in one row of controls
  const clickable = [...document.querySelectorAll('button, a.tile, a.row, .chip, input, select')].filter(visible);
  const boxes = clickable.map((el) => el.getBoundingClientRect());
  let overlaps = 0;
  for (let i = 0; i < boxes.length && overlaps < 10; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w <= 2 || h <= 2) continue;
      if (clickable[i].contains(clickable[j]) || clickable[j].contains(clickable[i])) continue;
      // an icon placed over its own field (the search button in the search input) is meant to overlap
      if ((placed(clickable[i]) || placed(clickable[j])) && clickable[i].parentElement === clickable[j].parentElement) continue;
      const small = Math.min(a.width * a.height, b.width * b.height);
      if (w * h > 0.25 * small) {
        out.push(['warning', 'overlap', where(clickable[i]), `overlaps ${where(clickable[j])}`]);
        overlaps++;
        break;
      }
    }
  }
  return out;
}
"""  # noqa: E501


@dataclass
class Result:
    page: str
    viewport: str
    path: str
    findings: list[list[str]] = field(default_factory=list)
    shot: Path | None = None
    changed: float | None = None  # share of changed pixels against the baseline, None without one

    @property
    def errors(self) -> list[list[str]]:
        return [f for f in self.findings if f[0] == "error"]


def pick(site: Path, pattern: str, which: int) -> str | None:
    """The page for a PAGES entry, relative to the site: the path itself, or a match of the glob (never an index
    page or a redirect stub)."""
    if "*" not in pattern:
        return pattern if (site / pattern).is_file() else None
    found = [p.relative_to(site).as_posix() for p in sorted(site.glob(pattern))
             if p.is_file() and p.name != "index.html" and not stub(p)]  # fmt: skip
    return found[which] if found else None


def stub(page: Path) -> bool:
    with page.open(encoding="utf-8", errors="replace") as f:
        return 'http-equiv="refresh"' in f.read(600)


def serve(site: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def try_filters(page, base: str) -> list[list[str]]:
    """Click the first filter of the page (a `[data-f]` button), check that the URL fragment changes and that the
    back button restores it."""
    btn = page.locator("button[data-f]:visible").first
    if not btn.count():
        return []
    before = page.evaluate("location.hash")
    label = (btn.inner_text() or "").strip().split("\n")[0][:40]
    btn.click()
    page.wait_for_timeout(250)
    after = page.evaluate("location.hash")
    if after == before:
        return [["error", "filter-no-url", "button[data-f]", f'click on "{label}" left the fragment at "{before}"']]
    page.go_back()
    page.wait_for_timeout(250)
    back = page.evaluate("location.hash")
    if back != before:
        return [["error", "filter-back", "button[data-f]", f'back after "{label}" gave "{back}", not "{before}"']]
    return []


def axe(page) -> list[list[str]]:
    try:
        page.add_script_tag(url=AXE)
        res = page.evaluate("rules => axe.run(document, {runOnly: rules}).then(r => r.violations.map(v => "
                            "[v.id, v.nodes.length, v.nodes[0] ? v.nodes[0].target.join(' ') : '', v.help]))",
                            AXE_RULES)  # fmt: skip
    except Exception as err:  # offline, or the page blocks it: a note, not a failure
        return [["warning", "axe-skipped", "", str(err).splitlines()[0][:100]]]
    return [["warning", f"a11y:{rule}", target, f"{k}× {help_}"] for rule, k, target, help_ in res]


def compare(shot: Path, base: Path, diff: Path) -> float:
    """Share of changed pixels between a screenshot and its baseline; writes a diff image when they differ."""
    from PIL import Image, ImageChops

    a, b = Image.open(shot).convert("RGB"), Image.open(base).convert("RGB")
    if a.size != b.size:
        w, h = max(a.width, b.width), max(a.height, b.height)
        a2, b2 = Image.new("RGB", (w, h), "white"), Image.new("RGB", (w, h), "white")
        a2.paste(a), b2.paste(b)
        a, b = a2, b2
    d = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 24 else 0)
    share = sum(1 for v in d.getdata() if v) / (d.width * d.height)
    if share:
        red = Image.new("RGB", a.size, (220, 30, 30))
        Image.composite(red, a.point(lambda v: v // 2 + 128), d).save(diff)
    return share


def run(site: Path, out: Path, *, baseline: Path | None = None, only: list[str] | None = None, use_axe: bool = True,
        shots: bool = True) -> list[Result]:  # fmt: skip
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    httpd, base = serve(site)
    results: list[Result] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for vp, (w, h) in VIEWPORTS.items():
                ctx = browser.new_context(viewport={"width": w, "height": h})
                for name, pattern, which in PAGES:
                    if only and name not in only:
                        continue
                    path = pick(site, pattern, which)
                    if not path:
                        continue
                    page = ctx.new_page()
                    r = Result(name, vp, path)
                    page.on("pageerror", lambda e, r=r: r.findings.append(["error", "script-error", "", str(e)[:160]]))
                    page.on("console", lambda m, r=r: r.findings.append(["error", "console-error", "", m.text[:160]])
                            if m.type == "error" else None)  # fmt: skip
                    page.on("response", lambda resp, r=r: r.findings.append(
                        ["error", "failed-request", "", f"{resp.status} {resp.url[len(base):][:120]}"])
                        if resp.status >= 400 and resp.url.startswith(base) else None)  # fmt: skip
                    page.goto(base + path, wait_until="networkidle")
                    page.wait_for_timeout(200)
                    r.findings += page.evaluate(AUDIT, vp == "phone")
                    if shots:
                        r.shot = out / f"{name}-{vp}.png"
                        full = page.evaluate("document.documentElement.scrollHeight")
                        page.screenshot(path=r.shot, full_page=full <= MAX_SHOT,
                                        clip=None if full <= MAX_SHOT else {"x": 0, "y": 0, "width": w,
                                                                            "height": MAX_SHOT})  # fmt: skip
                        old = baseline / r.shot.name if baseline else None
                        if old and old.is_file():
                            r.changed = compare(r.shot, old, out / f"{name}-{vp}.diff.png")
                    if vp == "desktop":
                        r.findings += try_filters(page, base)
                        if use_axe:
                            r.findings += axe(page)
                    results.append(r)
                    page.close()
                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
    return results


def report(results: list[Result], out: Path) -> str:
    lines = ["# UI check", ""]
    errors = sum(len(r.errors) for r in results)
    warnings = sum(len(r.findings) - len(r.errors) for r in results)
    changed = [r for r in results if r.changed is not None and r.changed > CHANGED]
    lines.append(f"{len(results)} page views, {errors} errors, {warnings} warnings, {len(changed)} visually changed.")
    for r in results:
        notes = []
        if r.changed is not None and r.changed > CHANGED:
            notes.append(f"changed {100 * r.changed:.1f} % against the baseline ({r.page}-{r.viewport}.diff.png)")
        if not r.findings and not notes:
            continue
        lines += ["", f"## {r.page} ({r.viewport}): {r.path}"] + [f"- {n}" for n in notes]
        seen: dict[tuple[str, str], int] = {}
        for sev, kind, where, detail in r.findings:
            seen[(sev, kind)] = seen.get((sev, kind), 0) + 1
            if seen[(sev, kind)] <= 8:
                lines.append(f"- **{sev}** {kind} `{where}` {detail}")
        for (sev, kind), k in seen.items():
            if k > 8:
                lines.append(f"- {sev} {kind}: {k - 8} more")
    text = "\n".join(lines) + "\n"
    (out / "report.md").write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("site", type=Path, nargs="?", default=Path("data/out"))
    ap.add_argument("--out", type=Path, default=Path("data/ui"))
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--approve", action="store_true", help="copy this run's screenshots into --baseline")
    ap.add_argument("--only", nargs="*", help="page names from PAGES")
    ap.add_argument("--no-axe", action="store_true")
    ap.add_argument("--no-shots", action="store_true")
    a = ap.parse_args(argv)
    results = run(a.site, a.out, baseline=a.baseline, only=a.only, use_axe=not a.no_axe, shots=not a.no_shots)
    text = report(results, a.out)
    print(text if len(text) < 6000 else text[:6000] + f"\n… the rest in {a.out / 'report.md'}")
    if a.approve and a.baseline:
        a.baseline.mkdir(parents=True, exist_ok=True)
        for r in results:
            if r.shot:
                shutil.copyfile(r.shot, a.baseline / r.shot.name)
        print(f"approved {sum(1 for r in results if r.shot)} screenshots into {a.baseline}")
    (a.out / "results.json").write_text(json.dumps([r.__dict__ | {"shot": str(r.shot)} for r in results],
                                                   ensure_ascii=False, indent=1), encoding="utf-8")  # fmt: skip
    return 1 if any(r.errors for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
