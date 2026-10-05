import importlib.util
import json
from pathlib import Path

from research import build, data, search, speeches

HERE = Path(__file__).parent
CLUSTERS = HERE / "speech_clusters.json"


def site(conn, out, similar=None):
    cards, meta = data.cards(conn)
    decided = data.decisions(conn)
    build.write_site(cards, meta, out, decisions=decided, members=data.roll_call_members(conn),
                     sittings=data.sittings(conn, decided))  # fmt: skip
    redes = speeches.load(conn)
    speeches.write_pages(out, redes, {c["id"] for c in cards}, data.speech_clusters(CLUSTERS), similar)
    return redes


def test_load_joins_the_parts(conn):
    redes = {r["id"]: r for r in speeches.load(conn)}
    assert list(redes) == ["ID10", "ID11", "ID12", "ID1", "ID2", "ID3"]  # protocol order, one per rede
    r = redes["ID1"]
    assert [p["id"] for p in r["parts"]] == ["ID1", "ID1-2", "ID1-3", "ID1-4", "ID1-5", "ID1-6", "ID1-7"]
    assert r["parts"][0]["paragraphs"][1] == ("comment", "(Beifall bei der CDU/CSU)")
    assert r["parts"][1]["paragraphs"] == [("text", "Gestatten Sie eine Frage?")]  # no paragraphs: clean text
    assert (r["sitting"], r["top_position"], r["label"], r["title"]) == ("21/88", 2, "TOP 2", "Mietpreisbremse")


def test_speech_page(conn, tmp_path):
    site(conn, tmp_path)
    page = (tmp_path / "reden" / "ID1.html").read_text()
    assert '<a href="../2.html">Dr. Bernd Berg</a> <span class="sub">CDU/CSU</span>' in page
    assert '<a href="../sitzungen/21-88.html#top-2">TOP 2</a>' in page
    assert '<a href="https://x/21088.pdf">Plenarprotokoll BT-PlPr. 21/88 (PDF)</a>' in page
    assert '<p class="rc">(Zuruf von der AfD: Falsch!)</p>' in page
    assert '<p class="rch"><span class="k">Präsidium</span> Gestatten Sie eine Zwischenfrage?</p>' in page
    # the question by Cohn stays in its place, with its anchor and her card
    assert '<div class="rp" id="ID1-2"><div class="rp-who"><a href="../3.html">Clara Cohn</a>' in page
    assert page.index('id="ID1-2"') < page.index('id="ID1-5"')
    assert '#cluster=7">In dieser Woche: Mieten &amp; Wohnungsbau</a>' in page
    for f in ('"Art">Rede', '"Person">Dr. Bernd Berg', '"Fraktion">CDU/CSU', '"Monat">Juli 2026',
              '"Thema">Mieten &amp; Wohnungsbau'):  # fmt: skip
        assert f"data-pagefind-filter={f}</span>" in page
    assert "Ähnliche Reden" not in page and "const PAGE" in page and '"kind":"speech"' in page
    # a speaker without a card: name without link
    hubig = (tmp_path / "reden" / "ID2.html").read_text()
    assert "Stefanie Hubig" in hubig and 'href="../9.html"' in hubig
    assert (tmp_path / "reden.css").exists()


def test_similar_speeches(conn, tmp_path):
    similar = {"ID1": ["ID1", "ID2-3", "ID404", "ID3", "ID2"]}  # itself, a part, unknown, a duplicate
    site(conn, tmp_path, similar)
    page = (tmp_path / "reden" / "ID1.html").read_text()
    block = page.split('<section class="similar">', 1)[1].split("</section>", 1)[0]
    assert block.count('class="row"') == 2
    assert block.index('href="ID2.html"') < block.index('href="ID3.html"')
    assert "ID1.html" not in block


def test_neighbours_from_env(monkeypatch, tmp_path):
    monkeypatch.delenv("LANDSCAPE_NEIGHBOURS", raising=False)
    assert speeches.neighbours() == {}
    path = tmp_path / "n.json"
    path.write_text(json.dumps({"ID1": ["ID2"], "ID2": "not a list"}))
    monkeypatch.setenv("LANDSCAPE_NEIGHBOURS", str(path))
    assert speeches.neighbours() == {"ID1": ["ID2"]}
    path.write_text("{")
    assert speeches.neighbours() == {}


def test_links_to_speech_pages(conn, tmp_path):
    site(conn, tmp_path)
    sitting = (tmp_path / "sitzungen" / "21-88.html").read_text()
    assert '<a href="../reden/ID1.html" title="Der ganze Text dieser Rede">Text</a>' in sitting
    assert "data-pagefind-body" not in sitting  # Pagefind indexes speeches only; sittings are found as entities
    assert '<form class="nav-q" role="search" action="suche.html"' in (tmp_path / "abgeordnete.html").read_text()
    spec = importlib.util.spec_from_file_location("check_links", HERE.parent / "scripts" / "check_links.py")
    check_links = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_links)
    (tmp_path / "suche.html").write_text(search.search_page())
    # search.js is a build.py asset (site() above already wrote it); the real pagefind/ comes from write_index
    # the portraits and the pages of other modules are written by the CLI, not here
    ours = ("reden", "sitzungen", "abstimmungen/2", "suche")
    broken = [(p, link) for p, link in check_links.check(tmp_path, anchors=True) if any(x in link for x in ours)]
    assert broken == []
    (tmp_path / "reden" / "ID3.html").unlink()
    # the sitting page and, now that its tabs are HTML (D13), Clara Cohn's card
    assert sorted(link for _, link in check_links.check(tmp_path) if "reden/" in link) == [
        "../reden/ID3.html", "reden/ID3.html"]  # fmt: skip


def test_search_index(conn, tmp_path):
    site(conn, tmp_path)
    search.write_index(tmp_path)
    assert (tmp_path / "pagefind" / "pagefind.js").exists()
    assert list((tmp_path / "pagefind").glob("pagefind.de*.pf_meta"))
    assert 'type="module" src="search.js"' in (tmp_path / "suche.html").read_text()
