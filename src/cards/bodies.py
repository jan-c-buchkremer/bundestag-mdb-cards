"""Gremien: `gremien/index.html`, one page per Ausschuss, Unterausschuss and other Bundestag body
(`gremien/<slug>.html`), and one page per Fraktion (`fraktionen/<slug>.html`, plus fraktionslos).

Built from the Stammdaten's `membership` table (kind committee/other for the Gremien, kind fraction for the
Fraktionen), joined with what the cards already know (fraction, gender, first term) and, for the Fraktionen, with
the Karrieren page's own numbers (careers.py) so both pages agree. Federal ministries are offices a minister or
Staatssekretär holds, not Gremien the Bundestag itself forms, and are left out here; every card already shows them
under "Regierungsämter". No ranking of members, every number links to its source (docs/plan.md)."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from cards import careers, cohesion, questions
from cards.data import (
    DIP_DOC,
    NO_FRACTION,
    WP,
    committee_short,
    dip_subject,
    drucksache_pdf,
    has_table,
    lead_rank,
    slugify,
)
from cards.ui import FOOTER, SHORT, TOKEN, dot, e, frac_link, fraction_order, n, shell, short_date

# federal ministries and the Kanzleramt are government offices, already on the card as "Regierungsämter"
_EXCLUDE_EXACT = {"Auswärtiges Amt", "Bundeskanzleramt"}
# DIP's Urheber on a Beschlussempfehlung sometimes spells a committee's name differently from the Stammdaten
_ALIASES = {
    "Ausschuss für Wahlprüfung, Immunität und Geschäftsordnung": "Ausschuss für Wahlprüfung, Immunität u. Geschäftsordnung",  # noqa: E501
    "Sportausschuss": "Ausschuss für Sport und Ehrenamt",
    "Vermittlungsausschuss": "Mitglieder des Ausschusses nach Artikel 77 Abs. 2 des Grundgesetzes (Vermittlungsausschuss)",  # noqa: E501
}
_LEAD = re.compile(r"^(Vorsitzende[r]?|Delegationsleiter)$")
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
FILTER_JS = """<script>
(() => {
  const q = document.getElementById('gq'), rows = [...document.querySelectorAll('#gremien a.row')];
  const count = document.getElementById('gcount');
  function apply() {
    const words = q.value.toLowerCase().split(/\\s+/).filter(Boolean);
    let shown = 0;
    for (const r of rows) { const ok = words.every((w) => r.textContent.toLowerCase().includes(w)); r.hidden = !ok; shown += ok; }
    count.textContent = shown === rows.length ? `${rows.length} Gremien` : `${shown} von ${rows.length}`;
  }
  q.addEventListener('input', apply);
  apply();
})();
</script>"""  # noqa: E501


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


def besch_by_committee(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Per committee (by name, DIP aliases resolved): its Beschlussempfehlungen (and -berichte), oldest first."""
    if not has_table(conn, "drucksache") or not has_table(conn, "vorgang_drucksache"):
        return {}
    out: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute(
        """SELECT d.id, d.number, d.title, d.date, d.pdf_url, d.originators,
                  (SELECT vd.vorgang_id FROM vorgang_drucksache vd JOIN vorgang v ON v.id = vd.vorgang_id
                   WHERE vd.drucksache_id = d.id AND v.type = 'Gesetzgebung' LIMIT 1) AS vorgang_id
           FROM drucksache d WHERE d.wahlperiode = ? AND d.type LIKE '%Beschlussempfehlung%'
           ORDER BY d.date, d.number""",
        (WP,),
    ):
        try:
            names = json.loads(r["originators"] or "[]")
        except ValueError:
            names = []
        for raw in names:
            name = _ALIASES.get(raw, raw)
            out[name].append({
                "number": r["number"], "title": dip_subject(r["title"]) or r["title"], "date": r["date"],
                "url": DIP_DOC.format(r["id"]), "pdf": r["pdf_url"] or drucksache_pdf(r["number"]),
                "vorgang": r["vorgang_id"],
            })  # fmt: skip
    return out


