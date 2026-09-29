"""Die Woche im Bundestag: `woche/<iso week>.html` per sitting week, `woche/index.html` and an Atom feed
`woche/feed.xml`.

Every sentence is a fixed template filled with counts and titles from the store; no text is generated. A week
page says on how many days the Bundestag sat, which Themenlandschaft clusters had the most speeches (with
`LANDSCAPE_CLUSTERS`), how many decisions were taken and which roll-call votes, which Aktuelle Stunden were held on
whose request, the chair's Ordnungsmaßnahmen (debate.py's rule-based reading) and, when the store has
`vorgang_position`, the bills with a step that week. Each item links to its sitting, vote or bill page."""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from cards import debate
from cards.data import has_table, page_id
from cards.pages import FOOTER, LANDSCAPE, WEEKDAYS, e, long_date, n, shell

BASE = "https://jan-c-buchkremer.github.io/bundestag-mdb-cards/"
ATOM = "http://www.w3.org/2005/Atom"
TOP_THEMES = 5
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


def themes(ss: list[dict], clusters: dict[str, dict], limit: int = TOP_THEMES) -> list[dict]:
    """The week's Themenlandschaft clusters with the most speeches."""
    count: Counter = Counter()
    label: dict[tuple, str] = {}
    for s in ss:
        for i in s["items"]:
            for sp in i["speeches"]:
                c = clusters.get(sp["id"])
                if c:
                    key = (c["week"], c["cluster_id"])
                    count[key] += 1
                    label.setdefault(key, c["label"])
    ranked = sorted(count.items(), key=lambda kv: (-kv[1], label[kv[0]]))[:limit]
    return [{"week": w, "cluster_id": cid, "label": label[(w, cid)], "n": k} for (w, cid), k in ranked]


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


def gather(ss: list[dict], decided: list[dict], measures: list[dict], clusters: dict[str, dict],
           steps: list[dict]) -> dict:  # fmt: skip
    """Everything a week page says, as data (the templates below turn it into sentences)."""
    ids = {s["id"] for s in ss}
    return {
        "sittings": ss,
        "days": sorted({s["date"] for s in ss}),
        "speeches": sum(len(i["speeches"]) for s in ss for i in s["items"]),
        "items": sum(len(s["items"]) for s in ss),
        "themes": themes(ss, clusters),
        "decisions": [d for d in decided if d["sitting"] in ids],
        "hours": current_hours(ss),
        "measures": [m for m in measures if m["sitting"] in ids],
        "steps": steps,
    }


def _a(href: str, text: str) -> str:
    return f'<a href="{e(href)}">{e(text)}</a>'


