"""The visual controls (controls.py, controls.js): each component's HTML with its counts, labels and ARIA attributes,
the mapping of DIP's Stände onto the pipeline's stages, the URL state round trip (in Node), and the full list without
JavaScript."""

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import test_subjects
from conftest import need_node

from research import controls, data, eu, pages, procedures, subjects

SRC = str(Path(controls.__file__).parent / "controls.js")


def test_toggle_is_a_real_button():
    b = controls.toggle("art", "antrag", "Antrag", cls="key", label="Antrag")
    assert b.startswith('<button type="button" class="tg key" data-f="art" data-v="antrag" aria-pressed="false"')
    assert 'data-label="Antrag"' in b and b.endswith(">Antrag</button>")
    seg = controls.toggle("art", "antrag", "", name="Antrag: 12", tab=False)
    assert 'aria-label="Antrag: 12"' in seg and 'tabindex="-1"' in seg


def test_segmented_bar():
    items = [("antrag", "Antrag", 30), ("gesetzgebung", "Gesetzgebung", 10)]
    html = controls.segmented("art", items, "Art", "Vorgänge")
    assert 'role="group" aria-label="Art"' in html
    assert 'style="flex-grow:30"' in html and 'aria-label="Antrag: 30 Vorgänge, 75 %"' in html
    key = html.split('class="seg-key"', 1)[1]
    assert key.count('aria-pressed="false"') == 2 and '<span class="c" data-n="10">10</span>' in key
    assert "25 %" in key
    assert controls.share(1, 300) == "0,3 %" and controls.share(0, 0) == "0 %"


def test_pipeline_and_stage_mapping():
    assert set(procedures.STAGE) == set(procedures.STATUS_GLOSSARY)  # every DIP Stand has a stage
    stages = {k for k, _ in (*procedures.STAGES, *procedures.ENDED, procedures.NO_STAGE)}
    assert set(procedures.STAGE.values()) <= stages
    assert procedures.STAGE["Überwiesen"] == "ausschuesse" and procedures.STAGE["Verabschiedet"] == "beschlossen"
    assert procedures.STAGE["Bundesrat hat Zustimmung versagt"] == "versagt"
    bill = {"type": procedures.GESETZ, "status": "Ein neuer Stand"}
    assert procedures.stage(bill) == "ohne" and procedures.stage({"type": "Antrag", "status": "x"}) == ""
    stages = [("eingebracht", "Eingebracht", 4), ("verkuendet", "Verkündet", 2)]
    html = controls.pipeline("stufe", stages, [("abgelehnt", "Abgelehnt", 1)], "Stand", "beendet ohne Gesetz",
                             ("ohne", "ohne", 0))  # fmt: skip
    main = html.split('<ol class="pipe-main">', 1)[1].split("</ol>", 1)[0]
    assert main.index('data-v="eingebracht"') < main.index('data-v="verkuendet"')
    assert '<span class="pl">Eingebracht</span><span class="c" data-n="4">4</span>' in main
    assert 'style="width:50%"' in main  # Verkündet: 2 of the largest 4
    assert "beendet ohne Gesetz" in html and 'data-v="abgelehnt"' in html and 'data-v="ohne"' not in html


def test_chips():
    html = controls.group_chips("von", Counter({"SPD": 3, "Bundesregierung": 2}))
    assert 'aria-label="Einbringer"' in html
    assert 'data-v="spd" aria-pressed="false" data-label="SPD" style="--c:var(--spd)"' in html
    assert 'style="--c:var(--reg)"' in html and ">Grüne <" in html
    assert re.search(r'data-v="afd"[^>]*disabled', html)  # nothing to filter
    assert 'data-v="frl"' not in html  # fraktionslos only when there is one
    sized = controls.sized_chips("ausschuss", [("a", "A", 4), ("b", "B", 1)], "Ausschuss")
    assert 'style="width:25%"' in sized and 'data-label="B"' in sized


def test_stacked_rows():
    kinds = [("Gesetzgebung", "Gesetzgebung"), ("Antrag", "Anträge")]
    html = controls.stacked("von", [("spd", "SPD", "spd", Counter({"Gesetzgebung": 2, "Antrag": 6})),
                                    ("reg", "Bundesregierung", "reg", Counter({"Gesetzgebung": 4}))],
                            kinds, "Einbringer", "Vorgänge")  # fmt: skip
    assert html.count('class="tg srow"') == 2 and 'aria-pressed="false"' in html
    assert '<span class="stot"><span class="c" data-n="8">8</span></span>' in html
    assert "2 Gesetzgebung · 6 Anträge" in html and 'title="Anträge: 6"' in html  # numbers in text and on hover
    assert 'style="width:50%"' in html  # the government's 4 against the SPD's 8


