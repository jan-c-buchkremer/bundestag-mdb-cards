"""Read the foundation store (read-only) and assemble one payload per card."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from cards.titles import short_title

WP = 21
BEFRAGUNG = "Befragung der Bundesregierung"  # every question and answer is its own rede there, see docs/decisions.md
OFFICE = re.compile(r"Bundeskanzler|Bundesminister|Staatssekretär|Staatsminister|Präsident", re.I)
_KURZINTERVENTION = re.compile(r"Kurzintervention|Zwischenbemerkung")
_COMMITTEE_PREFIX = re.compile(r"^Ausschuss (für |des |der )?")
# speech.fraction is NULL for ministers; person.party fills the gap (as in the landscape)
PARTY_TO_FRACTION = {"CDU": "CDU/CSU", "CSU": "CDU/CSU", "DIE LINKE.": "Die Linke"}
NO_FRACTION = "fraktionslos"
VOTE_CHOICES = ("yes", "no", "abstain")
MAP_MIN_CHARS = 500  # the landscape drops shorter speeches (its MIN_CHARS), so only longer ones can link to the map


def connect() -> sqlite3.Connection:
    path = Path(os.environ.get("BDF_DB", "../bundestag-data-foundation/data/bundestag.sqlite"))
    if not path.exists():
        raise FileNotFoundError(f"foundation store not found: {path} (set BDF_DB)")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def display_name(p: sqlite3.Row) -> str:
    return " ".join(x for x in (p["academic_title"], p["first_name"], p["name_prefix"], p["last_name"]) if x)


def committee_short(name: str) -> str:
    return _COMMITTEE_PREFIX.sub("", name)


# ---------------------------------------------------------------- speeches

_SQL_SPEECH = """
SELECT s.id, s.position, s.person_id, s.speaker_name, s.speaker_role, s.fraction, s.text, s.source_document_id,
       st.id AS sitting_id, st.date, st.pdf_url, p.party, a.id AS agenda_item_id, a.top_id, a.title AS agenda_title
