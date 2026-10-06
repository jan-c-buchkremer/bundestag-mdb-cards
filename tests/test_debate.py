import json

import pytest
from conftest import LONG

from research import debate


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Es ist verboten, Zeichen hochzuhalten. Ich erteile Ihnen dafür einen Ordnungsruf.", ["Ordnungsruf"]),
        ("– Herrn Frohnmaier erteile ich einen Ordnungsruf.", ["Ordnungsruf"]),
        ("Der Abgeordnete Kneller erhält von mir einen Ordnungsruf.", ["Ordnungsruf"]),
        ("– Auch Sie kriegen einen Ordnungsruf, weil Sie anscheinend nicht verstanden haben, worum es geht.",
         ["Ordnungsruf"]),
        ("Herr Reichardt, ich rüge Sie für den Ausdruck. Dafür rüge ich Sie.", ["Rüge"]),  # once per paragraph
        ("Deswegen erteile ich Ihnen hierfür eine Rüge.", ["Rüge"]),
        # announcements, threats and hypotheticals are not measures
        ("Im Wiederholungsfall würde ich einen Ordnungsruf erteilen müssen.", []),
        ("– Ich wäre Ihnen dankbar, wenn Sie aufhören würden. Ansonsten erteile ich einen Ordnungsruf.", []),
        ("Da brauchen Sie gar nicht zu lachen, sonst erteile ich Ihnen gleich den nächsten Ordnungsruf.", []),
        ("– Herr Reichardt, wenn Sie jetzt nicht aufhören, kriegen Sie von mir gleich einen Ordnungsruf.", []),
        ("Ich müsste Ihnen theoretisch einen Ordnungsruf erteilen,", []),
        ("Wenn nicht, dann müsste ich sie rügen.", []),
        ("Den einen Zwischenruf, den habe ich gerade überhört, den rüge ich jetzt nicht.", []),
        ("Fürs Protokoll: Der Ordnungsruf ging an Herrn Janich.", []),
    ],
)  # fmt: skip
def test_measures(text, expected):
    assert debate.measures(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Gerne.", "zugelassen"),
        ("Ja, aber selbstverständlich.", "zugelassen"),
        ("Wenn das zur Erhellung beiträgt, gern.", "zugelassen"),
        ("Nein, danke. – Meine Damen und Herren, es geht nicht darum …", "abgelehnt"),
        ("Das dient der Debatte nicht. Vielen Dank, nein.", "abgelehnt"),  # the no wins over a polite word
        ("Ich würde meine Rede gern zu Ende führen.", "abgelehnt"),
        ("Lassen Sie mich bitte fertig sprechen.", "abgelehnt"),
        ("– nein –, dass er in Sachen Trockenheit noch eine Schippe drauflegen könnte.", "abgelehnt"),
        ("Oh, um Gottes willen!", "unklar"),
    ],
)
def test_answer(text, expected):
    assert debate.answer(text) == expected


def test_speaker_group():
    """The foundation's speech.speaker_group, with the Bundesrat counted under Sonstige."""
    assert debate.speaker_group("Bundesregierung") == "Bundesregierung"
    assert debate.speaker_group("SPD") == "SPD"
    assert debate.speaker_group("Bundesrat") == "Sonstige"
    assert debate.speaker_group("Sonstige") == "Sonstige"


def test_a_ministers_speech_counts_for_the_government(conn):
    """Merz's speeches as Kanzler count for the Bundesregierung, not for the CDU/CSU (foundation speaker_group)."""
    conn.execute(
        "INSERT INTO speech (id, sitting_id, agenda_item_id, position, person_id, speaker_name, speaker_role, "
        "fraction, text, source_url, source_document_id, retrieved_at) VALUES ('ID9', '21/88', '21/88/2', 20, '2', "
        "'Dr. Bernd Berg, Bundesminister', 'Bundesminister des Innern', NULL, ?, 'u', 'd', 't')",
        (LONG,),
    )
    group = {s["id"]: s["group"] for s in debate._speeches(conn)}
    assert group["ID9"] == "Bundesregierung" and group["ID1"] == "CDU/CSU"
    member = conn.execute("SELECT member_fraction FROM speech WHERE id = 'ID9'").fetchone()[0]
    assert member == "CDU/CSU"  # the fraction is kept beside it


