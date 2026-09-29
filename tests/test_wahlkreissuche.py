from cards import wahlkreissuche

SRC = ("https://www.bundeswahlleiterin.de/…/btw25_wkr_gemeinden_20241130_utf8.csv",
       "Bundeswahlleiterin, BTW 2025 Wahlkreiseinteilung (Stand 2024-11-30)", "2026-09-29")  # fmt: skip


def test_municipalities_none_without_table(conn):
    conn.execute("DROP TABLE constituency_municipality")
    assert wahlkreissuche.municipalities(conn) is None


def test_municipalities_none_while_table_empty(conn):
    assert wahlkreissuche.municipalities(conn) is None  # the schema has the table before the file was fetched


def add_municipalities(conn):
    conn.executemany(
        "INSERT INTO constituency_municipality VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("btw25/13003000/14", "btw25", "13003000", "Rostock, Hanse- und Universitätsstadt", "Rostock", "MV",
             14, 0, *SRC),  # fmt: skip
            ("btw25/02000000/18", "btw25", "02000000", "Hamburg", "Hamburg", "HH", 18, 1, *SRC),
            ("btw25/02000000/19", "btw25", "02000000", "Hamburg", "Hamburg", "HH", 19, 1, *SRC),
        ],
    )  # fmt: skip


def test_municipalities_groups_split_gemeinde(conn):
    add_municipalities(conn)
    rows = {r["n"]: r for r in wahlkreissuche.municipalities(conn)}
    assert rows["Rostock, Hanse- und Universitätsstadt"]["w"] == [14]
    assert rows["Hamburg"]["w"] == [18, 19]
    assert rows["Hamburg"]["d"] == "Hamburg" and rows["Hamburg"]["s"] == "HH"


def card(pid, name, fraction, via, number, list_state=None, left=None):
    return {
        "id": pid,
        "name": name,
        "fraction": fraction,
        "mandate": {"to": left},
        "election": {"via": via, "number": number, "list_state": list_state},
    }


def test_member_index_direct_candidates_and_other_list_members():
    cards = [
        card("1", "Anna Adler", "SPD", "constituency", 14),
        card("2", "Bernd Berg", "CDU/CSU", "list", 14, list_state="MV"),  # stood in 14, lost it, entered via list
        card("3", "Clara Cohn", "Die Linke", "list", None, list_state="MV"),  # list only, no Wahlkreis
        card("4", "Dora Dahl", "AfD", "list", 99, list_state="BY"),  # different Land: not in MV's list
        card("5", "Speaker", "SPD", None, None),  # no election data: skipped
    ]
    idx = wahlkreissuche.member_index(cards)
    assert idx["direct"]["14"]["id"] == "1"
    assert [c["id"] for c in idx["candidates"]["14"]] == ["2"]
    assert {m["id"] for m in idx["list_by_state"]["MV"]} == {"2", "3"}
    assert "BY" in idx["list_by_state"] and idx["list_by_state"]["BY"][0]["id"] == "4"


def test_write_skips_page_without_table(tmp_path, conn):
    conn.execute("DROP TABLE constituency_municipality")
    written = wahlkreissuche.write(conn, tmp_path, [], [])
    assert written == {}
    assert not (tmp_path / "wahlkreise").exists()


def test_write_page_with_table(tmp_path, conn):
    add_municipalities(conn)
    cards = [card("1", "Anna Adler", "SPD", "constituency", 14)]
    wks = [{"number": 14, "name": "Rostock – Landkreis Rostock II", "state": "MV"}]
    written = wahlkreissuche.write(conn, tmp_path, cards, wks)
    assert written == {"wahlkreise": 1}
    html = (tmp_path / "wahlkreise" / "suche.html").read_text(encoding="utf-8")
    assert "Rostock, Hanse- und Universitätsstadt" in html
    assert '"direct":{"14":{"id":"1"' in html.replace(" ", "")


def test_activity_counts_reden_and_links_the_latest():
    c = {"reden": [{"id": "ID1", "date": "2026-07-08", "title": "Mietpreisbremse"},
                   {"id": "ID7", "date": "2026-09-10", "title": "Haushalt"}]}  # fmt: skip
    assert wahlkreissuche.activity(c) == {
        "reden": 2, "last": {"date": "2026-09-10", "title": "Haushalt", "page": "ID7"}
    }  # fmt: skip
    assert wahlkreissuche.activity({"reden": []}) == {"reden": 0}
