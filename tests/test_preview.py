from cards import preview


def test_live_defaults_fill_only_unset_inputs_that_exist(tmp_path, monkeypatch):
    store = tmp_path / "bundestag.sqlite"
    store.write_text("")
    monkeypatch.setattr(preview, "DEFAULTS", {"BDF_DB": store, "BDF_RAW": tmp_path / "missing"})
    env = {"LANDSCAPE_URL": "http://elsewhere/"}
    applied = preview.live_defaults(env)
    assert env["BDF_DB"] == str(store) and "BDF_RAW" not in env  # a live path that does not exist is left out
    assert env["LANDSCAPE_URL"] == "http://elsewhere/" and "LANDSCAPE_URL" not in applied  # set ones are kept
    assert env["CARDS_URL"] == "https://plenar-radar.de/"
