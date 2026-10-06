"""Fragen as text (question_pages.py): the subpages and a page per question from the foundation's question tables."""

import json

from research import question_pages, urls

DIP = ("https://x", "DIP", "2026-09-27")
PLPR = ("https://x/21088.xml", "BT-PlPr. 21/88", "2026-09-27")


def add_questions(c):
    """A Kleine Anfrage of Die Linke (21/700) answered in 21/750 with two questions and a table; one not read; a
    Mündliche Frage answered in writing; the Befragung of sitting 88 with its three turns."""
    c.executemany(
        "INSERT INTO drucksache VALUES (?,?,21,?,?,?,?,'BT',?,0,?,?,?,NULL)",
        [
            ("d700", "21/700", "Kleine Anfrage", "Häfen", "2026-05-04", None, '["Fraktion Die Linke"]', *DIP),
            ("d750", "21/750", "Antwort", "Antwort zu 21/700", "2026-05-20", "https://x/750.pdf", "[]", *DIP),
            ("d701", "21/701", "Kleine Anfrage", "Brücken", "2026-05-05", None, '["Fraktion der AfD"]', *DIP),
            ("d751", "21/751", "Antwort", "Antwort zu 21/701", "2026-05-21", None, "[]", *DIP),
            ("d900", "21/900", "Fragen", "Fragen für die Fragestunde", "2026-07-03", None, "[]", *DIP),
        ],
    )  # fmt: skip
    c.executemany(
        "INSERT INTO vorgang (id, wahlperiode, type, title, status, subjects, initiators, source_url, "
        "source_document_id, retrieved_at) VALUES (?,21,?,?,NULL,'[]','[]',?,?,?)",
        [("k1", "Kleine Anfrage", "Häfen in Deutschland", *DIP), ("k2", "Kleine Anfrage", "Brücken", *DIP),
         ("m1", "Mündliche Frage", "Zugausfälle", *DIP)],
    )  # fmt: skip
    c.executemany("INSERT INTO vorgang_drucksache VALUES (?,?)",
                  [("k1", "d700"), ("k1", "d750"), ("k2", "d701"), ("k2", "d751")])  # fmt: skip
    rows = [
        ("21/750/v/vf", "k1", "21/750", 1, "vorbemerkung_fragesteller", None, "Häfen sind wichtig.", None, None),
        ("21/750/1/frage", "k1", "21/750", 2, "frage", "1", "Wie viele Häfen gibt es?", None, None),
        ("21/750/1/antwort", "k1", "21/750", 3, "antwort", "1", "Es gibt viele.\n\nSiehe Tabelle.",
         "Bundesministerium für Verkehr", "2026-05-20"),
        ("21/750/2/frage", "k1", "21/750", 4, "frage", "2", "Welche sind die größten?", None, None),
        ("21/750/2/antwort", "k1", "21/750", 5, "antwort", "2", "Hamburg.", "Bundesministerium für Verkehr",
         "2026-05-20"),
        ("21/900/4/frage", "m1", "21/900", 1, "frage", "4", "Warum fallen Züge aus?", "Anna Adler", None),
        ("21/900/4/antwort", "m1", "21/900", 2, "antwort", "4", "Wegen Bauarbeiten.",
         "Parl. Staatssekretärs Bernd Berg", "2026-07-08"),
    ]  # fmt: skip
    c.executemany(
        "INSERT INTO question_text (id, vorgang_id, drucksache_number, position, part, number, text, name, "
        "answer_date, source_url, source_document_id, retrieved_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(*r, *DIP) for r in rows],
    )
    c.execute("UPDATE question_text SET answerer_person_id = '2' WHERE id = '21/900/4/antwort'")
    cells = {"caption": "Häfen", "head": [["Hafen", "Umschlag"]], "body": [["Hamburg", "100"]], "foot": []}
    c.executemany(
        "INSERT INTO question_table VALUES (?,?,?,?,?)",
        [("21/750/1/antwort/1", "21/750/1/antwort", 1, 1, json.dumps(cells)),
         ("21/750/2/antwort/1", "21/750/2/antwort", 1, 0, json.dumps({"extracted": False, "page": 7}))],
    )  # fmt: skip
    c.executemany("INSERT INTO question_parse VALUES (?,?,?,?,?)",
                  [("k1", "complete", 2, 2, "BT-Drs. 21/750"), ("k2", "failed", 0, 0, None),
                   ("m1", "complete", 1, 1, "BT-PlPr. 21/88")])  # fmt: skip
    c.execute(
        "INSERT INTO question_activity (id, vorgang_id, question_type, activity_type, dip_person_id, person_id, "
        "name, ressort, document_kind, document_number, source_url, source_document_id, retrieved_at) "
        "VALUES ('a1','m1','Mündliche Frage','Frage','p1','1','Anna Adler','Bundesministerium für Verkehr',"
        "'Drucksache','21/900',?,?,?)",
        DIP,
    )
    c.executemany("INSERT INTO question_turn VALUES (?,?,?,NULL)",
                  [("ID10", "einleitung", None), ("ID11", "frage", "ID11"), ("ID12", "antwort", "ID11")])  # fmt: skip


