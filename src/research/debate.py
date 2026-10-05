"""Debattenkultur: `debatte/index.html`, who speaks how much (in words) and how order is kept in the plenary.

Everything is counted from the protocol text in the foundation's store: speech words from `speech.text` (the
speaker's own paragraphs, without the chair's), the chair's measures and Zwischenfragen from `speech_paragraph`
of kind 'chair', interruptions from `interjection`. The page is written as HTML by Python like the sitting pages;
no member is ranked. German UI, see docs/plan.md."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from research import controls
from research.data import (
    MIN_CHARS,
    NO_FRACTION,
    PARTY_TO_FRACTION,
    WP,
    _houses,
    after_speaker,
    iso_week,
    kind_filter,
    page_id,
)
from research.speeches import rede_id
from research.ui import FOOTER, MONTHS, ORDER, SHORT, TOKEN, dot, e, frac_link, n, shell, short_date
from research.urls import slug as controls_slug

GOVERNMENT = "Bundesregierung"
OTHER = "Sonstige"  # Bundesrat, Wehrbeauftragter: neither fraction nor government
UNCLEAR = "unklar"
_GOV_ROLE = re.compile(r"^(Bundeskanzler|Bundesminister|Staatsminister|Parl\. Staatssekretär)")
_CHAIR_ROLE = re.compile(r"^(Vize)?[Pp]räsident")
AGE_GROUPS = ("unter 40", "40 bis 49", "50 bis 59", "60 und älter")
TERMS = ("erste Wahlperiode", "schon früher im Bundestag")
GENDERS = {"weiblich": "Frauen", "männlich": "Männer"}


def words(text: str | None) -> int:
    return len((text or "").split())


def speaker_group(role: str | None, fraction: str | None) -> str | None:
    """Fraction, the government, or 'Sonstige'; None for the chair, whose words are not a contribution."""
    if role and _CHAIR_ROLE.search(role) and not _GOV_ROLE.search(role):
        return None
    if role and _GOV_ROLE.search(role):
        return GOVERNMENT
    return fraction or OTHER


def age_group(birth: str | None, on: str) -> str | None:
    if not birth or len(birth) < 10:
        return None
    b, d = dt.date.fromisoformat(birth[:10]), dt.date.fromisoformat(on)
    age = d.year - b.year - ((d.month, d.day) < (b.month, b.day))
    return AGE_GROUPS[0] if age < 40 else AGE_GROUPS[1] if age < 50 else AGE_GROUPS[2] if age < 60 else AGE_GROUPS[3]


def group_order(g: str) -> tuple[int, str]:
    order = (*ORDER, GOVERNMENT, OTHER, UNCLEAR)
    return (order.index(g) if g in order else len(order), g)


# ---------------------------------------------------------------- 1. Redeanteile


def _members(conn: sqlite3.Connection) -> dict[str, dict]:
    """Every WP 21 member with fraction, gender, birth date and whether an earlier Wahlperiode had them."""
    earlier = Counter(r[0] for r in conn.execute("SELECT person_id FROM mandate WHERE wahlperiode < ?", (WP,)))
    fraction = {r[0]: r[1] for r in conn.execute(
        "SELECT person_id, name FROM membership WHERE wahlperiode = ? AND kind = 'fraction' ORDER BY from_date",
        (WP,))}  # fmt: skip
    out = {}
    for r in conn.execute(
        """SELECT p.id, p.gender, p.birth_date, p.party, p.last_name, m.to_date FROM mandate m
           JOIN person p ON p.id = m.person_id WHERE m.wahlperiode = ?""",
        (WP,),
    ):
        out[r[0]] = {
            "gender": r[1], "birth": r[2], "last_name": r[4], "current": r[5] is None,
            "fraction": fraction.get(r[0]) or PARTY_TO_FRACTION.get(r[3], r[3]) or NO_FRACTION,
            "term": TERMS[1] if earlier[r[0]] else TERMS[0],
        }  # fmt: skip
    return out


def _speeches(conn: sqlite3.Connection) -> list[dict]:
    return [
        {"id": r[0], "sitting": r[1], "date": r[2], "person": r[3], "group": speaker_group(r[4], r[5]),
         "words": words(r[6])}
        for r in conn.execute(
            f"""SELECT s.id, s.sitting_id, st.date, s.person_id, s.speaker_role, s.fraction, s.text FROM speech s
               JOIN sitting st ON st.id = s.sitting_id WHERE st.wahlperiode = ? {kind_filter(conn)}
               ORDER BY st.date, s.position""",
            (WP,),
        )
    ]  # fmt: skip


def shares(conn: sqlite3.Connection, themes: dict[str, dict] | None = None) -> dict:
    """Words per fraction (against seats), and among members' own speeches by gender, age and first term (against
    the members), the government apart; with `themes` also words per theme and fraction."""
    members = _members(conn)
    speeches = [s for s in _speeches(conn) if s["group"]]
    houses = _houses(conn)
    seats = dict(houses[-1][1]) if houses else dict(Counter(m["fraction"] for m in members.values() if m["current"]))
    last = speeches[-1]["date"] if speeches else dt.date.today().isoformat()
    by_group: Counter = Counter()
    dims: dict[str, Counter] = {"gender": Counter(), "age": Counter(), "term": Counter()}
    base: dict[str, Counter] = {"gender": Counter(), "age": Counter(), "term": Counter()}
    for s in speeches:
        by_group[s["group"]] += s["words"]
        m = members.get(s["person"])
        if s["group"] in (GOVERNMENT, OTHER) or not m:
            continue
        dims["gender"][GENDERS.get(m["gender"], "andere/keine Angabe")] += s["words"]
        dims["age"][age_group(m["birth"], s["date"]) or "ohne Angabe"] += s["words"]
        dims["term"][m["term"]] += s["words"]
    for m in members.values():
        if m["current"]:
            base["gender"][GENDERS.get(m["gender"], "andere/keine Angabe")] += 1
            base["age"][age_group(m["birth"], last) or "ohne Angabe"] += 1
            base["term"][m["term"]] += 1
    by_theme: dict[str, Counter] = defaultdict(Counter)
    for s in speeches:
        t = (themes or {}).get(s["id"])
        if t:
            by_theme[t["label"]][s["group"]] += s["words"]
    return {"words": dict(by_group), "seats": seats, "dims": {k: dict(v) for k, v in dims.items()},
            "base": {k: dict(v) for k, v in base.items()}, "themes": {k: dict(v) for k, v in by_theme.items()},
            "speeches": len(speeches), "from": speeches[0]["date"] if speeches else None, "to": last}  # fmt: skip


def themes(path: str | os.PathLike | None = None) -> dict[str, dict]:
    """The landscape's theme per speech, {speech id: {"theme_id", "label"}} from LANDSCAPE_THEMES; empty when it
    is not set, not there or not readable, and then the page leaves the theme table out."""
    path = path or os.environ.get("LANDSCAPE_THEMES")
    if not path or not Path(path).is_file():
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        print(f"{path}: not readable ({err}), Debattenkultur without themes")
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict) and v.get("label")}


# ---------------------------------------------------------------- 2. Ton und Ordnung

_CHAIR_HEAD = re.compile(r"^(Vize)?[Pp]räsident(in)? .{0,60}:$")  # the chair's name line
_CLAUSE = re.compile(r"[.!?;:,–]+\s*")
# a measure is a sentence in the present tense of the chair: "ich erteile Ihnen einen Ordnungsruf", "Sie bekommen
# einen Ordnungsruf", "ich rüge Sie"; announcements and threats ("sonst erteile ich …", "würde ich …") are not
_MEASURE = (
    ("Ordnungsruf", re.compile(r"\b(erteile|verhänge|bekommen|kriegen|erhält)\b.*\bOrdnungsruf")),
    ("Rüge", re.compile(r"\b(erteile|verhänge)\b.*\bRüge\b|\brüge\b")),
    ("Sitzungsausschluss", re.compile(r"\bschließe\b.*\bvon der (Sitzung|weiteren Teilnahme)|\bSitzungsausschluss\b")),
)
_NOT_YET = re.compile(r"\b(würde|müsste|ansonsten|sonst|wenn|falls|Wiederholungsfall|gleich|nicht|theoretisch|"
                      r"könnte|nächsten Mal)\b", re.I)  # fmt: skip
_NAME = re.compile(r"\b(?:Herrn?|Frau|Abgeordnete[nr]?|Kollegen?|Kollegin)\s+(?:(?:Dr\.|Prof\.)\s+)*"
                   r"(?:[A-ZÄÖÜ][\w-]+\s+)?([A-ZÄÖÜ][\w-]+)")  # fmt: skip


def measures(text: str) -> list[str]:
    """The chair's measures in one paragraph, at most one of each kind (the chair often repeats a measure in the
    same breath: "ich rüge Sie … Dafür rüge ich Sie")."""
    clauses = [c for c in _CLAUSE.split(text) if c]
    return [kind for kind, rx in _MEASURE if any(rx.search(c) and not _NOT_YET.search(c) for c in clauses)]


def name_index(conn: sqlite3.Connection) -> dict[str, str]:
    """Last name → fraction for the WP 21 members whose last name is unique in the house."""
    by_name: dict[str, set[str]] = defaultdict(set)
    for m in _members(conn).values():
        by_name[m["last_name"]].add(m["fraction"])
    return {k: next(iter(v)) for k, v in by_name.items() if len(v) == 1}


_ABOUT = re.compile(r"\b(gegen|über|von|vom|mit)\s+(den\s+|die\s+|der\s+)?$")


def addressee(text: str, names: dict[str, str], about: bool = False) -> str:
    """The one fraction of the members named in `text`, else 'unklar'; a name after "gegen", "über" or "von" is
    someone talked about, not to, and left out unless `about`."""
    found = {names[m[1]] for m in _NAME.finditer(text)
             if m[1] in names and (about or not _ABOUT.search(text[: m.start()]))}  # fmt: skip
    return found.pop() if len(found) == 1 else UNCLEAR


def _paragraphs(conn: sqlite3.Connection):
    return conn.execute(
        """SELECT p.speech_id, p.position, p.kind, p.text, s.sitting_id, st.date, s.fraction, s.speaker_role
           FROM speech_paragraph p JOIN speech s ON s.id = p.speech_id JOIN sitting st ON st.id = s.sitting_id
           WHERE st.wahlperiode = ? ORDER BY st.date, s.sitting_id, s.position, p.position""",
        (WP,),
    ).fetchall()


def _hecklers(conn: sqlite3.Connection) -> dict[tuple[str, int], set[str]]:
    """The fractions of the named Zwischenrufer per comment paragraph: {(speech id, paragraph): {fraction}}."""
    out: dict[tuple[str, int], set[str]] = defaultdict(set)
    for r in conn.execute(
        "SELECT speech_id, paragraph, fraction FROM interjection WHERE actor = 'person' AND kind IN ('zuruf', "
        "'gegenruf') AND fraction IS NOT NULL"
    ):
        out[(r[0], r[1])].add(r[2])
    return out


def order_measures(conn: sqlite3.Connection, rows: list | None = None) -> list[dict]:
    """The chair's measures with the fraction of the person they are for: named in the paragraph; else the one
    fraction of the named Zwischenrufer in the comment right before; else the speaker's own fraction when the
    chair speaks right after the speaker's words; else 'unklar'."""
    rows = rows if rows is not None else _paragraphs(conn)
    names, hecklers = name_index(conn), _hecklers(conn)
    out, seen = [], set()
    for i, r in enumerate(rows):
        if r[2] != "chair":
            continue
        for kind in measures(r[3]):
            key = (r[0], kind, _CLAUSE.sub(" ", r[3]).strip())
            if key in seen:
                continue
            seen.add(key)
            fraction = addressee(r[3], names)
            j = i - 1
            while j >= 0 and rows[j][2] == "chair" and _CHAIR_HEAD.match(rows[j][3].strip()):
                j -= 1
            before = rows[j] if j >= 0 else None
            if fraction == UNCLEAR and before is not None and before[0] == r[0]:
                heard = hecklers.get((before[0], before[1]), set())
                if before[2] == "comment" and len(heard) == 1:
                    fraction = next(iter(heard))
                elif before[2] == "text" and speaker_group(r[7], r[6]) not in (None, OTHER):
                    fraction = speaker_group(r[7], r[6])
            out.append({"kind": kind, "fraction": fraction, "sitting": r[4], "date": r[5], "speech": r[0],
                        "text": r[3]})  # fmt: skip
    return out


