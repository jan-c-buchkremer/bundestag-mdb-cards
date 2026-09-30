"""The building blocks every page of the site shares: the header and page shell, dates and numbers in German,
fraction names, colours and links, the result badge, and the entity page template (a header, then facets). Page
modules and the fact components (facts.py) import from here, so neither has to import the other."""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from cards.data import NO_FRACTION

HERE = Path(__file__).parent
LANDSCAPE = "https://jan-c-buchkremer.github.io/bundestag-topic-landscape/"
MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember")  # fmt: skip
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
VOTE = {"yes": "Ja", "no": "Nein", "abstain": "Enthaltung", "absent": "nicht abgegeben", "invalid": "ungültig"}
POSITION = {"yes": "dafür", "no": "dagegen", "abstain": "Enthaltung"}
ORDER = ("AfD", "CDU/CSU", "BÜNDNIS 90/DIE GRÜNEN", "SPD", "Die Linke", NO_FRACTION)  # as parliament.js
SHORT = {"BÜNDNIS 90/DIE GRÜNEN": "Grüne"}
TOKEN = {"CDU/CSU": "cdu", "SPD": "spd", "AfD": "afd", "BÜNDNIS 90/DIE GRÜNEN": "gru", "Die Linke": "lin",
         NO_FRACTION: "frl"}  # fmt: skip
NAV = (
    ("cards", "index.html", "Abgeordnete"),
    ("places", "orte/index.html", "Orte"),
    ("bodies", "gremien/index.html", "Gremien"),
    ("bills", "vorgaenge/index.html", "Vorgänge"),
    ("votes", "abstimmungen/index.html", "Abstimmungen"),
    ("sittings", "sitzungen/index.html", "Sitzungen"),
    ("questions", "regierung/index.html", "Fragen"),
    ("debate", "debatte/index.html", "Debattenkultur"),
    ("careers", "karrieren/index.html", "Karrieren"),
    ("data", "daten.html", "Daten"),
    ("search", "suche.html", "Suche"),
)
FOOTER = (
    "Daten: Deutscher Bundestag (Plenarprotokolle, namentliche Abstimmungen), Deutscher Bundestag/Bundesrat – DIP, "
    'gesammelt mit <a href="https://github.com/jan-c-buchkremer/bundestag-data-foundation">bundestag-data-foundation'
    "</a>. Beschlüsse per Handzeichen sind regelbasiert aus dem Text der Sitzungsleitung gelesen. Code: "
    '<a href="https://github.com/jan-c-buchkremer/bundestag-mdb-cards">bundestag-mdb-cards</a> (MIT).'
)


def e(s: object) -> str:
    return html.escape("" if s is None else str(s))


def _json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", r"<\/")


def n(x: int) -> str:
    return f"{x:,}".replace(",", ".")


def long_date(d: str, weekday: bool = False) -> str:
    day = dt.date.fromisoformat(d)
    s = f"{day.day}. {MONTHS[day.month - 1]} {day.year}"
    return f"{WEEKDAYS[day.weekday()]}, {s}" if weekday else s


def short_date(d: str) -> str:
    return f"{d[8:10]}.{d[5:7]}.{d[:4]}"


def fraction_order(f: str) -> tuple[int, str]:
    return (ORDER.index(f) if f in ORDER else len(ORDER) - 1, f)


def dot(f: str | None) -> str:
    return f'<span class="dot" style="background:var(--{TOKEN.get(f or "", "reg")})"></span>'


def frac_link(f: str | None, root: str = "../") -> str:
    """A fraction's name, linked to its page (bodies.py) when it is one of the six fractions; plain text (still
    short-named) for anything else, e.g. "unbekannt" or a government/other group."""
    if f in TOKEN:
        return f'<a href="{root}fraktionen/{TOKEN[f]}.html">{e(SHORT.get(f, f))}</a>'
    return e(f or "")


def site_header(root: str, active: str | None) -> str:
    """The header of every page; `root` is the way back to the site root ("" or "../")."""
    links = "".join(
        f'<a href="{root}{href}"{' class="on" aria-current="page"' if key == active else ""}>{label}</a>'
        for key, href, label in NAV
    )
    return (
        f'<header><a class="home" href="{root}index.html">Bundestag <span>21. Wahlperiode</span></a>'
        f'<nav class="site" aria-label="Bereiche">{links}<a class="ext" href="{LANDSCAPE}">Themenlandschaft ↗</a>'
        "</nav></header>"
    )


def shell(*, root: str, kind: str, active: str, title: str, desc: str, body: str, data: object, head: str = "") -> str:
    return (
        (HERE / "page.html")
        .read_text(encoding="utf-8")
        .replace("__TITLE__", e(title))
        .replace("__DESC__", e(desc))
        .replace("__HEAD__", head)
        .replace("__KIND__", kind)
        .replace("__HEADER__", site_header(root, active))
        .replace("__BODY__", body)
        .replace("__DATA__", _json(data))
        .replace("__ROOT__", root)
    )


# ---------------------------------------------------------------- building blocks


def search_marks(kind: str, date: str | None, **filters: str | None) -> str:
    """Hidden Pagefind filters for a page (search.py): its kind, its month and whatever else is given."""
    marks = {"Art": kind, "Monat": f"{MONTHS[int(date[5:7]) - 1]} {date[:4]}" if date else None, **filters}
    return "".join(f'<span hidden data-pagefind-filter="{k}">{e(v)}</span>' for k, v in marks.items() if v)


def badge(result: str | None) -> str:
    if result is None:
        return '<span class="badge none">ohne Ergebnis</span>'
    return f'<span class="badge {e(result)}">{e(result)}</span>'


def kind_label(kind: str) -> str:
    return "namentlich" if kind == "namentlich" else "Handzeichen"


# ---------------------------------------------------------------- the entity page template (docs/plan.md, D12)


def crumbs(*links: tuple[str | None, str]) -> str:
    """The way up the entity hierarchy: (href, label) pairs, the last one usually without a link."""
    parts = [f'<a href="{e(href)}">{e(label)}</a>' if href else f"<span>{e(label)}</span>" for href, label in links]
    return f'<p class="crumbs">{" › ".join(parts)}</p>'


def entity_header(title: str, lines: list[str], links: list[str] | None = None, when: str = "", cls: str = "") -> str:
    """The header of every entity page: what it is (`when`, a small line above), its name, a few lines of facts
    (HTML) and links to the sources."""
    top = f'<div class="when">{when}</div>' if when else ""
    rows = "".join(f"<div>{x}</div>" for x in lines if x)
    more = f'<div class="links">{"".join(links)}</div>' if links else ""
    return (
        f'<section class="card ent-head {cls}">{top}<h1>{e(title)}</h1><div class="lines">{rows}</div>{more}</section>'
    )


def facet(key: str, title: str, body: str, count: int | None = None, explain: str = "") -> str:
    """One facet of an entity page: the same headings in the same order on every page (Mitglieder, Reden,
    Abstimmungen und Beschlüsse, Drucksachen, Erwähnungen), each anchored as #<key>."""
    k = f' <span class="n">{n(count)}</span>' if count is not None else ""
    note = f'<p class="explain">{explain}</p>' if explain else ""
    return f'<section class="facet" id="{e(key)}"><h2>{e(title)}{k}</h2>{note}{body}</section>'
