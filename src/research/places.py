"""Places (docs/plan.md section 11.4, D16): Bund ⊃ Land ⊃ Wahlkreis, `orte/index.html`, `orte/<land slug>.html`,
`orte/wahlkreis-<nr>.html`. Each says who represents it:

- direct mandates by Wahlkreis (`election_candidacy`, else the Stammdaten mandate of type Direktwahl),
- list mandates by Land (`election_candidacy.list_state`, else the Stammdaten `mandate.state`, so Nachrücker are
  in), listed on the Land page and on every Wahlkreis page of that Land, marked as list mandates,
- who moved up or left, with dates.

No member drops out of the regional views: whoever has no Land in the data is listed on the Bund page. A Wahlkreis
without a direct member says why. Facts are drawn by facts.py; mentions of places in speeches are an empty facet
for now (plan 11.8).

A place owns its views (D25): the Bund page `orte/index.html` is the place hub with the map of the Wahlkreise, the
list of Länder and their Wahlkreise and the place search (Land, Wahlkreis name or number, Gemeinde) over one place
index, `orte/orte.json`. Who represents a place is decided here once, by `people`; the place pages list exactly
that, and the Abgeordnete page filters by a place with the same lists (`membership`, shipped in its payload), never
with a rule of its own."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from research import data, facts, redirects, urls
from research.data import STATES
from research.ui import FOOTER, TOKEN, crumbs, dot, e, entity_header, facet, frac_link, n, shell, short_date

PARTY_FRACTION = {"CDU": "CDU/CSU", "CSU": "CDU/CSU", "GRÜNE": "BÜNDNIS 90/DIE GRÜNEN", "Die Linke": "Die Linke"}
FACET = 20  # newest entries of a long facet (D23)
VOTES = 10  # newest roll-call votes on a place page
ZSD = ("Seit der Wahlrechtsreform 2023 bekommt ein Wahlkreissieger nur einen Sitz, wenn die Zweitstimmen seiner "
       "Partei im Land dafür reichen (Zweitstimmendeckung).")  # fmt: skip


def pct(x: float | None) -> str:
    return "–" if x is None else f"{x:.1f} %".replace(".", ",")


def representation(cards: list[dict], wks: list[dict], start: str | None) -> dict:
    """Who represents which place: {"wahlkreise": {nr: {number, name, state, official, direct: [...]}},
    "lists": {Land: [...]}, "unplaced": [...]}. Each member entry carries the card, how the mandate was won, the
    Wahlkreis stood in, and the dates it began (when after the constituent sitting) and ended."""
    wk: dict[int, dict] = {w["number"]: {**w, "official": w, "direct": []} for w in wks}
    lists: dict[str, list[dict]] = defaultdict(list)
    unplaced = []
    for c in cards:
        if c["kind"] != "member":
            continue
        el, m = c.get("election") or {}, c.get("mandate") or {}
        number = el.get("number") if el else m.get("number")
        via = el.get("via") or ("constituency" if m.get("type") == "Direktwahl" else "list" if m else None)
        entry = {
            "card": c, "via": via, "stood": number,
            "moved_up": m["from"] if m.get("from") and start and m["from"] > start else None,
            "left": m.get("to"), "list_position": el.get("list_position"),
        }  # fmt: skip
        if via == "constituency" and number is not None:
            if number not in wk:
                wk[number] = {"number": number, "name": m.get("constituency") or str(number),
                              "state": m.get("state"), "official": None, "direct": []}  # fmt: skip
            wk[number]["direct"].append(entry)
            continue
        land = el.get("list_state") or m.get("state")
        if land in STATES:
            lists[land].append(entry)
        else:
            unplaced.append(entry)
    for w in wk.values():
        w["direct"].sort(key=lambda x: bool(x["left"]))  # the sitting member first
    for xs in lists.values():
        xs.sort(key=lambda x: (x["card"]["last_name"], x["card"]["name"]))
    return {"wahlkreise": dict(sorted(wk.items())), "lists": dict(lists), "unplaced": unplaced}


def people(rep: dict, key: str) -> list[dict]:
    """Who represents a place, in the order its page lists them: for a Land (its code, "BY") the direct members of
    its Wahlkreise, then its list members; for a Wahlkreis (its number as a string, "217") its direct members (the
    one who left included), then the list members of its Land. The one definition of place membership (D25): the
    place pages list it, `membership` ships it to the Abgeordnete page's place filter."""
    if key in STATES:
        direct = [x for w in rep["wahlkreise"].values() if w["state"] == key for x in w["direct"]]
        return direct + rep["lists"].get(key, [])
    w = rep["wahlkreise"].get(int(key)) if key.isdigit() else None
    if w is None:
        return []
    return w["direct"] + rep["lists"].get(w["state"], [])


