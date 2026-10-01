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


def add_research(c):
    """The research view's cases: a Kleine Anfrage with signers and its answer, in a Vorgang without a page (a
    Kleine Anfrage never reaches the plenum); an Antrag by Anna Adler whose Vorgang has no page either; a Schriftliche
    Frage whose Sammeldrucksache names one asker (Clara Cohn), with its ministry; a Mündliche Frage answered in the
    Fragestunde of sitting 88 (Plenarprotokoll step), whose Sammeldrucksache names two askers; the Fragestunde turns
    (test_fragestunde)."""
    from test_fragestunde import add_fragestunde

    add_fragestunde(c)
    c.executemany(
        "INSERT INTO drucksache VALUES (?,?,21,?,?,?,?,'BT',?,?,?,?,?)",
        [
            ("rk1", "21/610", "Kleine Anfrage", "Brückensanierung", "2026-06-01", None, '["Fraktion der SPD"]', 2,
             *DIP),
            ("ra1", "21/700", "Antwort", "auf die Kleine Anfrage - Drucksache 21/610 - Brückensanierung",
             "2026-06-20", "https://x/700.pdf", '["Bundesregierung"]', 0, *DIP),
            ("rn1", "21/620", "Antrag", "Mehr Radwege", "2026-06-02", None, '["Fraktion der SPD"]', 1, *DIP),
            ("rs1", "21/630", "Schriftliche Fragen", "Schriftliche Fragen", "2026-07-03", None, "[]", 1, *DIP),
            ("rm1", "21/640", "Fragen", "Fragen für die Fragestunde", "2026-07-06", None, "[]", 2, *DIP),
        ],
    )  # fmt: skip
    c.executemany(
        "INSERT INTO vorgang (id, wahlperiode, type, title, status, subjects, initiators, source_url, "
        "source_document_id, retrieved_at) VALUES (?,21,?,?,?,'[]','[]',?,?,?)",
        [("rvk", "Kleine Anfrage", "Brückensanierung", "Beantwortet", *DIP),
         ("rvn", "Antrag", "Mehr Radwege", "Noch nicht beraten", *DIP),
         ("rvs", "Schriftliche Frage", "Ausbau der Ladesäulen an Autobahnen", "Beantwortet", *DIP),
         ("rvm", "Mündliche Frage", "Termin für das Mietgesetz", "Beantwortet", *DIP)],
    )  # fmt: skip
    c.executemany("INSERT INTO vorgang_drucksache VALUES (?,?)",
                  [("rvk", "rk1"), ("rvk", "ra1"), ("rvn", "rn1"), ("rvs", "rs1"), ("rvm", "rm1")])  # fmt: skip
    c.executemany(
        "INSERT INTO drucksache_author VALUES (?,?,?,?,?,?,?,?,?)",
        [("rk1/a", "rk1", "a", "1", "Anna Adler, MdB, SPD", "Kleine Anfrage", *DIP),
         ("rk1/x", "rk1", "x", "5", "Xaver Xaver, MdB, SPD", "Kleine Anfrage", *DIP),
         ("rn1/a", "rn1", "a", "1", "Anna Adler, MdB, SPD", "Antrag", *DIP),
         ("rs1/c", "rs1", "c", "3", "Clara Cohn, MdB, Die Linke", "Frage", *DIP),
         ("rm1/a", "rm1", "a", "1", "Anna Adler, MdB, SPD", "Frage", *DIP),
         ("rm1/b", "rm1", "b", "2", "Bernd Berg, MdB, CDU/CSU", "Frage", *DIP)],
    )  # fmt: skip
    bmdv = '[{"titel": "Bundesministerium für Verkehr", "federfuehrend": true}]'
    c.executemany(
        "INSERT INTO vorgang_position VALUES (?,?,?,?,'BT',?,?,?,?,?,'[]',?,NULL,'u','d','t')",
        [("rp1", "rvs", "2026-07-03", "Schriftliche Frage", "Drucksache", "21/630", "Schriftliche Fragen", None, None,
          bmdv),
         ("rp2", "rvk", "2026-06-20", "Antwort", "Drucksache", "21/700", "Antwort", None, None, bmdv),
         ("rp3", "rvm", "2026-07-08", "Mündliche Frage", "Plenarprotokoll", "21/88", None,
          "https://dserver.bundestag.de/btp/21/21088.pdf", "40-41", '[{"titel": "Bundesministerium der Justiz"}]')],
    )  # fmt: skip


