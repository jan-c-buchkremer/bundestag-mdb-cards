"""Groups (docs/plan.md section 11): `gremien/index.html`, one page per Ausschuss, Unterausschuss and other
Bundestag body (`gremien/<slug>.html`), one page per Fraktion (`fraktionen/<token>.html`, plus fraktionslos) and one
for the Bundesregierung (`gremien/bundesregierung.html`, from `government_role`).

Every group page is an entity page: a header, then the facets Mitglieder (with dates), Reden, Abstimmungen und
Beschlüsse (with the group's position, and its cohesion), Drucksachen (with the group as Urheber), each drawn by
facts.py; a facet that does not apply to the group says why. Long facets show the newest entries (D23).

Built from the Stammdaten's `membership` table (kind committee/other for the Gremien, kind fraction for the
Fraktionen), joined with what the cards already know (fraction, gender, first term) and, for the Fraktionen, with
the Rollen section's own numbers (careers.py) so both agree. Federal ministries are offices a minister or
Staatssekretär holds, not Gremien the Bundestag itself forms, and are left out here; every card already shows them
under "Regierungsämter". No ranking of members, every number links to its source (docs/plan.md)."""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from research import careers, cohesion, controls, data, facts, questions, urls
from research.data import (
    GOVERNMENT_GROUP,
    NO_FRACTION,
    OFFICE,
    WP,
    committee_short,
    has_table,
    lead_rank,
    slugify,
)
from research.ui import (
    FOOTER,
    ORDER,
    SHORT,
    TOKEN,
    crumbs,
    dot,
    e,
    facet,
    frac_link,
    fraction_order,
    n,
    shell,
    short_date,
)

FACET = 20  # newest entries of a long facet (D23)

# federal ministries and the Kanzleramt are government offices, already on the card as "Regierungsämter"
_EXCLUDE_EXACT = {"Auswärtiges Amt", "Bundeskanzleramt"}
# DIP's Urheber on a Beschlussempfehlung sometimes spells a committee's name differently from the Stammdaten
_ALIASES = {
    "Ausschuss für Wahlprüfung, Immunität und Geschäftsordnung": "Ausschuss für Wahlprüfung, Immunität u. Geschäftsordnung",  # noqa: E501
    "Sportausschuss": "Ausschuss für Sport und Ehrenamt",
    "Vermittlungsausschuss": "Mitglieder des Ausschusses nach Artikel 77 Abs. 2 des Grundgesetzes (Vermittlungsausschuss)",  # noqa: E501
}
_LEAD = careers.CHAIR  # the Rollen section lists the same chairs
_DEPUTY_LEAD = re.compile(r"^Stellvertretende[rs]?\s+(Vorsitzende[r]?|Delegationsleiter)$")
_OBLEUTE = re.compile(r"^(Obfrau|Obmann)$")
_ORDENTLICH = re.compile(r"^Ordentliches Mitglied$")
_STELLV_MITGLIED = re.compile(r"^Stellvertretendes Mitglied$")
GROUPS = ("Vorsitz", "Stellvertretender Vorsitz", "Obleute", "Ordentliche Mitglieder",
          "Stellvertretende Mitglieder", "Weitere Funktionen")  # fmt: skip
STYLE = """<style>
.bodies h2 { margin-top: 26px; }
.bodies .comp { margin: 10px 0 16px; }
.bodies ul.besch { padding-left: 20px; margin: 8px 0; }
.bodies ul.besch li { margin: 4px 0; }
.bodies table.plenum td.l { text-align: left; }
.bodies .filters { margin: 10px 0; }
</style>"""


def role_group(role: str | None) -> int:
    if role is None:
        return 3
    if _LEAD.match(role):
        return 0
    if _DEPUTY_LEAD.match(role):
        return 1
    if _OBLEUTE.match(role):
        return 2
    if _ORDENTLICH.match(role):
        return 3
    if _STELLV_MITGLIED.match(role):
        return 4
    return 5


# ---------------------------------------------------------------- Gremien (Ausschüsse, Unterausschüsse, other)