def membership(rep: dict) -> dict[str, list[str]]:
    """The person ids of every Land and Wahlkreis, from `people`: {"BY": [...], "217": [...]}."""
    keys = [*STATES, *(str(nr) for nr in rep["wahlkreise"])]
    return {k: list(dict.fromkeys(x["card"]["id"] for x in people(rep, k))) for k in keys}


def compact(rep: dict) -> dict[str, list[str]]:
    """`membership` for the page payload, without repeating a Land's list on each of its 299 Wahlkreise: a
    Wahlkreis holds its direct members and a reference "@<Land>:liste" to the list members of its Land, which
    places.js `expand` resolves. Expanding gives exactly `membership` (tests/test_places.py)."""
    out: dict[str, list[str]] = {}
    for code in STATES:
        out[code] = [x["card"]["id"] for x in people(rep, code)]
        out[f"{code}:liste"] = [x["card"]["id"] for x in rep["lists"].get(code, [])]
    for nr, w in rep["wahlkreise"].items():
        ref = [f"@{w['state']}:liste"] if w["state"] in STATES else []
        out[str(nr)] = [x["card"]["id"] for x in w["direct"]] + ref
    return out


def expand(members: dict[str, list[str]], key: str) -> list[str]:
    """places.js `expand` in Python, for the tests and the build's own checks."""
    out: list[str] = []
    for x in members.get(key, []):
        out += expand(members, x[1:]) if x.startswith("@") else [x]
    return list(dict.fromkeys(out))


def seat_fraction(w: dict) -> str | None:
    """The fraction of a Wahlkreis's direct seat, for the map: the seat's party in the official result, else the
    direct member's fraction; None without a direct seat (no Zweitstimmendeckung)."""
    o = w.get("official")
    if o:
        party = o.get("seat_party")
        return PARTY_FRACTION.get(party, party) if party else None
    return (w["direct"][0]["card"]["fraction"] or data.NO_FRACTION) if w["direct"] else None


def place_index(rep: dict, gemeinden: list[dict] | None) -> dict:
    """The one place index the place search runs over (places.js `search`), on the Orte page and in the Abgeordnete
    page's place filter: `orte/orte.json`."""
    return {
        "lands": [[code, name, data.land_slug(code)] for code, name in sorted(STATES.items(), key=lambda kv: kv[1])],
        "wahlkreise": [[nr, w["name"], w["state"]] for nr, w in rep["wahlkreise"].items()],
        "gemeinden": [[g["n"], g["d"], g["s"], g["w"]] for g in gemeinden or []],
    }


def _member(x: dict, nr: int | None = None) -> str:
    """One member row: name, fraction, how the mandate was won, and its dates."""
    c = x["card"]
    what = []
    if x["via"] == "constituency":
        what.append("Direktmandat")
    else:
        what.append("Landesliste" + (f", Platz {x['list_position']}" if x["list_position"] else ""))
        if nr is not None and x["stood"] == nr:
            what.append("hat hier im Wahlkreis kandidiert")
        elif nr is None and x["stood"]:
            what.append(f'kandidierte im <a href="../{e(urls.wahlkreis(x["stood"]))}">Wahlkreis {e(x["stood"])}</a>')
    when = []
    if x["moved_up"]:
        when.append(f"nachgerückt am {short_date(x['moved_up'])}")
    if x["left"]:
        when.append(f"ausgeschieden am {short_date(x['left'])}")
    f = c["fraction"] or data.NO_FRACTION
    return (f'<div class="row{" ended" if x["left"] else ""}"><div class="t"><a href="../{e(urls.person(c["id"]))}">'
            f'{e(c["name"])}</a> {dot(f)}{frac_link(f)}<div class="sub">{" · ".join(what)}</div></div>'
            f'<div class="d">{" · ".join(when)}</div></div>')  # fmt: skip


