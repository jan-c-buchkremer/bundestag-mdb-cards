"""Fragen an die Regierung: `regierung/index.html`, from DIP (Kleine Anfragen, Schriftliche and Mündliche Fragen)
and the protocols (Fragestunde, Regierungsbefragung). Numbers per fraction, no member ranking (docs/plan.md).

Below the statistics, the research view (docs/plan.md 12.5, D30): every single question, one list per kind, loaded
by the browser only when its tab is opened, from `regierung/<kind>.json` (`research`): filterable by words in the
title, Fraktion, member, ministry, month, status and, for Kleine Anfragen, the answer time. Each row links its
source: the Drucksache in DIP and as PDF, the Vorgang in DIP, the asker's card, and for oral questions the protocol
and the speech page. The store holds titles only, not the text of a question (a foundation requirement, plan 12.5);
the page says so.

Who asked a Schriftliche or Mündliche Frage: DIP names the askers per Sammeldrucksache (`drucksache_author`,
activity "Frage"), not per question, so a question's asker is known here only when its Sammeldrucksache names
exactly one (a foundation requirement: the asker per question from DIP's Aktivität with its Vorgangsbezug). Who
answered is the next best thing, and it is known: a question has its ministry (`vorgang_position.ressort`), and the
answerers name theirs, in the Sammeldrucksache's "Antwort" activities ("Daniela Ludwig, Parl. Staatssekr.,
Bundesministerium des Innern") and, for a Mündliche Frage, in the speaker role of the government member answering
in the Fragestunde ("Parl. Staatssekretärin beim Bundesminister des Innern"). The row names the answerers of its
ministry there (usually one, sometimes the two Parlamentarische Staatssekretäre of a ministry), linked to their
cards and, in the Fragestunde, to the speech page with the answer (`ministry_key`)."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from research import urls
from research.data import NO_FRACTION, PARTY_TO_FRACTION, WP, drucksache_pdf, excerpt, has_table, kind_filter
from research.ui import FOOTER, MONTHS, SHORT, TOKEN, dot, e, fraction_order, n, shell, short_date

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


# ---------------------------------------------------------------- the research view: one JSON per kind

_MINISTER = re.compile(r"bundesminister(?:ium|in)?\s+(.+)$")
_MINISTRY_ALIASES = {"auswärtiges amt": "des auswärtigen"}


def ministry_key(text: str | None) -> str | None:
    """The ministry a DIP Ressort, an answerer's activity or a speaker role names, as one key: "Bundesministerium
    des Innern", "…, Parl. Staatssekr., Bundesministerium des Innern" and "Parl. Staatssekretärin beim Bundesminister
    des Innern" all give "des innern"."""
    if not text:
        return None
    t = text.split(",")[-1].strip().lower()
    m = _MINISTER.search(t)
    key = m.group(1).strip() if m else t
    return _MINISTRY_ALIASES.get(key, key)


KINDS = (  # slug, tab label, what one row is
    ("kleine-anfragen", "Kleine Anfragen", "Kleine Anfrage"),
    ("schriftliche-fragen", "Schriftliche Fragen", "Schriftliche Frage"),
    ("muendliche-fragen", "Mündliche Fragen", "Mündliche Frage"),
    ("fragestunde", "Fragestunde", "Beitrag in der Fragestunde"),
    ("regierungsbefragung", "Regierungsbefragung", "Beitrag in der Regierungsbefragung"),
)
EXCERPT = 120  # characters of a turn in the Fragestunde or the Befragung; the speech page has the whole text


