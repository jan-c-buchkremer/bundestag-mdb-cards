import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from research import careers, data, places

JS = Path(__file__).parent.parent / "src" / "research" / "places.js"


def site(conn, tmp_path):
    cards, _ = data.cards(conn)
    decided = data.decisions(conn)
    places.write(tmp_path, cards, data.constituencies(conn), careers.constituted(conn), decided,
                 data.roll_call_members(conn))  # fmt: skip
    return lambda name: (tmp_path / "orte" / f"{name}.html").read_text()


def add_places(conn):
    """A second Wahlkreis in Bayern, and in NRW a list member who left and one who moved up after the constituent
    sitting (2026-07-08 in the fixture)."""
    kerg = ("https://x/kerg2.csv", "Bundeswahlleiterin, BTW 2025 Ergebnisse nach Wahlkreisen", "t")
    conn.execute("INSERT INTO constituency VALUES ('btw25/243','btw25',243,'Erlangen','BY','CSU',1,1,?,?,?)", kerg)
    conn.execute("UPDATE mandate SET to_date = '2026-06-30' WHERE id = '5/21'")
    conn.execute("UPDATE mandate SET from_date = '2026-08-01' WHERE id = '6/21'")


def test_list_members_on_their_land_and_every_wahlkreis_of_it(conn, tmp_path):
    add_places(conn)
    page = site(conn, tmp_path)
    by = page("bayern")
    assert 'href="../2.html">Dr. Bernd Berg</a>' in by and "Landesliste, Platz 3" in by
    stood, other = page("wahlkreis-242"), page("wahlkreis-243")
    assert 'href="../2.html"' in stood and "hat hier im Wahlkreis kandidiert" in stood
    assert 'href="../2.html"' in other and "hat hier im Wahlkreis kandidiert" not in other  # still listed
    members = by.split('id="mitglieder"', 1)[1].split('id="reden"', 1)[0]
    assert 'href="../1.html"' not in members  # Anna Adler is Mecklenburg-Vorpommern's
    assert 'href="../1.html"' in page("wahlkreis-14") and "Direktmandat" in page("wahlkreis-14")


def test_moved_up_and_left_with_dates(conn, tmp_path):
    add_places(conn)
    nw = site(conn, tmp_path)("nordrhein-westfalen")
    assert "ausgeschieden am 30.06.2026" in nw and "nachgerückt am 01.08.2026" in nw


def test_wahlkreis_without_direct_member_says_why(conn, tmp_path):
    page = site(conn, tmp_path)("wahlkreis-58")
    assert "Kein direkt gewähltes Mitglied" in page and "AfD (33,3 %)" in page and "Zweitstimmendeckung" in page
    assert '<section class="facet" id="erwaehnungen">' in page  # the empty slot for place mentions


def test_member_without_land_stays_on_the_bund_page(conn, tmp_path):
    bund = site(conn, tmp_path)("index")
    assert "Ohne Land in den Daten" in bund and 'href="../4.html"' in bund  # Dora Dahl: only in the vote lists


def test_representation_without_election_tables(conn):
    conn.executescript("DROP TABLE election_candidacy; DROP TABLE constituency;")
    cards, _ = data.cards(conn)
    rep = places.representation(cards, data.constituencies(conn), None)
    assert [x["card"]["id"] for x in rep["wahlkreise"][14]["direct"]] == ["1"]  # the Stammdaten's Direktwahl
    assert {x["card"]["id"] for x in rep["lists"]["BY"]} == {"2"}


def listed(page: str) -> list[str]:
    """The person ids a place page lists in its Mitglieder facet."""
    members = page.split('id="mitglieder"', 1)[1].split('<section class="facet"', 1)[0]
    return re.findall(r'<a href="\.\./([^/"]+)\.html">', members)


def node_expand(members: dict, keys: list[str]) -> dict[str, list[str]]:
    """places.js `expand` run in Node over the payload, as the Abgeordnete page runs it."""
    script = (f"const P = require({json.dumps(str(JS))}); const m = {json.dumps(members)};"
              f"const keys = {json.dumps(keys)};"
              "console.log(JSON.stringify(Object.fromEntries(keys.map(k => [k, P.expand(m, k)]))));")  # fmt: skip
    return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)


