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
    build.write_site(cards, meta, args.out)
    print(f"wrote {len(cards)} pages to {args.out}")


if __name__ == "__main__":
    main()
