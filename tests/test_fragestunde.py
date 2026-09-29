from conftest import LONG, speech

from cards import data, debate, questions, speeches


def add_fragestunde(conn):
    """A store ingested after speech.kind existed: one Fragestunde with a question and a long answer."""
    conn.execute("ALTER TABLE speech ADD COLUMN kind TEXT NOT NULL DEFAULT 'rede'")
    conn.execute("INSERT INTO agenda_item VALUES ('21/88/3','21/88',3,'Tagesordnungspunkt 3','Fragestunde','[]',"
                 "'https://x/21088.xml','BT-PlPr. 21/88','2026-09-27')")  # fmt: skip
    conn.executemany(
        "INSERT INTO speech VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'fragestunde')",
        [
            speech("21/88/3/f1", 13, "1", "Anna Adler (SPD)", "Wann kommt das Gesetz?", "21/88/3", fraction="SPD"),
            speech("21/88/3/f2", 14, "9", "Stefanie Hubig, Bundesministerin", LONG, "21/88/3", role="Bundesministerin"),
        ],
    )


def test_fragestunde_on_the_card_but_not_a_rede(conn):
    add_fragestunde(conn)
    cards = {c["id"]: c for c in data.cards(conn)[0]}
    assert [f["id"] for f in cards["1"]["fragestunde"]] == ["21/88/3/f1"]
    assert [f["role"] for f in cards["9"]["fragestunde"]] == ["Bundesministerin"]
    assert [r["id"] for r in cards["9"]["reden"]] == ["ID2"]  # the long answer is no Rede


def test_fragestunde_left_out_of_shares_and_sitting_counts(conn):
    add_fragestunde(conn)
    assert not any(s["id"].startswith("21/88/3/") for s in debate._speeches(conn))
    (sitting,) = data.sittings(conn, decided=[])
    item = next(i for i in sitting["items"] if i["id"] == "21/88/3")
    assert (item["speeches"], item["fragestunde"]) == ([], 2)
    assert questions.fragestunden(conn) == (1, 2)


def test_fragestunde_has_speech_pages(conn):
    add_fragestunde(conn)
    kinds = {r["id"]: r["kind"] for r in speeches.load(conn)}
    assert kinds["21/88/3/f2"] == "fragestunde"
    assert kinds["ID1"] == "rede"