def test_place_filter_lists_exactly_the_place_page_members(conn, tmp_path):
    """The Abgeordnete page's place filter (places.index_payload, expanded by places.js) and the place page list the
    same members, for a Wahlkreis and a Land, list members included (D25)."""
    add_places(conn)
    page = site(conn, tmp_path)
    cards, _ = data.cards(conn)
    payload = places.index_payload(cards, data.constituencies(conn))["members"]
    cases = {"242": "wahlkreis-242", "243": "wahlkreis-243", "14": "wahlkreis-14", "BY": "bayern",
             "NW": "nordrhein-westfalen", "MV": "mecklenburg-vorpommern"}  # fmt: skip
    for key, name in cases.items():
        assert set(places.expand(payload, key)) == set(listed(page(name))), key
    assert set(places.expand(payload, "243")) == {"2"}  # no direct member: the Bavarian list member only
    assert {"5", "6", "7"} <= set(places.expand(payload, "NW"))  # list members, the one who left included
    if shutil.which("node"):
        js = node_expand(payload, list(cases))
        assert {k: set(v) for k, v in js.items()} == {k: set(places.expand(payload, k)) for k in cases}


def test_compact_expands_to_membership(conn):
    add_places(conn)
    cards, _ = data.cards(conn)
    rep = places.representation(cards, data.constituencies(conn), None)
    full, small = places.membership(rep), places.compact(rep)
    assert {k: places.expand(small, k) for k in full} == full
    assert small["242"] == ["@BY:liste"]  # a Wahlkreis refers to its Land's list instead of repeating it


def test_list_member_without_land_is_on_the_bund_page_only(conn, tmp_path):
    """Lena Lose has a list mandate but no Land in the data: listed on the Bund page, in no Land's filter."""
    page = site(conn, tmp_path)
    bund = page("index")
    assert 'href="../10.html"' in bund.split("Ohne Land in den Daten", 1)[1]
    cards, _ = data.cards(conn)
    payload = places.index_payload(cards, data.constituencies(conn))["members"]
    assert not any("10" in places.expand(payload, k) for k in payload)


def test_place_pages_link_the_filtered_plenum_and_the_hub(conn, tmp_path):
    page = site(conn, tmp_path)
    assert 'href="../index.html#ort=242">Im Plenum zeigen</a>' in page("wahlkreis-242")
    assert 'href="../index.html#ort=BY">Im Plenum zeigen</a>' in page("bayern")
    assert 'href="index.html#wk=242">Auf der Karte</a>' in page("wahlkreis-242")
    hub = page("index")
    for part in ('id="suche"', 'id="karte"', 'id="laender"', 'href="wahlkreis-242.html"', 'href="bayern.html"',
                 '<script src="../wkmap.js"></script>'):  # fmt: skip
        assert part in hub, part
    index = json.loads((tmp_path / "orte" / "orte.json").read_text())
    assert [242, "Fürth", "BY"] in index["wahlkreise"] and ["BY", "Bayern", "bayern"] in index["lands"]
    stub = (tmp_path / "wahlkreise" / "suche.html").read_text()
    assert 'href="../orte/index.html#suche"' in stub


def test_place_search_and_old_index_states_in_node(conn):
    """places.js: the place search over orte.json, and the old view states of the Abgeordnete page that moved."""
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    cards, _ = data.cards(conn)
    rep = places.representation(cards, data.constituencies(conn), None)
    index = places.place_index(rep, [{"n": "Fürth, Stadt", "d": "Fürth", "s": "BY", "w": [242]}])
    slugs = {code: data.land_slug(code) for code in data.STATES}
    script = (f"const P = require({json.dumps(str(JS))}); const idx = {json.dumps(index)};"
              f"const s = {json.dumps(slugs)};"
              "console.log(JSON.stringify({search: ['bayern', '242', 'fürth'].map(q => P.search(idx, q)),"
              "legacy: ['#ansicht=wahlkreise', '#ansicht=wahlkreise&wk=14', '#ansicht=wahlkreise&state=BY',"
              "'#ansicht=plenum&q=x', ''].map(h => P.legacyTarget(h, s))}));")  # fmt: skip
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    bayern, nr, fuerth = out["search"]
    assert bayern[0] == {"kind": "land", "key": "BY", "label": "Bayern", "sub": "Land", "href": "orte/bayern.html"}
    assert nr[0]["href"] == "orte/wahlkreis-242.html" and nr[0]["key"] == "242"
    assert [h["kind"] for h in fuerth] == ["wk", "gemeinde"] and fuerth[1]["href"] == "orte/wahlkreis-242.html"
    assert out["legacy"] == ["orte/index.html", "orte/wahlkreis-14.html", "orte/bayern.html", None, None]
