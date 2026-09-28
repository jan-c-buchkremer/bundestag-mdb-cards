"""Check that every internal href/src in the built site points to a file that exists.

    uv run python scripts/check_links.py data/out [--anchors]

External links (http:, https:, mailto:, protocol-relative) are skipped. With --anchors, a "#id" in a link must
also be an id in the target page. Links that scripts build at runtime (card.js) are not in the HTML and not checked.
Exits 1 when a link is broken, listing the first ones."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

SKIP = re.compile(r"^([a-z][a-z0-9+.-]*:|//)", re.I)


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for k, v in attrs:
            if v is None:
                continue
            if k in ("href", "src"):
                self.links.append(v)
            elif k == "id":
                self.ids.add(v)


def parse(path: Path) -> Links:
    p = Links()
    p.feed(path.read_text(encoding="utf-8", errors="replace"))
    return p


def check(site: Path, anchors: bool = False) -> list[tuple[Path, str]]:
    """The broken links as (page, link)."""
    pages = sorted(site.rglob("*.html"))
    ids: dict[Path, set[str]] = {}
    broken = []
    targets: dict[Path, list[tuple[Path, str, str]]] = defaultdict(list)
    for page in pages:
        parsed = parse(page)
        ids[page.resolve()] = parsed.ids
        for link in parsed.links:
            if not link or SKIP.match(link):
                continue
            parts = urlsplit(link)
            target = (page.parent / unquote(parts.path)).resolve() if parts.path else page.resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                broken.append((page, link))
            elif anchors and parts.fragment and target.suffix == ".html":
                targets[target].append((page, link, unquote(parts.fragment)))
    for target, refs in targets.items():
        known = ids[target] if target in ids else parse(target).ids
        broken += [(page, link) for page, link, frag in refs if frag not in known]
    return broken


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("site", type=Path, nargs="?", default=Path("data/out"))
    ap.add_argument("--anchors", action="store_true", help="also check #fragments against ids in the target page")
    args = ap.parse_args()
    n_pages = sum(1 for _ in args.site.rglob("*.html"))
    broken = check(args.site, args.anchors)
    print(f"{n_pages} pages checked, {len(broken)} broken links")
    for page, link in broken[:50]:
        print(f"  {page.relative_to(args.site)}: {link}")
    sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