class Packer:
    """Shared tables of one kind's JSON, so a row refers to a person, a ministry or a Drucksache by its index:
    {"persons": [[id, name, fraction, has card]], "ressorts": [title], "statuses": [DIP Beratungsstand],
    "docs": [[number, DIP id, date, PDF or null]], "rows": [...]}. A PDF is null when it is the Bundestag's standard
    address of the number (data.drucksache_pdf, rebuilt by the page script)."""

    def __init__(self, cards: set[str], names: dict[str, tuple[str, str | None]]) -> None:
        self.cards, self.names = cards, names
        self.persons: list[list] = []
        self.ressorts: list[str] = []
        self.statuses: list[str] = []
        self.docs: list[list] = []
        self._p: dict[str, int] = {}
        self._r: dict[str, int] = {}
        self._d: dict[str, int] = {}

    def person(self, pid: str | None, name: str | None = None, fraction: str | None = None) -> int | None:
        if not pid and not name:
            return None
        key = pid or f"name:{name}"
        if key not in self._p:
            known = self.names.get(pid or "", (name, fraction))
            self._p[key] = len(self.persons)
            self.persons.append([pid, known[0] or name, fraction or known[1], 1 if pid in self.cards else 0])
        return self._p[key]

    def ressort(self, title: str | None) -> int | None:
        if not title:
            return None
        if title not in self._r:
            self._r[title] = len(self.ressorts)
            self.ressorts.append(title)
        return self._r[title]

    def status(self, s: str | None) -> int | None:
        if not s:
            return None
        if s not in self.statuses:
            self.statuses.append(s)
        return self.statuses.index(s)

    def doc(self, number: str, dip_id: str, date: str, pdf: str | None) -> int:
        if number not in self._d:
            self._d[number] = len(self.docs)
            self.docs.append([number, dip_id, date, None if not pdf or pdf == drucksache_pdf(number) else pdf])
        return self._d[number]

    def payload(self, kind: str, fields: list[str], rows: list[list]) -> dict:
        return {"kind": kind, "fields": fields, "persons": self.persons, "ressorts": self.ressorts,
                "statuses": self.statuses, "docs": self.docs, "rows": rows}  # fmt: skip


def _ressorts(conn: sqlite3.Connection) -> dict[str, str]:
    """Vorgang id -> the lead ministry (`vorgang_position.ressort`, federführend first) over all its steps."""
    if not has_table(conn, "vorgang_position"):
        return {}
    out: dict[str, str] = {}
    for vid, raw in conn.execute("SELECT vorgang_id, ressort FROM vorgang_position WHERE ressort IS NOT NULL "
                                 "ORDER BY date, id"):  # fmt: skip
        try:
            rs = [r for r in json.loads(raw) if isinstance(r, dict) and r.get("titel")]
        except ValueError:
            continue
        lead = next((r for r in rs if r.get("federfuehrend")), rs[0] if rs else None)
        if lead and (vid not in out or lead.get("federfuehrend")):
            out[vid] = lead["titel"]
    return out


def _people(conn: sqlite3.Connection) -> dict[str, tuple[str, str | None]]:
    """Person id -> (display name, current fraction or party's fraction)."""
    from research.data import display_name

    fr = {r["person_id"]: r["name"] for r in conn.execute(
        "SELECT person_id, name FROM membership WHERE kind = 'fraction' AND wahlperiode = ? ORDER BY from_date",
        (WP,))}  # fmt: skip
    return {r["id"]: (display_name(r), fr.get(r["id"]) or (PARTY_TO_FRACTION.get(r["party"], r["party"])
                                                          if r["party"] else None))
            for r in conn.execute("SELECT * FROM person")}  # fmt: skip