def test_anfrage_page_pairs_each_question_with_its_answer(conn):
    add_questions(conn)
    k1, k2 = sorted((a for a in question_pages.anfragen(conn)), key=lambda a: a["id"])
    assert k1["fractions"] == ["Die Linke"] and k1["answer"]["number"] == "21/750" and k1["status"] == "complete"
    html = question_pages.anfrage_page(k1, {"1"})
    q1 = html.split('id="frage-1"', 1)[1].split("</section>", 1)[0]
    assert "Wie viele Häfen gibt es?" in q1 and "Zu Frage 1" in q1 and "<caption>Häfen</caption>" in q1
    assert q1.index("Es gibt viele.") < q1.index("<table") < q1.index("Siehe Tabelle.")  # after its paragraph
    assert "Vorbemerkung der Fragesteller" in html and "Hamburg." in html
    assert "auf Seite 7 ließ sich nicht lesen" in html  # a table the foundation did not read names its page
    assert '<div data-pagefind-ignore><div class="k">Zu Frage 1' in html  # answers are not in the search index
    # an answer that was not read is never shown as unanswered
    unread = question_pages.anfrage_page(k2, set())
    assert "Antwort nicht lesbar" in unread and "noch nicht geantwortet" not in unread


def test_muendliche_frage_answered_in_writing_stays_muendlich(conn):
    add_questions(conn)
    (m1,) = question_pages.einzelfragen(conn)
    assert m1["asker"]["person"] == "1" and m1["date"] == "2026-07-03" and not m1["turns"]
    html = question_pages.frage_page(m1, {"1", "2"}, {"1": {"name": "Anna Adler", "fraction": "SPD"}})
    assert "Warum fallen Züge aus?" in html and "Wegen Bauarbeiten." in html
    assert "zählt weiter als mündliche Frage" in html and 'href="../../2.html"' in html
    index = question_pages.einzelfragen_page([m1], {"1": {"name": "Anna Adler", "fraction": "SPD"}}, [])
    assert 'data-weg="muendlich"' in index and "mündlich, schriftlich beantwortet" in index


def test_befragung_groups_turns_by_question(conn):
    add_questions(conn)
    (b,) = question_pages.befragungen(conn)
    assert [t["id"] for t in b["intro"]] == ["ID10"] and [[t["id"] for t in th] for th in b["threads"]] == [
        ["ID11", "ID12"]
    ]
    assert b["questioned"][0]["person"] == "9"
    html = question_pages.befragung_page(b, {"1", "9"})
    assert "1. Frage von Anna Adler" in html and f'href="../../{urls.speech("ID12")}"' in html
    assert question_pages.befragungen_page([b], set()).count("<li>") == 1


def test_write_forwards_the_muendliche_frage_vorgang_page(conn, tmp_path):
    add_questions(conn)
    (tmp_path / "vorgaenge").mkdir()
    got = question_pages.write(conn, tmp_path, {"1"}, ["2026-07-08"])
    assert got == {"anfragen": 2, "einzelfragen": 1, "befragungen": 1}
    assert (tmp_path / urls.anfrage("k1")).exists() and (tmp_path / urls.befragung("21/88")).exists()
    stub = (tmp_path / urls.vorgang("m1")).read_text()
    assert 'http-equiv="refresh"' in stub and "regierung/fragen/m1.html" in stub


def test_nothing_without_the_question_tables(conn, tmp_path):
    conn.execute("DROP TABLE question_turn")
    assert question_pages.write(conn, tmp_path, set(), []) == {}


def test_answer_names_read_as_german():
    assert question_pages.answer_by("Bundesministeriums des Innern") == "des Bundesministeriums des Innern"
    assert question_pages.answer_by("Parl. Staatssekretärin Anna Adler") == "der Parl. Staatssekretärin Anna Adler"
    assert (
        question_pages.answer_by("des Parlamentarischen Staatssekretärs X") == "des Parlamentarischen Staatssekretärs X"
    )
    assert question_pages.ministry_name("Auswärtigen Amts") == "Auswärtiges Amt"
    assert question_pages.ministry_name("Bundesministeriums für Verkehr") == "Bundesministerium für Verkehr"
