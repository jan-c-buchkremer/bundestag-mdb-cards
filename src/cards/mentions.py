"""Erwähnungen: `erwaehnungen/index.html` and one page per country, Land, Gemeinde or organisation the speeches
name, `erwaehnungen/<Wikidata QID>.html`.

The landscape (`landscape mentions`) finds the names with a local NER model and links them to Wikidata QIDs; this
module reads its `mentions.json` from LANDSCAPE_MENTIONS ({speech id: {QID: count}}, the foundation's speech ids
including the `-2` parts) and draws the pages. Without the file no pages are written.

A page shows how often the entity is named per month and per fraction, and lists every speech that names it, each
linking to the speech page and through it to the protocol. Fractions are compared as a share of their own speeches,
since a fraction with more speeches names everything more often. Nothing is ranked by person: the list is by date."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from cards.data import page_id
from cards.debate import GOVERNMENT, OTHER, speaker_group
from cards.pages import FOOTER, MONTHS, ORDER, SHORT, dot, e, fraction_order, n, search_marks, shell, short_date

MIN_SPEECHES = 3  # an entity with fewer speeches gets no page: mostly a wrongly tagged name
KINDS = {
    "land": "Bundesländer",
    "staat": "Staaten und Gebiete",
    "gemeinde": "Gemeinden",
    "organisation": "Organisationen",
}
KIND_ONE = {"land": "Bundesland", "staat": "Staat oder Gebiet", "gemeinde": "Gemeinde", "organisation": "Organisation"}
WIKIDATA = "https://www.wikidata.org/wiki/"
LANDSCAPE_REPO = "https://github.com/jan-c-buchkremer/bundestag-topic-landscape"
W, H, PAD_L, PAD_B, PAD_T = 520, 110, 30, 16, 6  # the monthly chart, in SVG units


def load(path: str | os.PathLike | None = None) -> dict | None:
    """The landscape's mentions.json from LANDSCAPE_MENTIONS; None when it is not set, not there or not readable."""
    path = path or os.environ.get("LANDSCAPE_MENTIONS")
    if not path or not Path(path).is_file():
        return None
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        print(f"{path}: not readable ({err}), no erwaehnungen/ pages")
        return None
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("entities"), dict)
        or not isinstance(raw.get("speeches"), dict)
    ):
        return None
    return raw


def group_order(g: str) -> tuple[int, str]:
    if g == GOVERNMENT:
        return (len(ORDER), g)
    if g == OTHER:
        return (len(ORDER) + 1, g)
    return fraction_order(g)


def aggregate(payload: dict, redes: list[dict]) -> dict:
    """Per entity the speech parts that name it, and per group (fraction, government, other) the parts in all.

    A part is one speaker's turn (a Zwischenfrage is a part of its own, with its own fraction). The Fragestunde and
    the chair are left out, as in the speaking shares of Debattenkultur."""
    totals: Counter = Counter()
    hits: dict[str, list[dict]] = defaultdict(list)
    for r in redes:
        if r.get("kind") == "fragestunde":
            continue
        for p in r["parts"]:
            group = speaker_group(p["role"], p["fraction"])
            if group is None:
                continue
            totals[group] += 1
            for qid, count in (payload["speeches"].get(p["id"]) or {}).items():
                if qid in payload["entities"]:
                    hits[qid].append({"rede": r, "part": p, "group": group, "count": count})
    return {"totals": totals, "hits": hits, "months": sorted({r["date"][:7] for r in redes})}


def month_span(first: str, last: str) -> list[str]:
    """Every month from first to last ("2025-03" … "2026-09"), also the ones without a sitting."""
    y, m = int(first[:4]), int(first[5:])
    out = []
    while (y, m) <= (int(last[:4]), int(last[5:])):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def month_name(m: str) -> str:
    return f"{MONTHS[int(m[5:]) - 1]} {m[:4]}"