_REQUEST = re.compile(r"Zwischenfrage")
_ASK = re.compile(r"\?|Wunsch")
_REFUSED = re.compile(
    r"\b(nein|nee|nö|niemals|verzichte|keine zwischenfragen?|im moment nicht|jetzt nicht|lieber nicht|"
    r"zu ende|fortsetzen|fortfahren|im zusammenhang|machen wir nachher|lassen sie mich)\b",
    re.I,
)
_ALLOWED = re.compile(r"\b(ja|gerne?|bitte|natürlich|selbstverständlich|klar|okay|na gut|absolut|erlaube|zulassen|"
                      r"auch das|dann mach|immer)\b", re.I)  # fmt: skip
_FRACTION_WORDS = (
    ("AfD", re.compile(r"\bAfD")), ("BÜNDNIS 90/DIE GRÜNEN", re.compile(r"Grünen|Bündnis 90", re.I)),
    ("Die Linke", re.compile(r"\bLinke|Linksfraktion")), ("SPD", re.compile(r"\bSPD")),
    ("CDU/CSU", re.compile(r"CDU|CSU|Union")),
)  # fmt: skip


def answer(text: str) -> str:
    """'zugelassen', 'abgelehnt' or 'unklar' from the first words the asked speaker says after the chair's
    question; a no wins over a polite "ja" in the same breath ("Vielen Dank, nein")."""
    head = text.strip()[:150]
    if _REFUSED.search(head):
        return "abgelehnt"
    if _ALLOWED.search(head):
        return "zugelassen"
    return UNCLEAR


