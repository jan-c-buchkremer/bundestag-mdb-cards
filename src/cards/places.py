"""Places (docs/plan.md section 11.4, D16): Bund ⊃ Land ⊃ Wahlkreis, `orte/index.html`, `orte/<land slug>.html`,
`orte/wahlkreis-<nr>.html`. Each says who represents it:

- direct mandates by Wahlkreis (`election_candidacy`, else the Stammdaten mandate of type Direktwahl),
- list mandates by Land (`election_candidacy.list_state`, else the Stammdaten `mandate.state`, so Nachrücker are
  in), listed on the Land page and on every Wahlkreis page of that Land, marked as list mandates,
- who moved up or left, with dates.

No member drops out of the regional views: whoever has no Land in the data is listed on the Bund page. A Wahlkreis
without a direct member says why. The index map, its Wahlkreise list and the Gemeinde lookup lead here (D17).
Facts are drawn by facts.py; mentions of places in speeches are an empty facet for now (plan 11.8)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from cards import data, facts, urls
from cards.data import STATES
from cards.ui import FOOTER, crumbs, dot, e, entity_header, facet, frac_link, n, shell, short_date

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
        return (f"Das direkt gewählte Mitglied ist am {short_date(x['left'])} ausgeschieden. Ein Direktmandat hat "
                "keine Nachwahl: Der Sitz ging an die Landesliste der Partei, wer nachgerückt ist, steht "
                "unten.")  # fmt: skip
    if o and not o.get("seat_party") and o.get("first_party"):
        return (
            f"Kein direkt gewähltes Mitglied: Die meisten Erststimmen hatte {e(o['first_party'])} "
            f"({pct(o.get('first_percent'))}), aber sie waren nicht durch Zweitstimmen gedeckt. {ZSD}"
        )
    return "Kein direkt gewähltes Mitglied in den Daten."


def _facets(people: list[dict], speeches: list[dict], authored: dict[str, list[dict]], decided: list[dict],
            rcm: dict[str, list[list]], who: str) -> list[str]:  # fmt: skip
    """The fact facets of a place, filtered by the members who represent it."""
    ids = {x["card"]["id"] for x in people}
    sps = [s for s in speeches if s["person"] in ids and s["kind"] in ("rede", "kurz")]
    shown = sorted(sps, key=lambda s: (s["date"], s["id"]), reverse=True)[:FACET]
    more = (f'<p class="explain">Die neuesten {n(len(shown))} von {n(len(sps))}; alle stehen auf den Karten.</p>'
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
        "Per Handzeichen hält das Protokoll nur Fraktionen fest, keine Personen.",
    ))  # fmt: skip
    docs = {d["number"]: d for x in people for d in authored.get(x["card"]["id"], [])}
    ds = sorted(docs.values(), key=lambda d: (d["date"], d["number"]), reverse=True)
    out.append(facet("drucksachen", "Drucksachen", facts.drucksache_list(ds[:FACET], "../", "drs", compact=False,
                                                                         limit=None), len(ds),
                     f"Drucksachen, die Mitglieder {who} laut DIP als Urheber führen, die neuesten {FACET}; "
                     "Fraktionsanträge tragen oft die Namen der ganzen Fraktion."))  # fmt: skip
    out.append(facet("erwaehnungen", "Erwähnungen", "", explain="Wo dieser Ort in Reden genannt wird, ist noch nicht "
                     "erfasst: Ortsnamen sind oft mehrdeutig (Halle, Neustadt, Essen) und brauchen ein Ortsverzeichnis "
                     "mit Auflösung, das in der Datengrundlage noch fehlt."))  # fmt: skip
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
                f'<a href="../index.html#ansicht=wahlkreise&amp;wk={nr}">Auf der Karte</a>',
                *ctx["lookup"]],
                when="Bundestagswahlkreis der Wahl 2025")]  # fmt: skip
    direct = _members(w["direct"], nr, "Kein direkt gewähltes Mitglied.")
    if not sitting:
        direct = f'<p class="explain">{why_no_direct(w)}</p>' + (direct if w["direct"] else "")
    stood = [x for x in lst if x["stood"] == nr]
    others = [x for x in lst if x["stood"] != nr]
    members = (f"<h3>Direkt gewählt</h3>{direct}"
               f'<h3>Über die Landesliste {e(STATES.get(land, land))} <span class="n">{n(len(lst))}</span></h3>'
               '<p class="explain">Wer über die Landesliste in den Bundestag kam, vertritt das ganze Land, also auch '
               "diesen Wahlkreis. Zuerst, wer hier kandidiert hat.</p>"
               f"{_members(stood + others, nr, 'Keine Listenmandate in den Daten.')}")  # fmt: skip
    body.append(facet("mitglieder", "Mitglieder", members, len(w["direct"]) + len(lst)))
    near = w["direct"] + stood
    body += _facets(near, ctx["speeches"], ctx["authored"], ctx["decided"], ctx["rcm"],
                    "aus diesem Wahlkreis (direkt gewählt oder hier kandidiert)")  # fmt: skip
    body.append(f"<footer>{FOOTER} Wahlergebnisse: Die Bundeswahlleiterin, Bundestagswahl 2025 "
                '(<a href="https://www.govdata.de/dl-de/by-2-0">dl-de/by-2-0</a>).</footer>')  # fmt: skip
    return shell(root="../", kind="p-place", active="places", title=f"Wahlkreis {nr}: {w['name']}",
                 desc=f"Wahlkreis {nr} {w['name']}: wer ihn im 21. Bundestag vertritt, direkt und über die "
                      "Landesliste, mit Reden, Abstimmungen und Drucksachen.", body="".join(body),
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
    members = (f'<h3>Wahlkreise <span class="n">{n(len(wks))}</span></h3><div class="rows">{"".join(rows)}</div>'
               f'<h3>Direkt gewählt <span class="n">{n(len(direct))}</span></h3>{_members(direct)}'
               f'<h3>Über die Landesliste <span class="n">{n(len(lst))}</span></h3>{_members(lst)}')  # fmt: skip
    body = [crumbs(("index.html", "Bund"), (None, name)),
            entity_header(name, [f"{n(len(wks))} Wahlkreise · {n(len(direct))} direkt gewählte Mitglieder · "
                                 f"{n(len(lst))} über die Landesliste"],
                          [f'<a href="../index.html#ansicht=wahlkreise&amp;state={land}">Auf der Karte</a>'],
                          when="Land"),
            facet("mitglieder", "Mitglieder", members, len(direct) + len(lst))]  # fmt: skip
    body += _facets(direct + lst, ctx["speeches"], ctx["authored"], ctx["decided"], ctx["rcm"], f"aus {name}")
    body.append(f"<footer>{FOOTER}</footer>")
    return shell(root="../", kind="p-place", active="places", title=name,
                 desc=f"{name} im 21. Bundestag: die Wahlkreise, die direkt gewählten Mitglieder und die "
                      "Landesliste, mit Reden, Abstimmungen und Drucksachen.", body="".join(body),
                 data={"kind": "place", "land": land})  # fmt: skip


def bund_page(rep: dict, lookup: list[str]) -> str:
    by_land: dict[str, list[dict]] = defaultdict(list)
    for w in rep["wahlkreise"].values():
        by_land[w["state"]].append(w)
    rows = "".join(
        f'<a class="row" href="{e(data.land_slug(code))}.html"><span class="t"><span class="ti">{e(name)}</span>'
        f'<span class="sub">{n(len(by_land.get(code, [])))} Wahlkreise · '
        f"{n(sum(len(w['direct']) for w in by_land.get(code, [])))} direkt · "
        f"{n(len(rep['lists'].get(code, [])))} über die Landesliste</span></span></a>"
        for code, name in sorted(STATES.items(), key=lambda kv: kv[1])
    )
    unplaced = ""
    if rep["unplaced"]:
        unplaced = ('<h3>Ohne Land in den Daten</h3><p class="explain">Mitglieder, für die weder die Ergebnisse der '
                    "Bundeswahlleiterin noch die Stammdaten ein Land nennen, etwa Nachrückerinnen und Nachrücker, die "
                    f"bisher nur in den Abstimmungslisten stehen.</p>{_members(rep['unplaced'])}")  # fmt: skip
    body = (crumbs((None, "Bund"))
            + entity_header("Bund, Länder und Wahlkreise", [
                f"16 Länder, {n(len(rep['wahlkreise']))} Wahlkreise. Jede Seite zeigt, wer den Ort im 21. Bundestag "
                "vertritt: direkt gewählt im Wahlkreis und über die Landesliste des Landes."],
                ['<a href="../index.html#ansicht=wahlkreise">Karte der Wahlkreise</a>', *lookup])
            + facet("laender", "Länder", f'<div class="rows">{rows}</div>{unplaced}')
            + f"<footer>{FOOTER}</footer>")  # fmt: skip
    return shell(root="../", kind="p-place", active="places", title="Orte: Bund, Länder, Wahlkreise",
                 desc="Die 16 Länder und 299 Wahlkreise und wer sie im 21. Deutschen Bundestag vertritt.", body=body,
                 data={"kind": "places"})  # fmt: skip


def index_payload(cards: list[dict], wks: list[dict]) -> dict:
    """What the index needs to link the place pages: the Land slugs and the Wahlkreise that get a page."""
    rep = representation(cards, wks, None)
    return {"lands": {code: data.land_slug(code) for code in STATES}, "wahlkreise": sorted(rep["wahlkreise"])}


def write(out: Path, cards: list[dict], wks: list[dict], start: str | None, decided: list[dict],
          rcm: dict[str, list[list]], gemeinde_search: bool = False) -> dict:  # fmt: skip
    """Write orte/; returns the representation (for the index and the search)."""
    rep = representation(cards, wks, start)
    authored = {c["id"]: [{**d, "url": data.DIP_DOC.format(d["id"])} for d in c.get("authored") or []] for c in cards}
    lookup = ['<a href="../wahlkreise/suche.html">Wahlkreis einer Gemeinde finden</a>'] if gemeinde_search else []
    ctx = {"speeches": data.speech_facts(cards), "authored": authored, "decided": decided, "rcm": rcm,
           "lookup": lookup}  # fmt: skip
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
    (d / "index.html").write_text(bund_page(rep, lookup), encoding="utf-8")
    return rep
