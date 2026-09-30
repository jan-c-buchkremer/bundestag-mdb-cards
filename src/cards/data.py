"""Read the foundation store (read-only) and assemble one payload per card."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from cards import subtops
from cards.titles import short_title

WP = 21
BEFRAGUNG = "Befragung der Bundesregierung"  # every question and answer is its own rede there, see docs/decisions.md
OFFICE = re.compile(r"Bundeskanzler|Bundesminister|Staatssekretär|Staatsminister|Präsident", re.I)
_KURZINTERVENTION = re.compile(r"Kurzintervention|Zwischenbemerkung")
_COMMITTEE_PREFIX = re.compile(r"^Ausschuss (für |des |der )?")
_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
# speech.fraction is NULL for ministers; person.party fills the gap (as in the landscape)
PARTY_TO_FRACTION = {"CDU": "CDU/CSU", "CSU": "CDU/CSU", "DIE LINKE.": "Die Linke"}
NO_FRACTION = "fraktionslos"
VOTE_CHOICES = ("yes", "no", "abstain")
MIN_CHARS = 500  # as the landscape: shorter units are procedural remarks, oaths and one-liners, not Reden
EXCERPT = 180  # characters of a speech shown next to its link, the full text is on reden/<id>.html
# Land codes of the Stammdaten and the Bundeswahlleiterin (as index.html and card.js); the place pages' names
STATES = {"BW": "Baden-Württemberg", "BY": "Bayern", "BE": "Berlin", "BB": "Brandenburg", "HB": "Bremen",
          "HH": "Hamburg", "HE": "Hessen", "MV": "Mecklenburg-Vorpommern", "NI": "Niedersachsen",
          "NW": "Nordrhein-Westfalen", "RP": "Rheinland-Pfalz", "SL": "Saarland", "SN": "Sachsen",
          "ST": "Sachsen-Anhalt", "SH": "Schleswig-Holstein", "TH": "Thüringen"}  # fmt: skip


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


def excerpt(text: str | None, limit: int = EXCERPT) -> str:
    """The start of a speech, cut at a word: what the fact components show before "Text" links the whole."""
    t = " ".join((text or "").split())
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + " …"


def land_slug(code: str) -> str:
    """ "BW" -> "baden-wuerttemberg", the file name of a Land's place page."""
    return slugify(STATES.get(code, code))


def slugify(name: str) -> str:
    """A stable, readable file name for a Gremium: transliterated, lower case, words joined by "-" (bodies.py,
    and the committee/other links on the card). Not length-capped: the 205 WP 21 committee and Gremium names are
    unique once slugified, some Parlamentariergruppen only by their long list of countries."""
    s = unicodedata.normalize("NFKD", name.translate(_UMLAUT)).encode("ascii", "ignore").decode("ascii")
    return _SLUG_STRIP.sub("-", s.lower()).strip("-") or "gremium"


# ---------------------------------------------------------------- speeches


def _sql_speech(conn: sqlite3.Connection) -> str:
    kind_col = "s.kind" if has_speech_kind(conn) else "'rede' AS kind"
    return f"""
SELECT s.id, s.position, s.person_id, s.speaker_name, s.speaker_role, s.fraction, s.text, s.source_document_id,
       st.id AS sitting_id, st.date, st.pdf_url, p.party, a.id AS agenda_item_id, a.top_id, a.title AS agenda_title,
       a.position AS top_position, {kind_col}
FROM speech s
JOIN sitting st ON st.id = s.sitting_id
JOIN person p ON p.id = s.person_id
LEFT JOIN agenda_item a ON a.id = s.agenda_item_id
WHERE st.wahlperiode = ?
ORDER BY st.date, s.position
"""


def _fraction(r: sqlite3.Row) -> str | None:
    return r["fraction"] or PARTY_TO_FRACTION.get(r["party"], r["party"])


def after_speaker(conn: sqlite3.Connection) -> set[tuple[str, int]]:
    """The comment paragraphs (speech id, position) that follow the speaker's own words: the nearest earlier
    paragraph of the part that is not a comment is of kind 'text'. A comment after the chair's words belongs to the
    chair or to the change of speaker: applause after "Nächster Redner ist … für die CDU/CSU" welcomes the next
    speaker, applause after an Ordnungsruf is for the chair. Used by the cards and the Debattenkultur page alike.
    A Zwischenfrage is its own speech part, so the comments in it go to the asker."""
    out, last = set(), {}
    for sid, pos, kind in conn.execute(
        """SELECT p.speech_id, p.position, p.kind FROM speech_paragraph p JOIN speech s ON s.id = p.speech_id
           JOIN sitting st ON st.id = s.sitting_id WHERE st.wahlperiode = ? ORDER BY p.speech_id, p.position""",
        (WP,),
    ):
        if kind == "comment":
            if last.get(sid) == "text":
                out.add((sid, pos))
        else:
            last[sid] = kind
    return out


def _paragraph_stats(conn: sqlite3.Connection) -> tuple[Counter, dict[str, str]]:
    """Applause paragraphs per speech part (after the speaker's own words, see after_speaker), and the chair's words
    among each part's last six paragraphs."""
    applause: Counter = Counter()
    tail: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    last: dict[str, str] = {}
    for r in conn.execute("SELECT speech_id, position, kind, text FROM speech_paragraph ORDER BY speech_id, position"):
        if r["kind"] != "comment":
            last[r["speech_id"]] = r["kind"]
        elif "Beifall" in r["text"] and last.get(r["speech_id"]) == "text":
            applause[r["speech_id"]] += 1
        t = tail[r["speech_id"]]
        t.append((r["position"], r["kind"], r["text"]))
        if len(t) > 6:
            t.pop(0)
    chair = {sid: " ".join(text for _, kind, text in t if kind == "chair") for sid, t in tail.items()}
    return applause, chair


def speeches(conn: sqlite3.Connection) -> dict[str, dict[str, list]]:
    """Per person: `reden` held (at least MIN_CHARS, as in the landscape), `kurz` shorter contributions, `fragen`
    (Zwischenfragen and Kurzinterventionen) put to others, and `befragung` turns in the Regierungsbefragung.

    A rede split at interruptions (`ID…`, `ID…-2`, …) belongs to the person of its first part; parts by anyone
    else are that person's Zwischenfrage or Kurzintervention (the chair's words before it decide which)."""
    applause, chair = _paragraph_stats(conn)
    rede: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute(_sql_speech(conn), (WP,)):
        rede[re.sub(r"-\d+$", "", r["id"])].append(r)

    out: dict[str, dict[str, list]] = defaultdict(
        lambda: {"reden": [], "kurz": [], "fragen": [], "befragung": [], "fragestunde": []}
    )
    for parts in rede.values():
        first = parts[0]
        where = {
            "date": first["date"], "sitting": first["sitting_id"], "top": first["top_id"],
            "position": first["top_position"], "title": short_title(first["agenda_title"], first["top_id"] or ""),
            "pdf": first["pdf_url"], "cite": first["source_document_id"],
        }  # fmt: skip
        if first["kind"] == "fragestunde":
            # a Fragestunde question, answer or Nachfrage: shown on the card, but not a Rede (docs/decisions.md) -
            # not counted towards "reden"/"kurz" or included in any speaking share
            for p in parts:
                out[p["person_id"]]["fragestunde"].append(
                    {"id": p["id"], **where, "words": len(p["text"].split()), "role": p["speaker_role"],
                     "fraction": _fraction(p), "on_map": False, "excerpt": excerpt(p["text"])}
                )  # fmt: skip
            continue
        if BEFRAGUNG in (first["agenda_title"] or ""):
            for p in parts:
                out[p["person_id"]]["befragung"].append(
                    {"id": p["id"], **where, "words": len(p["text"].split()), "role": p["speaker_role"],
                     "on_map": len(p["text"]) >= MIN_CHARS, "excerpt": excerpt(p["text"])}
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
                         "kind": kind, "excerpt": excerpt(p["text"])}
                    )  # fmt: skip
                since_main = 0
            prev = p
        long = len("\n\n".join(p["text"] for p in own)) >= MIN_CHARS  # re-joined like the landscape's speeches
        out[main]["reden" if long else "kurz"].append(
            {
                "id": first["id"], **where, "role": first["speaker_role"], "fraction": _fraction(first), "on_map": long,
                "words": sum(len(p["text"].split()) for p in own),
                "applause": sum(applause[p["id"]] for p in own),
                "interruptions": [{k: v for k, v in i.items() if k not in ("id", "excerpt")} for i in interruptions],
                "excerpt": excerpt(own[0]["text"]),
            }
        )  # fmt: skip
        for i in interruptions:
            out[i["person"]]["fragen"].append(
                {"id": i["id"], **where, "kind": i["kind"], "speaker": main, "speaker_name": display_speaker(first),
                 "excerpt": i["excerpt"]}
            )  # fmt: skip
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


