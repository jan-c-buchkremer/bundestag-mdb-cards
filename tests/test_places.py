from cards import careers, data, places


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
