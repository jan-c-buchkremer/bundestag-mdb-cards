"""End to end: the fixture store, enriched with what the entity pages need, written to a SQLite file, built with
`research build` and checked with scripts/check_links.py --anchors. Also follows every row of the redirect table in
docs/plan.md (section 11.3) through the stubs, fragments included."""

import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import test_procedures
import test_questions
import test_subtops
from conftest import LONG, speech, store

from research import cli, urls

HERE = Path(__file__).parent
SRC = ("u", "d", "t")


def enrich(c: sqlite3.Connection) -> None:
    """Bill g1 (Gesetzentwurf 21/500) with its DIP steps up to the Bundesrat and the Verkündung, a show-of-hands
    decision and a roll call; TOP 2 carries Vorlagen of three Vorgänge (21/500 and the Anträge' 21/100); block item
    TOP 5 with sub-items, 5a's Drucksache a Vorgang of its own and a speech under it; a second sitting week;
    Gemeinden for the place search; and the questions of every kind (test_questions.add_research), among them a
    Kleine Anfrage and an Antrag whose Vorgänge have no page."""
    test_procedures.add_bills(c)
    test_subtops.add_block(c)
    test_questions.add_research(c)
    test_procedures.add_missing_debate(c)
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
    c.execute("INSERT INTO sitting (id, wahlperiode, number, date, start_time, end_time, xml_url, pdf_url, source_url, "
              "source_document_id, retrieved_at) "
              "VALUES ('21/89',21,89,'2026-09-10',NULL,NULL,'https://x/21089.xml',"
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
    ("wahlkreise/suche.html", "orte/index.html", "suche"),  # the Gemeinde lookup is the place search
    ("suche.html", "suche.html", ""),
    ("index.html", "index.html", ""),
    ("abstimmungen/geschlossenheit.html", "abstimmungen/geschlossenheit.html", ""),
    # this session's moves (docs/plan.md 12.6)
    ("karrieren/index.html", "abgeordnete.html", "rollen"),  # Karrieren is the Rollen section of the Abgeordnete page
    ("karrieren/index.html#x", "abgeordnete.html", "rollen"),  # the old page had no anchors: any fragment → #rollen
    ("abstimmungen/index.html", "abstimmungen/index.html", ""),  # a sub-tab of Sitzungen now, same URL
    ("orte/index.html#suche", "orte/index.html", "suche"),
    ("orte/index.html#karte", "orte/index.html", "karte"),
]


@pytest.mark.parametrize(("old", "page", "frag"), REDIRECTS)
def test_old_urls_resolve(site, old, page, frag):
    landed, got = follow(site, old)
    assert landed == site / page and got == frag
    if frag:
        assert f'id="{frag}"' in landed.read_text(encoding="utf-8")


def test_old_index_view_states_reach_the_place_pages(site):
    """index.html#ansicht=wahlkreise… is view state the index's script turns into the place page (places.js
    legacyTarget, run here in Node), and the page it names exists; other hashes stay on the index."""
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    page = (site / "index.html").read_text()
    assert '<script src="places.js"></script>' in page and "Places.legacyTarget(location.hash" in page
    slugs = json.loads(re.search(r"Places\.legacyTarget\(location\.hash, (\{.*?\})\)", page).group(1))
    hashes = ["#ansicht=wahlkreise", "#ansicht=wahlkreise&wk=14", "#ansicht=wahlkreise&q=x&state=BY&wk=58",
              "#ansicht=wahlkreise&state=BB", "#ansicht=personen&state=BY", "#ort=BY", ""]  # fmt: skip
    script = (
        f"const P = require({json.dumps(str(site / 'places.js'))});"
        f"console.log(JSON.stringify({json.dumps(hashes)}.map(h => P.legacyTarget(h, {json.dumps(slugs)}))));"
    )
    got = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert got == ["orte/index.html", "orte/wahlkreis-14.html", "orte/wahlkreis-58.html", "orte/brandenburg.html",
                   None, None, None]  # fmt: skip
    assert all((site / t).is_file() for t in got if t)
    assert 'id="rollen"' in page and 'id="ortq"' in page and 'data-v="wahlkreise"' not in page


