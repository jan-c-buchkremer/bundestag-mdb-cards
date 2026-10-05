"""The building blocks every page of the site shares: the header and page shell, dates and numbers in German,
fraction names, colours and links, the result badge, and the entity page template (a header, then facets). Page
modules and the fact components (facts.py) import from here, so neither has to import the other."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
from pathlib import Path

from research.data import NO_FRACTION

HERE = Path(__file__).parent
# Where the Themenlandschaft is published; links into it are absolute, since the cards may be published elsewhere
LANDSCAPE = os.environ.get("LANDSCAPE_URL", "https://plenar-radar.de/themenlandschaft/")
LANDSCAPE = LANDSCAPE.rstrip("/") + "/"
# Where the cards themselves are published: the footer's Impressum and Datenschutz links are absolute, so the same
# constant works on every page whatever its depth
RESEARCH = os.environ.get("RESEARCH_URL", "https://plenar-radar.de/").rstrip("/") + "/"
LEGAL = f'<a href="{RESEARCH}impressum.html">Impressum</a> · <a href="{RESEARCH}datenschutz.html">Datenschutz</a>'
MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember")  # fmt: skip
WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
VOTE = {"yes": "Ja", "no": "Nein", "abstain": "Enthaltung", "absent": "nicht abgegeben", "invalid": "ungültig"}
POSITION = {"yes": "dafür", "no": "dagegen", "abstain": "Enthaltung"}
ORDER = ("AfD", "CDU/CSU", "BÜNDNIS 90/DIE GRÜNEN", "SPD", "Die Linke", NO_FRACTION)  # as parliament.js
SHORT = {"BÜNDNIS 90/DIE GRÜNEN": "Grüne"}
TOKEN = {"CDU/CSU": "cdu", "SPD": "spd", "AfD": "afd", "BÜNDNIS 90/DIE GRÜNEN": "gru", "Die Linke": "lin",
         NO_FRACTION: "frl"}  # fmt: skip
# The top bar (docs/plan.md 12.1, D26): a search field at the left end, then the sections in this order. The site's
# name sits in the centre column of a three-column grid, so it stays centred whatever the widths of the two sides; it
# leads to the front page (landing.py) and says which part of the site the reader is in: Recherche or Radar
# (docs/architecture.md, "Telling Radar apart"). Debattenkultur is a statistics page, quieter than the research items;
# Daten is the last research item, the Radar entry closes the bar in the Radar colour.
NAV_LEFT = (
    ("cards", "abgeordnete.html", "Abgeordnete"),
    ("places", "orte/index.html", "Orte"),
    ("bodies", "gremien/index.html", "Gremien"),
)
NAV_RIGHT = (
    ("bills", "vorgaenge/index.html", "Vorgänge"),
    ("sittings", "sitzungen/index.html", "Sitzungen"),
    ("questions", "regierung/index.html", "Fragen"),
    ("debate", "debatte/index.html", "Debattenkultur"),
    ("data", "daten.html", "Daten"),
)
NAV = (*NAV_LEFT, *NAV_RIGHT)
QUIET = {"debate"}  # informative statistics, not a research tool
# the sub-tabs of Sitzungen (D27): every vote belongs to a sitting, so Abstimmungen is a view of the time hierarchy
SITTING_TABS = (
    ("calendar", "sitzungen/index.html", "Sitzungswochen"),
    ("votes", "abstimmungen/index.html", "Abstimmungen"),
)
# The Radar mark: rings and a sweep, drawn in currentColor; every Radar element carries it (cards.css .rl, .rmark)
RADAR_ICON = (
    '<svg class="ri" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="8" cy="8" r="6.5" '
    'fill="none" stroke="currentColor" stroke-width="1.3" opacity=".45"/><circle cx="8" cy="8" r="3.5" fill="none" '
    'stroke="currentColor" stroke-width="1.3" opacity=".7"/><path d="M8 8 12.6 3.4" stroke="currentColor" '
    'stroke-width="1.6" stroke-linecap="round"/><circle cx="8" cy="8" r="1.4" fill="currentColor"/></svg>'
)
# The site's mark: a hemicycle of seats, the colours of the two parts meeting in it
LOGO = (
    '<svg class="logo" viewBox="0 0 28 16" width="28" height="16" aria-hidden="true">'
    '<path d="M3 15a11 11 0 0 1 11-11" fill="none" stroke="var(--research)" stroke-width="2.6" stroke-linecap="round" '
    'stroke-dasharray="0 4.6"/><path d="M14 4a11 11 0 0 1 11 11" fill="none" stroke="var(--radar)" '
    'stroke-width="2.6" stroke-linecap="round" stroke-dasharray="0 4.6"/>'
    '<path d="M8 15a6 6 0 0 1 12 0" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" '
    'stroke-dasharray="0 4.4" opacity=".55"/></svg>'
)
FOOTER = (
    "Daten: Deutscher Bundestag (Plenarprotokolle, namentliche Abstimmungen), Deutscher Bundestag/Bundesrat – DIP, "
    'gesammelt mit <a href="https://github.com/jan-c-buchkremer/bundestag-data-foundation">bundestag-data-foundation'
    "</a>. Beschlüsse per Handzeichen sind regelbasiert aus dem Text der Sitzungsleitung gelesen. Code: "
    '<a href="https://github.com/jan-c-buchkremer/bundestag-research-platform">bundestag-research-platform</a> '
    f'(MIT). Die Themen der Debatten zeigt die <a class="rl" href="{LANDSCAPE}">Themenlandschaft</a>. {LEGAL}'
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


def site_header(root: str, active: str | None, mode: str = "research") -> str:
    """The header of every page; `root` is the way back to the site root ("" or "../"). `mode` is the part of the site
    the page belongs to: "research", "radar", or "home" for the front page, which belongs to both. The search field
    submits to suche.html?q=…; nav.js adds the suggestions from the entity index and the phone's search icon."""

    def link(key: str, href: str, label: str, cls: str = "") -> str:
        on = key == active
        classes = " ".join(x for x in (cls, "quiet" if key in QUIET else "", "on" if on else "") if x)
        return (f'<a href="{root}{href}" data-nav="{key}"{f' class="{classes}"' if classes else ""}'
                f'{' aria-current="page"' if on else ""}>{label}</a>')  # fmt: skip

    search = (
        f'<form class="nav-q" role="search" action="{root}suche.html" data-root="{root}">'
        '<button type="button" class="nav-qi" aria-label="Suche öffnen" aria-expanded="false">'
        '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="none" '
        'stroke="currentColor" stroke-width="1.6"/><path d="M11 11l3.5 3.5" stroke="currentColor" stroke-width="1.6" '
        'stroke-linecap="round"/></svg></button>'
        '<input type="search" name="q" placeholder="Suche" autocomplete="off" '
        'aria-label="Suche: Person, Ort, Vorgang …">'
        '<div class="nav-sug" hidden></div></form>'
    )
    left = "".join(link(*x) for x in NAV_LEFT)
    right = "".join(link(*x) for x in NAV_RIGHT)
    on = active == "radar"
    radar = (f'<a href="{LANDSCAPE}" data-nav="radar" class="to-radar{" on" if on else ""}"'
             f'{' aria-current="page"' if on else ""}>{RADAR_ICON}Radar</a>')  # fmt: skip
    tag = {"research": '<span class="mode">Recherche</span>',
           "radar": f'<span class="mode">{RADAR_ICON}Radar</span>'}.get(mode, "")  # fmt: skip
    on = " on" if active == "home" else ""
    home = (f'<a href="{root}index.html" class="home brand{on}" aria-label="plenar-radar.de, Startseite">{LOGO}'
            f'<span class="wm">plenar<b>radar</b></span>{tag}</a>')  # fmt: skip
    return (
        f'<header class="m-{mode}"><nav class="site" aria-label="Bereiche"><div class="nav-l">{search}{left}</div>'
        f'<div class="nav-c">{home}</div><div class="nav-r">{right}{radar}</div></nav>'
        f'<script src="{root}nav.js" defer></script></header>'
    )


