from research import build, data


def card_page(conn, tmp_path, pid):
    cards, meta = data.cards(conn)
    decided = data.decisions(conn)
    build.write_site(cards, meta, tmp_path, decisions=decided, members=data.roll_call_members(conn),
                     sittings=data.sittings(conn, decided))  # fmt: skip
    return (tmp_path / f"{pid}.html").read_text()


def test_card_tabs_are_written_by_the_fact_components(conn, tmp_path):
    page = card_page(conn, tmp_path, "2")
    reden = page.split('id="tab-reden"', 1)[1].split('id="tab-abstimmungen"', 1)[0]
    assert '<div class="sp solo"' in reden and 'href="reden/ID1.html"' in reden
    assert "#rede=ID1" in reden  # on the landscape's map: linked in its week
    assert "Wohnen ist die soziale Frage" in reden  # a short excerpt, the full text on reden/
    votes = page.split('id="tab-abstimmungen"', 1)[1].split('id="tab-drucksachen"', 1)[0]
    assert 'class="dec hi"' in votes and 'data-dev="1"' in votes  # Berg voted against the CDU/CSU line
    assert '<span class="mark dev"' in votes and 'href="abstimmungen/21-88-1.html"' in votes
    assert "data-pagefind-body" not in page  # cards are found as entities (D20)


def test_card_documents_tab(conn, tmp_path):
    page = card_page(conn, tmp_path, "1")
    docs = page.split('id="tab-drucksachen"', 1)[1]
    assert 'id="drucksachen-eigene"' in docs and "eine von 3 Namen" in docs and 'data-small="1"' in docs
    assert 'href="https://dip.bundestag.de/drucksache/x/d1"' in docs
    assert 'id="drucksachen-berichte"' in docs


def test_card_js_renders_no_facts():
    js = (build.HERE / "card.js").read_text()
    for gone in ("function renderReden", "function renderVotes", "function renderDocuments", "votePage",
                 "fractionMark", "mapLink"):  # fmt: skip
        assert gone not in js
