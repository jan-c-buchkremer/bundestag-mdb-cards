"""Vote and sitting pages: `abstimmungen/` and `sitzungen/`, and the header shared by every page of the site.

These pages are written as HTML by Python (every link is in the file, so scripts/check_links.py can follow it);
`pages.js` adds the seating chart, the filters and nothing else. German UI, see docs/plan.md."""

from __future__ import annotations

import datetime as dt
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

from cards.data import NO_FRACTION, VOTE_CHOICES, majority

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
    ("votes", "abstimmungen/index.html", "Abstimmungen"),
    ("sittings", "sitzungen/index.html", "Sitzungen"),
    ("questions", "regierung/index.html", "Fragen"),
    ("debate", "debatte/index.html", "Debattenkultur"),
    ("bills", "gesetze/index.html", "Gesetze"),
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


def drs_links(refs: list[dict], limit: int | None = None) -> str:
    shown = refs if limit is None else refs[:limit]
    links = ", ".join(f'<a href="{e(r["url"])}" title="{e(r["type"] or "Drucksache")}">{e(r["number"])}</a>'
                      for r in shown)  # fmt: skip
    more = len(refs) - len(shown)
    return links + (f' <span class="faint">und {more} weitere</span>' if more > 0 else "")


def counts_line(c: dict) -> str:
    parts = [f"<b>{n(c['yes'])}</b> Ja", f"<b>{n(c['no'])}</b> Nein", f"<b>{n(c['abstain'])}</b> Enthaltung"]
    parts.append(f"<b>{n(c['absent'])}</b> nicht abgegeben")
    if c.get("invalid"):
        parts.append(f"<b>{n(c['invalid'])}</b> ungültig")
    return " · ".join(parts)


def count_bar(c: dict, cls: str = "bar") -> str:
    """Yes / no / abstain / not cast as one stacked bar."""
    keys = ("yes", "no", "abstain", "absent")
    total = sum(c.get(k, 0) for k in keys) or 1
    tip = ", ".join(f"{VOTE[k]}: {c.get(k, 0)}" for k in keys)
    segs = "".join(f'<i class="v-{k}" style="width:{100 * c.get(k, 0) / total:.2f}%"></i>' for k in keys if c.get(k))
    return f'<span class="{cls}" title="{e(tip)}">{segs}</span>'


def hands_bar(d: dict, cls: str = "bar") -> str:
    """Show of hands: one segment per fraction, as wide as its seats, coloured by its position."""
    house = d["house"] or {}
    total = sum(house.values()) or 1
    pos = d["fractions"] or {}
    segs, tip = [], []
    for f in sorted(house, key=fraction_order):
        p = pos.get(f)
        segs.append(f'<i class="v-{p or "unknown"}" style="width:{100 * house[f] / total:.2f}%"></i>')
        tip.append(f"{SHORT.get(f, f)}: {POSITION.get(p, 'unbekannt')}")
    title = "Nach Fraktionsstärke, keine Stimmenzahlen. " + ", ".join(tip)
    return f'<span class="{cls}" title="{e(title)}">{"".join(segs)}</span>'


def positions_line(pos: dict[str, str]) -> str:
    """ "dafür: CDU/CSU, SPD · dagegen: AfD" from the fractions' positions."""
    groups: dict[str, list[str]] = defaultdict(list)
    for f in sorted(pos, key=fraction_order):
        groups[pos[f]].append(SHORT.get(f, f))
    return " · ".join(f"{POSITION[p]}: <b>{e(', '.join(groups[p]))}</b>" for p in VOTE_CHOICES if groups[p])


def agenda_href(sitting: str, position: int, root: str = "../") -> str:
    return f"{root}sitzungen/{sitting.replace('/', '-')}.html#top-{position}"


# ---------------------------------------------------------------- one vote