def research_kleine_anfragen(conn: sqlite3.Connection, pk: Packer, ressorts: dict[str, str]) -> dict:
    """Rows [number index into docs, title, fractions, signers (person indices), ministry, answer [doc, days] or
    null]. The answer as `kleine_anfragen` pairs it."""
    ka = kleine_anfragen(conn)
    ids = {r["number"]: r for r in conn.execute(
        "SELECT id, number, pdf_url FROM drucksache WHERE wahlperiode = ? AND type IN ('Kleine Anfrage', 'Antwort')",
        (WP,))}  # fmt: skip
    signers: dict[str, list[str]] = defaultdict(list)
    for r in conn.execute(
        """SELECT d.number, a.person_id, a.name FROM drucksache_author a JOIN drucksache d ON d.id = a.drucksache_id
           WHERE d.wahlperiode = ? AND d.type = 'Kleine Anfrage' AND a.activity_type = 'Kleine Anfrage'
           ORDER BY a.rowid""",
        (WP,),
    ):
        signers[r["number"]].append((r["person_id"], r["name"]))
    vorgang_of = {did: vid for vid, did in conn.execute("SELECT vorgang_id, drucksache_id FROM vorgang_drucksache")}
    rows = []
    for q in ka["rows"]:
        src = ids.get(q["number"])
        doc = pk.doc(q["number"], src["id"] if src else "", q["date"], q["url"])
        who = [pk.person(pid, name.split(",")[0]) for pid, name in signers.get(q["number"], [])]
        a = q["answer"]
        answer = None
        if a:
            asrc = ids.get(a["number"])
            answer = [pk.doc(a["number"], asrc["id"] if asrc else "", a["date"], a["url"]), a["days"]]
        vid = vorgang_of.get(src["id"]) if src else None
        rows.append([doc, q["title"], q["fractions"], who, pk.ressort(ressorts.get(vid or "")), answer, vid])
    return pk.payload("kleine-anfragen", ["doc", "title", "fractions", "askers", "ressort", "answer", "vorgang"],
                      rows)  # fmt: skip


def research_written(conn: sqlite3.Connection, pk: Packer, ressorts: dict[str, str], kind: str) -> dict:
    """Schriftliche (kind "Schriftliche Frage") or Mündliche Fragen ("Mündliche Frage"), one row per DIP Vorgang:
    [vorgang id, date (null: the Sammeldrucksache's), title, status (index), ministry, Sammeldrucksache (doc index)
    or null, asker (person index) or null, answer in the plenum [sitting id or null, agenda position or null, pages,
    PDF, protocol number] or null (Mündliche Fragen), answered by [[person index, speech id or null]]]: the answerers
    of the question's ministry in its Sammeldrucksache, or in the Fragestunde of its sitting (`ministry_key`)."""
    dtype = "Schriftliche Fragen" if kind == "Schriftliche Frage" else "Fragen"
    collected: dict[str, sqlite3.Row] = {}
    for r in conn.execute(
        """SELECT vd.vorgang_id, d.id, d.number, d.date, d.pdf_url FROM vorgang_drucksache vd
           JOIN drucksache d ON d.id = vd.drucksache_id WHERE d.type = ? ORDER BY d.date""",
        (dtype,),
    ):
        collected.setdefault(r["vorgang_id"], r)
    askers: dict[str, list[tuple]] = defaultdict(list)
    for r in conn.execute(
        """SELECT a.drucksache_id, a.person_id, a.name FROM drucksache_author a JOIN drucksache d
           ON d.id = a.drucksache_id WHERE d.type = ? AND a.activity_type = 'Frage'""",
        (dtype,),
    ):
        askers[r["drucksache_id"]].append((r["person_id"], r["name"]))
    signed: dict[str, list[tuple]] = defaultdict(list)  # Sammeldrucksache -> its answerers, with their ministry
    for r in conn.execute(
        """SELECT a.drucksache_id, a.person_id, a.name FROM drucksache_author a JOIN drucksache d
           ON d.id = a.drucksache_id WHERE d.type = ? AND a.activity_type = 'Antwort' ORDER BY a.rowid""",
        (dtype,),
    ):
        signed[r["drucksache_id"]].append((r["person_id"], r["name"].split(",")[0], ministry_key(r["name"])))
    spoke: dict[str, list[tuple]] = defaultdict(list)  # sitting -> the government's turns in its Fragestunde
    for r in conn.execute(
        """SELECT s.id, s.sitting_id, s.person_id, s.speaker_name, s.speaker_role FROM speech s
            JOIN agenda_item a ON a.id = s.agenda_item_id WHERE a.title LIKE 'Fragestunde%'
            AND s.speaker_role IS NOT NULL ORDER BY s.position"""
    ):
        spoke[r["sitting_id"]].append((r["person_id"], r["speaker_name"].split(",")[0], ministry_key(r["speaker_role"]),
                                       r["id"]))  # fmt: skip
    plenum: dict[str, sqlite3.Row] = {}
    first: dict[str, str] = {}
    if has_table(conn, "vorgang_position"):
        for r in conn.execute("SELECT * FROM vorgang_position ORDER BY date, id"):
            first.setdefault(r["vorgang_id"], r["date"][:10])
            if r["document_kind"] == "Plenarprotokoll" and r["chamber"] == "BT":
                plenum.setdefault(r["vorgang_id"], r)
    fragestunde = {r["sitting_id"]: r["position"] for r in conn.execute(
        "SELECT sitting_id, min(position) AS position FROM agenda_item WHERE title LIKE 'Fragestunde%' "
        "GROUP BY sitting_id")}  # fmt: skip
    sittings = {r[0] for r in conn.execute("SELECT id FROM sitting")}
    rows = []
    for v in conn.execute("SELECT id, title, status FROM vorgang WHERE wahlperiode = ? AND type = ? ORDER BY id",
                          (WP, kind)):  # fmt: skip
        c = collected.get(v["id"])
        doc = pk.doc(c["number"], c["id"], c["date"], c["pdf_url"]) if c else None
        named = list(dict.fromkeys(askers.get(c["id"], []))) if c else []
        asker = pk.person(named[0][0], named[0][1].split(",")[0]) if len(named) == 1 else None
        p = plenum.get(v["id"])
        answer = None
        if p and p["document_number"]:
            sid = f"{WP}/{p['document_number'].split('/')[-1]}" if "/" in p["document_number"] else None
            answer = [sid if sid in sittings else None, fragestunde.get(sid), p["pages"], p["pdf_url"],
                      p["document_number"]]  # fmt: skip
        date = c["date"] if c else first.get(v["id"])
        key = ministry_key(ressorts.get(v["id"]))
        by: dict[str, list] = {}
        if key:
            for pid, name, k, *speech in [*(signed.get(c["id"], []) if c else []),
                                          *(spoke.get(answer[0], []) if answer and answer[0] else [])]:  # fmt: skip
                if k == key:
                    by.setdefault(pid or name, [pk.person(pid, name), speech[0] if speech else None])
        rows.append([v["id"], None if c and date == c["date"] else date, v["title"], pk.status(v["status"]),
                     pk.ressort(ressorts.get(v["id"])), doc, asker, answer, list(by.values())])  # fmt: skip
    slug = "schriftliche-fragen" if kind == "Schriftliche Frage" else "muendliche-fragen"
    return pk.payload(slug, ["vorgang", "date", "title", "status", "ressort", "doc", "asker", "answer", "answered_by"],
                      rows)  # fmt: skip