def _members(xs: list[dict], nr: int | None = None, empty: str = "Niemand.") -> str:
    rows = "".join(_member(x, nr) for x in xs) or f'<div class="empty">{e(empty)}</div>'
    return f'<div class="rows memb">{rows}</div>'


def why_no_direct(w: dict) -> str:
    """Why a Wahlkreis has no sitting direct member."""
    o = w.get("official")
    if w["direct"]:
        x = w["direct"][0]
        return (f"Das direkt gewählte Mitglied ist am {short_date(x['left'])} ausgeschieden. Für ein Direktmandat gibt "
                "es keine Nachwahl. Der Sitz ging an die Landesliste der Partei. Wer nachgerückt ist, steht "
                "unten.")  # fmt: skip
    if o and not o.get("seat_party") and o.get("first_party"):
        return (
            f"Kein direkt gewähltes Mitglied. Die meisten Erststimmen hatte {e(o['first_party'])} "
            f"({pct(o.get('first_percent'))}), sie waren aber nicht durch Zweitstimmen gedeckt. {ZSD}"
        )
    return "Kein direkt gewähltes Mitglied in den Daten."


def _facets(people: list[dict], speeches: list[dict], authored: dict[str, list[dict]], decided: list[dict],
            rcm: dict[str, list[list]], who: str) -> list[str]:  # fmt: skip
    """The fact facets of a place, filtered by the members who represent it."""
    ids = {x["card"]["id"] for x in people}
    sps = [s for s in speeches if s["person"] in ids and s["kind"] in ("rede", "kurz")]
    shown = sorted(sps, key=lambda s: (s["date"], s["id"]), reverse=True)[:FACET]
    more = (f'<p class="explain">Die neuesten {n(len(shown))} von {n(len(sps))}. Alle stehen in den Steckbriefen.</p>'
            if len(sps) > len(shown) else "")  # fmt: skip
    out = [facet("reden", "Reden", facts.speech_list(shown, "../", "reden", limit=None, note=more), len(sps),
                 f"Reden {who}.")]  # fmt: skip
    rc = [d for d in decided if d["kind"] == "namentlich" and any(m[0] in ids for m in rcm.get(d["id"], []))]
    rc = sorted(rc, key=lambda d: (d["date"], d["order"]), reverse=True)
    out.append(facet(
        "abstimmungen", "Abstimmungen und Beschlüsse",
        facts.decision_list(rc[:VOTES], "../", "dec", limit=None,
                            subset=lambda d: [m for m in rcm.get(d["id"], []) if m[0] in ids]),
        len(rc), f"Wie die Mitglieder {who} namentlich abgestimmt haben, die neuesten {VOTES} Abstimmungen. "
        "Bei Abstimmungen per Handzeichen hält das Protokoll nur die Fraktionen fest.",
    ))  # fmt: skip
    docs = {d["number"]: d for x in people for d in authored.get(x["card"]["id"], [])}
    ds = sorted(docs.values(), key=lambda d: (d["date"], d["number"]), reverse=True)
    out.append(facet("drucksachen", "Drucksachen", facts.drucksache_list(ds[:FACET], "../", "drs", compact=False,
                                                                         limit=None), len(ds),
                     f"Drucksachen, die Mitglieder {who} laut DIP als Urheber führen, die neuesten {FACET}. "
                     "Fraktionsanträge tragen oft die Namen der ganzen Fraktion."))  # fmt: skip
    out.append(facet("erwaehnungen", "Erwähnungen", "", explain="Nennungen dieses Ortes in Reden sind noch nicht "
                     "erfasst. Ortsnamen sind oft mehrdeutig (Halle, Neustadt, Essen), und für ihre Zuordnung fehlt "
                     "noch ein Ortsverzeichnis."))  # fmt: skip
    return out