def chart(counts: Counter, months: list[str]) -> str:
    """Bars: speeches naming the entity per month. Each bar links to the first such speech of the month in the
    list below (`#m-2026-03`)."""
    top = max(counts.values(), default=1)
    iw, ih = W - PAD_L - 4, H - PAD_T - PAD_B
    slot = iw / len(months)
    bars, labels = [], []
    for i, m in enumerate(months):
        c = counts.get(m, 0)
        x = PAD_L + i * slot
        if c:
            h = ih * c / top
            bars.append(
                f'<a href="#m-{m}"><rect x="{x + slot * 0.12:.1f}" y="{PAD_T + ih - h:.1f}" width="{slot * 0.76:.1f}" '
                f'height="{h:.1f}" rx="1.5"><title>{e(month_name(m))}: {n(c)} {"Rede" if c == 1 else "Reden"}'
                "</title></rect></a>"
            )
        if m[5:] in ("01", "04", "07", "10") or i == 0:
            labels.append(
                f'<text x="{x + slot / 2:.1f}" y="{H - 3}" class="ax" text-anchor="middle">{m[5:]}/{m[2:4]}</text>'
            )
    grid = "".join(
        f'<line x1="{PAD_L}" x2="{W - 4}" y1="{y:.1f}" y2="{y:.1f}" class="g"/>'
        f'<text x="{PAD_L - 5}" y="{y + 3.5:.1f}" class="ax" text-anchor="end">{n(v)}</text>'
        for v, y in ((0, PAD_T + ih), (top, PAD_T))
    )
    return (f'<svg viewBox="0 0 {W} {H}" class="bars" role="img" aria-label="Reden je Monat, die den Eintrag '
            f'nennen">{grid}{"".join(bars)}{"".join(labels)}</svg>')  # fmt: skip


def pct(part: int, whole: int) -> str:
    if not whole:
        return "–"
    p = 100 * part / whole
    return (f"{p:.1f}" if p < 10 else f"{p:.0f}").replace(".", ",") + " %"


STYLE = """<style>
.p-mentions h1 { font-size: 26px; font-weight: 600; letter-spacing: -.02em; margin: 8px 0 6px; }
.p-mentions h2 { font-size: 13px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 28px 0 8px; }
.p-mentions h2 .n { color: var(--faint); font-weight: 500; letter-spacing: 0; text-transform: none; margin-left: 6px; }
.p-mentions .kind { color: var(--muted); font-size: 13.5px; margin: 0 0 12px; }
.p-mentions svg.bars { display: block; width: 100%; height: auto; }
.p-mentions svg.bars rect { fill: var(--accent, #4a6fa5); }
.p-mentions svg.bars a:hover rect { opacity: .7; }
.p-mentions svg.bars .g { stroke: var(--line); stroke-width: 1; }
.p-mentions svg.bars .ax { fill: var(--faint); font-size: 9px; }
.p-mentions table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.p-mentions th { text-align: left; font-weight: 500; color: var(--muted); font-size: 12px; padding: 6px 8px; border-bottom: 1px solid var(--line); }
.p-mentions td { padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
.p-mentions th.r, .p-mentions td.r { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.p-mentions td.d { white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--muted); }
.p-mentions td.f { white-space: nowrap; }
.p-mentions tr.mh td { background: var(--card); color: var(--muted); font-size: 12px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; padding-top: 10px; }
.p-mentions .scroll { overflow-x: auto; }
.p-mentions dl.def { margin: 0; } .p-mentions dl.def dt { font-weight: 600; margin-top: 10px; } .p-mentions dl.def dd { margin: 2px 0 0; }
@media (max-width: 600px) {
  .p-mentions table.list thead { display: none; }
  .p-mentions table.list tr:not(.mh) { display: grid; grid-template-columns: 1fr auto; gap: 2px 10px; padding: 8px 4px; border-bottom: 1px solid var(--line); }
  .p-mentions table.list tr[hidden] { display: none; }
  .p-mentions table.list td { padding: 0; border: 0; }
  .p-mentions table.list td.t { grid-column: 1 / -1; grid-row: 2; }
}
</style>"""  # noqa: E501

FILTER = """<script>
(function () {
  const rows = document.querySelectorAll('#list tbody tr'), count = document.getElementById('count');
  let f = null;
  function apply() {
    let k = 0;
    rows.forEach(r => {
      if (r.classList.contains('mh')) { r.hidden = !!f; return; }
      const on = !f || r.dataset.f === f; r.hidden = !on; if (on) k++;
    });
    count.textContent = (f ? f + ': ' : '') + k.toLocaleString('de-DE') + ' Reden';
    if (f) { const a = document.createElement('a'); a.href = '#list'; a.textContent = ' · alle anzeigen'; a.addEventListener('click', ev => { ev.preventDefault(); f = null; apply(); }); count.appendChild(a); }
    if (f) document.getElementById('list').scrollIntoView();
  }
  document.querySelectorAll('a[data-f]').forEach(a => a.addEventListener('click', ev => {
    ev.preventDefault(); f = a.dataset.f; apply();
  }));
  apply();
})();
</script>"""  # noqa: E501

