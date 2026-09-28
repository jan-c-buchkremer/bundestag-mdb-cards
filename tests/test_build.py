import json

from cards import build, data


def test_write_site(conn, tmp_path):
    cards, meta = data.cards(conn)
    cards[0]["name"] = "</script><b>x"  # must not end the inline script
    build.write_site(cards, meta, tmp_path)
    assert (tmp_path / "index.html").exists()
    for asset in ("card.js", "cards.css", "parliament.js"):
        assert (tmp_path / asset).read_bytes() == (build.HERE / asset).read_bytes()
    page = (tmp_path / f"{cards[0]['id']}.html").read_text()
    assert "</script><b>" not in page
    assert "__CARD__" not in page and "__META__" not in page
    assert json.loads((tmp_path / "2.json").read_text())["name"] == "Dr. Bernd Berg"
    assert '"built":' in (tmp_path / "index.html").read_text()


def test_description():
    member = {"kind": "member", "name": "Anna Adler", "fraction": "SPD",
              "mandate": {"type": "Direktwahl", "number": 14, "constituency": "Rostock"}}  # fmt: skip
    assert build.description(member).startswith("Anna Adler (SPD, Wahlkreis 14 Rostock), Mitglied")
    speaker = {"kind": "speaker", "name": "Stefanie Hubig", "role": "Bundesministerin der Justiz"}
    assert build.description(speaker).startswith("Stefanie Hubig, Bundesministerin der Justiz im")