FROM speech s
JOIN sitting st ON st.id = s.sitting_id
JOIN person p ON p.id = s.person_id
LEFT JOIN agenda_item a ON a.id = s.agenda_item_id
WHERE st.wahlperiode = ?
ORDER BY st.date, s.position
"""


def _fraction(r: sqlite3.Row) -> str | None:
    return r["fraction"] or PARTY_TO_FRACTION.get(r["party"], r["party"])


def _paragraph_stats(conn: sqlite3.Connection) -> tuple[Counter, dict[str, str]]:
    """Applause paragraphs per speech part, and the chair's words among each part's last six paragraphs."""
    applause: Counter = Counter()
    tail: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for r in conn.execute("SELECT speech_id, position, kind, text FROM speech_paragraph ORDER BY speech_id, position"):
        if r["kind"] == "comment" and "Beifall" in r["text"]:
            applause[r["speech_id"]] += 1
        t = tail[r["speech_id"]]
        t.append((r["position"], r["kind"], r["text"]))
        if len(t) > 6:
            t.pop(0)
    chair = {sid: " ".join(text for _, kind, text in t if kind == "chair") for sid, t in tail.items()}
    return applause, chair


def speeches(conn: sqlite3.Connection) -> dict[str, dict[str, list]]:
    """Per person: `reden` held, `fragen` (Zwischenfragen and Kurzinterventionen) put to others, and `befragung`
    turns in the Regierungsbefragung.

    A rede split at interruptions (`ID…`, `ID…-2`, …) belongs to the person of its first part; parts by anyone
    else are that person's Zwischenfrage or Kurzintervention (the chair's words before it decide which)."""
    applause, chair = _paragraph_stats(conn)
    rede: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute(_SQL_SPEECH, (WP,)):
        rede[re.sub(r"-\d+$", "", r["id"])].append(r)

    out: dict[str, dict[str, list]] = defaultdict(lambda: {"reden": [], "fragen": [], "befragung": []})
    for parts in rede.values():
        first = parts[0]
        where = {
            "date": first["date"], "sitting": first["sitting_id"], "top": first["top_id"],
            "title": short_title(first["agenda_title"], first["top_id"] or ""),
            "pdf": first["pdf_url"], "cite": first["source_document_id"],
        }  # fmt: skip
        if BEFRAGUNG in (first["agenda_title"] or ""):
            for p in parts:
                out[p["person_id"]]["befragung"].append(
                    {"id": p["id"], **where, "words": len(p["text"].split()), "role": p["speaker_role"],
                     "on_map": len(p["text"]) >= MAP_MIN_CHARS}
                )  # fmt: skip
            continue

        main = first["person_id"]
        own = [p for p in parts if p["person_id"] == main]
        interruptions: list[dict] = []
        since_main = 0  # words the main speaker said since the last interruption started
        prev = None
        for p in parts:
            if p["person_id"] == main:
                since_main += len(p["text"].split())
            elif prev is not None and prev["person_id"] == main:
                last = next((i for i in reversed(interruptions) if i["person"] == p["person_id"]), None)
                # "Gestatten Sie …? – Bitte." between two parts of one question is not a second interruption
                if last is None or since_main >= 30:
                    announced = _KURZINTERVENTION.search(chair.get(prev["id"], ""))
                    kind = "kurzintervention" if announced else "zwischenfrage"
                    interruptions.append(
                        {"id": p["id"], "person": p["person_id"], "name": display_speaker(p), "fraction": _fraction(p),
                         "kind": kind}
                    )  # fmt: skip
                since_main = 0
            prev = p
        out[main]["reden"].append(
            {
                "id": first["id"], **where, "role": first["speaker_role"], "fraction": _fraction(first),
                "words": sum(len(p["text"].split()) for p in own),
                "on_map": len("\n\n".join(p["text"] for p in own)) >= MAP_MIN_CHARS,
                "applause": sum(applause[p["id"]] for p in own),
                "interruptions": [{k: v for k, v in i.items() if k != "id"} for i in interruptions],
            }
        )  # fmt: skip
        for i in interruptions:
            out[i["person"]]["fragen"].append(
                {"id": i["id"], **where, "kind": i["kind"], "speaker": main, "speaker_name": display_speaker(first)}
            )
    return out


def display_speaker(r: sqlite3.Row) -> str:
    return r["speaker_name"].split(",")[0].split(" (")[0]


# ---------------------------------------------------------------- votes

_SQL_VOTE = """
SELECT v.vote_id, v.person_id, v.fraction, v.vote, r.number, r.date, r.title, r.yes, r.no, r.abstain, r.absent,
       r.invalid, r.pdf_url, r.xlsx_url, r.sitting_id, r.drucksache_number
FROM individual_vote v JOIN roll_call_vote r ON r.id = v.vote_id
ORDER BY r.date, r.number
"""


def majority(tally: Counter) -> str | None:
    """The fraction's line: its most common yes/no/abstain vote, None on a tie or when nobody voted."""
    ranked = sorted(((tally[c], c) for c in VOTE_CHOICES), reverse=True)
    if ranked[0][0] == 0 or ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def votes(conn: sqlite3.Connection) -> tuple[dict[str, list[dict]], int]:
    """Per person, every roll-call vote with the own vote next to the fraction's line; and the number of votes."""
    rows = conn.execute(_SQL_VOTE).fetchall()
    tally: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in rows:
        tally[(r["vote_id"], r["fraction"])][r["vote"]] += 1
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["person_id"] is None:
            continue
        t = tally[(r["vote_id"], r["fraction"])]
        line = None if r["fraction"] == NO_FRACTION else majority(t)
        out[r["person_id"]].append(
            {
                "id": r["vote_id"], "date": r["date"], "title": r["title"], "vote": r["vote"],
                "fraction": r["fraction"], "line": line,
                "deviates": line is not None and r["vote"] in VOTE_CHOICES and r["vote"] != line,
                "fraction_tally": {c: t[c] for c in (*VOTE_CHOICES, "absent")},
                "result": {c: r[c] for c in (*VOTE_CHOICES, "absent")},
                "drucksache": r["drucksache_number"], "pdf": r["pdf_url"], "xlsx": r["xlsx_url"],
            }
        )  # fmt: skip
    return out, len({r["vote_id"] for r in rows})


# ---------------------------------------------------------------- Drucksachen

# as in the foundation's `query drucksachen`: activities that make someone an author; "Frage" is a Schriftliche Frage
AUTHORSHIP = ("Antrag", "Kleine Anfrage", "Entschließungsantrag", "Änderungsantrag", "Gesetzentwurf", "Frage")
RAPPORTEUR = "Berichterstattung"

