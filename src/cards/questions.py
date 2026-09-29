"""Fragen an die Regierung: `regierung/index.html`, from DIP (Kleine Anfragen, Schriftliche and Mündliche Fragen)
and the protocols (Regierungsbefragung). Numbers per fraction, no member ranking (docs/plan.md)."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from cards.data import NO_FRACTION, PARTY_TO_FRACTION, WP, drucksache_pdf, has_table
from cards.pages import FOOTER, MONTHS, SHORT, TOKEN, agenda_href, dot, e, fraction_order, n, shell, short_date

DEADLINE = 14  # § 104 Abs. 2 GO-BT: the government is asked to answer within 14 days, extendable
_ASKED = re.compile(r"Drucksache\s+(\d+)\s*/\s*(\d+)")
STYLE = """<style>
.qs table.plenum td.l { text-align: left; white-space: normal; }
.qs .open { font-size: 13px; margin: 6px 0 14px; }
.qs .open summary { cursor: pointer; color: var(--muted); }
.qs .open ol { padding-left: 20px; margin: 8px 0; }
.qs .open li { margin: 3px 0; }
.qs .month td .mb { display: inline-block; height: 8px; border-radius: 2px; vertical-align: 0; }
.qs .rows { overflow-x: auto; }
</style>"""


def fraction_of_originator(o: str) -> str:
    """DIP's Urheber "Fraktion der AfD", "Fraktion DIE LINKE" -> the fraction names used on the site."""
    s = re.sub(r"^Fraktion (der )?", "", o.strip())
    return {"DIE LINKE": "Die Linke", "DIE LINKE.": "Die Linke"}.get(s, s)


def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b[:10]) - dt.date.fromisoformat(a[:10])).days


def kleine_anfragen(conn: sqlite3.Connection) -> dict:
    """Every Kleine Anfrage of the Wahlperiode with its answer: first by the DIP Vorgang both belong to, else by
    the "Drucksache 21/54" the answer's title names. Days are calendar days between the two Drucksache dates."""
    asked = conn.execute(
        "SELECT id, number, date, title, originators, pdf_url FROM drucksache "
        "WHERE wahlperiode = ? AND type = 'Kleine Anfrage' ORDER BY date, id",
        (WP,),
    ).fetchall()
    answers = conn.execute(
        "SELECT id, number, date, title, pdf_url FROM drucksache WHERE wahlperiode = ? AND type = 'Antwort'", (WP,)
    ).fetchall()
    by_vorgang: dict[str, list[sqlite3.Row]] = defaultdict(list)
    vorgang_of: dict[str, list[str]] = defaultdict(list)
    for vid, did in conn.execute("SELECT vorgang_id, drucksache_id FROM vorgang_drucksache"):
        vorgang_of[did].append(vid)
    for a in answers:
        for vid in vorgang_of.get(a["id"], []):
            by_vorgang[vid].append(a)
    by_number: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for a in answers:
        m = _ASKED.search(a["title"] or "")
        if m:
            by_number[f"{m[1]}/{int(m[2])}"].append(a)
    newest = conn.execute("SELECT max(date) FROM drucksache WHERE wahlperiode = ?", (WP,)).fetchone()[0]
    rows = []
    for q in asked:
        found = [a for vid in vorgang_of.get(q["id"], []) for a in by_vorgang[vid]] or by_number.get(q["number"], [])
        answer = min(found, key=lambda a: (a["date"], a["id"])) if found else None
        rows.append({
            "number": q["number"], "date": q["date"], "title": q["title"],
            "url": q["pdf_url"] or drucksache_pdf(q["number"]),
            "fractions": [fraction_of_originator(o) for o in json.loads(q["originators"] or "[]")] or ["unbekannt"],
            "answer": None if answer is None else {
                "number": answer["number"], "date": answer["date"],
                "url": answer["pdf_url"] or drucksache_pdf(answer["number"]),
                "days": _days(q["date"], answer["date"]),
            },
        })  # fmt: skip
    return {"rows": rows, "as_of": newest}


