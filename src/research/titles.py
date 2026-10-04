"""Label-sized agenda item titles. Copied from bundestag-topic-landscape (`landscape.corpus.short_title`) so a
speech carries the same title on its card and on the map; change both together."""

from __future__ import annotations

import re

EINZELPLAN = {
    "1": "Bundespräsident", "2": "Bundestag", "3": "Bundesrat", "4": "Bundeskanzler", "5": "Auswärtiges Amt",
    "6": "Inneres", "7": "Justiz", "8": "Finanzen", "9": "Wirtschaft und Energie", "10": "Landwirtschaft",
    "11": "Arbeit und Soziales", "12": "Verkehr", "14": "Verteidigung", "15": "Gesundheit", "16": "Umwelt",
    "17": "Bildung, Familie", "19": "Bundesverfassungsgericht", "20": "Bundesrechnungshof",
    "23": "Entwicklung", "24": "Digitales", "25": "Wohnen, Bau", "30": "Forschung", "32": "Bundesschuld",
    "60": "Allgemeine Finanzverwaltung",
}  # fmt: skip

_PROCEDURAL = re.compile(
    r"^((\d+|[a-z]\)|–|ZP\s*\d+)\s*)*"
    r"(Erste|Zweite|Dritte|Beratung|Abgabe|auf Verlangen|Aktuelle Stunde|Wahlvorschl|Vereinbarte Debatte:|"
    r"Beschlussempfehlung|Bericht des|Antrag der|zu dem Antrag|zu der|\(Schluss)",
)
_GESETZ = re.compile(r"^.*?Entwurfs eines (\w+ )?Gesetzes ")
# where the next sub-item of a combined agenda item starts: "b) …", "25 b) …", "ZP 3 …", "2 Erste Beratung …"
_SUB_ITEM = re.compile(r"^((\d+\s*)?[b-z]\)|ZP\s*\d+|\d+\s)")


def short_title(title: str | None, top_id: str) -> str:
    """A label-sized title: the first non-procedural segment of the first sub-item, or the law's name.

    Only the first sub-item counts: in "a) Entwurf eines Gesetzes … | b) Beratung des Antrags … | <Antrag title>"
    the item is about the law, not the motion debated with it."""
    if not title:
        if top_id.startswith("Einzelplan"):
            num = top_id.removeprefix("Einzelplan").strip().lstrip("0")
            return f"Haushalt: {EINZELPLAN.get(num, top_id)}" if num else "Haushalt"
        return top_id
    segments = [s.strip() for s in title.split("|") if not s.strip().startswith("(Schluss")]
    if not segments:
        return top_id
    first = next((i for i, s in enumerate(segments) if i and _SUB_ITEM.match(s) and _PROCEDURAL.match(s)),
                 len(segments))  # fmt: skip
    for s in segments[:first]:
        if not _PROCEDURAL.match(s):
            return s
    s = _GESETZ.sub("", segments[0])
    return s[0].upper() + s[1:]
