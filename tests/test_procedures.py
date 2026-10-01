from cards import data, facts, procedures

DIP = ("https://search.dip.bundestag.de/api/v1/vorgang/1", "DIP Vorgang 1", "2026-09-27")


def add_bills(c):
    """Bill g1: Gesetzentwurf 21/500 debated in TOP 2 of sitting 88, decided by show of hands, with a roll-call
    vote linked by Vorgang; a § 80 Unterrichtung 21/501 shared with g2 must not pull in TOP 4. An Antrag v9 that
    never reaches the plenum gets no page."""
    c.executemany(
        "INSERT INTO drucksache VALUES (?,?,21,?,?,?,?,'BT','[]',0,?,?,?)",
        [
            ("d500", "21/500", "Gesetzentwurf", "Mietrecht", "2026-06-01", None, *DIP),
            ("d501", "21/501", "Unterrichtung", "über die gemäß § 80 überwiesenen Vorlagen", "2026-06-10", None, *DIP),
        ],
    )
    c.executemany(
        "INSERT INTO vorgang (id, wahlperiode, type, title, status, subjects, initiators, source_url, "
        "source_document_id, "
        "retrieved_at) VALUES (?,21,?,?,?,?,?,?,?,?)",
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
        "'u','d','t',0)"
    )
    c.execute(
        "INSERT INTO decision VALUES ('21/88/h1','21/88','21/88/2',1,2,'handzeichen','Gesetzentwurf','21/500',"
        "'angenommen',NULL,'Der Gesetzentwurf ist angenommen.','u','d','t',NULL,NULL)"
    )
    c.executemany("INSERT INTO decision_fraction VALUES ('21/88/h1',?,?)", [("SPD", "yes"), ("AfD", "no")])
    c.execute("UPDATE roll_call_vote SET vorgang_id = 'g1' WHERE id = '21/88/2'")


def load(conn):
    decided = data.decisions(conn)
    return {b["id"]: b for b in procedures.load(conn, data.sittings(conn, decided), decided)}


def test_load_without_positions(conn):
    conn.execute("DROP TABLE vorgang_position")  # a store from before the foundation fetched them
    add_bills(conn)
    got = load(conn)
    assert set(got) == {"g1", "g2"}  # the fixture's Anträge v1, v2 and v9 are neither debated nor decided
    b = got["g1"]
    assert b["positions"] is None and b["initiators"] == ["Bundesregierung"] and b["subjects"] == ["Recht"]
    assert [(a["sitting"], a["position"]) for a in b["debates"]] == [("21/88", 2)]  # not TOP 4: 21/501 lists many
    speeches = b["debates"][0]["speeches"]
    assert (speeches[0]["id"], speeches[0]["name"]) == ("ID1", "Dr. Bernd Berg")
    assert not any("-" in s["id"] for s in speeches)  # one entry per rede, Zwischenfragen stay in it
    h1, rc = b["decisions"]
    assert h1["id"] == "21/88/h1" and h1["fractions"] == {"SPD": "yes", "AfD": "no"} and h1["house"] == {"SPD": 3}
    assert rc["id"] == "21/88/2" and rc["counts"]["yes"] == 2  # a roll call linked by its Vorgang, no decision row
    assert [(s["phase"], s["what"]) for s in b["timeline"]] == [
        ("Eingebracht", "Gesetzentwurf"), ("Eingebracht", "Unterrichtung"), ("Beratung", "Beratung im Plenum (TOP 2)"),
        ("Abstimmung", "Abstimmung per Handzeichen"), ("Abstimmung", "Namentliche Abstimmung"),
    ]  # fmt: skip
    assert b["latest"] == "2026-07-08"
    assert got["g2"]["status"] == "unbekannt" and not got["g2"]["debates"]