def requester(text: str, names: dict[str, str]) -> str:
    hits = {f for f, rx in _FRACTION_WORDS if rx.search(text)}
    if len(hits) == 1:
        return hits.pop()
    return addressee(text, names, about=True) if not hits else UNCLEAR


def interim_questions(conn: sqlite3.Connection, rows: list | None = None) -> list[dict]:
    """Every chair paragraph that asks the speaker to allow a Zwischenfrage, with the answer: the speaker's next
    own paragraph (comments and the chair's name line skipped), or 'zugelassen' when the protocol goes straight on
    with another part of the same rede (the question itself)."""
    rows = rows if rows is not None else _paragraphs(conn)
    names = name_index(conn)
    out = []
    for i, r in enumerate(rows):
        if r[2] != "chair" or not _REQUEST.search(r[3]) or not _ASK.search(r[3]) or "keine Zwischenfrage" in r[3]:
            continue
        result = UNCLEAR
        for nxt in rows[i + 1 : i + 6]:
            if nxt[2] == "comment" or (nxt[2] == "chair" and _CHAIR_HEAD.match(nxt[3].strip())):
                continue
            if nxt[0] != r[0]:
                result = "zugelassen" if nxt[0].split("-")[0] == r[0].split("-")[0] else UNCLEAR
            elif nxt[2] == "text":
                result = answer(nxt[3])
            break
        out.append({"result": result, "asked": speaker_group(r[7], r[6]) or OTHER,
                    "by": requester(r[3], names), "sitting": r[4], "date": r[5]})  # fmt: skip
    return out


INTERRUPTIONS = ("zuruf", "unruhe", "widerspruch", "lachen")


def interruptions(conn: sqlite3.Connection) -> dict[str, dict[str, list[int]]]:
    """{month: {speaker group: [interruptions, words]}}: Zurufe, Unruhe, Widerspruch and Lachen aimed at the
    speaker (no other addressee named) from outside the speaker's own fraction, after the speaker's own words."""
    out: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for s in _speeches(conn):
        if s["group"]:
            out[s["date"][:7]][s["group"]][1] += s["words"]
    marks = ",".join("?" * len(INTERRUPTIONS))
    heard = after_speaker(conn)
    for r in conn.execute(
        f"""SELECT st.date, s.speaker_role, s.fraction, i.fraction, i.speech_id, i.paragraph FROM interjection i
            JOIN speech s ON s.id = i.speech_id JOIN sitting st ON st.id = s.sitting_id
            WHERE st.wahlperiode = ? AND i.kind IN ({marks}) AND i.to_person_id IS NULL {kind_filter(conn)}""",
        (WP, *INTERRUPTIONS),
    ):
        g = speaker_group(r[1], r[2])
        if g and (r[4], r[5]) in heard and not (r[3] and r[3] == r[2]):
            out[r[0][:7]][g][0] += 1
    return {m: dict(v) for m, v in sorted(out.items())}


# ---------------------------------------------------------------- 3. Beifall und Zurufe zwischen den Fraktionen


def network(conn: sqlite3.Connection) -> dict:
    """Who applauds and heckles during whose speeches. For every pair (A, B): the share of B's Reden (at least
    MIN_CHARS) during which the protocol notes applause of the whole fraction A ("fraction"), of some of its members
    ("members") or a Zuruf from A ("zuruf"); B is the speaker's fraction or the government. "months": per month
    the applause notes (whole fraction or some members) and how many of them cross a fraction line."""
    speeches = {}
    for r in conn.execute(
        f"""SELECT s.id, st.date, s.speaker_role, s.fraction, length(s.text) FROM speech s
           JOIN sitting st ON st.id = s.sitting_id WHERE st.wahlperiode = ? {kind_filter(conn)}""",
        (WP,),
    ):
        g = speaker_group(r[2], r[3])
        if g and g != OTHER and r[4] >= MIN_CHARS:
            speeches[r[0]] = (g, r[1][:7])
    count = Counter(g for g, _ in speeches.values())
    hits: dict[str, set[tuple[str, str, str]]] = {"fraction": set(), "members": set(), "zuruf": set()}
    months: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    heard, skipped = after_speaker(conn), 0
    for r in conn.execute(
        """SELECT speech_id, kind, actor, fraction, paragraph FROM interjection
           WHERE kind IN ('beifall', 'zuruf') AND to_person_id IS NULL AND fraction IS NOT NULL"""
    ):
        if r[0] not in speeches:
            continue
        if (r[0], r[4]) not in heard:
            skipped += 1
            continue
        g, month = speeches[r[0]]
        if r[1] == "zuruf":
            hits["zuruf"].add((r[3], g, r[0]))
        elif r[2] in ("fraction", "members"):
            hits[r[2]].add((r[3], g, r[0]))
            if g != GOVERNMENT:
                months[month][0] += 1
                months[month][1] += r[3] != g
    share = {
        k: {(a, b): c / count[b] for (a, b), c in Counter((a, b) for a, b, _ in v).items()} for k, v in hits.items()
    }
    return {"speeches": dict(count), "share": share, "months": dict(sorted(months.items())), "skipped": skipped}


# ---------------------------------------------------------------- rendering


