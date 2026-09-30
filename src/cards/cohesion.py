"""Fraktionsdisziplin: `abstimmungen/geschlossenheit.html`, how closely each fraction voted together in the roll-call
votes, and every vote of a member against the own fraction's line.

Built from what the vote pages already load (`data.decisions` and `data.roll_call_members`), with the same line
as the vote pages and the cards (`data.majority`): the most common of yes/no/abstain in the fraction, none on a tie.
No ranking of members: the dissents are listed by date, nothing is counted per person here."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from cards import urls
from cards.data import NO_FRACTION, VOTE_CHOICES, majority
from cards.ui import FOOTER, SHORT, TOKEN, VOTE, dot, e, frac_link, fraction_order, long_date, n, shell, short_date

PAGE = "geschlossenheit"
# the timeline's geometry, in SVG units (the SVG scales to the width of the page)
W, H, PAD_L, PAD_R, PAD_T, PAD_B = 520, 70, 28, 6, 6, 8


def rice(t: Counter) -> float | None:
    """Rice index |yes − no| / (yes + no): 1 when everyone who voted yes or no voted the same way, 0 on an even
    split. None when nobody in the fraction voted yes or no."""
    yes, no = t["yes"], t["no"]
    return abs(yes - no) / (yes + no) if yes + no else None


def cohesion(decisions: list[dict], members: dict[str, list[list]]) -> dict:
    """Per fraction one point per roll-call vote with a list (date, vote, line, Rice value), and every dissent:
    a cast yes/no/abstain that differs from the fraction's line. Absent and invalid are never a dissent, fraktionslos
    has no line. Oldest vote first."""
    votes = sorted((d for d in decisions if d["kind"] == "namentlich" and members.get(d["id"])), key=_vote_order)
    series: dict[str, list[dict]] = {}
    dissents: list[dict] = []
    for i, d in enumerate(votes):
        by_fraction: dict[str, list[list]] = {}
        for m in members[d["id"]]:
            by_fraction.setdefault(m[2], []).append(m)
        for f, ms in sorted(by_fraction.items(), key=lambda kv: fraction_order(kv[0])):
            if f == NO_FRACTION:
                continue
            t = Counter(m[3] for m in ms)
            line = majority(t)
            devs = [m for m in ms if line and m[3] in VOTE_CHOICES and m[3] != line]
            series.setdefault(f, []).append(
                {"vote": d, "order": i, "line": line, "rice": rice(t), "tally": t, "dissents": len(devs)}
            )
            for m in sorted(devs, key=lambda m: m[1]):
                dissents.append({"vote": d, "person": m[0], "name": m[1], "fraction": f, "own": m[3], "line": line})
    return {"votes": votes, "series": dict(sorted(series.items(), key=lambda kv: fraction_order(kv[0]))),
            "dissents": dissents}  # fmt: skip


def _vote_order(d: dict) -> tuple:
    """ "21/90/7": date, sitting, number of the vote in the sitting."""
    parts = d["id"].split("/")
    return (d["date"], *(int(p) if p.isdigit() else 0 for p in parts[1:3]))


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def pct(x: float | None, digits: int = 2) -> str:
    """0.996 -> "0,996" with digits=3: an average close to 1 must not round up to "everyone, always"."""
    if x is None:
        return "–"
    s = f"{x:.{digits}f}"
    if s.startswith("1") and x < 1:
        s = f"{int(x * 10**digits) / 10**digits:.{digits}f}"
    return s.replace(".", ",")


def timeline(f: str, points: list[dict], total: int) -> str:
    """One row of the small multiples: a dot per vote at its Rice value, hollow where the fraction was split (no
    line), the fraction's average as a dashed line. x is the order of the votes, not the calendar."""
    color = f"var(--{TOKEN.get(f, 'reg')})"
    iw, ih = W - PAD_L - PAD_R, H - PAD_T - PAD_B

    def x(i: int) -> float:
        return PAD_L + (iw * i / (total - 1) if total > 1 else iw / 2)

    def y(v: float) -> float:
        return PAD_T + ih * (1 - v)

    grid = "".join(
        f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="g"/>'
        f'<text x="{PAD_L - 6}" y="{y(v) + 3.5:.1f}" class="ax" text-anchor="end">{label}</text>'
        for v, label in ((0, "0"), (0.5, "0,5"), (1, "1"))
    )
    marks = []
    for p in points:
        if p["rice"] is None:
            continue
        d = p["vote"]
        i = p["order"]
        line = VOTE[p["line"]] if p["line"] else "gespalten"
        t = p["tally"]
        tip = (f"{short_date(d['date'])} · {d['title']}\nLinie: {line} · Ja {t['yes']}, Nein {t['no']}, "
               f"Enthaltung {t['abstain']} · Geschlossenheit {pct(p['rice'])}")  # fmt: skip
        fill = color if p["line"] else "var(--card)"
        marks.append(
            f'<a href="../{e(urls.decision(d))}"><circle cx="{x(i):.1f}" cy="{y(p["rice"]):.1f}" r="3" fill="{fill}" '
            f'stroke="{color}" stroke-width="1.5"><title>{e(tip)}</title></circle></a>'
        )
    avg = mean([p["rice"] for p in points if p["rice"] is not None])
    avg_line = (f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(avg):.1f}" y2="{y(avg):.1f}" class="avg" '
                f'stroke="{color}"/>' if avg is not None else "")  # fmt: skip
    return (f'<svg viewBox="0 0 {W} {H}" class="tl" role="img" aria-label="Geschlossenheit {e(SHORT.get(f, f))} je '
            f'Abstimmung, Durchschnitt {pct(avg, 3)}">{grid}{avg_line}{"".join(marks)}</svg>')  # fmt: skip


