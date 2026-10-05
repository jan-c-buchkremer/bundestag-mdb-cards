"""The front page `index.html` (docs/plan.md, "Current goal"): what the site offers, and the way there in one click.

It belongs to both parts of the site (docs/architecture.md): a hero with the house as it sits today (parliament.js,
every seat a link to its card), the size of the record in a few numbers, then the two parts side by side, Recherche
(blue, checkable facts) and Radar (violet, selection and interpretation), and the latest sitting week. Everything on
it is counted from the store or links to a page that exists; a Radar part that was not built (no Themenlandschaft
data, no Kompass) is left out. The Abgeordnete list that used to be here is `abgeordnete.html`; an old link with a
fragment (`/#ort=…`, `/#rollen`) is forwarded there."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from research import facts, urls
from research.data import NO_FRACTION, index_row
from research.ui import (
    FOOTER,
    LANDSCAPE,
    ORDER,
    RADAR_ICON,
    SHORT,
    TOKEN,
    dot,
    e,
    long_date,
    n,
    shell,
    short_date,
)
from research.weekly import week_label

LATEST_VOTES = 4  # roll-call votes in "Zuletzt im Plenum"

HEAD = """<script>
// an old link to the Abgeordnete list (it was the front page until 2026-10): /#ort=…, /#rollen, … go there
if (location.hash.length > 1) location.replace('abgeordnete.html' + location.search + location.hash);
</script>
<script src="parliament.js"></script>
<link rel="stylesheet" href="landing.css">"""

SCRIPT = '<script src="landing.js" defer></script>'  # after the shell defines PAGE


def _tile(href: str, title: str, desc: str, k: str = "") -> str:
    count = f'<span class="k">{k}</span>' if k else ""
    return f'<a class="tile" href="{e(href)}"><span class="t">{e(title)}</span><span class="d">{desc}</span>{count}</a>'


def page(
    cards: list[dict],
    meta: dict,
    sittings: list[dict],
    decisions: list[dict],
    *,
    speeches: int,
    procedures: int,
    themes: int,
    compass: bool,
    landscape: bool,
) -> str:
    members = [c for c in cards if c["kind"] == "member"]
    current = [index_row(c) for c in members if not (c["mandate"] or {}).get("to")]
    seats = [{k: r[k] for k in ("id", "name", "last", "fraction", "lead", "state", "photo", "office")}
             for r in current]  # fmt: skip
    seats = [{**s, "fraction": s["fraction"] or NO_FRACTION} for s in seats]
    per = Counter(s["fraction"] for s in seats)
    legend = "".join(f"<span>{dot(f)}{e(SHORT.get(f, f))} <b>{per[f]}</b></span>" for f in ORDER if f in per)
    last = sittings[-1] if sittings else None
    frm, to = (meta.get("sittings") or {}).get("from"), (meta.get("sittings") or {}).get("to")
    since = f"seit {long_date(frm)}" if frm else ""
    upto = f"Plenarprotokolle bis {short_date(to)}" if to else ""

    quick = ['<a href="orte/index.html#suche">Mein Wahlkreis</a>']
    if last:
        quick.append(f'<a href="{e(urls.week(last["week"]))}">Die letzte Sitzungswoche</a>')
    if compass:
        quick.append(f'<a class="rq" href="kompass.html">{RADAR_ICON}Wer stimmt wie ich?</a>')
    hero = f"""<section class="hero">
<div>
  <span class="eyebrow"><span class="live"></span>21. Deutscher Bundestag{f" · {e(upto)}" if upto else ""}</span>
  <h1>Den Bundestag <span class="r">recherchieren</span>. Seine Arbeit <span class="v">verstehen</span>.</h1>
  <p class="lead">Alle Reden, Vorgänge und Mitglieder, mit den offiziellen Quellen zum Nachprüfen. Ein Radar für
  die erweiterte Analyse.</p>
  <form class="bigq" role="search" action="suche.html">
    <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="none"
    stroke="currentColor" stroke-width="1.6"/><path d="M11 11l3.5 3.5" stroke="currentColor" stroke-width="1.6"
    stroke-linecap="round"/></svg>
    <input type="search" name="q" placeholder="Person, Ort, Gesetz, Thema …" aria-label="Suche" autocomplete="off">
    <button type="submit">Suchen</button>
  </form>
  <div class="quick">{"".join(quick)}</div>