def load_bodies(conn: sqlite3.Connection, cards: list[dict]) -> list[dict]:
    """Every Ausschuss, Unterausschuss and other Gremium with a WP 21 membership row, with its members joined
    from the cards (fraction, gender, first term)."""
    by_id = {c["id"]: c for c in cards}
    bodies: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT * FROM membership WHERE wahlperiode = ? AND kind IN ('committee', 'other') ORDER BY from_date, id",
        (WP,),
    ):
        name = r["name"]
        if r["kind"] == "other" and (name.startswith("Bundesministerium") or name in _EXCLUDE_EXACT):
            continue
        card = by_id.get(r["person_id"])
        if card is None:
            continue
        b = bodies.setdefault(name, {"name": name, "kind": r["kind"], "members": []})
        b["members"].append({
            "person": r["person_id"], "name": card["name"], "fraction": card["fraction"] or NO_FRACTION,
            "gender": card["gender"], "first_term": not any(wp < WP for wp in card["periods"]),
            "role": r["role"], "from": r["from_date"], "to": r["to_date"],
        })  # fmt: skip
    out = list(bodies.values())
    for b in out:
        b["short"] = committee_short(b["name"]) if b["kind"] == "committee" else b["name"]
        b["slug"] = slugify(b["short"])
    seen: Counter = Counter()
    for b in sorted(out, key=lambda b: b["slug"]):
        base = b["slug"]
        seen[base] += 1
        if seen[base] > 1:
            b["slug"] = f"{base}-{seen[base]}"
    return sorted(out, key=lambda b: (0 if b["kind"] == "committee" else 1, b["short"]))


def besch_by_committee(docs: list[dict]) -> dict[str, list[dict]]:
    """Per committee (by name, DIP aliases resolved): its Beschlussempfehlungen (and -berichte), oldest first."""
    out: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        if "Beschlussempfehlung" in (d["type"] or ""):
            for raw in d["originators"]:
                out[_ALIASES.get(raw, raw)].append(d)
    return out


def _newest(xs: list[dict], k: int = FACET) -> list[dict]:
    return sorted(xs, key=lambda x: (x["date"] or "", x.get("id") or ""), reverse=True)[:k]


def _more(shown: int, total: int, where: str) -> str:
    """Under a capped facet: how many there are in all and where the full list lives (D23)."""
    return f'<p class="explain">Die neuesten {n(shown)} von {n(total)}. {where}</p>' if total > shown else ""


GROUP_SLUGS = ("vorsitz", "stellv-vorsitz", "obleute", "ordentlich", "stellvertretend", "weitere")


def _member_row(m: dict) -> str:
    if m["to"]:
        when = f"{short_date(m['from'])} – {short_date(m['to'])}" if m["from"] else f"bis {short_date(m['to'])}"
    else:
        when = f"seit {short_date(m['from'])}" if m["from"] else ""
    who = f'<a href="../{e(m["person"])}.html">{e(m["name"])}</a>'
    sub = f'<div class="sub">{e(m["role"])}</div>' if m["role"] else ""
    attrs = f' data-fraktion="{TOKEN.get(m["fraction"], "")}" data-rolle="{GROUP_SLUGS[role_group(m["role"])]}"'
    return (f'<div class="row{" ended" if m["to"] else ""}"{attrs}><div class="t">{who} {dot(m["fraction"])}'
            f'{frac_link(m["fraction"])}{sub}</div><div class="d">{when}</div></div>')  # fmt: skip


def _members_section(ms: list[dict]) -> str:
    """The members by role, each group with its heading, filterable by fraction (the composition above), role and
    name (controls.js; a group without a row left is hidden)."""
    groups: dict[int, list[dict]] = defaultdict(list)
    for m in ms:
        groups[role_group(m["role"])].append(m)
    parts = []
    for i, label in enumerate(GROUPS):
        if not groups[i]:
            continue
        rows = "".join(_member_row(m) for m in sorted(groups[i], key=lambda m: m["name"]))
        parts.append(f'<section data-group><h3>{e(label)} <span class="n">{n(len(groups[i]))}</span></h3>'
                     f'<div class="rows memb">{rows}</div></section>')  # fmt: skip
    roles = controls.chips("rolle", [(GROUP_SLUGS[i], label, len(groups[i]), "accent") for i, label in enumerate(GROUPS)
                                     if groups[i]], "Rolle")  # fmt: skip
    return (
        "<h2>Mitglieder</h2>" + controls.toolbar("Name …") + controls.block("Rolle", roles)
        + '<div class="count" data-count></div><div class="grps" data-rows data-row=".row" data-limit="9999">'
        + "".join(parts) + '<div class="rows"><div class="empty" data-none hidden>Keine Treffer für diese Auswahl.'
        "</div></div></div>"
    )  # fmt: skip


