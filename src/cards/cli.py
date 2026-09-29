"""cards build [--out data/out]"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

from cards import (
    bills,
    build,
    careers,
    data,
    debate,
    photos,
    questions,
    search,
    sources,
    speeches,
    wahlkreissuche,
    weekly,
)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="cards")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build every card page, the index and the JSON exports")
    b.add_argument("--out", type=Path, default=Path("data/out"))
    args = p.parse_args(argv)

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
    has_gemeinden = data.has_table(conn, "constituency_municipality")
    write_photos(conn, cards, args.out / "fotos")
    careers.annotate(conn, cards)
    sittings = data.sittings(conn, decided)
    written = build.write_site(
        cards, meta, args.out, wks, gov, data.last_sitting(conn),
        decided, data.roll_call_members(conn), sittings, clusters,
        gemeinde_search=has_gemeinden,
    )  # fmt: skip
    written |= questions.write(conn, args.out) | sources.write(conn, args.out, meta)
    written |= debate.write(conn, args.out)
    written |= careers.write(conn, args.out)
    if has_gemeinden:
        written |= wahlkreissuche.write(conn, args.out, cards, wks)
    else:
        print("no constituency_municipality table in the store: no wahlkreise/suche.html")
    print(
        f"wrote {len(cards)} card pages, "
        + ", ".join(f"{v} pages in {k}/" if k != "kompass" else "kompass.html" for k, v in written.items())
    )
    similar = speeches.neighbours()
    n_speeches = speeches.write_pages(args.out, speeches.load(conn), {c["id"] for c in cards}, clusters, similar)
    print(f"wrote {n_speeches} speech pages in reden/" + (f", {len(similar)} with similar speeches" if similar else ""))
    n_bills = bills.write(conn, args.out).get("gesetze", 0)
    print(f"wrote {n_bills} pages in gesetze/" if n_bills else "no Gesetzgebung in the store: no gesetze/ pages")
    print(f"wrote {weekly.write(conn, args.out, sittings, decided, clusters).get('woche', 0)} pages in woche/")
    search.write_index(args.out)  # last: indexes everything written above


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