def vote_page(d: dict, members: list[list] | None) -> str:
    rc = d["kind"] == "namentlich"
    where = [e(long_date(d["date"]))]
    if d["sitting"]:
        num = d["sitting"].split("/")[1]
        where.append(f'<a href="../sitzungen/{e(d["sitting"].replace("/", "-"))}.html">{e(num)}. Sitzung</a>')
    lines = []
    if d["subject"] and d["subject"] != d["title"]:
        lines.append(f'<div><span class="k">Abgestimmt über</span> {e(d["subject"])}</div>')
    if d["agenda"] and d["sitting"]:
        a = d["agenda"]
        href = agenda_href(d["sitting"], a["position"])
        lines.append(f'<div><span class="k">Tagesordnung</span> <a href="{e(href)}">{e(a["label"])}</a> · '
                     f'{e(a["title"])}</div>')  # fmt: skip
    if d["drucksachen"]:
        lines.append(f'<div><span class="k">Drucksache{"n" if len(d["drucksachen"]) > 1 else ""}</span> '
                     f"{drs_links(d['drucksachen'])}</div>")  # fmt: skip

    if rc:
        kind = '<span class="tag">namentliche Abstimmung</span>'
        c = d["counts"]
        detail = counts_line(c) if c else "Keine Stimmenzahlen: zu dieser Abstimmung fehlt die Abstimmungsliste."
        result = f'<div class="result {e(d["result"] or "none")}">{badge(d["result"])}<span>{detail}</span></div>'
        if c:
            result += count_bar(c, "bar big")
        if d["result_from"] == "counts":
            result += ('<p class="note">Ergebnis aus den Stimmenzahlen der Abstimmungsliste; das Protokoll dieser '
                       "Abstimmung ist noch nicht ausgewertet.</p>")  # fmt: skip
    else:
        kind = '<span class="tag warn">Abstimmung per Handzeichen – nur Fraktionsergebnis</span>'
        pos = d["fractions"] or {}
        detail = positions_line(pos) if pos else "Das Protokoll nennt keine Fraktionen."
        result = f'<div class="result {e(d["result"] or "none")}">{badge(d["result"])}<span>{detail}</span></div>'
    head = f"""<p class="crumbs"><a href="index.html">Abstimmungen</a> › {kind}</p>
<section class="card vote-head">
  <div class="when">{" · ".join(where)}</div>
  <h1>{e(d["title"])}</h1>
  <div class="lines">{"".join(lines)}</div>
  {result}
</section>"""

    parts = [head]
    if rc and members:
        parts.append(
            '<h2>Im Plenum <span class="n">jeder Punkt eine Stimme</span></h2>'
            '<div class="chart"><div id="chart"></div><div class="legend" id="legend"></div>'
            '<label class="toggle"><input type="checkbox" id="dev"> Abweichungen von der Fraktionsmehrheit '
            "hervorheben</label>"
            '<p class="note">Sitze nach Fraktionen wie in der Sitzverteilung; in jeder Fraktion nach Stimme, dann '
            "Name. Ein Schema, nicht die echte Sitzordnung. Punkt antippen oder anklicken öffnet die Karte.</p></div>"
        )
        parts.append(fraction_table_rc(d, members))
    elif rc:
        parts.append('<p class="explain">Zu dieser Abstimmung gibt es keine Abstimmungsliste mit Einzelstimmen '
                     "(im Protokoll verlesen, aber nicht in den Listen des Bundestages).</p>")  # fmt: skip
    else:
        if d["fractions"]:
            parts.append(
                '<h2>Im Plenum <span class="n">nach Fraktion</span></h2>'
                '<div class="chart"><div id="chart"></div><div class="legend" id="legend"></div>'
                '<p class="note">Abstimmung per Handzeichen: Das Protokoll hält nur fest, wie die Fraktionen '
                "gestimmt haben, nicht wer. Von links: AfD, CDU/CSU, Grüne, SPD, Die Linke, fraktionslos. "
                "Jede Fraktion ist deshalb ganz in der Farbe ihrer Position gezeichnet, so groß wie "
                "sie an diesem Tag war (nach der Abstimmungsliste der nächsten namentlichen Abstimmung); einzelne "
                "Abweichungen sieht man nicht.</p></div>"
            )
        else:
            parts.append('<p class="explain">Das Protokoll nennt bei dieser Abstimmung per Handzeichen keine '
                         "Fraktionen („Wer stimmt dafür? – Wer stimmt dagegen? – … angenommen“), nur das "
                         "Ergebnis.</p>")  # fmt: skip
        parts.append(fraction_table_hands(d))
    if d["text"]:
        paras = "".join(f"<p>{e(p)}</p>" for p in d["text"].split("\n\n") if p.strip())
        parts.append(f'<h2>Aus dem Protokoll</h2><blockquote class="chair">{paras}</blockquote>')
    parts.append(f"<h2>Quellen</h2>{vote_sources(d)}")
    parts.append(f"<footer>{FOOTER}</footer>")
    data = {"kind": "vote", "mode": d["kind"], "id": d["id"]}
    if rc and members:
        data["members"] = members
    elif d["fractions"]:
        data["house"] = d["house"]
        data["positions"] = d["fractions"]
    desc = (f"{'Namentliche Abstimmung' if rc else 'Abstimmung per Handzeichen'} im Bundestag am "
            f"{long_date(d['date'])}: {d['title']} – {d['result'] or 'ohne Ergebnis'}.")  # fmt: skip
    head = '<script src="../parliament.js"></script>' if "members" in data or "house" in data else ""
    body = f"<div data-pagefind-body>{search_marks('Abstimmung', d['date'])}{chr(10).join(parts[:-1])}</div>{parts[-1]}"
    return shell(root="../", kind="p-vote", active="votes", title=d["title"][:90], desc=desc, head=head,
                 body=body, data=data)  # fmt: skip


