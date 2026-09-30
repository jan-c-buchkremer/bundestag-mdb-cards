import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cards import search

HERE = Path(__file__).parent


def test_search_page_has_custom_ui_markup():
    page = search.search_page()
    # no more Pagefind default UI
    assert "PagefindUI" not in page and "pagefind-ui" not in page
    # the skeleton search.js fills: input, mobile filter toggle, filter panel, result list, "mehr laden"
    assert '<input type="search" id="sq"' in page
    assert 'id="sf-toggle"' in page and 'aria-controls="sf-panel"' in page
    assert '<aside class="s-filters" id="sf-panel"' in page
    assert '<div class="rows" id="s-results"></div>' in page
    assert '<button type="button" class="more" id="s-more" hidden>Weitere Treffer</button>' in page
    assert '<script type="module" src="search.js"></script>' in page
    assert '<link rel="stylesheet" href="reden.css">' in page
    assert "Art, Fraktion, Person, Monat und Thema" in page


def test_pages_js_ships_the_highlight_script():
    """The highlight-and-scroll code lives in pages.js, loaded by every shell()-built page, speech pages included."""
    js = (HERE.parent / "src" / "cards" / "pages.js").read_text(encoding="utf-8")
    assert "function highlightQuery" in js
    assert "getAll('hl')" in js
    assert "data-pagefind-body" in js
    assert "scrollIntoView" in js
    assert "highlightQuery();" in js


def site_index(conn):
    from cards import bodies, careers, data, places, procedures, topics, wahlkreissuche

    cards, _ = data.cards(conn)
    decided = data.decisions(conn)
    sittings = data.sittings(conn, decided)
    rep = places.representation(cards, data.constituencies(conn), careers.constituted(conn))
    themes = topics.by_theme(json.loads((HERE / "speech_themes.json").read_text()), data.speech_facts(cards))
    procs = procedures.load(conn, sittings, decided)
    return search.entities(cards, bodies.load_bodies(conn, cards), True, procs, rep,
                           wahlkreissuche.municipalities(conn), themes, sittings)  # fmt: skip


def test_entity_index_has_every_type(conn):
    index = site_index(conn)
    types = {index["types"][t] for t, *_ in index["items"]}
    assert types == {"Person", "Gruppe", "Ort", "Thema", "Sitzungswoche"}  # the fixture has no debated Vorgang
    by_href = {href: (index["types"][t], label) for t, label, _, href, _ in index["items"]}
    assert by_href["1.html"] == ("Person", "Anna Adler")
    assert by_href["fraktionen/spd.html"] == ("Gruppe", "SPD")
    assert by_href["orte/wahlkreis-14.html"] == ("Ort", "Wahlkreis 14: Rostock")
    assert by_href["woche/2026-W28.html"] == ("Sitzungswoche", "Sitzungswoche 28/2026")
    assert by_href["themen/3.html"][0] == "Thema"


def test_entities_resolve_grouped_by_type(conn, tmp_path):
    """search.js's resolve() over the index the build writes: entities grouped by type, each with its page."""
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    path = tmp_path / "suche.json"
    path.write_text(json.dumps(site_index(conn), ensure_ascii=False))
    js = HERE.parent / "src" / "cards" / "search.js"
    script = (f"const s = require({json.dumps(str(js))}); const idx = require({json.dumps(str(path))});"
              "console.log(JSON.stringify(['rostock', 'spd', 'miete', '88. sitzung', 'bayern'].map(q => s.resolve(idx, q))));")  # fmt: skip # noqa: E501
    rostock, spd, miete, sitting, bayern = json.loads(subprocess.run(["node", "-e", script], capture_output=True,
                                                                     text=True, check=True).stdout)  # fmt: skip
    assert [g["type"] for g in rostock] == ["Ort"] and rostock[0]["items"][0]["href"] == "orte/wahlkreis-14.html"
    assert [g["type"] for g in spd][:2] == ["Person", "Gruppe"]  # SPD members, then the fraction itself
    assert spd[1]["items"][0] == {"label": "SPD", "sub": "Fraktion", "href": "fraktionen/spd.html"}
    assert miete[0]["type"] == "Thema" and miete[0]["items"][0]["href"] == "themen/3.html"
    assert sitting[0]["items"][0]["href"] == "woche/2026-W28.html"
    assert bayern[0]["items"][0]["href"] == "orte/bayern.html"  # the Land before the list members from Bayern
