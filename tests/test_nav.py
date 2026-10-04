"""The top bar (docs/plan.md 12.1, D26): a search field, then Orte · Gremien · Abgeordnete (home, centre) · Vorgänge
· Sitzungen · Fragen · Debattenkultur (quieter) · Daten, and no Themenlandschaft item."""

import re

from research import ui


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
    assert [label for _, label in got[1:]] == ["Orte", "Gremien", "Abgeordnete", "Vorgänge", "Sitzungen", "Fragen",
                                               "Debattenkultur", "Daten"]  # fmt: skip
    classes = dict((label, cls) for cls, label in got[1:])
    assert "home" in classes["Abgeordnete"] and "quiet" in classes["Debattenkultur"] and "on" in classes["Orte"]
    assert not any(
        "home" in c or "quiet" in c for label, c in classes.items() if label not in ("Abgeordnete", "Debattenkultur")
    )
    # the home item alone in the centre column of the grid, Daten the last item of the right one
    centre = html.split('<div class="nav-c">', 1)[1].split("</div>", 1)[0]
    assert re.findall(r">([^<]+)</a>", centre) == ["Abgeordnete"]
    right = html.split('<div class="nav-r">', 1)[1].split("</div>", 1)[0]
    assert re.findall(r">([^<]+)</a>", right)[-1] == "Daten"
    assert "Themenlandschaft" not in html and ui.LANDSCAPE not in html
    assert ui.LANDSCAPE in ui.FOOTER  # it moved to the footer


def test_search_field_submits_to_the_search_page():
    html = ui.site_header("../", None)
    form = re.search(r'<form class="nav-q" role="search" action="([^"]+)"[^>]*>(.*?)</form>', html, re.S)
    assert form and form.group(1) == "../suche.html"
    assert '<input type="search" name="q"' in form.group(2)  # GET: suche.html?q=…
    assert '<script src="../nav.js" defer></script>' in html
    assert 'class="home' in ui.site_header("", "cards") and 'aria-current="page">Abgeordnete' in ui.site_header(
        "", "cards"
    )
