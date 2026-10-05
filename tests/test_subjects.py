"""Sachgebiete (subjects.py) and the EU-Vorlagen (eu.py): every Vorgang with a Sachgebiet counts, a decision is
listed once, what has no Sachgebiet is named, and the EU-Vorlagen get a Stand from DIP's steps."""

import re

import test_procedures

from research import data, eu, procedures, search, subjects, urls

DIP = ("u", "d", "t")
EUROPE = subjects.EUROPE


def add_subjects(c):
    """Vorgänge with Sachgebiete that never reach the plenum (a Kleine Anfrage of Die Linke, a bill of a ministry
    and one of a Land, an Antrag on Europe), three EU-Vorlagen and a Petition without a Sachgebiet."""
    c.executemany(
        "INSERT INTO drucksache VALUES (?,?,21,?,?,?,?,'BT',?,0,?,?,?)",
        [
            ("d700", "21/700", "Kleine Anfrage", "Häfen", "2026-05-04", None, '["Fraktion Die Linke"]', *DIP),
            ("d701", "21/701", "Gesetzentwurf", "Zoll", "2026-05-05", None, '["Bundesregierung"]', *DIP),
            ("d702", "21/702", "Antrag", "Europa stärken", "2026-05-06", None, "[]", *DIP),
            ("d800", "21/800", "Unterrichtung", "Unionsdokumente", "2026-04-01", "https://x/800.pdf", "[]", *DIP),
            ("d801", "21/801", "Unterrichtung", "Unionsdokumente", "2026-04-15", None, "[]", *DIP),
        ],
    )  # fmt: skip
    c.executemany(
        "INSERT INTO vorgang (id, wahlperiode, type, title, status, subjects, initiators, source_url, "
        "source_document_id, retrieved_at) VALUES (?,21,?,?,?,?,?,?,?,?)",
        [
            ("w1", "Kleine Anfrage", "Häfen", "Beantwortet", '["Wirtschaft", "Verkehr"]', '["Fraktion DIE LINKE"]',
             *DIP),
            ("w2", "Gesetzgebung", "Zollgesetz", "Noch nicht beraten", '["Wirtschaft"]',
             '["Bundesministerium der Finanzen", "Bayern"]', *DIP),
            ("w3", "Antrag", "Europa stärken", None, f'["{EUROPE}", "Wirtschaft"]',
             '["Fraktion BÜNDNIS 90/DIE GRÜNEN"]', *DIP),
            ("e1", "EU-Vorlage", "Proposal for a Regulation on ports", None, "[]", "[]", *DIP),
            ("e2", "EU-Vorlage", "Mitteilung der Kommission", None, "[]", "[]", *DIP),
            ("e3", "EU-Vorlage", "Richtlinie über Zölle", None, "[]", "[]", *DIP),
            ("p1", "Petition", "Eine Petition", None, "[]", "[]", *DIP),
        ],
    )  # fmt: skip
    c.executemany(
        "INSERT INTO vorgang_drucksache VALUES (?,?)",
        [("w1", "d700"), ("w2", "d701"), ("w3", "d702"), ("e1", "d800"), ("e2", "d800"), ("e3", "d801")],
    )
    c.executemany(
        "INSERT INTO vorgang_position VALUES (?,?,?,?,'BT','Drucksache',?,'Unterrichtung',NULL,NULL,'[]',NULL,?,"
        "'u','d','t')",
        [
            ("q1", "e1", "2026-04-01", "Unterrichtung", "21/800", None),
            ("q2", "e1", "2026-04-02", "Überweisung gemäß § 93 GO-BT", None, None),
            ("q3", "e2", "2026-04-01", "Unterrichtung", "21/800", None),
            ("q4", "e3", "2026-04-15", "Unterrichtung", "21/801", None),
            ("q5", "e3", "2026-04-16", "Überweisung gemäß § 93 GO-BT", None, None),
            ("q6", "e3", "2026-05-20", "Mitteilung des federführenden Ausschusses", None, None),
            ("q7", "e2", "2026-04-02", "Von einer Überweisung abgesehen", None, None),
        ],
    )  # fmt: skip


def setup(conn):
    test_procedures.add_bills(conn)
    add_subjects(conn)
    decided = data.decisions(conn)
    sittings = data.sittings(conn, decided)
    return procedures.load(conn, sittings, decided), sittings