def test_files_that_must_keep_existing(site):
    for path in (
        "1.json",
        "woche/feed.xml",
        "suche.json",
        "suche-kurz.json",
        "orte/orte.json",
        "nav.js",
        "places.js",
        "wkmap.js",
        "fragen.js",
        "wahlkreise.json",
        "fotos",
        "pagefind/pagefind.js",
    ):
        assert (site / path).exists(), path
    feed = (site / "woche" / "feed.xml").read_text()
    assert "<id>https://plenar-radar.de/woche/2026-W28.html</id>" in feed


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


def test_calendar_shows_a_weeks_votes_and_vorgaenge(site):
    """sitzungen/index.html: week W28's card holds sitting 88 with its votes (facts.decision, result badge, roll call
    or show of hands) and the Vorgänge that moved forward, each behind the week's toggles."""
    cal = (site / "sitzungen" / "index.html").read_text()
    assert 'href="#2026-W28"' in cal and 'href="#2026-W37"' in cal  # the year strip links the sitting weeks
    card = cal.split('<section class="wk" id="2026-W28">', 1)[1].split("</section>", 1)[0]
    assert 'href="21-88.html">88. Sitzung</a>' in card and 'href="../woche/2026-W28.html"' in card
    votes = card.split('<div class="votes">', 1)[1].split('<div class="procs">', 1)[0]
    assert 'id="abst-' not in votes and 'class="badge angenommen"' in votes
    assert "namentlich" in votes and "Handzeichen" in votes
    assert 'href="../vorgaenge/g1.html#abst-21-88-2"' in votes  # a vote of one Vorgang links its timeline point
    procs = card.split('<div class="procs">', 1)[1]
    assert 'href="../vorgaenge/g1.html">' in procs and "abgestimmt" in procs and "beraten (TOP 2)" in procs
    assert 'class="t-votes"' in card and 'class="t-procs"' in card
    assert 'aria-current="page">Sitzungswochen</a>' in cal  # the sub-tabs, Abstimmungen beside it
    votes_page = (site / "abstimmungen" / "index.html").read_text()
    assert 'aria-current="page">Abstimmungen</a>' in votes_page and "ist ein Punkt in seinem Ablauf" in votes_page


def test_week_page_has_vorgaenge_and_votes_as_facets(site):
    week = (site / "woche" / "2026-W28.html").read_text()
    facet = week.split('id="vorgaenge"', 1)[1].split('<section class="facet"', 1)[0]
    assert 'href="../vorgaenge/g1.html"' in facet and 'href="../vorgaenge/g5.html"' in facet
    assert 'id="abstimmungen"' in week
    assert "ist ein Punkt in seinem Ablauf" in (site / "vorgaenge" / "g1.html").read_text()  # D15, in one paragraph


def test_fragen_lists_link_their_sources(site):
    """regierung/<kind>.json for every kind; the pages a row links (cards, speech pages, sittings) exist."""
    from research import questions

    for slug, _, _ in questions.KINDS:
        d = json.loads((site / "regierung" / f"{slug}.json").read_text())
        assert d["rows"], slug
        for pid, _, _, card in d["persons"]:
            assert not card or (site / f"{pid}.html").is_file(), (slug, pid)
    turns = json.loads((site / "regierung" / "fragestunde.json").read_text())["rows"]
    for speech_id, *_ in turns:
        assert (site / urls.speech(speech_id).split("#")[0]).is_file(), speech_id
    (mf,) = json.loads((site / "regierung" / "muendliche-fragen.json").read_text())["rows"]
    sitting, position = mf[7][:2]
    assert f'id="top-{position}"' in (site / urls.sitting(sitting).split("#")[0]).read_text()
    adler = (site / "1.html").read_text()
    assert "21/620" in adler and "vorgaenge/rvn.html" not in adler  # an Antrag whose Vorgang has no page: no link


def test_vorgang_with_a_beratung_missing_from_the_protocols(site):
    page = (site / "vorgaenge" / "325338.html").read_text()
    assert page.count("Der Protokolltext dieser Beratung ist nicht im Datenbestand") == 2
    assert 'href="https://dserver.bundestag.de/btp/21/21031.pdf"' in page and "Beschlüsse laut DIP" in page
    daten = (site / "daten.html").read_text()
    gap = daten.split("Beratungen ohne Protokolltext", 1)[1].split("</ul></li>", 1)[0]
    assert "Sitzung 21/31" in gap and 'href="vorgaenge/325338.html"' in gap and "S. 3392-3396" in gap