</div>
<div class="house"><div id="chart"></div><div class="cap">{legend}</div>
<p class="hint">{n(len(seats))} Sitze. Jeder Punkt führt zu einer Person.</p></div>
</section>"""

    n_dec = len(decisions)
    numbers = (
        '<section class="numbers" aria-label="Der Datenbestand">'
        f'<a href="abgeordnete.html"><b>{n(len(members))}</b><span>Abgeordnete in der Wahlperiode</span></a>'
        f'<a href="sitzungen/index.html"><b>{n(len(sittings))}</b><span>Sitzungen {e(since)}</span></a>'
        f'<a href="suche.html"><b>{n(speeches)}</b><span>Reden im Volltext</span></a>'
        f'<a href="abstimmungen/index.html"><b>{n(n_dec)}</b><span>Abstimmungen und Beschlüsse</span></a>'
        f'<a href="vorgaenge/index.html"><b>{n(procedures)}</b><span>Vorgänge</span></a>'
        "</section>"
    )

    n_rc = sum(1 for d in decisions if d["kind"] == "namentlich")
    tiles = (
        ("abgeordnete.html", "Abgeordnete",
         "Ein Steckbrief pro Mitglied: Zugehörigkeiten, Reden, Ausschüsse und Herkunft.",
         f"{n(len(members))} Steckbriefe"),
        ("orte/index.html", "Orte", "Abgeordnete nach Land, Wahlkreis und Gemeinde.", "299 Wahlkreise"),
        ("vorgaenge/index.html", "Vorgänge", "Gesetze und Anträge vom Entwurf bis zum Beschluss.", n(procedures)),
        ("sitzungen/index.html", "Sitzungen", "Sitzungswochen mit Tagesordnung und Reden.", n(len(sittings))),
        ("abstimmungen/index.html", "Abstimmungen", "Namentlich und per Handzeichen.",
         f"{n(n_rc)} namentlich"),
        ("regierung/index.html", "Fragen", "Was Abgeordnete die Bundesregierung fragen und wie sie antwortet."),
        ("gremien/index.html", "Gremien", "Fraktionen, Ausschüsse und Ämter."),
        ("debatte/index.html", "Debattenkultur", "Statistische Kennzahlen über Beiträge und Verhalten im Bundestag."),
        ("daten.html", "Daten", "Über die Daten und Downloads."),
    )  # fmt: skip
    research = f"""<section class="world research" id="recherche">
<span class="tagline">Recherche</span>
<h2>Fakten</h2>
<p>Die Arbeit des Bundestages aus den amtlichen Quellen: Plenarprotokolle, Abstimmungen, Drucksachen. Jede Angabe
führt zu ihrer Quelle.</p>
<div class="tiles">{"".join(_tile(*t) for t in tiles)}</div>
</section>"""

    radar_tiles = []
    if landscape:
        radar_tiles.append(_tile(LANDSCAPE, "Themenlandschaft", "Zu jeder Sitzungswoche eine Landkarte ihrer Themen. "
                                 "Interaktiv und informativ.", "jede Sitzungswoche"))  # fmt: skip
    if themes:
        radar_tiles.append(_tile(urls.THEMES, "Themen der Wahlperiode", "Die Themen der gesamten Wahlperiode mit "
                                 "Fraktionen und Vorgängen.", f"{n(themes)} Themen"))  # fmt: skip
    if compass:
        radar_tiles.append(_tile("kompass.html", "Wer stimmt wie ich?", "Ausgewählte Abstimmungen als Quiz, im "
                                 "Vergleich mit den Fraktionen.", "läuft nur im Browser"))  # fmt: skip
    radar = (f"""<section class="world radar" id="radar">