_SQL_DRUCKSACHE = """
SELECT da.person_id, da.activity_type, d.id, d.number, d.type, d.title, d.date, d.pdf_url, d.author_count,
       d.originators, d.source_document_id, group_concat(v.subjects, '\x1f') AS subjects
FROM drucksache_author da
JOIN drucksache d ON d.id = da.drucksache_id
LEFT JOIN vorgang_drucksache vd ON vd.drucksache_id = d.id
LEFT JOIN vorgang v ON v.id = vd.vorgang_id
WHERE da.person_id IS NOT NULL AND d.wahlperiode = ?
GROUP BY da.id
ORDER BY d.date, d.number
"""


def drucksachen(conn: sqlite3.Connection) -> dict[str, dict[str, list]]:
    """Per person: `authored` Drucksachen (incl. Schriftliche Fragen) and `reported` ones (Berichterstattung),
    each with the Bundestag's own subject index (DIP sachgebiet) of its Vorgänge."""
    out: dict[str, dict[str, list]] = defaultdict(lambda: {"authored": [], "reported": []})
    for r in conn.execute(_SQL_DRUCKSACHE, (WP,)):
        if r["activity_type"] in AUTHORSHIP:
            key = "authored"
        elif r["activity_type"] == RAPPORTEUR:
            key = "reported"
        else:
            continue  # e.g. "Antwort": the government answering, not the member's document
        subjects = sorted({s for part in (r["subjects"] or "").split("\x1f") if part for s in json.loads(part)})
        out[r["person_id"]][key].append(
            {
                "id": r["id"], "number": r["number"], "type": r["type"], "activity": r["activity_type"],
                "title": r["title"], "date": r["date"], "pdf": r["pdf_url"], "authors": r["author_count"],
                "originators": json.loads(r["originators"]), "subjects": subjects, "cite": r["source_document_id"],
            }
        )  # fmt: skip
    return out


# ---------------------------------------------------------------- persons


def _dated(r: sqlite3.Row) -> dict:
    return {"name": r["name"], "role": r["role"], "from": r["from_date"], "to": r["to_date"]}


def cards(conn: sqlite3.Connection) -> tuple[list[dict], dict]:
    """One payload per card, and facts shared by all pages (sources, coverage).

    Members: everyone with a WP 21 mandate, plus members who vote but are not yet in the Stammdaten (moved up
    after the snapshot). Speakers: everyone else who spoke in a WP 21 sitting (D9)."""
    by_person = speeches(conn)
    docs = drucksachen(conn)
    vote_rows, n_votes = votes(conn)
    mandates: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM mandate ORDER BY wahlperiode"):
        mandates[r["person_id"]].append(r)
    members: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM membership WHERE wahlperiode = ? ORDER BY from_date, id", (WP,)):
        members[r["person_id"]].append(r)

    ids = {pid for pid, ms in mandates.items() if ms[-1]["wahlperiode"] == WP} | set(vote_rows) | set(by_person)
    persons = {r["id"]: r for r in conn.execute("SELECT * FROM person")}
    out = []
    for pid in sorted(ids, key=lambda i: (persons[i]["last_name"], persons[i]["first_name"], i)):
        p = persons[pid]
        wp21 = next((m for m in mandates[pid] if m["wahlperiode"] == WP), None)
        is_member = wp21 is not None or pid in vote_rows
        ms = members[pid]
        fraction_rows = [m for m in ms if m["kind"] == "fraction"]
        current = [m for m in fraction_rows if m["to_date"] is None] or fraction_rows
        if current:
            fraction = current[-1]["name"]
        elif vote_rows.get(pid):
            fraction = vote_rows[pid][-1]["fraction"]
        else:
            fraction = None
        sp = by_person.get(pid, {"reden": [], "fragen": [], "befragung": []})
        roles = [r["role"] for r in sp["reden"] + sp["befragung"] if r["role"]]
        out.append(
            {
                "id": pid,
                "kind": "member" if is_member else "speaker",
                "name": display_name(p),
                "first_name": p["first_name"], "last_name": p["last_name"],
                "birth_date": p["birth_date"], "birth_place": p["birth_place"],
                "gender": p["gender"], "party": p["party"], "fraction": fraction,
                # speakers: their office as the protocol names it; the latest one if it changed
                "role": (roles[-1] if roles else p["role"]) if not is_member else None,
                "mandate": None if wp21 is None else {
                    "type": wp21["mandate_type"], "number": wp21["constituency_number"],
                    "constituency": wp21["constituency_name"], "state": wp21["state"],
                    "from": wp21["from_date"], "to": wp21["to_date"],
                },
                "in_stammdaten": wp21 is not None,
                "first_vote": vote_rows[pid][0]["date"] if vote_rows.get(pid) else None,
                "periods": [m["wahlperiode"] for m in mandates[pid]],
                "since": mandates[pid][0]["from_date"] if mandates[pid] else None,
                "offices": [_dated(m) for m in ms if m["kind"] == "other" and OFFICE.search(m["role"] or "")],
                "fraction_roles": [_dated(m) for m in fraction_rows if m["role"]],
                "fractions": [_dated(m) for m in fraction_rows],
                "committees": [
                    {**_dated(m), "short": committee_short(m["name"])} for m in ms if m["kind"] == "committee"
                ],
                "other": [_dated(m) for m in ms if m["kind"] == "other" and not OFFICE.search(m["role"] or "")],
                "reden": sp["reden"], "fragen": sp["fragen"], "befragung": sp["befragung"],
                "votes": vote_rows.get(pid, []),
                **docs.get(pid, {"authored": [], "reported": []}),
                "career": [
                    {"wp": m["wahlperiode"], "from": m["from_date"], "to": m["to_date"], "type": m["mandate_type"],
                     "number": m["constituency_number"], "constituency": m["constituency_name"], "state": m["state"]}
                    for m in mandates[pid]
                ],
                "aw_id": p["aw_politician_id"], "wikidata": p["wikidata_qid"],
            }
        )  # fmt: skip
    return out, meta(conn, n_votes)


