"""research build [--out data/out] | research preview [--no-build] [--port 8000]"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

from research import (
    bodies,
    build,
    careers,
    data,
    debate,
    landing,
    photos,
    places,
    preview,
    procedures,
    questions,
    search,
    sources,
    speeches,
    topics,
    urls,
    wahlkreissuche,
    weekly,
)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="research")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build every card page, the index and the JSON exports")
    b.add_argument("--out", type=Path, default=Path("data/out"))
    pv = sub.add_parser("preview", help="build from the live data and serve the site on localhost")
    pv.add_argument("--out", type=Path, default=Path("data/out"))
    pv.add_argument("--no-build", action="store_true", help="serve the last build as it is")
    pv.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    if args.cmd == "preview":
        builder = None if args.no_build else (lambda out: main(["build", "--out", str(out)]))
        preview.run(args.out, args.port, builder)
        return

    conn = data.connect()
    cards, meta = data.cards(conn)
    kinds = Counter(c["kind"] for c in cards)
    in_gov = sum(1 for c in cards if c["government"])
    print(
        f"{kinds['member']} member cards, {kinds['speaker']} speaker cards, {in_gov} of them with a government office;"
        f" {meta['votes']} roll-call votes"
    )
    wks = data.constituencies(conn)
    if not wks:
        print("no election tables in the store: cards without vote shares and list positions")
    gov = data.government(conn)
    if not gov:
        print("no government_role table in the store: no Regierungsbank, no Regierung filter")
    decided = data.decisions(conn)
    if not decided:
        print("no decision table in the store: sitting pages without decisions, no vote pages")
    clusters = data.speech_clusters()
    if clusters:
        print(f"{len(clusters)} speeches with a Themenlandschaft cluster: sitting pages with 'Worum ging es'")
    gemeinden = wahlkreissuche.municipalities(conn)  # None: the table is missing or empty in older stores
    write_photos(conn, cards, args.out / "fotos")
    careers.annotate(conn, cards)
    sittings = data.sittings(conn, decided)
    portraits = {c["id"] for c in cards if c["photo"]}  # the photos that were made, not only those in the store
    for s in sittings:
        for i in s["items"]:
            for sp in i["speeches"]:
                sp["photo"] = sp["person"] in portraits
    rcm = data.roll_call_members(conn)
    groups = bodies.load_bodies(conn, cards)
    written = build.write_site(
        cards, meta, args.out, gov, data.last_sitting(conn),
        decided, rcm, sittings, clusters,
        places=places.index_payload(cards, wks), roles=careers.build_section(conn, cards, groups, gov),
    )  # fmt: skip
    written |= questions.write(conn, args.out, {c["id"] for c in cards}) | sources.write(conn, args.out, meta)
    written |= debate.write(conn, args.out)
    written |= careers.write(args.out)
    if gemeinden is None:
        print("no constituency_municipality table in the store: the place search finds Länder and Wahlkreise only")
    print(
        f"wrote {len(cards)} card pages, "
        + ", ".join(f"{v} pages in {k}/" if k != "kompass" else "kompass.html" for k, v in written.items())
    )
    similar = speeches.neighbours()
    themes = debate.themes()
    n_speeches = speeches.write_pages(args.out, speeches.load(conn), {c["id"] for c in cards}, clusters, similar,
                                      themes)  # fmt: skip
    print(f"wrote {n_speeches} speech pages in reden/" + (f", {len(similar)} with similar speeches" if similar else ""))
    procs = procedures.write(conn, args.out, sittings, decided, rcm)
    missing = procedures.missing_debates(procs)
    print(f"{sum(len(x) for x in missing.values())} Beratungen in {len(missing)} sittings without protocol text")
    written |= sources.write(conn, args.out, meta, missing)
    print(f"wrote {len(procs)} pages in vorgaenge/, stubs in gesetze/ and abstimmungen/ for what moved there")
    print(f"wrote {weekly.write(conn, args.out, sittings, decided).get('woche', 0)} pages in woche/")
    written_themes = topics.write(args.out, themes, data.speech_facts(cards), sittings)
    print(f"wrote {len(written_themes)} topic pages in themen/" if written_themes
          else "LANDSCAPE_THEMES not set: no topic pages")  # fmt: skip
    rep = places.write(args.out, cards, wks, careers.constituted(conn), decided, rcm, gemeinden)
    print(f"wrote {len(rep['wahlkreise'])} Wahlkreis pages and {len(data.STATES)} Land pages in orte/")
    n_bodies = bodies.write(conn, args.out, cards, gov, decided, rcm)
    print(f"wrote {n_bodies['gremien']} pages in gremien/, {n_bodies['fraktionen']} pages in fraktionen/")
    landing.write(
        args.out,
        cards,
        meta,
        sittings,
        decided,
        speeches=n_speeches,
        procedures=len(procs),
        themes=len(written_themes),
        compass="kompass" in written,
        landscape=bool(clusters),
    )
    print("wrote the front page index.html, the Abgeordnete list in abgeordnete.html")
    index = search.entities(cards, groups, (args.out / urls.GOVERNMENT).exists(), procs, rep, gemeinden,
                            written_themes, sittings)  # fmt: skip
    print(f"{len(index['items'])} entities in suche.json")
    search.write_index(args.out, index)  # last: indexes everything written above


def write_photos(conn, cards: list[dict], out: Path) -> None:
    """Downscale the portraits of everyone with a card; a card whose photo could not be made shows initials."""
    raw = photos.raw_dir()
    ids = {c["id"] for c in cards}
    sources = {pid: p["path"] for pid, p in data.photos(conn).items() if pid in ids}
    if sources and not raw.is_dir():
        print(f"raw folder {raw} not found (set BDF_RAW): cards without photos")
    start = time.perf_counter()
    have, encoded = photos.write_photos(sources, raw, out)
    for c in cards:
        if c["photo"] and c["id"] not in have:
            c["photo"] = None
    print(f"{len(have)} photos in {out} ({encoded} made, {time.perf_counter() - start:.1f} s)")


if __name__ == "__main__":
    main()
