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
  <h1>Was im Bundestag <span class="r">passiert</span>. Und was es <span class="v">bedeutet</span>.</h1>
  <p class="lead">Jede Rede, jede Abstimmung, jedes Mitglied, mit Quelle zum Nachprüfen. Und ein Radar für die
  Themen, die den Bundestag bewegen.</p>
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
<p class="hint">{n(len(seats))} Sitze. Jeder Punkt führt zu einer Karte.</p></div>
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
        ("abgeordnete.html", "Abgeordnete", "Eine Karte je Mitglied: Reden, Stimmen, Ausschüsse.",
         f"{n(len(members))} Karten"),
        ("orte/index.html", "Orte", "Wer vertritt mein Land, meinen Wahlkreis, meine Gemeinde?", "299 Wahlkreise"),
        ("vorgaenge/index.html", "Vorgänge", "Gesetze und Anträge vom Entwurf bis zum Beschluss.", n(procedures)),
        ("sitzungen/index.html", "Sitzungen", "Jede Sitzungswoche, jede Tagesordnung, jede Rede.", n(len(sittings))),
        ("abstimmungen/index.html", "Abstimmungen", "Namentlich und per Handzeichen, mit Ergebnis.",
         f"{n(n_rc)} namentlich"),
        ("regierung/index.html", "Fragen", "Was Abgeordnete die Bundesregierung fragen, und wer antwortet."),
        ("gremien/index.html", "Gremien", "Fraktionen, Ausschüsse, Regierung und wer darin sitzt."),
        ("debatte/index.html", "Debattenkultur", "Zwischenrufe, Beifall, Ordnungsrufe: gezählt."),
        ("daten.html", "Daten", "Alles als offene Daten zum Herunterladen, mit Quellen."),
    )  # fmt: skip
    research = f"""<section class="world research" id="recherche">
<span class="tagline">Recherche</span>
<h2>Was ist passiert?</h2>
<p>Nachprüfbare Fakten aus den amtlichen Quellen: Plenarprotokolle, Abstimmungen, Drucksachen. Jede Angabe führt
zu ihrer Quelle.</p>
<div class="tiles">{"".join(_tile(*t) for t in tiles)}</div>
</section>"""

    radar_tiles = []
    if landscape:
        radar_tiles.append(_tile(LANDSCAPE, "Themenlandschaft", "Alle Reden einer Woche als Karte, nach Ähnlichkeit "
                                 "gruppiert: worüber gestritten wird.", "jede Sitzungswoche"))  # fmt: skip
    if themes:
        radar_tiles.append(_tile(urls.THEMES, "Themen der Wahlperiode", "Die großen Themen über alle Wochen, mit "
                                 "Fraktionen und Vorgängen.", f"{n(themes)} Themen"))  # fmt: skip
    if compass:
        radar_tiles.append(_tile("kompass.html", "Wer stimmt wie ich?", "Ausgewählte Abstimmungen als Quiz: welcher "
                                 "Fraktion komme ich am nächsten?", "läuft nur im Browser"))  # fmt: skip
    radar = (f"""<section class="world radar" id="radar">
<span class="tagline">{RADAR_ICON}Radar</span>
<h2>Was bewegt sich?</h2>
<p>Auswahl und Deutung: Themen, die ein Modell in den Reden findet, und kuratierte Fragen. Das Radar kann irren,
aber nie unnachvollziehbar.</p>
<div class="tiles">{"".join(radar_tiles)}</div>
<p class="fine">Violett heißt auf dieser Seite immer: hier wird ausgewählt oder gedeutet. Jedes Ergebnis führt zu
seinen Belegen in der Recherche, und die sind blau.</p>
</section>""" if radar_tiles else "")  # fmt: skip

    recent = ""
    if last:
        week = [s for s in sittings if s["week"] == last["week"]]
        wk_speeches = sum(len(i["speeches"]) for s in week for i in s["items"])
        ids = {s["id"] for s in week}
        wk_dec = [d for d in decisions if d["sitting"] in ids]
        days = f"{long_date(week[0]['date'])} bis {long_date(week[-1]['date'])}" if len(week) > 1 \
            else long_date(week[0]["date"])  # fmt: skip
        go = [f'<a href="{e(urls.week(last["week"]))}">Die Woche in Sätzen, Reden und Beschlüssen</a>',
              f'<a href="{e(urls.sitting(last["id"]))}">Die letzte Sitzung: {last["number"]}. Sitzung, '
              f'{e(short_date(last["date"]))}</a>']  # fmt: skip
        if landscape:
            go.append(f'<a class="rl" href="{e(LANDSCAPE)}{e(last["week"])}.html">Worüber debattiert wurde: die Woche '
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

    body = (f'{hero}{numbers}<h2 class="worlds-h">Zwei Wege in den Bundestag</h2>'
            f'<div class="worlds">{research}{radar}</div>{recent}<footer>{FOOTER}</footer>{SCRIPT}')  # fmt: skip
    desc = ("Der 21. Deutsche Bundestag zum Nachschlagen: Abgeordnete, Reden, Abstimmungen, Vorgänge und Sitzungen, "
            "jede Angabe mit Quelle; dazu ein Radar für die Themen der Debatten.")  # fmt: skip
    data = {"kind": "home", "seats": seats, "token": TOKEN}
    return shell(root="", kind="p-home", active="home", title="plenar-radar.de – der Bundestag, nachprüfbar",
                 desc=desc, body=body, data=data, head=HEAD, mode="home")  # fmt: skip


def write(out: Path, *args, **kwargs) -> None:
    """Write the front page; the arguments as `page`."""
    (out / "index.html").write_text(page(*args, **kwargs), encoding="utf-8")