def _stats_section(ms: list[dict]) -> str:
    current = [m for m in ms if m["to"] is None]
    if not current:
        return '<h2>Zusammensetzung</h2><p class="explain">Aktuell keine Mitglieder im Datenbestand.</p>'
    by_fraction = Counter(m["fraction"] for m in current)
    women = sum(1 for m in current if m["gender"] == "weiblich")
    first = sum(1 for m in current if m["first_term"])
    order = sorted(by_fraction, key=fraction_order)
    comp_rows = "".join(
        f'<tr><td>{dot(f)} {frac_link(f)}</td><td class="num">{by_fraction[f]}</td></tr>' for f in order
    )  # fmt: skip
    table = ('<div class="rows"><table class="plenum"><thead><tr><th>Fraktion</th><th>Mitglieder</th></tr></thead>'
             f"<tbody>{comp_rows}</tbody></table></div>")  # fmt: skip
    items = [(TOKEN.get(f, "frl"), SHORT.get(f, f), by_fraction[f], TOKEN.get(f, "frl")) for f in order]
    chart = controls.segmented("fraktion", items, "Aktuelle Mitglieder nach Fraktion", "Mitglieder")
    return (
        "<h2>Zusammensetzung</h2>"
        f'<p class="explain">{n(len(current))} aktuelle Mitglieder, davon {n(women)} Frauen '
        f"({100 * women / len(current):.0f} %) und {n(first)} zum ersten Mal im Bundestag "
        f"({100 * first / len(current):.0f} %). Ein Klick auf eine Fraktion zeigt unten nur ihre Mitglieder.</p>"
        + controls.view("zusammensetzung", "Aktuelle Mitglieder nach Fraktion", chart, table)
    )


def body_page(b: dict, besch: list[dict]) -> str:
    kind_label = "Ausschuss" if b["kind"] == "committee" else "Gremium"
    head = (
        crumbs(("index.html", "Gremien"), (None, b["short"]))
        + f'<section class="card ent-head"><h1>{e(b["short"])}</h1>'
        f'<div class="lines">{kind_label} · {n(len(b["members"]))} Mitgliedschaften in der {WP}. Wahlperiode</div></section>'  # noqa: E501
    )
    members = controls.scope(_stats_section(b["members"]) + _members_section(b["members"]), "Mitgliedschaften",
                             "Mitgliedschaft")  # fmt: skip
    parts = [head, facet("mitglieder", "Mitglieder", members, len({m["person"] for m in b["members"]}))]
    parts.append(facet("reden", "Reden", "", explain="Ausschüsse und Gremien beraten nicht im Plenum. Ihre Mitglieder "
                       "sprechen dort für ihre Fraktion. Ihre Reden stehen in ihren Steckbriefen."))  # fmt: skip
    parts.append(facet("abstimmungen", "Abstimmungen und Beschlüsse", "", explain="Ausschüsse stimmen nicht "
                       "öffentlich ab. Was sie dem Plenum empfehlen, steht in ihren Beschlussempfehlungen unter "
                       "Drucksachen."))  # fmt: skip
    if b["kind"] == "committee":
        docs = sorted(besch, key=lambda d: (d["date"], d["number"]), reverse=True)
        parts.append(facet("drucksachen", "Drucksachen", facts.drucksache_list(docs, "../", "besch", compact=False),
                           len(docs), "Beschlussempfehlungen und Berichte dieses Ausschusses an das Plenum laut "
                           "DIP, die neueste zuerst. „Vorgang“ führt zum Ablauf, in dem die Empfehlung "
                           "beraten und abgestimmt wurde."))  # fmt: skip
    else:
        parts.append(facet("drucksachen", "Drucksachen", "", explain="Keine Drucksachen dieses Gremiums im DIP."))
    parts.append(f"<footer>{FOOTER}</footer>")
    desc = (
        f"{kind_label} des 21. Deutschen Bundestages: {b['short']}, Mitglieder nach Fraktion und Funktion, mit Quelle."
    )
    return shell(root="../", kind="p-body", active="bodies", title=b["short"], desc=desc,
                 body=f'<div class="bodies">{"".join(parts)}</div>', data={"kind": "body", "name": b["name"]},
                 head=STYLE + controls.head("../"))  # fmt: skip