NOTE = (
    "Erkannt werden nur Namen, die in den Listen stehen (Staaten, Bundesländer, Gemeinden ab 50.000 Einwohnern und "
    "eine geprüfte Auswahl von Organisationen, auch mit gängigen Kürzeln wie EU oder NATO); Umschreibungen "
    "(‚die Bahn‘, ‚Brüssel‘) und Adjektive (‚deutsche‘, ‚Berliner‘) zählen nicht. Namen, die zugleich Wörter oder "
    "Familiennamen sind (Essen, Halle, Hagen), sind ausgenommen. Berlin, Hamburg und Bremen sind Land und Stadt "
    "zugleich, und „Berlin“ steht oft für die Bundesregierung; die Zählung unterscheidet das nicht. Die Zahlen sind "
    "deshalb Untergrenzen und können einzelne Fehltreffer enthalten."
)


def entity_page(qid: str, ent: dict, hits: list[dict], agg: dict, cards: set[str], model: str) -> str:
    totals = agg["totals"]
    hits = sorted(hits, key=lambda h: (h["rede"]["date"], h["rede"]["number"], h["part"]["id"]), reverse=True)
    per_month = Counter(h["rede"]["date"][:7] for h in hits)
    by_group: dict[str, list[dict]] = defaultdict(list)
    for h in hits:
        by_group[h["group"]].append(h)
    months = month_span(min(per_month), max(per_month)) if per_month else []
    months = month_span(min(months[0], agg["months"][0]), max(months[-1], agg["months"][-1])) if months else months
    total_mentions = sum(h["count"] for h in hits)

    rows_g = []
    for g in sorted(by_group, key=group_order):
        hs = by_group[g]
        rows_g.append(
            f'<tr><td>{dot(g)} <a href="#list" data-f="{e(g)}">{e(SHORT.get(g, g))}</a></td>'
            f'<td class="r">{n(len(hs))}</td>'
            f'<td class="r">{n(sum(h["count"] for h in hs))}</td><td class="r">{n(totals[g])}</td>'
            f'<td class="r">{pct(len(hs), totals[g])}</td></tr>'
        )
    rows, seen = [], set()
    for h in hits:
        r, p = h["rede"], h["part"]
        m = r["date"][:7]
        if m not in seen:
            seen.add(m)
            rows.append(
                f'<tr class="mh" id="m-{m}"><td colspan="5">{e(month_name(m))} '
                f'<span class="faint">· {n(per_month[m])} Reden</span></td></tr>'
            )
        who = f'<a href="../{e(p["person"])}.html">{e(p["name"])}</a>' if p["person"] in cards else e(p["name"])
        rows.append(
            f'<tr data-f="{e(h["group"])}"><td class="d">{e(short_date(r["date"]))}</td>'
            f'<td class="t"><a href="../reden/{e(page_id(r["id"]))}.html#{e(p["id"])}">'
            f"{e(r['title'] or 'Plenarsitzung')}</a>"
            f'</td><td class="w">{who}</td><td class="f">{dot(h["group"])} {e(SHORT.get(h["group"], h["group"]))}</td>'
            f'<td class="r">{n(h["count"])}×</td></tr>'
        )
    first, last = hits[-1]["rede"]["date"], hits[0]["rede"]["date"]
    kind = KIND_ONE[ent["kind"]]
    body = f"""<div class="mentions">
<p class="crumbs"><a href="index.html">Erwähnungen</a> › {e(kind)}</p>
<div hidden data-pagefind-body>{search_marks("Erwähnung", None)}<h1 data-pagefind-meta="title">{e(ent["label"])} in den Reden</h1><p>{e(kind)}, {n(len(hits))} Reden</p></div>
<article>
<h1>{e(ent["label"])} in den Reden</h1>
<p class="kind">{e(kind)} · <a href="{WIKIDATA}{e(qid)}">Wikidata {e(qid)}</a></p>
<p class="lead">{n(len(hits))} Redebeiträge nennen „{e(ent["label"])}“, insgesamt {n(total_mentions)}-mal, zwischen dem {e(short_date(first))} und dem {e(short_date(last))}. Jede Zeile in der Liste unten führt zur Rede und von dort zum Plenarprotokoll.</p>
<h2>Je Monat <span class="n">Reden, die den Namen nennen; ein Balken führt zur ersten Rede des Monats</span></h2>
<div class="chart">{chart(per_month, months)}</div>
<h2>Nach Fraktion <span class="n">Redebeiträge, die den Namen nennen, und ihr Anteil an allen Redebeiträgen der Fraktion</span></h2>
<div class="scroll"><table><thead><tr><th>Fraktion</th><th class="r">Reden mit Erwähnung</th><th class="r">Erwähnungen</th><th class="r">alle Redebeiträge</th><th class="r">Anteil</th></tr></thead><tbody>
{"".join(rows_g)}
</tbody></table></div>
<p class="explain">Ein Redebeitrag ist der Auftritt eines Redners; eine Zwischenfrage zählt für die Fraktion der Fragenden. Regierungsmitglieder sind getrennt als Bundesregierung gezählt, das Präsidium und die Fragestunde sind nicht dabei. Der Anteil setzt die Reden mit Erwähnung ins Verhältnis zu allen Redebeiträgen der Fraktion, denn größere Fraktionen reden mehr. Ein Klick auf den Namen der Fraktion zeigt in der Liste unten nur ihre Reden.</p>
<h2>Alle Reden <span class="n">nach Datum, die neueste zuerst</span></h2>
<div class="count" id="count">{n(len(hits))} Reden</div>
<div class="scroll"><table class="list" id="list"><thead><tr><th>Datum</th><th>Rede</th><th>Redner/in</th><th>Fraktion</th><th class="r">Nennungen</th></tr></thead><tbody>
{"".join(rows)}
</tbody></table></div>
<h2>So ist gezählt</h2>
<p class="explain">{e(NOTE)} Erkennung: spaCy-Modell <code>{e(model)}</code>, lokal ausgeführt, mit <a href="{LANDSCAPE_REPO}">bundestag-topic-landscape</a>; Zuordnung über Wikidata-Nummern (CC0).</p>
</article>
</div>
<footer>{FOOTER}</footer>{FILTER}"""  # noqa: E501
    desc = (f"Wie oft und von wem „{ent['label']}“ in den Reden des 21. Deutschen Bundestages genannt wird: "
            f"{n(len(hits))} Reden, nach Monat und Fraktion, mit Quellen.")  # fmt: skip
    return shell(root="../", kind="p-mentions", active="mentions", title=f"{ent['label']} in den Reden – Erwähnungen",
                 desc=desc, head=STYLE, body=body, data={"kind": "mention", "qid": qid})  # fmt: skip