def wahlkreis_page(w: dict, lst: list[dict], ctx: dict) -> str:
    nr, land = w["number"], w["state"]
    sitting = [x for x in w["direct"] if not x["left"]]
    lines = [f'<span class="k">Land</span> <a href="../{e(urls.land(land))}">{e(STATES.get(land, land))}</a>'
             if land in STATES else ""]  # fmt: skip
    o = w.get("official")
    if o and o.get("turnout"):
        lines.append(f'<span class="k">Wahlbeteiligung 2025</span> {pct(o["turnout"])}')
    if o and o.get("first_party"):
        lines.append(f'<span class="k">Meiste Erststimmen</span> {e(o["first_party"])} ({pct(o["first_percent"])})')
    body = [crumbs(("index.html", "Bund"), (f"../{urls.land(land)}" if land in STATES else None,
                                            STATES.get(land, "Land")), (None, f"Wahlkreis {nr}")),
            entity_header(f"Wahlkreis {nr}: {w['name']}", lines, [
                f'<a href="../{e(plenum_href(str(nr)))}">Im Plenum zeigen</a>',
                f'<a href="index.html#wk={nr}">Auf der Karte</a>', *ctx["lookup"]],
                when="Bundestagswahlkreis der Wahl 2025")]  # fmt: skip
    direct = _members(w["direct"], nr, "Kein direkt gewähltes Mitglied.")
    if not sitting:
        direct = f'<p class="explain">{why_no_direct(w)}</p>' + (direct if w["direct"] else "")
    assert w["direct"] + lst == people(ctx["rep"], str(nr))  # exactly the place's members, reordered below
    stood = [x for x in lst if x["stood"] == nr]
    others = [x for x in lst if x["stood"] != nr]
    members = (f"<h3>Direkt gewählt</h3>{direct}"
               f'<h3>Über die Landesliste {e(STATES.get(land, land))} <span class="n">{n(len(lst))}</span></h3>'
               '<p class="explain">Wer über die Landesliste in den Bundestag kam, vertritt das ganze Land, also auch '
               "diesen Wahlkreis. Zuerst die Abgeordneten, die hier kandidiert haben.</p>"
               f"{_members(stood + others, nr, 'Keine Listenmandate in den Daten.')}")  # fmt: skip
    body.append(facet("mitglieder", "Mitglieder", members, len(w["direct"]) + len(lst)))
    near = w["direct"] + stood
    body += _facets(near, ctx["speeches"], ctx["authored"], ctx["decided"], ctx["rcm"],
                    "aus diesem Wahlkreis (direkt gewählt oder hier kandidiert)")  # fmt: skip
    body.append(f"<footer>{FOOTER} Wahlergebnisse: Die Bundeswahlleiterin, Bundestagswahl 2025 "
                '(<a href="https://www.govdata.de/dl-de/by-2-0">dl-de/by-2-0</a>).</footer>')  # fmt: skip
    return shell(root="../", kind="p-place", active="places", title=f"Wahlkreis {nr}: {w['name']}",
                 desc=f"Wahlkreis {nr} {w['name']}: die direkt und über die Landesliste gewählten Abgeordneten im "
                      "21. Bundestag mit Reden, Abstimmungen und Drucksachen.", body="".join(body),
                 data={"kind": "place", "wahlkreis": nr})  # fmt: skip