def pct(x: float) -> str:
    return f"{100 * x:.1f} %".replace(".", ",")


def label(g: str) -> str:
    return SHORT.get(g, g)


def short_label(g: str) -> str:
    return {GOVERNMENT: "Regierung", NO_FRACTION: "fraktionsl."}.get(g, label(g))


def colour(g: str) -> str:
    return f"var(--{TOKEN[g]})" if g in TOKEN else "var(--reg)" if g == GOVERNMENT else "var(--faint)"


def share_rows(have: dict[str, int], base: dict[str, int], keys: list[str], unit: str, base_unit: str) -> str:
    """One row per group: its share of the words as a bar, its share of the base as a tick on the same scale."""
    total, total_base = sum(have.values()) or 1, sum(base.values()) or 1
    top = max([have.get(k, 0) / total for k in keys] + [base.get(k, 0) / total_base for k in keys] + [0.01])
    rows = []
    for k in keys:
        w, b = have.get(k, 0) / total, base.get(k, 0) / total_base
        tick = (f'<i class="tick" style="left:{100 * b / top:.2f}%" title="{e(base_unit)}: {pct(b)}"></i>'
                if k in base else "")  # fmt: skip
        rows.append(
            f'<tr><td>{dot(k) if k in TOKEN else ""}{frac_link(k)}</td><td class="bars"><span class="sh">'
            f'<i style="width:{100 * w / top:.2f}%;background:{colour(k)}"></i>{tick}</span></td>'
            f"<td>{pct(w)}</td><td>{pct(b) if k in base else '–'}</td></tr>"
        )
    return (f'<div class="scroll"><table class="plenum deb"><thead><tr><th></th><th></th><th>{e(unit)}</th>'
            f"<th>{e(base_unit)}</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>")  # fmt: skip


def section_shares(s: dict) -> str:
    groups = sorted(s["words"], key=group_order)
    total = sum(s["words"].values())
    fractions = [g for g in groups if g not in (GOVERNMENT, OTHER)]
    parl = {g: s["words"][g] for g in fractions}
    out = [
        '<section id="redeanteile"><h2>Redeanteile</h2>',
        '<p class="note"><b>Gemessen in Wörtern, da das Protokoll keine Redezeit festhält.</b> '
        "Gezählt sind die Wörter jedes Beitrags im Plenarprotokoll ohne die Worte der Sitzungsleitung. "
        f"{n(total)} Wörter in {n(s['speeches'])} Beiträgen vom {e(short_date(s['from'] or s['to']))} bis "
        f"{e(short_date(s['to']))}, einschließlich Reden, Zwischenfragen, Kurzinterventionen und "
        f"Regierungsbefragung.</p>",
        "<h3>Fraktionen: Anteil an den Wörtern und an den Sitzen</h3>",
        share_rows(parl, s["seats"], fractions, "Wörter", "Sitze"),
        '<p class="how">Wörter der Abgeordneten nach ihrer Fraktion im Protokoll, ohne Regierungsmitglieder. '
        "Der Strich zeigt den Sitzanteil laut der letzten namentlichen Abstimmung. Redezeit wird im Ältestenrat "
        "nach Fraktionsstärke verteilt. Unterschiede entstehen etwa durch Zwischenfragen, Kurzinterventionen und "
        "unterschiedlich schnelles Sprechen.</p>",
    ]
    gov, other = s["words"].get(GOVERNMENT, 0), s["words"].get(OTHER, 0)
    out.append(
        f'<p class="how"><span class="dot" style="background:var(--reg)"></span> <b>Bundesregierung</b>: '
        f"{n(gov)} Wörter, {pct(gov / (total or 1))} aller Wörter, getrennt von den Fraktionen gezählt "
        "(Bundeskanzler, Ministerinnen und Minister, Staatsminister, Parlamentarische Staatssekretäre, wenn das "
        f"Protokoll sie in dieser Rolle nennt). Sonstige (Bundesrat, Wehrbeauftragter): {n(other)} Wörter.</p>"
    )
    dims = (("gender", "Nach Geschlecht", list(GENDERS.values()) + ["andere/keine Angabe"]),
            ("age", "Nach Alter am Tag der Rede", [*AGE_GROUPS, "ohne Angabe"]),
            ("term", "Erste Wahlperiode oder schon früher im Bundestag", list(TERMS)))  # fmt: skip
    for key, title, keys in dims:
        keys = [k for k in keys if s["dims"][key].get(k) or s["base"][key].get(k)]
        out += [f"<h3>{e(title)}</h3>", share_rows(s["dims"][key], s["base"][key], keys, "Wörter", "Abgeordnete")]
    out.append(
        '<p class="how">Nur Beiträge von Abgeordneten, ohne Regierungsrolle. Vergleich mit allen Abgeordneten, die '
        "heute ein Mandat haben (Alter am Tag der letzten Sitzung). „Schon früher im Bundestag“ heißt: ein Mandat "
        "in einer früheren Wahlperiode laut Stammdaten. Geschlecht wie in den Stammdaten angegeben.</p>"
    )
    if s["themes"]:
        out.append(theme_table(s["themes"]))
    out.append("</section>")
    return "".join(out)


def theme_table(by_theme: dict[str, dict[str, int]], limit: int = 25) -> str:
    rows = []
    top = sorted(by_theme.items(), key=lambda kv: -sum(kv[1].values()))[:limit]
    for name, per in top:
        total = sum(per.values()) or 1
        segs = "".join(f'<i style="width:{100 * v / total:.2f}%;background:{colour(g)}" title="{e(label(g))}: '
                       f'{pct(v / total)}"></i>'
                       for g, v in sorted(per.items(), key=lambda kv: group_order(kv[0])))  # fmt: skip
        rows.append(f'<tr><td class="wrap">{e(name)}</td><td class="bars"><span class="stack">{segs}</span></td>'
                    f"<td>{n(sum(per.values()))}</td></tr>")  # fmt: skip
    return (
        '<h3>Nach Thema</h3><p class="how">Themen aus der Themenlandschaft, die meistbesprochenen zuerst; der '
        "Balken teilt die Wörter eines Themas auf Fraktionen und Bundesregierung auf. Die Themen sind maschinell "
        "gebildet und nicht amtlich.</p>"
        '<div class="scroll"><table class="plenum deb"><thead><tr><th>Thema</th><th></th><th>Wörter</th></tr>'
        "</thead><tbody>"
        f"{''.join(rows)}</tbody></table></div>"
    )