def ka_summary(ka: dict) -> list[dict]:
    """Per fraction: asked, answered, median days, share within DEADLINE days, the open ones oldest first."""
    per: dict[str, list[dict]] = defaultdict(list)
    for r in ka["rows"]:
        for f in r["fractions"]:
            per[f].append(r)
    out = []
    for f in sorted(per, key=fraction_order):
        rs = per[f]
        days = [r["answer"]["days"] for r in rs if r["answer"]]
        still = [{**r, "age": _days(r["date"], ka["as_of"])} for r in rs if not r["answer"]]
        out.append({
            "fraction": f, "asked": len(rs), "answered": len(days),
            "median": statistics.median(days) if days else None,
            "in_time": sum(d <= DEADLINE for d in days) / len(days) if days else None,
            "open": sorted(still, key=lambda r: (r["date"], r["number"])),
        })  # fmt: skip
    return out


def months(dates_by_fraction: dict[str, list[str]]) -> tuple[list[str], dict[str, Counter]]:
    """All months from the first to the last date ("2025-04"), and the count per month per fraction."""
    counts = {f: Counter(d[:7] for d in ds) for f, ds in dates_by_fraction.items()}
    have = sorted({m for c in counts.values() for m in c})
    if not have:
        return [], counts
    y, m = map(int, have[0].split("-"))
    span = []
    while f"{y}-{m:02d}" <= have[-1]:
        span.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return span, counts