def land_page(land: str, wks: list[dict], lst: list[dict], ctx: dict) -> str:
    name = STATES[land]
    rows = []
    for w in wks:
        holder = next((x for x in w["direct"] if not x["left"]), None)
        who = (f'{e(holder["card"]["name"])} {dot(holder["card"]["fraction"])}' if holder
               else '<span class="faint">kein direkt gewähltes Mitglied</span>')  # fmt: skip
        rows.append(f'<a class="row" href="wahlkreis-{w["number"]}.html"><span class="d">{w["number"]}</span>'
                    f'<span class="t"><span class="ti">{e(w["name"])}</span><span class="sub">{who}</span>'
                    "</span></a>")  # fmt: skip
    direct = [x for w in wks for x in w["direct"]]
    assert direct + lst == people(ctx["rep"], land)  # the Land page lists exactly the place's members
    members = (f'<h3>Wahlkreise <span class="n">{n(len(wks))}</span></h3><div class="rows">{"".join(rows)}</div>'
               f'<h3>Direkt gewählt <span class="n">{n(len(direct))}</span></h3>{_members(direct)}'
               f'<h3>Über die Landesliste <span class="n">{n(len(lst))}</span></h3>{_members(lst)}')  # fmt: skip
    body = [crumbs(("index.html", "Bund"), (None, name)),
            entity_header(name, [f"{n(len(wks))} Wahlkreise · {n(len(direct))} direkt gewählte Mitglieder · "
                                 f"{n(len(lst))} über die Landesliste"],
                          [f'<a href="../{e(plenum_href(land))}">Im Plenum zeigen</a>',
                           f'<a href="index.html#land={land}">Auf der Karte</a>'],
                          when="Land"),
            facet("mitglieder", "Mitglieder", members, len(direct) + len(lst))]  # fmt: skip
    body += _facets(direct + lst, ctx["speeches"], ctx["authored"], ctx["decided"], ctx["rcm"], f"aus {name}")
    body.append(f"<footer>{FOOTER}</footer>")
    return shell(root="../", kind="p-place", active="places", title=name,
                 desc=f"{name} im 21. Bundestag: die Wahlkreise, die direkt gewählten Mitglieder und die "
                      "Landesliste, mit Reden, Abstimmungen und Drucksachen.", body="".join(body),
                 data={"kind": "place", "land": land})  # fmt: skip


def plenum_href(key: str) -> str:
    """The Abgeordnete page filtered by a place (its plenum and list show exactly `people(rep, key)`)."""
    return f"abgeordnete.html#ort={key}"


HUB_STYLE = """<style>
.hub .psearch { position: relative; margin: 4px 0 18px; }
.hub .psearch input { width: 100%; background: var(--card); color: var(--text); border: 1px solid var(--line);
  border-radius: 10px; padding: 10px 12px; font-size: 14.5px; }
.hub #presults .row { grid-template-columns: minmax(0, 1fr) auto; }
.hub #presults .k { font-size: 11px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: var(--faint); }
.hub .map { position: relative; overflow: hidden; touch-action: pan-y; background: var(--card); border: 1px solid var(--line);
  border-radius: 14px; aspect-ratio: .74; max-height: 78vh; margin: 0 auto; }
.hub .map.zoomed { touch-action: none; }
.hub .map svg { display: block; width: 100%; height: 100%; }
.hub .map.drag svg, .hub .map.drag path { cursor: grabbing; }
.hub .map path { stroke: var(--card); stroke-width: .6px; vector-effect: non-scaling-stroke; stroke-linejoin: round; cursor: pointer;
  transition: fill-opacity .12s; }
.hub .map path.dim { fill-opacity: .18; }
.hub .map .ov path { fill: none; pointer-events: none; stroke-linejoin: round; }
.hub .map .ov g { filter: drop-shadow(0 1px 2.5px rgba(0,0,0,.35)); }
.hub .map .ov .case { stroke: var(--card); stroke-width: 4.5px; }
.hub .map .ov .hover { stroke: var(--accent); stroke-width: 1.8px; fill: rgba(255,255,255,.26); }
.hub .map .ov .sel { stroke: var(--accent); stroke-width: 2.6px; }
.hub .mapzoom { position: absolute; top: 8px; right: 8px; display: flex; flex-direction: column; background: var(--card);
  border: 1px solid var(--line); border-radius: 9px; box-shadow: 0 2px 8px rgba(0,0,0,.08); overflow: hidden; }
.hub .mapzoom button { width: 32px; height: 32px; border: 0; background: transparent; color: var(--text); font-size: 18px;
  line-height: 1; cursor: pointer; display: grid; place-items: center; }
.hub .mapzoom button + button { border-top: 1px solid var(--line); }
.hub .mapzoom button:disabled { color: var(--faint); cursor: default; }
.hub .map .info { position: absolute; left: 8px; bottom: 8px; max-width: 62%; background: var(--card); border: 1px solid var(--line);
  border-radius: 10px; padding: 7px 11px; font-size: 12.5px; box-shadow: 0 3px 12px rgba(0,0,0,.08); pointer-events: none; }
.hub .map .info[hidden], .hub .strip[hidden] { display: none; }
.hub .map .info .k, .hub .strip .k { color: var(--muted); }
.hub .strip { display: flex; align-items: center; gap: 10px; background: var(--card); border: 1px solid var(--line);
  border-radius: 10px; padding: 8px 12px; margin: 8px 0 4px; font-size: 13px; }
.hub .strip .t { flex: 1; min-width: 0; }
.hub .strip a.go { white-space: nowrap; font-weight: 500; }
.hub .maplegend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12px; color: var(--muted); margin: 8px 0 2px; }
.hub .maplegend span { display: inline-flex; align-items: center; gap: 5px; }
.hub .mapcredit { color: var(--faint); font-size: 11.5px; margin: 4px 0 0; }
.hub .maploading { color: var(--faint); font-size: 13px; padding: 30px 16px; }
.hub details.land { background: var(--card); border: 1px solid var(--line); border-radius: 12px; margin: 0 0 8px; }
.hub details.land > summary { cursor: pointer; padding: 10px 14px; display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; }
.hub details.land > summary a { font-weight: 600; }
.hub details.land > summary .sub { color: var(--muted); font-size: 12.5px; }
.hub details.land .rows { border: 0; border-top: 1px solid var(--line); border-radius: 0 0 12px 12px; }
.hub .wkrow { grid-template-columns: 40px 1fr; }
.hub .wkrow .d { color: var(--faint); font-variant-numeric: tabular-nums; }
@media (min-width: 1000px) {
  body.p-places main { max-width: 1320px; }
  .hub .cols { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 28px; align-items: start; }
  .hub .cols .mapcol { position: sticky; top: 12px; }
}
</style>"""  # noqa: E501

