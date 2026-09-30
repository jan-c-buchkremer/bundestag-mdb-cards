"""Full-text search: the search page `suche.html` and the Pagefind index in `pagefind/`.

Pagefind (the `pagefind` package ships its binary) indexes the built site as the last step of the build and writes
a static index; the browser loads only the index chunks a query needs. `suche.html` carries its own UI (`search.js`)
built on the Pagefind JS API, styled like the rest of the site, not Pagefind's default UI. Pages opt in with
`data-pagefind-body`: speech pages (their text, not the protocol's comments), cards, vote and sitting pages.
Filters come from `data-pagefind-filter`; `search.js` reads their live counts from Pagefind's own `filters()` and
`search()` results, so the panel never needs its own count logic."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from cards.ui import FOOTER, e, search_marks, shell

BODY = f"""<h1>Suche</h1>
<p class="lead">Volltextsuche in allen Reden der 21. Wahlperiode, in den Karten der Abgeordneten, den Abstimmungen
und den Sitzungen. Die Filter grenzen nach Art, Fraktion, Person, Monat und Thema ein.</p>
<div class="search" id="search">
  <div class="s-bar">
    <input type="search" id="sq" placeholder="Reden, Namen, Themen durchsuchen …" autocomplete="off" aria-label="Suche">
    <button type="button" id="sf-toggle" class="sf-toggle" aria-expanded="false" aria-controls="sf-panel">Filter
    </button>
  </div>
  <div class="s-count" id="s-count" aria-live="polite"></div>
  <div class="s-layout">
    <aside class="s-filters" id="sf-panel" aria-label="Filter"></aside>
    <div class="rows" id="s-results"></div>
  </div>
  <button type="button" class="more" id="s-more" hidden>Weitere Treffer</button>
</div>
<noscript><p>Die Suche braucht JavaScript.</p></noscript>
<footer>{FOOTER}</footer>
<script type="module" src="search.js"></script>"""


HEAD = '<link rel="stylesheet" href="reden.css">'


def card_block(c: dict, desc: str) -> str:
    """What the search knows of a card, which is otherwise drawn by card.js: name, description, committees and
    offices. Hidden on the page itself."""
    places = [x["name"] for x in c.get("committees") or []] + [o.get("office") or "" for o in c.get("government") or []]
    marks = search_marks("Abgeordnete" if c["kind"] == "member" else "Rednerin/Redner", None, Person=c["name"],
                         Fraktion=c.get("fraction"))  # fmt: skip
    return (f'<div hidden data-pagefind-body>{marks}<h1 data-pagefind-meta="title">{e(c["name"])}</h1>'
            f'<p>{e(desc)}</p><p>{e(", ".join(p for p in places if p))}</p></div>')  # fmt: skip


def search_page() -> str:
    return shell(root="", kind="p-search", active="search", title="Suche – Bundestag, 21. Wahlperiode",
                 desc="Volltextsuche in den Reden, Abstimmungen, Sitzungen und Abgeordneten des 21. Bundestages.",
                 body=BODY, data={"kind": "search"},
                 head=HEAD)  # fmt: skip


def write_index(out: Path) -> None:
    """Write suche.html, then index the whole site into out/pagefind/ (replacing an older index)."""
    (out / "suche.html").write_text(search_page(), encoding="utf-8")
    shutil.rmtree(out / "pagefind", ignore_errors=True)
    # the protocol's comments and the chair's words on speech pages are shown, not searched
    skip = ".speech .rc, .speech .rch"
    subprocess.run([sys.executable, "-m", "pagefind", "--site", str(out), "--quiet", "--exclude-selectors", skip],
                   check=True)  # fmt: skip
