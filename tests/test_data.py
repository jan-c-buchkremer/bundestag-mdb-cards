from collections import Counter

from cards import data


def by_id(conn):
    cards, meta = data.cards(conn)
    return {c["id"]: c for c in cards}, meta


def test_rede_belongs_to_first_speaker_and_counts_interruptions(conn):
    cards, _ = by_id(conn)
    (rede,) = cards["2"]["reden"]
    assert rede["id"] == "ID1"
    assert rede["title"] == "Mietpreisbremse"
    assert rede["words"] == 105 + 1 + 105 + 1  # own parts only
    assert rede["applause"] == 2
    assert [(i["person"], i["kind"]) for i in rede["interruptions"]] == [
        ("3", "zwischenfrage"),  # two parts, one question: "Bitte." in between is not a second one
        ("1", "kurzintervention"),
    ]
    assert [f["kind"] for f in cards["3"]["fragen"]] == ["zwischenfrage"]
    assert cards["3"]["reden"] == []
    assert cards["1"]["fragen"][0]["speaker"] == "2"
    assert cards["1"]["fragen"][0]["speaker_name"] == "Dr. Bernd Berg"


def test_befragung_turns_are_not_reden(conn):
    cards, _ = by_id(conn)
    assert len(cards["9"]["befragung"]) == 2
    assert [r["id"] for r in cards["9"]["reden"]] == ["ID2"]
    assert [b["id"] for b in cards["1"]["befragung"]] == ["ID11"]
    assert cards["1"]["reden"] == []


def test_majority_ties_and_empty_have_no_line():
    assert data.majority(Counter(yes=3, no=1)) == "yes"
    assert data.majority(Counter(yes=1, no=1, absent=1)) is None
    assert data.majority(Counter(absent=4)) is None


def test_votes_against_fraction_line(conn):
    cards, meta = by_id(conn)
    assert meta["votes"] == 2
    berg = cards["2"]["votes"][0]
    assert (berg["vote"], berg["line"], berg["deviates"]) == ("no", "yes", True)  # the unmatched row counts too
    assert berg["fraction_tally"] == {"yes": 3, "no": 1, "abstain": 0, "absent": 0}
    adler = cards["1"]["votes"]
    assert [(v["line"], v["deviates"]) for v in adler] == [("yes", False), (None, False)]
    assert cards["3"]["votes"][0]["line"] == "abstain"


def test_card_kinds(conn):
    cards, _ = by_id(conn)
    assert set(cards) == {"1", "2", "3", "4", "5", "6", "7", "9"}
    dahl = cards["4"]  # votes, but no WP 21 mandate in the Stammdaten yet
    assert (dahl["kind"], dahl["in_stammdaten"], dahl["fraction"], dahl["first_vote"]) == (
        "member", False, "CDU/CSU", "2026-07-08",
    )  # fmt: skip
    hubig = cards["9"]
    assert (hubig["kind"], hubig["role"], hubig["mandate"]) == ("speaker", "Bundesministerin", None)


def test_offices_committees_and_index(conn):
    cards, _ = by_id(conn)
    assert [o["role"] for o in cards["3"]["offices"]] == ["Vizepräsidentin des Deutschen Bundestages"]
    assert [o["name"] for o in cards["3"]["other"]] == ["Ältestenrat"]
    assert [o["role"] for o in cards["2"]["offices"]] == ["Parlamentarischer Staatssekretär"]
    assert [c["short"] for c in cards["1"]["committees"]] == ["Gesundheit", "Haushaltsausschuss"]
    assert cards["2"]["name"] == "Dr. Bernd Berg"
    row = data.index_row(cards["1"])
    assert row["committees"] == ["Gesundheit"]  # the ended membership is not current
    assert row["first_term"] is False
    assert data.index_row(cards["2"])["first_term"] is True
    assert data.index_row(cards["4"])["first_term"] is False  # WP 20 before
    assert data.index_row(cards["2"])["office"] == "Parlamentarischer Staatssekretär"
    assert cards["1"]["since"] == "2006-10-01"


def test_drucksachen_authorship_and_subjects(conn):
    cards, meta = by_id(conn)
    adler = cards["1"]
    assert [(d["number"], d["activity"], d["authors"]) for d in adler["authored"]] == [
        ("21/100", "Antrag", 3),
        ("21/200", "Kleine Anfrage", 120),
    ]
    assert adler["authored"][0]["subjects"] == ["Gesundheit", "Recht", "Wohnen"]  # union over both Vorgänge
    assert [d["number"] for d in adler["reported"]] == ["21/300"]  # a rapporteur, not an author
    assert cards["2"]["authored"] == [] and cards["2"]["reported"] == []  # a government answer is neither
    assert meta["dip"] == {"from": "2026-07-06", "to": "2026-07-09", "n": 4, "complete": True}


def test_career(conn):
    cards, _ = by_id(conn)
    assert [(m["wp"], m["type"]) for m in cards["1"]["career"]] == [
        (19, "Direktwahl"),
        (20, "Direktwahl"),
        (21, "Direktwahl"),
    ]


def test_dip_complete_needs_every_sitting_month(conn):
    assert data.dip_complete(conn) is True  # one sitting month (2026-07), DIP has it
    conn.execute("INSERT INTO sitting VALUES ('21/90', 21, 90, '2026-09-10', NULL, NULL, 'x', 'x', 'x', 'x', 'x')")
    assert data.dip_complete(conn) is False


def test_short_contributions_are_not_reden(conn):
    cards, _ = by_id(conn)
    assert cards["3"]["reden"] == []  # under 500 characters, as in the landscape
    assert [(k["id"], k["on_map"]) for k in cards["3"]["kurz"]] == [("ID3", False)]
    assert all(r["on_map"] for r in cards["2"]["reden"])


def test_election_2025(conn):
    cards, meta = by_id(conn)
    assert cards["1"]["election"] == {
        "via": "constituency", "party": "SPD", "number": 14, "constituency": "Rostock", "percent": 38.2,
        "list_state": "MV", "list_position": 2,
    }  # fmt: skip
    berg = cards["2"]["election"]  # a list member's own share is the party's Erststimme result where they stood
    assert (berg["via"], berg["list_position"], berg["number"], berg["percent"]) == ("list", 3, 242, 30.5)
    assert cards["3"]["election"] is None  # Nachrücker are not in the file
    assert [s["doc"] for s in meta["election"]] == [
        "Bundeswahlleiterin, BTW 2025 Gewählte (Stand 2025-03-12)",
        "Bundeswahlleiterin, BTW 2025 Ergebnisse nach Wahlkreisen (Stand 2025-03-14)",
    ]
    wks = {w["number"]: w for w in data.constituencies(conn)}
    assert (wks[58]["seat_party"], wks[58]["first_party"], wks[58]["first_percent"]) == (None, "AfD", 33.3)
    assert wks[14]["turnout"] == 80.0


def test_store_without_election_tables(conn):
    for t in ("election_candidacy", "constituency_result", "constituency"):
        conn.execute(f"DROP TABLE {t}")
    cards, meta = by_id(conn)
    assert cards["1"]["election"] is None and meta["election"] == []
    assert data.constituencies(conn) == []