def test_tiles():
    kinds = [("Antrag", "Anträge")]
    items = [("a.html", "Wirtschaft", 90, Counter({"Antrag": 90})), ("b.html", "Sport", 1, Counter({"Antrag": 1}))]
    html = controls.tiles(items, kinds, "Vorgänge", "Vorgang", "Sachgebiete")
    assert '<nav class="tiles" aria-label="Sachgebiete">' in html
    assert '<a class="tile" href="a.html"' in html and "1 <span" in html and ">Vorgang</span>" in html
    big, small = controls.tile_basis([90, 1])
    assert big > small == controls.TILE_MIN  # by count, and never narrower than a readable name
    assert '<div class="trow" data-c="1"><a class="tile" href="a.html"' in html  # the largest alone in its row
    assert controls.tile_basis([40, 1], per=10) == [400, controls.TILE_MIN]  # a fixed width per unit (Gremien)


def test_tile_rows_fill_the_field_and_never_grow_downwards():
    """Every row is split into equal tiles and full; rows hold no fewer tiles than the one above, so the field is one
    rectangle and a smaller item never gets a bigger tile."""
    for counts in ([400, 120, 90, 60, 50, 40, 30, 20, 10, 5, 3, 1], [5] * 7, [1], list(range(190, 0, -1))):
        rows = controls.tile_rows(controls.tile_basis(counts))
        assert sum(rows) == len(counts) and all(c in controls.ROW_SPLITS for c in rows)
        assert rows == sorted(rows)
    assert controls.tile_rows(controls.tile_basis([400, 120, 90, 60, 50, 40, 30, 20, 10, 5, 3, 1]))[0] < 3


def test_strip():
    weeks = controls.weeks_between("2025-12-24", "2026-01-12")
    assert weeks == ["2025-W52", "2026-W01", "2026-W02", "2026-W03"]
    html = controls.strip(weeks, Counter({"2026-W01": 4, "2026-W02": 1}), {"2026-W02"}, "Vorgänge", "Vorgang")
    assert html.count('class="swk') == 4 and html.count('tabindex="-1"') == 3  # one tab stop, arrow keys move
    assert 'aria-label="KW 2/2026, Sitzungswoche: 1 Vorgang"' in html and 'class="swk s"' in html
    assert 'data-w="2026-W01"' in html and 'style="height:100%"' in html and 'style="height:25%"' in html
    assert "Dez 2025" in html and "data-zeit-clear hidden" in html
    assert "Jan" not in html  # a quarter in the last 4 weeks has no room for its label
    longer = controls.weeks_between("2025-12-24", "2026-02-02")
    assert "Jan 2026" in controls.strip(longer, Counter(), set(), "Vorgänge", "Vorgang")


def test_view_shows_chart_and_table_without_javascript():
    html = controls.view("stufe", "Stand", "<p>chart</p>", "<p>table</p>")
    assert '<figure class="cv" data-view="stufe">' in html and "<p>chart</p>" in html and "<p>table</p>" in html
    assert '<button type="button" data-show="alt" aria-pressed="false">Als Tabelle</button>' in html
    text = (Path(controls.__file__).parent / "cards.css").read_text(encoding="utf-8")
    assert "html.js .cv-alt { display: none" in text  # only hidden once the script runs
    assert controls.head("../").startswith(controls.HEAD) and 'src="../controls.js" defer' in controls.head("../")


def test_the_full_list_is_in_the_file(conn):
    """Without JavaScript every row is there and none is hidden; controls.js cuts the list to the newest LIMIT."""
    procs, sittings = test_subjects.setup(conn)
    html = procedures.index_page(procs, [s["date"] for s in sittings])
    box = html.split("data-rows", 1)[1].split("data-none", 1)[0]
    assert box.count('<a class="row"') == len(procs) and " hidden" not in box.split(">", 1)[1]
    assert f'data-limit="{controls.LIMIT}"' in html and "data-more hidden>mehr anzeigen" in html
    assert 'class="ctl-scope" data-noun="Vorgänge" data-one="Vorgang" data-dat="Vorgängen"' in html
    for part in ('data-f="art"', 'data-f="stufe"', 'data-f="von"', 'class="strip"', "data-q", "data-reset"):
        assert part in html, part
    g1 = html.split('href="g1.html"', 1)[1].split(">", 1)[0]
    assert 'data-art="gesetzgebung" data-stufe="verkuendet" data-von="reg" data-w="2026-W28"' in g1