def fraction_table_rc(d: dict, members: list[list]) -> str:
    by_fraction: dict[str, list[list]] = defaultdict(list)
    for m in members:
        by_fraction[m[2]].append(m)
    rows = []
    for f in sorted(by_fraction, key=fraction_order):
        ms = by_fraction[f]
        t = Counter(m[3] for m in ms)
        line = None if f == NO_FRACTION else majority(t)
        dev = [m for m in ms if line and m[3] in VOTE_CHOICES and m[3] != line]
        dev_html = ""
        if dev:
            names = ", ".join(
                (f'<a href="../{e(m[0])}.html">{e(m[1])}</a>' if m[0] else e(m[1])) + f" ({VOTE[m[3]]})"
                for m in sorted(dev, key=lambda m: m[1])
            )
            dev_html = f'<tr class="dev"><td colspan="6">Anders als die Fraktionsmehrheit: {names}</td></tr>'
        rows.append(
            f"<tr><td>{dot(f)} {e(f)}</td>"
            + "".join(f'<td class="num">{t[k]}</td>' for k in ("yes", "no", "abstain", "absent"))
            + f"<td>{count_bar(dict(t), 'bar')}</td></tr>{dev_html}"
        )
    return (
        '<h2>Nach Fraktionen</h2><div class="rows"><table class="plenum"><thead><tr><th>Fraktion</th><th>Ja</th>'
        "<th>Nein</th><th>Enth.</th><th>nicht abg.</th><th></th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
        '<p class="explain">„Nicht abgegeben“ sagt nichts über den Grund: Krankheit, Elternzeit, Dienstreisen und '
        "Pairing-Absprachen stehen nicht in den Listen.</p>"
    )


def fraction_table_hands(d: dict) -> str:
    house = d["house"] or {}
    pos = d["fractions"] or {}
    fractions = sorted(set(house) | set(pos), key=fraction_order)
    if not fractions:
        return ""
    rows = "".join(
        f'<tr><td>{dot(f)} {e(f)}</td><td class="num">{house.get(f, "")}</td>'
        f"<td>{f'<span class="vote {pos[f]}">{POSITION[pos[f]]}</span>' if f in pos else '<span class="faint">nicht genannt</span>'}</td></tr>"  # noqa: E501
        for f in fractions
    )
    return (
        '<h2>Nach Fraktionen</h2><div class="rows"><table class="plenum"><thead><tr><th>Fraktion</th><th>Sitze</th>'
        f"<th>Position</th></tr></thead><tbody>{rows}</tbody></table></div>"
        '<p class="explain">Die Position ist die, die die Sitzungsleitung für die Fraktion festgestellt hat. '
        "„Nicht genannt“: Die Fraktion kommt im Protokolltext zu dieser Abstimmung nicht vor.</p>"
    )


