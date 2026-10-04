from pathlib import Path

from research import data, debate, topics

THEMES = Path(__file__).parent / "speech_themes.json"


def test_no_topic_pages_without_the_landscape_file(conn, tmp_path, monkeypatch):
    monkeypatch.delenv("LANDSCAPE_THEMES", raising=False)
    cards, _ = data.cards(conn)
    assert topics.write(tmp_path, debate.themes(), data.speech_facts(cards), data.sittings(conn)) == {}
    assert not (tmp_path / "themen").exists()


def test_topic_pages(conn, tmp_path):
    cards, _ = data.cards(conn)
    written = topics.write(tmp_path, debate.themes(THEMES), data.speech_facts(cards), data.sittings(conn))
    assert set(written) == {3, 5}  # ID404 is not in the store; ID1-5 is a part of the rede ID1
    page = (tmp_path / "themen" / "3.html").read_text()
    assert "Miete · Wohnen · Mietpreisbremse" in page and 'href="../reden/ID1.html"' in page
    assert "nicht dauerhaft" in page and 'content="noindex"' in page  # theme ids change with every rebuild
    assert "#thema=3" in page
    assert 'href="3.html"' in (tmp_path / "themen" / "index.html").read_text()