def gremien_index_page(bodies: list[dict], government: bool = False) -> str:
    committees = [b for b in bodies if b["kind"] == "committee"]
    others = [b for b in bodies if b["kind"] != "committee"]
    frac_rows = "".join(
        f'<a class="row" href="../fraktionen/{TOKEN[f]}.html"><span class="t"><span class="ti">{dot(f)} {e(SHORT.get(f, f))}</span></span></a>'  # noqa: E501
        for f in ORDER
    )
    gov = ('<h2>Bundesregierung</h2><div class="rows"><a class="row" href="bundesregierung.html"><span class="t">'
           '<span class="ti">Bundesregierung</span></span></a></div>' if government else "")  # fmt: skip

    def current(b: dict) -> list[dict]:
        return [m for m in b["members"] if m["to"] is None]

    shown = sorted(bodies, key=lambda b: (-len(current(b)), b["short"]))
    fractions = [(TOKEN[f], SHORT.get(f, f), TOKEN[f]) for f in ORDER]
    items = [(f"{b['slug']}.html", b["short"], len(current(b)), Counter(TOKEN.get(m["fraction"], "frl")
              for m in current(b))) for b in shown]  # fmt: skip
    attrs = [f'data-art="{"ausschuss" if b["kind"] == "committee" else "gremium"}"' for b in shown]
    field = controls.tiles(
        items, fractions, "Mitglieder", "Mitglied", "Ausschüsse und Gremien", attrs, listing=True, per=0.8
    )  # a committee of 40 gets 32 cells, the smallest 6
    kinds = [("ausschuss", "Ausschüsse und Unterausschüsse", len(committees), "accent"),
             ("gremium", "weitere Gremien", len(others), "accent")]  # fmt: skip
    lists = controls.scope(
        controls.toolbar("Gremium suchen …") + controls.block("Art", controls.chips("art", kinds, "Art"))
        + controls.view("gremien", "Ausschüsse und Gremien nach Zahl der aktuellen Mitglieder", field, None,
                        "Als Liste"),
        "Gremien", "Gremium",
    )  # fmt: skip
    body = f"""<div class="bodies"><h1>Gremien</h1>
<p class="lead">Die Fraktionen, die Ausschüsse und Unterausschüsse und die weiteren Gremien des 21. Bundestages (Kommissionen, Delegationen, Parlamentariergruppen, Beiräte, Kuratorien und Stiftungsräte, denen der Bundestag Mitglieder entsendet), aus den Stammdaten. Jedes Gremium mit seinen Mitgliedern nach Rolle, der Zusammensetzung nach Fraktion und, bei Ausschüssen, seinen Beschlussempfehlungen. Bundesministerien sind Regierungsämter, keine Gremien des Bundestages, und stehen im jeweiligen Steckbrief unter „Regierungsämter“.</p>
<h2>Fraktionen</h2><div class="rows">{frac_rows}</div>
{gov}
<h2>Ausschüsse und Gremien <span class="n">{n(len(bodies))}</span></h2>
<p class="explain">Jede Kachel ist ein Gremium. Ihre Fläche entspricht der Zahl der aktuellen Mitglieder, mit einer Mindestgröße, damit jeder Name lesbar bleibt. Der Balken zeigt die Fraktionen.</p>
{lists}
</div>
<footer>{FOOTER}</footer>"""  # noqa: E501
    return shell(root="../", kind="p-bodies", active="bodies", title="Gremien",
                 desc="Fraktionen, Ausschüsse, Unterausschüsse und weitere Gremien des 21. Deutschen Bundestages "
                      "mit ihren Mitgliedern.", body=body, data={"kind": "bodies"},
                 head=STYLE + controls.head("../"))  # fmt: skip


# ---------------------------------------------------------------- Fraktionen


