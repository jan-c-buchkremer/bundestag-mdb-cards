from collections import Counter

from cards import build, cohesion, data


def test_rice():
    assert cohesion.rice(Counter(yes=3, no=1)) == 0.5
    assert cohesion.rice(Counter(yes=2, abstain=5)) == 1.0  # abstentions are not in the value
    assert cohesion.rice(Counter(abstain=1, absent=4)) is None


def test_pct_never_rounds_up_to_one():
    assert cohesion.pct(0.9996, 3) == "0,999"
    assert cohesion.pct(1.0, 3) == "1,000"
    assert cohesion.pct(0.5) == "0,50"
    assert cohesion.pct(None) == "–"


def test_lines_and_dissents(conn):
    c = cohesion.cohesion(data.decisions(conn), data.roll_call_members(conn))
    assert [d["id"] for d in c["votes"]] == ["21/88/1", "21/88/2"]
    assert list(c["series"]) == ["CDU/CSU", "SPD", "Die Linke"]
    spd = c["series"]["SPD"]
    assert (spd[0]["line"], spd[0]["rice"], spd[0]["dissents"]) == ("yes", 1 / 3, 1)
    # a tie: no line, split, and nobody dissents; the absent member is never a dissent
    assert (spd[1]["line"], spd[1]["rice"], spd[1]["dissents"]) == (None, 0.0, 0)
    assert c["series"]["Die Linke"][0]["rice"] is None
    got = [(x["vote"]["id"], x["person"], x["fraction"], x["own"], x["line"]) for x in c["dissents"]]
    assert got == [("21/88/1", "2", "CDU/CSU", "no", "yes"), ("21/88/1", "6", "SPD", "no", "yes")]


def test_page(conn, tmp_path):
    cards, meta = data.cards(conn)
    decided = data.decisions(conn)
    written = build.write_site(cards, meta, tmp_path, decisions=decided, members=data.roll_call_members(conn),
                               sittings=data.sittings(conn, decided))  # fmt: skip
    assert written["abstimmungen"] == len(decided) + 2  # the votes, the overview and this page
    page = (tmp_path / "abstimmungen" / "geschlossenheit.html").read_text()
    assert "gespalten" in page and "Rice-Index" in page
    rows = page.split('<table class="dis"', 1)[1].split("</tbody>", 1)[0]
    assert rows.count("<tr data-f=") == 2
    assert 'href="../6.html"' in rows and 'href="21-88-1.html"' in rows
    assert "statt Ja" in rows
    assert 'href="21-88-2.html"' in page  # the split vote is a hollow point in the SPD timeline
    assert 'href="../abstimmungen/geschlossenheit.html"' in (tmp_path / "sitzungen" / "21-88.html").read_text()
    assert 'href="abstimmungen/geschlossenheit.html"' in (tmp_path / "index.html").read_text()


def test_no_page_without_lists(tmp_path):
    assert cohesion.write_page(tmp_path, [], {}) == 0
    assert not (tmp_path / "abstimmungen").exists()