def meta(conn: sqlite3.Connection, n_votes: int) -> dict:
    stamm = conn.execute(
        "SELECT source_url, source_document_id, max(retrieved_at) AS retrieved FROM mandate WHERE wahlperiode = ?",
        (WP,),
    ).fetchone()
    span = conn.execute("SELECT min(date), max(date), count(*) FROM sitting WHERE wahlperiode = ?", (WP,)).fetchone()
    dip = conn.execute("SELECT min(date), max(date), count(*) FROM drucksache WHERE wahlperiode = ?", (WP,)).fetchone()
    return {
        "wp": WP,
        "stammdaten": {"url": stamm["source_url"], "doc": stamm["source_document_id"], "retrieved": stamm["retrieved"]},
        "sittings": {"from": span[0], "to": span[1], "n": span[2]},
        "votes": n_votes,
        "dip": {"from": dip[0], "to": dip[1], "n": dip[2], "complete": dip_complete(conn)},
    }


def dip_complete(conn: sqlite3.Connection) -> bool:
    """True when DIP has Drucksachen in every month that had a sitting. The card only states counts then; an
    interrupted backfill leaves gaps that `bdf update` never fills (it fetches from the latest file on)."""
    sat = {r[0] for r in conn.execute("SELECT DISTINCT substr(date, 1, 7) FROM sitting WHERE wahlperiode = ?", (WP,))}
    dip = {
        r[0] for r in conn.execute("SELECT DISTINCT substr(date, 1, 7) FROM drucksache WHERE wahlperiode = ?", (WP,))
    }
    return bool(sat) and sat <= dip


def index_row(c: dict) -> dict:
    """What the index page needs to list, search and filter one card."""
    m = c["mandate"] or {}
    return {
        "id": c["id"], "name": c["name"], "last": c["last_name"], "kind": c["kind"], "fraction": c["fraction"],
        "role": c["role"], "state": m.get("state"), "type": m.get("type"), "number": m.get("number"),
        "constituency": m.get("constituency"), "left": m.get("to"),
        "first_term": c["kind"] == "member" and not any(wp < WP for wp in c["periods"]),
        "office": next((o["role"] for o in c["offices"] if o["to"] is None), None),
        "committees": sorted({x["short"] for x in c["committees"] if x["to"] is None}),
        "reden": len(c["reden"]),
    }  # fmt: skip
