import os

from PIL import Image

from research import photos


def make(raw, rel, size, mode="RGB"):
    path = raw / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30)).save(path)
    return rel


def test_downscale_only_changed_sources(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out" / "fotos"
    sources = {
        "1": make(raw, "bundestag/fotos/a.jpg", (864, 1152)),
        "9": make(raw, "wikidata/fotos/b.png", (600, 400), "RGBA"),  # transparent PNG -> white background
        "7": make(raw, "bundestag/fotos/small.jpg", (120, 160)),  # never enlarged
        "8": "bundestag/fotos/missing.jpg",
    }
    (raw / "bundestag/fotos/broken.jpg").write_bytes(b"not an image")
    sources["6"] = "bundestag/fotos/broken.jpg"

    ids, encoded = photos.write_photos(sources, raw, out)
    assert ids == {"1", "9", "7"} and encoded == 3
    with Image.open(out / "1.jpg") as im:
        assert (im.format, im.size) == ("JPEG", (240, 320))
    with Image.open(out / "9.jpg") as im:
        assert im.size == (240, 160) and im.mode == "RGB"
        assert im.getpixel((5, 5))[1] > 100  # blended with white, not black
    with Image.open(out / "7.jpg") as im:
        assert im.size == (120, 160)

    # a second run with nothing changed decodes nothing
    assert photos.write_photos(sources, raw, out) == ({"1", "9", "7"}, 0)

    # a replaced source is made again; a person who is gone loses the photo
    src = raw / sources["1"]
    make(raw, sources["1"], (300, 300))
    os.utime(src, ns=(src.stat().st_atime_ns, src.stat().st_mtime_ns + 10**9))
    del sources["7"]
    ids, encoded = photos.write_photos(sources, raw, out)
    assert (ids, encoded) == ({"1", "9"}, 1)
    assert not (out / "7.jpg").exists()
    with Image.open(out / "1.jpg") as im:
        assert im.size == (240, 240)

    # an output removed by hand is made again even though the manifest knows the source
    (out / "9.jpg").unlink()
    assert photos.write_photos(sources, raw, out)[1] == 1


def test_raw_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("BDF_RAW", raising=False)
    monkeypatch.setenv("BDF_DB", str(tmp_path / "foundation" / "bundestag.sqlite"))
    assert photos.raw_dir() == tmp_path / "foundation" / "raw"
    monkeypatch.setenv("BDF_RAW", "/elsewhere")
    assert str(photos.raw_dir()) == "/elsewhere"
