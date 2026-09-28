from conftest import STAMM, mandate, membership

from cards import careers, data


def add_changes(c):
    """Yvonne (SPD, NW) leaves on 31.07.2026 and Paul (SPD, NW) moves up on 01.08.2026; Zora leaves the CDU/CSU
    for fraktionslos; Xaver leaves the SPD without joining another fraction."""
    c.execute("UPDATE mandate SET to_date = '2026-07-31' WHERE id = '6/21'")
    c.execute(
        "INSERT INTO person VALUES ('8','Paul','Pohl',NULL,NULL,'1980-01-01','Bonn','männlich','SPD',1,NULL,NULL,"
        "NULL,NULL,?,?,?)",
        STAMM,
    )
    c.execute("INSERT INTO mandate VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", mandate("8", 21, "Landesliste", state="NW"))
    c.execute("UPDATE mandate SET from_date = '2026-08-01' WHERE id = '8/21'")
    c.executemany(
        "INSERT INTO membership VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            membership("6", 1, "fraction", "SPD", to="2026-07-31"),
            membership("7", 1, "fraction", "CDU/CSU", to="2026-05-05"),
            membership("7", 2, "fraction", "fraktionslos", frm="2026-05-05"),
            membership("5", 1, "fraction", "SPD", to="2026-06-01"),
        ],
    )


def test_tenure(conn):
    ms = careers.members(conn)
    rows = {r["fraction"]: r for r in careers.tenure(ms)}
    assert rows["SPD"]["counts"]["3"] == 1 and rows["SPD"]["counts"]["1"] == 2  # Adler 19-21; Xaver, Yvonne
    assert rows["SPD"]["first"] == 2 / 3
    assert "Dahl" not in {m["last_name"] for m in ms}  # no WP 21 mandate in the Stammdaten


def test_changes(conn):
    add_changes(conn)
    ms = careers.members(conn)
    assert "Yvonne" not in {m["last_name"] for m in ms if m["to"] is None}
    ch = careers.changes(ms, careers.constituted(conn))
    assert [m["name"] for m in ch["left"]] == ["Yvonne Yvonne"]
    assert [(m["name"], m["after"]["name"]) for m in ch["joined"]] == [("Paul Pohl", "Yvonne Yvonne")]
    moved = [(x["member"]["name"], x["from"], x["to"], x["date"]) for x in ch["moved"]]
    assert moved == [("Zora Zora", "CDU/CSU", "fraktionslos", "2026-05-05"),
                     ("Xaver Xaver", "SPD", "fraktionslos", "2026-06-01")]  # fmt: skip
    html = careers.page(ms, ch, careers.offices(conn, ms))
    assert "nach dem Ausscheiden von" in html and 'href="../8.html"' in html and "Nordrhein-Westfalen" in html


def test_first_speech(conn):
    # thanks the previous speaker, then calls Berg: not Berg's first speech
    conn.execute("INSERT INTO speech_paragraph VALUES ('ID12/1','ID12',1,'chair',"
                 "'Gratulation zu Ihrer ersten Rede! – Das Wort hat Dr. Bernd Berg.')")  # fmt: skip
    cards, _ = data.cards(conn)
    careers.annotate(conn, cards)
    by = {c["id"]: c for c in cards}
    fs = by["2"]["first_speech"]
    assert (fs["id"], fs["date"], fs["sitting"], fs["maiden"]) == ("ID1", "2026-07-08", "21/88", False)
    assert by["3"]["first_speech"]["id"] == "ID3" and not by["3"]["first_speech"]["maiden"]
    assert by["9"]["first_speech"] is None  # not a member
    conn.execute("INSERT INTO speech_paragraph VALUES ('ID1-7/1','ID1-7',1,'chair',"
                 "'Herr Kollege Berg, herzlichen Glückwunsch zu Ihrer ersten Rede.')")  # fmt: skip
    assert careers.first_speech(conn, by["2"])["maiden"]
    conn.execute("UPDATE speech_paragraph SET text = 'Es spricht Dr. Bernd Berg. Das ist seine erste Rede.' "
                 "WHERE id = 'ID12/1'")  # fmt: skip
    conn.execute("DELETE FROM speech_paragraph WHERE id = 'ID1-7/1'")
    assert careers.first_speech(conn, by["2"])["maiden"]


def test_write(conn, tmp_path):
    assert careers.write(conn, tmp_path) == {"karrieren": 1}
    html = (tmp_path / "karrieren" / "index.html").read_text()
    assert "Wahlperioden im Bundestag" in html and 'href="../1.html"' in html