def test_rows_date_is_the_latest_step_that_happened(conn):
    """A promulgated law with an Inkrafttreten in 2030 sorts by its last step until today, and says when it comes
    into force."""
    test_subjects.setup(conn)
    conn.execute("UPDATE vorgang SET inkrafttreten = ? WHERE id = 'g1'", (json.dumps([{"datum": "2030-01-01"}]),))
    decided = data.decisions(conn)
    procs = {b["id"]: b for b in procedures.load(conn, data.sittings(conn, decided), decided, today="2026-10-05")}
    g1 = procs["g1"]
    assert g1["latest"] == "2026-07-08" and g1["in_force"] == "2030-01-01"
    assert "tritt am 01.01.2030 in Kraft" in procedures.row(g1, "g1.html")
    later = procedures.load(conn, data.sittings(conn, decided), decided, today="2030-02-01")
    assert next(b for b in later if b["id"] == "g1")["latest"] == "2030-01-01"


def test_sachgebiet_and_eu_and_votes_pages_have_their_controls(conn):
    procs, sittings = test_subjects.setup(conn)
    got = subjects.load(conn, procs)
    index = subjects.index_page(got, subjects.without_subject(conn), subjects.plenary_without_vorgang(sittings), True)
    assert '<figure class="cv" data-view="sachgebiete">' in index
    assert 'class="tile" href="../sachgebiete/wirtschaft' in index
    assert "<th>Sachgebiet</th>" in index  # the table behind "Als Tabelle"
    page = eu.page(eu.load(conn), procs, europe=True, sitting_dates=["2026-07-08"])
    assert 'data-f="stand"' in page and 'class="strip"' in page and 'data-w="2026-W14"' in page
    decisions = data.decisions(conn)
    votes = pages.votes_index(decisions, {"sittings": {"from": "2025-03-25"}}, sitting_dates=["2026-07-08"])
    assert 'data-attr-art="kind" data-attr-ergebnis="result"' in votes and 'data-row=".dec"' in votes
    assert 'data-f="art" data-v="namentlich"' in votes and 'style="--c:var(--v-no)"' in votes
    assert 'data-w="2026-W28"' in votes and "<select" not in votes


def node(script: str):
    run = subprocess.run(["node", "-e", f"const C = require({json.dumps(SRC)});{script}"], capture_output=True,
                         text=True, check=True)  # fmt: skip
    return json.loads(run.stdout)


def test_url_state_round_trip_in_node():
    need_node()
    hashes = ["#von=spd,cdu&art=antrag&zeit=2026-W10..2026-W20&q=Miete%20und%20Pacht&ansicht=stufe",
              "#art=namentlich&ergebnis=abgelehnt", "#zeit=2026-W20..2026-W10", "#glossar", "", "#q=a%26b"]  # fmt: skip
    got = node(f"""console.log(JSON.stringify({json.dumps(hashes)}.map(h => {{
        const s = C.parse(h); return [s, C.serialize(s), C.serialize(C.parse(C.serialize(s)))]; }})))""")
    full, votes, reversed_, anchor, none, amp = got
    assert full[0] == {"f": {"von": ["spd", "cdu"], "art": ["antrag"]}, "zeit": ["2026-W10", "2026-W20"],
                       "q": "Miete und Pacht", "ansicht": ["stufe"]}  # fmt: skip
    assert full[1] == "art=antrag&von=spd,cdu&zeit=2026-W10..2026-W20&q=Miete%20und%20Pacht&ansicht=stufe"
    assert all(x[1] == x[2] for x in got)  # serialize ∘ parse is stable
    assert votes[1] == "art=namentlich&ergebnis=abgelehnt"  # the old URLs of the votes page keep working
    assert reversed_[0]["zeit"] == ["2026-W10", "2026-W20"]
    assert anchor[1] == none[1] == ""  # an anchor is no state
    assert amp[0]["q"] == "a&b"


def test_row_matching_in_node():
    need_node()
    rows = [{"tok": {"art": ["antrag"], "von": ["spd", "cdu"]}, "w": "2026-W12", "text": "mieten"},
            {"tok": {"art": ["gesetzgebung"], "von": ["reg"]}, "w": "2026-W30", "text": "pflege"},
            {"tok": {"art": ["antrag"], "von": []}, "w": "", "text": "mieten"}]  # fmt: skip
    cases = ["#art=antrag", "#von=reg,cdu", "#art=antrag&von=reg", "#zeit=2026-W10..2026-W20", "#q=miet"]
    got = node(f"""const rows = {json.dumps(rows)};
        console.log(JSON.stringify({json.dumps(cases)}.map(h => rows.map(r => C.matches(r, C.parse(h))))))""")
    assert got == [[True, False, True], [True, True, False], [False, False, False], [True, False, False],
                   [True, False, True]]  # fmt: skip
    skip = node(f"""console.log(JSON.stringify(C.matches({json.dumps(rows[1])}, C.parse('#art=antrag'), 'art')))""")
    assert skip is True  # a control's own counts ignore its own filter
