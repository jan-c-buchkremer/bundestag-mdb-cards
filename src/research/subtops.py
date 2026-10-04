"""Sub-TOPs of block agenda items ("TOP 41: 41b … 41s"): loading them and cutting an item's decisions and speeches
along them. The foundation's `agenda_sub_item` (PR bundestag-data-foundation #19) may be missing from a store, and
so may `agenda_item.no_debate`, `decision.sub_item_id` and `speech.sub_item_id`; then every function here returns
what the caller had before and the pages look as they always did. HTML is in subtop_pages.py."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict

from research import data
from research.titles import _GESETZ, _PROCEDURAL, short_title

NO_DEBATE_TITLE = "Abstimmungen ohne Aussprache"
_MOTION_HEAD = re.compile(r"^–\s*zu (dem|der)\b")  # "– zu dem Antrag der Abgeordneten …" leads into the motion's title
_ENTWURF = re.compile(r"Entwurfs eines (.+)$")


def has_item_no_debate(conn: sqlite3.Connection) -> bool:
    return data._has_column(conn, "agenda_item", "no_debate")


def has_speech_sub_item(conn: sqlite3.Connection) -> bool:
    return data._has_column(conn, "speech", "sub_item_id")


def has_decision_sub_item(conn: sqlite3.Connection) -> bool:
    return data._has_column(conn, "decision", "sub_item_id")


def sub_title(title: str | None, label: str) -> str:
    """A short heading for one sub-TOP from its title lines (joined with " | "): the motions' titles after a
    "– zu dem Antrag …" line, else the first line that is more than procedure, else the law's name."""
    segments = [s.strip() for s in (title or "").split("|") if s.strip()]
    motions = [segments[k + 1] for k, s in enumerate(segments[:-1]) if _MOTION_HEAD.match(s)]
    if motions:
        return " · ".join(motions)
    for s in segments:
        if not _PROCEDURAL.match(s) and not s.startswith("Antrag auf "):
            return s
    for s in segments:
        m = _ENTWURF.search(s)
        if m:
            return f"Entwurf eines {m.group(1)}"
    if segments:
        s = _GESETZ.sub("", segments[0])
        return s[:1].upper() + s[1:]
    return label


def item_title(title: str | None, top_id: str, no_debate: bool, has_subs: bool) -> str:
    """The heading of an agenda item: a block of votes without debate is named for what it is, not for the
    first Vorlage in it; everything else keeps the usual short title."""
    if has_subs and no_debate:
        return NO_DEBATE_TITLE
    return short_title(title, top_id)


def load(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Per agenda item id, its sub-items in the order called up; empty without the foundation's table."""
    if not data.has_table(conn, "agenda_sub_item"):
        return {}
    out: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM agenda_sub_item ORDER BY agenda_item_id, position"):
        out[r["agenda_item_id"]].append(
            {
                "id": r["id"], "item": r["agenda_item_id"], "label": r["label"], "position": r["position"],
                "title": sub_title(r["title"], r["label"]),
                "segments": [s.strip() for s in (r["title"] or "").split("|") if s.strip()],
                "numbers": json.loads(r["drucksache_numbers"]), "no_debate": bool(r["no_debate"]),
            }
        )  # fmt: skip
    return dict(out)


def by_id(blocks: dict[str, list[dict]]) -> dict[str, dict]:
    return {s["id"]: s for subs in blocks.values() for s in subs}


def distribute(item: dict) -> None:
    """Sort an item's decisions and speeches into its sub-TOPs (item["sub_items"], each with "decisions" and
    "speeches"). What names no sub-TOP of this item stays with the block: item["block_decisions"] and
    item["block_speeches"]. item["decisions"] and item["speeches"] stay complete, as other pages count them."""
    subs = {s["id"]: s for s in item["sub_items"]}
    for s in subs.values():
        s["decisions"], s["speeches"] = [], []
    item["block_decisions"], item["block_speeches"] = [], []
    for d in item["decisions"]:
        (subs[d["sub"]]["decisions"] if d.get("sub") in subs else item["block_decisions"]).append(d)
    for sp in item["speeches"]:
        (subs[sp["sub_item"]]["speeches"] if sp.get("sub_item") in subs else item["block_speeches"]).append(sp)
