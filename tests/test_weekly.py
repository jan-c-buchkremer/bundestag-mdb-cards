from xml.etree import ElementTree as ET

from research import data, weekly


def sitting(sid, number, date, items=()):
    return {"id": sid, "page": sid.replace("/", "-"), "number": number, "date": date, "week": data.iso_week(date),
            "items": list(items)}  # fmt: skip


def item(position, segments, speeches=()):
    return {"position": position, "title": segments[-1], "segments": segments,
            "speeches": [{"id": s} for s in speeches]}  # fmt: skip


def test_group_by_week():
    ss = [sitting("21/3", 3, "2026-07-09"), sitting("21/1", 1, "2026-06-30"), sitting("21/2", 2, "2026-07-08")]
    got = weekly.group(ss)
    assert list(got) == ["2026-W28", "2026-W27"]  # newest week first
    assert [s["number"] for s in got["2026-W28"]] == [2, 3]
    assert weekly.week_span("2026-W28") == ("2026-07-06", "2026-07-12")
    assert weekly.week_label("2026-W07") == "Sitzungswoche 7/2026"


def test_current_hours():
    s = sitting("21/2", 2, "2026-07-08", [
        item(3, ["Aktuelle Stunde", "auf Verlangen der Fraktion der AfD", "Messerangriffe", "(Schluss: 15:01 Uhr)"]),
        item(4, ["Tagesordnungspunkt 4", "Mietrecht"]),
    ])  # fmt: skip
    (h,) = weekly.current_hours([s])
    assert (h["by"], h["topic"], h["position"]) == ("auf Verlangen der Fraktion der AfD", "Messerangriffe", 3)


def test_sentences():
    s1 = sitting("21/2", 2, "2026-07-08", [item(1, ["TOP 1", "Mietrecht"], ["ID1", "ID2", "ID3"])])
    s2 = sitting("21/3", 3, "2026-07-09", [
        item(2, ["Aktuelle Stunde", "auf Verlangen der Fraktion Die Linke", "Gaza"])])  # fmt: skip
    decided = [
        {"sitting": "21/2", "result": "angenommen", "kind": "handzeichen", "date": "2026-07-08", "order": 1},
        {"sitting": "21/2", "result": "abgelehnt", "kind": "namentlich", "date": "2026-07-08", "order": 2,
         "page": "21-2-1", "title": "Mietpreisbremse", "counts": {"yes": 200, "no": 400, "abstain": 3, "absent": 27}},
        {"sitting": "21/9", "result": "angenommen", "kind": "handzeichen", "date": "2026-09-01", "order": 1},
    ]  # fmt: skip
    measures = [{"kind": "Ordnungsruf", "fraction": "AfD", "sitting": "21/3", "date": "2026-07-09"}]
    steps = [{"vorgang": "g1", "title": "Mietrechtsgesetz", "date": "2026-07-09", "position": "2. Beratung",
              "chamber": "BT"}]  # fmt: skip
    w = weekly.gather([s1, s2], decided, measures, steps)
    got = dict(weekly.sentences(w, "../", have=set()))
    assert "Der Bundestag hat in dieser Woche an zwei Tagen getagt:" in got["Sitzungen"]
    assert 'href="../sitzungen/21-2.html">2. Sitzung</a> am Mittwoch, 8. Juli 2026' in got["Sitzungen"]
    assert "3 Reden zu 2 Tagesordnungspunkten" in got["Sitzungen"]
    assert "Worüber debattiert wurde" not in got  # the landscape's week page shows the topics (D18)
    assert "2 Beschlüsse gefasst: 1 angenommen, 1 abgelehnt." in got["Beschlüsse"]
    assert "Eine Abstimmung war namentlich" in got["Beschlüsse"]
    assert "../abstimmungen/21-2-1.html" in got["Beschlüsse"] and "<b>200</b> Ja · <b>400</b> Nein" in got["Beschlüsse"]
    assert "Es gab eine Aktuelle Stunde" in got["Aktuelle Stunden"] and "#top-2" in got["Aktuelle Stunden"]
    assert "(auf Verlangen der Fraktion Die Linke)" in got["Aktuelle Stunden"]
    assert "1 Ordnungsruf erteilt" in got["Ordnungsmaßnahmen"] and "an AfD" in got["Ordnungsmaßnahmen"]
    assert "Ein Gesetzesvorhaben hatte" in got["Gesetzgebung"]
    assert "vorgaenge/g1" not in got["Gesetzgebung"]  # no page written for g1
    assert "vorgaenge/g1.html" in dict(weekly.sentences(w, "../", have={"g1"}))["Gesetzgebung"]

    empty = dict(weekly.sentences(weekly.gather([sitting("21/5", 5, "2026-09-10")], [], [], []), "../"))
    assert "an einem Tag getagt" in empty["Sitzungen"] and "0 Reden" in empty["Sitzungen"]
    assert "Worüber debattiert wurde" not in empty and "Gesetzgebung" not in empty
    assert "keine Beschlüsse" in empty["Beschlüsse"] and "kein Ordnungsruf" in empty["Ordnungsmaßnahmen"]


def test_feed_is_valid_atom():
    weeks = {wk: weekly.gather(ss, [], [], []) for wk, ss in weekly.group(
        [sitting("21/2", 2, "2026-07-08"), sitting("21/1", 1, "2026-06-30")]).items()}  # fmt: skip
    root = ET.fromstring(weekly.feed(weeks).encode("utf-8"))
    ns = {"a": weekly.ATOM}
    assert root.tag == f"{{{weekly.ATOM}}}feed"
    assert root.find("a:updated", ns).text == "2026-07-08T00:00:00Z"
    entries = root.findall("a:entry", ns)
    assert [x.find("a:title", ns).text for x in entries] == ["Sitzungswoche 28/2026", "Sitzungswoche 27/2026"]
    link = entries[0].find("a:link", ns).get("href")
    assert link == "https://plenar-radar.de/woche/2026-W28.html"
    content = entries[0].find("a:content", ns)
    assert content.get("type") == "html"
    assert 'href="https://plenar-radar.de/sitzungen/21-2.html"' in content.text


def test_write(conn, tmp_path):
    conn.execute(
        "INSERT INTO agenda_item VALUES ('21/88/3','21/88',3,'Aktuelle Stunde','Aktuelle Stunde | auf Verlangen der "
        "Fraktion der AfD | Messerangriffe','[]','u','d','t',0)"
    )
    decided = data.decisions(conn)
    sittings = data.sittings(conn, decided)
    assert weekly.write(conn, tmp_path, sittings, decided) == {"woche": 1}
    page = (tmp_path / "woche" / "2026-W28.html").read_text()
    assert "Sitzungswoche 28/2026" in page and "Messerangriffe" in page and "an einem Tag getagt" in page
    assert 'href="../sitzungen/21-88.html"' in page and 'href="../sitzungen/index.html">21. Wahlperiode</a>' in page
    assert "plenar-radar.de/themenlandschaft/2026-W28.html" in page  # the topic map lives there
    for key in ("sitzungen", "reden", "abstimmungen", "drucksachen"):
        assert f'<section class="facet" id="{key}">' in page
    assert "../sitzungen/index.html" in (tmp_path / "woche" / "index.html").read_text()  # the old index: a stub
    ET.parse(tmp_path / "woche" / "feed.xml")
    assert weekly.write(conn, tmp_path, [], []) == {}