def test_every_debated_vorgang_is_a_procedure(conn):
    """An Antrag that reaches the plenum gets a page; an agenda item with Vorlagen of two Vorgänge is a debate of
    both, and a decision on a Drucksache of both stays on its own page, linking them."""
    add_bills(conn)
    conn.execute("UPDATE agenda_item SET drucksache_numbers = '[\"21/500\", \"21/100\"]' WHERE id = '21/88/2'")
    conn.execute(
        "INSERT INTO decision VALUES ('21/88/h2','21/88','21/88/2',2,3,'handzeichen','Antrag','21/100',"
        "'abgelehnt',NULL,'Der Antrag ist abgelehnt.','u','d','t',NULL,NULL)"
    )
    got = load(conn)
    assert {"g1", "v1", "v2"} <= set(got) and "v9" not in got
    item = next(i for s in data.sittings(conn) for i in s["items"] if i["id"] == "21/88/2")
    assert [v["id"] for v in item["vorgaenge"]] == ["g1", "v1", "v2"]
    (h2,) = [d for d in data.decisions(conn) if d["id"] == "21/88/h2"]
    assert h2["vorgaenge"] == ["v1", "v2"] and h2["href"] == "abstimmungen/21-88-h2.html"
    # a point on both timelines, but its own page stays the canonical one
    assert "21/88/h2" in {d["id"] for d in got["v1"]["decisions"]} | {d["id"] for d in got["v2"]["decisions"]}


def test_timeline_from_positions(conn):
    add_bills(conn)
    conn.executemany(
        "INSERT INTO vorgang_position VALUES (?,'g1',?,?,?,?,?,?,?,?,'[]',NULL,?,'u','d','t')",
        [
            ("p1", "2026-06-01", "Gesetzentwurf", "BT", "Drucksache", "21/500", "Gesetzentwurf", "https://x/500.pdf",
             None, None),
            ("p2", "2026-07-08", "2. Beratung", "BT", "Plenarprotokoll", "21/88", None, "https://x/88.pdf", "13-18",
             '[{"beschlusstenor": "Annahme", "dokumentnummer": "21/500"}]'),
            ("p3", "2026-07-20", "Zustimmung", "BR", None, None, None, None, None, None),
        ],
    )  # fmt: skip
    b = load(conn)["g1"]
    t = b["timeline"]
    assert [(s["phase"], s["what"]) for s in t] == [
        ("Eingebracht", "Gesetzentwurf"), ("Beratung", "2. Beratung"), ("Abstimmung", "Abstimmung per Handzeichen"),
        ("Abstimmung", "Namentliche Abstimmung"), ("Bundesrat", "Zustimmung"),
    ]  # fmt: skip
    assert t[1]["sitting"] == ("21/88", 2, None) and t[1]["note"] == "Annahme (21/500)"
    assert t[1]["doc"] == ("Plenarprotokoll 21/88, S. 13-18", "https://x/88.pdf")
    assert b["latest"] == "2026-07-20"
    relation = facts.relation_counts(data.decisions(conn))
    html = procedures.procedure_page(b, {"sitzungen/21-88.html"}, data.roll_call_members(conn), relation)
    assert 'href="../sitzungen/21-88.html#top-2"' in html and "auch die im Bundesrat" in html
    assert 'id="abst-21-88-h1"' in html and 'id="abst-21-88-2"' in html  # the votes are points on the timeline
    assert 'class="chart vchart"' in html  # with the seating chart of the roll call


def test_write(conn, tmp_path):
    conn.execute("DROP TABLE vorgang_position")  # a store from before the foundation fetched them
    add_bills(conn)
    decided = data.decisions(conn)
    procs = procedures.write(conn, tmp_path, data.sittings(conn, decided), decided, data.roll_call_members(conn))
    assert {b["id"] for b in procs} == {"g1", "g2"}
    page = (tmp_path / "vorgaenge" / "g1.html").read_text()
    assert "../reden/" not in page  # the speech pages were not written
    assert "Schritte im Bundesrat und die Verkündung fehlen hier" in page
    index = (tmp_path / "vorgaenge" / "index.html").read_text()
    assert 'href="g1.html"' in index and '<option value="Verkündet">Verkündet (1)</option>' in index
    assert 'id="status-verkuendet"' in index
    stub = (tmp_path / "gesetze" / "g1.html").read_text()
    assert 'http-equiv="refresh" content="0; url=../vorgaenge/g1.html"' in stub
    assert '<link rel="canonical" href="../vorgaenge/g1.html">' in stub and "location.replace" in stub
    vote = (tmp_path / "abstimmungen" / "21-88-h1.html").read_text()
    assert 'href="../vorgaenge/g1.html#abst-21-88-h1"' in vote
    assert (tmp_path / "gesetze" / "index.html").read_text().count("../vorgaenge/index.html") >= 2


def test_write_without_vorgang_table(conn, tmp_path):
    conn.execute("DROP TABLE vorgang")
    decided = data.decisions(conn)
    assert procedures.write(conn, tmp_path, data.sittings(conn, decided), decided, {}) == []
    assert (tmp_path / "vorgaenge" / "index.html").exists()  # the nav links it, so it is written even empty