def vote_sources(d: dict) -> str:
    items = []
    s = d.get("sources") or {}
    if s.get("xlsx"):
        items.append(f'<li>Abstimmungsliste {e(s.get("cite"))}: <a href="{e(s["xlsx"])}">XLSX</a>'
                     + (f', <a href="{e(s["pdf"])}">PDF</a>' if s.get("pdf") else "")
                     + ". © Deutscher Bundestag</li>")  # fmt: skip
    if d["protocol"]:
        items.append(f'<li>Plenarprotokoll {e(d["cite"])}: <a href="{e(d["protocol"])}">PDF</a>. '
                     "© Deutscher Bundestag</li>")  # fmt: skip
    for r in d["drucksachen"]:
        items.append(f'<li>Drucksache {e(r["number"])}{f" ({e(r["type"])})" if r["type"] else ""}: '
                     f'<a href="{e(r["url"])}">DIP</a>, <a href="{e(r["pdf"])}">PDF</a></li>')  # fmt: skip
    return f'<ul class="sources">{"".join(items)}</ul>'


# ---------------------------------------------------------------- all votes


def votes_index(decisions: list[dict], meta: dict) -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for d in decisions:
        groups[d["sitting"] or d["date"]].append(d)
    kinds = Counter(d["kind"] for d in decisions)
    results = Counter(d["result"] for d in decisions)
    out = []
    for ds in groups.values():
        first = ds[0]
        if first["sitting"]:
            num = first["sitting"].split("/")[1]
            label = f'<a href="../sitzungen/{e(first["sitting"].replace("/", "-"))}.html">{e(num)}. Sitzung</a>'
        else:
            label = '<span class="faint">Protokoll noch nicht ausgewertet</span>'
        rows = "".join(vote_row(d) for d in sorted(ds, key=lambda d: d["order"]))
        out.append(f'<section class="grp"><h3>{label} · {e(long_date(first["date"], True))}</h3>'
                   f'<div class="rows">{rows}</div></section>')  # fmt: skip
    first_date = min((d["date"] for d in decisions), default=meta["sittings"]["from"])
    body = f"""<h1>Abstimmungen</h1>
<p class="lead">{n(len(decisions))} Beschlüsse seit {e(long_date(first_date))}: {n(kinds["namentlich"])} namentliche Abstimmungen mit der Stimme jedes Mitglieds, {n(kinds["handzeichen"])} Abstimmungen per Handzeichen, bei denen das Protokoll nur festhält, wie die Fraktionen gestimmt haben. {n(results["angenommen"])} angenommen, {n(results["abgelehnt"])} abgelehnt. Überweisungen an Ausschüsse, Wahlen und Fragen der Tagesordnung sind keine Beschlüsse in der Sache und fehlen hier. Wie geschlossen die Fraktionen in den namentlichen Abstimmungen gestimmt haben und wer wann abgewichen ist, zeigt die Seite <a href="geschlossenheit.html">Geschlossenheit der Fraktionen</a>.</p>
<div class="filters">
  <input type="search" id="q" placeholder="Titel, Drucksache oder Tagesordnungspunkt …" autocomplete="off">
  <select id="kind"><option value="">namentlich und per Handzeichen</option><option value="namentlich">nur namentlich</option><option value="handzeichen">nur per Handzeichen</option></select>
  <select id="result"><option value="">angenommen und abgelehnt</option><option value="angenommen">angenommen</option><option value="abgelehnt">abgelehnt</option></select>
</div>
<div class="count" id="count"></div>
<div id="groups">{"".join(out)}</div>
<footer>{FOOTER}</footer>"""  # noqa: E501
    return shell(root="../", kind="p-votes", active="votes", title="Abstimmungen im Bundestag",
                 desc=f"Alle {len(decisions)} Beschlüsse des 21. Deutschen Bundestages, namentlich und per "
                 "Handzeichen, mit Ergebnis und Quelle.", body=body, data={"kind": "votes"})  # fmt: skip


def vote_row(d: dict) -> str:
    bar = count_bar(d["counts"], "mini") if d["counts"] else hands_bar(d, "mini") if d["house"] else ""
    sub = []
    if d["subject"] and d["subject"] != d["title"]:
        sub.append(e(d["subject"]))
    if d["agenda"]:
        sub.append(f"{e(d['agenda']['label'])}")
    if d["drucksachen"]:
        sub.append("Drs. " + ", ".join(e(r["number"]) for r in d["drucksachen"][:3]))
    return (
        f'<a class="row v" href="{e(d["page"])}.html" data-kind="{d["kind"]}" data-result="{e(d["result"] or "")}">'
        f'<span class="t"><span class="ti">{e(d["title"])}</span><span class="sub">{" · ".join(sub)}</span></span>'
        f'<span class="l">{badge(d["result"])}{bar}<span class="k">{kind_label(d["kind"])}</span></span></a>'
    )