def axis(votes: list[dict]) -> str:
    """Month labels under the last timeline, at the first vote of each month (where there is room)."""
    total = len(votes)
    iw = W - PAD_L - PAD_R
    seen, labels, last = set(), [], -99.0
    for i, d in enumerate(votes):
        month = d["date"][:7]
        if month in seen:
            continue
        seen.add(month)
        xv = PAD_L + (iw * i / (total - 1) if total > 1 else iw / 2)
        if xv - last < 30:  # a month with few votes: its label would run into the next one
            continue
        last = xv
        labels.append(f'<text x="{xv:.1f}" y="12" class="ax">{d["date"][5:7]}/{d["date"][2:4]}</text>')
    return f'<svg viewBox="0 0 {W} 16" class="tl axis" aria-hidden="true">{"".join(labels)}</svg>'


STYLE = """<style>
.p-cohesion h1 { font-size: 26px; font-weight: 600; letter-spacing: -.02em; margin: 8px 0 6px; }
.p-cohesion h2 { font-size: 13px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 28px 0 8px; }
.p-cohesion h2 .n { color: var(--faint); font-weight: 500; letter-spacing: 0; text-transform: none; margin-left: 6px; }
.coh .fr:first-child { margin-top: 0; }
.coh .fr { margin: 18px 0 4px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.coh .fr b { font-weight: 600; }
.coh .fr .m { color: var(--muted); font-size: 13px; }
.coh .scroll { overflow-x: auto; }
.coh svg.tl { display: block; width: 100%; min-width: 460px; height: auto; overflow: visible; }
.coh svg.tl .g { stroke: var(--line); stroke-width: 1; }
.coh svg.tl .avg { stroke-width: 1.5; stroke-dasharray: 5 4; opacity: .7; }
.coh svg.tl .ax { fill: var(--faint); font-size: 9px; }
.coh svg.tl a:hover circle { stroke-width: 3; }
.coh table.dis { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.coh table.dis th { text-align: left; font-weight: 500; color: var(--muted); font-size: 12px; padding: 6px 8px; border-bottom: 1px solid var(--line); }
.coh table.dis td { padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
.coh table.dis td.d { white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--muted); }
.coh table.dis td.o, .coh table.dis td.f { white-space: nowrap; }
.coh dl.def + .explain { margin-top: 12px; }
.coh table.dis .ti { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.coh .filters { margin: 10px 0; }
.coh dl.def { margin: 0; } .coh dl.def dt { font-weight: 600; margin-top: 10px; } .coh dl.def dd { margin: 2px 0 0; }
/* phone: one block per dissent, date and vote on top, then the vote's title, then the member */
@media (max-width: 600px) {
  .coh table.dis thead { display: none; }
  .coh table.dis tr { display: grid; grid-template-columns: 1fr auto; gap: 2px 10px; padding: 8px 12px; border-bottom: 1px solid var(--line); }
  .coh table.dis tr[hidden] { display: none; }
  .coh table.dis td { padding: 0; border: 0; }
  .coh table.dis td.t { grid-column: 1 / -1; grid-row: 2; }
  .coh table.dis td.o { grid-column: 2; grid-row: 1; }
  .coh table.dis td.w { grid-column: 1; grid-row: 3; }
  .coh table.dis td.f { grid-column: 2; grid-row: 3; color: var(--muted); font-size: 12.5px; }
}
</style>"""  # noqa: E501