HUB_JS = """<script>
// the place hub (places.py `bund_page`): the place search over orte/orte.json (places.js), the map (wkmap.js);
// every result, map click and list row leads to the canonical place page
document.addEventListener('DOMContentLoaded', () => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const $ = id => document.getElementById(id);
  const q = $('pq'), out = $('presults');
  const KIND = { land: 'Land', wk: 'Wahlkreis', gemeinde: 'Gemeinde' };
  let index = null, loading = null;
  const load = () => loading ??= fetch('orte.json').then(r => r.json()).then(x => { index = x; });
  const map = WkMap.mount({
    box: $('map'), strip: $('strip'), legend: $('maplegend'), credit: $('mapcredit'), src: '../wahlkreise.json',
    wahlkreise: PAGE.wahlkreise, lands: PAGE.lands, legendItems: PAGE.legend, href: nr => `wahlkreis-${nr}.html`,
    selected: null,
  });
  function render() {
    const text = q.value.trim();
    if (text.length < 2) { out.innerHTML = ''; map.light(null); return; }
    load().then(() => {
      const hits = Places.search(index, text, 40);
      out.innerHTML = hits.length ? `<div class="rows">${hits.slice(0, 15).map(h => `<a class="row" href="../${esc(h.href)}"><span class="t"><span class="ti">${esc(h.label)}</span><span class="sub">${esc(h.sub)}</span></span><span class="k">${KIND[h.kind]}</span></a>`).join('')}</div>`
        : '<div class="rows"><div class="empty">Kein Land, kein Wahlkreis und keine Gemeinde gefunden.</div></div>';
      const nrs = new Set();
      for (const h of hits) {
        if (h.kind === 'land') Object.entries(PAGE.wahlkreise).forEach(([nr, w]) => { if (w.land === h.key) nrs.add(+nr); });
        else nrs.add(+h.key);
      }
      map.light(nrs);
    });
  }
  q.addEventListener('input', render);
  q.addEventListener('keydown', e => { if (e.key === 'Enter') { const a = out.querySelector('a'); if (a) location.href = a.href; } });
  // ?q=… (the old Gemeinde lookup carries its query here), #wk=<nr> and #land=<code> (the place pages' "Auf der Karte")
  const qs = new URLSearchParams(location.search).get('q'), h = new URLSearchParams(location.hash.slice(1));
  if (qs) { q.value = qs; render(); }
  map.ready.then(() => {
    if (h.get('wk')) { map.select(+h.get('wk'), true); $('karte').scrollIntoView(); }
    else if (h.get('land')) {
      const nrs = new Set(Object.entries(PAGE.wahlkreise).filter(([, w]) => w.land === h.get('land')).map(([nr]) => +nr));
      map.light(nrs); map.zoomTo(nrs); $('karte').scrollIntoView();
    }
  });
  if (location.hash === '#suche') q.focus();
});
</script>"""  # noqa: E501


