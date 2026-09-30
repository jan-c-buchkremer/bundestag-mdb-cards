from cards import data, questions, sources

DIP = ("https://search.dip.bundestag.de/api/v1/drucksache/9", "BT-Drs. 21/9", "2026-09-27")


def add_questions(c):
    """Two AfD Kleine Anfragen, one answered via the Vorgang (10 days), one via the title (20 days), one open; a
    Sammeldrucksache of Schriftliche Fragen with one asker; a Fragestunde without speeches."""
    c.executemany(
        "INSERT INTO drucksache VALUES (?,?,21,?,?,?,?,'BT',?,?,?,?,?)",
        [
            ("k1", "21/10", "Kleine Anfrage", "Brücken", "2026-06-01", None, '["Fraktion der AfD"]', 5, *DIP),
            ("k2", "21/11", "Kleine Anfrage", "Tunnel", "2026-06-01", None, '["Fraktion der AfD"]', 5, *DIP),
            ("k3", "21/12", "Kleine Anfrage", "Häfen", "2026-07-01", None, '["Fraktion DIE LINKE"]', 5, *DIP),
            ("a1", "21/20", "Antwort", "auf die Kleine Anfrage\r\n- Drucksache 21/99 -\r\nBrücken", "2026-06-11",
             None, '["Bundesregierung"]', 0, *DIP),
            ("a2", "21/21", "Antwort", "auf die Kleine Anfrage\r\n- Drucksache 21/11 -\r\nTunnel", "2026-06-21",
             None, '["Bundesregierung"]', 0, *DIP),
            ("s1", "21/30", "Schriftliche Fragen", "Schriftliche Fragen", "2026-07-03", None, "[]", 1, *DIP),
        ],
    )  # fmt: skip
    c.executemany(
        "INSERT INTO vorgang (id, wahlperiode, type, title, status, subjects, initiators, source_url, "
        "source_document_id, "
        "retrieved_at) VALUES (?,21,?,?,NULL,'[]','[]',?,?,?)",
        [("vk1", "Kleine Anfrage", "Brücken", *DIP), ("vs1", "Schriftliche Frage", "A", *DIP),
         ("vs2", "Schriftliche Frage", "B", *DIP)],
    )  # fmt: skip
    c.executemany(
        "INSERT INTO vorgang_drucksache VALUES (?,?)", [("vk1", "k1"), ("vk1", "a1"), ("vs1", "s1"), ("vs2", "s1")]
    )
    c.execute("INSERT INTO drucksache_author VALUES ('s1/c','s1','c','3','Clara Cohn','Frage',?,?,?)", DIP)
    c.execute(
        "INSERT INTO agenda_item VALUES ('21/88/3','21/88',3,'Tagesordnungspunkt 3','Fragestunde','[]','u','d','t',0)"
    )


def test_kleine_anfragen(conn):
    add_questions(conn)
    ka = questions.kleine_anfragen(conn)
    by = {r["number"]: r for r in ka["rows"]}
    assert by["21/10"]["answer"]["days"] == 10  # the Vorgang wins over the title's (wrong) number
    assert by["21/11"]["answer"]["number"] == "21/21"  # title fallback
    assert by["21/12"]["answer"] is None and by["21/12"]["fractions"] == ["Die Linke"]
    assert by["21/10"]["url"] == "https://dserver.bundestag.de/btd/21/000/2100010.pdf"
    s = {x["fraction"]: x for x in questions.ka_summary(ka)}
    assert (s["AfD"]["asked"], s["AfD"]["answered"], s["AfD"]["median"], s["AfD"]["in_time"]) == (2, 2, 15, 0.5)
    assert ka["as_of"] == "2026-07-09" and s["Die Linke"]["open"][0]["age"] == 8


def test_months():
    span, c = questions.months({"x": ["2026-01-05", "2026-03-01"]})
    assert span == ["2026-01", "2026-02", "2026-03"] and c["x"]["2026-02"] == 0


def test_written_and_befragung(conn):
    add_questions(conn)
    w = questions.written_questions(conn)["Schriftliche Frage"]
    assert w["total"] == 2 and w["months"]["2026-07"] == 2 and w["askers"] == {"Die Linke": 1}
    (b,) = questions.befragungen(conn)
    assert [g["name"] for g in b["government"]] == ["Stefanie Hubig"] and b["questions"] == {"SPD": 1}
    assert questions.fragestunden(conn) == (1, 0)


def test_write_pages(conn, tmp_path):
    add_questions(conn)
    assert questions.write(conn, tmp_path) == {"regierung": 1}
    page = (tmp_path / "regierung" / "index.html").read_text()
    assert "BT-Drs. 21/12" in page and "../sitzungen/21-88.html#top-1" in page and "Fragestunden" in page
    export = tmp_path / "export"
    export.mkdir()
    (export / "README.md").write_text("x")
    files = sources.copy_export(tmp_path, str(export))
    assert files == [{"path": "daten/README.md", "name": "README.md", "size": 1}]
    _, meta = data.cards(conn)
    sources.write(conn, tmp_path, meta)
    daten = (tmp_path / "daten.html").read_text()
    assert 'href="daten/README.md"' in daten and "Deutscher Bundestag/Bundesrat – DIP" in daten


def test_copy_export_absent(tmp_path):
    assert sources.copy_export(tmp_path, "") == []
    assert sources.copy_export(tmp_path, str(tmp_path / "missing")) == []


def test_stale_roles(conn):
    conn.execute("DELETE FROM government_role")
    conn.execute(
        "INSERT INTO government_role VALUES ('protocol:1:parl_sts:x','1',NULL,'Anna Adler','Parlamentarische "
        "Staatssekretärin','BMF','parl_sts','2026-01-01','2026-03-01','u','d','t','protocol')"
    )
    (r,) = sources.stale_roles(conn)
    assert r["days"] == 129 and r["name"] == "Anna Adler"
    assert sources.stale_roles(conn, days=200) == []
