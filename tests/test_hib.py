"""hib ("heute im bundestag") on the Vorgang pages, the Drucksache rows and the Gremium pages. The article texts are
protected: no page shows them (test_e2e.py builds the whole site from these rows and looks for MARKER)."""

from research import bodies, data, facts, procedures

MARKER = "GESCHUETZTER-HIB-TEXT-7f3a"
HIB = "https://www.bundestag.de/presse/hib/kurzmeldungen-{}"
FORSCHUNG = "Forschung, Technologie, Raumfahrt und Technikfolgenabschätzung"
# id, number, date, ressort, kind, title, committee, Drucksachen in the order the text mentions them
ITEMS = [
    ("1223018", "784/2026", "2026-10-07", "Inneres", "Antwort", "Zukunft der unabhängigen Asylverfahrensberatung",
     None, ["21/400", "21/200"]),
    ("1223016", "784/2026", "2026-10-07", "Wirtschaft und Energie", "Antrag",
     "Linke will Offshore-Windindustrie und Klimaziele retten", None, ["21/100"]),
    ("1216000", "700/2026", "2026-09-10", "Recht", "Antrag", "Mietpreisbremse verlängern", None, ["21/100"]),
    ("1217090", "730/2026", "2026-09-23", FORSCHUNG, "Ausschuss", "Reform des Wissenschaftsfreiheitsgesetzes gebilligt",
     "Forschungsausschuss", ["21/4500"]),
    ("1222652", "775/2026", "2026-10-05", "Inneres", "Anhörung", "Experten uneins über Vereinsgesetz",
     "des Innenausschusses", ["21/6805"]),
    ("1217358", "744/2026", "2026-09-23", "Digitales und Staatsmodernisierung", "Ausschuss",
     "Klingbeil im Digitalausschuss", "Ausschuss für Digitales und Staatsmodernisierung", []),
    ("1222700", "776/2026", "2026-10-06", "Gesundheit", "Anhörung", "Sachverständige zur Pflegereform",
     "des Gesundheitsausschusses", ["21/300"]),
    ("1217500", "735/2026", "2026-09-24", "Gesundheit", "Ausschuss", "Pflegebericht beraten", "Gesundheitsausschuss",
     []),
    ("1217600", "736/2026", "2026-09-25", "Haushalt", "Ausschuss", "Vorlagen gebilligt", "im Haushaltsausschuss", []),
]  # fmt: skip


def add_hib(c) -> None:
    """The hib items above, each with MARKER in its protected text."""
    c.executemany(
        "INSERT INTO hib_item VALUES (?,?,?,21,?,?,?,'STO',?,?,?,?,'2026-10-07')",
        [(i, num, d, title, ressort, kind, com, f"{MARKER} Der Text der Meldung {i}.", HIB.format(i), f"hib {num}")
         for i, num, d, ressort, kind, title, com, _ in ITEMS],
    )  # fmt: skip
    c.executemany(
        "INSERT INTO hib_drucksache VALUES (?,?,?)",
        [(i, x, k) for i, *_, drs in ITEMS for k, x in enumerate(drs, 1)],
    )


def test_items_newest_first_without_text(conn):
    add_hib(conn)
    items = data.hib_items(conn)
    assert [h["id"] for h in items[:2]] == ["1223018", "1223016"]  # same day: by id, descending
    assert all("text" not in h and MARKER not in str(h) for h in items)
    first = items[0]
    assert [r["number"] for r in first["drucksachen"]] == ["21/400", "21/200"]  # in the order of the text
    assert first["drucksachen"][0]["url"] == "https://dip.bundestag.de/drucksache/x/d4"  # DIP has it
    assert first["url"] == HIB.format("1223018") and first["number"] == "784/2026"
    assert data.hib_newest(conn)["21/100"] == {"url": HIB.format("1223016"), "number": "784/2026"}


def test_without_hib_tables(conn):
    assert data.hib_items(conn) == []  # tables there, no rows
    conn.executescript("DROP TABLE hib_drucksache; DROP TABLE hib_item;")
    assert data.hib_items(conn) == [] and data.hib_newest(conn) == {}


def _load(conn):
    decided = data.decisions(conn)
    return {b["id"]: b for b in procedures.load(conn, data.sittings(conn, decided), decided)}


