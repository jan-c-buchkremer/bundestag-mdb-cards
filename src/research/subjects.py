"""Sachgebiete (docs/plan.md, "Current goal" 2): `sachgebiete/index.html` and one page per DIP Sachgebiet,
`sachgebiete/<slug>.html`. A Sachgebiet is the Bundestag's own subject index: its documentation sets one or more per
Vorgang in DIP (`vorgang.subjects`). So it is Research, and the pages only count and list what the store holds.

A Sachgebiet page is an entity page: a header with the Vorgänge by kind, then the facets Einbringer (Vorgänge per
fraction, Bundesregierung, Bundesrat and Länder), Vorgänge (all of them, filterable as on `vorgaenge/index.html`),
Reden (the debates of its Vorgänge), Abstimmungen und Beschlüsse and Drucksachen, each rendered by facts.py. Every
WP 21 Vorgang with a Sachgebiet counts, not only the ones that reached the plenum and have a page here; a row of one
without a page links DIP. A Vorgang can carry several Sachgebiete, so counts across Sachgebiete overlap.

The index also names what has no Sachgebiet: Schriftliche and Mündliche Fragen (they have the answering Ressort
instead), EU-Vorlagen (`eu.py`), Petitionen, and the plenary business that has no Vorgang at all."""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from research import controls, data, facts, urls, weekly
from research.data import GOVERNMENT_GROUP, LAENDER_GROUP, OTHER_GROUP, WP, has_table, initiator_group, page_id
from research.procedures import DIP_VORGANG, GESETZ, STYLE, _json_list, vorgaenge_controls
from research.ui import (
    FOOTER,
    ORDER,
    PROCEDURE_TABS,
    crumbs,
    dot,
    e,
    entity_header,
    facet,
    frac_link,
    n,
    shell,
    subtabs,
)

EUROPE = "Europapolitik und Europäische Union"  # the Sachgebiet the EU-Vorlagen page and this one link each other
# the kinds of Vorgang a column of their own on the index and in the Einbringer table: (DIP type, plural)
KINDS = ((GESETZ, "Gesetzgebung"), ("Antrag", "Anträge"), ("Kleine Anfrage", "Kleine Anfragen"))
SPEECHES = 100  # newest speeches of a Sachgebiet in the page (the largest have a few thousand)
DRUCKSACHEN = 100  # newest Drucksachen of a Sachgebiet in the page
GOVERNMENT = GOVERNMENT_GROUP
LAENDER = LAENDER_GROUP
OTHER = OTHER_GROUP
NONE = "ohne Angabe"
OVERLAP = ("Ein Vorgang kann mehrere Sachgebiete haben. Er zählt dann in jedem, deshalb lassen sich die Zahlen "
           "verschiedener Sachgebiete nicht addieren.")  # fmt: skip
PLURAL = {"Aktuelle Stunde": "Aktuelle Stunden", "Regierungsbefragung": "Regierungsbefragungen",
          "Fragestunde": "Fragestunden"}  # fmt: skip
# DIP's kinds of Vorgang are singular ("Kleine Anfrage"); in a count they take the plural
KIND_PLURAL = {"Kleine Anfrage": "Kleine Anfragen", "Antrag": "Anträge", "Große Anfrage": "Große Anfragen",
               "Entschließungsantrag BT": "Entschließungsanträge BT", "Rechtsverordnung": "Rechtsverordnungen",
               "Untersuchungsausschuss": "Untersuchungsausschüsse", "Enquete-Kommission": "Enquete-Kommissionen",
               "Wahlprüfungsverfahren": "Wahlprüfungsverfahren", "EU-Vorlage": "EU-Vorlagen",
               "Wahl im BT": "Wahlen im BT"}  # fmt: skip
DIP_SEARCH = "https://dip.bundestag.de/suche?f.wahlperiode=21&f.sachgebiet={}"


def _group_order(g: str) -> tuple[int, str]:
    tail = (GOVERNMENT, LAENDER, OTHER, NONE)
    return (ORDER.index(g), g) if g in ORDER else (len(ORDER) + tail.index(g), g)


