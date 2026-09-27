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


def short_title(title: str | None, top_id: str) -> str:
    """A label-sized title: the first non-procedural segment, or the law's name."""
    if not title:
        if top_id.startswith("Einzelplan"):
            num = top_id.removeprefix("Einzelplan").strip().lstrip("0")
            return f"Haushalt: {EINZELPLAN.get(num, top_id)}" if num else "Haushalt"
        return top_id
    segments = [s.strip() for s in title.split("|") if not s.strip().startswith("(Schluss")]
    if not segments:
        return top_id
    for s in segments:
        if not _PROCEDURAL.match(s):
            return s
    s = _GESETZ.sub("", segments[0])
    return s[0].upper() + s[1:]
