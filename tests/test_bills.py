from cards import bills

DIP = ("https://search.dip.bundestag.de/api/v1/vorgang/1", "DIP Vorgang 1", "2026-09-27")
POSITION = """CREATE TABLE vorgang_position (
    id TEXT PRIMARY KEY, vorgang_id TEXT NOT NULL, date TEXT NOT NULL, position TEXT NOT NULL, chamber TEXT,
    document_kind TEXT, document_number TEXT, document_type TEXT, pdf_url TEXT, pages TEXT,
    originators TEXT NOT NULL, ressort TEXT, decisions TEXT,
    source_url TEXT NOT NULL, source_document_id TEXT NOT NULL, retrieved_at TEXT NOT NULL
)"""


def add_bills(c):
    """Bill g1: Gesetzentwurf 21/500 debated in TOP 2 of sitting 88, decided by show of hands, with a roll-call
    vote linked by Vorgang; a § 80 Unterrichtung 21/501 shared with g2 must not pull in TOP 4. An Antrag v9 is no
    bill."""
    c.executemany(
        "INSERT INTO drucksache VALUES (?,?,21,?,?,?,?,'BT','[]',0,?,?,?)",
        [
            ("d500", "21/500", "Gesetzentwurf", "Mietrecht", "2026-06-01", None, *DIP),
            ("d501", "21/501", "Unterrichtung", "über die gemäß § 80 überwiesenen Vorlagen", "2026-06-10", None, *DIP),
        ],
    )
    c.executemany(
        "INSERT INTO vorgang VALUES (?,21,?,?,?,?,?,?,?,?)",
        [
            ("g1", "Gesetzgebung", "Mietrechtsgesetz", "Verkündet", '["Recht"]', '["Bundesregierung"]', *DIP),
            ("g2", "Gesetzgebung", "Anderes Gesetz", None, "[]", "[]", *DIP),
            ("v9", "Antrag", "Ein Antrag", None, "[]", "[]", *DIP),
        ],
    )
    c.executemany("INSERT INTO vorgang_drucksache VALUES (?,?)", [("g1", "d500"), ("g1", "d501"), ("g2", "d501")])
    c.execute("UPDATE agenda_item SET drucksache_numbers = '[\"21/500\"]' WHERE id = '21/88/2'")
    c.execute(
        "INSERT INTO agenda_item VALUES ('21/88/4','21/88',4,'Tagesordnungspunkt 4','Sonstiges','[\"21/501\"]',"
        "'u','d','t')"
    )
    c.execute(
        "INSERT INTO decision VALUES ('21/88/h1','21/88','21/88/2',1,2,'handzeichen','Gesetzentwurf','21/500',"
        "'angenommen',NULL,'Der Gesetzentwurf ist angenommen.','u','d','t')"
    )
    c.executemany("INSERT INTO decision_fraction VALUES ('21/88/h1',?,?)", [("SPD", "yes"), ("AfD", "no")])
    c.execute("UPDATE roll_call_vote SET vorgang_id = 'g1' WHERE id = '21/88/2'")


def test_load_without_positions(conn):
    add_bills(conn)
    got = {b["id"]: b for b in bills.load(conn)}
    assert set(got) == {"g1", "g2"}
    b = got["g1"]
    assert b["positions"] is None and b["initiators"] == ["Bundesregierung"] and b["subjects"] == ["Recht"]
    assert [a["id"] for a in b["debates"]] == ["21/88/2"]  # not TOP 4: 21/501 lists many bills
    speeches = b["debates"][0]["speeches"]
    assert (speeches[0]["id"], speeches[0]["name"]) == ("ID1", "Dr. Bernd Berg")
    assert not any("-" in s["id"] for s in speeches)  # one entry per rede, Zwischenfragen stay in it
    (d,) = b["decisions"]
    assert d["result"] == "angenommen" and d["fractions"] == {"SPD": "yes", "AfD": "no"}
    assert [v["id"] for v in b["votes"]] == ["21/88/2"]
    assert [s["what"] for s in b["timeline"]] == [
        "Gesetzentwurf", "Unterrichtung", "Beratung im Plenum (TOP 2)", "Beschluss über 21/500",
        "Namentliche Abstimmung",
    ]  # fmt: skip
    assert b["latest"] == "2026-07-08"
    assert got["g2"]["status"] == "unbekannt" and not got["g2"]["debates"]


def test_timeline_from_positions(conn):
    add_bills(conn)
    conn.execute(POSITION)
    conn.executemany(
        "INSERT INTO vorgang_position VALUES (?,'g1',?,?,?,?,?,?,?,?,'[]',NULL,?,'u','d','t')",
        [
            ("p1", "2026-06-01", "Gesetzentwurf", "BT", "Drucksache", "21/500", "Gesetzentwurf", "https://x/500.pdf",
             None, None),
            ("p2", "2026-07-08", "2. Beratung", "BT", "Plenarprotokoll", "21/88", None, "https://x/88.pdf", "13-18",
             '[{"beschlusstenor": "Annahme", "dokumentnummer": "21/500"}]'),
            ("p3", "2026-07-20", "Verkündung", "BR", None, None, None, None, None, None),
        ],
    )  # fmt: skip
    (b,) = [b for b in bills.load(conn) if b["id"] == "g1"]
    t = b["timeline"]
    assert [s["what"] for s in t] == ["Gesetzentwurf", "2. Beratung", "Verkündung"]
    assert t[1]["sitting"] == ("21/88", 2) and t[1]["note"] == "Annahme (21/500)"
    assert t[1]["doc"] == ("Plenarprotokoll 21/88, S. 13-18", "https://x/88.pdf")
    assert b["latest"] == "2026-07-20"
    html = bills.bill_page(b, {"sitzungen/21-88.html"})
    assert 'href="../sitzungen/21-88.html#top-2"' in html and "auch die im Bundesrat" in html


def test_write(conn, tmp_path):
    add_bills(conn)
    (tmp_path / "abstimmungen").mkdir()
    (tmp_path / "abstimmungen" / "21-88-h1.html").write_text("")
    assert bills.write(conn, tmp_path) == {"gesetze": 3}
    page = (tmp_path / "gesetze" / "g1.html").read_text()
    assert 'href="../abstimmungen/21-88-h1.html"' in page
    assert "../sitzungen/21-88" not in page and "../reden/" not in page  # those pages were not written
    assert "Schritte im Bundesrat und die Verkündung fehlen hier" in page
    index = (tmp_path / "gesetze" / "index.html").read_text()
    assert 'href="g1.html"' in index and '<option value="Verkündet">Verkündet (1)</option>' in index


def test_write_without_bills(conn, tmp_path):
    assert bills.write(conn, tmp_path) == {}
