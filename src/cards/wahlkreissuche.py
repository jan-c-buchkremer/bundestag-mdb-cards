"""The Gemeinden of the Wahlkreise, from the foundation's `constituency_municipality` (None when that table does not
exist yet or is empty, e.g. an older store), for the place index (places.py `place_index`, `orte/orte.json`) and the
entity search (search.py).

Per Gemeinde: its Wahlkreis, or several for the 18 Gemeinden the Bundeswahlleiterin's file splits across
Wahlkreise (the file names only a running Gemeindeteil number, not which streets belong where — a finer lookup
needs another source, see docs/decisions.md). The former lookup page `wahlkreise/suche.html` is the place search
of the Orte page now (D25); places.py writes its stub. No postcodes this round: they cannot be mapped to a Gemeinde
without a further source (OpenPLZ, docs/plan.md 11.8)."""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from cards.data import ELECTION, has_table


def municipalities(conn: sqlite3.Connection) -> list[dict] | None:
    """Compact Gemeinde -> Wahlkreis(e) index, one entry per (name, Kreis, Land); a split Gemeinde carries
    several Wahlkreis numbers. None when the foundation has not filled `constituency_municipality` yet (the table
    exists in every store, empty until the Wahlkreiseinteilung was fetched)."""
    if not has_table(conn, "constituency_municipality"):
        return None
    grouped: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for r in conn.execute(
        "SELECT name, district, state, constituency_number FROM constituency_municipality "
        "WHERE election = ? ORDER BY name COLLATE NOCASE",
        (ELECTION,),
    ):
        grouped[(r["name"], r["district"], r["state"])].append(r["constituency_number"])
    if not grouped:
        return None
    return [
        {"n": name, "d": district, "s": state, "w": sorted(set(numbers))}
        for (name, district, state), numbers in grouped.items()
    ]
