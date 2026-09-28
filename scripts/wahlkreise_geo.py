"""One-off: Wahlkreis outlines of the Bundestagswahl 2025 as SVG paths for the index map.

    uv run python scripts/wahlkreise_geo.py [--zip btw25_geometrie_wahlkreise_shp.zip] [--tolerance 250]

Reads the generalised shapefile of the Bundeswahlleiterin ("Geometrie der Wahlkreise", UTM32 / EPSG:25832,
generalisiert; downloaded when --zip is not given), simplifies all Wahlkreise together so neighbours keep a shared
border (shapely coverage_simplify), and writes src/cards/wahlkreise.json:

    {"viewBox": "0 0 W H", "source": …, "licence": …, "paths": {"1": "M…z", …}}

Coordinates are kilometres from the north-west corner of the bounding box (y down), one decimal, relative path
commands. Not part of the daily build: Wahlkreise only change with a new Wahlkreiseinteilung. Needs the dev
dependencies pyshp and shapely.

Source: © Die Bundeswahlleiterin, Statistisches Bundesamt, Wiesbaden 2024, Wahlkreiskarte für die Wahl zum
21. Deutschen Bundestag; Grundlage der Geoinformationen © GeoBasis-DE / BKG 2024; Datenlizenz Deutschland –
Namensnennung – Version 2.0 (dl-de/by-2-0).
"""

from __future__ import annotations

import argparse
import io
import json
import urllib.request
import zipfile
from pathlib import Path

import shapefile
import shapely
from shapely.geometry import MultiPolygon, Polygon, shape

URL = (
    "https://www.bundeswahlleiterin.de/dam/jcr/aa735279-6f34-4222-b7e0-2d5192ee29c3/"
    "btw25_geometrie_wahlkreise_shp.zip"
)
PAGE = "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/wahlkreiseinteilung/downloads.html"
LICENCE = "Datenlizenz Deutschland – Namensnennung – Version 2.0 (dl-de/by-2-0)"
ATTRIBUTION = (
    "© Die Bundeswahlleiterin, Statistisches Bundesamt, Wiesbaden 2024, Wahlkreiskarte für die Wahl zum "
    "21. Deutschen Bundestag. Grundlage der Geoinformationen © GeoBasis-DE / BKG 2024"
)
OUT = Path(__file__).resolve().parent.parent / "src" / "cards" / "wahlkreise.json"
MIN_AREA = 0.5  # km²: drop tiny islands and slivers after simplification


def read(zip_bytes: bytes) -> dict[int, shapely.Geometry]:
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    stem = next(n for n in z.namelist() if n.endswith(".shp"))[:-4]
    r = shapefile.Reader(
        shp=io.BytesIO(z.read(stem + ".shp")), dbf=io.BytesIO(z.read(stem + ".dbf")),
        shx=io.BytesIO(z.read(stem + ".shx")), encoding="utf-8",
    )  # fmt: skip
    return {int(rec["WKR_NR"]): shape(s.__geo_interface__) for s, rec in zip(r.shapes(), r.records(), strict=True)}


def ring_path(coords, x0: float, y1: float) -> str:
    """One closed ring in km, y flipped, as `M x y l dx dy … z` on a 0.1 km grid."""
    pts = [(round((x - x0) / 100), round((y1 - y) / 100)) for x, y in coords[:-1]]  # units of 0.1 km
    dedup = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    if len(dedup) < 3:
        return ""
    fmt = lambda v: f"{v / 10:g}"  # noqa: E731
    out = [f"M{fmt(dedup[0][0])} {fmt(dedup[0][1])}l"]
    prev = dedup[0]
    steps = []
    for p in dedup[1:]:
        steps.append(f"{fmt(p[0] - prev[0])} {fmt(p[1] - prev[1])}")
        prev = p
    return out[0] + " ".join(steps).replace(" -", "-") + "z"


def polygons(g: shapely.Geometry) -> list[Polygon]:
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    return [p for part in getattr(g, "geoms", []) for p in polygons(part)]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--zip", type=Path, help="local copy of the shapefile zip (default: download)")
    p.add_argument("--tolerance", type=float, default=250, help="simplification tolerance in metres")
    args = p.parse_args()
    raw = args.zip.read_bytes() if args.zip else urllib.request.urlopen(URL, timeout=60).read()
    geoms = read(raw)
    numbers = sorted(geoms)
    simple = shapely.coverage_simplify([geoms[n] for n in numbers], args.tolerance)
    x0, y0, x1, y1 = shapely.total_bounds(simple)
    paths = {}
    for n, g in zip(numbers, simple, strict=True):
        parts = []
        for poly in polygons(g):
            if poly.area < MIN_AREA * 1e6:
                continue
            for ring in (poly.exterior, *poly.interiors):
                parts.append(ring_path(list(ring.coords), x0, y1))
        paths[str(n)] = "".join(parts)
    out = {
        "viewBox": f"0 0 {round((x1 - x0) / 1000, 1):g} {round((y1 - y0) / 1000, 1):g}",
        "source": PAGE, "file": URL.rsplit("/", 1)[1], "attribution": ATTRIBUTION, "licence": LICENCE,
        "crs": "EPSG:25832, km from the north-west corner, y down", "tolerance_m": args.tolerance,
        "paths": paths,
    }  # fmt: skip
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(paths)} Wahlkreise, {OUT.stat().st_size / 1024:.0f} KB → {OUT}")


if __name__ == "__main__":
    main()