def test_addressee():
    names = {"Keuter": "AfD", "Stegner": "SPD"}
    assert debate.addressee("Mein Ordnungsruf gilt Herrn Keuter.", names) == "AfD"
    assert debate.addressee("Das war ein Angriff gegen Herrn Stegner.", names) == "unklar"  # talked about
    assert debate.addressee("Herr Kollege, dafür erteile ich Ihnen einen Ordnungsruf.", names) == "unklar"
    assert debate.requester("Erlauben Sie eine Zwischenfrage aus der AfD-Fraktion?", names) == "AfD"
    assert debate.requester("Gestatten Sie eine Zwischenfrage von Herrn Stegner?", names) == "SPD"


def test_shares(conn):
    s = debate.shares(conn, {"ID1": {"theme_id": 3, "label": "Wohnen"}})
    long = 105
    # Berg's two long parts plus "Bitte." and "Doch."; the minister's words go to the government
    assert s["words"]["CDU/CSU"] == 2 * long + 2
    assert s["words"]["Bundesregierung"] == 2 * long + 1
    assert s["seats"] == {"SPD": 3}  # the house as the latest vote list shows it (in the fixture, SPD only)
    # among the members' own words: Adler (SPD) has an earlier Wahlperiode, Berg and Cohn do not
    assert s["dims"]["term"]["schon früher im Bundestag"] == 3 + 4
    assert s["base"]["term"] == {"schon früher im Bundestag": 1, "erste Wahlperiode": 6}  # Lose included
    assert s["dims"]["gender"]["Männer"] == 2 * long + 2
    assert s["themes"] == {"Wohnen": {"CDU/CSU": long}}


def test_order_and_questions(conn):
    conn.executemany(
        "INSERT INTO speech_paragraph VALUES (?,?,?,?,?)",
        [
            ("ID2/1", "ID2", 1, "text", "Wir handeln."),
            ("ID2/2", "ID2", 2, "chair", "Herr Kollege Adler, ich erteile Ihnen einen Ordnungsruf."),
            ("ID2/3", "ID2", 3, "chair", "Frau Ministerin, lassen Sie eine Zwischenfrage aus der AfD-Fraktion zu?"),
            ("ID2/4", "ID2", 4, "comment", "(Zuruf von der AfD)"),
            ("ID2/5", "ID2", 5, "text", "Nein, danke."),
        ],
    )
    ms = debate.order_measures(conn)
    assert [(m["kind"], m["fraction"], m["sitting"]) for m in ms] == [("Ordnungsruf", "SPD", "21/88")]
    qs = debate.interim_questions(conn)
    # the fixture's chair question in Berg's rede is followed by the next part of the same rede
    assert sorted((q["asked"], q["result"], q["by"]) for q in qs) == [
        ("Bundesregierung", "abgelehnt", "AfD"), ("CDU/CSU", "zugelassen", "unklar")]  # fmt: skip


def test_interruptions_and_network(conn):
    ints = debate.interruptions(conn)
    # the Linke Zuruf, the AfD laughter and the AfD Zuruf during Berg's parts; Adler's Gegenruf is a gegenruf
    assert ints["2026-07"]["CDU/CSU"] == [3, 2 * 105 + 2]
    net = debate.network(conn)
    assert net["speeches"] == {"Bundesregierung": 2, "CDU/CSU": 2}  # only parts of at least MIN_CHARS
    assert net["share"]["fraction"] == {("CDU/CSU", "CDU/CSU"): 0.5}
    assert net["share"]["members"] == {("SPD", "CDU/CSU"): 0.5}
    assert net["share"]["zuruf"] == {("Die Linke", "CDU/CSU"): 0.5, ("AfD", "CDU/CSU"): 0.5}
    assert net["months"] == {"2026-07": [2, 1]}  # SPD applause during a CDU/CSU speech crosses the line