def sitting_link(sid: str, date: str) -> str:
    return f'<a href="../sitzungen/{e(page_id(sid))}.html">{e(short_date(date))}</a>'


ORDER_KINDS = ("Ordnungsruf", "Rüge", "Sitzungsausschluss")
ORDER_PLURAL = {"Ordnungsruf": "Ordnungsrufe", "Rüge": "Rügen", "Sitzungsausschluss": "Sitzungsausschlüsse"}
QUESTION_RESULTS = ("zugelassen", "abgelehnt", UNCLEAR)
MIN_WORDS = 2000  # a month of a fraction with fewer words gets no interruption rate


def token(g: str) -> str:
    """A group as a filter value: the fraction's token, "reg" for the Bundesregierung, else its slug."""
    return TOKEN.get(g) or ("reg" if g == GOVERNMENT else re.sub(r"[^a-z0-9]+", "-", g.lower()).strip("-"))


def dec(x: float) -> str:
    """12.34 -> "12,3"."""
    return f"{x:.1f}".replace(".", ",")


def rates(ints: dict[str, dict[str, list[int]]]) -> dict[str, dict[str, float]]:
    """Interruptions per 1,000 words, per month and group, for the months with at least MIN_WORDS words."""
    groups = {g for per in ints.values() for g in per if g != OTHER}
    return {m: {g: 1000 * per[g][0] / per[g][1] for g in groups if g in per and per[g][1] >= MIN_WORDS}
            for m, per in ints.items()}  # fmt: skip


def multiples(ms: list[dict], qs: list[dict], ints: dict[str, dict[str, list[int]]]) -> str:
    """Small multiples, one card per fraction (and the Bundesregierung): its Ordnungsmaßnahmen, the Zwischenfragen
    put to it as a bar (zugelassen, abgelehnt, unklar), and its interruptions per 1,000 words as a column per month,
    on one scale for all cards. A card filters the list of Ordnungsmaßnahmen below."""
    per_measure: dict[str, Counter] = defaultdict(Counter)
    for m in ms:
        per_measure[m["fraction"]][m["kind"]] += 1
    per_q: dict[str, Counter] = defaultdict(Counter)
    for q in qs:
        per_q[q["asked"]][q["result"]] += 1
    rate = rates(ints)
    months = sorted(rate)
    top = max([v for r in rate.values() for v in r.values()] + [1])
    groups = sorted({*per_measure, *per_q, *(g for r in rate.values() for g in r)} - {OTHER, UNCLEAR}, key=group_order)
    shades = {"zugelassen": "k2", "abgelehnt": "k4", UNCLEAR: "k5"}
    cards = []
    for g in groups:
        c, qc = per_measure[g], per_q[g]
        measures = " · ".join(f"{c[k]} {ORDER_PLURAL[k] if c[k] != 1 else k}" for k in ORDER_KINDS if c[k]) or "keine"
        asked = sum(qc.values())
        qbar = "".join(f'<i class="{shades[r]}" style="flex-grow:{qc[r]}" title="{r}: {qc[r]}"></i>'
                       for r in QUESTION_RESULTS if qc[r])  # fmt: skip
        qtext = (f"{n(asked)} gewünscht: " + " · ".join(f"{qc[r]} {r}" for r in QUESTION_RESULTS if qc[r])
                 if asked else "keine gewünscht")  # fmt: skip
        cols = "".join(
            f'<i style="height:{100 * rate[m][g] / top:.1f}%" title="{e(month_label(m))}: {dec(rate[m][g])}"></i>'
            if g in rate[m] else f'<i class="gap" title="{e(month_label(m))}: zu wenige Wörter"></i>'
            for m in months
        )  # fmt: skip
        vals = [rate[m][g] for m in months if g in rate[m]]
        mean = dec(sum(vals) / len(vals)) if vals else "–"
        inner = (
            f'<span class="mh"><i class="dot" style="background:{colour(g)}"></i>{e(label(g))}</span>'
            f'<span class="mk">Ordnungsmaßnahmen</span><span class="mv">{measures}</span>'
            f'<span class="mk">Zwischenfragen an die {"Bundesregierung" if g == GOVERNMENT else "Fraktion"}</span>'
            f'<span class="qb">{qbar}</span><span class="mv">{qtext}</span>'
            f'<span class="mk">Unterbrechungen je 1.000 Wörter</span><span class="spark">{cols}</span>'
            f'<span class="mv">im Mittel der Monate {mean}</span>'
        )
        cards.append(controls.toggle("fraktion", token(g), inner, cls="mult", label=label(g)))
    legend = ('<div class="legend"><span><i class="sw k2"></i>zugelassen</span><span><i class="sw k4"></i>abgelehnt'
              '</span><span><i class="sw k5"></i>unklar</span></div>')  # fmt: skip
    span = f"{month_label(months[0])} bis {month_label(months[-1])}" if months else ""
    return (
        f'{legend}<div class="mults" role="group" aria-label="Je Fraktion">{"".join(cards)}</div>'
        f'<p class="note">Die Säulen: je ein Monat, {e(span)}, alle Karten auf derselben Skala (höchster Wert '
        f"{dec(top)}). Ein Klick auf eine Karte zeigt unten ihre Ordnungsmaßnahmen.</p>"
    )


def measures_table(ms: list[dict]) -> str:
    per: dict[str, Counter] = defaultdict(Counter)
    for m in ms:
        per[m["fraction"]][m["kind"]] += 1
    head = "".join(f"<th>{ORDER_PLURAL[k]}</th>" for k in ORDER_KINDS)
    rows = "".join(
        f"<tr><td>{dot(f) if f in TOKEN else ''}{frac_link(f)}</td>" + "".join(f"<td>{per[f][k]}</td>"
                                                                             for k in ORDER_KINDS) + "</tr>"
        for f in sorted(per, key=group_order)
    )  # fmt: skip
    return (
        '<h3>Ordnungsrufe, Rügen, Sitzungsausschlüsse</h3><div class="scroll"><table class="plenum deb"><thead><tr>'
        f"<th>Fraktion der betroffenen Person</th>{head}</tr></thead><tbody>{rows}</tbody></table></div>"
    )


