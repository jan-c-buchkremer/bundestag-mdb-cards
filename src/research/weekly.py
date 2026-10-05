"""Die Woche im Bundestag: `woche/<iso week>.html`, the sitting week in the time hierarchy (docs/plan.md 11.5, D18):
Wahlperiode (`sitzungen/index.html`) → week → sitting → agenda item, with breadcrumbs up and links down. Also the
Atom feed `woche/feed.xml`; `woche/index.html` is a stub to the Wahlperiode page.

A week page is an entity page: a header with the link to the landscape's week page for the topic map (which it
does not duplicate), the week in a few sentences, and the facets Sitzungen, Reden, Abstimmungen und Beschlüsse and
Drucksachen (the Vorlagen on the week's agenda), drawn by facts.py. Every sentence is a fixed template filled with
counts and titles from the store; no text is generated. It says on how many days the Bundestag sat, how many
decisions were taken and which roll-call votes, which Aktuelle Stunden were held on whose request, the chair's
Ordnungsmaßnahmen (debate.py's rule-based reading) and, when the store has `vorgang_position`, the bills with a
step that week. Its Vorgänge and its Abstimmungen are facets of their own.

The Wahlperiode page `sitzungen/index.html` is a calendar of the sitting weeks (docs/plan.md 12.4, D29), in the
visual language of the landscape's week overview (D10): a strip per year with the sitting weeks, then one card per
week with its sittings; toggles reveal per week, or for all weeks, each sitting's Abstimmungen (facts.decision,
with result and roll call or show of hands) and the Vorgänge that moved forward that day (debated, decided, or a
DIP step in the Bundestag), each linked to its page. Every vote shown here is the same component as on the sitting
page and on the Vorgang timeline; there is no third renderer."""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from research import debate, facts, redirects, urls
from research.data import has_table, page_id
from research.ui import (
    FOOTER,
    LANDSCAPE,
    MONTHS,
    RESEARCH,
    SITTING_TABS,
    WEEKDAYS,
    crumbs,
    e,
    entity_header,
    facet,
    long_date,
    n,
    shell,
    short_date,
    subtabs,
)

# where this site is published: the feed needs absolute links
BASE = RESEARCH
ATOM = "http://www.w3.org/2005/Atom"
FEED_WEEKS = 20
NUMBERS = {1: "einem", 2: "zwei", 3: "drei", 4: "vier", 5: "fünf"}


def plural(k: int, one: str, many: str) -> str:
    """ "1 Rede", "3 Reden"; "eine" is left to the sentence."""
    return f"{n(k)} {one if k == 1 else many}"


def week_label(week: str) -> str:
    y, w = week.split("-W")
    return f"Sitzungswoche {int(w)}/{y}"


def week_span(week: str) -> tuple[str, str]:
    y, w = week.split("-W")
    monday = dt.date.fromisocalendar(int(y), int(w), 1)
    return monday.isoformat(), (monday + dt.timedelta(days=6)).isoformat()


def group(sittings: list[dict]) -> dict[str, list[dict]]:
    """Sittings by ISO week, newest week first, sittings in order within a week."""
    weeks: dict[str, list[dict]] = defaultdict(list)
    for s in sorted(sittings, key=lambda s: (s["date"], s["number"])):
        weeks[s["week"]].append(s)
    return dict(sorted(weeks.items(), reverse=True))


def current_hours(ss: list[dict]) -> list[dict]:
    """Aktuelle Stunden: agenda items whose title starts "Aktuelle Stunde | auf Verlangen der Fraktion … | topic"."""
    out = []
    for s in ss:
        for i in s["items"]:
            seg = i["segments"]
            if seg and seg[0].startswith("Aktuelle Stunde"):
                by = next((x for x in seg[1:] if x.startswith("auf Verlangen")), None)
                topic = next((x for x in seg[1:] if x != by and not x.startswith("(")), None)
                out.append({"sitting": s, "position": i["position"], "by": by, "topic": topic or i["title"]})
    return out


