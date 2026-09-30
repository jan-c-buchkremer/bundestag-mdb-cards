import importlib.util
import json
from pathlib import Path

from cards import build, data, mentions, pages, speeches

HERE = Path(__file__).parent
PAYLOAD = {
    "model": "de_core_news_lg",
    "entities": {
        "Q183": {"label": "Deutschland", "kind": "staat"},
        "Q64": {"label": "Berlin", "kind": "land"},
        "Q7184": {"label": "NATO", "kind": "organisation"},
    },
    # ID1: Berg (CDU/CSU); ID1-2: Cohn's question (Die Linke); ID2: the minister; ID404 is not in the store
    "speeches": {
        "ID1": {"Q183": 2, "Q64": 1},
        "ID1-2": {"Q183": 1},
        "ID2": {"Q183": 3, "Q7184": 1},
        "ID404": {"Q183": 9},
    },
}


def test_load_reads_env_and_survives_bad_files(monkeypatch, tmp_path):
    monkeypatch.delenv("LANDSCAPE_MENTIONS", raising=False)
    assert mentions.load() is None
    path = tmp_path / "m.json"
    path.write_text(json.dumps(PAYLOAD))
    monkeypatch.setenv("LANDSCAPE_MENTIONS", str(path))
    assert mentions.load()["entities"]["Q64"]["label"] == "Berlin"
    path.write_text("{")
    assert mentions.load() is None
    path.write_text(json.dumps({"entities": []}))
    assert mentions.load() is None


def test_aggregate_attributes_parts_to_their_own_group(conn):
    agg = mentions.aggregate(PAYLOAD, speeches.load(conn))
    by_part = {h["part"]["id"]: (h["group"], h["count"]) for h in agg["hits"]["Q183"]}
    # the Zwischenfrage counts for Cohn's fraction; the minister is the government; unknown speeches are ignored
    assert by_part == {"ID1": ("CDU/CSU", 2), "ID1-2": ("Die Linke", 1), "ID2": ("Bundesregierung", 3)}
    assert agg["totals"]["Die Linke"] == 3 and agg["totals"]["CDU/CSU"] == 4  # ID3 is a third Linke part
    assert [h["count"] for h in agg["hits"]["Q7184"]] == [1]


def test_fragestunde_is_left_out(conn):
    redes = speeches.load(conn)
    for r in redes:
        r["kind"] = "fragestunde"
    assert not mentions.aggregate(PAYLOAD, redes)["hits"]


def test_month_span_includes_months_without_sittings():
    assert mentions.month_span("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_pages(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(pages, "OPTIONAL_NAV", set())  # the cli drops the nav entry unless LANDSCAPE_MENTIONS is set
    monkeypatch.setattr(mentions, "MIN_SPEECHES", 2)
    cards, meta = data.cards(conn)
    decided = data.decisions(conn)
    build.write_site(cards, meta, tmp_path, decisions=decided, members=data.roll_call_members(conn),
                     sittings=data.sittings(conn, decided))  # fmt: skip
    redes = speeches.load(conn)
    ids = {c["id"] for c in cards}
    speeches.write_pages(tmp_path, redes, ids)
    assert mentions.write(tmp_path, redes, ids, PAYLOAD) == 2  # Deutschland + the index; NATO and Berlin: one Rede
    page = (tmp_path / "erwaehnungen" / "Q183.html").read_text()
    assert "Deutschland in den Reden" in page and "https://www.wikidata.org/wiki/Q183" in page
    assert "3 Redebeiträge nennen „Deutschland“, insgesamt 6-mal" in page
    # every row links to the speech page, at the part
    assert '<a href="../reden/ID1.html#ID1-2">' in page and '<a href="../reden/ID2.html#ID2">' in page
    assert '<a href="../2.html">Dr. Bernd Berg</a>' in page
    assert "Bundesregierung" in page and 'data-f="Die Linke"' in page and 'id="m-2026-07"' in page
    assert not (tmp_path / "erwaehnungen" / "Q7184.html").exists()
    index = (tmp_path / "erwaehnungen" / "index.html").read_text()
    assert '<a href="Q183.html">Deutschland</a>' in index and "Q7184" not in index
    assert '<a href="erwaehnungen/index.html">Erwähnungen</a>' in (tmp_path / "index.html").read_text()
    spec = importlib.util.spec_from_file_location("check_links", HERE.parent / "scripts" / "check_links.py")
    check_links = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check_links)
    # the nav's targets (regierung/, …) are written by other modules, not here
    ours = [(p, link) for p, link in check_links.check(tmp_path, anchors=True) if "erwaehnungen" in str(p)]
    broken = [(p, link) for p, link in ours if "reden/" in link or "erwaehnungen" in link or "#" in link]
    assert broken == []


def test_no_pages_without_the_file(conn, tmp_path, monkeypatch):
    monkeypatch.delenv("LANDSCAPE_MENTIONS", raising=False)
    assert mentions.write(tmp_path, speeches.load(conn), set()) == 0
    assert not (tmp_path / "erwaehnungen").exists()


def test_nav_entry_is_optional():
    assert "mentions" in pages.OPTIONAL_NAV
    assert "erwaehnungen/index.html" not in pages.site_header("", None)