def fraction_leadership(ms_f: list[dict], f: str) -> list[dict]:
    """Current fraction leadership among this fraction's members, most senior first (data.lead_rank, as the
    index's seating chart ranks it)."""
    out = []
    for m in ms_f:
        for fr in m["fractions"]:
            if fr["name"] == f and fr["role"] and fr["to_date"] is None:
                rank = lead_rank([fr["role"]])
                if rank is not None:
                    out.append({"member": m, "role": fr["role"], "rank": rank})
    return sorted(out, key=lambda x: x["rank"])


def _avg_age(ms: list[dict]) -> float | None:
    today = dt.date.today()
    ages = []
    for m in ms:
        if m["birth_date"]:
            b = dt.date.fromisoformat(m["birth_date"][:10])
            ages.append(today.year - b.year - ((today.month, today.day) < (b.month, b.day)))
    return sum(ages) / len(ages) if ages else None


def fraction_page(
    f: str,
    ms_f: list[dict],
    leaders: list[dict],
    ch: dict,
    off_f: list[dict],
    ka_row: dict | None,
    coh_row: list[dict] | None,
    gov_f: list[dict],
    speeches: list[dict],
    decided: list[dict],
    roll_call_members: dict[str, list[list]],
    docs: list[dict],
) -> str:
    current = [m for m in ms_f if m["to"] is None]
    women = sum(1 for m in current if m["gender"] == "weiblich")
    first = sum(1 for m in current if not any(wp < WP for wp in m["periods"]))
    age = _avg_age(current)
    lead_rows = "".join(
        f'<div class="row"><div class="t"><a href="../{e(x["member"]["id"])}.html">{e(x["member"]["name"])}</a>'
        f'<div class="sub">{e(x["role"])}</div></div></div>'
        for x in leaders
    )  # fmt: skip
    left_f = [m for m in ch["left"] if m["fraction"] == f]
    joined_f = [m for m in ch["joined"] if m["fraction"] == f]
    moved_in = [x for x in ch["moved"] if x["to"] == f]
    moved_out = [x for x in ch["moved"] if x["from"] == f]
    member_rows = "".join(
        f'<div class="row{" ended" if m["to"] else ""}"><div class="t"><a href="../{e(m["id"])}.html">{e(m["name"])}'
        f'</a></div><div class="d">{_when(m["from"], m["to"])}</div></div>'
        for m in sorted(ms_f, key=lambda m: m["name"])
    )  # fmt: skip
    changes = []
    if left_f or joined_f or moved_in or moved_out:
        items = []
        for m in left_f:
            items.append(
                f'<li>{short_date(m["to"])}: <a href="../{e(m["id"])}.html">{e(m["name"])}</a> ausgeschieden</li>'
            )  # noqa: E501
        for m in joined_f:
            items.append(
                f'<li>{short_date(m["from"])}: <a href="../{e(m["id"])}.html">{e(m["name"])}</a> nachgerückt</li>'
            )  # noqa: E501
        for x in moved_in:
            items.append(
                f'<li>{short_date(x["date"]) if x["date"] else ""}: <a href="../{e(x["member"]["id"])}.html">'
                f"{e(x['member']['name'])}</a> von {frac_link(x['from'])} gewechselt</li>"
            )
        for x in moved_out:
            items.append(
                f'<li>{short_date(x["date"]) if x["date"] else ""}: <a href="../{e(x["member"]["id"])}.html">'
                f"{e(x['member']['name'])}</a> zu {frac_link(x['to'])} gewechselt</li>"
            )
        changes.append(f"<h2>Veränderungen in der Wahlperiode</h2><ul>{''.join(items)}</ul>")
    else:
        changes.append('<h2>Veränderungen in der Wahlperiode</h2><p class="explain">Keine in den Stammdaten.</p>')

    off_rows = "".join(
        f'<li><a href="../{e(o["member"]["id"])}.html">{e(o["member"]["name"])}</a>: {e(o["office"])}</li>'
        for o in off_f
    )  # fmt: skip
    gov_rows = "".join(
        f'<li><a href="../{e(g["id"])}.html">{e(g["name"])}</a>: {e(g["office"])}</li>' for g in gov_f
    )  # fmt: skip

    stats = (
        (
            f'<p class="explain">{n(len(current))} aktuelle Mitglieder, davon {n(women)} Frauen '
            f"({100 * women / len(current):.0f} %) und {n(first)} zum ersten Mal im Bundestag "
            f"({100 * first / len(current):.0f} %)" + (f", Durchschnittsalter {age:.0f} Jahre" if age else "") + "."
            "</p>"
        )
        if current
        else '<p class="explain">Aktuell keine Mitglieder.</p>'
    )

    ka_link = '<a href="../regierung/index.html">Fragen an die Regierung</a>'
    ka_text = (
        (
            f'<p class="explain"><b>{n(ka_row["asked"])}</b> Kleine Anfragen gestellt, '
            f"<b>{n(ka_row['answered'])}</b> beantwortet. Alle Fraktionen im Vergleich: {ka_link}.</p>"
        )
        if ka_row
        else f'<p class="explain">Keine Kleinen Anfragen im Datenbestand. {ka_link}.</p>'
    )
    coh_link = '<a href="../abstimmungen/geschlossenheit.html">Geschlossenheit der Fraktionen</a>'
    coh_text = (
        (
            f'<p class="explain">Durchschnittliche Geschlossenheit in {n(len(coh_row))} namentlichen Abstimmungen: '
            f"<b>{cohesion.pct(cohesion.mean([p['rice'] for p in coh_row if p['rice'] is not None]), 3)}</b>. "
            f"Alle Abweichungen: {coh_link}.</p>"
        )
        if coh_row
        else f'<p class="explain">Keine namentlichen Abstimmungen mit Liste im Datenbestand. {coh_link}.</p>'
    )

    head = (
        crumbs(("../gremien/index.html", "Gremien"), (None, "Fraktion"))
        + f'<section class="card ent-head"><h1>{dot(f)} {e(f)}</h1>'
        f'<div class="lines">{n(len(current))} aktuelle Mitglieder in der {WP}. Wahlperiode</div></section>'
    )
    members = []
    if lead_rows:
        members.append(f'<h3>Fraktionsführung</h3><div class="rows memb">{lead_rows}</div>')
    members.append(f"<h3>Zusammensetzung</h3>{stats}")
    members.append(f'<h3>Alle Mitglieder</h3><div class="rows memb">{member_rows}</div>')
    members += changes
    if off_rows:
        members.append(f"<h3>Ämter im Ausschuss</h3><ul>{off_rows}</ul>")
    if gov_rows:
        members.append(f"<h3>Mitglieder der Bundesregierung</h3><ul>{gov_rows}</ul>")
    parts = [head, facet("mitglieder", "Mitglieder", "".join(members), len(ms_f))]
    token = TOKEN.get(f, "frl")
    shown = _newest(speeches)
    parts.append(facet("reden", "Reden", facts.speech_list(shown, "../", "reden", limit=None, note=_more(
        len(shown), len(speeches), f'Alle Reden finden sich über die <a href="../suche.html?Fraktion={e(f)}">Suche '
                                   f'mit dem '
        f"Filter Fraktion</a> und in den Steckbriefen der Mitglieder. Redeanteile im Vergleich zeigt die "
        '<a href="../debatte/index.html">Debattenkultur</a>.')), len(speeches)))  # fmt: skip
    ds = [d for d in decided if d["kind"] == "handzeichen" and f in (d.get("fractions") or {})
          or d["kind"] == "namentlich" and any(m[2] == f for m in roll_call_members.get(d["id"], []))]  # fmt: skip
    newest = sorted(ds, key=lambda d: (d["date"], d["order"]), reverse=True)[:FACET]
    parts.append(facet(
        "abstimmungen", "Abstimmungen und Beschlüsse",
        coh_text + facts.decision_list(newest, "../", "dec", limit=None, group=f,
                                       members=lambda d: roll_call_members.get(d["id"]),
                                       note=_more(len(newest), len(ds), 'Alle Beschlüsse stehen unter <a href="../'
                                                  'abstimmungen/index.html">Abstimmungen</a>.')),
        len(ds), "Rechts die Position der Fraktion. Bei namentlichen Abstimmungen ist das die Mehrheit ihrer Stimmen, "
        "gezählt wie in den Steckbriefen, bei Handzeichen die Feststellung der Sitzungsleitung.",
    ))  # fmt: skip
    own = [d for d in docs if f in d["groups"]]
    shown = _newest(own)
    parts.append(facet("drucksachen", "Drucksachen", ka_text + facts.drucksache_list(
        shown, "../", "drs", compact=False, limit=None, note=_more(len(shown), len(own), "Alle stehen im DIP.")),
        len(own), "Drucksachen, die die Fraktion laut DIP als Urheber führen, die neueste zuerst."))  # fmt: skip
    parts.append(f"<footer>{FOOTER}</footer>")
    desc = (
        f"Die Fraktion {f} im 21. Deutschen Bundestag: Mitglieder, Führung, Reden, Abstimmungen und Drucksachen, "
        "mit Quelle."
    )
    return shell(root="../", kind="p-fraction", active="bodies", title=f, desc=desc,
                 body=f'<div class="bodies">{"".join(parts)}</div>', data={"kind": "fraction", "name": f,
                 "token": token}, head=STYLE)  # fmt: skip


