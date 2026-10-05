import json

from research import build, data


def test_write_site(conn, tmp_path):
    cards, meta = data.cards(conn)
    cards[0]["name"] = "</script><b>x"  # must not end the inline script
    build.write_site(cards, meta, tmp_path)
    assert (tmp_path / "abgeordnete.html").exists()
    for asset in ("card.js", "cards.css", "parliament.js"):
        assert (tmp_path / asset).read_bytes() == (build.HERE / asset).read_bytes()
    page = (tmp_path / f"{cards[0]['id']}.html").read_text()
    assert "</script><b>" not in page
    assert "__CARD__" not in page and "__META__" not in page
    assert json.loads((tmp_path / "2.json").read_text())["name"] == "Dr. Bernd Berg"
    assert '"built":' in (tmp_path / "abgeordnete.html").read_text()


def test_description():
    member = {"kind": "member", "name": "Anna Adler", "fraction": "SPD",
              "mandate": {"type": "Direktwahl", "number": 14, "constituency": "Rostock"}}  # fmt: skip
    assert build.description(member).startswith("Anna Adler (SPD, Wahlkreis 14 Rostock), Mitglied")
    speaker = {"kind": "speaker", "name": "Stefanie Hubig", "role": "Bundesministerin der Justiz"}
    assert build.description(speaker).startswith("Stefanie Hubig, Bundesministerin der Justiz im")


def test_index_payload(conn, tmp_path):
    cards, meta = data.cards(conn)
    build.write_site(cards, meta, tmp_path, data.government(conn), data.last_sitting(conn))
    page = (tmp_path / "abgeordnete.html").read_text()
    payload = json.loads(page.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    assert {g["id"]: g["card"] for g in payload["government"]} == {"9": True, "Q77": False, "2": True}
    assert payload["last_sitting"]["week"] == "2026-W28"
    assert next(r for r in payload["cards"] if r["id"] == "9")["gov"] == "Bundesministerin der Justiz"
    assert json.loads((tmp_path / "wahlkreise.json").read_text())["paths"]["1"].startswith("M")


def test_index_without_round2_tables(conn_without_round2, tmp_path):
    cards, meta = data.cards(conn_without_round2)
    build.write_site(cards, meta, tmp_path, data.government(conn_without_round2), None)
    assert '"government":[]' in (tmp_path / "abgeordnete.html").read_text()


def test_legal_pages_and_no_font_cdn(conn, tmp_path):
    cards, meta = data.cards(conn)
    build.write_site(cards, meta, tmp_path)
    impressum = (tmp_path / "impressum.html").read_text()
    assert "jan.c.buchkremer@gmail.com" in impressum and 'href="datenschutz.html"' in impressum
    assert "Cloudflare" in (tmp_path / "datenschutz.html").read_text()
    assert (tmp_path / "fonts" / "inter-latin.woff2").read_bytes() == (
        build.HERE / "fonts" / "inter-latin.woff2"
    ).read_bytes()
    for page in ("abgeordnete.html", f"{cards[0]['id']}.html", "impressum.html"):
        html = (tmp_path / page).read_text()
        assert "fonts.googleapis" not in html
    assert 'href="impressum.html">Impressum</a>' in (tmp_path / "abgeordnete.html").read_text()