def _fraction_at(conn: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    per: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute(
        "SELECT person_id, name, from_date, to_date FROM membership WHERE kind = 'fraction' AND wahlperiode = ?",
        (WP,),
    ):
        per[r["person_id"]].append(r)
    return per


def written_questions(conn: sqlite3.Connection) -> dict:
    """Schriftliche and Mündliche Fragen. DIP has one Vorgang per question, dated here by the Sammeldrucksache it
    is printed in; askers are named per Sammeldrucksache only, so the fractions count (Drucksache, person) pairs."""
    out: dict = {}
    fractions = _fraction_at(conn)
    parties = {r["id"]: r["party"] for r in conn.execute("SELECT id, party FROM person")}
    for kind, dtype in (("Schriftliche Frage", "Schriftliche Fragen"), ("Mündliche Frage", "Fragen")):
        dates = conn.execute(
            """SELECT v.id, min(d.date) FROM vorgang v
               LEFT JOIN vorgang_drucksache vd ON vd.vorgang_id = v.id
               LEFT JOIN drucksache d ON d.id = vd.drucksache_id AND d.type = ?
               WHERE v.wahlperiode = ? AND v.type = ? GROUP BY v.id""",
            (dtype, WP, kind),
        ).fetchall()
        docs = conn.execute(
            "SELECT id, number, date, author_count FROM drucksache WHERE wahlperiode = ? AND type = ? ORDER BY date",
            (WP, dtype),
        ).fetchall()
        askers: Counter = Counter()
        for r in conn.execute(
            """SELECT a.person_id, d.date FROM drucksache_author a JOIN drucksache d ON d.id = a.drucksache_id
               WHERE d.wahlperiode = ? AND d.type = ? AND a.activity_type = 'Frage'
               GROUP BY a.drucksache_id, coalesce(a.person_id, a.dip_person_id)""",
            (WP, dtype),
        ):
            f = None
            for m in fractions.get(r["person_id"] or "", []):
                if m["from_date"] <= r["date"] and (m["to_date"] is None or m["to_date"] >= r["date"]):
                    f = m["name"]
            if f is None and r["person_id"] in parties:
                p = parties[r["person_id"]]
                f = PARTY_TO_FRACTION.get(p, p) if p else NO_FRACTION
            askers[f or "unbekannt"] += 1
        out[kind] = {
            "total": len(dates),
            "months": Counter(d[1][:7] for d in dates if d[1]),
            "undated": sum(1 for d in dates if not d[1]),
            "docs": len(docs), "docs_with_authors": sum(1 for d in docs if d["author_count"]),
            "askers": askers,
        }  # fmt: skip
    return out


def befragungen(conn: sqlite3.Connection) -> list[dict]:
    """Regierungsbefragungen: the government members who answered and the questions per fraction. Every question
    and follow-up is its own turn in the protocol; a turn with a fraction and no role counts as one question."""
    items = conn.execute(
        """SELECT a.id, a.sitting_id, a.position, s.date FROM agenda_item a JOIN sitting s ON s.id = a.sitting_id
           WHERE s.wahlperiode = ? AND a.title LIKE 'Befragung der Bundesregierung%' ORDER BY s.date, a.position""",
        (WP,),
    ).fetchall()
    out = []
    for it in items:
        gov: dict[str, dict] = {}
        asked: Counter = Counter()
        for s in conn.execute(
            "SELECT person_id, speaker_name, speaker_role, fraction FROM speech WHERE agenda_item_id = ? "
            "ORDER BY position",
            (it["id"],),
        ):
            if s["speaker_role"]:
                name = s["speaker_name"].split(",")[0].strip()
                gov.setdefault(s["person_id"], {"id": s["person_id"], "name": name, "role": s["speaker_role"]})
            elif s["fraction"]:
                asked[s["fraction"]] += 1
        out.append({"sitting": it["sitting_id"], "position": it["position"], "date": it["date"],
                    "government": list(gov.values()), "questions": asked})  # fmt: skip
    return out


def fragestunden(conn: sqlite3.Connection) -> tuple[int, int]:
    """Agenda items "Fragestunde" in the Wahlperiode, and how many speeches the store has for them."""
    r = conn.execute(
        """SELECT count(DISTINCT a.id), count(sp.id) FROM agenda_item a JOIN sitting s ON s.id = a.sitting_id
           LEFT JOIN speech sp ON sp.agenda_item_id = a.id WHERE s.wahlperiode = ? AND a.title LIKE 'Fragestunde%'""",
        (WP,),
    ).fetchone()
    return r[0], r[1]


# ---------------------------------------------------------------- the page


def _month_label(m: str) -> str:
    return f"{MONTHS[int(m[5:]) - 1][:3]} {m[:4]}"


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{round(100 * x)} %"


def _median(x: float | None) -> str:
    return "–" if x is None else f"{x:g}".replace(".", ",")


def _ka_section(ka: dict) -> str:
    summary = ka_summary(ka)
    if not summary:
        return '<h2>Kleine Anfragen</h2><p class="explain">Keine Kleinen Anfragen im Datenbestand.</p>'
    body = "".join(
        f"<tr><td>{dot(s['fraction'])} {e(s['fraction'])}</td><td>{n(s['asked'])}</td><td>{n(s['answered'])}</td>"
        f"<td>{n(len(s['open']))}</td><td>{_median(s['median'])}</td><td>{_pct(s['in_time'])}</td></tr>"
        for s in summary
    )
    table = (
        '<div class="rows"><table class="plenum"><thead><tr><th>Fraktion</th><th>gestellt</th><th>beantwortet</th>'
        f"<th>offen</th><th>Median Tage</th><th>in {DEADLINE} Tagen</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )
    opens = "".join(
        f'<details class="open"><summary>{dot(s["fraction"])} {e(s["fraction"])}: {n(len(s["open"]))} offene '
        "Anfragen, älteste zuerst</summary><ol>"
        + "".join(
            f'<li><a href="{e(r["url"])}">BT-Drs. {e(r["number"])}</a> vom {short_date(r["date"])}, '
            f"{n(r['age'])} Tage: {e(r['title'])}</li>"
            for r in s["open"]
        )
        + "</ol></details>"
        for s in summary
        if s["open"]
    )
    span, counts = months({s["fraction"]: [r["date"] for r in ka["rows"] if s["fraction"] in r["fractions"]]
                           for s in summary})  # fmt: skip
    fr = [s["fraction"] for s in summary]
    peak = max((c for f in fr for c in counts[f].values()), default=1) or 1
    month_rows = "".join(
        f"<tr><td>{_month_label(m)}</td>"
        + "".join(
            f'<td title="{e(f)}: {counts[f][m]}">{counts[f][m] or ""} <span class="mb" style="width:'
            f'{40 * counts[f][m] / peak:.0f}px;background:var(--{TOKEN.get(f, "reg")})"></span></td>'
            for f in fr
        )
        + "</tr>"
        for m in span
    )
    month_table = (
        '<h3>Gestellte Kleine Anfragen je Monat</h3><div class="rows month"><table class="plenum"><thead><tr>'
        "<th>Monat</th>" + "".join(f"<th>{dot(f)} {e(SHORT.get(f, f))}</th>" for f in fr) + "</tr></thead><tbody>"
        + month_rows + "</tbody></table></div>"
    )  # fmt: skip
    return (
        "<h2>Kleine Anfragen</h2>"
        '<p class="explain">Eine Kleine Anfrage stellt eine Fraktion (oder fünf Prozent der Abgeordneten) schriftlich '
        f"an die Bundesregierung. Nach § 104 Abs. 2 der Geschäftsordnung des Bundestages wird die Bundesregierung "
        f"aufgefordert, innerhalb von {DEADLINE} Tagen zu antworten; im Benehmen mit den Fragestellern kann die Frist "
        "verlängert werden. Gezählt werden Kalendertage "
        "zwischen dem Datum der Anfrage-Drucksache und dem der Antwort-Drucksache (Quelle: DIP). Offen heißt: im "
        f"Datenbestand noch keine Antwort, Stand {short_date(ka['as_of'])}. Fraktionen ohne Kleine Anfrage "
        "fehlen in der Tabelle.</p>"
        f"{table}{opens}{month_table}"
    )


def _questions_section(wq: dict) -> str:
    parts = ["<h2>Schriftliche und Mündliche Fragen</h2>"]
    parts.append(
        '<p class="explain">Jede und jeder Abgeordnete kann einzelne Fragen an die Bundesregierung richten: '
        "schriftlich (die Antworten erscheinen wöchentlich gesammelt als Drucksache) oder mündlich für die "
        "Fragestunde. DIP führt jede Frage als eigenen Vorgang; der Monat ist der der Sammeldrucksache.</p>"
    )
    for kind, label in (("Schriftliche Frage", "Schriftliche Fragen"), ("Mündliche Frage", "Mündliche Fragen")):
        w = wq.get(kind)
        if not w or not w["total"]:
            continue
        span, c = months({"all": [f"{m}-01" for m, k in w["months"].items() for _ in range(k)]})
        rows = "".join(f"<tr><td>{_month_label(m)}</td><td>{n(c['all'][m])}</td></tr>" for m in span)
        undated = f", {n(w['undated'])} ohne Sammeldrucksache" if w["undated"] else ""
        parts.append(
            f"<h3>{label}: {n(w['total'])}{undated}</h3>"
            '<details class="open"><summary>je Monat</summary><div class="rows"><table class="plenum"><thead><tr>'
            f"<th>Monat</th><th>Fragen</th></tr></thead><tbody>{rows}</tbody></table></div></details>"
        )
        if w["askers"] and w["docs_with_authors"] >= 0.9 * w["docs"]:
            total = sum(w["askers"].values())
            body = "".join(
                f"<tr><td>{dot(f)} {e(f)}</td><td>{n(k)}</td><td>{_pct(k / total)}</td></tr>"
                for f, k in sorted(w["askers"].items(), key=lambda x: fraction_order(x[0]))
            )
            parts.append(
                '<div class="rows"><table class="plenum"><thead><tr><th>Fraktion</th><th>Nennungen</th><th>Anteil</th>'
                f"</tr></thead><tbody>{body}</tbody></table></div>"
                '<p class="explain">DIP nennt die Fragesteller:innen je Sammeldrucksache, nicht je Frage. Eine Nennung '
                "heißt: mindestens eine Frage in dieser Drucksache. Die Zahl der Nennungen ist deshalb kleiner als die "
                f"der Fragen. Fragesteller:innen genannt in {w['docs_with_authors']} von {w['docs']} "
                "Sammeldrucksachen.</p>"
            )
        else:
            parts.append(
                f'<p class="explain">Nach Fraktionen nicht auswertbar: DIP nennt nur für {w["docs_with_authors"]} von '
                f"{w['docs']} Sammeldrucksachen Fragesteller:innen.</p>"
            )
    return "".join(parts)


def _befragung_section(bf: list[dict], fs: tuple[int, int]) -> str:
    gap = ""
    if fs[0] and not fs[1]:
        gap = (
            f'<p class="explain"><b>Lücke:</b> Die {n(fs[0])} Fragestunden der Wahlperiode stehen in der '
            "Tagesordnung, aber der Datenbestand hat keine Beiträge dazu. Die Fragen selbst stehen "
            "in den Drucksachen „Fragen für die Fragestunde“ (oben).</p>"
        )
    elif fs[0]:
        gap = (
            f'<p class="explain">Die {n(fs[0])} Fragestunden der Wahlperiode haben {n(fs[1])} Fragen, Antworten und '
            "Nachfragen im Protokoll. Sie stehen auf den Karten der Beteiligten und zählen nicht als Reden.</p>"
        )
    if not bf:
        return "<h2>Regierungsbefragung</h2>" + gap
    total: Counter = Counter()
    for b in bf:
        total.update(b["questions"])
    fr = sorted(total, key=fraction_order)
    rows = "".join(
        f'<tr><td class="l"><a href="{e(agenda_href(b["sitting"], b["position"]))}">{short_date(b["date"])}</a></td>'
        f'<td class="l">'
        + "; ".join(
            (f'<a href="../{e(g["id"])}.html">{e(g["name"])}</a>' if g["id"] else e(g["name"])) + f", {e(g['role'])}"
            for g in b["government"]
        )
        + "</td>"
        + "".join(f"<td>{b['questions'][f] or ''}</td>" for f in fr)
        + "</tr>"
        for b in reversed(bf)
    )
    sums = "".join(f"<td><b>{n(total[f])}</b></td>" for f in fr)
    return (
        "<h2>Regierungsbefragung</h2>"
        '<p class="explain">In der Regierungsbefragung stellen sich Mitglieder der Bundesregierung den Fragen der '
        "Abgeordneten. Gezählt sind Wortmeldungen mit Fraktion, also Fragen und Nachfragen; das Datum führt zum "
        "Tagesordnungspunkt im Protokoll.</p>"
        '<div class="rows"><table class="plenum"><thead><tr><th>Datum</th><th>Befragt</th>'
        + "".join(f"<th>{dot(f)} {e(SHORT.get(f, f))}</th>" for f in fr)
        + f'</tr></thead><tbody><tr><td class="l">zusammen</td><td></td>{sums}</tr>{rows}</tbody></table></div>'
        + gap
    )


def page(ka: dict, wq: dict, bf: list[dict], fs: tuple[int, int]) -> str:
    body = (
        '<section class="card"><h1>Fragen an die Regierung</h1><div class="lines">Kleine Anfragen, Schriftliche '
        "und Mündliche Fragen und die Regierungsbefragung im 21. Bundestag, nach Fraktionen. Jede Zahl führt zu "
        'ihrer Drucksache oder zum Plenarprotokoll. <a href="../daten.html">Über die Daten</a></div></section>'
        f'<div class="qs">{_ka_section(ka)}{_questions_section(wq)}{_befragung_section(bf, fs)}</div>'
        f"<footer>{FOOTER}</footer>"
    )
    return shell(root="../", kind="p-questions", active="questions", title="Fragen an die Regierung",
                 desc="Wie oft die Fraktionen des 21. Bundestages die Bundesregierung fragen und wie schnell sie "
                      "antwortet: Kleine Anfragen, Schriftliche und Mündliche Fragen, Regierungsbefragung.",
                 body=body, data={"kind": "questions"}, head=STYLE)  # fmt: skip


def write(conn: sqlite3.Connection, out: Path) -> dict[str, int]:
    """Write regierung/index.html; returns {"regierung": 1}, or {} when the store has no DIP tables."""
    if not has_table(conn, "drucksache"):
        return {}
    d = out / "regierung"
    d.mkdir(parents=True, exist_ok=True)
    html = page(kleine_anfragen(conn), written_questions(conn), befragungen(conn), fragestunden(conn))
    (d / "index.html").write_text(html, encoding="utf-8")
    return {"regierung": 1}