def _member_row(m: dict) -> str:
    if m["to"]:
        when = f"{short_date(m['from'])} – {short_date(m['to'])}" if m["from"] else f"bis {short_date(m['to'])}"
    else:
        when = f"seit {short_date(m['from'])}" if m["from"] else ""
    who = f'<a href="../{e(m["person"])}.html">{e(m["name"])}</a>'
    sub = f'<div class="sub">{e(m["role"])}</div>' if m["role"] else ""
    return (f'<div class="row{" ended" if m["to"] else ""}"><div class="t">{who} {dot(m["fraction"])}'
            f'{frac_link(m["fraction"])}{sub}</div><div class="d">{when}</div></div>')  # fmt: skip


def _members_section(ms: list[dict]) -> str:
    groups: dict[int, list[dict]] = defaultdict(list)
    for m in ms:
        groups[role_group(m["role"])].append(m)
    parts = []
    for i, label in enumerate(GROUPS):
        if not groups[i]:
            continue
        rows = "".join(_member_row(m) for m in sorted(groups[i], key=lambda m: m["name"]))
        parts.append(f'<h3>{e(label)} <span class="n">{n(len(groups[i]))}</span></h3>'
                     f'<div class="rows memb">{rows}</div>')  # fmt: skip
    return f"<h2>Mitglieder</h2>{''.join(parts)}"


def _stats_section(ms: list[dict]) -> str:
    current = [m for m in ms if m["to"] is None]
    if not current:
        return '<h2>Zusammensetzung</h2><p class="explain">Aktuell keine Mitglieder im Datenbestand.</p>'
    by_fraction = Counter(m["fraction"] for m in current)
    women = sum(1 for m in current if m["gender"] == "weiblich")
    first = sum(1 for m in current if m["first_term"])
    bar = "".join(
        f'<i style="width:{100 * by_fraction[f] / len(current):.2f}%;background:var(--{TOKEN.get(f, "reg")})" '
        f'title="{e(SHORT.get(f, f))}: {by_fraction[f]}"></i>'
        for f in sorted(by_fraction, key=fraction_order)
    )  # fmt: skip
    comp_rows = "".join(
        f'<tr><td>{dot(f)} {frac_link(f)}</td><td class="num">{by_fraction[f]}</td></tr>'
        for f in sorted(by_fraction, key=fraction_order)
    )  # fmt: skip
    return (
        "<h2>Zusammensetzung</h2>"
        f'<p class="explain">{n(len(current))} aktuelle Mitglieder, davon {n(women)} Frauen '
        f"({100 * women / len(current):.0f} %) und {n(first)} zum ersten Mal im Bundestag "
        f"({100 * first / len(current):.0f} %).</p>"
        f'<span class="bar big comp">{bar}</span>'
        '<div class="rows"><table class="plenum"><thead><tr><th>Fraktion</th><th>Mitglieder</th></tr></thead>'
        f"<tbody>{comp_rows}</tbody></table></div>"
    )


def _besch_section(items: list[dict], have_gesetze: set[str]) -> str:
    if not items:
        return '<h2>Beschlussempfehlungen</h2><p class="explain">Keine Beschlussempfehlungen dieses Ausschusses im Datenbestand.</p>'  # noqa: E501
    rows = []
    for x in items:
        if x["vorgang"] and f"{x['vorgang']}.html" in have_gesetze:
            link = f'<a href="../gesetze/{e(x["vorgang"])}.html">{e(x["number"])}</a>'
        else:
            link = f'<a href="{e(x["url"])}">{e(x["number"])}</a>'
        rows.append(f"<li><b>{short_date(x['date'])}</b> {link}: {e(x['title'])}</li>")
    explain = ("Beschlussempfehlungen (und -berichte) dieses Ausschusses an das Plenum, laut DIP-Urheberangabe. Wo "
               "die Drucksache zu einem Gesetzgebungsvorgang gehört, führt der Link zu dessen Seite, sonst zur "
               "Drucksache im DIP.")  # fmt: skip
    return (
        f'<h2>Beschlussempfehlungen <span class="n">{n(len(items))}</span></h2>'
        f'<p class="explain">{explain}</p>'
        f'<ul class="besch">{"".join(rows)}</ul>'
    )