def load(conn: sqlite3.Connection, procs: list[dict]) -> dict[str, list[dict]]:
    """{Sachgebiet: its Vorgänge, newest first}: every WP 21 Vorgang with a Sachgebiet, straight from the store, as
    {id, type, title, status, initiators, subjects, latest, page, debates, decisions, docs}. `page`, the debates and
    the decisions come from procedures.load (`procs`); `latest` is the newest step there, else the date of the newest
    Drucksache. `docs` are the Drucksachen ids, without an Unterrichtung shared by several Vorgänge (the § 80 GO-BT
    lists, data.vorgang_index). Empty without the `vorgang` table."""
    if not has_table(conn, "vorgang"):
        return {}
    docs: dict[str, list[str]] = {}
    newest: dict[str, str] = {}
    if has_table(conn, "vorgang_drucksache") and has_table(conn, "drucksache"):
        for r in conn.execute(
            """SELECT vd.vorgang_id, d.id, d.date, d.type,
                      (SELECT count(*) FROM vorgang_drucksache x WHERE x.drucksache_id = d.id) AS shared
               FROM vorgang_drucksache vd JOIN drucksache d ON d.id = vd.drucksache_id ORDER BY d.date"""
        ):
            if r["date"]:
                newest[r["vorgang_id"]] = max(newest.get(r["vorgang_id"], ""), r["date"])
            if not (r["type"] == "Unterrichtung" and r["shared"] > 1):
                docs.setdefault(r["vorgang_id"], []).append(r["id"])
    by_id = {b["id"]: b for b in procs}
    out: dict[str, list[dict]] = {}
    for r in conn.execute("SELECT * FROM vorgang WHERE wahlperiode = ? ORDER BY id", (WP,)):
        subjects = [s for s in _json_list(r["subjects"]) if isinstance(s, str) and s.strip()]
        if not subjects:
            continue
        b = by_id.get(r["id"])
        v = {
            "id": r["id"], "type": r["type"] or "Vorgang", "title": r["title"], "status": r["status"] or "unbekannt",
            "initiators": _json_list(r["initiators"]), "subjects": subjects, "page": b is not None,
            "latest": (b["latest"] if b else "") or newest.get(r["id"], ""),
            "in_force": b["in_force"] if b else None,
            "debates": b["debates"] if b else [], "decisions": b["decisions"] if b else [],
            "docs": docs.get(r["id"], []),
        }  # fmt: skip
        for s in subjects:
            out.setdefault(s, []).append(v)
    for vs in out.values():
        vs.sort(key=lambda v: (v["latest"], v["id"]), reverse=True)
    return dict(sorted(out.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def summary(vs: list[dict]) -> dict:
    """The counts of a Sachgebiet: Vorgänge by kind, debated ones, debates, speeches and decisions (each once)."""
    debates = {(a["sitting"], a["position"], a["sub"]) for v in vs for a in v["debates"]}
    speeches = {sp["id"] for v in vs for a in v["debates"] for sp in a["speeches"]}
    decisions = {d["id"]: d for v in vs for d in v["decisions"]}
    return {
        "vorgaenge": len(vs), "kinds": Counter(v["type"] for v in vs),
        "debated": sum(1 for v in vs if v["debates"]), "debates": len(debates), "speeches": len(speeches),
        "decisions": len(decisions), "roll_calls": sum(1 for d in decisions.values() if d["kind"] == "namentlich"),
    }  # fmt: skip


# ---------------------------------------------------------------- the Sachgebiet page


def per_group(vs: list[dict]) -> dict[str, Counter]:
    """Vorgänge per group of initiators and kind ("all", the KINDS, "other"). A Vorgang with several initiators
    counts once for each group."""
    per: dict[str, Counter] = {}
    for v in vs:
        groups = {initiator_group(x) for x in v["initiators"] if isinstance(x, str)} or {NONE}
        for g in groups:
            c = per.setdefault(g, Counter())
            c["all"] += 1
            c[v["type"] if v["type"] in dict(KINDS) else "other"] += 1
    return dict(sorted(per.items(), key=lambda gc: _group_order(gc[0])))


def initiators_table(vs: list[dict]) -> str:
    """The Einbringer as a table: Vorgänge per group and kind (the stacked rows' "Als Tabelle")."""
    rows = []
    for g, c in per_group(vs).items():
        name = f"{dot(g)} {frac_link(g)}" if g in ORDER else e(g)
        cells = "".join(f'<td class="num">{n(c[k]) if c[k] else "–"}</td>' for k in [t for t, _ in KINDS] + ["other"])
        rows.append(f'<tr><td>{name}</td><td class="num">{n(c["all"])}</td>{cells}</tr>')
    head = "".join(f"<th>{e(label)}</th>" for _, label in KINDS)
    return (
        '<div class="rows scroll"><table class="plenum"><thead><tr><th>Einbringer</th><th>Vorgänge</th>'
        f"{head}<th>andere</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def initiators_chart(vs: list[dict]) -> str:
    """The Einbringer as stacked bar rows, one per group, segments by kind; a row filters the Vorgänge below. The
    rows without an initiator (ohne Angabe) stand in the table only, having nothing to filter by."""
    groups = [(controls.GROUP_TOKENS[g], controls.SHORT.get(g, g), controls.GROUP_TOKENS[g], c)
              for g, c in per_group(vs).items() if g in controls.GROUP_TOKENS]  # fmt: skip
    kinds = [*KINDS, ("other", "andere")]
    return controls.stacked("von", [(v, label, colour, Counter({k: c[k] for k, _ in kinds}))
                                    for v, label, colour, c in groups], kinds, "Einbringer", "Vorgänge")  # fmt: skip


def vorgaenge_list(vs: list[dict], sitting_dates: list[str]) -> str:
    """All Vorgänge of a Sachgebiet with the charts and filters of the Vorgänge index; a Vorgang without a page
    here links DIP."""
    return vorgaenge_controls(
        vs,
        lambda v: (f"../{urls.vorgang(v['id'])}", False) if v["page"] else (DIP_VORGANG.format(v["id"]), True),
        sitting_dates,
        glossary=f"../{urls.PROCEDURES}",
        wrap=False,
    )


def _kinds_line(s: dict) -> str:
    kinds = ", ".join(f"{n(k)} {e(t if k == 1 else KIND_PLURAL.get(t, t))}" for t, k in s["kinds"].most_common())
    return f"{n(s['vorgaenge'])} {'Vorgang' if s['vorgaenge'] == 1 else 'Vorgänge'} ({kinds})"


def subject_page(name: str, vs: list[dict], drucksachen: dict[str, dict], have: set[str],
                 sitting_dates: list[str] | None = None) -> str:  # fmt: skip
    """One Sachgebiet; `drucksachen` holds data.drucksache_facts by id, `have` the speech pages that exist,
    `sitting_dates` the days of the sittings (the weeks marked on the activity strip)."""
    s = summary(vs)
    lines = [
        _kinds_line(s),
        f"{n(s['debated'])} davon im Plenum beraten, in {n(s['debates'])} "
        f"{'Tagesordnungspunkt' if s['debates'] == 1 else 'Tagesordnungspunkten'} mit {n(s['speeches'])} Reden",
        f"{n(s['decisions'])} Abstimmungen und Beschlüsse, {n(s['roll_calls'])} davon namentlich",
    ]
    links = [f'<a href="{e(DIP_SEARCH.format(quote(name)))}">Sachgebiet im DIP ↗</a>']
    if name == EUROPE:
        links.append(f'<a href="../{urls.EU}">EU-Vorlagen</a>')
    eu = (f' Die EU-Vorlagen haben kein Sachgebiet. Sie stehen auf einer <a href="../{urls.EU}">eigenen Seite</a>.'
          if name == EUROPE else "")  # fmt: skip

    speeches = {sp["id"]: sp for v in vs for a in v["debates"] for sp in a["speeches"]}
    sps = sorted((sp for sp in speeches.values() if f"reden/{page_id(urls.rede(sp['id']))}.html" in have),
                 key=lambda sp: (sp["date"], sp["id"]), reverse=True)  # fmt: skip
    shown = sps[:SPEECHES]
    sp_note = (f'<p class="explain">Die neuesten {n(len(shown))} von {n(len(sps))}. Alle Reden stehen bei den '
               "Vorgängen und Sitzungen.</p>" if len(sps) > len(shown) else "")  # fmt: skip

    decisions = sorted({d["id"]: d for v in vs for d in v["decisions"]}.values(),
                       key=lambda d: (d["date"], d["order"]), reverse=True)  # fmt: skip

    ids = list(dict.fromkeys(x for v in vs for x in v["docs"] if x in drucksachen))
    docs = sorted((drucksachen[x] for x in ids), key=lambda r: (r["date"] or "", r["number"]), reverse=True)
    shown_docs = docs[:DRUCKSACHEN]
    drs_note = (f'<p class="explain">Die neuesten {n(len(shown_docs))} von {n(len(docs))}. Alle stehen bei den '
                "Vorgängen und im DIP.</p>" if len(docs) > len(shown_docs) else "")  # fmt: skip

    body = (
        crumbs((f"../{urls.PROCEDURES}", "Vorgänge"), ("index.html", "Sachgebiete"), (None, name))
        + entity_header(name, lines, links, when="Sachgebiet (DIP)")
        + f'<p class="explain">{OVERLAP}{eu}</p>'
        + controls.scope(
            facet("einbringer", "Einbringer", controls.view("einbringer", "Vorgänge nach Einbringer und Art",
                  initiators_chart(vs), initiators_table(vs)), explain="Wer die Vorgänge eingebracht hat, nach "
                  "Fraktionen, Bundesregierung (mit den Ministerien) und Bundesrat. Ein Vorgang mit mehreren "
                  "Einbringern zählt bei jedem. Bei einem Fraktionsantrag ist die ganze Fraktion der Einbringer. "
                  "Einzelne Abgeordnete werden deshalb hier nicht gezählt. Ein Klick auf eine Zeile zeigt unten "
                  "nur ihre Vorgänge.")
            + facet("vorgaenge", "Vorgänge", vorgaenge_list(vs, sitting_dates or []), len(vs), "Alle Vorgänge der "
                    "21. Wahlperiode mit diesem Sachgebiet, der zuletzt bewegte zuerst. Jedes Diagramm ist auch ein "
                    "Filter. Ein Vorgang ohne Beratung im Plenum hat hier keine eigene Seite. Er führt zum DIP (↗)."),
            "Vorgänge", "Vorgang")
        + facet("reden", "Reden", facts.speech_list(shown, "../", "reden", note=sp_note,
                                                    empty="Kein Vorgang dieses Sachgebiets wurde im Plenum beraten."),
                len(sps), "Die Reden unter den Tagesordnungspunkten, die eine Drucksache eines dieser Vorgänge "
                "aufrufen, die neueste zuerst.")
        + facet("abstimmungen", "Abstimmungen und Beschlüsse", facts.decision_list(decisions, "../", "dec",
                empty="Über keinen Vorgang dieses Sachgebiets wurde abgestimmt."), len(decisions),
                "Jeder Beschluss steht einmal, auch wenn er mehrere Vorgänge betrifft.")
        + facet("drucksachen", "Drucksachen", facts.drucksache_list(shown_docs, "../", "drs", compact=False,
                note=drs_note), len(docs))
        + f"<footer>{FOOTER}</footer>"
    )  # fmt: skip
    return shell(root="../", kind="p-subject", active="bills", title=f"Sachgebiet {name}",
                 desc=f"Das Sachgebiet „{name}“ im 21. Bundestag: {s['vorgaenge']} Vorgänge mit Reden, "
                      "Abstimmungen und Drucksachen.",
                 body=f'<div class="bills">{body}</div>', data={"kind": "subject", "name": name},
                 head=STYLE + controls.head("../"))  # fmt: skip


# ---------------------------------------------------------------- the index


def without_subject(conn: sqlite3.Connection) -> Counter:
    """WP 21 Vorgänge without a Sachgebiet, by kind."""
    if not has_table(conn, "vorgang"):
        return Counter()
    return Counter(
        r["type"] or "Vorgang"
        for r in conn.execute("SELECT type, subjects FROM vorgang WHERE wahlperiode = ?", (WP,))
        if not [s for s in _json_list(r["subjects"]) if isinstance(s, str) and s.strip()]
    )


def plenary_without_vorgang(sittings: list[dict]) -> dict[str, int]:
    """Agenda items that are no Vorgang: Aktuelle Stunden, Regierungsbefragungen and Fragestunden."""
    items = [i for s in sittings for i in s["items"]]
    first = [(i["segments"] or [i["title"]])[0] for i in items]
    return {
        "Aktuelle Stunde": len(weekly.current_hours(sittings)),
        "Regierungsbefragung": sum(1 for t in first if t.startswith("Befragung der Bundesregierung")),
        "Fragestunde": sum(1 for t in first if t.startswith("Fragestunde")),
    }


def index_page(subjects: dict[str, list[dict]], none: Counter, plenary: dict[str, int], questions: bool) -> str:
    """All Sachgebiete, largest first, then what has none. `questions`: the Fragen page was written."""
    rows = []
    for name, vs in subjects.items():
        s = summary(vs)
        kinds = "".join(f'<td class="num">{n(s["kinds"][t])}</td>' for t, _ in KINDS)
        rows.append(f'<tr><td><a href="../{e(urls.subject(name))}">{e(name)}</a></td><td class="num">'
                    f'{n(s["vorgaenge"])}</td>{kinds}<td class="num">{n(s["debated"])}</td>'
                    f'<td class="num">{n(s["decisions"])}</td></tr>')  # fmt: skip
    head = "".join(f"<th>{e(label)}</th>" for _, label in KINDS)
    table = (
        '<div class="rows scroll"><table class="plenum subjects"><thead><tr><th>Sachgebiet</th><th>Vorgänge</th>'
        f"{head}<th>im Plenum beraten</th><th>Beschlüsse</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )  # fmt: skip
    if rows:
        kinds = [*KINDS, ("other", "andere")]
        items = []
        for name, vs in subjects.items():
            c = Counter(v["type"] if v["type"] in dict(KINDS) else "other" for v in vs)
            items.append((f"../{urls.subject(name)}", name, len(vs), c))
        table = controls.view("sachgebiete", "Die Sachgebiete nach Zahl der Vorgänge",
                              controls.tiles(items, kinds, "Vorgänge", "Vorgang", "Sachgebiete"), table)  # fmt: skip
    else:
        table = '<div class="rows"><div class="empty">Keine Vorgänge mit Sachgebiet im Datenbestand.</div></div>'
    with_subject = len({v["id"] for vs in subjects.values() for v in vs})

    fragen = '<a href="../regierung/index.html#liste">Fragen</a>' if questions else "Fragen"
    n_fragen = none["Schriftliche Frage"] + none["Mündliche Frage"]
    n_petitions = sum(k for t, k in none.items() if t.startswith("Petition"))
    named = {"Schriftliche Frage", "Mündliche Frage", "EU-Vorlage"}
    rest = sorted(((t, k) for t, k in none.items() if t not in named and not t.startswith("Petition")),
                  key=lambda tk: (-tk[1], tk[0]))  # fmt: skip
    items = [
        f"<li><b>Schriftliche und Mündliche Fragen</b> ({n(n_fragen)}). Sie haben statt eines Sachgebiets das "
        f"Ressort, das sie beantwortet. Sie stehen bei den {fragen}.</li>",
        f'<li><b><a href="../{urls.EU}">EU-Vorlagen</a></b> ({n(none["EU-Vorlage"])}). Eine EU-Vorlage ist eine Art '
        "von Vorgang. Sie sagt, woher etwas kommt. Ein Sachgebiet sagt, worum es geht.</li>",
        f"<li><b>Petitionen</b> ({n(n_petitions)})</li>" if n_petitions else
        "<li><b>Petitionen</b>. Sie haben kein Sachgebiet. Im Datenbestand steht keine Petition als Vorgang.</li>",
    ]  # fmt: skip
    if rest:
        items.append("<li><b>Weitere Vorgänge</b> ohne Sachgebiet sind "
                     + ", ".join(f"{e(t)} ({n(k)})" for t, k in rest) + ".</li>")  # fmt: skip
    plenum = ", ".join(f"{n(k)} {e(t if k == 1 else PLURAL[t])}" for t, k in plenary.items())
    body = f"""{subtabs("../", PROCEDURE_TABS, "subjects")}<div class="bills"><h1>Sachgebiete</h1>
<p class="lead">Das Dokumentations- und Informationssystem für Parlamentsmaterialien (DIP) ordnet jeden Vorgang einem
oder mehreren Sachgebieten zu. Die Dokumentation des Bundestages legt sie fest. Hier stehen alle {n(len(subjects))}
Sachgebiete mit dem, was der 21. Bundestag darin getan hat, das größte zuerst. {n(with_subject)} Vorgänge der
Wahlperiode haben ein Sachgebiet. Jede Kachel führt zu ihren Vorgängen, Reden, Abstimmungen und Drucksachen. Ihre
Fläche entspricht der Zahl der Vorgänge, mit einer Mindestgröße, damit jeder Name lesbar bleibt. Der Balken in der
Kachel zeigt die Arten.</p>
<p class="explain">{OVERLAP} „Im Plenum beraten“ zählt die Vorgänge, deren Drucksache ein Tagesordnungspunkt aufruft.
„Beschlüsse“ zählt jeden Beschluss einmal.</p>
{table}
<section class="facet" id="ohne"><h2>Ohne Sachgebiet</h2>
<p class="explain">Diese Vorgänge haben im DIP kein Sachgebiet. Sie fehlen deshalb oben.</p>
<ul>{"".join(items)}</ul>
<p class="explain">Ohne Vorgang im DIP sind {e(plenum)}. Sie stehen bei den
<a href="../{urls.PERIOD}">Sitzungen</a>, die Fragestunden und Regierungsbefragungen auch bei den {fragen}.</p>
</section></div>
<footer>{FOOTER}</footer>"""
    return shell(root="../", kind="p-subjects", active="bills", title="Sachgebiete im Bundestag",
                 desc="Die Arbeit des 21. Deutschen Bundestages nach den Sachgebieten des DIP: Vorgänge, Reden, "
                      "Abstimmungen und Drucksachen.", body=body, data={"kind": "subjects"},
                 head=STYLE + controls.head("../"))  # fmt: skip


def write(conn: sqlite3.Connection, out: Path, procs: list[dict], sittings: list[dict]) -> dict[str, list[dict]]:
    """Write sachgebiete/: the index and one page per Sachgebiet. Call after procedures.write (the Vorgang pages) and
    the speech and Fragen pages, so every link can be checked. Returns the Sachgebiete written."""
    subjects = load(conn, procs)
    drucksachen = {r["id"]: r for r in data.drucksache_facts(conn)}
    have_vorgang = {b["id"] for b in procs}
    for r in drucksachen.values():
        if r["vorgang"] not in have_vorgang:
            r["vorgang"] = None
    have = {f"reden/{p.name}" for p in (out / "reden").glob("*.html")} if (out / "reden").is_dir() else set()
    d = out / "sachgebiete"
    d.mkdir(parents=True, exist_ok=True)
    for name, vs in subjects.items():
        page = subject_page(name, vs, drucksachen, have, [s["date"] for s in sittings])
        (out / urls.subject(name)).write_text(page, encoding="utf-8")
    questions = (out / "regierung" / "index.html").is_file()
    page = index_page(subjects, without_subject(conn), plenary_without_vorgang(sittings), questions)
    (out / urls.SUBJECTS).write_text(page, encoding="utf-8")
    return subjects