def test_themes_loader(tmp_path):
    assert debate.themes(tmp_path / "missing.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert debate.themes(bad) == {}
    ok = tmp_path / "themes.json"
    ok.write_text(json.dumps({"ID1": {"theme_id": 1, "label": "Wohnen"}, "ID2": {"theme_id": 2}, "ID3": 5}))
    assert debate.themes(ok) == {"ID1": {"theme_id": 1, "label": "Wohnen"}}


def test_write(conn, tmp_path, monkeypatch):
    monkeypatch.delenv("LANDSCAPE_THEMES", raising=False)
    assert debate.write(conn, tmp_path) == {"debatte": 1}
    page = (tmp_path / "debatte" / "index.html").read_text()
    assert "Gemessen in Wörtern, da das Protokoll keine Redezeit festhält" in page
    assert 'href="../debatte/index.html"' in page and "<svg" in page
    assert "Nach Thema" not in page


def test_comments_after_the_chair_are_not_the_speakers(conn):
    # the chair announces the next speaker at the end of Berg's rede; the applause welcomes her, not Berg
    conn.executemany(
        "INSERT INTO speech_paragraph VALUES (?,?,?,?,?)",
        [
            ("ID1-5/4", "ID1-5", 4, "chair", "Nächste Rednerin ist für die SPD-Fraktion Anna Adler."),
            ("ID1-5/5", "ID1-5", 5, "comment", "(Beifall bei der SPD – Zuruf von der AfD)"),
        ],
    )
    conn.executemany(
        "INSERT INTO interjection VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("ID1-5/5/1/1", "ID1-5", 5, 1, "beifall", "fraction", "SPD", None, None, None, None, None),
            ("ID1-5/5/2/1", "ID1-5", 5, 2, "zuruf", "fraction", "AfD", None, None, "Na endlich!", None, None),
        ],
    )
    assert ("ID1-5", 5) not in debate.after_speaker(conn) and ("ID1-5", 2) in debate.after_speaker(conn)
    net = debate.network(conn)
    assert ("SPD", "CDU/CSU") not in net["share"]["fraction"]
    assert net["share"]["zuruf"] == {("Die Linke", "CDU/CSU"): 0.5, ("AfD", "CDU/CSU"): 0.5}  # as before
    assert net["skipped"] == 2
    assert debate.interruptions(conn)["2026-07"]["CDU/CSU"][0] == 3  # the Zuruf after the chair is not counted


def test_small_multiples_per_fraction():
    """One card per fraction on one scale, each a filter of the Ordnungsmaßnahmen; the tables behind
    "Als Tabelle"; the list filterable by kind, fraction and week."""
    ms = [{"kind": "Ordnungsruf", "fraction": "SPD", "sitting": "21/88", "date": "2026-07-08", "speech": "ID1",
           "text": "Ich erteile Ihnen einen Ordnungsruf."},
          {"kind": "Rüge", "fraction": "unklar", "sitting": "21/88", "date": "2026-07-08", "speech": "ID1",
           "text": "Ich rüge Sie."}]  # fmt: skip
    qs = [{"asked": "SPD", "result": "zugelassen"}, {"asked": "SPD", "result": "abgelehnt"},
          {"asked": "Bundesregierung", "result": "zugelassen"}]  # fmt: skip
    ints = {"2026-06": {"SPD": [10, 4000], "AfD": [2, 1000]}, "2026-07": {"SPD": [20, 4000], "AfD": [30, 3000]}}
    html = debate.section_order(ms, qs, ints, ["2026-07-08"])
    cards = html.split('class="mults"', 1)[1].split('<p class="note">', 1)[0]
    assert cards.count('class="tg mult"') == 3  # SPD, AfD, Bundesregierung; "unklar" is no card
    assert 'data-f="fraktion" data-v="spd"' in cards and 'data-v="reg"' in cards
    assert "1 Ordnungsruf" in cards and "2 gewünscht: 1 zugelassen · 1 abgelehnt" in cards
    assert 'style="height:50.0%"' in cards and 'style="height:100.0%"' in cards  # one scale: AfD 10 is the top
    assert 'class="gap"' in cards  # AfD in June: too few words
    assert "<th>Ordnungsrufe</th>" in html and "<th>gewünscht</th>" in html  # the tables behind "Als Tabelle"
    assert 'data-fraktion="spd" data-art="ordnungsruf" data-w="2026-W28"' in html and 'class="strip"' in html