def radar_link(href: str, label: str, title: str = "") -> str:
    """A link to a Radar result inside a Research page: the Radar colour and mark, never a plain blue link
    (docs/architecture.md, "Telling Radar apart")."""
    t = f' title="{e(title)}"' if title else ""
    return f'<a class="rl" href="{e(href)}"{t}>{e(label)}</a>'


def method_note(text: str) -> str:
    """The footer note of a Radar page: in two or three sentences, how its results were made and what they can and
    cannot tell (docs/architecture.md)."""
    return (
        f'<aside class="radar-note"><span class="rmark">{RADAR_ICON}So entsteht diese Seite</span><p>{text}</p></aside>'
    )


def subtabs(root: str, tabs: tuple[tuple[str, str, str], ...], active: str) -> str:
    """Sub-tabs of a section (Sitzungswochen | Abstimmungen), styled as the card's tabs."""
    links = "".join(
        f'<a href="{root}{href}"{' class="on" aria-current="page"' if key == active else ""}>{label}</a>'
        for key, href, label in tabs
    )
    return f'<nav class="tabs sub" aria-label="Ansichten"><div class="tabs-in">{links}</div></nav>'


def shell(
    *,
    root: str,
    kind: str,
    active: str | None,
    title: str,
    desc: str,
    body: str,
    data: object,
    head: str = "",
    mode: str = "research",
) -> str:
    """A page of the site in the shared shell; `mode` "radar" gives it the Radar colour and header (site_header)."""
    return (
        (HERE / "page.html")
        .read_text(encoding="utf-8")
        .replace("__TITLE__", e(title))
        .replace("__DESC__", e(desc))
        .replace("__HEAD__", head)
        .replace("__KIND__", f"{kind} mode-{mode}")
        .replace("__HEADER__", site_header(root, active, mode))
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