def research_turns(conn: sqlite3.Connection, pk: Packer, which: str) -> dict:
    """Turns in the Fragestunde (`speech.kind` 'fragestunde') or the Regierungsbefragung (every turn under an agenda
    item "Befragung der Bundesregierung"): [speech id, date, person, role (an answer) or null (a question), sitting
    id, agenda position, agenda title, excerpt]. Each links its speech page (urls.speech)."""
    if which == "fragestunde":
        if not _has_kind(conn):
            return pk.payload("fragestunde", [], [])
        where = "s.kind = 'fragestunde'"
    else:
        where = f"a.title LIKE 'Befragung der Bundesregierung%' {kind_filter(conn)}"
    rows = []
    for r in conn.execute(
        f"""SELECT s.id, st.date, s.person_id, s.speaker_name, s.speaker_role, s.fraction, s.sitting_id, a.position,
                   a.title, s.text FROM speech s JOIN sitting st ON st.id = s.sitting_id
            LEFT JOIN agenda_item a ON a.id = s.agenda_item_id
            WHERE st.wahlperiode = ? AND {where} ORDER BY st.date, s.sitting_id, s.position""",
        (WP,),
    ):
        who = pk.person(r["person_id"], r["speaker_name"].split(",")[0].split(" (")[0], r["fraction"])
        title = (r["title"] or "").split("|")[0].strip()
        rows.append([r["id"], r["date"], who, r["speaker_role"], r["sitting_id"], r["position"], title,
                     excerpt(r["text"], EXCERPT)])  # fmt: skip
    return pk.payload(which, ["speech", "date", "person", "role", "sitting", "position", "agenda", "excerpt"], rows)


