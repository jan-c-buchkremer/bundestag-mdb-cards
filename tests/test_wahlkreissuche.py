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


def test_write_skips_page_without_table(tmp_path, conn):
    conn.execute("DROP TABLE constituency_municipality")
    written = wahlkreissuche.write(conn, tmp_path, [])
    assert written == {}
    assert not (tmp_path / "wahlkreise").exists()


def test_write_page_with_table(tmp_path, conn):
    add_municipalities(conn)
    wks = [{"number": 14, "name": "Rostock – Landkreis Rostock II", "state": "MV"}]
    written = wahlkreissuche.write(conn, tmp_path, wks)
    assert written == {"wahlkreise": 1}
    html = (tmp_path / "wahlkreise" / "suche.html").read_text(encoding="utf-8")
    assert "Rostock, Hanse- und Universitätsstadt" in html
    # an entry point: it links the place pages and renders no member list of its own (D17)
    assert (
        "../orte/wahlkreis-" in html
        and '"MV":{"name":"Mecklenburg-Vorpommern","slug":"mecklenburg-vorpommern"}' in html
    )
    assert '"direct"' not in html and "list_by_state" not in html
