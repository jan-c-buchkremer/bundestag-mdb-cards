import sqlite3
from pathlib import Path

import pytest

LONG = "Wohnen ist die soziale Frage unserer Zeit. " * 15  # 105 words
PLPR = "BT-PlPr. 21/88"
STAMM = ("https://www.bundestag.de/resource/blob/472878/MdB-Stammdaten.zip", "MDB_STAMMDATEN 2026-04-29", "2026-09-27")


def person(pid, first, last, party, is_mdb=1, title=None, role=None, gender="weiblich"):
    return (pid, first, last, None, title, "1970-01-02", "Rostock", gender, party, is_mdb, role, None, None, None,
            *STAMM)  # fmt: skip


def mandate(pid, wp, kind, number=None, name=None, state="BY", to=None):
    return (f"{pid}/{wp}", pid, wp, "2025-03-25" if wp == 21 else f"{1930 + 4 * wp}-10-01", to, kind, number, name,
            state, *STAMM)  # fmt: skip


def membership(pid, n, kind, name, role=None, frm="2025-03-25", to=None):
    return (f"{pid}/21/{n}", pid, 21, kind, name, role, frm, to, *STAMM)


def speech(sid, position, pid, name, text, agenda="21/88/2", role=None, fraction=None):
    return (sid, "21/88", agenda, position, pid, name, role, fraction, text, "https://x/21088.xml", PLPR, "2026-09-27")


def vote_row(n, pid, last, fraction, vote, vote_id="21/88/1"):
    return (f"{vote_id}/{n}", vote_id, pid, last, "X", fraction, vote)


