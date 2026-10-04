"""Search: the search page `suche.html`, the entity index `suche.json` and the Pagefind index in `pagefind/`.

Entity resolution first (docs/plan.md 11.7, D20): the build writes every entity with its canonical page into
`suche.json` (persons, groups, places with the Gemeinden, Vorgänge, topics, sitting weeks), and `search.js`
resolves a query against it in the browser, grouped by type. Below, one "Reden" section of full-text hits.

Pagefind (the `pagefind` package ships its binary) indexes the built site as the last step of the build and writes
a static index; the browser loads only the index chunks a query needs. `suche.html` carries its own UI (`search.js`)
built on the Pagefind JS API, styled like the rest of the site, not Pagefind's default UI. Pages opt in with
`data-pagefind-body`: only the speech pages now (their text, not the protocol's comments).
Filters come from `data-pagefind-filter`; `search.js` reads their live counts from Pagefind's own `filters()` and
`search()` results, so the panel never needs its own count logic."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from research import data, urls
from research.ui import FOOTER, ORDER, TOKEN, shell

# the entity types, in the order the results show them (search.js reads them from suche.json)
TYPES = ("Person", "Gruppe", "Ort", "Vorgang", "Thema", "Sitzungswoche")
GEMEINDE = "Gemeinde"  # the sub line of a Gemeinde entry; the light index leaves them out

BODY = f"""<h1>Suche</h1>
<p class="lead">Findet zuerst, was der Bundestag ist: Abgeordnete, Fraktionen und Gremien, Länder, Wahlkreise und
Gemeinden, Vorgänge, Themen und Sitzungswochen, jeweils mit ihrer Seite. Darunter die Volltextsuche in allen Reden
der 21. Wahlperiode; die Filter grenzen sie nach Art, Fraktion, Person, Monat und Thema ein.</p>
<div class="search" id="search">
  <div class="s-bar">
    <input type="search" id="sq" placeholder="Name, Ort, Vorgang, Thema oder Wort aus einer Rede …"
      autocomplete="off" aria-label="Suche">
    <button type="button" id="sf-toggle" class="sf-toggle" aria-expanded="false" aria-controls="sf-panel">Filter
    </button>
  </div>
  <div class="s-entities" id="s-entities" aria-live="polite"></div>
  <h2 class="s-h">Reden</h2>
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


def entities(cards: list[dict], bodies: list[dict], government: bool, procs: list[dict], places: dict,
             gemeinden: list[dict] | None, themes: dict[int, dict], sittings: list[dict]) -> dict:  # fmt: skip
    """The entity index: {"types": TYPES, "items": [[type, label, sub, href, keys], …]}, each href a canonical
    page relative to the site root, `keys` further words it is found by (a Wahlkreis number, a week's dates)."""
    from research import pages

    items: list[list] = []

    def add(kind: str, label: str, sub: str, href: str, keys: str = "") -> None:
        items.append([TYPES.index(kind), label, sub, href, keys])

    for c in cards:
        m = c.get("mandate") or {}
        sub = c["fraction"] or "fraktionslos" if c["kind"] == "member" else c.get("role") or "ohne Mandat"
        add("Person", c["name"], sub, urls.person(c["id"]), " ".join(filter(None, [c.get("role"), m.get("to") and
                                                                                  "ausgeschieden"])))  # fmt: skip
    for f in ORDER:
        add("Gruppe", f, "Fraktion", f"fraktionen/{TOKEN[f]}.html", "Fraktion Grüne" if "GRÜNEN" in f else "Fraktion")
    if government:
        add("Gruppe", "Bundesregierung", "Regierung", urls.GOVERNMENT, "Regierung Kabinett Minister")
    for b in bodies:
        add("Gruppe", b["short"], "Ausschuss" if b["kind"] == "committee" else "Gremium", f"gremien/{b['slug']}.html",
            b["name"])  # fmt: skip
    add("Ort", "Bund", "16 Länder, alle Wahlkreise", urls.PLACES, "Deutschland Länder")
    for code, name in data.STATES.items():
        add("Ort", name, "Land", urls.land(code), code)
    wk_names = {}
    for nr, w in places["wahlkreise"].items():
        wk_names[nr] = w["name"]
        add("Ort", f"Wahlkreis {nr}: {w['name']}", data.STATES.get(w["state"], "Wahlkreis"), urls.wahlkreis(nr),
            str(nr))  # fmt: skip
    for g in gemeinden or []:
        for nr in g["w"]:
            if nr in wk_names:
                part = " (Teil)" if len(g["w"]) > 1 else ""
                add("Ort", f"{g['n']}{part}", f"{GEMEINDE} im Wahlkreis {nr}: {wk_names[nr]}", urls.wahlkreis(nr),
                    g["d"])  # fmt: skip
    for p in procs:
        add("Vorgang", p["title"], f"{p['type']} · {p['status']}", urls.vorgang(p["id"]), " ".join(p["initiators"]))
    for th in themes.values():
        add("Thema", th["label"], f"{len(th['speeches'])} Reden", urls.theme(th["id"]))
    weeks: dict[str, list[dict]] = {}
    for st in sittings:
        weeks.setdefault(st["week"], []).append(st)
    for week, ss in sorted(weeks.items(), reverse=True):
        keys = " ".join(f"{st['number']}. Sitzung {st['date'][8:10]}.{st['date'][5:7]}.{st['date'][:4]}" for st in ss)
        add("Sitzungswoche", pages.week_label(week), ", ".join(f"{st['number']}. Sitzung" for st in ss),
            urls.week(week), f"{week} {keys}")  # fmt: skip
    return {"types": list(TYPES), "items": items}


def search_page() -> str:
    return shell(root="", kind="p-search", active=None, title="Suche – Bundestag, 21. Wahlperiode",
                 desc="Volltextsuche in den Reden, Abstimmungen, Sitzungen und Abgeordneten des 21. Bundestages.",
                 body=BODY, data={"kind": "search"},
                 head=HEAD)  # fmt: skip


LABEL = 110  # characters of a label in the light index; a Vorgang's title can be several hundred


def light(index: dict) -> dict:
    """The index for the top bar's suggestions (nav.js), loaded on the first keystroke on any page: the same entities
    without the Gemeinden (some 11,000 of them, found on the search page), labels cut to LABEL characters."""
    items = [[t, label if len(label) <= LABEL else label[: LABEL - 1] + "…", sub, href, keys]
             for t, label, sub, href, keys in index["items"] if not sub.startswith(GEMEINDE)]  # fmt: skip
    return {"types": index["types"], "items": items}


def write_index(out: Path, index: dict | None = None) -> None:
    """Write suche.html, suche.json and suche-kurz.json (light), then index the speech pages into out/pagefind/
    (replacing an older index)."""
    (out / "suche.html").write_text(search_page(), encoding="utf-8")
    if index is not None:
        for name, payload in (("suche.json", index), ("suche-kurz.json", light(index))):
            (out / name).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    shutil.rmtree(out / "pagefind", ignore_errors=True)
    # the protocol's comments and the chair's words on speech pages are shown, not searched
    skip = ".speech .rc, .speech .rch"
    subprocess.run([sys.executable, "-m", "pagefind", "--site", str(out), "--quiet", "--exclude-selectors", skip],
                   check=True)  # fmt: skip
