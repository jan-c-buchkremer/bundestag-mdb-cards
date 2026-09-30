from cards import build, data, subtops

SRC = "'https://x/21088.xml', 'BT-PlPr. 21/88', '2026-09-27'"


def add_block(conn):
    """TOP 5, a block without debate: 5a a law (two votes), 5b a petition list (one vote); one speech during it."""
    conn.execute(
        "INSERT INTO agenda_item VALUES ('21/88/5','21/88',5,'Tagesordnungspunkt 5',"
        "'Zweite Beratung des Entwurfs eines Gesetzes zur Änderung des Seelotsgesetzes | Beratung der "
        "Beschlussempfehlung des Petitionsausschusses | Sammelübersicht 304 zu Petitionen','[]',"
        f"{SRC},1)"
    )
    conn.executemany(
        f"INSERT INTO agenda_sub_item VALUES (?,'21/88/5',?,?,?,?,1,2,{SRC},1)",
        [
            ("21/88/5/5a", "5a", 1, "Zweite Beratung des von der Bundesregierung eingebrachten Entwurfs eines "
             "Gesetzes zur Änderung des Seelotsgesetzes | Beschlussempfehlung und Bericht des Verkehrsausschusses",
             '["21/6498"]'),
            ("21/88/5/5b", "5b", 2, "Beratung der Beschlussempfehlung des Petitionsausschusses | "
             "Sammelübersicht 304 zu Petitionen", '["21/7954"]'),
        ],
    )  # fmt: skip
    for i, (sub, kind, result) in enumerate([("5a", "handzeichen", "angenommen"), ("5a", "handzeichen", "angenommen"),
                                             ("5b", "handzeichen", "abgelehnt")], 1):  # fmt: skip
        conn.execute(
            "INSERT INTO decision VALUES (?, '21/88', '21/88/5', ?, ?, ?, 'Antrag', NULL, ?, NULL, 'Text.', "
            f"{SRC}, ?, NULL)",
            (f"21/88/h{i + 4}", i, 1, kind, result, f"21/88/5/{sub}"),
        )
    conn.executemany("INSERT INTO decision_fraction VALUES (?,?,?)",
                     [("21/88/h5", "SPD", "yes"), ("21/88/h5", "AfD", "no")])  # fmt: skip
    conn.execute(
        "INSERT INTO speech (id, sitting_id, agenda_item_id, position, person_id, speaker_name, text, source_url, "
        "source_document_id, retrieved_at, kind) VALUES ('ID50', '21/88', '21/88/5', 50, '3', 'Clara Cohn', 'Kurz.', "
        f"{SRC}, 'rede')"
    )


def page(conn, tmp_path, name="21-88"):
    cards, meta = data.cards(conn)
    decided = data.decisions(conn)
    build.write_site(cards, meta, tmp_path, decisions=decided, sittings=data.sittings(conn, decided))
    return (tmp_path / "sitzungen" / f"{name}.html").read_text()


def item(conn, item_id="21/88/5"):
    return next(i for s in data.sittings(conn) for i in s["items"] if i["id"] == item_id)


def test_sub_title_is_short():
    t = "Beratung des Antrags des BMF | Vorzeitige Teilrückzahlung Portugals | Antrag auf Einholung eines Beschlusses"
    assert subtops.sub_title(t, "41c") == "Vorzeitige Teilrückzahlung Portugals"
    t = "Zweite Beratung des von der Bundesregierung eingebrachten Entwurfs eines Dritten Gesetzes zur Änderung des X"
    assert (
        subtops.sub_title(t + " | Beschlussempfehlung und Bericht", "41b")
        == "Entwurf eines Dritten Gesetzes zur Änderung des X"
    )
    t = "Beratung der Beschlussempfehlung | – zu dem Antrag der AfD | Erstes | – zu dem Antrag der AfD | Zweites"
    assert subtops.sub_title(t, "41d") == "Erstes · Zweites"
    assert subtops.sub_title(None, "41z") == "41z"


def test_block_without_debate_lists_sub_tops(conn, tmp_path):
    add_block(conn)
    i = item(conn)
    assert i["title"] == "Abstimmungen ohne Aussprache" and i["no_debate"]
    assert [s["label"] for s in i["sub_items"]] == ["5a", "5b"]
    assert [len(s["decisions"]) for s in i["sub_items"]] == [2, 1]
    assert len(i["decisions"]) == 3 and not i["block_decisions"]  # the item keeps all of them for other pages
    html = page(conn, tmp_path)
    assert 'id="top-5"' in html and 'id="top-5-5a"' in html and 'id="top-5-5b"' in html
    assert "TOP 5</span> Abstimmungen ohne Aussprache" in html
    assert "Entwurf eines Gesetzes zur Änderung des Seelotsgesetzes</h4>" in html
    assert "keine Aussprache vorgesehen" in html and "Plenarprotokoll BT-PlPr. 21/88" in html
    assert "dafür: <b>" in html  # the fractions' positions of 5a's decision
    vote = (tmp_path / "abstimmungen" / "21-88-h5.html").read_text()
    assert 'href="../sitzungen/21-88.html#top-5-5a"' in vote and "ohne Aussprache abgestimmt" in vote


def test_speech_without_sub_item_stays_with_the_block_with_a_note(conn, tmp_path):
    add_block(conn)
    i = item(conn)
    assert [sp["id"] for sp in i["block_speeches"]] == ["ID50"]
    assert "Wortmeldung während des Abstimmungsblocks" in page(conn, tmp_path)


def test_speech_with_sub_item_goes_under_its_sub_top(conn, tmp_path):
    add_block(conn)
    conn.execute("UPDATE speech SET sub_item_id = '21/88/5/5b' WHERE id = 'ID50'")
    i = item(conn)
    assert [sp["id"] for sp in i["sub_items"][1]["speeches"]] == ["ID50"] and not i["block_speeches"]
    html = page(conn, tmp_path)
    assert "Wortmeldung während des Abstimmungsblocks" not in html
    assert html.index("reden/ID50.html") > html.index('id="top-5-5b"')


def test_no_debate_item_without_sub_items_says_so(conn, tmp_path):
    add_block(conn)
    conn.executescript("DELETE FROM decision WHERE agenda_item_id = '21/88/5'; DELETE FROM agenda_sub_item;")
    i = item(conn)
    assert "sub_items" not in i and i["no_debate"]
    assert "keine Aussprache vorgesehen" in page(conn, tmp_path)


def test_store_without_the_new_structure(conn, tmp_path):
    conn.execute("ALTER TABLE agenda_item DROP COLUMN no_debate")
    conn.execute("ALTER TABLE decision DROP COLUMN sub_item_id")
    conn.executescript("DROP TABLE agenda_item_vorlage; DROP TABLE agenda_sub_item;")
    i = item(conn, "21/88/2")
    assert "sub_items" not in i and not i["no_debate"] and i["decisions"]
    html = page(conn, tmp_path)
    assert 'id="top-2"' in html and "subtop" not in html
