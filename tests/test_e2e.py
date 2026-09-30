"""End to end: the fixture store, enriched with what the entity pages need, written to a SQLite file, built with
`cards build` and checked with scripts/check_links.py --anchors. Also follows every row of the redirect table in
docs/plan.md (section 11.3) through the stubs, fragments included."""

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import test_procedures
import test_subtops
from conftest import LONG, speech, store

from cards import cli

HERE = Path(__file__).parent
SRC = ("u", "d", "t")


def enrich(c: sqlite3.Connection) -> None:
    """Bill g1 (Gesetzentwurf 21/500) with its DIP steps up to the Bundesrat and the Verkündung, a show-of-hands
    decision and a roll call; TOP 2 carries Vorlagen of three Vorgänge (21/500 and the Anträge' 21/100); block item
    TOP 5 with sub-items, 5a's Drucksache a Vorgang of its own and a speech under it; a second sitting week; and
    Gemeinden for the Wahlkreis lookup."""
    test_procedures.add_bills(c)
    test_subtops.add_block(c)
    c.execute("UPDATE agenda_item SET drucksache_numbers = '[\"21/500\", \"21/100\"]' WHERE id = '21/88/2'")
    c.execute("INSERT INTO drucksache VALUES ('d6498','21/6498',21,'Gesetzentwurf','Seelotsgesetz','2026-06-02',NULL,"
              "'BT','[\"Bundesregierung\"]',0,?,?,?)", SRC)  # fmt: skip
    c.execute("INSERT INTO vorgang (id, wahlperiode, type, title, status, subjects, initiators, source_url, "
              "source_document_id, retrieved_at) VALUES ('g5',21,'Gesetzgebung','Seelotsgesetz','Verabschiedet','[]',"
              "'[\"Bundesregierung\"]',?,?,?)", SRC)  # fmt: skip
    c.execute("INSERT INTO vorgang_drucksache VALUES ('g5','d6498')")
    c.execute("UPDATE speech SET sub_item_id = '21/88/5/5a' WHERE id = 'ID50'")
    c.executemany(
        "INSERT INTO vorgang_position VALUES (?,'g1',?,?,?,?,?,?,?,?,'[]',NULL,?,'u','d','t')",
        [
            ("p1", "2026-06-01", "Gesetzentwurf", "BT", "Drucksache", "21/500", "Gesetzentwurf", "https://x/500.pdf",
             None, None),
            ("p2", "2026-07-08", "2. Beratung", "BT", "Plenarprotokoll", "21/88", None, "https://x/88.pdf", "13-18",
             '[{"beschlusstenor": "Annahme", "dokumentnummer": "21/500"}]'),
            ("p3", "2026-07-20", "Durchgang", "BR", "Plenarprotokoll", "1066", None, "https://x/br.pdf", "1", None),
        ],
    )  # fmt: skip
    c.execute(
        "UPDATE vorgang SET verkuendung = ? WHERE id = 'g1'",
        (
            json.dumps(
                [
                    {
                        "verkuendungsdatum": "2026-08-01",
                        "fundstelle": "BGBl. 2026 I Nr. 200",
                        "pdf_url": "https://x/bgbl.pdf",
                    }
                ]
            ),
        ),
    )
    c.execute("INSERT INTO sitting VALUES ('21/89',21,89,'2026-09-10',NULL,NULL,'https://x/21089.xml',"
              "'https://x/21089.pdf','https://x/21089.xml','BT-PlPr. 21/89','2026-09-27')")  # fmt: skip
    c.execute("INSERT INTO agenda_item VALUES ('21/89/1','21/89',1,'Tagesordnungspunkt 1','Haushalt 2027','[]',"
              "'u','BT-PlPr. 21/89','t',0)")  # fmt: skip
    c.execute("INSERT INTO speech VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'rede',NULL)",
              (*speech("ID60", 1, "1", "Anna Adler (SPD)", LONG, "21/89/1", fraction="SPD")[:1], "21/89",
               *speech("ID60", 1, "1", "Anna Adler (SPD)", LONG, "21/89/1", fraction="SPD")[2:]))  # fmt: skip
    muni = ("https://x/gemeinden.csv", "Bundeswahlleiterin, Wahlkreiseinteilung", "t")
    c.executemany(
        "INSERT INTO constituency_municipality VALUES (?,'btw25',?,?,?,?,?,?,?,?,?)",
        [("btw25/13003000/14", "13003000", "Rostock, Hanse- und Universitätsstadt", "Rostock", "MV", 14, 0, *muni),
         ("btw25/12065000/58", "12065000", "Oranienburg, Stadt", "Oberhavel", "BB", 58, 0, *muni)],
    )  # fmt: skip
    c.commit()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    c = store()
    enrich(c)
    db = tmp / "store.sqlite"
    dst = sqlite3.connect(db)
    c.backup(dst)
    dst.close()
    out = tmp / "out"
    env = {"BDF_DB": str(db), "LANDSCAPE_THEMES": str(HERE / "speech_themes.json"), "BDF_RAW": str(tmp / "raw")}
    with pytest.MonkeyPatch.context() as mp:
        for k, v in env.items():
            mp.setenv(k, v)
        for k in ("LANDSCAPE_CLUSTERS", "LANDSCAPE_NEIGHBOURS", "FOUNDATION_EXPORT"):
            mp.delenv(k, raising=False)
        cli.main(["build", "--out", str(out)])
    return out


def test_check_links_passes(site):
    run = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "check_links.py"), str(site), "--anchors"],
                         capture_output=True, text=True)  # fmt: skip
    assert run.returncode == 0, run.stdout
    assert " 0 broken links" in run.stdout


