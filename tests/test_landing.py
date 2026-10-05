"""The front page (landing.py): the two parts of the site, links only to pages that exist, old links forwarded."""

import json

from research import data, landing, ui


def page(conn, **kw) -> str:
    cards, meta = data.cards(conn)
    decided = data.decisions(conn)
    args = {"speeches": 12, "procedures": 3, "themes": 0, "compass": False, "landscape": False} | kw
    return landing.page(cards, meta, data.sittings(conn, decided), decided, **args)


def test_front_page(conn):
    html = page(conn)
    assert '<header class="m-home">' in html and '<body class="p-home mode-home">' in html
    # an old link to the Abgeordnete list that was the front page keeps working
    assert "location.replace('abgeordnete.html' + location.search + location.hash)" in html
    assert '<section class="world research"' in html and 'href="abgeordnete.html"' in html
    seats = json.loads(html.split("const PAGE = ", 1)[1].split(";\n", 1)[0])["seats"]
    cards, _ = data.cards(conn)
    assert {s["id"] for s in seats} == {
        c["id"] for c in cards if c["kind"] == "member" and not (c["mandate"] or {}).get("to")
    }
    assert '<script src="landing.js" defer></script>' in html


def test_radar_only_what_was_built(conn):
    assert 'class="world radar"' not in page(conn)  # no Themenlandschaft data, no themes, no Kompass
    html = page(conn, themes=32, compass=True, landscape=True)
    radar = html.split('<section class="world radar"', 1)[1].split("</section>", 1)[0]
    assert f'href="{ui.LANDSCAPE}"' in radar and 'href="themen/index.html"' in radar and 'href="kompass.html"' in radar
    assert 'class="rl"' in html  # the week in the Themenlandschaft, as a Radar link