def body_page(b: dict, besch: list[dict], have_gesetze: set[str]) -> str:
    kind_label = "Ausschuss" if b["kind"] == "committee" else "Gremium"
    head = (
        f'<p class="crumbs"><a href="index.html">Gremien</a></p>'
        f'<section class="card"><h1>{e(b["short"])}</h1>'
        f'<div class="lines">{kind_label} · {n(len(b["members"]))} Mitgliedschaften in der {WP}. Wahlperiode</div></section>'  # noqa: E501
    )
    parts = [head, _stats_section(b["members"]), _members_section(b["members"])]
    if b["kind"] == "committee":
        parts.append(_besch_section(besch, have_gesetze))
    parts.append(f"<footer>{FOOTER}</footer>")
    desc = (
        f"{kind_label} des 21. Deutschen Bundestages: {b['short']}, Mitglieder nach Fraktion und Funktion, mit Quelle."
    )
    return shell(root="../", kind="p-body", active="bodies", title=b["short"], desc=desc,
                 body=f'<div class="bodies">{"".join(parts)}</div>', data={"kind": "body", "name": b["name"]},
                 head=STYLE)  # fmt: skip


def gremien_index_page(bodies: list[dict]) -> str:
    committees = [b for b in bodies if b["kind"] == "committee"]
    others = [b for b in bodies if b["kind"] != "committee"]
    frac_rows = "".join(
        f'<a class="row" href="../fraktionen/{TOKEN[f]}.html"><span class="t"><span class="ti">{dot(f)} {e(SHORT.get(f, f))}</span></span></a>'  # noqa: E501
        for f in ("AfD", "CDU/CSU", "BÜNDNIS 90/DIE GRÜNEN", "SPD", "Die Linke", NO_FRACTION)
    )

    def row(b: dict) -> str:
        current = sum(1 for m in b["members"] if m["to"] is None)
        return (f'<a class="row" href="{e(b["slug"])}.html"><span class="t"><span class="ti">{e(b["short"])}</span>'
                f'</span><span class="l">{n(current)} Mitglieder</span></a>')  # fmt: skip

    body = f"""<div class="bodies"><h1>Gremien</h1>
<p class="lead">Die Fraktionen, die Ausschüsse und Unterausschüsse und die weiteren Gremien des 21. Bundestages (Kommissionen, Delegationen, Parlamentariergruppen, Beiräte, Kuratorien und Stiftungsräte, denen der Bundestag Mitglieder entsendet), aus den Stammdaten. Jedes Gremium mit seinen Mitgliedern nach Rolle, der Zusammensetzung nach Fraktion und, bei Ausschüssen, seinen Beschlussempfehlungen. Bundesministerien sind Regierungsämter, keine Gremien des Bundestages, und stehen auf der jeweiligen Karte unter „Regierungsämter“.</p>
<h2>Fraktionen</h2><div class="rows">{frac_rows}</div>
<h2>Ausschüsse <span class="n">{n(len(committees))}</span></h2>
<div class="filters"><input type="search" id="gq" placeholder="Gremium suchen …" autocomplete="off"></div>
<div class="count" id="gcount">{n(len(bodies))} Gremien</div>
<div class="rows" id="gremien">{"".join(row(b) for b in committees)}{"".join(row(b) for b in others)}</div>
</div>
<footer>{FOOTER}</footer>
{FILTER_JS}"""  # noqa: E501
    return shell(root="../", kind="p-bodies", active="bodies", title="Gremien",
                 desc="Fraktionen, Ausschüsse, Unterausschüsse und weitere Gremien des 21. Deutschen Bundestages "
                      "mit ihren Mitgliedern.", body=body, data={"kind": "bodies"}, head=STYLE)  # fmt: skip


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
    reden: int,
    words: int,
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
        f'<div class="row{" ended" if m["to"] else ""}"><div class="t"><a href="../{e(m["id"])}.html">{e(m["name"])}</a></div>'  # noqa: E501
        f"<div class=\"d\">{f'bis {short_date(m['to'])}' if m['to'] else ''}</div></div>"
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
        f'<p class="crumbs"><a href="../gremien/index.html">Gremien</a></p>'
        f'<section class="card"><h1>{dot(f)} {e(f)}</h1>'
        f'<div class="lines">{n(len(current))} aktuelle Mitglieder in der {WP}. Wahlperiode</div></section>'
    )
    parts = [head]
    if lead_rows:
        parts.append(f'<h2>Fraktionsführung</h2><div class="rows memb">{lead_rows}</div>')
    parts.append(f"<h2>Zusammensetzung</h2>{stats}")
    parts.append(
        f'<h2>Mitglieder <span class="n">{n(len(current))}</span></h2><div class="rows memb">{member_rows}</div>'
    )  # noqa: E501
    parts += changes
    parts.append(
        f'<h2>Reden und Wörter</h2><p class="explain"><b>{n(reden)}</b> Reden. Redeanteile im Vergleich: '
        f'<a href="../debatte/index.html">Debattenkultur</a>.</p>'
    )
    parts.append(f"<h2>Geschlossenheit</h2>{coh_text}")
    parts.append(f"<h2>Kleine Anfragen</h2>{ka_text}")
    if off_rows:
        parts.append(f"<h2>Ämter im Ausschuss</h2><ul>{off_rows}</ul>")
    if gov_rows:
        parts.append(f"<h2>Mitglieder der Bundesregierung</h2><ul>{gov_rows}</ul>")
    parts.append(f"<footer>{FOOTER}</footer>")
    desc = (
        f"Die Fraktion {f} im 21. Deutschen Bundestag: Mitglieder, Führung, Redeanteile und Abstimmungen, mit Quelle."
    )
    return shell(root="../", kind="p-fraction", active="bodies", title=f, desc=desc,
                 body=f'<div class="bodies">{"".join(parts)}</div>', data={"kind": "fraction", "name": f},
                 head=STYLE)  # fmt: skip