def test_research_lists_each_kind_with_its_sources(conn):
    add_research(conn)
    cards = {c["id"] for c in data.cards(conn)[0]}
    lists = questions.research(conn, cards)
    assert set(lists) == {s for s, _, _ in questions.KINDS}

    ka = lists["kleine-anfragen"]
    row = next(r for r in ka["rows"] if ka["docs"][r[0]][0] == "21/610")
    assert (
        row[1] == "Brückensanierung" and row[2] == ["SPD"] and ka["ressorts"][row[4]] == "Bundesministerium für Verkehr"
    )
    assert [ka["persons"][i][:2] for i in row[3]] == [["1", "Anna Adler"], ["5", "Xaver Xaver"]]
    assert ka["docs"][row[0]][1] == "rk1" and ka["docs"][row[5][0]][3] == "https://x/700.pdf" and row[5][1] == 19
    assert row[6] == "rvk"  # the Vorgang, linked in DIP: it has no page here

    sf = lists["schriftliche-fragen"]
    (row,) = [r for r in sf["rows"] if r[0] == "rvs"]
    assert row[2] == "Ausbau der Ladesäulen an Autobahnen" and sf["ressorts"][row[4]] == "Bundesministerium für Verkehr"
    assert sf["persons"][row[6]] == ["3", "Clara Cohn", "Die Linke", 1]  # the only asker of its Sammeldrucksache
    assert sf["docs"][row[5]][:3] == ["21/630", "rs1", "2026-07-03"]

    mf = lists["muendliche-fragen"]
    (row,) = mf["rows"]
    assert row[6] is None  # two askers in the Sammeldrucksache: not attributed to either
    assert row[7] == ["21/88", 3, "40-41", "https://dserver.bundestag.de/btp/21/21088.pdf", "21/88"]

    fs = lists["fragestunde"]
    assert [r[0] for r in fs["rows"]] == ["21/88/3/f1", "21/88/3/f2"]
    assert fs["rows"][1][3] == "Bundesministerin" and fs["rows"][0][3] is None  # an answer, a question
    assert fs["persons"][fs["rows"][0][2]][:2] == ["1", "Anna Adler"]

    rb = lists["regierungsbefragung"]
    assert [r[0] for r in rb["rows"]] == ["ID10", "ID11", "ID12"] and rb["rows"][0][
        6
    ] == "Befragung der Bundesregierung"


def test_research_page_frame(conn, tmp_path):
    add_research(conn)
    questions.write(conn, tmp_path, {c["id"] for c in data.cards(conn)[0]})
    page = (tmp_path / "regierung" / "index.html").read_text()
    assert 'id="liste"' in page and 'data-k="schriftliche-fragen"' in page and "Nur Titel:" in page
    assert '<script src="../fragen.js"></script>' in page and "Kleine Anfragen</h2>" in page  # statistics stay
    for slug, _, _ in questions.KINDS:
        assert (tmp_path / "regierung" / f"{slug}.json").is_file()


def test_research_json_size_on_the_full_data_shape():
    """The lists on the live data's shape (2,740 Kleine Anfragen with about 15 signers each, 9,038 Schriftliche
    Fragen, 1,624 Mündliche Fragen, 1,536 Fragestunde and 3,047 Befragung turns), with titles of a realistic length:
    each kind's file stays small enough to load on demand."""
    import gzip
    import json
    import random

    rnd = random.Random(21)
    words = [
        "Förderung",
        "Ausbau",
        "Bundesmittel",
        "Sanierung",
        "Brücken",
        "Schienen",
        "Pflegekräfte",
        "Rente",
        "Digitalisierung",
        "Klima",
    ]

    def title(k: int) -> str:
        return " ".join(rnd.choice(words) for _ in range(k))

    pk = questions.Packer(set(), {})
    persons = [pk.person(str(i), f"Vorname Nachname {i}", "SPD") for i in range(650)]
    ministries = [pk.ressort(f"Bundesministerium für {title(3)}") for _ in range(16)]
    weekly = [pk.doc(f"21/{9000 + i}", str(900000 + i), "2026-05-07", None) for i in range(80)]
    sizes = {}
    ka = [[pk.doc(f"21/{i}", str(100000 + i), "2026-05-07", None), title(12), ["AfD"],
           [rnd.choice(persons) for _ in range(15)], rnd.choice(ministries),
           [pk.doc(f"21/{20000 + i}", str(200000 + i), "2026-05-21", None), 14], str(300000 + i)]
          for i in range(2740)]  # fmt: skip
    sizes["kleine-anfragen"] = pk.payload("kleine-anfragen", [], ka)
    sf = [[str(400000 + i), None, title(11), pk.status("Beantwortet"), rnd.choice(ministries), rnd.choice(weekly),
           rnd.choice(persons), None] for i in range(9038)]  # fmt: skip
    sizes["schriftliche-fragen"] = questions.Packer(set(), {}).payload("schriftliche-fragen", [], sf)
    turns = [[f"ID21{i:05d}", "2026-05-07", rnd.choice(persons), None, "21/50", 4, "Befragung der Bundesregierung",
              title(14)[:120]] for i in range(3047)]  # fmt: skip
    sizes["regierungsbefragung"] = questions.Packer(set(), {}).payload("regierungsbefragung", [], turns)
    raw = {k: json.dumps(v, ensure_ascii=False, separators=(",", ":")).encode() for k, v in sizes.items()}
    kb = {k: (len(v) // 1024, len(gzip.compress(v)) // 1024) for k, v in raw.items()}  # (as written, as served)
    print(kb)
    assert all(served < 450 for _, served in kb.values()), kb  # GitHub Pages serves JSON gzip-compressed
    assert kb["schriftliche-fragen"][0] < 1400 and kb["kleine-anfragen"][0] < 900, kb
