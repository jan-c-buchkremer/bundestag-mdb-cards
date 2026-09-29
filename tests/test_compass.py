import json

from cards import build, compass, data

HANDS = {"id": "21/90/h1", "kind": "handzeichen",
         "fractions": {"SPD": "yes", "AfD": "no", "Die Linke": "abstain"}}  # fmt: skip
ROLL = {"id": "21/88/1", "kind": "namentlich",
        "fractions": {"SPD": {"yes": 2, "no": 1, "abstain": 0},
                      "CDU/CSU": {"yes": 1, "no": 1, "abstain": 0}}}  # fmt: skip


def cand(id_, kind, **kw):
    return {"id": id_, "kind": kind, "topic": "Wohnen", "initiator": "Bundesregierung", "invert": False,
            "question": "Soll …?", "why": "curator only", "note": None, "camp_vote_risk": None,
            "review": "curator only", "selected": True, "question_approved": True, **kw}  # fmt: skip


def test_fraction_positions_roll_call_line_and_show_of_hands():
    assert compass.fraction_positions(ROLL, False) == {"SPD": "yes"}  # CDU/CSU tied: no line
    assert compass.fraction_positions(HANDS, True) == {"SPD": "no", "AfD": "yes", "Die Linke": "abstain"}


def test_build_questions_needs_both_flags_and_publishes_no_curator_notes():
    decisions = [
        {**ROLL, "page": "21-88-1", "date": "2026-07-08", "title": "Miete", "drucksachen": []},
        {**HANDS, "page": "21-90-h1", "date": "2026-09-01", "title": "Rente", "drucksachen": []},
    ]
    members = {"21/88/1": [["1", "Adler", "SPD", "yes"], ["2", "Berg", "CDU/CSU", "absent"]]}
    cands = [cand("21/88/1", "namentlich", invert=True, camp_vote_risk="Lagerabstimmung"),
             cand("21/90/h1", "handzeichen", question_approved=False),
             cand("21/99/1", "namentlich")]  # fmt: skip
    (q,) = compass.build_questions(cands, decisions, members)
    assert q["id"] == "21/88/1" and q["fractions"] == {"SPD": "no"}
    assert q["votes"] == [["1", "no"]]  # flipped; an absent member is left out
    assert q["caution"] == "Lagerabstimmung" and q["initiator"] == "Bundesregierung"
    assert "curator only" not in json.dumps(q)


def test_candidate_file_is_complete_and_keeps_review_notes_apart():
    cands = compass.candidates()
    assert len({c["id"] for c in cands}) == len(cands)
    for c in cands:
        assert {"selected", "question_approved", "invert", "question", "review", "camp_vote_risk"} <= set(c)
        assert "geprüft werden" not in (c["note"] or ""), c["id"]  # a reminder for the curator is a review note
        assert not c["invert"] or c["yes_on_decision"], c["id"]  # every flip says what a Ja did


def test_no_page_until_curated(conn, tmp_path):
    decided = data.decisions(conn)
    assert compass.questions(decided, data.roll_call_members(conn)) == []  # nothing selected and approved yet


def test_page_when_curated(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(compass, "candidates", lambda: [cand("21/88/1", "namentlich", note="öffentlich")])
    monkeypatch.setattr(compass, "MIN_QUESTIONS", 1)
    cards, meta = data.cards(conn)
    decided = data.decisions(conn)
    written = build.write_site(cards, meta, tmp_path, decisions=decided, members=data.roll_call_members(conn),
                               sittings=data.sittings(conn, decided))  # fmt: skip
    assert written["kompass"] == 1
    page = (tmp_path / "kompass.html").read_text()
    assert "öffentlich" in page and "curator only" not in page
    assert 'href="../kompass.html"' in (tmp_path / "abstimmungen" / "index.html").read_text()
