from pathlib import Path

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