def _when(frm: str | None, to: str | None) -> str:
    if to:
        return f"{short_date(frm)} – {short_date(to)}" if frm else f"bis {short_date(to)}"
    return f"seit {short_date(frm)}" if frm else ""


# ---------------------------------------------------------------- Bundesregierung


def government_page(roles: dict[str, list[dict]], names: dict[str, str], speeches: list[dict],
                    docs: list[dict]) -> str:  # fmt: skip
    """The Bundesregierung as a group: everyone with an office in `government_role` (Wikidata, Stammdaten, protocol
    evidence), current first, with dates; the speeches given in a government role; the Drucksachen with the
    Bundesregierung as Urheber. It does not vote as a group, so it has no cohesion."""
    rows = []
    for pid, offices in roles.items():
        for o in offices:
            if o["kind"] == "beamteter_sts":
                continue  # civil servants, not members of the government
            when = (f"laut Plenarprotokoll, zuletzt belegt am {short_date(o['to'] or o['from'])}" if o["evidence"]
                    else _when(o["from"], o["to"]))  # fmt: skip
            src = next((x for x in o["sources"] if x.get("url")), None)
            srcl = f' · <a href="{e(src["url"])}">Quelle</a>' if src else ""
            rows.append((o["to"] is not None and not o["evidence"], names.get(pid, pid), (
                f'<div class="row{" ended" if o["to"] and not o["evidence"] else ""}"><div class="t">'
                f'<a href="../{e(urls.person(pid))}">{e(names.get(pid, pid))}</a><div class="sub">{e(o["office"])}'
                f'</div></div><div class="d">{e(when)}{srcl}</div></div>')))  # fmt: skip
    rows.sort(key=lambda r: (r[0], r[1]))
    people = len({r[1] for r in rows})
    head = (crumbs(("index.html", "Gremien"), (None, "Bundesregierung"))
            + '<section class="card ent-head"><h1>Bundesregierung</h1><div class="lines">Bundeskanzler, '
            "Bundesminister, Staatsminister und Parlamentarische Staatssekretäre der 21. Wahlperiode, aus Wikidata, "
            "den Stammdaten und den Plenarprotokollen</div></section>")  # fmt: skip
    parts = [head, facet("mitglieder", "Mitglieder", f'<div class="rows memb">{"".join(r[2] for r in rows)}</div>',
                         people, "Aktuelle Ämter zuerst. Beamtete Staatssekretärinnen und Staatssekretäre gehören der "
                         "Bundesregierung nicht an.")]  # fmt: skip
    gov = [s for s in speeches if s.get("role") and OFFICE.search(s["role"]) and "räsident" not in s["role"]]
    shown = _newest(gov)
    parts.append(facet("reden", "Reden", facts.speech_list(shown, "../", "reden", limit=None, note=_more(
        len(shown), len(gov), "Alle stehen in den Steckbriefen der Regierungsmitglieder.")), len(gov),
        "Reden und Antworten in einem Regierungsamt, wie das Protokoll die Rolle nennt."))  # fmt: skip
    parts.append(facet("abstimmungen", "Abstimmungen und Beschlüsse", "", explain="Die Bundesregierung stimmt im "
                       "Bundestag nicht ab. Regierungsmitglieder mit Mandat stimmen als Abgeordnete in ihrer "
                       "Fraktion. Ihre Stimmen stehen in ihren Steckbriefen. Deshalb gibt es hier auch keine "
                       "Geschlossenheit."))  # fmt: skip
    own = [d for d in docs if GOVERNMENT_GROUP in d["groups"]]
    shown = _newest(own)
    parts.append(facet("drucksachen", "Drucksachen", facts.drucksache_list(
        shown, "../", "drs", compact=False, limit=None, note=_more(len(shown), len(own), "Alle stehen im DIP.")),
        len(own), "Gesetzentwürfe, Unterrichtungen und Antworten, die die Bundesregierung laut DIP als Urheber "
        "führen."))  # fmt: skip
    parts.append(f"<footer>{FOOTER}</footer>")
    return shell(root="../", kind="p-body", active="bodies", title="Bundesregierung",
                 desc="Die Bundesregierung in der 21. Wahlperiode: Mitglieder mit Amtszeiten, Reden im Amt und "
                      "Drucksachen, mit Quelle.", body=f'<div class="bodies">{"".join(parts)}</div>',
                 data={"kind": "government"}, head=STYLE)  # fmt: skip