def vote_outcomes(conn: sqlite3.Connection) -> dict[str, str]:
    """Roll-call vote id -> "angenommen" | "abgelehnt" as the chair announced it (foundation `decision`)."""
    if not has_table(conn, "decision"):
        return {}
    return {
        r["roll_call_vote_id"]: r["result"]
        for r in conn.execute(
            "SELECT roll_call_vote_id, result FROM decision WHERE roll_call_vote_id IS NOT NULL AND result IS NOT NULL"
        )
    }


def outcome(announced: str | None, result: dict[str, int]) -> tuple[str | None, str | None]:
    """The overall result and where it comes from: the chair's announcement ("protocol"), else counted from the
    list as a simple majority of yes over no ("count"; a tie rejects). Votes that need more than a simple majority
    (Kanzlerwahl, Grundgesetz) are announced, so the count is only a fallback."""
    if announced:
        return announced, "protocol"
    if not result["yes"] and not result["no"]:
        return None, None
    return ("angenommen" if result["yes"] > result["no"] else "abgelehnt"), "count"


def votes(conn: sqlite3.Connection) -> tuple[dict[str, list[dict]], int]:
    """Per person, every roll-call vote with the overall result, the own vote and the fraction's line; and the
    number of votes."""
    rows = conn.execute(_SQL_VOTE).fetchall()
    announced = vote_outcomes(conn)
    tally: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for r in rows:
        tally[(r["vote_id"], r["fraction"])][r["vote"]] += 1
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["person_id"] is None:
            continue
        t = tally[(r["vote_id"], r["fraction"])]
        line = None if r["fraction"] == NO_FRACTION else majority(t)
        result = {c: r[c] for c in (*VOTE_CHOICES, "absent")}
        decided, decided_from = outcome(announced.get(r["vote_id"]), result)
        out[r["person_id"]].append(
            {
                "id": r["vote_id"], "date": r["date"], "title": r["title"], "vote": r["vote"],
                "fraction": r["fraction"], "line": line,
                "deviates": line is not None and r["vote"] in VOTE_CHOICES and r["vote"] != line,
                "fraction_tally": {c: t[c] for c in (*VOTE_CHOICES, "absent")},
                "result": result, "outcome": decided, "outcome_from": decided_from,
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


# DIP's Urheber titles ("Fraktion der SPD", "Fraktion BÜNDNIS 90/DIE GRÜNEN", "Bundesregierung") -> the group
_ORIGINATOR = (("cdu/csu", "CDU/CSU"), ("spd", "SPD"), ("afd", "AfD"), ("grünen", "BÜNDNIS 90/DIE GRÜNEN"),
               ("linke", "Die Linke"))  # fmt: skip
GOVERNMENT_GROUP = "Bundesregierung"


def originator_group(title: str) -> str | None:
    """The group behind a DIP Urheber title: a fraction, the Bundesregierung, or None (a committee, the Bundesrat, a
    person). Matched by name; a normalised field in the foundation would be better (docs/plan.md 11.8)."""
    t = title.lower()
    if t.startswith("bundesregierung"):
        return GOVERNMENT_GROUP
    if "fraktion" in t or "gruppe" in t:
        return next((f for key, f in _ORIGINATOR if key in t), None)
    return None


def drucksache_facts(conn: sqlite3.Connection) -> list[dict]:
    """Every WP 21 Drucksache as the fact components show it, oldest first: number, type, title, date, Urheber and
    the groups behind them, the DIP and PDF links, and its Vorgang when it belongs to exactly one."""
    if not has_table(conn, "drucksache"):
        return []
    vindex = vorgang_index(conn)
    out = []
    for r in conn.execute("SELECT * FROM drucksache WHERE wahlperiode = ? ORDER BY date, number", (WP,)):
        originators = json.loads(r["originators"] or "[]")
        vs = vindex.get(r["number"], set())
        bt = (r["publisher"] or "BT") == "BT"
        out.append({
            "id": r["id"], "number": r["number"], "type": r["type"], "date": r["date"],
            "title": dip_subject(r["title"]) or r["title"], "originators": originators,
            "groups": sorted({g for g in map(originator_group, originators) if g}),
            "url": DIP_DOC.format(r["id"]), "pdf": r["pdf_url"] or (drucksache_pdf(r["number"]) if bt else None),
            "cite": r["source_document_id"], "vorgang": next(iter(vs)) if len(vs) == 1 else None,
        })  # fmt: skip
    return out


def speech_facts(cards: list[dict]) -> list[dict]:
    """Every speech of the cards as the speech component takes it (with its speaker), oldest first: Reden, short
    contributions, Befragung and Fragestunde turns. Zwischenfragen stay inside the rede they interrupt."""
    out = []
    for c in cards:
        who = {"person": c["id"], "name": c["name"], "photo": bool(c.get("photo"))}
        for key, kind in (
            ("reden", "rede"),
            ("kurz", "kurz"),
            ("befragung", "befragung"),
            ("fragestunde", "fragestunde"),
        ):
            for s in c.get(key) or []:
                out.append({**s, **who, "kind": kind, "fraction": s.get("fraction") or c["fraction"]})
    return sorted(out, key=lambda s: (s["date"], s["id"]))


# ---------------------------------------------------------------- election (Bundeswahlleiterin)

ELECTION = "btw25"  # the election that formed WP 21


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def has_speech_kind(conn: sqlite3.Connection) -> bool:
    """False for a store ingested before speech.kind existed: every speech is then a 'rede'."""
    return _has_column(conn, "speech", "kind")


def kind_filter(conn: sqlite3.Connection, alias: str = "s") -> str:
    """SQL to AND into a WHERE clause on `speech alias`, excluding Fragestunde turns from speech counts and
    speaking shares (docs/decisions.md): empty for a store without the column, so every speech counts there."""
    return f"AND {alias}.kind != 'fragestunde'" if has_speech_kind(conn) else ""


def has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def _first_votes(conn: sqlite3.Connection) -> dict[tuple[int, str], float]:
    """Erststimme share per (Wahlkreis, party): a candidate's own result, since each party runs one candidate."""
    return {
        (r["constituency_number"], r["party"]): r["percent"]
        for r in conn.execute(
            "SELECT constituency_number, party, percent FROM constituency_result WHERE election = ? AND vote = 1",
            (ELECTION,),
        )
    }


def elections(conn: sqlite3.Connection) -> dict[str, dict]:
    """Per person: how they were elected in 2025, with Wahlkreis, first-vote share and list position.
    Empty when the store has no election tables yet (foundation before the Bundeswahlleiterin source)."""
    if not has_table(conn, "election_candidacy"):
        return {}
    shares = _first_votes(conn)
    names = {
        r["number"]: r["name"]
        for r in conn.execute("SELECT number, name FROM constituency WHERE election = ?", (ELECTION,))
    }
    out = {}
    for r in conn.execute("SELECT * FROM election_candidacy WHERE election = ? AND person_id IS NOT NULL", (ELECTION,)):
        wk = r["constituency_number"]
        out[r["person_id"]] = {
            "via": r["elected_via"], "party": r["party"],
            "number": wk, "constituency": names.get(wk),
            "percent": r["first_vote_percent"] if r["first_vote_percent"] is not None else shares.get((wk, r["party"])),
            "list_state": r["list_state"], "list_position": r["list_position"],
        }  # fmt: skip
    return out


def constituencies(conn: sqlite3.Connection) -> list[dict]:
    """Every Wahlkreis with the party that got the seat (None: the winner had no Zweitstimmendeckung),
    the strongest party by first votes, and turnout."""
    if not has_table(conn, "constituency"):
        return []
    top: dict[int, tuple[str, float]] = {}
    for (wk, party), pct in _first_votes(conn).items():
        if pct is not None and (wk not in top or pct > top[wk][1]):
            top[wk] = (party, pct)
    none = (None, None)
    return [
        {
            "number": r["number"], "name": r["name"], "state": r["state"], "seat_party": r["seat_party"],
            "first_party": top.get(r["number"], none)[0], "first_percent": top.get(r["number"], none)[1],
            "turnout": round(100 * r["voters"] / r["electorate"], 1) if r["voters"] and r["electorate"] else None,
        }
        for r in conn.execute("SELECT * FROM constituency WHERE election = ? ORDER BY number", (ELECTION,))
    ]  # fmt: skip


def election_sources(conn: sqlite3.Connection) -> list[dict]:
    if not has_table(conn, "constituency"):
        return []
    return [
        {"url": r["source_url"], "doc": r["source_document_id"], "retrieved": r["retrieved"]}
        for t in ("election_candidacy", "constituency")
        for r in conn.execute(
            f"SELECT source_url, source_document_id, max(retrieved_at) AS retrieved FROM {t} WHERE election = ?",
            (ELECTION,),
        )
        if r["source_url"]
    ]


# ---------------------------------------------------------------- interjections (Im Plenum)

REACTIONS = ("beifall", "zuruf", "gegenruf", "lachen", "heiterkeit", "widerspruch", "zustimmung")
MAX_TEXT = 300  # a Zuruf is a sentence or two; the few long ones are cut on the page


def plenum(conn: sqlite3.Connection) -> dict[str, dict]:
    """Per person: reactions the protocol records on their own contributions, by fraction, and the Zurufe they
    made themselves. Empty when the store has no interjection table yet."""
    if not has_table(conn, "interjection"):
        return {}
    out: dict[str, dict] = defaultdict(lambda: {"received": {}, "house": 0, "made": []})
    heard = after_speaker(conn)  # notes after the chair's words are not reactions to the speaker
    for r in conn.execute(
        """SELECT s.person_id, i.kind, i.actor, i.fraction, i.speech_id, i.paragraph, 1 AS n
           FROM interjection i JOIN speech s ON s.id = i.speech_id JOIN sitting st ON st.id = s.sitting_id
           WHERE st.wahlperiode = ? AND i.kind IN ({})
             AND (i.person_id IS NULL OR i.person_id != s.person_id)""".format(",".join("?" * len(REACTIONS))),
        (WP, *REACTIONS),
    ):
        if (r["speech_id"], r["paragraph"]) not in heard:
            continue
        p = out[r["person_id"]]
        if r["actor"] == "house":
            p["house"] += r["n"]
            continue
        if not r["fraction"]:
            continue
        f = p["received"].setdefault(r["fraction"], {"beifall": 0, "beifall_members": 0, "zurufe": 0, "lachen": 0,
                                                     "widerspruch": 0})  # fmt: skip
        if r["kind"] == "beifall":
            f["beifall" if r["actor"] == "fraction" else "beifall_members"] += r["n"]
        elif r["kind"] in ("zuruf", "gegenruf"):
            f["zurufe"] += r["n"]
        elif r["kind"] in ("lachen", "heiterkeit"):
            f["lachen"] += r["n"]
        elif r["kind"] == "widerspruch":
            f["widerspruch"] += r["n"]
    for r in conn.execute(
        """SELECT i.person_id, i.kind, i.text, i.to_person_id, i.to_name, s.id AS speech_id, s.person_id AS speaker,
                  s.speaker_name, st.date, st.id AS sitting, a.title, a.top_id
           FROM interjection i JOIN speech s ON s.id = i.speech_id JOIN sitting st ON st.id = s.sitting_id
           LEFT JOIN agenda_item a ON a.id = s.agenda_item_id
           WHERE st.wahlperiode = ? AND i.actor = 'person' AND i.kind IN ('zuruf', 'gegenruf')
             AND i.person_id IS NOT NULL
           ORDER BY st.date, s.position, i.paragraph, i.part""",
        (WP,),
    ):
        text = r["text"] or ""
        out[r["person_id"]]["made"].append(
            {
                "date": r["date"], "id": r["speech_id"], "kind": r["kind"],
                "text": text[:MAX_TEXT] + ("…" if len(text) > MAX_TEXT else ""),
                "speaker": r["speaker"], "speaker_name": display_speaker(r),
                "to": r["to_person_id"], "to_name": r["to_name"],
                # the page builds the protocol link and "BT-PlPr. 21/94" from the sitting; repeating them on every
                # row doubled the size of the pages of frequent interjectors
                "title": short_title(r["title"], r["top_id"] or ""), "sitting": r["sitting"],
            }
        )  # fmt: skip
    return out


# ---------------------------------------------------------------- abgeordnetenwatch


def aw_profiles(conn: sqlite3.Connection) -> dict[str, dict]:
    """Per person: public profile and citizen questions (lifetime totals of the profile, not per Wahlperiode).
    Empty when the store has no aw_profile table yet."""
    if not has_table(conn, "aw_profile"):
        return {}
    return {
        r["person_id"]: {
            "url": r["url"], "questions": r["questions"], "answered": r["questions_answered"],
            "retrieved": r["retrieved_at"],
        }
        for r in conn.execute("SELECT * FROM aw_profile WHERE person_id IS NOT NULL")
    }  # fmt: skip


def side_jobs(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Per person: Nebentätigkeiten (side jobs) reported under the Bundestag's Verhaltensregeln, republished by
    abgeordnetenwatch, newest change first. Facts as published only: no income totals, no linking to speeches or
    votes. Empty when the store has no side_job table yet."""
    if not has_table(conn, "side_job"):
        return {}
    out: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM side_job WHERE person_id IS NOT NULL ORDER BY data_change_date DESC, id DESC"):
        out[r["person_id"]].append(
            {
                "id": r["id"], "label": r["label"], "category": r["category"], "organization": r["organization"],
                "income_level": r["income_level"], "income_range": r["income_range"], "interval": r["interval"],
                "changed": r["data_change_date"], "url": r["source_url"],
            }
        )  # fmt: skip
    return dict(out)


# ---------------------------------------------------------------- photos and government offices


def photos(conn: sqlite3.Connection) -> dict[str, dict]:
    """Per person: the portrait's credit and the page it comes from (bundestag.de biography or Commons file), and
    its download under the foundation's raw folder (`path`, for the build only). Empty without `person_photo`."""
    if not has_table(conn, "person_photo"):
        return {}
    return {
        r["person_id"]: {"credit": r["credit"], "url": r["bio_url"] or r["source_url"], "path": r["local_path"]}
        for r in conn.execute("SELECT * FROM person_photo")
    }


_MALE_ADJ = re.compile(r"\b(Parlamentarisch|beamtet)er\b")
_MALE_TITLE = re.compile(r"\b(Bundeskanzler|Bundesminister|Staatsminister|Staatssekretär|Chef)\b")
_FEMALE_ROLE = re.compile(r"(Kanzlerin|Ministerin|Staatssekretärin)\b")
# which source dates an office when several name it: Wikidata and the Stammdaten give the term, the protocols
# only show that the office was held on the days someone spoke in it
SOURCE_RANK = {"wikidata": 0, "stammdaten": 1, "protocol": 2}


def feminine(office: str) -> str:
    """Wikidata labels positions in the masculine ("Bundesminister der Finanzen") whoever holds them. Only the
    holder's own title changes: "Staatsminister beim Bundeskanzler" names the Kanzler, not the holder."""
    return _MALE_TITLE.sub(r"\1in", _MALE_ADJ.sub(r"\1e", office, count=1), count=1)


def _office_key(office: str) -> str:
    return " ".join(feminine(office).lower().split())


def government_roles(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Per person: offices in the federal government (foundation `government_role`), newest first. Rows naming
    the same office for an overlapping time (Wikidata, Stammdaten, protocol evidence) become one office with
    every source, dated by the best one. Works with and without the `source_kind` column; empty without the table."""
    if not has_table(conn, "government_role"):
        return {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    rows = conn.execute("SELECT * FROM government_role WHERE person_id IS NOT NULL ORDER BY from_date, id").fetchall()
    for r in sorted(rows, key=lambda r: SOURCE_RANK.get(_source_kind(r), 9)):
        src = {"kind": _source_kind(r), "url": r["source_url"], "doc": r["source_document_id"],
               "from": r["from_date"], "to": r["to_date"]}  # fmt: skip
        same = next(
            (o for o in grouped[r["person_id"]] if _office_key(o["office"]) == _office_key(r["office"])
             and (o["from"] or "") <= (r["to_date"] or "9999") and (r["from_date"] or "") <= (o["to"] or "9999")),
            None,
        )  # fmt: skip
        if same is not None:
            same["sources"].append(src)
            same["department"] = same["department"] or r["department"]
            continue
        grouped[r["person_id"]].append(
            {"office": r["office"], "department": r["department"], "kind": r["kind"], "from": r["from_date"],
             "to": r["to_date"], "evidence": src["kind"] == "protocol", "sources": [src]}
        )  # fmt: skip
    today = dt.date.today().isoformat()
    for offices in grouped.values():
        offices.sort(key=lambda o: (in_office(o, today), o["from"] or ""), reverse=True)
    return dict(grouped)


def in_office(o: dict, today: str) -> bool:
    """Protocol evidence has no end: its last date is only the last time the person spoke in the office."""
    return o["evidence"] or o["to"] is None or o["to"] >= today


def _source_kind(r: sqlite3.Row) -> str:
    # sqlite3.Row: `in` tests the values, not the column names
    return (r["source_kind"] if "source_kind" in r.keys() else None) or "wikidata"  # noqa: SIM118


# ---------------------------------------------------------------- persons


def _dated(r: sqlite3.Row) -> dict:
    return {"name": r["name"], "role": r["role"], "from": r["from_date"], "to": r["to_date"]}


def cards(conn: sqlite3.Connection) -> tuple[list[dict], dict]:
    """One payload per card, and facts shared by all pages (sources, coverage).

    Members: everyone with a WP 21 mandate, plus members who vote but are not yet in the Stammdaten (moved up
    after the snapshot). Speakers: everyone else who spoke in a WP 21 sitting (D9), and every member of the
    government in `government_role` without a mandate, even one who never spoke (kind "speaker" with offices)."""
    by_person = speeches(conn)
    docs = drucksachen(conn)
    elected = elections(conn)
    aw = aw_profiles(conn)
    sj = side_jobs(conn)
    heard = plenum(conn)
    vote_rows, n_votes = votes(conn)
    portraits = photos(conn)
    gov_roles = government_roles(conn)
    mandates: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM mandate ORDER BY wahlperiode"):
        mandates[r["person_id"]].append(r)
    members: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM membership WHERE wahlperiode = ? ORDER BY from_date, id", (WP,)):
        members[r["person_id"]].append(r)

    persons = {r["id"]: r for r in conn.execute("SELECT * FROM person")}
    ids = {pid for pid, ms in mandates.items() if ms[-1]["wahlperiode"] == WP} | set(vote_rows) | set(by_person)
    ids |= {pid for pid in gov_roles if pid in persons}  # every member of the government, even if never heard
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
        sp = by_person.get(pid, {"reden": [], "kurz": [], "fragen": [], "befragung": [], "fragestunde": []})
        roles = [r["role"] for r in sp["reden"] + sp["befragung"] + sp["fragestunde"] if r["role"]]
        female = p["gender"] == "weiblich" or any(_FEMALE_ROLE.search(r) for r in roles)
        offices_held = [
            {**o, "office": feminine(o["office"]) if female else o["office"]} for o in gov_roles.get(pid, [])
        ]
        latest_office = offices_held[0]["office"] if offices_held else None  # current ones sort first
        photo = portraits.get(pid)
        out.append(
            {
                "id": pid,
                "kind": "member" if is_member else "speaker",
                "name": display_name(p),
                "first_name": p["first_name"], "last_name": p["last_name"],
                "birth_date": p["birth_date"], "birth_place": p["birth_place"],
                "gender": p["gender"], "party": p["party"], "fraction": fraction,
                # speakers: their office as the protocol names it (the latest one if it changed), else the government's
                "role": None if is_member else roles[-1] if roles else latest_office or p["role"],
                "government": offices_held,
                "photo": {"credit": photo["credit"], "url": photo["url"]} if photo else None,
                "mandate": None if wp21 is None else {
                    "type": wp21["mandate_type"], "number": wp21["constituency_number"],
                    "constituency": wp21["constituency_name"], "state": wp21["state"],
                    "from": wp21["from_date"], "to": wp21["to_date"],
                },
                "in_stammdaten": wp21 is not None,
                "election": elected.get(pid),
                "first_vote": vote_rows[pid][0]["date"] if vote_rows.get(pid) else None,
                "periods": [m["wahlperiode"] for m in mandates[pid]],
                "since": mandates[pid][0]["from_date"] if mandates[pid] else None,
                "offices": [_dated(m) for m in ms if m["kind"] == "other" and OFFICE.search(m["role"] or "")],
                "fraction_roles": [_dated(m) for m in fraction_rows if m["role"]],
                "fractions": [_dated(m) for m in fraction_rows],
                "committees": [
                    {**_dated(m), "short": committee_short(m["name"]), "slug": slugify(committee_short(m["name"]))}
                    for m in ms if m["kind"] == "committee"
                ],  # fmt: skip
                "other": [
                    {**_dated(m), "slug": slugify(m["name"])}
                    for m in ms if m["kind"] == "other" and not OFFICE.search(m["role"] or "")
                ],  # fmt: skip
                "reden": sp["reden"], "kurz": sp["kurz"], "fragen": sp["fragen"], "befragung": sp["befragung"],
                "fragestunde": sp["fragestunde"],
                "votes": vote_rows.get(pid, []),
                **docs.get(pid, {"authored": [], "reported": []}),
                "career": [
                    {"wp": m["wahlperiode"], "from": m["from_date"], "to": m["to_date"], "type": m["mandate_type"],
                     "number": m["constituency_number"], "constituency": m["constituency_name"], "state": m["state"]}
                    for m in mandates[pid]
                ],
                "aw_id": p["aw_politician_id"], "wikidata": p["wikidata_qid"], "aw": aw.get(pid),
                "side_jobs": sj.get(pid, []),
                "plenum": heard.get(pid, {"received": {}, "house": 0, "made": []}) if heard else None,
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
        "election": election_sources(conn),
    }


def dip_complete(conn: sqlite3.Connection) -> bool:
    """True when DIP has Drucksachen in every month that had a sitting. The card only states counts then; an
    interrupted backfill leaves gaps that `bdf update` never fills (it fetches from the latest file on)."""
    sat = {r[0] for r in conn.execute("SELECT DISTINCT substr(date, 1, 7) FROM sitting WHERE wahlperiode = ?", (WP,))}
    dip = {
        r[0] for r in conn.execute("SELECT DISTINCT substr(date, 1, 7) FROM drucksache WHERE wahlperiode = ?", (WP,))
    }
    return bool(sat) and sat <= dip


# ---------------------------------------------------------------- government, seating chart, last sitting

# government_role.kind (foundation, from Wikidata) in order of rank; beamtete Staatssekretäre are civil servants,
# not members of the government, and have no seat on the Regierungsbank
GOVERNMENT_KINDS = ("kanzler", "minister", "staatsminister", "parl_sts")
_LEAD = (  # fraction leadership in the seating chart's front row, most senior first
    re.compile(r"^Vorsitzender?$"),
    re.compile(r"^Erster? Parlamentarische"),
    re.compile(r"^(Erster? )?Stellv.*Vorsitzender?\b(?!.*Geschäftsführer)"),
    re.compile(r"Parlamentarischer? Geschäftsführer"),
)


def lead_rank(roles: list[str]) -> int | None:
    """Rank of the most senior fraction leadership role (0 = Vorsitz), None for none."""
    ranks = [i for role in roles for i, rx in enumerate(_LEAD) if rx.search(role or "")]
    return min(ranks) if ranks else None


def government(conn: sqlite3.Connection) -> list[dict]:
    """Current members of the government (Kanzler, Minister, Staatsminister, Parlamentarische Staatssekretäre),
    one entry per person with the highest-ranking office, in order of rank. Empty when the store has no
    government_role table yet (foundation before the Wikidata source)."""
    if not has_table(conn, "government_role"):
        return []
    # protocol rows (foundation `source_kind`) date evidence, not a term: their last date does not end the office
    evidence = "OR g.source_kind = 'protocol'" if _has_column(conn, "government_role", "source_kind") else ""
    rows = conn.execute(
        f"""SELECT g.person_id, g.wikidata_qid, g.name, g.office, g.department, g.kind, g.from_date, g.to_date,
                  {"g.source_kind" if evidence else "'wikidata'"} AS source_kind, p.party, p.gender
           FROM government_role g LEFT JOIN person p ON p.id = g.person_id
           WHERE g.to_date IS NULL OR g.to_date >= date('now') {evidence}"""
    ).fetchall()
    best: dict[str, sqlite3.Row] = {}
    same: dict[str, list[sqlite3.Row]] = defaultdict(list)  # every current row per person
    rank = {k: i for i, k in enumerate(GOVERNMENT_KINDS)}
    for r in rows:
        if r["kind"] not in rank:
            continue
        pid = r["person_id"] or f"Q{(r['wikidata_qid'] or '').lstrip('Q')}"  # the foundation's id for non-MdBs
        same[pid].append(r)
        key = (rank[r["kind"]], r["from_date"] or "")
        if pid not in best or key < (rank[best[pid]["kind"]], best[pid]["from_date"] or ""):
            best[pid] = r
    out = []
    for pid, r in best.items():
        # the office only the protocols know: its last date is the latest sitting that prints it, not an end
        held = [x for x in same[pid] if _office_key(x["office"]) == _office_key(r["office"])]
        evidence_only = all(x["source_kind"] == "protocol" for x in held)
        out.append({
            "id": pid, "name": r["name"], "department": r["department"], "kind": r["kind"],
            "office": feminine(r["office"]) if r["gender"] == "weiblich" else r["office"],
            "fraction": PARTY_TO_FRACTION.get(r["party"], r["party"]) if r["party"] else None,
            "evidence": evidence_only,
            "seen": max(x["to_date"] or x["from_date"] for x in held) if evidence_only else None,
        })  # fmt: skip
    return sorted(out, key=lambda g: (rank[g["kind"]], g["department"] or "", g["name"]))


def last_sitting(conn: sqlite3.Connection) -> dict | None:
    """The latest sitting in the store, its ISO week (the Themenlandschaft's page) and everyone who held a
    speech in it: the owners of each rede, not those who only put a Zwischenfrage."""
    r = conn.execute(
        "SELECT id, date FROM sitting WHERE wahlperiode = ? ORDER BY date DESC, number DESC LIMIT 1", (WP,)
    ).fetchone()
    if r is None:
        return None
    speakers = {
        s["person_id"]
        for s in conn.execute(
            f"SELECT id, person_id FROM speech s WHERE sitting_id = ? AND person_id IS NOT NULL {kind_filter(conn)}",
            (r["id"],),
        )
        if not re.search(r"-\d+$", s["id"])
    }
    y, w, _ = dt.date.fromisoformat(r["date"]).isocalendar()
    return {"id": r["id"], "date": r["date"], "week": f"{y}-W{w:02d}", "speakers": sorted(speakers)}


def index_row(c: dict, government: dict[str, dict] | None = None) -> dict:
    """What the index page needs to list, search and filter one card, and to seat it in the Plenum view."""
    m = c["mandate"] or {}
    gov = (government or {}).get(c["id"])
    return {
        "id": c["id"], "name": c["name"], "last": c["last_name"], "kind": c["kind"], "fraction": c["fraction"],
        "role": c["role"], "state": m.get("state"), "type": m.get("type"), "number": m.get("number"),
        "constituency": m.get("constituency"), "left": m.get("to"),
        "first_term": c["kind"] == "member" and not any(wp < WP for wp in c["periods"]),
        "office": next((o["role"] for o in c["offices"] if o["to"] is None), None),
        "committees": sorted({x["short"] for x in c["committees"] if x["to"] is None}),
        "reden": len(c["reden"]),
        "lead": lead_rank([r["role"] for r in c["fraction_roles"] if r["to"] is None]),
        "gov": gov["office"] if gov else None,
        "photo": bool(c.get("photo")),
    }  # fmt: skip


# ---------------------------------------------------------------- decisions and sittings (vote and sitting pages)

DIP_DOC = "https://dip.bundestag.de/drucksache/x/{}"  # DIP ignores the title slug; the id picks the document
RESULTS = ("angenommen", "abgelehnt")
_DRS = re.compile(r"\b(\d{2})/(\d{1,5})\b")
# a subject with none of these names only a document type ("Beschlussempfehlung", "Gesetzentwurf – zweite Beratung")
_INFORMATIVE = re.compile(r"„|\b(zur|zum|über|gegen|zu dem|zu der|betreffend)\b")
_HIER = re.compile(r"^([a-z]\) )?hier: ")
_INTRODUCED = re.compile(r"^von (der|den) (.+?) eingebrachten (\w+)")
# the chair proposing a referral ("Interfraktionell wird Überweisung der Vorlage auf Drucksache 21/6466 an …
# vorgeschlagen") or declaring one decided ("Dann ist die Überweisung so beschlossen")
_REFERRAL = re.compile(r"Überweisung (der|des|von) .*?vorgeschlagen|Überweisung (so )?beschlossen|überwiesen", re.S)


def page_id(any_id: str) -> str:
    """File name of a vote or sitting page: "21/90/h3" -> "21-90-h3"."""
    return any_id.replace("/", "-")


def drucksache_pdf(number: str) -> str:
    """The Bundestag's PDF of a Drucksache, from its number alone: 21/6130 -> …/btd/21/061/2106130.pdf."""
    wp, n = number.split("/")
    n5 = f"{int(n):05d}"
    return f"https://dserver.bundestag.de/btd/{wp}/{n5[:3]}/{wp}{n5}.pdf"


def drucksache_numbers(text: str | None) -> list[str]:
    return [f"{wp}/{int(n)}" for wp, n in _DRS.findall(text or "")]


def vorgang_index(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """BT-Drucksache number -> the WP 21 Vorgänge it belongs to (DIP `vorgang_drucksache`). An Unterrichtung shared by
    several Vorgänge is left out: it is the § 80 GO-BT list of referred bills (21/2669 is in 28 Vorgänge) and would tie
    unrelated debates and decisions to each of them. Empty without the DIP tables."""
    if not has_table(conn, "vorgang") or not has_table(conn, "vorgang_drucksache"):
        return {}
    out: dict[str, set[str]] = defaultdict(set)
    for r in conn.execute(
        """SELECT d.number, d.type, d.publisher, vd.vorgang_id,
                  (SELECT count(*) FROM vorgang_drucksache x WHERE x.drucksache_id = d.id) AS shared
           FROM vorgang_drucksache vd JOIN drucksache d ON d.id = vd.drucksache_id
           JOIN vorgang v ON v.id = vd.vorgang_id WHERE v.wahlperiode = ?""",
        (WP,),
    ):
        if (r["publisher"] or "BT") != "BT" or (r["type"] == "Unterrichtung" and r["shared"] > 1):
            continue
        out[r["number"]].add(r["vorgang_id"])
    return dict(out)


def vorgang_titles(conn: sqlite3.Connection) -> dict[str, str]:
    """WP 21 Vorgang id -> title; empty without the table."""
    if not has_table(conn, "vorgang"):
        return {}
    return {r["id"]: r["title"] for r in conn.execute("SELECT id, title FROM vorgang WHERE wahlperiode = ?", (WP,))}


def decision_href(page: str, vorgaenge: list[str]) -> str:
    """Where a decision lives (D15): a point on its Vorgang's timeline when it belongs to exactly one, else its own
    page in abstimmungen/. Relative to the site root."""
    if len(vorgaenge) == 1:
        return f"vorgaenge/{vorgaenge[0]}.html#abst-{page}"
    return f"abstimmungen/{page}.html"


def _dip_index(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {r["number"]: r for r in conn.execute("SELECT id, number, type, title FROM drucksache")}


def drucksache_ref(number: str, dip: dict[str, sqlite3.Row]) -> dict:
    """A Drucksache as the pages link it: to DIP when DIP has it, else to the PDF."""
    r = dip.get(number)
    return {
        "number": number, "type": r["type"] if r else None,
        "url": DIP_DOC.format(r["id"]) if r else drucksache_pdf(number), "pdf": drucksache_pdf(number),
    }  # fmt: skip


def dip_subject(title: str | None) -> str | None:
    """The substantive line of a DIP title: DIP puts "zu dem Antrag … – Drucksache 21/1 –" lines before it."""
    lines = [ln.strip(" -–") for ln in (title or "").replace("\r", "").split("\n")]
    lines = [ln for ln in lines if ln and not ln.startswith("Drucksache")]
    return lines[-1] if lines else None


def clean_subject(subject: str) -> str:
    """ "von der Bundesregierung eingebrachten Gesetzentwurf zur …" -> "Gesetzentwurf der Bundesregierung zur …"."""
    s = _INTRODUCED.sub(lambda m: f"{m[3]} der {m[2]}", subject.strip())
    return s[:1].upper() + s[1:]


def is_bare(subject: str) -> bool:
    return not (_INFORMATIVE.search(subject) or subject.startswith("Einzelplan"))


def decision_title(subject: str, rcv_title: str | None, drs: str | None, dip: dict, agenda_title: str | None) -> str:
    """A headline for a decision. The chair often names only the document type ("Beschlussempfehlung"); then the
    Drucksache's DIP title, else the agenda item's title says what it is about (the subject stays next to it)."""
    if rcv_title:
        return rcv_title
    subject = clean_subject(subject)
    if not is_bare(subject):
        return subject
    about = dip_subject(dip[drs]["title"]) if drs in dip else None
    about = _HIER.sub("", about or agenda_title or "")
    if not about:
        return subject
    if about.split()[0] == subject.split()[0]:  # "Sammelübersicht 171 zu Petitionen" says it already
        return about if len(subject.split()) == 1 else subject
    return f"{subject}: {about}"


def _houses(conn: sqlite3.Connection) -> list[tuple[str, dict[str, int]]]:
    """Seats per fraction on each roll-call date, from the vote lists (every member has a row, absent or not)."""
    by_date: dict[str, Counter] = {}
    for r in conn.execute(
        """SELECT r.date, r.id, v.fraction, count(*) AS n
           FROM individual_vote v JOIN roll_call_vote r ON r.id = v.vote_id
           GROUP BY r.id, v.fraction ORDER BY r.date, r.number"""
    ):
        by_date.setdefault(r["date"], {}).setdefault(r["id"], Counter())[r["fraction"]] = r["n"]
    # the last vote of a day: the house as it stood after the day's changes
    return [(d, dict(list(votes.values())[-1])) for d, votes in sorted(by_date.items())]


def house_on(houses: list[tuple[str, dict[str, int]]], date: str) -> dict[str, int]:
    """The fractions' seats on a date: from the latest vote list on or before it, else the first one after."""
    before = [h for d, h in houses if d <= date]
    if before:
        return before[-1]
    return houses[0][1] if houses else {}


_SQL_DECISION = """
SELECT d.*, st.date, st.pdf_url AS protocol, st.source_document_id AS cite, a.position AS top_position, a.top_id,
       a.title AS agenda_title
FROM decision d JOIN sitting st ON st.id = d.sitting_id LEFT JOIN agenda_item a ON a.id = d.agenda_item_id
WHERE st.wahlperiode = ?
"""


def decisions(conn: sqlite3.Connection) -> list[dict]:
    """Every decision on substance (foundation `decision`), plus the roll-call votes without one (their protocol is
    not in the store yet, or the vote is not in its text), newest sitting first, in protocol order within one.
    Roll-call votes carry the totals and the tally per fraction; show-of-hands decisions the fractions' positions
    and the seats per fraction on that day. Empty when the store has no decision table yet."""
    if not has_table(conn, "decision"):
        return []
    dip = _dip_index(conn)
    houses = _houses(conn)
    rcv = {r["id"]: r for r in conn.execute("SELECT * FROM roll_call_vote")}
    tally: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for r in conn.execute("SELECT vote_id, fraction, vote, count(*) AS n FROM individual_vote GROUP BY 1, 2, 3"):
        tally[r["vote_id"]][r["fraction"]][r["vote"]] = r["n"]
    positions: dict[str, dict[str, str]] = defaultdict(dict)
    for r in conn.execute("SELECT decision_id, fraction, position FROM decision_fraction"):
        positions[r["decision_id"]][r["fraction"]] = r["position"]
    agendas = {r["id"]: r for r in conn.execute("SELECT * FROM agenda_item")}
    blocks = subtops.load(conn)
    subs = subtops.by_id(blocks)
    vindex = vorgang_index(conn)
    known = vorgang_titles(conn)
    own_vorgang = _has_column(conn, "decision", "vorgang_id")

    def vorgaenge(numbers: list[str], *ids: str | None) -> list[str]:
        """The Vorgänge a decision concerns: named by the foundation, or owning one of its Drucksachen."""
        out = {i for i in ids if i in known}
        for x in numbers:
            out |= vindex.get(x, set())
        return sorted(out)

    def agenda(aid: str | None) -> dict | None:
        a = agendas.get(aid)
        if a is None:
            return None
        no_debate = "no_debate" in a.keys() and bool(a["no_debate"])  # noqa: SIM118 (Row `in` tests values)
        return {"id": a["id"], "position": a["position"], "label": top_label(a["top_id"]), "no_debate": no_debate,
                "title": subtops.item_title(a["title"], a["top_id"], no_debate, a["id"] in blocks)}  # fmt: skip

    def roll_call(v: sqlite3.Row) -> dict:
        per = tally[v["id"]]
        return {
            "counts": {c: v[c] for c in ("yes", "no", "abstain", "absent", "invalid")},
            "fractions": {f: {c: t[c] for c in (*VOTE_CHOICES, "absent")} for f, t in per.items()},
            "sources": {"xlsx": v["xlsx_url"], "pdf": v["pdf_url"], "cite": v["source_document_id"]},
        }

    out = []
    linked = set()
    for r in conn.execute(_SQL_DECISION, (WP,)):
        v = rcv.get(r["roll_call_vote_id"])
        numbers = drucksache_numbers(r["drucksache_number"])
        if v is not None:
            linked.add(v["id"])
            numbers += [n for n in drucksache_numbers(v["drucksache_number"]) if n not in numbers]
        a = agenda(r["agenda_item_id"])
        sub = subs.get(r["sub_item_id"]) if subtops.has_decision_sub_item(conn) else None
        vs = vorgaenge(numbers, r["vorgang_id"] if own_vorgang else None, v["vorgang_id"] if v is not None else None)
        d = {
            "id": r["id"], "page": page_id(r["id"]), "kind": r["kind"], "date": r["date"], "sitting": r["sitting_id"],
            "order": r["position"], "agenda": a,
            "sub": {k: sub[k] for k in ("id", "label", "title", "no_debate")} if sub else None,
            "title": decision_title(r["subject"], v["title"] if v else None, r["drucksache_number"], dip,
                                    sub["title"] if sub else a["title"] if a else None),
            "subject": clean_subject(r["subject"]),
            "drucksachen": [drucksache_ref(n, dip) for n in numbers],
            "result": r["result"], "result_from": "protocol",
            "text": r["text"], "protocol": r["protocol"], "cite": r["cite"],
            "counts": None, "fractions": None, "house": None, "sources": None,
            "vorgaenge": vs, "vorgang_titles": {v: known[v] for v in vs}, "href": decision_href(page_id(r["id"]), vs),
        }  # fmt: skip
        if v is not None:
            d.update(roll_call(v))
        elif r["kind"] == "handzeichen":
            d["fractions"] = positions.get(r["id"], {})
            d["house"] = house_on(houses, r["date"])
        out.append(d)
    sittings = {r["id"]: r for r in conn.execute("SELECT id, pdf_url, source_document_id FROM sitting")}
    for v in rcv.values():
        if v["id"] in linked:
            continue
        st = sittings.get(v["sitting_id"])
        a = agenda(v["agenda_item_id"])
        numbers = drucksache_numbers(v["drucksache_number"])
        vs = vorgaenge(numbers, v["vorgang_id"])
        d = {
            "id": v["id"], "page": page_id(v["id"]), "kind": "namentlich", "date": v["date"],
            "sitting": v["sitting_id"] if st else None, "order": 1000 + v["number"], "agenda": a,
            "title": v["title"], "subject": None,
            "drucksachen": [drucksache_ref(n, dip) for n in numbers],
            "result": "angenommen" if v["yes"] > v["no"] else "abgelehnt", "result_from": "counts",
            "text": None, "protocol": st["pdf_url"] if st else None, "cite": st["source_document_id"] if st else None,
            "house": None, "sub": None,
            "vorgaenge": vs, "vorgang_titles": {v: known[v] for v in vs}, "href": decision_href(page_id(v["id"]), vs),
            **roll_call(v),
        }  # fmt: skip
        out.append(d)
    out.sort(key=lambda d: (d["date"], _sitting_number(d["sitting"] or d["id"]), d["order"]), reverse=True)
    return out


def _sitting_number(sid: str) -> int:
    return int(sid.split("/")[1])


def roll_call_members(conn: sqlite3.Connection) -> dict[str, list[list]]:
    """Per roll-call vote, every row of its list: [person id or None, name, fraction, vote]."""
    out: dict[str, list[list]] = defaultdict(list)
    for r in conn.execute("SELECT vote_id, person_id, first_name, last_name, fraction, vote FROM individual_vote"):
        name = f"{r['first_name']} {r['last_name']}".strip()
        out[r["vote_id"]].append([r["person_id"], name, r["fraction"], r["vote"]])
    return out


def top_label(top_id: str | None) -> str:
    """ "Tagesordnungspunkt 22" -> "TOP 22", "Zusatzpunkt 18" -> "ZP 18"."""
    return (top_id or "").replace("Tagesordnungspunkt", "TOP").replace("Zusatzpunkt", "ZP")


def referrals(conn: sqlite3.Connection) -> dict[str, dict]:
    """Per agenda item: whether the chair referred something to the committees, and which Drucksachen. From the
    chair text under the agenda item (foundation `agenda_item_paragraph`); empty without that table."""
    if not has_table(conn, "agenda_item_paragraph"):
        return {}
    out: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT agenda_item_id, text FROM agenda_item_paragraph WHERE kind = 'chair' AND text LIKE '%berwei%' "
        "ORDER BY agenda_item_id, position"
    ):
        m = _REFERRAL.search(r["text"])
        if not m:
            continue
        ref = out.setdefault(r["agenda_item_id"], {"drucksachen": []})
        head = r["text"][m.start() : m.end()].split(" an ")[0]  # the Drucksachen before "an die … Ausschüsse"
        for n in drucksache_numbers(head):
            if n not in ref["drucksachen"]:
                ref["drucksachen"].append(n)
    return out


def iso_week(date: str) -> str:
    y, w, _ = dt.date.fromisoformat(date).isocalendar()
    return f"{y}-W{w:02d}"


def _sql_sitting_speech(conn: sqlite3.Connection) -> str:
    kind_col = "s.kind" if has_speech_kind(conn) else "'rede' AS kind"
    sub_col = "s.sub_item_id" if subtops.has_speech_sub_item(conn) else "NULL AS sub_item_id"
    return f"""
SELECT s.id, s.agenda_item_id, s.person_id, s.speaker_role, s.fraction, s.text, p.party, p.first_name, p.last_name,
       p.academic_title, p.name_prefix, {kind_col}, {sub_col}
FROM speech s JOIN person p ON p.id = s.person_id
WHERE s.sitting_id = ?
ORDER BY s.position
"""


def _vorlagen(conn: sqlite3.Connection) -> dict[tuple[str, str | None], set[str]]:
    """(agenda item id, sub-item id or None) -> Vorgang ids from the foundation's `agenda_item_vorlage`; empty
    without the table (the Drucksache numbers of the item then decide alone)."""
    if not has_table(conn, "agenda_item_vorlage"):
        return {}
    out: dict[tuple[str, str | None], set[str]] = defaultdict(set)
    for r in conn.execute(
        "SELECT agenda_item_id, sub_item_id, vorgang_id FROM agenda_item_vorlage WHERE vorgang_id IS NOT NULL"
    ):
        out[(r["agenda_item_id"], r["sub_item_id"])].add(r["vorgang_id"])
    return out


def sittings(conn: sqlite3.Connection, decided: list[dict] | None = None) -> list[dict]:
    """Every WP 21 sitting, oldest first, with its agenda in order: per agenda item the Drucksachen and the Vorgänge
    they belong to (an item can carry Vorlagen of several), the Reden (owner of each rede, as on the cards; `on_map`
    when it is a point in the Themenlandschaft), the decisions taken under it and what was referred to committees.
    A block item's sub-items carry their own Drucksachen and Vorgänge."""
    decided = decided if decided is not None else decisions(conn)
    by_item: dict[str, list[dict]] = defaultdict(list)
    for d in sorted(decided, key=lambda d: d["order"]):
        if d["agenda"]:
            by_item[d["agenda"]["id"]].append({**d, "sub": d["sub"]["id"] if d.get("sub") else None})
    dip = _dip_index(conn)
    referred = referrals(conn)
    vindex = vorgang_index(conn)
    titles = vorgang_titles(conn)
    vorlagen = _vorlagen(conn)

    def vorgaenge(numbers: list[str], item: str, sub: str | None) -> list[dict]:
        ids = set(vorlagen.get((item, sub), set()))
        for x in numbers:
            ids |= vindex.get(x, set())
        return [{"id": v, "title": titles[v]} for v in sorted(ids) if v in titles]

    photos = (
        {r[0] for r in conn.execute("SELECT person_id FROM person_photo")} if has_table(conn, "person_photo") else set()
    )
    rows = conn.execute("SELECT * FROM sitting WHERE wahlperiode = ? ORDER BY date, number", (WP,)).fetchall()
    sql_speech = _sql_sitting_speech(conn)
    blocks = subtops.load(conn)
    no_debate = subtops.has_item_no_debate(conn)
    out = []
    for i, st in enumerate(rows):
        week = iso_week(st["date"])
        items = {}
        for a in conn.execute("SELECT * FROM agenda_item WHERE sitting_id = ? ORDER BY position", (st["id"],)):
            numbers = json.loads(a["drucksache_numbers"])
            in_subs = {x for sub in blocks.get(a["id"], []) for x in sub["numbers"]}
            items[a["id"]] = {
                "id": a["id"], "position": a["position"], "label": top_label(a["top_id"]),
                "title": subtops.item_title(a["title"], a["top_id"], bool(a["no_debate"]) if no_debate else False,
                                            a["id"] in blocks),
                "no_debate": bool(a["no_debate"]) if no_debate else False,
                "segments": [s.strip() for s in (a["title"] or "").split("|") if s.strip()],
                "drucksachen": [drucksache_ref(n, dip) for n in numbers],
                "vorgaenge": vorgaenge([x for x in numbers if x not in in_subs], a["id"], None),
                "speeches": [], "fragestunde": 0, "decisions": by_item.get(a["id"], []),
                "referred": referred.get(a["id"]),
            }  # fmt: skip
        rede: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for s in conn.execute(sql_speech, (st["id"],)):
            if s["kind"] == "fragestunde":
                # counted apart: a Fragestunde turn is not a Rede (docs/decisions.md)
                if s["agenda_item_id"] in items:
                    items[s["agenda_item_id"]]["fragestunde"] += 1
                continue
            rede[re.sub(r"-\d+$", "", s["id"])].append(s)
        for parts in rede.values():
            first = parts[0]
            item = items.get(first["agenda_item_id"])
            if item is None:
                continue
            own = [p for p in parts if p["person_id"] == first["person_id"]]
            length = len("\n\n".join(p["text"] for p in own))
            item["speeches"].append(
                {"id": first["id"], "person": first["person_id"], "name": display_name(first),
                 "fraction": _fraction(first), "role": first["speaker_role"],
                 "words": sum(len(p["text"].split()) for p in own), "on_map": length >= MIN_CHARS,
                 "photo": first["person_id"] in photos, "sub_item": first["sub_item_id"],
                 "date": st["date"], "sitting": st["id"], "position": item["position"], "title": item["title"],
                 "excerpt": excerpt(own[0]["text"]), "pdf": st["pdf_url"], "cite": st["source_document_id"]}
            )  # fmt: skip
        for item in items.values():
            if item["id"] in blocks:
                item["sub_items"] = [
                    {**sub, "drucksachen": [drucksache_ref(n, dip) for n in sub["numbers"]],
                     "vorgaenge": vorgaenge(sub["numbers"], item["id"], sub["id"])}
                    for sub in blocks[item["id"]]
                ]  # fmt: skip
                subtops.distribute(item)
        out.append(
            {
                "id": st["id"], "page": page_id(st["id"]), "number": st["number"], "date": st["date"],
                "start": st["start_time"], "end": st["end_time"], "pdf": st["pdf_url"], "xml": st["xml_url"],
                "cite": st["source_document_id"], "week": week,
                "prev": page_id(rows[i - 1]["id"]) if i else None,
                "next": page_id(rows[i + 1]["id"]) if i + 1 < len(rows) else None,
                "items": list(items.values()),
            }
        )  # fmt: skip
    return out


def speech_clusters(path: str | os.PathLike | None = None) -> dict[str, dict]:
    """The Themenlandschaft's topic cluster per speech: {speech id: {"week", "cluster_id", "label"}}, from the JSON
    the landscape build writes (`speech_clusters.json`, path in LANDSCAPE_CLUSTERS). Empty when it is not set or
    not there: the sitting pages then leave out "Worum ging es"."""
    path = path or os.environ.get("LANDSCAPE_CLUSTERS")
    if not path or not Path(path).is_file():
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        print(f"{path}: not readable ({err}), sitting pages without topics")
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(sid): c for sid, c in raw.items()
        if isinstance(c, dict) and c.get("week") and c.get("cluster_id") is not None and c.get("label")
    }  # fmt: skip
