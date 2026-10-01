import json

import pytest

from cards import debate


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
    assert debate.speaker_group("Bundesministerin der Justiz", None) == "Bundesregierung"
    assert debate.speaker_group("Bundeskanzler", "CDU/CSU") == "Bundesregierung"  # counted apart from fractions
    assert debate.speaker_group(None, "SPD") == "SPD"
    assert debate.speaker_group("Ministerpräsidentin (Mecklenburg-Vorpommern)", None) == "Sonstige"
    assert debate.speaker_group("Vizepräsidentin", None) is None


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
    assert "Gemessen in Wörtern, nicht in Redezeit" in page
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