def bund_page(rep: dict, lookup: list[str]) -> str:
    """The place hub: the place search, the map of the Wahlkreise and the list of Länder with their Wahlkreise, each
    leading to the place's page; and the members whose Land is unknown, so nobody drops out of the regional views."""
    by_land: dict[str, list[dict]] = defaultdict(list)
    for w in rep["wahlkreise"].values():
        by_land[w["state"]].append(w)
    lands = []
    for code, name in sorted(STATES.items(), key=lambda kv: kv[1]):
        wks = by_land.get(code, [])
        rows = []
        for w in wks:
            holder = next((x for x in w["direct"] if not x["left"]), None)
            who = (f'{e(holder["card"]["name"])} {dot(holder["card"]["fraction"])}' if holder
                   else '<span class="faint">kein direkt gewähltes Mitglied</span>')  # fmt: skip
            rows.append(f'<a class="row wkrow" href="wahlkreis-{w["number"]}.html"><span class="d">{w["number"]}</span>'
                        f'<span class="t"><span class="ti">{e(w["name"])}</span><span class="sub">{who}</span></span>'
                        "</a>")  # fmt: skip
        lands.append(
            f'<details class="land" id="land-{e(code)}"><summary><a href="{e(data.land_slug(code))}.html">{e(name)}</a>'
            f'<span class="sub">{n(len(wks))} Wahlkreise · {n(sum(len(w["direct"]) for w in wks))} direkt · '
            f"{n(len(rep['lists'].get(code, [])))} über die Landesliste</span></summary>"
            f'<div class="rows">{"".join(rows)}</div></details>'
        )
    unplaced = ""
    if rep["unplaced"]:
        unplaced = ('<h3>Ohne Land in den Daten</h3><p class="explain">Mitglieder, für die weder die Ergebnisse der '
                    "Bundeswahlleiterin noch die Stammdaten ein Land nennen, etwa Nachrückerinnen und Nachrücker, die "
                    f"bisher nur in den Abstimmungslisten stehen.</p>{_members(rep['unplaced'])}")  # fmt: skip
    search = (
        '<section class="facet" id="suche"><h2>Ort suchen</h2><div class="psearch"><input type="search" id="pq" '
        'placeholder="Land, Wahlkreis (Name oder Nummer) oder Gemeinde …" autocomplete="off" aria-label="Ort suchen">'
        '</div><div id="presults" aria-live="polite"></div></section>'
    )
    mapbox = (
        '<section class="facet mapcol" id="karte"><h2>Karte der Wahlkreise</h2>'
        '<div class="map" id="map"><div class="maploading">Karte wird geladen …</div></div>'
        '<div class="strip" id="strip" hidden></div><div class="maplegend" id="maplegend"></div>'
        f'<p class="mapcredit" id="mapcredit"></p><p class="explain">{ZSD} Grau: kein Direktmandat.</p></section>'
    )
    body = (crumbs((None, "Bund"))
            + entity_header("Bund, Länder und Wahlkreise", [
                f"16 Länder, {n(len(rep['wahlkreise']))} Wahlkreise. Jede Seite zeigt die Abgeordneten des Ortes im "
                "21. Bundestag, direkt im Wahlkreis gewählt und über die Landesliste. Nach dem Ort gefiltert zeigt sie "
                'auch das <a href="../abgeordnete.html">Plenum</a>.'], lookup,
                when="Orte")
            + f'<div class="hub">{search}<div class="cols">{mapbox}<div>'
            + facet("laender", "Länder und Wahlkreise", "".join(lands) + unplaced)
            + "</div></div></div>"
            + f"<footer>{FOOTER} Wahlergebnisse und Wahlkreiskarte: Die Bundeswahlleiterin "
            '(<a href="https://www.govdata.de/dl-de/by-2-0">dl-de/by-2-0</a>).</footer>' + HUB_JS)  # fmt: skip
    fills = {}
    for nr, w in rep["wahlkreise"].items():
        f = seat_fraction(w)
        holder = next((x for x in w["direct"] if not x["left"]), None)
        fills[str(nr)] = {"name": w["name"], "land": w["state"], "fill": f"--{TOKEN[f]}" if f in TOKEN else None,
                          "holder": holder["card"]["name"] if holder else None}  # fmt: skip
    seen = {seat_fraction(w) for w in rep["wahlkreise"].values()}
    legend = [[{"BÜNDNIS 90/DIE GRÜNEN": "Grüne"}.get(f, f), f"--{TOKEN[f]}"] for f in TOKEN if f in seen]
    if None in seen:
        legend.append(["kein Direktmandat (Zweitstimmendeckung)", None])
    return shell(root="../", kind="p-place p-places", active="places", title="Orte: Bund, Länder, Wahlkreise",
                 desc="Die 16 Länder und 299 Wahlkreise und wer sie im 21. Deutschen Bundestag vertritt: Karte, Liste "
                      "und Suche nach Land, Wahlkreis oder Gemeinde.", body=body,
                 data={"kind": "places", "wahlkreise": fills, "lands": STATES, "legend": legend},
                 head=f'{HUB_STYLE}<script src="../places.js"></script><script src="../wkmap.js"></script>',
                 )  # fmt: skip