# ---------------------------------------------------------------- sittings


SHOWN = 10  # speeches of an agenda item shown before "alle N Reden zeigen"
FACES = 24  # avatars of the hidden speakers under the fade (the row is clipped to the width)
TOPICS = 5  # clusters under "Worum ging es"
# without JavaScript the long speech lists stay open
NOSCRIPT = ("<noscript><style>.sp-list .sp-rest{display:block!important}.sp-list .sp-shown::after,"
            ".sp-bar{display:none!important}</style></noscript>")  # fmt: skip


def sitting_page(s: dict, clusters: dict[str, dict] | None = None) -> str:
    week = f"{LANDSCAPE}{s['week']}.html"
    n_speeches = sum(len(i["speeches"]) for i in s["items"])
    n_dec = sum(len(i["decisions"]) for i in s["items"])
    n_rc = sum(1 for i in s["items"] for d in i["decisions"] if d["kind"] == "namentlich")
    time = f" · {e(s['start'])}–{e(s['end'])} Uhr" if s["start"] and s["end"] else ""
    prev = f'<a href="{e(s["prev"])}.html">← {e(s["prev"].split("-")[1])}. Sitzung</a>' if s["prev"] else ""
    nxt = f'<a class="next" href="{e(s["next"])}.html">{e(s["next"].split("-")[1])}. Sitzung →</a>' if s["next"] else ""
    nav = [prev or "<span></span>", nxt]
    summary = [f"{len(s['items'])} Tagesordnungspunkte", f"{n_speeches} Reden"]
    if n_dec:
        summary.append(f"{n_dec} Beschlüsse" + (f", davon {n_rc} namentlich" if n_rc else ""))
    toc = "".join(
        f'<a href="#top-{i["position"]}"><span class="lbl">{e(i["label"])}</span> {e(i["title"])}</a>'
        for i in s["items"]
    )
    head = f"""<p class="crumbs"><a href="index.html">Sitzungen</a></p>
<section class="card sit-head">
  <div class="when">{e(long_date(s["date"], True))}{time}</div>
  <h1>{s["number"]}. Sitzung des 21. Bundestages</h1>
  <div class="lines">{" · ".join(summary)}</div>
  <div class="links"><a href="{e(s["pdf"])}">Plenarprotokoll {e(s["cite"])} (PDF)</a><a href="{e(week)}">Diese Woche in der Themenlandschaft ↗</a></div>
  <nav class="prevnext">{"".join(nav)}</nav>
</section>
<h2>Tagesordnung</h2>
<nav class="toc">{toc}</nav>"""  # noqa: E501
    items = "".join(agenda_item(i, s, clusters or {}) for i in s["items"])
    body = f"<div data-pagefind-body>{search_marks('Sitzung', s['date'])}{head}{items}</div><footer>{FOOTER}</footer>"
    desc = f"{s['number']}. Sitzung des 21. Deutschen Bundestages am {long_date(s['date'])}: Tagesordnung, Reden und Beschlüsse."  # noqa: E501
    title = f"{s['number']}. Sitzung, {short_date(s['date'])}"
    data = {"kind": "sitting", "id": s["id"]}
    head = NOSCRIPT if any(len(i["speeches"]) > SHOWN for i in s["items"]) else ""
    return shell(root="../", kind="p-sitting", active="sittings", title=title, desc=desc, body=body, data=data,
                 head=head)  # fmt: skip