def index_page(entities: dict[str, dict], hits: dict[str, list[dict]], listed: set[str], model: str) -> str:
    sections = []
    for kind, title in KINDS.items():
        qs = sorted(
            (q for q in listed if entities[q]["kind"] == kind), key=lambda q: (-len(hits[q]), entities[q]["label"])
        )
        if not qs:
            continue
        rows = "".join(
            f'<tr><td><a href="{e(q)}.html">{e(entities[q]["label"])}</a></td><td class="r">{n(len(hits[q]))}</td>'
            f'<td class="r">{n(sum(h["count"] for h in hits[q]))}</td></tr>'
            for q in qs
        )
        sections.append(
            f'<h2>{e(title)} <span class="n">{n(len(qs))}</span></h2>'
            f'<div class="scroll"><table><thead><tr><th>Name</th>'
            f'<th class="r">Reden</th><th class="r">Erwähnungen</th></tr></thead><tbody>{rows}</tbody></table></div>'
        )
    body = f"""<div class="mentions">
<h1>Erwähnungen</h1>
<p class="lead">Welche Staaten, Bundesländer, Städte und Organisationen nennen die Reden im 21. Deutschen Bundestag, und wann? Jede Seite zeigt den Verlauf je Monat, die Aufteilung nach Fraktionen und alle Reden mit Link zum Protokoll. Die Einträge sind nach der Zahl der Reden geordnet, die den Namen nennen; Personen kommen nicht vor.</p>
<p class="explain">{e(NOTE)} Einträge mit weniger als {MIN_SPEECHES} Reden haben keine eigene Seite. Erkennung: spaCy-Modell <code>{e(model)}</code>, lokal ausgeführt.</p>
{"".join(sections)}
</div>
<footer>{FOOTER}</footer>"""  # noqa: E501
    return shell(root="../", kind="p-mentions", active="mentions", title="Erwähnungen in den Reden",
                 desc="Welche Staaten, Bundesländer, Städte und Organisationen die Reden des 21. Bundestages nennen, "
                      "nach Monat und Fraktion, mit Quellen.", head=STYLE, body=body,
                 data={"kind": "mentions"})  # fmt: skip


def write(out: Path, redes: list[dict], cards: set[str], payload: dict | None = None) -> int:
    """Write erwaehnungen/; returns the number of pages, 0 without the landscape's mentions.json."""
    payload = payload if payload is not None else load()
    if not payload:
        return 0
    agg = aggregate(payload, redes)
    entities, hits = payload["entities"], agg["hits"]
    listed = {q for q, hs in hits.items() if len(hs) >= MIN_SPEECHES}
    if not listed:
        return 0
    model = payload.get("model", "")
    d = out / "erwaehnungen"
    d.mkdir(parents=True, exist_ok=True)
    for q in listed:
        (d / f"{q}.html").write_text(entity_page(q, entities[q], hits[q], agg, cards, model), encoding="utf-8")
    (d / "index.html").write_text(index_page(entities, hits, listed, model), encoding="utf-8")
    return len(listed) + 1