def bill_steps(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """{week: [{vorgang, title, date, position, chamber}]} from `vorgang_position`; empty without the table."""
    if not has_table(conn, "vorgang_position") or not has_table(conn, "vorgang"):
        return {}
    out: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute(
        """SELECT p.vorgang_id, v.title, p.date, p.position, p.chamber FROM vorgang_position p
           JOIN vorgang v ON v.id = p.vorgang_id WHERE v.type = 'Gesetzgebung' ORDER BY p.date, v.title"""
    ):
        y, w, _ = dt.date.fromisoformat(r[2][:10]).isocalendar()
        out[f"{y}-W{w:02d}"].append({"vorgang": r[0], "title": r[1], "date": r[2][:10], "position": r[3],
                                     "chamber": r[4]})  # fmt: skip
    return out


def vorgang_steps(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """{date: [{vorgang, title, position}]}: every Vorgang's DIP steps in the Bundestag (`vorgang_position`, chamber
    BT), by date; empty without the table."""
    if not has_table(conn, "vorgang_position") or not has_table(conn, "vorgang"):
        return {}
    out: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute(
        """SELECT p.vorgang_id, v.title, p.date, p.position FROM vorgang_position p
           JOIN vorgang v ON v.id = p.vorgang_id WHERE p.chamber = 'BT' ORDER BY p.date, p.id"""
    ):
        out[r[2][:10]].append({"vorgang": r[0], "title": r[1], "position": r[3]})
    return out


def moves(ss: list[dict], decided: list[dict], steps: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """The Vorgänge that moved forward in each sitting, {sitting id: [{id, title, what: [..]}]}: debated under one of
    its agenda items or sub-items, decided there (data.decisions' Vorgänge of each decision), or a DIP step in the
    Bundestag on that day. Every Vorgang once per sitting, in agenda order."""
    by_sitting: dict[str, list[dict]] = defaultdict(list)
    for d in sorted(decided, key=lambda d: d["order"]):
        if d["sitting"]:
            by_sitting[d["sitting"]].append(d)
    out = {}
    for s in ss:
        found: dict[str, dict] = {}
        add = _adder(found)
        for i in s["items"]:
            for v in i.get("vorgaenge") or []:
                add(v["id"], v["title"], f"beraten ({i['label']})")
            for sub in i.get("sub_items") or []:
                for v in sub.get("vorgaenge") or []:
                    add(v["id"], v["title"], f"beraten ({i['label']} › {sub['label']})")
        for d in by_sitting.get(s["id"], []):
            for vid in d.get("vorgaenge") or []:
                add(vid, d["vorgang_titles"].get(vid, vid), "abgestimmt")
        for st in steps.get(s["date"], []):
            add(st["vorgang"], st["title"], st["position"])
        out[s["id"]] = list(found.values())
    return out


def _adder(found: dict[str, dict]):
    def add(vid: str, title: str, what: str) -> None:
        x = found.setdefault(vid, {"id": vid, "title": title, "what": []})
        if what not in x["what"]:
            x["what"].append(what)

    return add


def gather(ss: list[dict], decided: list[dict], measures: list[dict], steps: list[dict],
           moved: dict[str, list[dict]] | None = None) -> dict:  # fmt: skip
    """Everything a week page says, as data (the templates below turn it into sentences)."""
    ids = {s["id"] for s in ss}
    return {
        "moves": {s["id"]: (moved or {}).get(s["id"], []) for s in ss},
        "sittings": ss,
        "days": sorted({s["date"] for s in ss}),
        "speeches": sum(len(i["speeches"]) for s in ss for i in s["items"]),
        "items": sum(len(s["items"]) for s in ss),
        "decisions": [d for d in decided if d["sitting"] in ids],
        "hours": current_hours(ss),
        "measures": [m for m in measures if m["sitting"] in ids],
        "steps": steps,
    }


def _a(href: str, text: str) -> str:
    return f'<a href="{e(href)}">{e(text)}</a>'


def sentences(w: dict, root: str, have: set[str] | None = None, votes: bool = True) -> list[tuple[str, str]]:
    """(heading, HTML) per section; `root` is "../" on the page and BASE in the feed, `have` the Vorgang pages that
    exist (None: link every one). `votes`: list the roll-call votes (the feed; the page has them as a facet)."""
    out = []
    days = w["days"]
    k = len(days)
    day_word = "an einem Tag" if k == 1 else f"an {NUMBERS.get(k, n(k))} Tagen"
    sits = ", ".join(
        f"{_a(f'{root}sitzungen/{s["page"]}.html', f'{s["number"]}. Sitzung')} am "
        f"{WEEKDAYS[dt.date.fromisoformat(s['date']).weekday()]}, {e(long_date(s['date']))}"
        for s in w["sittings"]
    )
    out.append(("Sitzungen", f"<p>Der Bundestag hat in dieser Woche {day_word} getagt: {sits}. Es gab "
                             f"{plural(w['speeches'], 'Rede', 'Reden')} zu "
                             f"{plural(w['items'], 'Tagesordnungspunkt', 'Tagesordnungspunkten')}.</p>"))  # fmt: skip
    ds = w["decisions"]
    if ds:
        res = Counter(d["result"] for d in ds)
        rest = len(ds) - res["angenommen"] - res["abgelehnt"]
        text = (f"<p>Der Bundestag hat {plural(len(ds), 'Beschluss', 'Beschlüsse')} gefasst: "
                f"{n(res['angenommen'])} angenommen, {n(res['abgelehnt'])} abgelehnt"
                + (f", {n(rest)} mit anderem oder ohne Ergebnis" if rest else "") + ".</p>")  # fmt: skip
        rc = sorted((d for d in ds if d["kind"] == "namentlich"), key=lambda d: (d["date"], d["order"]))
        if rc:
            lead = "Eine Abstimmung war" if len(rc) == 1 else f"{n(len(rc))} Abstimmungen waren"
            rows = "".join(facts.decision(d, root, agenda=False) for d in rc) if votes else ""
            text += f"<p>{lead} namentlich.</p>{rows}"
        out.append(("Beschlüsse", text))
    else:
        out.append(("Beschlüsse", "<p>Für diese Woche sind keine Beschlüsse im Datenbestand.</p>"))
    if w["hours"]:
        rows = "".join(
            f'<li>{_a(f"{root}sitzungen/{h["sitting"]["page"]}.html#top-{h["position"]}", h["topic"])}'
            + (f" ({e(h['by'])})" if h["by"] else "") + "</li>"
            for h in w["hours"]
        )  # fmt: skip
        k = len(w["hours"])
        lead = "Es gab eine Aktuelle Stunde" if k == 1 else f"Es gab {n(k)} Aktuelle Stunden"
        out.append(("Aktuelle Stunden", f"<p>{lead}:</p><ul>{rows}</ul>"))
    ms = w["measures"]
    if ms:
        kinds = Counter(m["kind"] for m in ms)
        what = ", ".join(plural(v, kind, {"Ordnungsruf": "Ordnungsrufe", "Rüge": "Rügen"}.get(kind, kind + "e"))
                         for kind, v in kinds.items())  # fmt: skip
        rows = "".join(
            f'<li>{e(m["kind"])} am {_a(f"{root}sitzungen/{page_id(m["sitting"])}.html", long_date(m["date"]))}, '
            + ("Fraktion nicht eindeutig" if m["fraction"] == debate.UNCLEAR else f"an {e(m['fraction'])}") + "</li>"
            for m in ms
        )  # fmt: skip
        out.append(("Ordnungsmaßnahmen", f"<p>Die Sitzungsleitung hat {what} erteilt, so wie das Protokoll es "
                                         f"festhält:</p><ul>{rows}</ul>"))  # fmt: skip
    else:
        out.append(("Ordnungsmaßnahmen", "<p>Im Protokoll dieser Woche ist kein Ordnungsruf, keine Rüge und kein "
                                         "Sitzungsausschluss erkannt worden.</p>"))  # fmt: skip
    if w["steps"]:
        rows = "".join(
            "<li>"
            + (_a(f"{root}{urls.vorgang(b['vorgang'])}", b["title"]) if have is None or b["vorgang"] in have
               else e(b["title"]))
            + f": {e(b['position'])}" + (f" ({e(b['chamber'])})" if b["chamber"] else "")
            + f", {e(long_date(b['date']))}</li>"
            for b in w["steps"]
        )  # fmt: skip
        k = len({b["vorgang"] for b in w["steps"]})
        lead = "Ein Gesetzesvorhaben hatte" if k == 1 else f"{n(k)} Gesetzesvorhaben hatten"
        out.append(("Gesetzgebung", f"<p>{lead} in dieser Woche einen Schritt im Verfahren:</p><ul>{rows}</ul>"))
    return out


def week_page(week: str, w: dict, prev: str | None, nxt: str | None, have: set[str]) -> str:
    frm, to = week_span(week)
    summary = "".join(f"<h3>{e(h)}</h3>{t}" for h, t in sentences(w, "../", have, votes=False))
    nav = (f'<a href="{e(prev)}.html">← {e(week_label(prev))}</a>' if prev else "<span></span>") + (
        f'<a class="next" href="{e(nxt)}.html">{e(week_label(nxt))} →</a>' if nxt else "")  # fmt: skip
    sits = "".join(
        f'<a class="row s" href="../{e(urls.sitting(s["id"]))}"><span class="d">{e(short(s["date"]))}</span>'
        f'<span class="t"><span class="ti">{s["number"]}. Sitzung</span><span class="sub">'
        + " · ".join(e(i["label"]) for i in s["items"][:12])
        + (" …" if len(s["items"]) > 12 else "")
        + "</span></span></a>"
        for s in w["sittings"]
    )
    sps = [sp for s in w["sittings"] for i in s["items"] for sp in i["speeches"]]
    ds = sorted(w["decisions"], key=lambda d: (d["date"], d["order"]))
    refs = list({r["number"]: r for s in w["sittings"] for i in s["items"] for r in i["drucksachen"]}.values())
    body = (
        crumbs(("../sitzungen/index.html", "21. Wahlperiode"), (None, week_label(week)))
        + entity_header(week_label(week), [f"{e(long_date(frm))} bis {e(long_date(to))}"], [
            f'<a class="rl" href="{LANDSCAPE}{e(week)}.html">Worüber debattiert wurde: diese Woche in der '
            "Themenlandschaft</a>",
            '<a href="feed.xml">Als Feed abonnieren (Atom)</a>'], when="Sitzungswoche")
        + f'<nav class="prevnext">{nav}</nav>'
        + facet("sitzungen", "Sitzungen", f'<div class="rows">{sits}</div>', len(w["sittings"]))
        + facet("woche", "Die Woche in Sätzen", summary, explain="Jeder Satz ist aus den Daten gezählt und verlinkt "
                "die Sitzung, Abstimmung oder den Vorgang, aus dem er stammt.")
        + facet("reden", "Reden", facts.speech_list(sps, "../", "reden", where=True), len(sps))
        + facet("vorgaenge", "Vorgänge", moved_rows(w, "../", have), len({x["id"] for xs in w["moves"].values()
                                                                           for x in xs if x["id"] in have}),
                "Vorgänge, die in dieser Woche weitergekommen sind: im Plenum beraten, abgestimmt oder mit einem "
                "Schritt im Bundestag laut DIP. Ein Vorgang erstreckt sich meist über mehrere Wochen; sein ganzer "
                "Ablauf steht auf seiner Seite.")
        + facet("abstimmungen", "Abstimmungen und Beschlüsse", facts.decision_list(ds, "../", "dec"), len(ds))
        + facet("drucksachen", "Drucksachen", f"<p>{facts.drucksache_list(refs, '../', limit=40)}</p>" if refs
                else '<p class="explain">Keine Drucksachen auf der Tagesordnung.</p>', len(refs),
                "Die Vorlagen auf der Tagesordnung dieser Woche.")
        + f"<footer>{FOOTER}</footer>"
    )  # fmt: skip
    return shell(root="../", kind="p-week", active="sittings", title=f"Die Woche im Bundestag: {week_label(week)}",
                 desc=f"Der 21. Bundestag in der {week_label(week)}: Sitzungen, Reden, Beschlüsse.", body=body,
                 data={"kind": "week", "id": week},
                 head='<link rel="alternate" type="application/atom+xml" title="Die Woche im Bundestag" '
                      'href="feed.xml">')  # fmt: skip


def moved_rows(w: dict, root: str, have: set[str]) -> str:
    """The week's Vorgänge, by sitting: what happened to each, linked to its page."""
    rows = []
    for s in w["sittings"]:
        for x in w["moves"].get(s["id"], []):
            if x["id"] not in have:
                continue
            rows.append(f'<div class="row"><div class="d">{e(short(s["date"]))}</div><div class="t">'
                        f'<a href="{root}{e(urls.vorgang(x["id"]))}">{e(x["title"])}</a>'
                        f'<div class="sub">{e(", ".join(x["what"]))} · <a href="{root}{e(urls.sitting(s["id"]))}">'
                        f"{s['number']}. Sitzung</a></div></div></div>")  # fmt: skip
    return facts.fact_list(rows, "vg", "Kein Vorgang ist in dieser Woche weitergekommen.", limit=30)


def short(d: str) -> str:
    return f"{d[8:10]}.{d[5:7]}.{d[:4]}"


def feed(weeks: dict[str, dict], have: set[str] | None = None, limit: int = FEED_WEEKS) -> str:
    """Atom feed of the newest weeks, one entry per week, with absolute links."""
    ET.register_namespace("", ATOM)
    root = ET.Element(f"{{{ATOM}}}feed")

    def sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
        el = ET.SubElement(parent, f"{{{ATOM}}}{tag}", attrs)
        el.text = text
        return el

    def stamp(date: str) -> str:
        return f"{date}T00:00:00Z"

    newest = next(iter(weeks.values()), None)
    sub(root, "title", "Die Woche im Bundestag")
    sub(root, "subtitle", "Jede Sitzungswoche des 21. Deutschen Bundestages in wenigen Sätzen, aus den Daten gezählt.")
    sub(root, "id", f"{BASE}woche/")
    sub(root, "link", href=f"{BASE}woche/feed.xml", rel="self")
    sub(root, "link", href=f"{BASE}{urls.PERIOD}")
    sub(root, "updated", stamp(newest["days"][-1]) if newest else "1970-01-01T00:00:00Z")
    sub(sub(root, "author"), "name", "bundestag-research-platform")
    for week, w in list(weeks.items())[:limit]:
        entry = sub(root, "entry")
        sub(entry, "title", week_label(week))
        sub(entry, "id", f"{BASE}woche/{week}.html")
        sub(entry, "link", href=f"{BASE}woche/{week}.html")
        sub(entry, "updated", stamp(w["days"][-1]))
        html = "".join(f"<h2>{e(h)}</h2>{t}" for h, t in sentences(w, BASE, have))
        sub(entry, "content", html, type="html")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def write(conn: sqlite3.Connection, out: Path, sittings: list[dict], decided: list[dict]) -> dict[str, int]:
    """Write woche/ and the stub of its old index; call after the sitting, vote and Vorgang pages. Returns
    {"woche": pages}."""
    if not sittings:
        return {}
    measures = debate.order_measures(conn)
    steps = bill_steps(conn)
    bills_dir = out / "vorgaenge"
    have = {p.stem for p in bills_dir.glob("*.html") if p.stem != "index"} if bills_dir.is_dir() else set()
    moved = moves(sittings, decided, vorgang_steps(conn))
    weeks = {wk: gather(ss, decided, measures, steps.get(wk, []), moved) for wk, ss in group(sittings).items()}
    (out / "sitzungen").mkdir(parents=True, exist_ok=True)
    (out / urls.PERIOD).write_text(period_page(sittings, decided, moved, have), encoding="utf-8")
    d = out / "woche"
    d.mkdir(parents=True, exist_ok=True)
    keys = list(weeks)  # newest first
    for i, (wk, w) in enumerate(weeks.items()):
        prev = keys[i + 1] if i + 1 < len(keys) else None
        nxt = keys[i - 1] if i else None
        (d / f"{wk}.html").write_text(week_page(wk, w, prev, nxt, have), encoding="utf-8")
    redirects.write(out, "woche/index.html", urls.PERIOD, "21. Wahlperiode: Sitzungswochen und Sitzungen")
    (d / "feed.xml").write_text(feed(weeks, have), encoding="utf-8")
    return {"woche": len(weeks)}


# ---------------------------------------------------------------- the Wahlperiode: a calendar of sitting weeks

PERIOD_STYLE = """<style>
body.p-sittings main { max-width: 1100px; }
.cal .year { font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--faint);
  margin: 26px 0 10px; }
.cal .strip { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 4px; margin: 0 0 6px; }
.cal .strip .m { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 4px 4px 6px;
  min-width: 0; }
.cal .strip .m b { display: block; font-size: 11px; font-weight: 600; color: var(--muted); margin-bottom: 3px; }
.cal .strip .m span, .cal .strip .m a { display: inline-block; font-size: 11px; min-width: 20px; text-align: center;
  border-radius: 5px; padding: 1px 2px; margin: 1px 0; color: var(--faint); font-variant-numeric: tabular-nums; }
.cal .strip .m a { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.cal .tools { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 10px 0 4px; font-size: 13px; }
.cal .tools label { cursor: pointer; }
.cal .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }
.cal .wk { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
  min-width: 0; scroll-margin-top: 12px; }
.cal .wk:target { border-color: var(--accent); }
.cal .wk h3 { margin: 0; font-size: 15px; font-weight: 600; }
.cal .wk .dates { color: var(--muted); font-size: 12.5px; margin: 0 0 8px; }
.cal .wk .n { color: var(--faint); font-size: 12px; float: right; }
.cal .wk .sit { border-top: 1px solid var(--line); padding: 7px 0 5px; }
.cal .wk .sit > a { font-weight: 500; }
.cal .wk .sit .sub { color: var(--muted); font-size: 12.5px; }
.cal .wk .opts { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12.5px; color: var(--muted);
  margin: -2px 0 8px; }
.cal .wk .opts label { cursor: pointer; }
.cal .wk .votes, .cal .wk .procs { display: none; margin: 6px 0 2px; }
.cal .wk:has(.t-votes:checked) .votes, .cal .wk:has(.t-procs:checked) .procs { display: block; }
.cal .wk .k { font-size: 11px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: var(--faint);
  margin: 6px 0 2px; }
.cal .wk .dec { padding: 6px 0; border-top: 1px dashed var(--line); font-size: 13px; }
.cal .wk .procs li { margin: 2px 0; font-size: 13px; }
.cal .wk .procs ul { padding-left: 18px; margin: 2px 0; }
.cal .wk .procs .sub { color: var(--muted); font-size: 12px; }
@media (max-width: 640px) {
  .cal .strip { grid-template-columns: repeat(6, minmax(0, 1fr)); }
  .cal .grid { grid-template-columns: 1fr; }
}
</style>"""

PERIOD_JS = """<script>
// the toggles above the calendar set every week's toggles; each week's own still works alone (CSS :has)
document.querySelectorAll('.cal .tools input').forEach(t => t.addEventListener('change', () => {
  document.querySelectorAll(`.cal .wk input.${t.dataset.for}`).forEach(x => { x.checked = t.checked; });
}));
</script>"""


def _strip(year: str, weeks: list[str]) -> str:
    """One year as twelve months, each with the ISO weeks whose Monday falls in it; a sitting week links its card."""
    sitting = set(weeks)
    months: dict[int, list[str]] = defaultdict(list)
    day = dt.date.fromisocalendar(int(year), 1, 1)
    while day.year <= int(year):
        if day.year == int(year):
            y, w, _ = day.isocalendar()
            months[day.month].append(f"{y}-W{w:02d}")
        day += dt.timedelta(days=7)
    cells = []
    for m in range(1, 13):
        ws = "".join(f'<a href="#{wk}" title="{e(week_label(wk))}">{int(wk[-2:])}</a>' if wk in sitting
                     else f"<span>{int(wk[-2:])}</span>" for wk in months[m])  # fmt: skip
        cells.append(f'<div class="m"><b>{MONTHS[m - 1][:3]}</b>{ws}</div>')
    return f'<div class="strip" aria-label="Sitzungswochen {e(year)}">{"".join(cells)}</div>'


def week_card(week: str, ss: list[dict], decided: dict[str, list[dict]], moved: dict[str, list[dict]],
              have: set[str]) -> str:  # fmt: skip
    """A sitting week: its sittings, each with its Abstimmungen and its Vorgänge behind the week's toggles."""
    n_speeches = sum(len(i["speeches"]) for s in ss for i in s["items"])
    sits, k_votes, k_procs = [], 0, 0
    for s in ss:
        ds = decided.get(s["id"], [])
        ps = [x for x in moved.get(s["id"], []) if x["id"] in have]
        k_votes += len(ds)
        k_procs += len(ps)
        votes = "".join(facts.decision(d, "../", when=False, agenda=True) for d in ds)
        procs = "".join(f'<li><a href="../{e(urls.vorgang(x["id"]))}">{e(x["title"])}</a> '
                        f'<span class="sub">{e(", ".join(x["what"]))}</span></li>' for x in ps)  # fmt: skip
        sits.append(
            f'<div class="sit"><a href="{e(s["page"])}.html">{s["number"]}. Sitzung</a> '
            f'<span class="sub">{e(WEEKDAYS[dt.date.fromisoformat(s["date"]).weekday()])}, {short_date(s["date"])} · '
            f"{n(len(s['items']))} Tagesordnungspunkte · {n(sum(len(i['speeches']) for i in s['items']))} Reden · "
            f"{n(len(ds))} Abstimmungen</span>"
            + (f'<div class="votes"><div class="k">Abstimmungen</div>{votes}</div>' if ds else "")
            + (f'<div class="procs"><div class="k">Vorgänge</div><ul>{procs}</ul></div>' if ps else "")
            + "</div>"
        )
    opts = []
    if k_votes:
        opts.append(f'<label><input type="checkbox" class="t-votes"> Abstimmungen ({n(k_votes)})</label>')
    if k_procs:
        opts.append(f'<label><input type="checkbox" class="t-procs"> Vorgänge ({n(k_procs)})</label>')
    return (
        f'<section class="wk" id="{e(week)}"><span class="n">{plural(n_speeches, "Rede", "Reden")}</span>'
        f'<h3><a href="../{e(urls.week(week))}">{e(week_label(week))}</a></h3>'
        f'<div class="dates">{short(ss[0]["date"])[:6]} – {short(ss[-1]["date"])} · '
        f'<a class="rl" href="{LANDSCAPE}{e(week)}.html">Themenlandschaft</a></div>'
        + (f'<div class="opts">{"".join(opts)}</div>' if opts else "")
        + f"{''.join(sits)}</section>"
    )


def period_page(sittings: list[dict], decided: list[dict], moved: dict[str, list[dict]], have: set[str]) -> str:
    """The Wahlperiode (D18) as a calendar of its sitting weeks, newest first (D29)."""
    by_sitting: dict[str, list[dict]] = defaultdict(list)
    for d in sorted(decided, key=lambda d: d["order"]):
        if d["sitting"]:
            by_sitting[d["sitting"]].append(d)
    weeks = group(sittings)
    years: dict[str, list[str]] = defaultdict(list)
    for wk in weeks:
        years[wk[:4]].append(wk)
    parts = []
    for year, wks in years.items():
        cards = "".join(week_card(wk, weeks[wk], by_sitting, moved, have) for wk in wks)
        parts.append(f'<div class="year">{e(year)}</div>{_strip(year, wks)}<div class="grid">{cards}</div>')
    tools = ('<div class="tools"><span class="faint">In allen Wochen zeigen:</span>'
             '<label><input type="checkbox" data-for="t-votes"> Abstimmungen</label>'
             '<label><input type="checkbox" data-for="t-procs"> Vorgänge</label></div>')  # fmt: skip
    first = e(long_date(sittings[0]["date"])) if sittings else ""
    body = (
        subtabs("../", SITTING_TABS, "calendar")
        + f'<h1>21. Wahlperiode</h1><p class="lead">{n(len(sittings))} Sitzungen in {n(len(weeks))} Sitzungswochen '
        f"seit {first}, die neueste zuerst. Jede Woche mit ihren Sitzungen; darunter lassen sich je Sitzung die "
        "Abstimmungen und die Vorgänge zeigen, die an dem Tag weitergekommen sind. Jede Sitzung führt zu ihrer "
        "Tagesordnung mit Reden und Beschlüssen, jede Woche zu ihrer Seite. Vorgänge erstrecken sich über viele "
        'Wochen und haben eigene Seiten: <a href="../vorgaenge/index.html">Vorgänge</a>. '
        '<a href="../woche/feed.xml">Die Woche im Bundestag als Feed (Atom)</a></p>'
        f'<div class="cal">{tools}{"".join(parts)}</div><footer>{FOOTER}</footer>{PERIOD_JS}'
    )
    return shell(root="../", kind="p-sittings", active="sittings", title="Sitzungen des Bundestages",
                 desc="Alle Sitzungswochen und Sitzungen des 21. Deutschen Bundestages als Kalender, mit Abstimmungen "
                      "und Vorgängen.", body=body, data={"kind": "sittings"},
                 head=PERIOD_STYLE + ('<script src="../parliament.js"></script>' if decided else ""))  # fmt: skip