def agenda_item(i: dict, s: dict, clusters: dict[str, dict] | None = None) -> str:
    parts = [f'<section class="top" id="top-{i["position"]}"><h3><span class="lbl">{e(i["label"])}</span> '
             f'{e(i["title"])}</h3>']  # fmt: skip
    if len(i["segments"]) > 1 or (i["segments"] and i["segments"][0] != i["title"]):
        parts.append('<details class="full"><summary>Vollständiger Titel</summary>'
                     + "".join(f"<p>{e(x)}</p>" for x in i["segments"]) + "</details>")  # fmt: skip
    if i["drucksachen"]:
        parts.append(f'<div class="drs"><span class="k">Drucksachen</span> {drs_links(i["drucksachen"], 8)}</div>')
    if i["decisions"]:
        rows = "".join(
            f'<a class="dec" href="../abstimmungen/{e(d["page"])}.html">{badge(d["result"])}'
            f'<span class="ti">{e(d["title"])}</span><span class="k">{kind_label(d["kind"])}</span></a>'
            for d in i["decisions"]
        )
        parts.append(f'<div class="decs"><div class="k">Beschlüsse</div>{rows}</div>')
    if i["referred"]:
        drs = i["referred"]["drucksachen"]
        parts.append('<div class="ref"><span class="badge ref">überwiesen</span> '
                     + (f"Drucksache{'n' if len(drs) > 1 else ''} {', '.join(e(x) for x in drs)} an die Ausschüsse"
                        if drs else "an die Ausschüsse") + "</div>")  # fmt: skip
    parts.append(topics_block(i, clusters or {}))
    if i["speeches"]:
        parts.append(speeches_block(i, s))
    parts.append("</section>")
    return "".join(parts)


def topics(i: dict, clusters: dict[str, dict]) -> list[dict]:
    """The Themenlandschaft clusters of an agenda item's speeches, the most speeches first."""
    count: Counter = Counter()
    label: dict[tuple, str] = {}
    for sp in i["speeches"]:
        c = clusters.get(sp["id"])
        if c:
            key = (c["week"], c["cluster_id"])
            count[key] += 1
            label.setdefault(key, c["label"])
    ranked = sorted(count.items(), key=lambda kv: (-kv[1], label[kv[0]]))
    return [{"week": w, "cluster_id": cid, "label": label[(w, cid)], "n": k} for (w, cid), k in ranked]


def topics_block(i: dict, clusters: dict[str, dict]) -> str:
    """ "Worum ging es": the item's top clusters in the Themenlandschaft; nothing without the landscape's data."""
    found = topics(i, clusters)
    if not found:
        return ""
    total = len(i["speeches"])
    links = "".join(
        f'<a class="topic" href="{LANDSCAPE}{e(t["week"])}.html#cluster={e(t["cluster_id"])}" '
        f'title="{t["n"]} von {total} Reden zu diesem Punkt in diesem Thema der Themenlandschaft">'
        f'{e(t["label"])} <span class="n">{t["n"]}</span></a>'
        for t in found[:TOPICS]
    )
    more = len(found) - TOPICS
    rest = f'<span class="faint">und {more} weitere</span>' if more > 0 else ""
    return (f'<div class="topics"><div class="k">Worum ging es <span class="n">aus der Themenlandschaft'
            "</span></div>"
            f'<div class="chips">{links}{rest}</div></div>')  # fmt: skip


def speeches_block(i: dict, s: dict) -> str:
    """The item's speeches; beyond SHOWN the list fades out over the faces of the rest and a button opens it
    (pages.js). All rows are in the HTML, so every card link stays in the file."""
    sps = i["speeches"]
    head = f'<div class="k">Reden <span class="n">{len(sps)}</span></div>'
    if len(sps) <= SHOWN:
        return f'<div class="speeches">{head}{"".join(speech_row(sp, s) for sp in sps)}</div>'
    rest = sps[SHOWN:]
    people = list({sp["person"]: sp for sp in rest}.values())
    faces = "".join(
        f'<span class="av" style="--c:var(--{TOKEN.get(sp["fraction"] or "", "reg")})" title="{e(sp["name"])}">'
        f"{avatar(sp)}</span>"
        for sp in people[:FACES]
    )
    rid = f"rest-{i['position']}"
    return (
        f'<div class="speeches sp-list" data-n="{len(sps)}">{head}'
        f'<div class="sp-shown">{"".join(speech_row(sp, s) for sp in sps[:SHOWN])}</div>'
        f'<div class="sp-rest" id="{rid}">{"".join(speech_row(sp, s) for sp in rest)}</div>'
        f'<div class="sp-bar"><span class="sp-faces" aria-hidden="true">{faces}</span>'
        f'<button type="button" class="sp-more" aria-expanded="false" aria-controls="{rid}">alle {len(sps)} Reden '
        "zeigen</button></div></div>"
    )


