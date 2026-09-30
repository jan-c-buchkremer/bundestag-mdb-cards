from cards import bodies, careers, data


def test_load_bodies(conn):
    cards, _ = data.cards(conn)
    bs = bodies.load_bodies(conn, cards)
    by_name = {b["name"]: b for b in bs}
    assert "Ausschuss für Gesundheit" in by_name and "Haushaltsausschuss" in by_name
    # "Präsidium" and "Ältestenrat" (kind other) are kept; ministries (BMI) are not excluded in this fixture,
    # since the test data uses the abbreviation "BMI", not a "Bundesministerium …" name
    assert "Präsidium" in by_name and "Ältestenrat" in by_name and "BMI" in by_name
    gesundheit = by_name["Ausschuss für Gesundheit"]
    assert gesundheit["short"] == "Gesundheit" and gesundheit["slug"] == "gesundheit"
    assert [m["name"] for m in gesundheit["members"]] == ["Anna Adler"]
    assert gesundheit["members"][0]["role"] == "Obfrau"


def test_role_group():
    assert bodies.role_group("Vorsitzender") == 0
    assert bodies.role_group("Stellvertretende Vorsitzende") == 1
    assert bodies.role_group("Obfrau") == 2
    assert bodies.role_group("Ordentliches Mitglied") == 3
    assert bodies.role_group(None) == 3
    assert bodies.role_group("Stellvertretendes Mitglied") == 4
    assert bodies.role_group("Parlamentarischer Staatssekretär") == 5


def test_write(conn, tmp_path):
    cards, _ = data.cards(conn)
    careers.annotate(conn, cards)
    government = data.government(conn)
    decided = data.decisions(conn)
    rcm = data.roll_call_members(conn)
    counts = bodies.write(conn, tmp_path, cards, government, decided, rcm)
    # all six fractions are written (the Gremien index links them), though the fixture has only three
    assert counts["gremien"] > 1 and counts["fraktionen"] == 6
    assert (tmp_path / "fraktionen" / "afd.html").exists()

    index = (tmp_path / "gremien" / "index.html").read_text()
    assert 'href="gesundheit.html"' in index
    assert 'href="../fraktionen/spd.html"' in index

    gesundheit = (tmp_path / "gremien" / "gesundheit.html").read_text()
    assert 'href="../1.html"' in gesundheit and "Obfrau" in gesundheit

    spd = (tmp_path / "fraktionen" / "spd.html").read_text()
    assert 'href="../1.html"' in spd  # Anna Adler is SPD
    assert "Geschlossenheit" in spd
    for key in ("mitglieder", "reden", "abstimmungen", "drucksachen"):  # the facets of every group page
        assert f'<section class="facet" id="{key}">' in spd
    assert "seit 25.03.2025" in spd  # members with dates
    assert "21/100" in spd.split('id="drucksachen"', 1)[1]  # "Fraktion SPD" is the Urheber of Drs. 21/100
    assert 'href="../reden/ID11.html' not in spd  # a question in the Befragung is no Rede of the fraction

    gov = (tmp_path / "gremien" / "bundesregierung.html").read_text()
    assert 'href="../9.html">Stefanie Hubig</a>' in gov and "Bundesministerin der Justiz" in gov
    assert "Beamtin" not in gov and "stimmt im Bundestag nicht ab" in gov
    assert 'href="bundesregierung.html"' in index

    frl = (tmp_path / "fraktionen" / "frl.html").read_text()
    assert "fraktionslos" in frl.lower() or "Aktuell keine Mitglieder" in frl


def test_write_without_decisions(conn, tmp_path):
    cards, _ = data.cards(conn)
    careers.annotate(conn, cards)
    counts = bodies.write(conn, tmp_path, cards, [], [], {})
    assert counts["gremien"] > 1
    spd = (tmp_path / "fraktionen" / "spd.html").read_text()
    assert "Keine namentlichen Abstimmungen" in spd