def index_payload(cards: list[dict], wks: list[dict]) -> dict:
    """What the Abgeordnete page needs to filter by a place (D25): the members of every Land and Wahlkreis as
    `compact` gives them, and the names and pages to label the filter and link the place."""
    rep = representation(cards, wks, None)
    return {
        "lands": {code: {"name": name, "slug": data.land_slug(code)} for code, name in STATES.items()},
        "wahlkreise": {str(nr): {"name": w["name"], "land": w["state"]} for nr, w in rep["wahlkreise"].items()},
        "members": compact(rep),
    }


def write(out: Path, cards: list[dict], wks: list[dict], start: str | None, decided: list[dict],
          rcm: dict[str, list[list]], gemeinden: list[dict] | None = None) -> dict:  # fmt: skip
    """Write orte/ with the place index orte/orte.json, and the stub of the old Gemeinde lookup; returns the
    representation (for the search)."""
    rep = representation(cards, wks, start)
    authored = {c["id"]: [{**d, "url": data.DIP_DOC.format(d["id"])} for d in c.get("authored") or []] for c in cards}
    lookup = ['<a href="index.html#suche">Ort oder Gemeinde suchen</a>']
    ctx = {"speeches": data.speech_facts(cards), "authored": authored, "decided": decided, "rcm": rcm,
           "lookup": lookup, "rep": rep}  # fmt: skip
    d = out / "orte"
    d.mkdir(parents=True, exist_ok=True)
    by_land: dict[str, list[dict]] = defaultdict(list)
    for w in rep["wahlkreise"].values():
        by_land[w["state"]].append(w)
        lst = rep["lists"].get(w["state"], [])
        (d / f"wahlkreis-{w['number']}.html").write_text(wahlkreis_page(w, lst, ctx), encoding="utf-8")
    for code in STATES:
        (d / f"{data.land_slug(code)}.html").write_text(
            land_page(code, by_land.get(code, []), rep["lists"].get(code, []), ctx), encoding="utf-8"
        )
    (d / "index.html").write_text(bund_page(rep, []), encoding="utf-8")
    index = json.dumps(place_index(rep, gemeinden), ensure_ascii=False, separators=(",", ":"))
    (d / "orte.json").write_text(index, encoding="utf-8")
    # the Gemeinde lookup is the hub's place search now; the stub carries ?q=… over (redirects.PAGE)
    redirects.write(out, "wahlkreise/suche.html", f"{urls.PLACES}#suche", "Ort suchen")
    return rep