def section_order(ms: list[dict], qs: list[dict], ints: dict[str, dict[str, list[int]]],
                  sitting_dates: list[str] | None = None) -> str:  # fmt: skip
    items = "".join(
        f'<li class="mrow" data-fraktion="{e(token(m["fraction"]))}" data-art="{e(controls_slug(m["kind"]))}" '
        f'data-w="{iso_week(m["date"])}"><span class="d">{sitting_link(m["sitting"], m["date"])}</span> '
        f"<b>{e(m['kind'])}</b> · {dot(m['fraction']) if m['fraction'] in TOKEN else ''}{e(label(m['fraction']))}"
        f'<div class="q">„{e(m["text"][:280])}{"…" if len(m["text"]) > 280 else ""}“ '
        f'<a href="../reden/{e(page_id(rede_id(m["speech"])))}.html#{e(m["speech"])}">in der Rede →</a></div></li>'
        for m in reversed(ms)
    )
    unclear = sum(1 for m in ms if m["fraction"] == UNCLEAR)
    q_unclear = sum(1 for q in qs if q["result"] == UNCLEAR)
    kinds = Counter(m["kind"] for m in ms)
    fractions = Counter(m["fraction"] for m in ms)
    groups = sorted(fractions, key=group_order)
    art = [(controls_slug(k), k, kinds[k], "accent") for k in ORDER_KINDS]
    chips = controls.block("Art", controls.chips("art", art, "Art der Maßnahme"))
    chips += controls.block("Fraktion der betroffenen Person", controls.chips(
        "fraktion", [(token(g), label(g), fractions[g], token(g) if g in TOKEN or g == GOVERNMENT else "sonstige")
                     for g in groups], "Fraktion der betroffenen Person"))  # fmt: skip
    listing = (
        f'<div class="count" data-count></div><div class="rows" data-rows data-row="li.mrow" '
        f'data-limit="{controls.LIMIT}"><ul class="ms">{items}</ul>'
        '<div class="empty" data-none hidden>Keine Treffer für diese Auswahl.</div>'
        '<button type="button" class="more" data-more hidden>mehr anzeigen</button></div>'
        if items
        else '<div class="rows"><div class="empty">Keine Ordnungsmaßnahmen im Datenbestand.</div></div>'
    )
    tables = measures_table(ms) + questions_table(qs) + interruptions_table(ints)
    body = (
        '<h2>Ton und Ordnung</h2>'
        + controls.view("je-fraktion", "Je Fraktion: Ordnungsmaßnahmen, Zwischenfragen, Unterbrechungen",
                        multiples(ms, qs, ints), tables)
        + '<p class="how"><b>Ordnungsmaßnahmen</b> sind aus den Worten der Sitzungsleitung gelesen: gezählt ist ein '
        "Satz wie „Ich erteile Ihnen einen Ordnungsruf“ oder „ich rüge Sie“, nicht eine Ankündigung oder Drohung "
        "(„sonst erteile ich …“, „im Wiederholungsfall …“). Die Fraktion ist die der Person, die die Sitzungsleitung "
        "im selben Absatz beim Namen nennt, sonst die des namentlich vermerkten Zwischenrufers direkt davor, oder die "
        "der Rednerin oder des Redners, wenn die Sitzungsleitung direkt nach deren Worten spricht. Ohne solchen "
        f"Anhalt steht „unklar“ ({unclear} von {len(ms)}). Die Regeln lesen Text und können einzelne Fälle "
        "übersehen, etwa nachträglich erteilte Ordnungsrufe in anderer Formulierung.</p>"
        '<p class="how"><b>Zwischenfragen:</b> Ein Wunsch ist ein Satz der Sitzungsleitung wie „Gestatten Sie eine '
        "Zwischenfrage …?“. Die Antwort ist der nächste eigene Absatz der gefragten Person („Ja, gerne.“ / „Nein, "
        "danke.“). Folgt direkt der Beitrag der fragenden Person, gilt die Frage als zugelassen. Nicht einordnen "
        f"ließen sich {q_unclear} von {len(qs)} Wünschen ({pct(q_unclear / (len(qs) or 1))}), etwa wenn die Antwort "
        "im Redefluss steht. Regierungsmitglieder zählen als Bundesregierung.</p>"
        '<p class="how"><b>Unterbrechungen:</b> Zurufe, Unruhe, Widerspruch und Lachen, die das Protokoll während '
        "eines Beitrags vermerkt, je 1.000 Wörter der Beiträge dieser Fraktion im Monat. Zurufe aus der eigenen "
        "Fraktion und Zurufe an eine andere genannte Person nicht mitgezählt, ebenso Vermerke direkt nach Worten der "
        "Sitzungsleitung. Das Protokoll hält fest, was die Stenografie hört. Ein Zuruf kann Kritik, Ergänzung oder "
        f"Zustimmung sein. Monate mit weniger als {n(MIN_WORDS)} Wörtern einer Fraktion bleiben leer.</p>"
        + "<h3>Die Ordnungsmaßnahmen mit Datum und Wortlaut</h3>"
        + (controls.toolbar("Wörter im Wortlaut …") + chips
           + controls.activity([m["date"] for m in ms], sitting_dates or [], "Ordnungsmaßnahmen", "Ordnungsmaßnahme")
           if ms else "")
        + listing
    )  # fmt: skip
    return f'<section id="ordnung">{controls.scope(body, "Ordnungsmaßnahmen", "Ordnungsmaßnahme")}</section>'


def questions_table(qs: list[dict]) -> str:
    by: dict[str, Counter] = defaultdict(Counter)
    for q in qs:
        by[q["asked"]][q["result"]] += 1
        by["alle"][q["result"]] += 1
    keys = ["alle", *sorted((k for k in by if k != "alle"), key=group_order)]
    rows = "".join(
        f"<tr><td>{dot(k) if k in TOKEN else ''}{e(label(k)) if k != 'alle' else '<b>alle</b>'}</td>"
        f"<td>{sum(by[k].values())}</td>"
        + "".join(f"<td>{by[k][r]} <span class=\"faint\">{pct(by[k][r] / (sum(by[k].values()) or 1))}</span></td>"
                  for r in QUESTION_RESULTS)
        + "</tr>"
        for k in keys
    )  # fmt: skip
    return (
        "<h3>Zwischenfragen</h3>"
        '<div class="scroll"><table class="plenum deb"><thead><tr><th>Gefragt wurde</th><th>gewünscht</th>'
        f"<th>zugelassen</th><th>abgelehnt</th><th>unklar</th></tr></thead><tbody>{rows}</tbody></table></div>"
    )