<span class="tagline">{RADAR_ICON}Radar</span>
<h2>Analyse</h2>
<p>Datengetriebene Werkzeuge: automatisierte Extraktion von Themen im Bundestag, eine kuratierte
Abstimmungssimulation und bald weitere Features.</p>
<div class="tiles">{"".join(radar_tiles)}</div>
<p class="fine">Violett heißt auf dieser Seite immer: dieses Tool kann keine absolute Objektivität mehr
gewährleisten. Jedes Element führt jedoch zu seiner Datengrundlage in der Recherche-Plattform, wo die Fakten sich
befinden.</p>
</section>""" if radar_tiles else "")  # fmt: skip

    recent = ""
    if last:
        week = [s for s in sittings if s["week"] == last["week"]]
        wk_speeches = sum(len(i["speeches"]) for s in week for i in s["items"])
        ids = {s["id"] for s in week}
        wk_dec = [d for d in decisions if d["sitting"] in ids]
        days = f"{long_date(week[0]['date'])} bis {long_date(week[-1]['date'])}" if len(week) > 1 \
            else long_date(week[0]["date"])  # fmt: skip
        go = [f'<a href="{e(urls.week(last["week"]))}">Die Sitzungswoche mit Reden und Beschlüssen</a>',
              f'<a href="{e(urls.sitting(last["id"]))}">Die letzte Sitzung: {last["number"]}. Sitzung, '
              f'{e(short_date(last["date"]))}</a>']  # fmt: skip
        if landscape:
            go.append(f'<a class="rl" href="{e(LANDSCAPE)}{e(last["week"])}.html">Die Themen der Woche '
                      "in der Themenlandschaft</a>")  # fmt: skip
        rc = sorted((d for d in decisions if d["kind"] == "namentlich"), key=lambda d: (d["date"], d["order"]))
        votes = facts.decision_list(rc[-LATEST_VOTES:][::-1], "", limit=None, agenda=False)
        recent = f"""<section class="recent">
<h2>Zuletzt im Plenum</h2>
<div class="cols">
<div class="wk"><span class="when">{e(days)}</span>
<h3><a href="{e(urls.week(last["week"]))}">{e(week_label(last["week"]))}</a></h3>
<div class="facts3"><div><b>{len(week)}</b><span>{"Sitzung" if len(week) == 1 else "Sitzungen"}</span></div>
<div><b>{n(wk_speeches)}</b><span>Reden</span></div><div><b>{n(len(wk_dec))}</b><span>Beschlüsse</span></div></div>
<div class="go">{"".join(go)}</div></div>
<div class="vl"><h3>Die letzten namentlichen Abstimmungen</h3>{votes}
<a class="all" href="abstimmungen/index.html">Alle Abstimmungen und Beschlüsse →</a></div>
</div>
</section>"""

    body = (f'{hero}{numbers}<h2 class="worlds-h">Recherche und Analyse</h2>'
            f'<div class="worlds">{research}{radar}</div>{recent}<footer>{FOOTER}</footer>{SCRIPT}')  # fmt: skip
    desc = ("Den 21. Deutschen Bundestag recherchieren: Abgeordnete, Reden, Abstimmungen, Vorgänge und Sitzungen "
            "mit den offiziellen Quellen. Dazu ein Radar für die erweiterte Analyse.")  # fmt: skip
    data = {"kind": "home", "seats": seats, "token": TOKEN}
    title = "plenar-radar.de – den Bundestag recherchieren und verstehen"
    return shell(root="", kind="p-home", active="home", title=title,
                 desc=desc, body=body, data=data, head=HEAD, mode="home")  # fmt: skip


def write(out: Path, *args, **kwargs) -> None:
    """Write the front page; the arguments as `page`."""
    (out / "index.html").write_text(page(*args, **kwargs), encoding="utf-8")
