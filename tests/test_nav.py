"""The top bar (docs/plan.md 12.1, D26; docs/architecture.md, "Telling Radar apart"): a search field, then Abgeordnete
· Orte · Gremien, the site's name in the centre (home, with the part of the site), Vorgänge · Sitzungen · Fragen ·
Debattenkultur (quieter) · Daten, and the Radar entry last, in the Radar colour."""

import re

from research import ui

MENU = '<button type="button" class="nav-menu" aria-expanded="false">Menü</button>'  # last in the bar: the phone's menu


def items(html: str) -> list[tuple[str, str]]:
    """(tag, what) in document order: the search form, then every link as (class, label)."""
    out = []
    rx = r'<form class="nav-q"[^>]*>|<a href="[^"]*" data-nav="[^"]*"( class="([^"]*)")?[^>]*>([^<]*)</a>'
    for m in re.finditer(rx, html):
        out.append(("search", "") if m.group(0).startswith("<form") else (m.group(2) or "", m.group(3)))
    return out


def test_order_and_marks():
    html = ui.site_header("../", "places")
    got = items(html)
    assert got[0] == ("search", "")
    assert [label for _, label in got[1:]] == ["Abgeordnete", "Orte", "Gremien", "Vorgänge", "Sitzungen", "Fragen",
                                               "Debattenkultur", "Daten"]  # fmt: skip
    classes = dict((label, cls) for cls, label in got[1:])
    assert "quiet" in classes["Debattenkultur"] and "on" in classes["Orte"]
    assert not any("quiet" in c for label, c in classes.items() if label != "Debattenkultur")
    # the site's name alone in the centre column, leading to the front page; the Radar entry ends the right one
    centre = html.split('<div class="nav-c">', 1)[1].split("</div>", 1)[0]
    assert 'href="../index.html" class="home brand"' in centre and "plenar<b>radar</b>" in centre
    right = html.split('<div class="nav-r">', 1)[1].split("</div>", 1)[0]
    assert right.rstrip().endswith("Radar</a>" + MENU)
    assert f'href="{ui.LANDSCAPE}" data-nav="radar" class="to-radar"' in right
    assert ui.LANDSCAPE in ui.FOOTER and 'class="rl"' in ui.FOOTER


def test_mode():
    """The header says which part of the site a page is in; the front page belongs to both."""
    research = ui.site_header("", None)
    assert '<header class="m-research has-menu">' in research and ">Recherche</span>" in research
    radar = ui.site_header("", "radar", "radar")
    assert '<header class="m-radar has-menu">' in radar and 'class="to-radar on"' in radar
    assert '<span class="mode"><svg class="ri"' in radar
    home = ui.site_header("", "home", "home")
    assert '<header class="m-home has-menu">' in home and 'class="mode"' not in home and 'class="home brand on"' in home
    page = ui.shell(root="", kind="p-x", active="radar", title="T", desc="D", body="", data={}, mode="radar")
    assert '<body class="p-x mode-radar">' in page


def test_search_field_submits_to_the_search_page():
    html = ui.site_header("../", None)
    form = re.search(r'<form class="nav-q" role="search" action="([^"]+)"[^>]*>(.*?)</form>', html, re.S)
    assert form and form.group(1) == "../suche.html"
    assert '<input type="search" name="q"' in form.group(2)  # GET: suche.html?q=…
    assert '<script src="../nav.js" defer></script>' in html
    assert 'aria-current="page">Abgeordnete' in ui.site_header("", "cards")