def _has_kind(conn: sqlite3.Connection) -> bool:
    from research.data import has_speech_kind

    return has_speech_kind(conn)


def research(conn: sqlite3.Connection, cards: set[str]) -> dict[str, dict]:
    """Every kind's JSON for the research view, {slug: payload}; each kind has its own person, ministry and
    Drucksache tables so the browser loads one file per tab."""
    names = _people(conn)
    ressorts = _ressorts(conn)
    has_vorgang = has_table(conn, "vorgang") and has_table(conn, "vorgang_drucksache")
    out = {"kleine-anfragen": research_kleine_anfragen(conn, Packer(cards, names), ressorts)}
    if has_vorgang:
        out["schriftliche-fragen"] = research_written(conn, Packer(cards, names), ressorts, "Schriftliche Frage")
        out["muendliche-fragen"] = research_written(conn, Packer(cards, names), ressorts, "Mündliche Frage")
    out["fragestunde"] = research_turns(conn, Packer(cards, names), "fragestunde")
    out["regierungsbefragung"] = research_turns(conn, Packer(cards, names), "regierungsbefragung")
    return out


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
        f'<tr><td class="l"><a href="../{e(urls.sitting(b["sitting"], b["position"]))}">'
        f"{short_date(b['date'])}</a></td>"
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


RESEARCH_STYLE = """<style>
.fr .qtabs { display: flex; flex-wrap: wrap; gap: 4px; margin: 10px 0 12px; }
.fr .qtabs button { border: 1px solid var(--line); background: var(--card); color: var(--muted); border-radius: 8px;
  padding: 5px 11px; font-size: 13px; cursor: pointer; }
.fr .qtabs button[aria-selected="true"] { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
.fr .qtabs .n { color: var(--faint); font-size: 12px; margin-left: 3px; }
.fr .filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 8px; }
.fr .filters input, .fr .filters select { background: var(--card); color: var(--text); border: 1px solid var(--line);
  border-radius: 8px; padding: 6px 9px; font-size: 13px; min-width: 0; max-width: 100%; }
.fr .filters input { flex: 1 1 200px; }
.fr .filters select[hidden] { display: none; }
.fr .row.q { grid-template-columns: 84px minmax(0, 1fr); }
.fr .row.q .go { font-size: 12.5px; margin-top: 3px; }
.fr .count { color: var(--muted); font-size: 12.5px; margin: 4px 0 8px; }
@media (max-width: 640px) { .fr .row.q { grid-template-columns: 1fr; } }
</style>"""  # noqa: E501


