import json

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


def add_missing_debate(c):
    """An SGB-VI-like Gesetzgebung: DIP records its 1st Beratung in Plenarprotokoll 21/31 (not in the store) and its
    2nd/3rd Beratung in 21/88 with four decisions, but no agenda item names its Drucksache 21/310: the store has the
    preliminary protocol without the late-evening debates."""
    src = ("u", "d", "t")
    c.execute("INSERT INTO drucksache VALUES ('d310','21/310',21,'Gesetzentwurf','SGB VI-Anpassungsgesetz',"
              "'2025-11-03',NULL,'BT','[\"Bundesregierung\"]',0,?,?,?)", src)  # fmt: skip
    c.execute("INSERT INTO vorgang (id, wahlperiode, type, title, status, subjects, initiators, source_url, "
              "source_document_id, retrieved_at) VALUES ('325338',21,'Gesetzgebung','SGB VI-Anpassungsgesetz',"
              "'Verabschiedet','[]','[\"Bundesregierung\"]',?,?,?)", src)  # fmt: skip
    c.execute("INSERT INTO vorgang_drucksache VALUES ('325338','d310')")
    decisions = json.dumps([
        {"beschlusstenor": "Ablehnung", "dokumentnummer": "21/411", "seite": "4227B", "abstimmungsart": "Handzeichen"},
        {"beschlusstenor": "Annahme in Ausschussfassung", "dokumentnummer": "21/310", "seite": "4228A"},
        {"beschlusstenor": "Annahme in Ausschussfassung", "dokumentnummer": "21/310", "seite": "4228C",
         "abstimmungsart": "Handzeichen"},
        {"beschlusstenor": "Ablehnung", "dokumentnummer": "21/412", "seite": "4228D"},
    ], ensure_ascii=False)  # fmt: skip
    c.executemany(
        "INSERT INTO vorgang_position VALUES (?,'325338',?,?,'BT',?,?,?,?,?,'[]',NULL,?,'u','d','t')",
        [("s1", "2025-11-03", "Gesetzentwurf", "Drucksache", "21/310", "Gesetzentwurf", None, None, None),
         ("s2", "2025-11-13", "1. Beratung", "Plenarprotokoll", "21/31", None, None, "3392-3396", None),
         ("s3", "2026-07-08", "2. Beratung", "Plenarprotokoll", "21/88", None,
          "https://dserver.bundestag.de/btp/21/21088.pdf#P.4220", "4220-4228", decisions)],
    )  # fmt: skip


def test_beratung_without_protocol_text(conn):
    """A DIP Beratung whose sitting has no agenda item naming the Vorgang's Drucksachen: the step with its protocol
    PDF and pages, DIP's decisions marked apart, and the note (docs/plan.md 12.6)."""
    add_missing_debate(conn)
    b = load(conn)["325338"]
    first, second = (s for s in b["timeline"] if s["phase"] == "Beratung")
    assert first["missing"]["pdf"] == "https://dserver.bundestag.de/btp/21/21031.pdf"  # built from the number
    assert first["missing"]["pages"] == "3392-3396"
    assert second["missing"]["pdf"].endswith("21088.pdf#P.4220") and len(second["missing"]["decisions"]) == 4
    assert procedures.missing_debates([b]) == {
        "21/31": [{"vorgang": "325338", "title": "SGB VI-Anpassungsgesetz", "pages": "3392-3396",
                   "what": "1. Beratung", "pdf": "https://dserver.bundestag.de/btp/21/21031.pdf"}],
        "21/88": [{"vorgang": "325338", "title": "SGB VI-Anpassungsgesetz", "pages": "4220-4228",
                   "what": "2. Beratung", "pdf": "https://dserver.bundestag.de/btp/21/21088.pdf#P.4220"}],
    }  # fmt: skip
    html = procedures.procedure_page(b, {"sitzungen/21-88.html"}, {}, facts.relation_counts([]))
    li = html.split('class="BT p-Beratung missing"', 2)
    assert len(li) == 3  # both Beratungen
    first_li = li[1].split("</p></li>", 1)[0]
    assert 'href="https://dserver.bundestag.de/btp/21/21031.pdf">Plenarprotokoll 21/31, S. 3392-3396 (PDF)' in first_li
    assert "Der Protokolltext dieser Beratung ist nicht im Datenbestand" in first_li
    second_li = li[2].split("</p></li>", 1)[0]
    assert (
        "Beschlüsse laut DIP" in second_li and "Annahme in Ausschussfassung · Drucksache 21/310 · S. 4228A" in second_li
    )
    assert 'href="../sitzungen/21-88.html' not in second_li  # no agenda item to link
    assert 'class="dec' not in second_li  # DIP's decisions are not drawn as votes parsed from the protocol