def test_vorgang_page_lists_its_hib_items(conn):
    add_hib(conn)
    conn.execute("UPDATE agenda_item SET drucksache_numbers = '[\"21/100\"]' WHERE id = '21/88/2'")
    b = _load(conn)["v2"]  # Drucksachen 21/100 and 21/200
    assert [h["id"] for h in b["hib"]] == ["1223018", "1223016", "1216000"]
    html = procedures.procedure_page(b, set(), {}, facts.relation_counts([]))
    section = html.split('id="hib"', 1)[1].split("</section>", 1)[0]
    assert "hib-Meldungen" in html and "Parlamentsnachrichten des Bundestages" in section
    assert section.index("1223018") < section.index("1223016") < section.index("1216000")
    assert f'href="{HIB.format("1223018")}"' in section
    assert "Zukunft der unabhängigen Asylverfahrensberatung ↗" in section
    assert "Antwort · hib 784/2026" in section
    assert "07.10.2026" in section and "Deutscher Bundestag, hib" in section
    # the Drucksache row links the newest item that names it
    drs = html.split('id="drucksachen"', 1)[1]
    assert f'class="hib" href="{HIB.format("1223016")}"' in drs and "hib ↗" in drs
    assert MARKER not in html


def test_a_vorgang_hib_reported_on_gets_a_page_before_the_plenum(conn):
    conn.execute(
        "INSERT INTO vorgang (id, wahlperiode, type, title, status, subjects, initiators, source_url,"
        " source_document_id, retrieved_at)"
        " VALUES ('v3', 21, 'Kleine Anfrage', 'Pflege', NULL, '[]', '[]', 'u', 'd', 't')"
    )
    conn.execute("INSERT INTO vorgang_drucksache VALUES ('v3', 'd2')")
    assert "v1" not in _load(conn)  # an Antrag the plenum has not taken up
    add_hib(conn)
    loaded = _load(conn)
    assert [h["id"] for h in loaded["v1"]["hib"]] == ["1223016", "1216000"]
    assert "v3" not in loaded  # a Kleine Anfrage has its page under Fragen, hib or not


def test_vorgang_page_without_hib_items(conn):
    conn.execute("UPDATE agenda_item SET drucksache_numbers = '[\"21/100\"]' WHERE id = '21/88/2'")
    html = procedures.procedure_page(_load(conn)["v2"], set(), {}, facts.relation_counts([]))
    assert 'id="hib"' not in html and "hib ↗" not in html


def test_drucksache_row_links_hib():
    r = {"number": "21/100", "url": "https://dip/x", "date": "2026-07-06", "title": "Mieten",
         "hib": {"url": HIB.format("1"), "number": "1/2026"}}  # fmt: skip
    assert f'<a class="hib" href="{HIB.format("1")}"' in facts.drucksache(r)
    assert "hib" not in facts.drucksache(r, compact=True)
    assert 'class="hib"' not in facts.drucksache({**r, "hib": None})


def test_committee_names():
    assert bodies.hib_committee("des Innenausschusses") == "Innenausschuss"
    assert bodies.hib_committee("Forschungsausschuss") == "Forschungsausschuss"
    assert bodies.hib_committee("des Ausschusses für Gesundheit") == "Ausschuss für Gesundheit"
    assert bodies.hib_committee("des Auswärtigen Ausschusses") == "Auswärtiger Ausschuss"
    assert bodies.hib_committee("im  Haushaltsausschuss") == "Haushaltsausschuss"


def test_hib_by_body_and_the_names_left_over(conn):
    add_hib(conn)
    cards, _ = data.cards(conn)
    groups = bodies.load_bodies(conn, cards)
    items = data.hib_items(conn)
    got = bodies.hib_by_body(items, groups)
    assert [h["id"] for h in got["Ausschuss für Gesundheit"]] == ["1222700", "1217500"]
    assert [h["id"] for h in got["Haushaltsausschuss"]] == ["1217600"]
    # the committees of the fixture's items that are no body of the fixture: listed, to be added to HIB_COMMITTEES
    # (or, here, missing from the Stammdaten of the fixture)
    assert bodies.hib_unmatched(items, groups) == [
        "Ausschuss für Digitales und Staatsmodernisierung", "Forschungsausschuss", "Innenausschuss"]  # fmt: skip


def test_every_short_form_names_a_full_committee_name():
    for short, full in bodies.HIB_COMMITTEES.items():
        assert short.endswith("ausschuss") or short.endswith("Ausschuss"), short
        assert full.startswith("Ausschuss "), full


def test_gremium_page_timeline(conn, tmp_path):
    add_hib(conn)
    cards, _ = data.cards(conn)
    bodies.write(conn, tmp_path, cards, data.government(conn), data.decisions(conn), {})
    page = (tmp_path / "gremien" / "gesundheit.html").read_text()
    section = page.split('id="hib"', 1)[1].split("</section>", 1)[0]
    assert "Sitzungen und Anhörungen laut hib" in page
    assert section.index("Oktober 2026") < section.index("1222700") < section.index("September 2026")
    assert section.index("September 2026") < section.index("1217500")
    assert "Anhörung · hib 776/2026 · Drs. " in section and ">21/300</a>" in section  # its Drucksache, via facts
    assert "Deutscher Bundestag, hib" in section
    assert 'id="hib"' not in (tmp_path / "gremien" / "praesidium.html").read_text()  # no items: no section
    for p in tmp_path.rglob("*.html"):
        assert MARKER not in p.read_text(), p