FILTER = """<script>
(function () {
  const sel = document.getElementById('fr'), rows = document.querySelectorAll('#dis tbody tr'), count = document.getElementById('count');
  function apply() {
    let k = 0;
    rows.forEach(r => { const on = !sel.value || r.dataset.f === sel.value; r.hidden = !on; if (on) k++; });
    count.textContent = k.toLocaleString('de-DE') + ' Abweichungen';
  }
  sel.addEventListener('change', apply);
  apply();
})();
</script>"""  # noqa: E501


def page(decisions: list[dict], members: dict[str, list[list]]) -> str:
    c = cohesion(decisions, members)
    votes, series, dissents = c["votes"], c["series"], c["dissents"]
    blocks = []
    for f, points in series.items():
        values = [p["rice"] for p in points if p["rice"] is not None]
        split = sum(1 for p in points if p["line"] is None)
        devs = sum(p["dissents"] for p in points)
        facts = [f"Durchschnitt <b>{pct(mean(values), 3)}</b>", f"{n(len(points))} Abstimmungen"]
        if split:
            facts.append(f"{n(split)}-mal gespalten")
        facts.append(f"{n(devs)} Abweichungen")
        blocks.append(f'<div class="fr">{dot(f)} <b>{frac_link(f)}</b> <span class="m">{" · ".join(facts)}</span></div>'
                      + timeline(f, points, len(votes)))  # fmt: skip
    if votes:
        blocks.append(axis(votes))
    rows = []
    for x in reversed(dissents):  # newest first
        d = x["vote"]
        who = f'<a href="../{e(x["person"])}.html">{e(x["name"])}</a>' if x["person"] else e(x["name"])
        rows.append(
            f'<tr data-f="{e(x["fraction"])}"><td class="d">{e(short_date(d["date"]))}</td>'
            f'<td class="t"><a class="ti" href="../{e(urls.decision(d))}">{e(d["title"])}</a></td>'
            f'<td class="w">{who}</td>'
            f'<td class="f">{dot(x["fraction"])} {frac_link(x["fraction"])}</td>'
            f'<td class="o"><span class="vote {x["own"]}">{VOTE[x["own"]]}</span> '
            f'<span class="faint">statt {VOTE[x["line"]]}</span></td></tr>'
        )
    options = "".join(f'<option value="{e(f)}">{e(f)}</option>' for f in series)
    first = long_date(votes[0]["date"]) if votes else ""
    body = f"""<div class="coh">
<p class="crumbs"><a href="index.html">Abstimmungen</a></p>
<h1>Geschlossenheit der Fraktionen</h1>
<p class="lead">Wie einheitlich haben die Fraktionen in den {n(len(votes))} namentlichen Abstimmungen seit {e(first)} abgestimmt, und wer hat anders gestimmt als die eigene Fraktion? Hier stehen nur namentliche Abstimmungen: Nur bei ihnen ist die Stimme jedes Mitglieds bekannt.</p>
<h2>So ist gerechnet</h2>
<dl class="def">
<dt>Fraktionslinie</dt><dd>Die Stimme, die in der Fraktion bei dieser Abstimmung am häufigsten abgegeben wurde: Ja, Nein oder Enthaltung. Liegen zwei davon gleichauf, hat die Fraktion keine Linie, sie war <b>gespalten</b>. Fraktionslose haben keine Linie.</dd>
<dt>Abweichung</dt><dd>Ein Mitglied hat Ja, Nein oder Enthaltung gestimmt, und das ist nicht die Fraktionslinie. Wer nicht abgestimmt hat oder eine ungültige Stimme abgegeben hat, weicht nie ab: Das Fehlen hat viele Gründe (Krankheit, Elternzeit, Dienstreise, Absprachen), die nicht in den Listen stehen.</dd>
<dt>Geschlossenheit</dt><dd>Der Rice-Index: |Ja − Nein| geteilt durch (Ja + Nein) der Fraktion. 1 heißt: alle, die Ja oder Nein gestimmt haben, haben gleich gestimmt; 0 heißt: genau halb Ja, halb Nein. Enthaltungen zählen in diesem Wert nicht mit (sie gelten aber als Abweichung, wenn die Linie Ja oder Nein war). Hat niemand in der Fraktion Ja oder Nein gestimmt, gibt es keinen Wert.</dd>
</dl>
<p class="explain">Die Zahlen sagen nichts darüber, ob eine Abweichung abgesprochen war (etwa eine Gewissensentscheidung oder eine persönliche Erklärung im Protokoll). Jede Zeile führt zur Abstimmung mit der Abstimmungsliste als Quelle.</p>
<h2>Je Abstimmung <span class="n">ein Punkt, von der ersten (links) zur neuesten (rechts)</span></h2>
<div class="chart"><div class="scroll">{"".join(blocks)}</div>
<p class="note">Gestrichelt: der Durchschnitt der Fraktion. Hohler Punkt: Die Fraktion war gespalten. Punkt antippen oder anklicken öffnet die Abstimmung.</p></div>
<h2>Alle Abweichungen <span class="n">die neueste zuerst</span></h2>
<div class="filters"><select id="fr" aria-label="Fraktion"><option value="">alle Fraktionen</option>{options}</select></div>
<div class="count" id="count">{n(len(dissents))} Abweichungen</div>
<div class="rows"><table class="dis" id="dis"><thead><tr><th>Datum</th><th>Abstimmung</th><th>Mitglied</th><th>Fraktion</th><th>Stimme</th></tr></thead><tbody>
{"".join(rows)}
</tbody></table></div>
</div>
<footer>{FOOTER}</footer>{FILTER}"""  # noqa: E501
    desc = (f"Wie geschlossen die Fraktionen des 21. Deutschen Bundestages in {len(votes)} namentlichen Abstimmungen "
            "gestimmt haben, und jede Abweichung von der Fraktionslinie, mit Quelle.")  # fmt: skip
    return shell(root="../", kind="p-cohesion", active="votes", title="Geschlossenheit der Fraktionen", desc=desc,
                 head=STYLE, body=body, data={"kind": "cohesion"})  # fmt: skip


def write_page(out: Path, decisions: list[dict], members: dict[str, list[list]]) -> int:
    """Write abstimmungen/geschlossenheit.html; nothing without roll-call lists. Returns the number of pages."""
    if not any(members.get(d["id"]) for d in decisions if d["kind"] == "namentlich"):
        return 0
    (out / "abstimmungen").mkdir(parents=True, exist_ok=True)
    (out / "abstimmungen" / f"{PAGE}.html").write_text(page(decisions, members), encoding="utf-8")
    return 1