# ---------------------------------------------------------------- write


def write(
    conn: sqlite3.Connection,
    out: Path,
    cards: list[dict],
    government: list[dict],
    decisions: list[dict],
    roll_call_members: dict[str, list[list]],
) -> dict[str, int]:
    """Write gremien/ and fraktionen/. Call after gesetze/ so Beschlussempfehlungen can link the bill page."""
    bodies = load_bodies(conn, cards)
    besch = besch_by_committee(conn)
    have_gesetze = {p.name for p in (out / "gesetze").iterdir()} if (out / "gesetze").is_dir() else set()
    gd = out / "gremien"
    gd.mkdir(parents=True, exist_ok=True)
    for b in bodies:
        (gd / f"{b['slug']}.html").write_text(body_page(b, besch.get(b["name"], []), have_gesetze), encoding="utf-8")
    (gd / "index.html").write_text(gremien_index_page(bodies), encoding="utf-8")

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
    fractions = sorted({m["fraction"] for m in ms} | {NO_FRACTION}, key=fraction_order)
    for f in fractions:
        ms_f = [m for m in ms if m["fraction"] == f]
        leaders = fraction_leadership(ms_f, f)
        off_f = [o for o in off if o["member"]["fraction"] == f]
        gov_f = [g for g in government if g["fraction"] == f]
        reden = sum(len(c["reden"]) for c in cards if c["fraction"] == f)
        words = sum(s["words"] for c in cards if c["fraction"] == f for s in c["reden"])
        html = fraction_page(f, ms_f, leaders, ch, off_f, ka_by_f.get(f), coh_series.get(f), gov_f, reden, words)
        (fd / f"{TOKEN.get(f, 'frl')}.html").write_text(html, encoding="utf-8")
    return {"gremien": len(bodies) + 1, "fraktionen": len(fractions)}
