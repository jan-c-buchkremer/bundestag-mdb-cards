"""Stubs at the old paths of moved pages (docs/plan.md section 11.3, D21). GitHub Pages is static, so a redirect is
an HTML file: a meta refresh for browsers without JavaScript, a canonical link, a visible link, and a
`location.replace` that carries the old query and fragment over, rewritten by the stub's fragment rules (an old
anchor that has a new name, or none at all).

The live output folder is never emptied, so every page that moves must get its stub in the same build: an old page
left in place would keep serving stale content."""

from __future__ import annotations

import json
import os
from pathlib import Path

from cards.ui import e

PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Umgezogen: {title}</title>
<meta http-equiv="refresh" content="0; url={href}">
<link rel="canonical" href="{href}">
<script>
(function () {{
  var target = {target}, rules = {rules};
  var old = location.hash.slice(1), frag = target.frag;
  for (var i = 0; i < rules.length; i++) {{
    var rx = new RegExp(rules[i][0]);
    if (rx.test(old)) {{ frag = old.replace(rx, rules[i][1]); old = null; break; }}
  }}
  if (old) frag = old;  // an old fragment without a rule is kept as it is
  location.replace(target.path + location.search + (frag ? '#' + frag : ''));
}})();
</script>
<style>
body {{ font: 15px/1.5 Inter, system-ui, sans-serif; margin: 40px 16px; color: #1f2328; }}
a {{ color: #2563eb; }}
</style>
</head>
<body>
<p>Diese Seite ist umgezogen: <a href="{href}">{title}</a></p>
</body>
</html>
"""


def relative(old: str, target: str) -> str:
    """The target (relative to the site root, "vorgaenge/x.html#abst-1") as seen from the old page's folder."""
    path, _, frag = target.partition("#")
    rel = os.path.relpath(path, os.path.dirname(old) or ".").replace(os.sep, "/")
    return rel + (f"#{frag}" if frag else "")


def stub(old: str, target: str, title: str, rules: list[tuple[str, str]] | None = None) -> str:
    """The stub for `old` (a path relative to the site root) pointing at `target`. `rules` are (regex, replacement)
    pairs tried on the old fragment in order; the first that matches gives the new fragment. Without a match an old
    fragment is kept, and without an old fragment the target's own fragment is used."""
    href = relative(old, target)
    path, _, frag = href.partition("#")
    js = json.dumps({"path": path, "frag": frag}, ensure_ascii=False).replace("</", r"<\/")
    return PAGE.format(title=e(title), href=e(href), target=js,
                       rules=json.dumps([list(r) for r in rules or []]).replace("</", r"<\/"))  # fmt: skip


def write(out: Path, old: str, target: str, title: str, rules: list[tuple[str, str]] | None = None) -> None:
    """Write the stub for `old` into the output folder, replacing whatever page was there."""
    path = out / old
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stub(old, target, title, rules), encoding="utf-8")


def any_fragment(new: str) -> list[tuple[str, str]]:
    """Rules for a page that had no anchors of its own: whatever fragment an old link carries, go to `new`."""
    return [(".*", new)]