def store() -> sqlite3.Connection:
    """The fixture store, in memory: the schema of tests/schema.sql and a few rows of every table."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript((Path(__file__).parent / "schema.sql").read_text())
    c.executemany(
        "INSERT INTO person VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            person("1", "Anna", "Adler", "SPD"),
            person("2", "Bernd", "Berg", "CSU", title="Dr.", gender="männlich"),
            person("3", "Clara", "Cohn", "DIE LINKE."),
            person("4", "Dora", "Dahl", "CDU"),  # moved up after the Stammdaten snapshot: WP 20 mandate only
            person("9", "Stefanie", "Hubig", None, is_mdb=0, role="Bundesministerin der Justiz"),
            person("5", "Xaver", "Xaver", "SPD"),
            person("6", "Yvonne", "Yvonne", "SPD"),
            person("7", "Zora", "Zora", "CDU"),
            person("10", "Lena", "Lose", "GRÜNE"),  # a list mandate whose Land the Stammdaten do not name
        ],
    )
    c.executemany(
        "INSERT INTO mandate VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            mandate("1", 19, "Direktwahl", 14, "Rostock", "MV"),
            mandate("1", 20, "Direktwahl", 14, "Rostock", "MV"),
            mandate("1", 21, "Direktwahl", 14, "Rostock", "MV"),
            mandate("2", 21, "Landesliste", 242, "Fürth"),
            mandate("3", 21, "Landesliste", None, None, "BE"),
            mandate("4", 20, "Landesliste", None, None, "NW"),
            mandate("5", 21, "Landesliste", None, None, "NW"),
            mandate("6", 21, "Landesliste", None, None, "NW"),
            mandate("7", 21, "Landesliste", None, None, "NW"),
            mandate("10", 21, "Landesliste", None, None, None),
        ],
    )
    c.executemany(
        "INSERT INTO membership VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            membership("1", 1, "fraction", "SPD"),
            membership("1", 2, "committee", "Ausschuss für Gesundheit", "Obfrau"),
            membership("1", 3, "committee", "Haushaltsausschuss", "Stellvertretendes Mitglied", to="2025-12-31"),
            membership("2", 1, "fraction", "CDU/CSU", "Parlamentarischer Geschäftsführer"),
            membership("2", 2, "other", "BMI", "Parlamentarischer Staatssekretär", "2025-05-06"),
            membership("3", 1, "fraction", "Die Linke"),
            membership("3", 2, "other", "Präsidium", "Vizepräsidentin des Deutschen Bundestages"),
            membership("3", 3, "other", "Ältestenrat"),
            membership("10", 1, "fraction", "BÜNDNIS 90/DIE GRÜNEN"),
        ],
    )
    c.execute("INSERT INTO sitting VALUES ('21/88',21,88,'2026-07-08',NULL,NULL,'https://x/21088.xml',"
              "'https://x/21088.pdf','https://x/21088.xml','BT-PlPr. 21/88','2026-09-27')")  # fmt: skip
    c.executemany(
        "INSERT INTO agenda_item VALUES (?,'21/88',?,?,?,'[]','https://x/21088.xml',?,'2026-09-27',0)",
        [
            ("21/88/1", 1, "Tagesordnungspunkt 1", "Befragung der Bundesregierung", PLPR),
            ("21/88/2", 2, "Tagesordnungspunkt 2", "Beratung des Antrags der Fraktion X | Mietpreisbremse", PLPR),
        ],
    )
    c.executemany(
        "INSERT INTO speech VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'rede',NULL)",
        [
            # Regierungsbefragung: every question and answer is its own rede
            speech("ID10", 1, "9", "Stefanie Hubig, Bundesministerin", LONG, "21/88/1", role="Bundesministerin"),
            speech("ID11", 2, "1", "Anna Adler (SPD)", "Frau Ministerin, wann?", "21/88/1", fraction="SPD"),
            speech("ID12", 3, "9", "Stefanie Hubig, Bundesministerin", "Bald.", "21/88/1", role="Bundesministerin"),
            # Berg's rede, interrupted by Cohn (one question over two parts) and by Adler (Kurzintervention)
            speech("ID1", 4, "2", "Dr. Bernd Berg (CDU/CSU)", LONG, fraction="CDU/CSU"),
            speech("ID1-2", 5, "3", "Clara Cohn (Die Linke)", "Gestatten Sie eine Frage?", fraction="Die Linke"),
            speech("ID1-3", 6, "2", "Dr. Bernd Berg (CDU/CSU)", "Bitte.", fraction="CDU/CSU"),
            speech("ID1-4", 7, "3", "Clara Cohn (Die Linke)", "Warum nicht früher?", fraction="Die Linke"),
            speech("ID1-5", 8, "2", "Dr. Bernd Berg (CDU/CSU)", LONG, fraction="CDU/CSU"),
            speech("ID1-6", 9, "1", "Anna Adler (SPD)", "Das stimmt so nicht.", fraction="SPD"),
            speech("ID1-7", 10, "2", "Dr. Bernd Berg (CDU/CSU)", "Doch.", fraction="CDU/CSU"),
            speech("ID2", 11, "9", "Stefanie Hubig, Bundesministerin", LONG, role="Bundesministerin"),
            speech(
                "ID3",
                12,
                "3",
                "Clara Cohn (Die Linke)",
                "Ich schwöre es, so wahr mir Gott helfe.",
                fraction="Die Linke",
            ),
        ],
    )
    c.executemany(
        "INSERT INTO speech_paragraph VALUES (?,?,?,?,?)",
        [
            ("ID1/1", "ID1", 1, "text", LONG),
            ("ID1/2", "ID1", 2, "comment", "(Beifall bei der CDU/CSU)"),
            ("ID1/3", "ID1", 3, "comment", "(Zuruf von der AfD: Falsch!)"),
            ("ID1/4", "ID1", 4, "chair", "Gestatten Sie eine Zwischenfrage?"),
            ("ID1-5/1", "ID1-5", 1, "text", LONG),
            ("ID1-5/2", "ID1-5", 2, "comment", "(Beifall bei der CDU/CSU und der SPD)"),
            ("ID1-5/3", "ID1-5", 3, "chair", "Zu einer Kurzintervention hat Frau Adler das Wort."),
        ],
    )
    c.executemany(
        "INSERT INTO roll_call_vote VALUES (?,'21/88',?,'2026-07-08',?,NULL,NULL,NULL,?,?,?,0,?,'https://x/1.xlsx',"
        "'https://x/1.pdf','https://x/1.xlsx',?,'2026-09-27',?)",
        [
            ("21/88/1", 1, "Mietpreisbremse", 4, 3, 1, 0, "NA 21/88/1", "21/88/2"),
            ("21/88/2", 2, "Haushalt", 2, 2, 0, 1, "NA 21/88/2", None),
        ],
    )
    c.executemany(
        "INSERT INTO individual_vote VALUES (?,?,?,?,?,?,?)",
        [
            vote_row(1, "1", "Adler", "SPD", "yes"),
            vote_row(2, "5", "Xaver", "SPD", "yes"),
            vote_row(3, "6", "Yvonne", "SPD", "no"),
            vote_row(4, "2", "Berg", "CDU/CSU", "no"),
            vote_row(5, "4", "Dahl", "CDU/CSU", "yes"),
            vote_row(6, "7", "Zora", "CDU/CSU", "yes"),
            vote_row(7, "3", "Cohn", "Die Linke", "abstain"),
            vote_row(8, None, "Unbekannt", "CDU/CSU", "yes"),
            # a tie: the SPD has no line on the second vote
            vote_row(1, "1", "Adler", "SPD", "yes", "21/88/2"),
            vote_row(2, "5", "Xaver", "SPD", "no", "21/88/2"),
            vote_row(3, "6", "Yvonne", "SPD", "absent", "21/88/2"),
        ],
    )
    dip = ("https://search.dip.bundestag.de/api/v1/drucksache/1", "BT-Drs. 21/1", "2026-09-27")
    c.executemany(
        "INSERT INTO drucksache VALUES (?,?,21,?,?,?,?,'BT',?,?,?,?,?)",
        [
            ("d1", "21/100", "Antrag", "Mieten", "2026-07-06", "https://x/100.pdf", '["Fraktion SPD"]', 3, *dip),
            ("d2", "21/200", "Kleine Anfrage", "Pflege", "2026-07-07", "https://x/2.pdf", '["SPD"]', 120, *dip),
            ("d3", "21/300", "Beschlussempfehlung und Bericht", "Pflege", "2026-07-08", None, "[]", 0, *dip),
            ("d4", "21/400", "Antwort", "Antwort auf 21/200", "2026-07-09", None, '["Bundesregierung"]', 0, *dip),
        ],
    )  # fmt: skip
    c.executemany(
        "INSERT INTO drucksache_author VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("d1/a", "d1", "a", "1", "Anna Adler, MdB, SPD", "Antrag", *dip),
            ("d2/a", "d2", "a", "1", "Anna Adler, MdB, SPD", "Kleine Anfrage", *dip),
            ("d3/a", "d3", "a", "1", "Anna Adler, MdB, SPD", "Berichterstattung", *dip),
            ("d4/b", "d4", "b", "2", "Bernd Berg", "Antwort", *dip),
            ("d1/z", "d1", "z", None, "Jemand Unbekannt", "Antrag", *dip),
        ],
    )
    c.executemany(
        "INSERT INTO vorgang (id, wahlperiode, type, title, status, subjects, initiators, source_url, "
        "source_document_id, "
        "retrieved_at) VALUES (?,21,'Antrag',?,NULL,?,'[]',?,?,?)",
        [("v1", "Mieten", '["Wohnen", "Recht"]', *dip), ("v2", "Pflege", '["Gesundheit"]', *dip)],
    )
    c.executemany("INSERT INTO vorgang_drucksache VALUES (?,?)", [("v1", "d1"), ("v2", "d1"), ("v2", "d2")])
    kerg = ("https://x/kerg2.csv", "Bundeswahlleiterin, BTW 2025 Ergebnisse nach Wahlkreisen (Stand 2025-03-14)", "t")
    elected = ("https://x/gewaehlte.zip", "Bundeswahlleiterin, BTW 2025 Gewählte (Stand 2025-03-12)", "t")
    c.executemany(
        "INSERT INTO constituency VALUES (?,'btw25',?,?,?,?,?,?,?,?,?)",
        [
            ("btw25/14", 14, "Rostock", "MV", "SPD", 200000, 160000, *kerg),
            ("btw25/242", 242, "Fürth", "BY", "CSU", 180000, 150000, *kerg),
            ("btw25/58", 58, "Oberhavel", "BB", None, 190000, 150000, *kerg),  # the winner got no seat
        ],
    )
    c.executemany(
        "INSERT INTO constituency_result VALUES (?,'btw25',?,'party',?,?,?,?,?,?,?)",
        [
            ("btw25/14/1/1", 14, "SPD", 1, 60000, 38.2, *kerg),
            ("btw25/14/2/1", 14, "AfD", 1, 40000, 25.0, *kerg),
            ("btw25/242/1/1", 242, "CSU", 1, 45000, 30.5, *kerg),
            ("btw25/242/2/1", 242, "SPD", 1, 30000, 20.0, *kerg),
            ("btw25/58/1/1", 58, "AfD", 1, 50000, 33.3, *kerg),
            ("btw25/58/2/1", 58, "SPD", 1, 40000, 26.7, *kerg),
        ],
    )
    c.executemany(
        "INSERT INTO election_candidacy VALUES (?,'btw25',?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("btw25/1", "1", "Adler", "Anna", 1970, "SPD", "constituency", 14, 38.2, "MV", 2, None, *elected),
            ("btw25/2", "2", "Berg", "Bernd Maria", 1970, "CSU", "list", 242, None, "BY", 3, None, *elected),
            ("btw25/3", None, "Unbekannt", "Uwe", 1960, "AfD", "list", None, None, "BB", 1, None, *elected),
        ],
    )
    c.executemany(
        "INSERT INTO interjection VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("ID1/2/1/1", "ID1", 2, 1, "beifall", "fraction", "CDU/CSU", None, None, None, None, None),
            ("ID1/2/1/2", "ID1", 2, 1, "beifall", "members", "SPD", None, None, None, None, None),
            ("ID1/2/1/3", "ID1", 2, 1, "beifall", "person", "CDU/CSU", "2", "Dr. Bernd Berg", None, None, None),  # own
            ("ID1/3/1/1", "ID1", 3, 1, "zuruf", "person", "Die Linke", "3", "Clara Cohn", "Falsch!", None, None),
            ("ID1/3/2/1", "ID1", 3, 2, "lachen", "fraction", "AfD", None, None, None, None, None),
            ("ID1/3/3/1", "ID1", 3, 3, "beifall", "house", None, None, None, None, None, None),
            ("ID1-5/2/1/1", "ID1-5", 2, 1, "zuruf", "fraction", "AfD", None, None, "Unsinn!", None, None),
            ("ID2/1/1/1", "ID2", 1, 1, "gegenruf", "person", "SPD", "1", "Anna Adler", "Doch!", "3", "Clara Cohn"),
        ],
    )
    aw = "https://www.abgeordnetenwatch.de"
    c.execute(
        "INSERT INTO aw_profile VALUES (79001, '1', ?, 107, 95, ?, 'aw politician 79001', '2026-09-28T03:00:00+00:00')",
        (f"{aw}/profile/anna-adler", f"{aw}/api/v2/politicians/79001"),
    )
    c.execute(
        "INSERT INTO side_job VALUES (20001, 21, '1', 68001, 'Mitglied des Beirates, ehrenamtlich', NULL, "
        "'Funktionen in Vereinen, Verbänden und Stiftungen', 1, '1.000 € bis 3.500 €', NULL, 'jährlich', NULL, "
        "601, 'Musterverein e.V.', 'Berlin', '[]', '2026-01-10', '2026-09-01', ?, 'aw sidejob 20001', "
        "'2026-09-28T03:00:00+00:00')",
        (f"{aw}/api/v2/sidejobs/20001",),
    )
    wd = ("https://query.wikidata.org/sparql", "Wikidata P39 2026-09-28", "2026-09-28")
    c.executemany(
        "INSERT INTO government_role VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'wikidata')",
        [
            ("g1", "9", "Q1", "Stefanie Hubig", "Bundesministerin der Justiz", "BMJV", "minister", "2025-05-06",
             None, *wd),
            ("g2", "2", "Q2", "Bernd Berg", "Parlamentarischer Staatssekretär", "BMI", "parl_sts", "2025-05-06",
             None, *wd),
            ("g3", "1", "Q3", "Anna Adler", "Parlamentarische Staatssekretärin", "BMG", "parl_sts", "2025-05-06",
             "2025-12-31", *wd),  # left office
            ("g4", None, "Q77", "Rita Roster", "Staatsministerin", "Kanzleramt", "staatsminister", "2025-05-06",
             None, *wd),  # no person row matched
            ("g5", None, "Q78", "Bea Beamtin", "Staatssekretärin", "BMF", "beamteter_sts", "2025-05-06", None, *wd),
        ],
    )  # fmt: skip
    c.execute("INSERT INTO person VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              ("Q79", "Bruno", "Böhm", None, None, "1978-06-02", None, None, "SPD", 0, "beamteter Staatssekretär",
               None, None, "Q79", "https://www.wikidata.org/wiki/Q79", "Wikidata Q79", "2026-09-28"))  # fmt: skip
    c.executemany(
        "INSERT INTO government_role VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'wikidata')",
        [
            ("g6", "Q79", "Q79", "Bruno Böhm", "beamteter Staatssekretär", "Bundesministerium der Finanzen",
             "beamteter_sts", "2025-05-06", None, *wd),  # never spoke, no mandate: a card only for the office
            ("g7", "9", "Q1", "Stefanie Hubig", "Bundesminister der Justiz", "BMJV", "minister", "2025-05-06",
             None, *wd),  # the same office again in Wikidata's masculine label
        ],
    )  # fmt: skip
    c.executemany(
        "INSERT INTO person_photo VALUES (?,?,?,?,?,?,?,?)",
        [
            ("1", "https://x/adler.jpg", "Jemand/SPD-Fraktion", "https://x/adler", "bundestag/fotos/adler.jpg",
             "https://x/bio", "bundestag.de Biografie Adler, Anna", "2026-09-28"),
            ("9", "https://x/hubig.png", "Sandro Halank, CC BY-SA 4.0", None, "wikidata/fotos/hubig.png",
             "https://commons.wikimedia.org/wiki/File:Hubig.png", "Wikimedia Commons File:Hubig.png", "2026-09-28"),
        ],
    )  # fmt: skip
    c.execute(
        "INSERT INTO decision VALUES ('21/88/1', '21/88', '21/88/2', 1, 1, 'namentlich', 'Antrag', NULL, 'angenommen',"
        " '21/88/1', 'Damit ist der Antrag angenommen.', 'https://x/21088.xml', 'BT-PlPr. 21/88', '2026-09-27',"
        " NULL, NULL)"
    )
    return c


@pytest.fixture
def conn():
    return store()


@pytest.fixture
def conn_without_round2(conn):
    """A store from before the government roster, photos and decisions."""
    conn.executescript("DROP TABLE government_role; DROP TABLE person_photo; DROP TABLE decision;")
    return conn