def test_slug():
    assert urls.subject(EUROPE) == "sachgebiete/europapolitik-und-europaeische-union.html"
    assert urls.subject("Außenpolitik, Entwicklung") == "sachgebiete/aussenpolitik-entwicklung.html"
    assert urls.SUBJECTS == "sachgebiete/index.html"


def test_initiator_groups():
    g = subjects.initiator_group
    assert [g("Fraktion der AfD"), g("Fraktion DIE LINKE"), g("Fraktion BÜNDNIS 90/DIE GRÜNEN")] == [
        "AfD", "Die Linke", "BÜNDNIS 90/DIE GRÜNEN"]  # fmt: skip
    assert g("Bundesregierung") == g("Bundesministerium der Finanzen") == "Bundesregierung"
    assert g("Bayern") == g("Bundesrat") == "Bundesrat und Länder"
    assert g("Präsident des Deutschen Bundestages") == "Sonstige"


def test_every_vorgang_with_a_sachgebiet_counts(conn):
    procs, _ = setup(conn)
    got = subjects.load(conn, procs)
    assert list(got)[0] == "Wirtschaft"  # largest first (3 Vorgänge)
    assert set(got) == {"Wirtschaft", "Verkehr", EUROPE, "Recht", "Wohnen", "Gesundheit"}
    recht = {v["id"]: v for v in got["Recht"]}
    assert set(recht) == {"g1", "v1"}  # g1 has a page, the Antrag v1 never reached the plenum
    assert recht["g1"]["page"] and not recht["v1"]["page"] and recht["g1"]["debates"]
    assert [v["id"] for v in got["Wirtschaft"]] == ["w3", "w2", "w1"]  # newest Drucksache first
    assert not any(v["type"] == "EU-Vorlage" for vs in got.values() for v in vs)


def test_subject_page(conn, tmp_path):
    procs, _ = setup(conn)
    got = subjects.load(conn, procs)
    docs = {r["id"]: r for r in data.drucksache_facts(conn)}
    have = {"reden/ID1.html"}
    html = subjects.subject_page("Recht", got["Recht"], docs, have)
    crumbs = '<p class="crumbs"><a href="../vorgaenge/index.html">Vorgänge</a> › <a href="index.html">Sachgebiete</a>'
    assert crumbs in html
    assert '<div class="when">Sachgebiet (DIP)</div><h1>Recht</h1>' in html
    order = [html.index(f'id="{k}"') for k in ("einbringer", "vorgaenge", "reden", "abstimmungen", "drucksachen")]
    assert order == sorted(order)
    assert 'href="../vorgaenge/g1.html"' in html  # a Vorgang with a page
    assert 'href="https://dip.bundestag.de/vorgang/v1"' in html  # one without links DIP
    assert 'id="bills"' in html and 'id="bq"' in html and 'id="bty"' in html and 'id="bst"' in html
    assert "reden/ID1.html" in html and 'id="abst-' not in html  # speeches, decisions linked to their place
    assert "lassen sich die Zahlen verschiedener Sachgebiete nicht addieren" in html
    einbringer = html.split('id="einbringer"', 1)[1].split('id="vorgaenge"', 1)[0]
    assert "<th>Einbringer</th>" in einbringer and "Bundesregierung" in einbringer and "ohne Angabe" in einbringer


def test_a_decision_on_two_vorgaenge_of_a_sachgebiet_is_listed_once(conn):
    test_procedures.add_bills(conn)
    conn.execute("UPDATE agenda_item SET drucksache_numbers = '[\"21/500\", \"21/100\"]' WHERE id = '21/88/2'")
    conn.execute("UPDATE vorgang SET subjects = '[\"Recht\"]' WHERE id IN ('v1', 'v2')")
    conn.execute(
        "INSERT INTO decision VALUES ('21/88/h2','21/88','21/88/2',2,3,'handzeichen','Antrag','21/100',"
        "'abgelehnt',NULL,'Der Antrag ist abgelehnt.','u','d','t',NULL,NULL)"
    )
    decided = data.decisions(conn)
    procs = procedures.load(conn, data.sittings(conn, decided), decided)
    vs = subjects.load(conn, procs)["Recht"]
    assert sum(1 for v in vs for d in v["decisions"] if d["id"] == "21/88/h2") == 2
    html = subjects.subject_page("Recht", vs, {}, set())
    facet = html.split('id="abstimmungen"', 1)[1].split('<section class="facet"', 1)[0]
    assert facet.count('data-kind="handzeichen" data-result="abgelehnt"') == 1
    assert subjects.summary(vs)["decisions"] == len(re.findall(r'class="dec[ "]', facet))


