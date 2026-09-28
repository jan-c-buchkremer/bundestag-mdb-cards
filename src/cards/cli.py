"""cards build [--out data/out]"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from cards import build, data


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="cards")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build every card page, the index and the JSON exports")
    b.add_argument("--out", type=Path, default=Path("data/out"))
    args = p.parse_args(argv)

    conn = data.connect()
    cards, meta = data.cards(conn)
    kinds = Counter(c["kind"] for c in cards)
    print(f"{kinds['member']} member cards, {kinds['speaker']} speaker cards; {meta['votes']} roll-call votes")
    wks = data.constituencies(conn)
    if not wks:
        print("no election tables in the store: cards without vote shares and list positions")
    gov = data.government(conn)
    if not gov:
        print("no government_role table in the store: no Regierungsbank, no Regierung filter")
    decided = data.decisions(conn)
    if not decided:
        print("no decision table in the store: sitting pages without decisions, no vote pages")
    written = build.write_site(
        cards, meta, args.out, wks, gov, data.last_sitting(conn),
        decided, data.roll_call_members(conn), data.sittings(conn, decided),
    )  # fmt: skip
    print(f"wrote {len(cards)} card pages, " + ", ".join(f"{v} pages in {k}/" for k, v in written.items()))


if __name__ == "__main__":
    main()
