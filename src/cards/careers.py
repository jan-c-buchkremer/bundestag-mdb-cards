"""Rollen: the section `#rollen` of the Abgeordnete page (index.html, below the plenum), so the reader learns who sits
there and who holds which role (docs/plan.md 12.3, D28): the Präsidium, the fraction chairs, the committee chairs,
the members in the government, and from the Stammdaten's mandate history (every Wahlperiode since 1949) and the
WP 21 fraction memberships how long the current members have served, who left and who moved up, and who switched
fractions. Each role links the entity that owns it (the Gremium, the Fraktion, the Bundesregierung, D25). Counts
per fraction and lists by date, no member ranking (docs/plan.md). The former `karrieren/index.html` is a stub to
the section. Also the first speech in WP 21 for each card (`annotate`)."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from cards import redirects, urls
from cards.data import NO_FRACTION, PARTY_TO_FRACTION, WP, display_name, feminine, government_roles
from cards.ui import SHORT, TOKEN, dot, e, fraction_order, n, short_date

BUCKETS = ("1", "2", "3", "4", "5 und mehr")
CHAIR = re.compile(r"^(Vorsitzende[r]?|Delegationsleiter)$")  # a Gremium's chair (bodies.py groups by it too)
FRACTION_CHAIR = re.compile(r"^(Vorsitzende[r]?|Erster? Vorsitzende[r]?)$")
PRESIDIUM = "Präsidium"
STATES = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}  # as card.js
# the chair calls the next speaker to a first speech ("Das ist ihre erste Rede.", "zu seiner ersten Rede") in the
# paragraph before it, and congratulates in the second person after it ("Gratulation zu Ihrer ersten Rede"). One
# paragraph often does both for two people ("Gratulation zu Ihrer ersten Rede! – Die letzte Rede hält Claudia
# Moll."), so the call must name the speaker in the same part between dashes, and case tells "ihre" from "Ihre".
_CALLED = re.compile(r"\b(?:ihre|seine|die)r?\s+erste[n]?\s+Rede\b|\bJungfernrede\b|^Zu Ihrer ersten Rede\b")
_THANKED = re.compile(r"\bIhre[rn]?\s+erste[n]?\s+Rede\b")
_DASH = re.compile(r"\s[–-]\s")
_NOT = re.compile(r"\b(?:nicht|keine)\b[^.–]*\berste", re.I)  # "dass es nicht Ihre erste Rede war"


def members(conn: sqlite3.Connection) -> list[dict]:
    """Everyone with a WP 21 mandate in the Stammdaten: name, fraction (the latest WP 21 membership, else the
    party's), the Wahlperioden served, the WP 21 mandate's dates and state."""
    periods: dict[str, list[int]] = defaultdict(list)
    for r in conn.execute("SELECT person_id, wahlperiode FROM mandate ORDER BY wahlperiode"):
        periods[r["person_id"]].append(r["wahlperiode"])
    fractions: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute(
        "SELECT * FROM membership WHERE wahlperiode = ? AND kind = 'fraction' ORDER BY from_date, id", (WP,)
    ):
        fractions[r["person_id"]].append(r)
    out = []
    for r in conn.execute(
        """SELECT m.person_id, m.from_date, m.to_date, m.state, m.source_url, m.source_document_id, p.*
           FROM mandate m JOIN person p ON p.id = m.person_id WHERE m.wahlperiode = ?""",
        (WP,),
    ):
        rows = fractions[r["person_id"]]
        open_rows = [f for f in rows if f["to_date"] is None] or rows
        fraction = open_rows[-1]["name"] if open_rows else PARTY_TO_FRACTION.get(r["party"], r["party"])
        out.append(
            {"id": r["person_id"], "name": display_name(r), "last_name": r["last_name"], "gender": r["gender"],
             "birth_date": r["birth_date"], "fraction": fraction or NO_FRACTION, "periods": periods[r["person_id"]],
             "from": r["from_date"], "to": r["to_date"], "state": r["state"], "fractions": [dict(f) for f in rows],
             "url": r["source_url"], "doc": r["source_document_id"]}
        )  # fmt: skip
    return sorted(out, key=lambda m: (m["last_name"], m["name"], m["id"]))


def tenure(ms: list[dict]) -> list[dict]:
    """Per fraction, the current members (mandate not ended) by number of Wahlperioden served."""
    by: dict[str, Counter] = defaultdict(Counter)
    for m in ms:
        if m["to"] is None:
            by[m["fraction"]][BUCKETS[min(len(m["periods"]), len(BUCKETS)) - 1]] += 1
    return [
        {"fraction": f, "counts": c, "total": sum(c.values()), "first": c["1"] / sum(c.values())}
        for f, c in sorted(by.items(), key=lambda x: fraction_order(x[0]))
    ]


def constituted(conn: sqlite3.Connection) -> str | None:
    return conn.execute("SELECT min(date) FROM sitting WHERE wahlperiode = ?", (WP,)).fetchone()[0]


def changes(ms: list[dict], start: str | None) -> dict[str, list[dict]]:
    """Who left the Bundestag (mandate ended), who moved up (mandate began after the constituent sitting), and
    fraction changes (a second, different fraction, or leaving a fraction while the mandate runs). A mover-up is
    paired with the member who left before from the same state and fraction, when exactly that one fits."""
    left = sorted((m for m in ms if m["to"]), key=lambda m: (m["to"], m["name"]))
    joined = sorted((m for m in ms if start and m["from"] > start), key=lambda m: (m["from"], m["name"]))
    taken: set[str] = set()
    for m in joined:
        fits = [x for x in left if x["id"] not in taken and x["state"] == m["state"]
                and x["fraction"] == m["fraction"] and x["to"] <= m["from"]]  # fmt: skip
        m["after"] = fits[-1] if fits else None
        if m["after"]:
            taken.add(m["after"]["id"])
    moved = []
    for m in ms:
        rows = m["fractions"]
        for prev, cur in zip(rows, rows[1:], strict=False):
            if cur["name"] != prev["name"]:
                moved.append({"member": m, "from": prev["name"], "to": cur["name"],
                              "date": cur["from_date"] or prev["to_date"]})  # fmt: skip
        last = rows[-1] if rows else None
        if last and last["to_date"] and m["to"] is None and all(r["to_date"] for r in rows):
            moved.append({"member": m, "from": last["name"], "to": NO_FRACTION, "date": last["to_date"]})
    moved.sort(key=lambda x: (x["date"] or "", x["member"]["name"]))
    return {"left": left, "joined": joined, "moved": moved}


def offices(conn: sqlite3.Connection, ms: list[dict]) -> list[dict]:
    """Government offices (foundation `government_role`) held by WP 21 members, by start date."""
    by_id = {m["id"]: m for m in ms}
    out = []
    for pid, held in government_roles(conn).items():
        if pid not in by_id:
            continue
        m = by_id[pid]
        for o in held:
            office = feminine(o["office"]) if m["gender"] == "weiblich" else o["office"]
            out.append({**o, "office": office, "member": m})
    return sorted(out, key=lambda o: (o["from"] or "", o["member"]["name"]))


def first_speech(conn: sqlite3.Connection, card: dict) -> dict | None:
    """The card's earliest rede in WP 21 (as `data.speeches` groups them, Regierungsbefragung left out) and whether
    the chair calls it the speaker's first speech: announcing it by name in the paragraph before, or congratulating
    in the paragraphs in and after it."""
    redes = card["reden"] + card["kurz"]
    if not redes:
        return None
    s = min(redes, key=lambda r: (r["date"], r["sitting"], r["id"]))
    pos = conn.execute(
        "SELECT min(position), max(position) FROM speech WHERE sitting_id = ? AND (id = ? OR id LIKE ?)",
        (s["sitting"], s["id"], s["id"] + "-%"),
    ).fetchone()
    said = False
    if pos[0] is not None:
        for r in conn.execute(
            """SELECT s.position, p.text FROM speech_paragraph p JOIN speech s ON s.id = p.speech_id
               WHERE s.sitting_id = ? AND s.position BETWEEN ? AND ? AND p.kind = 'chair'""",
            (s["sitting"], pos[0] - 1, pos[1]),
        ):
            if _NOT.search(r["text"]):
                continue
            called = any(_CALLED.search(x) and card["last_name"] in x for x in _DASH.split(r["text"]))
            said |= called or (r["position"] >= pos[0] and bool(_THANKED.search(r["text"])))
    return {
        "id": s["id"],
        "date": s["date"],
        "sitting": s["sitting"],
        "title": s["title"],
        "maiden": said,
        "href": urls.speech(s["id"]),
    }


def annotate(conn: sqlite3.Connection, cards: list[dict]) -> None:
    """Add `first_speech` to every member card (the Laufbahn tab shows it)."""
    for c in cards:
        c["first_speech"] = first_speech(conn, c) if c["kind"] == "member" else None


# ---------------------------------------------------------------- the Rollen section


def _card(m: dict, root: str = "") -> str:
    return f'<a href="{root}{e(m["id"])}.html">{e(m["name"])}</a>'


def _frac(f: str) -> str:
    return f"{dot(f)} {e(SHORT.get(f, f))}"


def _state(m: dict) -> str:
    return e(STATES.get(m["state"], m["state"]))


def _pct(x: float) -> str:
    return f"{100 * x:.0f} %"


def _tenure_section(rows: list[dict]) -> str:
    if not rows:
        return '<h3>Wie lange schon im Bundestag</h3><p class="explain">Keine Mandate im Datenbestand.</p>'
    body = "".join(
        f'<tr><td class="l">{_frac(r["fraction"])}</td>'
        + "".join(f"<td>{n(r['counts'][b]) if r['counts'][b] else ''}</td>" for b in BUCKETS)
        + f"<td>{n(r['total'])}</td><td>{_pct(r['first'])}</td></tr>"
        for r in rows
    )
    total = Counter()
    for r in rows:
        total.update(r["counts"])
    all_n = sum(total.values())
    foot = (
        '<tr><td class="l">zusammen</td>' + "".join(f"<td>{n(total[b])}</td>" for b in BUCKETS)
        + f"<td>{n(all_n)}</td><td>{_pct(total['1'] / all_n)}</td></tr>"
    )  # fmt: skip
    return (
        "<h3>Wie lange schon im Bundestag</h3>"
        '<p class="explain">Wahlperioden der heutigen Mitglieder, die 21. mitgezählt, nach Fraktion; Pausen zählen '
        "nicht mit. „Erstmals“ heißt: nur in der 21. Wahlperiode. Grundlage: alle Mandate seit 1949 in den "
        "Stammdaten.</p>"
        '<div class="rows"><table class="plenum"><thead><tr><th class="l">Fraktion</th>'
        + "".join(f"<th>{b}</th>" for b in BUCKETS)
        + f"<th>Mitglieder</th><th>erstmals</th></tr></thead><tbody>{body}</tbody><tfoot>{foot}</tfoot></table></div>"
    )


def _changes_section(ch: dict) -> str:
    none = '<p class="explain">Keine in den Stammdaten.</p>'

    def lst(items: list[str]) -> str:
        return f"<ul>{''.join(items)}</ul>" if items else none

    joined = [f"<li>{short_date(m['from'])}: {_card(m)} ({_frac(m['fraction'])}, {_state(m)})"
              + (f", nach dem Ausscheiden von {_card(m['after'])}" if m.get("after") else "") + "</li>"
              for m in ch["joined"]]  # fmt: skip
    left = [f"<li>{short_date(m['to'])}: {_card(m)} ({_frac(m['fraction'])}, {_state(m)})</li>" for m in ch["left"]]
    moved = [f"<li>{short_date(x['date']) if x['date'] else 'ohne Datum'}: {_card(x['member'])}, "
             f"{_frac(x['from'])} → {_frac(x['to'])}</li>" for x in ch["moved"]]  # fmt: skip
    return (
        "<h3>Nachgerückt und ausgeschieden</h3>"
        '<p class="explain">Mandate, die nach der konstituierenden Sitzung beginnen (Nachrücker über die '
        "Landesliste), und Mandate, die vor dem Ende der Wahlperiode aufhören. „Nach dem Ausscheiden von“ steht nur, "
        "wenn genau ein Mitglied derselben Fraktion und desselben Landes vorher ausschied.</p>"
        f"<h4>Nachgerückt</h4>{lst(joined)}<h4>Ausgeschieden</h4>{lst(left)}"
        "<h3>Fraktionswechsel</h3>"
        '<p class="explain">Wer in der 21. Wahlperiode die Fraktion gewechselt oder verlassen hat, laut Stammdaten.</p>'
        f"{lst(moved)}"
    )


def roles(cards: list[dict], bodies: list[dict], government: list[dict], ms: list[dict], ch: dict,
          stamm: dict | None = None) -> dict:  # fmt: skip
    """Who holds which role now, as data: the Präsidium (the Gremium of that name), the fraction chairs (a current
    fraction role "Vorsitzende/r"), the chairs of every other Gremium, the members in the government (current
    offices, data.government), and the tenure and changes from the Stammdaten."""
    by_id = {c["id"]: c for c in cards if c["kind"] == "member"}
    presidium, chairs = [], []
    for b in bodies:
        for m in b["members"]:
            if m["to"] is not None or m["person"] not in by_id:
                continue
            if b["name"] == PRESIDIUM:
                presidium.append({"body": b, "card": by_id[m["person"]], "role": m["role"]})
            elif CHAIR.match(m["role"] or ""):
                chairs.append({"body": b, "card": by_id[m["person"]], "role": m["role"]})
    presidium.sort(key=lambda x: ("Vize" in (x["role"] or ""), x["card"]["last_name"]))
    chairs.sort(key=lambda x: x["body"]["short"])
    fraction_chairs = sorted(
        ({"fraction": c["fraction"], "card": c, "role": r["role"]}
         for c in by_id.values() for r in c["fraction_roles"] if r["to"] is None and FRACTION_CHAIR.match(r["role"])),
        key=lambda x: (fraction_order(x["fraction"] or NO_FRACTION), x["card"]["last_name"]),
    )  # fmt: skip
    in_government = [g for g in government if g["id"] in by_id]
    return {"presidium": presidium, "fraction_chairs": fraction_chairs, "chairs": chairs,
            "government": in_government, "tenure": tenure(ms), "changes": ch, "stamm": stamm}  # fmt: skip


def section(r: dict, government_page: bool) -> str:
    """The Rollen section of the Abgeordnete page (root ""), anchored as #rollen; every name links the card, every
    role the page of the entity it belongs to."""

    def who(c: dict) -> str:
        f = c["fraction"] or NO_FRACTION
        return f'{_card(c)} {dot(f)}<span class="faint">{e(SHORT.get(f, f))}</span>'

    none = '<p class="explain">Keine in den Stammdaten.</p>'
    pres = "".join(f"<li>{e(x['role'] or 'Mitglied')}: {who(x['card'])}</li>" for x in r["presidium"])
    slug = r["presidium"][0]["body"]["slug"] if r["presidium"] else None
    pres_link = f'<p><a href="gremien/{e(slug)}.html">Zum Präsidium →</a></p>' if slug else ""
    fch = "".join(
        f'<li><a href="fraktionen/{TOKEN.get(x["fraction"], "frl")}.html">{e(SHORT.get(x["fraction"], x["fraction"]))}'
        f"</a>: {who(x['card'])}</li>"
        for x in r["fraction_chairs"] if x["fraction"] in TOKEN
    )  # fmt: skip
    chairs = "".join(f'<li><a href="gremien/{e(x["body"]["slug"])}.html">{e(x["body"]["short"])}</a>: {who(x["card"])}'
                     "</li>" for x in r["chairs"])  # fmt: skip
    gov = "".join(f"<li>{e(g['office'])}: {who(g['card'])}</li>" for g in r["government"] if g.get("card"))
    gov_more = (
        " Alle Ämter mit Daten und Quellen stehen auf der Seite der "
        '<a href="gremien/bundesregierung.html">Bundesregierung</a>.'
        if government_page
        else ""
    )
    stamm = r.get("stamm")
    src = f' Quelle: <a href="{e(stamm["url"])}">{e(stamm["doc"])}</a>.' if stamm else ""
    return (
        '<section class="facet roles" id="rollen"><h2>Rollen</h2>'
        '<p class="explain">Wer im Bundestag welche Rolle hat: Präsidium, Fraktionsvorsitz, Vorsitz der Ausschüsse '
        "und Gremien, Ämter in der Bundesregierung, und wie lange die Mitglieder schon dabei sind. Jede Rolle führt "
        f"zur Seite ihres Gremiums, ihrer Fraktion oder der Bundesregierung, jeder Name zur Karte.{src}</p>"
        f"<h3>Präsidium</h3>{f'<ul>{pres}</ul>' if pres else none}{pres_link}"
        f"<h3>Fraktionsvorsitz</h3>{f'<ul>{fch}</ul>' if fch else none}"
        f"<h3>Vorsitz der Ausschüsse und Gremien</h3>{f'<ul>{chairs}</ul>' if chairs else none}"
        f"<h3>In der Bundesregierung</h3>"
        f'<p class="explain">Mitglieder des Bundestages mit einem Regierungsamt heute.{gov_more}</p>'
        f"{f'<ul>{gov}</ul>' if gov else none}"
        f"{_tenure_section(r['tenure'])}{_changes_section(r['changes'])}</section>"
    )


STYLE = """<style>
.roles ul { padding-left: 20px; margin: 6px 0 4px; }
.roles li { margin: 3px 0; }
.roles li .dot { margin: 0 4px 0 6px; width: 7px; height: 7px; }
.roles h3 { font-size: 15px; margin: 22px 0 6px; }
.roles h4 { font-size: 13px; font-weight: 600; color: var(--muted); margin: 12px 0 4px; }
.roles table.plenum td.l, .roles table.plenum th.l { text-align: left; }
.roles table.plenum tfoot td { font-weight: 600; }
.roles .rows { overflow-x: auto; }
</style>"""


def build_section(conn: sqlite3.Connection, cards: list[dict], bodies: list[dict], government: list[dict]) -> str:
    """The Rollen section for the Abgeordnete page, with its style."""
    by_id = {c["id"]: c for c in cards}
    gov = [{**g, "card": by_id.get(g["id"])} for g in government]
    ms = members(conn)
    stamm = {"url": ms[0]["url"], "doc": ms[0]["doc"]} if ms else None
    r = roles(cards, bodies, gov, ms, changes(ms, constituted(conn)), stamm)
    return STYLE + section(r, bool(government))


def write(out: Path) -> dict[str, int]:
    """karrieren/index.html is the Rollen section of the Abgeordnete page now: a stub to index.html#rollen."""
    redirects.write(out, "karrieren/index.html", "index.html#rollen", "Rollen", redirects.any_fragment("rollen"))
    return {"karrieren": 1}