def interruptions_table(ints: dict[str, dict[str, list[int]]]) -> str:
    rate = rates(ints)
    groups = sorted({g for r in rate.values() for g in r}, key=group_order)
    head = "".join(f"<th>{dot(g) if g in TOKEN else ''}{e(label(g))}</th>" for g in groups)

    def cell(m: str, g: str) -> str:
        if g not in rate[m]:
            return '<td class="faint">–</td>'
        shown = dec(rate[m][g])
        return f'<td title="{ints[m][g][0]} Unterbrechungen, {n(ints[m][g][1])} Wörter">{shown}</td>'

    rows = "".join(f"<tr><td>{e(month_label(m))}</td>{''.join(cell(m, g) for g in groups)}</tr>" for m in rate)
    return (
        "<h3>Unterbrechungen je 1.000 Wörter</h3>"
        f'<div class="scroll"><table class="plenum deb heat"><thead><tr><th>Monat</th>{head}</tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def heatmap(share: dict[tuple[str, str], float], actors: list[str], speakers: list[str], title: str) -> str:
    """Actor fraction (rows) × speaker (columns) as an SVG grid, the share written in each cell."""
    cw, ch, left, top = 64, 34, 92, 40
    w, h = left + cw * len(speakers), top + ch * len(actors)
    cells = []
    for j, b in enumerate(speakers):
        cells.append(f'<text x="{left + cw * j + cw / 2}" y="{top - 10}" class="hl">{e(short_label(b))}</text>')
    for i, a in enumerate(actors):
        cells.append(f'<text x="{left - 8}" y="{top + ch * i + ch / 2 + 4}" class="vl">{e(short_label(a))}</text>')
        for j, b in enumerate(speakers):
            v = share.get((a, b), 0.0)
            x, y = left + cw * j, top + ch * i
            ink = "#fff" if v > 0.55 else "var(--text)"
            cells.append(
                f"<g><title>{e(label(a))} während Reden von {e(label(b))}: {pct(v)}</title>"
                f'<rect x="{x + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="3" '
                f'style="fill:var(--accent);fill-opacity:{0.06 + 0.9 * v:.3f}"></rect>'
                f'<text x="{x + cw / 2}" y="{y + ch / 2 + 4}" style="fill:{ink}">{round(100 * v)}</text></g>'
            )
    return (f'<figure class="heat"><svg viewBox="0 0 {w} {h}" role="img" aria-label="{e(title)}">'
            f'{"".join(cells)}</svg><figcaption>{e(title)}</figcaption></figure>')  # fmt: skip


def line_chart(points: list[tuple[str, float]], label_y: str) -> str:
    """A small SVG line of monthly shares, 0 to 100 %."""
    if len(points) < 2:
        return ""
    w, h, left, bottom = 640, 180, 36, 26
    step = (w - left - 10) / (len(points) - 1)

    def xy(i: int, v: float) -> tuple[float, float]:
        return left + step * i, 10 + (h - bottom - 10) * (1 - v)

    grid = "".join(f'<line x1="{left}" x2="{w - 10}" y1="{xy(0, g)[1]:.1f}" y2="{xy(0, g)[1]:.1f}" class="g"/>'
                   f'<text x="{left - 6}" y="{xy(0, g)[1] + 4:.1f}" class="vl">{round(100 * g)}</text>'
                   for g in (0, 0.25, 0.5, 0.75, 1))  # fmt: skip
    path = " ".join(f"{'M' if i == 0 else 'L'}{xy(i, v)[0]:.1f},{xy(i, v)[1]:.1f}" for i, (_, v) in enumerate(points))
    dots = "".join(f'<circle cx="{xy(i, v)[0]:.1f}" cy="{xy(i, v)[1]:.1f}" r="3"><title>{e(month_label(m))}: '
                   f"{pct(v)}</title></circle>" for i, (m, v) in enumerate(points))  # fmt: skip
    ticks = "".join(f'<text x="{xy(i, 0)[0]:.1f}" y="{h - 6}" class="hl">{e(month_label(m, short=True))}</text>'
                    for i, (m, _) in enumerate(points) if i % max(1, len(points) // 8) == 0)  # fmt: skip
    return (f'<figure class="line"><svg viewBox="0 0 {w} {h}" role="img" aria-label="{e(label_y)}">{grid}'
            f'<path d="{path}"/>{dots}{ticks}</svg><figcaption>{e(label_y)}</figcaption></figure>')  # fmt: skip


def month_label(m: str, short: bool = False) -> str:
    name = MONTHS[int(m[5:]) - 1]
    return f"{name[:3]} {m[2:4]}" if short else f"{name} {m[:4]}"


def section_network(net: dict) -> str:
    speakers = sorted((g for g, c in net["speeches"].items() if c >= 20), key=group_order)
    actors = [
        g
        for g in speakers
        if g != GOVERNMENT and any(v for k in net["share"].values() for (a, _), v in k.items() if a == g)
    ]
    points = [(m, c / t) for m, (t, c) in net["months"].items() if t >= 500]
    return (
        '<section id="netz"><h2>Beifall und Zurufe zwischen den Fraktionen</h2>'
        '<p class="how">Jede Zelle: in wie viel Prozent der Reden der Spalte (Fraktion oder Bundesregierung der '
        "redenden Person) das Protokoll mindestens einmal Beifall oder einen Zuruf der Zeile vermerkt. Gezählt "
        f"sind Reden ab {MIN_CHARS} Zeichen; Spalten mit weniger als 20 Reden fehlen. Das Protokoll hält fest, "
        "<em>wann</em> Beifall fällt, nicht <em>wem</em> er gilt. Deshalb zählt nur, was direkt auf die eigenen "
        "Worte der redenden Person folgt. Vermerke nach Worten der Sitzungsleitung bleiben außen vor "
        f"({n(net['skipped'])} Vermerke): Beifall nach „Nächster Redner ist …“ begrüßt meist die nächste Person am "
        "Pult, Beifall nach einem Ordnungsruf gilt dem Präsidium. Eine Zwischenfrage ist ein eigener Beitrag; "
        "Reaktionen darin zählen für die fragende Person. Beifall kann trotzdem einem Zwischenruf gelten. Die "
        "Zahlen beschreiben also Reaktionen während einer Rede, keine Zustimmung zu ihr.</p>"
        + heatmap(
            net["share"]["fraction"],
            actors,
            speakers,
            "Beifall der ganzen Fraktion (Zeile) während Reden der Spalte, in %",
        )
        + heatmap(
            net["share"]["members"],
            actors,
            speakers,
            "Beifall von Teilen der Fraktion (Zeile, „bei Abgeordneten der …“), in %",
        )
        + heatmap(
            net["share"]["zuruf"], actors, speakers, "Zurufe aus der Fraktion (Zeile) während Reden der Spalte, in %"
        )
        + "<h3>Beifall über Fraktionsgrenzen, je Monat</h3>"
        + line_chart(points, "Anteil der Beifallsvermerke aus anderen Fraktionen als der der redenden Person, in %")
        + '<p class="how">Alle Beifallsvermerke (ganze Fraktion oder Teile) während Reden von Abgeordneten; der '
        "Anteil, der aus einer anderen Fraktion kommt als der redenden. Ein höherer Wert heißt, dass im Monat "
        "häufiger über Fraktionsgrenzen hinweg geklatscht wurde; er hängt auch von den Themen des Monats ab und "
        "davon, wer wie oft redet. Monate mit weniger als 500 Vermerken fehlen.</p></section>"
    )


HEAD = """<style>
.p-debate h2 { font-size: 20px; margin: 36px 0 8px; }
.p-debate h3 { font-size: 15px; margin: 22px 0 8px; }
.p-debate .note { background: var(--accent-soft); border-radius: 8px; padding: 10px 12px; font-size: 14px; }
.p-debate .how { color: var(--muted); font-size: 13px; max-width: 680px; }
table.deb td.bars { width: 45%; }
table.deb .sh, table.deb .stack { position: relative; display: flex; height: 12px; background: var(--bg);
  border-radius: 3px; overflow: visible; }
table.deb .stack { overflow: hidden; }
table.deb .sh i, table.deb .stack i { display: block; height: 100%; }
table.deb .sh .tick { position: absolute; top: -3px; width: 2px; height: 18px; background: var(--text); }
table.deb td { white-space: nowrap; }
table.deb td.wrap { white-space: normal; min-width: 140px; }
.p-debate .scroll { overflow-x: auto; }
table.heat td { font-variant-numeric: tabular-nums; }
details.deb summary { cursor: pointer; color: var(--accent); font-size: 14px; margin: 6px 0; }
ul.ms { list-style: none; padding: 0; font-size: 13px; }
ul.ms li { padding: 8px 0; border-top: 1px solid var(--line); }
ul.ms .q { color: var(--muted); margin-top: 3px; }
.p-debate figure { margin: 12px 0 20px; }
.p-debate figure svg { width: 100%; height: auto; font-size: 12px; }
.p-debate figure text { fill: var(--text); text-anchor: middle; }
.p-debate figure text.vl { text-anchor: end; fill: var(--muted); }
.p-debate figure text.hl { fill: var(--muted); }
.p-debate figure.heat svg { max-width: 560px; }
.p-debate figure.line path { fill: none; stroke: var(--accent); stroke-width: 2; }
.p-debate figure.line circle { fill: var(--accent); }
.p-debate figure.line line.g { stroke: var(--line); }
.p-debate figcaption { font-size: 13px; color: var(--muted); }
.mults { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 8px; }
.mult { display: flex; flex-direction: column; align-items: stretch; gap: 2px; text-align: left;
  border: 1px solid var(--line); border-radius: 10px; background: var(--card); padding: 10px 12px 12px;
  font-size: 13px; }
.mult:hover { border-color: var(--k3); }
.mult[aria-pressed=true] { border-color: var(--accent); background: var(--accent-soft); }
.mult .mh { display: flex; align-items: center; gap: 7px; font-weight: 600; font-size: 14px; margin-bottom: 4px; }
.mult .mk { font-size: 10.5px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: var(--faint);
  margin-top: 6px; }
.mult .mv { color: var(--muted); font-size: 12.5px; font-variant-numeric: tabular-nums; }
.mult .qb { display: flex; gap: 1px; height: 10px; border-radius: 3px; overflow: hidden; background: var(--bg); }
.mult .qb i { display: block; height: 100%; }
.mult .spark { display: flex; align-items: flex-end; gap: 1px; height: 40px; border-bottom: 1px solid var(--line); }
.mult .spark i { flex: 1; display: block; background: var(--k2); min-height: 1px; }
.mult .spark i.gap { background: transparent; }
ul.ms li[hidden] { display: none; }
@media (max-width: 560px) {
  table.deb td.bars { width: 30%; } table.plenum.deb td, table.plenum.deb th { padding: 7px 6px; }
}
</style>"""


def page(s: dict, ms: list[dict], qs: list[dict], ints: dict, net: dict | None = None,
         sitting_dates: list[str] | None = None) -> str:  # fmt: skip
    body = (
        '<h1>Debattenkultur</h1><p class="lead">Redeanteile, Ordnungsmaßnahmen und Reaktionen im 21. Bundestag, '
        "gezählt aus den Plenarprotokollen. Die Seite vergleicht Gruppen und keine einzelnen Abgeordneten. Jede Zahl "
        "beruht auf dem Protokolltext, die Ordnungsmaßnahmen sind mit ihrer Sitzung "
        'verlinkt.</p><p class="jump"><a href="#redeanteile">Redeanteile</a> · <a href="#ordnung">Ton und '
        'Ordnung</a> · <a href="#netz">Beifall und Zurufe</a></p>'
        f"{section_shares(s)}{section_order(ms, qs, ints, sitting_dates)}{section_network(net) if net else ''}"
        f"<footer>{FOOTER}</footer>"
    )
    return shell(root="../", kind="p-debate", active="debate", title="Debattenkultur im Bundestag",
                 desc="Redeanteile in Wörtern, Ordnungsrufe, Zwischenfragen und Unterbrechungen im 21. Deutschen "
                      "Bundestag, aus den Plenarprotokollen.",
                 body=body, data={"kind": "debate"}, head=HEAD + controls.head("../"))  # fmt: skip


def write(conn: sqlite3.Connection, out: Path) -> dict[str, int]:
    """Write `debatte/index.html`; returns the page count for the build log."""
    rows = _paragraphs(conn)
    s = shares(conn, themes())
    if not s["speeches"]:
        return {}
    d = out / "debatte"
    d.mkdir(parents=True, exist_ok=True)
    days = [r[0] for r in conn.execute("SELECT date FROM sitting WHERE wahlperiode = ? ORDER BY date", (WP,))]
    (d / "index.html").write_text(
        page(s, order_measures(conn, rows), interim_questions(conn, rows), interruptions(conn), network(conn), days),
        encoding="utf-8",
    )
    return {"debatte": 1}