def sentences(w: dict, root: str, have: set[str] | None = None) -> list[tuple[str, str]]:
    """(heading, HTML) per section; `root` is "../" on the page and BASE in the feed, `have` the bill pages that
    exist (None: link every bill)."""
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
    if w["themes"]:
        rows = "".join(
            f"<li>{_a(f'{LANDSCAPE}{t["week"]}.html#cluster={t["cluster_id"]}', t['label'])}: "
            f"{plural(t['n'], 'Rede', 'Reden')}</li>"
            for t in w["themes"]
        )
        out.append(("Worüber debattiert wurde", "<p>Die meisten Reden gehörten in der Themenlandschaft zu diesen "
                                                f"Themen:</p><ul>{rows}</ul>"))  # fmt: skip
    ds = w["decisions"]
    if ds:
        res = Counter(d["result"] for d in ds)
        rest = len(ds) - res["angenommen"] - res["abgelehnt"]
        text = (f"<p>Der Bundestag hat {plural(len(ds), 'Beschluss', 'Beschlüsse')} gefasst: "
                f"{n(res['angenommen'])} angenommen, {n(res['abgelehnt'])} abgelehnt"
                + (f", {n(rest)} mit anderem oder ohne Ergebnis" if rest else "") + ".</p>")  # fmt: skip
        rc = sorted((d for d in ds if d["kind"] == "namentlich"), key=lambda d: (d["date"], d["order"]))
        if rc:
            rows = "".join(
                f'<li>{_a(f"{root}abstimmungen/{d["page"]}.html", d["title"])}: {e(d["result"] or "ohne Ergebnis")}'
                + (f" ({n(d['counts']['yes'])} Ja, {n(d['counts']['no'])} Nein, {n(d['counts']['abstain'])} "
                   "Enthaltungen)" if d.get("counts") else "") + "</li>"
                for d in rc
            )  # fmt: skip
            text += (f"<p>{'Eine Abstimmung war' if len(rc) == 1 else f'{n(len(rc))} Abstimmungen waren'} "
                     f"namentlich:</p><ul>{rows}</ul>")  # fmt: skip
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
            + (_a(f"{root}gesetze/{b['vorgang']}.html", b["title"]) if have is None or b["vorgang"] in have
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
    parts = "".join(f"<h2>{e(h)}</h2>{t}" for h, t in sentences(w, "../", have))
    nav = (f'<a href="{e(prev)}.html">← {e(week_label(prev))}</a>' if prev else "<span></span>") + (
        f'<a class="next" href="{e(nxt)}.html">{e(week_label(nxt))} →</a>' if nxt else "")  # fmt: skip
    body = (
        f'<p class="crumbs"><a href="index.html">Die Woche im Bundestag</a> · '
        f'<a href="../sitzungen/index.html">Sitzungen</a></p>'
        f'<h1>{e(week_label(week))}</h1><p class="lead">{e(long_date(frm))} bis {e(long_date(to))}. Jeder Satz auf '
        "dieser Seite ist aus den Daten gezählt und verlinkt die Sitzung, Abstimmung oder das Gesetz, aus dem er "
        f'stammt.</p><nav class="prevnext">{nav}</nav>{parts}<footer>{FOOTER}</footer>'
    )
    return shell(root="../", kind="p-week", active="sittings", title=f"Die Woche im Bundestag: {week_label(week)}",
                 desc=f"Der 21. Bundestag in der {week_label(week)}: Sitzungen, Themen, Beschlüsse.", body=body,
                 data={"kind": "week", "id": week},
                 head='<link rel="alternate" type="application/atom+xml" title="Die Woche im Bundestag" '
                      'href="feed.xml">')  # fmt: skip


def index_page(weeks: dict[str, dict]) -> str:
    rows = "".join(
        f'<a class="row s" href="{e(week)}.html"><span class="d">{e(week_label(week))}</span><span class="t">'
        f'<span class="sub">{plural(len(w["sittings"]), "Sitzung", "Sitzungen")} · '
        f"{plural(w['speeches'], 'Rede', 'Reden')} · {plural(len(w['decisions']), 'Beschluss', 'Beschlüsse')}"
        "</span></span></a>"
        for week, w in weeks.items()
    )
    body = (
        '<p class="crumbs"><a href="../sitzungen/index.html">Sitzungen</a></p><h1>Die Woche im Bundestag</h1>'
        '<p class="lead">Jede Sitzungswoche des 21. Bundestages in wenigen Sätzen: Sitzungen, Themen, Beschlüsse, '
        "Aktuelle Stunden und Ordnungsmaßnahmen. Die Sätze sind feste Vorlagen, gefüllt mit Zahlen aus den "
        'Plenarprotokollen. <a href="feed.xml">Als Feed abonnieren (Atom)</a></p>'
        f'<div class="rows">{rows}</div><footer>{FOOTER}</footer>'
    )
    return shell(root="../", kind="p-weeks", active="sittings", title="Die Woche im Bundestag",
                 desc="Jede Sitzungswoche des 21. Deutschen Bundestages in wenigen Sätzen, aus den Daten gezählt.",
                 body=body, data={"kind": "weeks"},
                 head='<link rel="alternate" type="application/atom+xml" title="Die Woche im Bundestag" '
                      'href="feed.xml">')  # fmt: skip


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
    sub(root, "link", href=f"{BASE}woche/index.html")
    sub(root, "updated", stamp(newest["days"][-1]) if newest else "1970-01-01T00:00:00Z")
    sub(sub(root, "author"), "name", "bundestag-mdb-cards")
    for week, w in list(weeks.items())[:limit]:
        entry = sub(root, "entry")
        sub(entry, "title", week_label(week))
        sub(entry, "id", f"{BASE}woche/{week}.html")
        sub(entry, "link", href=f"{BASE}woche/{week}.html")
        sub(entry, "updated", stamp(w["days"][-1]))
        html = "".join(f"<h2>{e(h)}</h2>{t}" for h, t in sentences(w, BASE, have))
        sub(entry, "content", html, type="html")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def write(conn: sqlite3.Connection, out: Path, sittings: list[dict], decided: list[dict],
          clusters: dict[str, dict] | None = None) -> dict[str, int]:  # fmt: skip
    """Write woche/; call after the sitting, vote and bill pages. Returns {"woche": pages}."""
    if not sittings:
        return {}
    measures = debate.order_measures(conn)
    steps = bill_steps(conn)
    bills_dir = out / "gesetze"
    have = {p.stem for p in bills_dir.glob("*.html")} if bills_dir.is_dir() else set()
    weeks = {wk: gather(ss, decided, measures, clusters or {}, steps.get(wk, [])) for wk, ss in group(sittings).items()}
    d = out / "woche"
    d.mkdir(parents=True, exist_ok=True)
    keys = list(weeks)  # newest first
    for i, (wk, w) in enumerate(weeks.items()):
        prev = keys[i + 1] if i + 1 < len(keys) else None
        nxt = keys[i - 1] if i else None
        (d / f"{wk}.html").write_text(week_page(wk, w, prev, nxt, have), encoding="utf-8")
    (d / "index.html").write_text(index_page(weeks), encoding="utf-8")
    (d / "feed.xml").write_text(feed(weeks, have), encoding="utf-8")
    return {"woche": len(weeks) + 1}