def test_index_names_what_has_no_sachgebiet(conn):
    procs, sittings = setup(conn)
    got = subjects.load(conn, procs)
    html = subjects.index_page(got, subjects.without_subject(conn), subjects.plenary_without_vorgang(sittings), True)
    assert 'aria-current="page">Sachgebiete</a>' in html and 'href="../vorgaenge/eu-vorlagen.html"' in html
    table = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert table.index("wirtschaft.html") < table.index("recht.html")
    ohne = html.split('id="ohne"', 1)[1]
    assert "EU-Vorlagen</a></b> (3)" in ohne and "<b>Petitionen</b> (1)" in ohne
    assert 'href="../regierung/index.html#liste"' in ohne and 'href="../sitzungen/index.html"' in ohne
    assert "0 Aktuelle Stunden, 1 Regierungsbefragung, 0 Fragestunden" in ohne


def test_eu_stand():
    def pos(*texts):
        return [{"position": t, "tenors": []} for t in texts]

    assert eu.stand([]) == eu.UNKNOWN
    assert eu.stand(pos("Unterrichtung")) == eu.NOT_REFERRED
    assert eu.stand(pos("Unterrichtung", "Von einer Überweisung abgesehen")) == eu.NOT_REFERRED
    assert eu.stand(pos("Unterrichtung", "Überweisung gemäß § 93 GO-BT")) == eu.REFERRED
    assert eu.stand(pos("Überweisung", "Mitteilung des federführenden Ausschusses")) == eu.MITTEILUNG


def test_eu_page(conn):
    procs, _ = setup(conn)
    got = {v["id"]: v for v in eu.load(conn)}
    assert [got[x]["stand"] for x in ("e1", "e2", "e3")] == [eu.REFERRED, eu.NOT_REFERRED, eu.MITTEILUNG]
    assert got["e1"]["committees"] is None and got["e1"]["docs"][0]["number"] == "21/800"
    html = eu.page(list(got.values()), procs, europe=True)
    assert 'aria-current="page">EU-Vorlagen</a>' in html
    assert f'href="../{urls.subject(EUROPE)}"' in html and "Keine davon wurde im Plenum beraten" in html
    assert "Proposal for a Regulation on ports" in html and 'href="https://x/800.pdf"' in html
    assert html.count("Ausschuss: –") == 3 and "enthält der Datenbestand noch nicht" in html
    assert 'id="eq"' in html and f'<option value="{eu.MITTEILUNG}">' in html


def test_eu_committees_from_the_referral_table(conn):
    add_subjects(conn)
    conn.execute(f"CREATE TABLE {eu.REFERRAL} (vorgang_id TEXT, committee TEXT, lead INTEGER)")
    conn.executemany(f"INSERT INTO {eu.REFERRAL} VALUES (?,?,?)",
                     [("e1", "Verkehrsausschuss", 0), ("e1", "Ausschuss für Wirtschaft", 1)])  # fmt: skip
    got = {v["id"]: v for v in eu.load(conn)}
    assert got["e1"]["committees"] == ["Ausschuss für Wirtschaft", "Verkehrsausschuss"]  # the lead one first
    assert got["e2"]["committees"] == []
    assert "Ausschuss: Ausschuss für Wirtschaft, Verkehrsausschuss" in eu.page(list(got.values()), [], europe=False)


def test_vorgang_page_links_its_sachgebiete(conn):
    procs, _ = setup(conn)
    g1 = next(b for b in procs if b["id"] == "g1")
    html = procedures.procedure_page(g1, set(), {}, {"decisions": 0, "on_one": 0, "several": 0})
    assert '<span class="k">Sachgebiete</span> <a href="../sachgebiete/recht.html">Recht</a>' in html
    assert 'aria-current="page">Vorgänge</a>' in procedures.index_page(procs)


def test_search_finds_sachgebiete(conn):
    procs, _ = setup(conn)
    got = subjects.load(conn, procs)
    index = search.entities([], [], False, [], {"wahlkreise": {}}, None, {}, [], got)
    hits = {label: href for t, label, _, href, _ in index["items"] if index["types"][t] == "Sachgebiet"}
    assert hits["Wirtschaft"] == "sachgebiete/wirtschaft.html" and hits[EUROPE] == urls.subject(EUROPE)