def avatar(sp: dict) -> str:
    """Initials, covered by the portrait when there is one."""
    initials = "".join(w[0] for w in sp["name"].split()[-2:] if w)
    photo = (f'<img src="../fotos/{e(sp["person"])}.jpg" alt="" loading="lazy" onerror="this.remove()">'
             if sp["photo"] else "")  # fmt: skip
    return f"{e(initials)}{photo}"


def speech_row(sp: dict, s: dict) -> str:
    who = e(sp["role"]) if sp["role"] else e(sp["fraction"] or "")
    land = (f' · <a href="{LANDSCAPE}{e(s["week"])}.html#open={e(sp["id"])}" '
            'title="Diese Rede in der Themenlandschaft">Themenlandschaft ↗</a>' if sp["on_map"] else "")  # fmt: skip
    links = f'<span class="go"><a href="../reden/{e(sp["id"])}.html" title="Der Text dieser Rede">Text</a>{land}</span>'
    return (
        f'<div class="sp"><span class="av" style="--c:var(--{TOKEN.get(sp["fraction"] or "", "reg")})">'
        f"{avatar(sp)}</span>"
        f'<span class="who"><a href="../{e(sp["person"])}.html">{e(sp["name"])}</a> '
        f'<span class="sub">{who} · {n(sp["words"])} Wörter</span></span>{links}</div>'
    )


def sittings_index(sittings: list[dict]) -> str:
    weeks: dict[str, list[dict]] = defaultdict(list)
    for s in reversed(sittings):
        weeks[s["week"]].append(s)
    out = []
    for week, ss in weeks.items():
        rows = "".join(
            f'<a class="row s" href="{e(s["page"])}.html"><span class="d">{e(short_date(s["date"]))}</span>'
            f'<span class="t"><span class="ti">{s["number"]}. Sitzung</span><span class="sub">'
            f"{len(s['items'])} Tagesordnungspunkte · {sum(len(i['speeches']) for i in s['items'])} Reden · "
            f"{sum(len(i['decisions']) for i in s['items'])} Beschlüsse</span></span></a>"
            for s in sorted(ss, key=lambda s: s["number"])
        )
        y, w = week.split("-W")
        out.append(f'<section class="grp"><h3>Sitzungswoche {int(w)}/{y} · <a href="{LANDSCAPE}{e(week)}.html">'
                   f'Themenlandschaft ↗</a></h3><div class="rows">{rows}</div></section>')  # fmt: skip
    body = (
        f'<h1>Sitzungen</h1><p class="lead">{len(sittings)} Sitzungen des 21. Bundestages seit '
        f"{e(long_date(sittings[0]['date'])) if sittings else ''}, die neueste zuerst. Jede Sitzung mit ihrer "
        "Tagesordnung, den Reden, den Beschlüssen und dem Plenarprotokoll.</p>"
        f"{''.join(out)}<footer>{FOOTER}</footer>"
    )
    return shell(root="../", kind="p-sittings", active="sittings", title="Sitzungen des Bundestages",
                 desc="Alle Sitzungen des 21. Deutschen Bundestages mit Tagesordnung, Reden und Beschlüssen.",
                 body=body, data={"kind": "sittings"})  # fmt: skip


def write_pages(out: Path, decisions: list[dict], members: dict[str, list[list]], sittings: list[dict],
                meta: dict, clusters: dict[str, dict] | None = None) -> dict[str, int]:  # fmt: skip
    """Write abstimmungen/ and sitzungen/; returns the number of pages written per folder."""
    votes_dir, sit_dir = out / "abstimmungen", out / "sitzungen"
    votes_dir.mkdir(parents=True, exist_ok=True)
    sit_dir.mkdir(parents=True, exist_ok=True)
    for d in decisions:
        (votes_dir / f"{d['page']}.html").write_text(vote_page(d, members.get(d["id"])), encoding="utf-8")
    (votes_dir / "index.html").write_text(votes_index(decisions, meta), encoding="utf-8")
    for s in sittings:
        (sit_dir / f"{s['page']}.html").write_text(sitting_page(s, clusters), encoding="utf-8")
    (sit_dir / "index.html").write_text(sittings_index(sittings), encoding="utf-8")
    return {"abstimmungen": len(decisions) + 1, "sitzungen": len(sittings) + 1}