def research_section(counts: dict[str, int]) -> str:
    """The research view's frame: one tab per kind (with its number of entries), the filters and the list, which
    fragen.js fills from the kind's JSON once its tab is opened."""
    tabs = "".join(f'<button type="button" data-k="{slug}" aria-selected="false">{label}<span class="n">'
                   f"{n(counts[slug])}</span></button>" for slug, label, _ in KINDS if slug in counts)  # fmt: skip
    return (
        '<section class="facet fr" id="liste"><h2>Die einzelnen Fragen</h2>'
        '<p class="explain">Jede Kleine Anfrage, jede Schriftliche und Mündliche Frage und jeder Beitrag in der '
        "Fragestunde und der Regierungsbefragung, mit Link zur Quelle: der Drucksache oder dem Vorgang im DIP, dem "
        "PDF, der Karte der Fragenden und bei mündlichen Fragen dem Protokoll. <b>Nur Titel:</b> Der Datenbestand "
        "enthält von Kleinen Anfragen und Schriftlichen Fragen nur den Titel, nicht den Wortlaut der Frage; der "
        "steht in der verlinkten Drucksache. Die Fragenden einer Schriftlichen oder Mündlichen Frage nennt DIP je "
        "Sammeldrucksache, nicht je Frage; genannt ist hier nur, wer allein in seiner Sammeldrucksache steht. "
        "Wer geantwortet hat, ergibt sich aus dem Ressort der Frage: genannt sind, wer für dieses Ressort in der "
        "Sammeldrucksache oder in der Fragestunde geantwortet hat, meist eine Person, manchmal die beiden "
        "Parlamentarischen Staatssekretäre eines Ministeriums.</p>"
        f'<div id="fragen"><div class="qtabs" role="tablist">{tabs}</div>'
        '<div class="filters"><input type="search" id="fq" placeholder="Wörter im Titel …" autocomplete="off" '
        'aria-label="Wörter im Titel"><input type="search" id="fm" placeholder="Abgeordnete …" autocomplete="off" '
        'aria-label="Abgeordnete"><select id="ff" aria-label="Fraktion"></select><select id="fr" aria-label="Ressort">'
        '</select><select id="fmo" aria-label="Monat"></select><select id="fs" aria-label="Stand"></select>'
        '<select id="ft" aria-label="Antwortzeit" hidden><option value="">jede Antwortzeit</option>'
        f"<option>bis {DEADLINE} Tage</option><option>15 bis 28 Tage</option><option>mehr als 28 Tage</option>"
        '<option>offen</option></select></div><div class="count" id="fcount"></div><div class="rows" id="flist"></div>'
        '<button type="button" class="more" id="fmore" style="display:none">Weitere zeigen</button></div></section>'
    )


def page(ka: dict, wq: dict, bf: list[dict], fs: tuple[int, int], counts: dict[str, int] | None = None) -> str:
    research = research_section(counts) if counts else ""
    body = (
        '<section class="card"><h1>Fragen an die Regierung</h1><div class="lines">Kleine Anfragen, Schriftliche '
        "und Mündliche Fragen, Fragestunde und Regierungsbefragung im 21. Bundestag: oben die Zahlen nach "
        "Fraktionen, darunter jede einzelne Frage zum Durchsuchen. Jede Zahl und jede Frage führt zu ihrer "
        'Drucksache oder zum Plenarprotokoll. <a href="#liste">Zu den einzelnen Fragen ↓</a> · '
        '<a href="../daten.html">Über die Daten</a></div></section>'
        f'<div class="qs">{_ka_section(ka)}{_questions_section(wq)}{_befragung_section(bf, fs)}</div>{research}'
        f"<footer>{FOOTER}</footer>" + ('<script src="../fragen.js"></script>' if research else "")
    )
    return shell(root="../", kind="p-questions", active="questions", title="Fragen an die Regierung",
                 desc="Jede Frage der Abgeordneten an die Bundesregierung im 21. Bundestag zum Durchsuchen, und wie "
                      "oft die Fraktionen fragen und wie schnell die Regierung antwortet: Kleine Anfragen, "
                      "Schriftliche und Mündliche Fragen, Fragestunde, Regierungsbefragung.",
                 body=body, data={"kind": "questions"}, head=STYLE + RESEARCH_STYLE)  # fmt: skip


def write(conn: sqlite3.Connection, out: Path, cards: set[str] | None = None) -> dict[str, int]:
    """Write regierung/index.html and one JSON per kind for its research view; returns {"regierung": pages}, or {}
    when the store has no DIP tables. `cards`: the person ids with a card, so a row links only cards that exist."""
    if not has_table(conn, "drucksache"):
        return {}
    d = out / "regierung"
    d.mkdir(parents=True, exist_ok=True)
    lists = research(conn, cards or set())
    for slug, payload in lists.items():
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        (d / f"{slug}.json").write_text(text, encoding="utf-8")
        print(f"regierung/{slug}.json: {len(payload['rows'])} rows, {len(text.encode()) / 1024:.0f} KB")
    counts = {slug: len(p["rows"]) for slug, p in lists.items()}
    html = page(kleine_anfragen(conn), written_questions(conn), befragungen(conn), fragestunden(conn), counts)
    (d / "index.html").write_text(html, encoding="utf-8")
    return {"regierung": 1}
