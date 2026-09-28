from pathlib import Path

from cards import build, data, pages
from cards.titles import short_title

CLUSTERS = Path(__file__).parent / "speech_clusters.json"


def sitting_html(conn, tmp_path, clusters):
    cards, meta = data.cards(conn)
    decided = data.decisions(conn)
    build.write_site(cards, meta, tmp_path, decisions=decided, sittings=data.sittings(conn, decided),
                     clusters=clusters)  # fmt: skip
    return (tmp_path / "sitzungen" / "21-88.html").read_text()


def test_speech_clusters_from_env(monkeypatch, tmp_path):
    monkeypatch.delenv("LANDSCAPE_CLUSTERS", raising=False)
    assert data.speech_clusters() == {}
    monkeypatch.setenv("LANDSCAPE_CLUSTERS", str(tmp_path / "missing.json"))
    assert data.speech_clusters() == {}
    monkeypatch.setenv("LANDSCAPE_CLUSTERS", str(CLUSTERS))
    assert data.speech_clusters()["ID1"] == {"week": "2026-W28", "cluster_id": 7, "label": "Mieten & Wohnungsbau"}
    broken = tmp_path / "broken.json"
    broken.write_text("{")
    assert data.speech_clusters(broken) == {}


def test_worum_ging_es_with_clusters(conn, tmp_path):
    page = sitting_html(conn, tmp_path, data.speech_clusters(CLUSTERS))
    item = page.split('id="top-2"', 1)[1]
    block = item.split('<div class="topics">', 1)[1].split("</div></div>", 1)[0]
    assert block.index("Mieten &amp; Wohnungsbau") < block.index("Eigentum")  # two speeches before one
    assert 'href="https://jan-c-buchkremer.github.io/bundestag-topic-landscape/2026-W28.html#cluster=7"' in block
    assert '<span class="n">2</span>' in block
    assert item.index('class="topics"') < item.index('class="speeches"')  # above the speeches
    assert "not in the store" not in page


def test_worum_ging_es_without_clusters(conn, tmp_path, monkeypatch):
    monkeypatch.delenv("LANDSCAPE_CLUSTERS", raising=False)
    page = sitting_html(conn, tmp_path, data.speech_clusters())
    assert "Worum ging es" not in page and 'class="speeches"' in page


def test_topics_top_five():
    sps = [{"id": f"S{k}"} for k in range(12)]
    clusters = {f"S{k}": {"week": "2026-W28", "cluster_id": k % 7, "label": f"T{k % 7}"} for k in range(12)}
    block = pages.topics_block({"speeches": sps}, clusters)
    assert block.count('class="topic"') == 5 and "und 2 weitere" in block


def test_long_speech_list_collapses():
    def sp(k):
        return {"id": f"S{k}", "person": str(k % 30), "name": f"Rednerin {k}", "fraction": "SPD", "role": None,
                "words": 500, "on_map": True, "photo": False}  # fmt: skip

    s = {"week": "2026-W28"}
    short = pages.speeches_block({"position": 3, "speeches": [sp(k) for k in range(10)]}, s)
    assert "sp-more" not in short and short.count('class="sp"') == 10
    long = pages.speeches_block({"position": 3, "speeches": [sp(k) for k in range(40)]}, s)
    shown, rest = long.split('<div class="sp-rest" id="rest-3">', 1)
    assert shown.count('class="sp"') == 10 and rest.count('class="sp"') == 30  # every card link stays in the file
    assert 'aria-controls="rest-3"' in long and "alle 40 Reden zeigen" in long
    assert long.split('class="sp-faces"', 1)[1].count('class="av"') == pages.FACES  # 30 people, capped


def test_title_is_the_first_sub_items():
    title = ("a) – Zweite und dritte Beratung des von der Bundesregierung eingebrachten Entwurfs eines Gesetzes zur "
             "Modernisierung des Bundespolizeigesetzes | Beschlussempfehlung und Bericht des Innenausschusses | "
             "b) Beratung der Beschlussempfehlung und des Berichts des Innenausschusses zu dem Antrag der Fraktion "
             "Die Linke | Grundrechte schützen")  # fmt: skip
    assert short_title(title, "Zusatzpunkt 21") == "Zur Modernisierung des Bundespolizeigesetzes"
    zp = "7 Erste Beratung des Entwurfs eines Gesetzes zur Mietpreisbremse | ZP 3 Beratung des Antrags der Fraktion X | Mieten stoppen"  # noqa: E501
    assert short_title(zp, "Tagesordnungspunkt 7") == "Zur Mietpreisbremse"
    antrag = "Beratung des Antrags der Fraktion der AfD | Deutschland braucht echte Reformen"
    assert short_title(antrag, "Zusatzpunkt 18") == "Deutschland braucht echte Reformen"