# ---------------------------------------------------------------- write


def write(
    conn: sqlite3.Connection,
    out: Path,
    cards: list[dict],
    government: list[dict],
    decisions: list[dict],
    roll_call_members: dict[str, list[list]],
) -> dict[str, int]:
    """Write gremien/ (with the Bundesregierung when the store has `government_role`) and fraktionen/, one page
    for each of the six fractions even when the store has no member of one (the Gremien index links all six)."""
    docs = data.drucksache_facts(conn)
    # a Drucksache links its Vorgang only when that has a page (not every Kleine Anfrage or Antrag reaches the plenum)
    have = {f.stem for f in (out / "vorgaenge").glob("*.html")}
    for d in docs:
        if d["vorgang"] not in have:
            d["vorgang"] = None
    speeches = data.speech_facts(cards)
    bodies = load_bodies(conn, cards)
    besch = besch_by_committee(docs)
    roles = data.government_roles(conn)
    gd = out / "gremien"
    gd.mkdir(parents=True, exist_ok=True)
    for b in bodies:
        (gd / f"{b['slug']}.html").write_text(body_page(b, besch.get(b["name"], [])), encoding="utf-8")
    if roles:
        names = {c["id"]: c["name"] for c in cards}
        (gd / "bundesregierung.html").write_text(government_page(roles, names, speeches, docs), encoding="utf-8")
    (gd / "index.html").write_text(gremien_index_page(bodies, bool(roles)), encoding="utf-8")

    ms = careers.members(conn)
    ch = careers.changes(ms, careers.constituted(conn))
    off = careers.offices(conn, ms)
    ka_by_f = (
        {r["fraction"]: r for r in questions.ka_summary(questions.kleine_anfragen(conn))}
        if has_table(conn, "drucksache")
        else {}
    )  # noqa: E501
    coh_series = cohesion.cohesion(decisions, roll_call_members)["series"] if decisions and roll_call_members else {}

    fd = out / "fraktionen"
    fd.mkdir(parents=True, exist_ok=True)
    fractions = sorted({m["fraction"] for m in ms} | set(ORDER), key=fraction_order)
    for f in fractions:
        ms_f = [m for m in ms if m["fraction"] == f]
        leaders = fraction_leadership(ms_f, f)
        off_f = [o for o in off if o["member"]["fraction"] == f]
        gov_f = [g for g in government if g["fraction"] == f]
        sps = [s for s in speeches if s["fraction"] == f and s["kind"] in ("rede", "kurz")]
        html = fraction_page(f, ms_f, leaders, ch, off_f, ka_by_f.get(f), coh_series.get(f), gov_f, sps, decisions,
                             roll_call_members, docs)  # fmt: skip
        (fd / f"{TOKEN.get(f, 'frl')}.html").write_text(html, encoding="utf-8")
    return {"gremien": len(bodies) + 1 + bool(roles), "fraktionen": len(fractions)}