def follow(site: Path, url: str) -> tuple[Path, str]:
    """Where a link lands: the file, and the fragment after a stub's rules (the JS of redirects.PAGE, in Python)."""
    path, _, frag = url.partition("#")
    page = site / path
    text = page.read_text(encoding="utf-8")
    if 'http-equiv="refresh"' not in text:
        return page, frag
    target = json.loads(re.search(r"var target = (\{.*?\}), rules", text).group(1))
    rules = json.loads(re.search(r"rules = (\[.*?\]);", text).group(1))
    new = target["frag"]
    for rx, rep in rules:
        if re.search(rx, frag):
            new = re.sub(rx, rep.replace("$", "\\"), frag, count=1)
            break
    else:
        new = frag or new
    landed = (page.parent / target["path"]).resolve().relative_to(site.resolve())
    return follow(site, str(landed) + (f"#{new}" if new else ""))


# every row of the redirect table (docs/plan.md 11.3), with an example from the fixture: old URL -> landing page
REDIRECTS = [
    ("gesetze/g1.html", "vorgaenge/g1.html", ""),
    ("gesetze/index.html", "vorgaenge/index.html", ""),
    ("gesetze/index.html#status-verkuendet", "vorgaenge/index.html", "status-verkuendet"),
    ("gesetze/index.html#glossar", "vorgaenge/index.html", "glossar"),
    ("abstimmungen/21-88-2.html", "vorgaenge/g1.html", "abst-21-88-2"),  # roll call of exactly one Vorgang
    ("abstimmungen/21-88-h1.html#chart", "vorgaenge/g1.html", "abst-21-88-h1"),  # an old fragment is replaced
    ("abstimmungen/21-88-1.html", "abstimmungen/21-88-1.html", ""),  # no Vorgang: keeps its page
    ("woche/index.html", "sitzungen/index.html", ""),
    ("sitzungen/21-88.html#top-2", "sitzungen/21-88.html", "top-2"),
    ("sitzungen/21-88.html#top-5-5a", "sitzungen/21-88.html", "top-5-5a"),
    ("1.html", "1.html", ""),
    ("reden/ID1.html#ID1-2", "reden/ID1.html", "ID1-2"),
    ("woche/2026-W28.html", "woche/2026-W28.html", ""),
    ("fraktionen/spd.html", "fraktionen/spd.html", ""),
    ("gremien/gesundheit.html", "gremien/gesundheit.html", ""),
    ("wahlkreise/suche.html", "wahlkreise/suche.html", ""),
    ("suche.html", "suche.html", ""),
    ("index.html", "index.html", ""),
    ("abstimmungen/geschlossenheit.html", "abstimmungen/geschlossenheit.html", ""),
]


@pytest.mark.parametrize(("old", "page", "frag"), REDIRECTS)
def test_old_urls_resolve(site, old, page, frag):
    landed, got = follow(site, old)
    assert landed == site / page and got == frag
    if frag:
        assert f'id="{frag}"' in landed.read_text(encoding="utf-8")


def test_files_that_must_keep_existing(site):
    for path in ("1.json", "woche/feed.xml", "suche.json", "pagefind/pagefind.js"):
        assert (site / path).is_file(), path
    feed = (site / "woche" / "feed.xml").read_text()
    assert "<id>https://jan-c-buchkremer.github.io/bundestag-mdb-cards/woche/2026-W28.html</id>" in feed


def test_entity_pages_are_written(site):
    for path in ("orte/index.html", "orte/bayern.html", "orte/wahlkreis-58.html", "gremien/bundesregierung.html",
                 "vorgaenge/g1.html", "vorgaenge/g5.html", "vorgaenge/v1.html", "themen/3.html",
                 "woche/2026-W37.html", "sitzungen/21-89.html"):  # fmt: skip
        assert (site / path).is_file(), path


def test_procedure_timeline_with_roll_call_and_show_of_hands(site):
    page = (site / "vorgaenge" / "g1.html").read_text()
    tl = page.split('<ol class="tl">', 1)[1].split("</ol>", 1)[0]
    order = [tl.index(x) for x in ("Gesetzentwurf", 'id="abst-21-88-h1"', 'id="abst-21-88-2"', "Bundesrat",
                                   "BGBl. 2026 I Nr. 200")]  # fmt: skip
    assert order == sorted(order)  # tabled → votes → Bundesrat → Verkündung
    assert 'class="chart vchart"' in tl and "dafür: <b>" in tl  # roll-call chart and the hands' positions


def test_agenda_item_with_several_vorlagen_and_a_block_with_sub_items(site):
    sitting = (site / "sitzungen" / "21-88.html").read_text()
    top2 = sitting.split('id="top-2"', 1)[1].split('<section class="top"', 1)[0]
    for v in ("g1", "v1", "v2"):  # three Vorgänge on one agenda item
        assert f'href="../vorgaenge/{v}.html"' in top2
    sub = sitting.split('id="top-5-5a"', 1)[1].split('id="top-5-5b"', 1)[0]
    assert 'href="../vorgaenge/g5.html"' in sub and "reden/ID50.html" in sub
    g5 = (site / "vorgaenge" / "g5.html").read_text()
    assert 'href="../sitzungen/21-88.html#top-5-5a"' in g5  # the Vorgang links the sub-item, not the block


def test_search_index_groups_every_entity_type(site):
    index = json.loads((site / "suche.json").read_text())
    assert {index["types"][t] for t, *_ in index["items"]} == set(index["types"])
    gemeinde = [x for x in index["items"] if x[1] == "Oranienburg, Stadt"]
    assert gemeinde and gemeinde[0][3] == "orte/wahlkreis-58.html"
