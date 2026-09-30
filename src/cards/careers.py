"""Karrieren: `karrieren/index.html`, from the Stammdaten's mandate history (every Wahlperiode since 1949) and the
WP 21 fraction memberships: how many Wahlperioden the current members have served, per fraction; who left the
Bundestag and who moved up; fraction changes; government offices held by members. Counts per fraction and lists
by date, no member ranking (docs/plan.md). Also the first speech in WP 21 for each card (`annotate`)."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from cards import urls
from cards.data import NO_FRACTION, PARTY_TO_FRACTION, WP, display_name, feminine, government_roles
from cards.ui import FOOTER, SHORT, dot, e, fraction_order, n, shell, short_date

BUCKETS = ("1", "2", "3", "4", "5 und mehr")
KINDS = {"kanzler": "Bundeskanzler", "minister": "Bundesminister", "staatsminister": "Staatsminister",
         "parl_sts": "Parlamentarische Staatssekretäre", "beamteter_sts": "Beamtete Staatssekretäre"}  # fmt: skip
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


# ---------------------------------------------------------------- page


def _card(m: dict) -> str:
    return f'<a href="../{e(m["id"])}.html">{e(m["name"])}</a>'


def _frac(f: str) -> str:
    return f"{dot(f)} {e(SHORT.get(f, f))}"


def _state(m: dict) -> str:
    return e(STATES.get(m["state"], m["state"]))


def _when(o: dict) -> str:
    if o["evidence"]:  # protocol rows date the sittings that print the office, not the term
        return f"in Plenarprotokollen vom {short_date(o['from'])} bis {short_date(o['to'] or o['from'])}"
    return f"seit {short_date(o['from'])}" if not o["to"] else f"{short_date(o['from'])}–{short_date(o['to'])}"


def _pct(x: float) -> str:
    return f"{100 * x:.0f} %"


def _tenure_section(rows: list[dict]) -> str:
    if not rows:
        return '<h2>Wahlperioden im Bundestag</h2><p class="explain">Keine Mandate im Datenbestand.</p>'
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
        "<h2>Wahlperioden im Bundestag</h2>"
        '<p class="explain">Wie viele Wahlperioden die heutigen Mitglieder im Bundestag waren, die 21. mitgezählt, '
        "nach Fraktion. Grundlage sind alle Mandate seit 1949 in den Stammdaten; Pausen zählen nicht mit. "
        "„Erstmals“ heißt: nur in der 21. Wahlperiode.</p>"
        '<div class="rows"><table class="plenum"><thead><tr><th class="l">Fraktion</th>'
        + "".join(f"<th>{b}</th>" for b in BUCKETS)
        + f"<th>Mitglieder</th><th>erstmals</th></tr></thead><tbody>{body}</tbody><tfoot>{foot}</tfoot></table></div>"
    )


def _changes_section(ch: dict) -> str:
    left = "".join(
        f"<li>{short_date(m['to'])}: {_card(m)} ({_frac(m['fraction'])}, {_state(m)})</li>" for m in ch["left"]
    )
    joined = "".join(
        f"<li>{short_date(m['from'])}: {_card(m)} ({_frac(m['fraction'])}, {_state(m)})"
        + (f", nach dem Ausscheiden von {_card(m['after'])}" if m.get("after") else "")
        + "</li>"
        for m in ch["joined"]
    )
    moved = "".join(
        f"<li>{short_date(x['date']) if x['date'] else 'ohne Datum'}: {_card(x['member'])}, "
        f"{_frac(x['from'])} → {_frac(x['to'])}</li>"
        for x in ch["moved"]
    )
    none = '<p class="explain">Keine in den Stammdaten.</p>'
    return (
        "<h2>Ausgeschieden und nachgerückt</h2>"
        '<p class="explain">Mandate der 21. Wahlperiode, die vor ihrem Ende aufhören, und Mandate, die nach der '
        "konstituierenden Sitzung beginnen (Nachrücker über die Landesliste). Die Zuordnung „nach dem Ausscheiden "
        "von“ steht nur, wenn genau ein Mitglied derselben Fraktion und desselben Landes vorher ausschied.</p>"
        f"<h3>Ausgeschieden</h3>{f'<ul>{left}</ul>' if left else none}"
        f"<h3>Nachgerückt</h3>{f'<ul>{joined}</ul>' if joined else none}"
        "<h2>Fraktionswechsel</h2>"
        '<p class="explain">Mitglieder, die in der 21. Wahlperiode die Fraktion gewechselt oder verlassen haben, laut '
        "Stammdaten.</p>"
        f"{f'<ul>{moved}</ul>' if moved else none}"
    )


def _offices_section(held: list[dict]) -> str:
    if not held:
        return '<h2>Regierungsämter</h2><p class="explain">Keine Regierungsämter von Mitgliedern im Datenbestand.</p>'
    by: dict[str, list[dict]] = defaultdict(list)
    for o in held:
        by[o["kind"]].append(o)
    parts = []
    for kind, label in KINDS.items():
        if not by[kind]:
            continue
        items = "".join(
            f"<li>{_card(o['member'])} ({_frac(o['member']['fraction'])}): {e(o['office'])}, "
            f"{_when(o)} "
            f'<a class="faint" href="{e(o["sources"][0]["url"])}">Quelle</a></li>'
            for o in by[kind]
        )
        parts.append(f"<h3>{e(label)} ({n(len(by[kind]))})</h3><ul>{items}</ul>")
    return (
        "<h2>Regierungsämter</h2>"
        '<p class="explain">Ämter in der Bundesregierung, die Mitglieder des 21. Bundestages innehaben oder in dieser '
        "Wahlperiode innehatten, nach Beginn. Quellen: Wikidata, Stammdaten, Plenarprotokolle.</p>" + "".join(parts)
    )


def page(ms: list[dict], ch: dict, held: list[dict]) -> str:
    stamm = ms[0] if ms else None
    src = f' Quelle: <a href="{e(stamm["url"])}">{e(stamm["doc"])}</a>.' if stamm else ""
    body = (
        '<section class="card"><h1>Karrieren</h1><div class="lines">Wie lange die Mitglieder des 21. Bundestages '
        "schon im Parlament sind, wer ausgeschieden und nachgerückt ist, wer die Fraktion gewechselt hat und wer ein "
        f"Regierungsamt hat. Jeder Name führt zur Karte.{src} "
        '<a href="../daten.html">Über die Daten</a></div></section>'
        f'<div class="qs">{_tenure_section(tenure(ms))}{_changes_section(ch)}{_offices_section(held)}</div>'
        f"<footer>{FOOTER}</footer>"
    )
    return shell(root="../", kind="p-careers", active="careers", title="Karrieren",
                 desc="Wahlperioden, Nachrücker, Fraktionswechsel und Regierungsämter der Mitglieder des "
                      "21. Deutschen Bundestages.",
                 body=body, data={"kind": "careers"}, head=STYLE)  # fmt: skip


STYLE = """<style>
.qs table.plenum td.l, .qs table.plenum th.l { text-align: left; }
.qs table.plenum tfoot td { font-weight: 600; }
.qs .rows { overflow-x: auto; }
.qs ul { padding-left: 20px; }
.qs li { margin: 4px 0; }
</style>"""


def write(conn: sqlite3.Connection, out: Path) -> dict[str, int]:
    """Write karrieren/index.html; returns {"karrieren": 1}."""
    ms = members(conn)
    d = out / "karrieren"
    d.mkdir(parents=True, exist_ok=True)
    html = page(ms, changes(ms, constituted(conn)), offices(conn, ms))
    (d / "index.html").write_text(html, encoding="utf-8")
    return {"karrieren": 1}
