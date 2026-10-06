"""Fragen as text (docs/plan.md goal 4): the three subpages of Fragen and a page for every question to the government.

- `regierung/anfragen.html`, Kleine und Große Anfragen (a Fraktion asks), and `regierung/anfragen/<vorgang>.html`: the
  askers' and the government's preliminary remarks, every numbered question with its "Zu Frage n", the tables of the
  answer, annexes.
- `regierung/einzelfragen.html`, Mündliche and Schriftliche Fragen (an MdB asks, § 105 and Anlage 4 GO-BT), one
  instrument with two ways of answering, and `regierung/fragen/<vorgang>.html`: the question and its written answer,
  or the exchange in the Fragestunde (the answer, every Nachfrage and Zusatzfrage). A Mündliche Frage the Fragestunde
  did not reach, answered in writing, counts as mündlich and says so.
- `regierung/regierungsbefragung.html`, one entry per Befragung der Bundesregierung (who was questioned, the questions
  by fraction), and `regierung/regierungsbefragung/<sitting>.html`: every question with its answer, Nachfragen and
  Zusatzfragen.

This repo parses nothing (the split in goal 4): the texts and turns are the foundation's `question_text`,
`question_table`, `question_turn` and `question_parse`. A question the foundation marks `failed` or `partial` is shown
as "Antwort nicht lesbar" with the PDF, never as unanswered. Without those tables nothing is written.

Search: each question page is in the Pagefind index (`data-pagefind-body`) with its title and question text; the
answers are on the page but not indexed (`data-pagefind-ignore`)."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from research import controls, redirects, urls
from research.data import WP, drucksache_pdf, has_table, page_id
from research.questions import fraction_of_originator
from research.ui import (
    FOOTER,
    SHORT,
    TOKEN,
    crumbs,
    dot,
    e,
    entity_header,
    frac_link,
    long_date,
    n,
    search_marks,
    shell,
    short_date,
    subtabs,
)

QUESTION_TABS = (
    ("questions", "regierung/index.html", "Überblick"),
    ("anfragen", urls.ANFRAGEN, "Kleine und Große Anfragen"),
    ("einzelfragen", urls.EINZELFRAGEN, "Einzelfragen"),
    ("befragung", urls.BEFRAGUNGEN, "Regierungsbefragung"),
)
ANFRAGE_TYPES = ("Kleine Anfrage", "Große Anfrage")
EINZEL_TYPES = ("Mündliche Frage", "Schriftliche Frage")
DIP_VORGANG = "https://dip.bundestag.de/vorgang/{}"
TURN_LABEL = {"einleitung": "Einleitung", "frage": "Frage", "antwort": "Antwort", "nachfrage": "Nachfrage",
              "zusatzfrage": "Zusatzfrage"}  # fmt: skip
# question_parse.status -> what a row and a page say
STATUS = {"complete": "beantwortet", "partial": "Antwort nicht lesbar", "failed": "Antwort nicht lesbar",
          "unanswered": "nicht beantwortet"}  # fmt: skip
STATUS_SLUG = {"complete": "beantwortet", "partial": "nicht-lesbar", "failed": "nicht-lesbar",
               "unanswered": "offen"}  # fmt: skip

STYLE = """<style>
.qp .row .l { white-space: normal; max-width: 40vw; }
.qp .st { display: inline-block; font-size: 12px; padding: 1px 7px; border-radius: 9px;
  background: var(--chip, #eef0f3); color: var(--muted); }
.qp .st.nicht-lesbar { background: var(--warn-soft); color: var(--warn); }
.qp .q-part { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 4px 22px 10px;
  margin: 12px 0; font-size: 15px; line-height: 1.6; }
.qp .q-part p { margin: 10px 0; max-width: 72ch; }
.qp .q-part .k { font-size: 11px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase;
  color: var(--faint); margin-top: 12px; }
.qp .q-part .k a, .qp .q-part .k .sub { text-transform: none; letter-spacing: 0; font-weight: 500; }
.qp .q-ask { border-left: 3px solid var(--c, var(--line)); }
.qp .q-ans { border-left: 3px solid var(--reg, var(--line)); }
.qp .q-turn { border-left: 3px solid var(--c, var(--line)); padding-left: 14px; margin: 14px 0; }
.qp .q-turn .who { font-size: 13px; color: var(--muted); margin-top: 10px; }
.qp .q-turn .who a { font-weight: 600; }
.qp .q-turn .who .role { font-size: 11px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase;
  color: var(--faint); margin-right: 6px; }
.qp .q-gap { padding: 8px 12px; background: var(--warn-soft); color: var(--warn); border-radius: 8px; font-size: 14px; }
.qp .q-thread { margin: 18px 0 26px; }
.qp .q-thread > h3 { font-size: 15px; font-weight: 600; margin: 0 0 4px; }
.qp table.qt { border-collapse: collapse; font-size: 13px; margin: 10px 0; }
.qp table.qt td, .qp table.qt th { border: 1px solid var(--line); padding: 3px 7px; vertical-align: top; }
.qp table.qt th { background: var(--bg); font-weight: 600; }
.qp table.qt caption { text-align: left; font-size: 13px; color: var(--muted); padding: 4px 0; }
.qp .scroll { overflow-x: auto; }
.qp .bf { margin: 0 0 22px; }
.qp .bf h2 { font-size: 17px; margin: 0 0 2px; }
.qp .bf .who { color: var(--muted); font-size: 14px; margin-bottom: 6px; }
.qp .bf ol { margin: 6px 0 0; padding-left: 20px; font-size: 14px; }
.qp .bf ol li { margin: 0 0 4px; }
</style>"""


def available(conn: sqlite3.Connection) -> bool:
    """The store has the foundation's question tables (foundation v0.2.0)."""
    return all(has_table(conn, t) for t in ("question_text", "question_turn", "question_parse", "question_table"))


def answer_by(name: str) -> str:
    """Who answered, after "Antwort": the PDF prints the genitive without its article ("Bundesministeriums des
    Innern", "Parl. Staatssekretärs Christoph de Vries"), or with it ("des Parlamentarischen Staatssekretärs …")."""
    if name.startswith(("des ", "der ")):
        return name
    words = name.split()
    office = words[1] if words[0] == "Parl." and len(words) > 1 else words[0]
    return ("der " if office.endswith("in") else "des ") + name


def ministry_name(name: str | None) -> str | None:
    """The answering ministry in the nominative, for lists: "Bundesministeriums des Innern" -> "Bundesministerium
    des Innern", "Auswärtigen Amts" -> "Auswärtiges Amt"."""
    if not name:
        return name
    for gen, nom in (("Bundesministeriums ", "Bundesministerium "), ("Auswärtigen Amts", "Auswärtiges Amt"),
                     ("Bundeskanzleramts", "Bundeskanzleramt")):  # fmt: skip
        if name.startswith(gen):
            return nom + name[len(gen) :]
    return name


def _paragraphs(text: str | None) -> list[str]:
    return [p.strip() for p in (text or "").split("\n\n") if p.strip()]


def _text(text: str | None) -> str:
    return "".join(f"<p>{e(p)}</p>" for p in _paragraphs(text))


def _cell(c) -> str:
    if isinstance(c, dict):
        span = "".join(f' {k}="{int(c[k])}"' for k in ("colspan", "rowspan") if c.get(k))
        return f"<td{span}>{e(c.get('text') or '')}</td>"
    return f"<td>{e(c or '')}</td>"


def table_html(cells: dict, pdf: str | None) -> str:
    """A table of an answer from its cells ({"caption", "head", "body", "foot"}); one the foundation could not read
    names its page and links the PDF."""
    if cells.get("extracted") is False:
        page = f" auf Seite {cells['page']}" if cells.get("page") else ""
        link = f' <a href="{e(pdf)}">PDF</a>' if pdf else ""
        return f'<p class="q-gap">Eine Tabelle{page} ließ sich nicht lesen. Sie steht im PDF.{link}</p>'
    cap = f"<caption>{e(cells['caption'])}</caption>" if cells.get("caption") else ""
    head = "".join("<tr>" + "".join(_cell(c).replace("<td", "<th").replace("</td>", "</th>") for c in r) + "</tr>"
                   for r in cells.get("head") or [])  # fmt: skip
    body = "".join("<tr>" + "".join(_cell(c) for c in r) + "</tr>" for r in [*(cells.get("body") or []),
                                                                             *(cells.get("foot") or [])])  # fmt: skip
    return f'<div class="scroll"><table class="qt">{cap}<thead>{head}</thead><tbody>{body}</tbody></table></div>'


def _with_tables(t: dict, pdf: str | None) -> str:
    """A text's paragraphs with its tables after the paragraph they follow."""
    paras = _paragraphs(t["text"])
    after = defaultdict(list)
    for tb in t["tables"]:
        after[min(tb["after"], len(paras))].append(table_html(tb["cells"], pdf))
    out = "".join(after[0])
    for i, p in enumerate(paras, 1):
        out += f"<p>{e(p)}</p>" + "".join(after[i])
    return out


# ---------------------------------------------------------------- data


def _texts(conn: sqlite3.Connection, types: tuple[str, ...]) -> dict[str, list[dict]]:
    """question_text rows by Vorgang (in position order), each with its tables."""
    tables: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute("SELECT question_text_id, position, after_paragraph, cells FROM question_table "
                          "ORDER BY question_text_id, position"):  # fmt: skip
        tables[r["question_text_id"]].append({"after": r["after_paragraph"] or 0, "cells": json.loads(r["cells"])})
    out: dict[str, list[dict]] = defaultdict(list)
    marks = ",".join("?" * len(types))
    for r in conn.execute(
        f"""SELECT t.* FROM question_text t JOIN vorgang v ON v.id = t.vorgang_id
            WHERE v.wahlperiode = ? AND v.type IN ({marks}) ORDER BY t.drucksache_number, t.position""",
        (WP, *types),
    ):
        out[r["vorgang_id"]].append({**dict(r), "tables": tables.get(r["id"], [])})
    return out


def _status(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["vorgang_id"]: r["status"] for r in conn.execute("SELECT vorgang_id, status FROM question_parse")}


def _people(conn: sqlite3.Connection) -> dict[str, dict]:
    from research.data import display_name

    return {r["id"]: {"name": display_name(r), "fraction": r["fraction"]} for r in conn.execute("SELECT * FROM person")}


def _turns(conn: sqlite3.Connection, where: str, args: tuple) -> list[dict]:
    """Speeches with their question_turn role, in protocol order."""
    return [
        {"id": r["id"], "person": r["person_id"], "name": r["speaker_name"].split(",")[0].split(" (")[0].strip(),
         "office": r["speaker_role"], "group": r["speaker_group"], "role": r["role"], "thread": r["thread_id"],
         "vorgang": r["vorgang_id"], "text": r["text"], "sitting": r["sitting_id"], "item": r["agenda_item_id"],
         "date": r["date"]}
        for r in conn.execute(
            f"""SELECT s.id, s.person_id, s.speaker_name, s.speaker_role, s.speaker_group, s.text, s.sitting_id,
                       s.agenda_item_id, st.date, q.role, q.thread_id, q.vorgang_id
                FROM speech s JOIN sitting st ON st.id = s.sitting_id
                LEFT JOIN question_turn q ON q.speech_id = s.id
                WHERE st.wahlperiode = ? AND {where} ORDER BY st.date, s.sitting_id, s.position""",
            (WP, *args),
        )
    ]  # fmt: skip


def anfragen(conn: sqlite3.Connection) -> list[dict]:
    """Every Kleine and Große Anfrage of the Wahlperiode, newest first: its Fraktionen (the Anfrage's Urheber), the
    Anfrage and the answer as Drucksachen, the texts and the parse status."""
    marks = ",".join("?" * len(ANFRAGE_TYPES))
    docs: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in conn.execute(
        f"""SELECT vd.vorgang_id, d.* FROM vorgang_drucksache vd JOIN drucksache d ON d.id = vd.drucksache_id
            JOIN vorgang v ON v.id = vd.vorgang_id WHERE v.wahlperiode = ? AND v.type IN ({marks})
            ORDER BY d.date, d.number""",
        (WP, *ANFRAGE_TYPES),
    ):
        docs[r["vorgang_id"]].append(r)
    texts, status = _texts(conn, ANFRAGE_TYPES), _status(conn)
    out = []
    for v in conn.execute(f"SELECT * FROM vorgang WHERE wahlperiode = ? AND type IN ({marks})", (WP, *ANFRAGE_TYPES)):
        ds = docs.get(v["id"], [])
        asked = next((d for d in ds if d["type"] in ANFRAGE_TYPES), None)
        answer = next((d for d in ds if d["type"] == "Antwort"), None)
        fr = [fraction_of_originator(o) for o in json.loads(asked["originators"] or "[]")] if asked else []
        ts = texts.get(v["id"], [])
        ministry = next((t["name"] for t in ts if t["part"] == "antwort" and t["name"]), None)
        out.append({
            "id": v["id"], "type": v["type"], "title": v["title"], "fractions": fr or ["unbekannt"],
            "asked": _doc(asked), "answer": _doc(answer), "texts": ts, "ministry": ministry,
            "status": status.get(v["id"]) or ("unanswered" if not answer else "failed"),
            "date": (answer or asked)["date"] if (answer or asked) else "",
        })  # fmt: skip
    out.sort(key=lambda a: (a["date"], a["id"]), reverse=True)
    return out


def _doc(d: sqlite3.Row | None) -> dict | None:
    if d is None:
        return None
    return {"number": d["number"], "date": d["date"], "id": d["id"],
            "pdf": d["pdf_url"] or drucksache_pdf(d["number"])}  # fmt: skip


def einzelfragen(conn: sqlite3.Connection) -> list[dict]:
    """Every Mündliche and Schriftliche Frage, newest first: asker and Ressort (`question_activity`), the question and
    its written answer (`question_text`), the turns of the Fragestunde that answered it (`question_turn` by its
    thread), the Fragen-Drucksache and the parse status."""
    marks = ",".join("?" * len(EINZEL_TYPES))
    asker: dict[str, dict] = {}
    answerer: dict[str, dict] = {}
    ressort: dict[str, str] = {}
    page: dict[str, str] = {}
    if has_table(conn, "question_activity"):
        for r in conn.execute("SELECT * FROM question_activity ORDER BY id"):
            if r["ressort"]:
                ressort.setdefault(r["vorgang_id"], r["ressort"])
            if r["activity_type"] == "Frage":
                asker.setdefault(r["vorgang_id"], {"person": r["person_id"], "name": r["name"]})
                page.setdefault(r["vorgang_id"], r["document_number"])
            elif r["activity_type"] == "Antwort":
                answerer.setdefault(r["vorgang_id"], {"person": r["person_id"], "name": r["name"]})
    dates = {r["number"]: r["date"] for r in conn.execute(
        "SELECT number, date FROM drucksache WHERE wahlperiode = ? AND type IN ('Schriftliche Fragen', 'Fragen')",
        (WP,))}  # fmt: skip
    texts, status = _texts(conn, EINZEL_TYPES), _status(conn)
    threads: dict[str, list[dict]] = defaultdict(list)
    for t in _turns(conn, "s.kind = 'fragestunde'", ()):
        if t["thread"]:
            threads[t["thread"]].append(t)
    out = []
    for v in conn.execute(f"SELECT * FROM vorgang WHERE wahlperiode = ? AND type IN ({marks})", (WP, *EINZEL_TYPES)):
        ts = texts.get(v["id"], [])
        frage = next((t for t in ts if t["part"] == "frage"), None)
        number = (frage or {}).get("drucksache_number") or page.get(v["id"])
        thread = threads.get(frage["thread_id"], []) if frage and frage["thread_id"] else []
        out.append({
            "id": v["id"], "type": v["type"], "title": v["title"], "asker": asker.get(v["id"]),
            "answerer": answerer.get(v["id"]), "ressort": ressort.get(v["id"]), "texts": ts, "frage": frage,
            "turns": thread, "drucksache": number, "date": dates.get(number or "", ""),
            "status": status.get(v["id"], "failed"),
        })  # fmt: skip
    out.sort(key=lambda q: (q["date"], q["id"]), reverse=True)
    return out


def befragungen(conn: sqlite3.Connection) -> list[dict]:
    """Every Befragung der Bundesregierung, newest first: the turns in order, grouped by the question they belong to,
    and who was questioned (the speakers of the `einleitung` and `antwort` turns, with their office)."""
    items = conn.execute(
        """SELECT a.id, a.sitting_id, a.position, a.title, s.date, s.number FROM agenda_item a
           JOIN sitting s ON s.id = a.sitting_id WHERE s.wahlperiode = ? AND a.kind = 'befragung'
           ORDER BY s.date, a.position""",
        (WP,),
    ).fetchall()
    by_item: dict[str, list[dict]] = defaultdict(list)
    for t in _turns(conn, "s.agenda_item_id IN (SELECT id FROM agenda_item WHERE kind = 'befragung')", ()):
        by_item[t["item"]].append(t)
    out = []
    for it in items:
        turns = by_item.get(it["id"], [])
        questioned: dict[str, dict] = {}
        for t in turns:
            if t["role"] in ("einleitung", "antwort") and t["office"]:
                questioned.setdefault(t["person"] or t["name"], {"person": t["person"], "name": t["name"],
                                                                 "office": t["office"]})  # fmt: skip
        threads: dict[str, list[dict]] = {}
        intro = []
        for t in turns:
            if t["thread"]:
                threads.setdefault(t["thread"], []).append(t)
            else:
                intro.append(t)
        out.append({"id": it["id"], "sitting": it["sitting_id"], "position": it["position"], "date": it["date"],
                    "number": it["number"], "questioned": list(questioned.values()), "intro": intro,
                    "threads": list(threads.values())})  # fmt: skip
    out.reverse()
    return out


# ---------------------------------------------------------------- shared parts


def _person(p: dict | None, cards: set[str], root: str) -> str:
    if not p:
        return "unbekannt"
    name = p["name"].split(",")[0].strip()
    return f'<a href="{root}{e(urls.person(p["person"]))}">{e(name)}</a>' if p.get("person") in cards else e(name)


def _fraction_of(p: dict | None, people: dict[str, dict]) -> str | None:
    return people.get((p or {}).get("person") or "", {}).get("fraction")


def turn_html(t: dict, cards: set[str], root: str) -> str:
    """One spoken turn: its role, the speaker (linked, with office or fraction) and the text, linked to the
    protocol's speech page."""
    who = (f'<a href="{root}{e(urls.person(t["person"]))}">{e(t["name"])}</a>' if t["person"] in cards
           else e(t["name"]))  # fmt: skip
    sub = t["office"] or t["group"]
    colour = TOKEN.get(t["group"] or "", "reg")
    return (
        f'<div class="q-turn" style="--c:var(--{colour})" id="{e(page_id(t["id"]))}"><div class="who">'
        f'<span class="role">{e(TURN_LABEL.get(t["role"] or "", "Beitrag"))}</span>{dot(t["group"])}{who}'
        f"{f' <span class="sub">{e(sub)}</span>' if sub else ''} · "
        f'<a href="{root}{e(urls.speech(t["id"]))}">im Protokoll</a></div>{_text(t["text"])}</div>'
    )


def _row(href: str, date: str, title: str, sub: str, status: str, attrs: dict[str, str]) -> str:
    data = "".join(f' data-{k}="{e(v)}"' for k, v in attrs.items())
    st = STATUS.get(status, status)
    return (
        f'<a class="row" href="{e(href)}"{data}><span class="d">{short_date(date) if date else ""}</span>'
        f'<span class="t"><span class="ti">{e(title)}</span><span class="sub">{sub}</span></span>'
        f'<span class="l"><span class="st {e(STATUS_SLUG.get(status, ""))}">{e(st)}</span></span></a>'
    )


def _status_chips(items: list[dict]) -> str:
    c = Counter(STATUS_SLUG.get(x["status"], "offen") for x in items)
    labels = {"beantwortet": "beantwortet", "nicht-lesbar": "Antwort nicht lesbar", "offen": "nicht beantwortet"}
    return controls.block("Stand", controls.chips("stand", [(k, labels[k], c[k], "accent") for k in labels if c[k]],
                                                  "Stand"))  # fmt: skip


def _fraction_chips(counts: Counter, title: str) -> str:
    return controls.block(
        title,
        controls.chips(
            "fraktion", [(tok, SHORT.get(f, f), counts[tok], tok) for f, tok in TOKEN.items() if counts[tok]], title
        ),
    )


def _page(title: str, active: str, root: str, body: str, desc: str, kind: str) -> str:
    return shell(root=root, kind=kind, active="questions", title=title, desc=desc,
                 body=f'{subtabs(root, QUESTION_TABS, active)}<div class="qp">{body}</div><footer>{FOOTER}</footer>',
                 data={"kind": "questions"}, head=STYLE + controls.head(root))  # fmt: skip


def _gap(status: str, pdf: str | None) -> str:
    """What a page says for a question whose answer was not read, or is not there."""
    link = f' <a href="{e(pdf)}">Antwort als PDF</a>' if pdf else ""
    if status in ("failed", "partial"):
        what = "Ein Teil der Antwort" if status == "partial" else "Die Antwort"
        return f'<p class="q-gap">Antwort nicht lesbar: {what} ließ sich aus dem PDF nicht lesen.{link}</p>'
    if status == "unanswered":
        return '<p class="q-gap">Die Bundesregierung hat noch nicht geantwortet.</p>'
    return ""


# ---------------------------------------------------------------- Kleine und Große Anfragen


def anfrage_page(a: dict, cards: set[str]) -> str:
    root = "../../"
    fr = " und ".join(frac_link(f, root) for f in a["fractions"])
    pdf = (a["answer"] or {}).get("pdf")
    lines = [f'<span class="k">Fraktion</span> {fr}']
    if a["asked"]:
        lines.append(f'<span class="k">{e(a["type"])}</span> Drucksache {e(a["asked"]["number"])} vom '
                     f'{long_date(a["asked"]["date"])} (<a href="{e(a["asked"]["pdf"])}">PDF</a>)')  # fmt: skip
    if a["answer"]:
        by = f" (Antwort {e(answer_by(a['ministry']))})" if a["ministry"] else ""
        lines.append(f'<span class="k">Antwort</span> Drucksache {e(a["answer"]["number"])} vom '
                     f'{long_date(a["answer"]["date"])}{by}, <a href="{e(pdf)}">PDF</a>')  # fmt: skip
    head = entity_header(a["title"], lines, [f'<a href="{DIP_VORGANG.format(e(a["id"]))}">Vorgang im DIP ↗</a>'],
                         when=e(a["type"]), cls="sp-head")  # fmt: skip
    colour = TOKEN.get(a["fractions"][0], "reg")
    parts, answers = [], defaultdict(list)
    for t in a["texts"]:
        if t["part"] == "antwort":
            answers[t["number"]].append(t)
    for t in a["texts"]:
        if t["part"] == "vorbemerkung_fragesteller":
            parts.append(f'<section class="q-part q-ask" style="--c:var(--{colour})"><div class="k">Vorbemerkung der '
                         f"Fragesteller</div>{_with_tables(t, pdf)}</section>")  # fmt: skip
        elif t["part"] == "vorbemerkung_bundesregierung":
            parts.append('<section class="q-part q-ans" data-pagefind-ignore><div class="k">Vorbemerkung der '
                         f"Bundesregierung</div>{_with_tables(t, pdf)}</section>")  # fmt: skip
        elif t["part"] == "frage":
            ans = "".join(f'<div class="k">Zu Frage {e(x["number"])}</div>{_with_tables(x, pdf)}'
                          for x in answers.get(t["number"], []))  # fmt: skip
            parts.append(f'<section class="q-part q-ask" style="--c:var(--{colour})" id="frage-{e(t["number"])}">'
                         f'<div class="k">Frage {e(t["number"])}</div>{_with_tables(t, pdf)}'
                         f"{f'<div data-pagefind-ignore>{ans}</div>' if ans else ''}</section>")  # fmt: skip
        elif t["part"] == "anlage":
            parts.append(
                f'<section class="q-part" data-pagefind-ignore><div class="k">Anlage'
                f"{f' {e(t["number"])}' if t['number'] else ''}</div>{_with_tables(t, pdf)}</section>"
            )
    marks = search_marks(a["type"], a["date"], Fraktion=a["fractions"][0])
    body = (
        crumbs(
            (f"{root}{urls.ANFRAGEN}", "Kleine und Große Anfragen"),
            (None, a["asked"]["number"] if a["asked"] else a["type"]),
        )  # fmt: skip
        + f'<article data-pagefind-body>{marks}<span hidden data-pagefind-meta="title">{e(a["title"])}</span>'
        + head
        + _gap(a["status"], pdf)
        + "".join(parts)
        + "</article>"
    )
    if a["status"] == "complete" and not parts:
        body += '<p class="explain">Zu dieser Anfrage sind keine Texte im Datenbestand.</p>'
    desc = f"{a['type']} der Fraktion {', '.join(a['fractions'])}: {a['title']}. Fragen und Antworten im Wortlaut."
    return _page(a["title"], "anfragen", root, body, desc[:300], "p-question")


def anfragen_page(items: list[dict], sitting_dates: list[str]) -> str:
    root = "../"
    rows, fr, art = [], Counter(), Counter()
    for a in items:
        toks = [TOKEN[f] for f in a["fractions"] if f in TOKEN]
        fr.update(toks)
        art[a["type"]] += 1
        sub = " · ".join(x for x in (a["type"], ", ".join(SHORT.get(f, f) for f in a["fractions"]),
                                     ministry_name(a["ministry"]) or "") if x)  # fmt: skip
        rows.append(_row(urls.anfrage(a["id"]).removeprefix("regierung/"), a["date"], a["title"], e(sub), a["status"],
                         {"fraktion": " ".join(toks), "art": urls.slug(a["type"]),
                          "stand": STATUS_SLUG.get(a["status"], "offen"),
                          "w": _week(a["date"])}))  # fmt: skip
    kinds = [(urls.slug(t), t, k) for t, k in art.most_common()]
    lists = controls.scope(
        controls.toolbar("Wörter im Titel …")
        + controls.view("art", "Art", controls.segmented("art", kinds, "Art", "Anfragen"),
                        controls.segmented_table(kinds, "Art", "Anfragen"))
        + _fraction_chips(fr, "Fraktion") + _status_chips(items)
        + controls.activity([a["date"] for a in items], sitting_dates, "Anfragen", "Anfrage", "Datum")
        + controls.rows(rows, "anfragen", "Keine Anfragen im Datenbestand."), "Anfragen", "Anfrage")  # fmt: skip
    unread = sum(1 for a in items if a["status"] in ("failed", "partial"))
    body = (
        '<h1>Kleine und Große Anfragen</h1><p class="lead">Mit einer Kleinen oder Großen Anfrage fragt eine Fraktion '
        "die Bundesregierung schriftlich (§§ 100 bis 104 GO-BT). Hier steht jede Anfrage des 21. Bundestages mit "
        "ihren Fragen und der Antwort im Wortlaut, die neueste zuerst. Das Datum ist das der Antwort, bei offenen "
        "Anfragen das der Anfrage.</p>"
        f'<p class="explain">Die Texte stammen aus den PDF-Dateien der Antworten. {n(unread)} Antworten ließen sich '
        "ganz oder teilweise nicht lesen. Sie sind als „Antwort nicht lesbar“ markiert und verlinken das PDF.</p>"
        + lists
    )
    return _page("Kleine und Große Anfragen", "anfragen", root, body,
                 "Alle Kleinen und Großen Anfragen des 21. Bundestages mit Fragen und Antworten im Wortlaut.",
                 "p-questions")  # fmt: skip


def _week(date: str) -> str:
    from research.data import iso_week

    return iso_week(date) if date else ""


# ---------------------------------------------------------------- Einzelfragen


def _way(q: dict) -> str:
    """mündlich or schriftlich; a Mündliche Frage answered in writing stays mündlich."""
    return "muendlich" if q["type"] == "Mündliche Frage" else "schriftlich"


def frage_page(q: dict, cards: set[str], people: dict[str, dict]) -> str:
    root = "../../"
    fraction = _fraction_of(q["asker"], people)
    colour = TOKEN.get(fraction or "", "reg")
    answers = [t for t in q["texts"] if t["part"] == "antwort"]
    pdf = drucksache_pdf(q["drucksache"]) if q["drucksache"] else None
    lines = [f'<span class="k">Gefragt von</span> {_person(q["asker"], cards, root)}'
             + (f" ({frac_link(fraction, root)})" if fraction else "")]  # fmt: skip
    if q["ressort"]:
        lines.append(f'<span class="k">Ressort</span> {e(q["ressort"])}')
    if q["drucksache"]:
        lines.append(f'<span class="k">Drucksache</span> {e(q["drucksache"])}'
                     f'{f" vom {long_date(q['date'])}" if q["date"] else ""} '
                     f'(<a href="{e(pdf)}">PDF</a>)')  # fmt: skip
    head = entity_header(q["title"], lines, [f'<a href="{DIP_VORGANG.format(e(q["id"]))}">Vorgang im DIP ↗</a>'],
                         when=e(q["type"]), cls="sp-head")  # fmt: skip
    parts = []
    if q["frage"]:
        parts.append(f'<section class="q-part q-ask" style="--c:var(--{colour})"><div class="k">Frage'
                     f'{f" {e(q['frage']['number'])}" if q["frage"]["number"] else ""}'
                     f"</div>{_text(q['frage']['text'])}</section>")  # fmt: skip
    for t in answers:
        # the name as printed after "Antwort", else DIP's answerer ("Sören Bartol, Parl. Staatssekr., …")
        who = answer_by(t["name"]) if t["name"] else f"von {(q['answerer'] or {}).get('name') or 'unbekannt'}"
        if t["answerer_person_id"] in cards:
            who = f'<a href="{root}{e(urls.person(t["answerer_person_id"]))}">{e(who)}</a>'
        else:
            who = e(who)
        when = f" vom {long_date(t['answer_date'])}" if t["answer_date"] else ""
        parts.append(f'<section class="q-part q-ans" data-pagefind-ignore><div class="k">Antwort {who}{when}</div>'
                     f"{_with_tables(t, pdf)}</section>")  # fmt: skip
    if q["turns"]:
        first = q["turns"][0]
        note = ('<p class="explain">Die Frage wurde in der Fragestunde aufgerufen. Die Antwort und alle Nachfragen '
                'stehen hier in der Reihenfolge des Protokolls. Nachfragen stellt die fragende Person, Zusatzfragen '
                "andere Abgeordnete.</p>")  # fmt: skip
        parts.append(f'<section class="q-thread" data-pagefind-ignore><h2>In der Fragestunde am '
                     f'<a href="{root}{e(urls.sitting(first["sitting"]))}">{e(long_date(first["date"]))}</a></h2>{note}'
                     + "".join(turn_html(t, cards, root) for t in q["turns"]) + "</section>")  # fmt: skip
    elif q["type"] == "Mündliche Frage" and answers:
        parts.insert(0, '<p class="explain">Die Fragestunde hat diese Frage nicht erreicht. Sie wurde schriftlich '
                        "beantwortet und zählt weiter als mündliche Frage.</p>")  # fmt: skip
    if not q["turns"]:
        parts.append(_gap(q["status"], pdf))
    marks = search_marks(q["type"], q["date"], Fraktion=fraction)
    body = (
        crumbs((f"{root}{urls.EINZELFRAGEN}", "Einzelfragen"), (None, q["type"]))
        + f'<article data-pagefind-body>{marks}<span hidden data-pagefind-meta="title">{e(q["title"])}</span>'
        + head
        + "".join(parts)
        + "</article>"
    )
    asker = (q["asker"] or {}).get("name", "").split(",")[0]
    desc = f"{q['type']} von {asker}: {q['title']}. Frage und Antwort im Wortlaut." if asker else q["title"]
    return _page(q["title"], "einzelfragen", root, body, desc[:300], "p-question")


def einzelfragen_page(items: list[dict], people: dict[str, dict], sitting_dates: list[str]) -> str:
    root = "../"
    rows, fr, way, rs = [], Counter(), Counter(), Counter()
    for q in items:
        f = _fraction_of(q["asker"], people)
        tok = TOKEN.get(f or "", "")
        fr[tok] += 1
        w = _way(q)
        way[w] += 1
        r = urls.slug(q["ressort"].removeprefix("Bundesministerium ")) if q["ressort"] else ""
        if r:
            rs[(r, q["ressort"])] += 1
        how = "mündlich" if w == "muendlich" else "schriftlich"
        if w == "muendlich" and not q["turns"] and any(t["part"] == "antwort" for t in q["texts"]):
            how = "mündlich, schriftlich beantwortet"
        asker = (q["asker"] or {}).get("name", "").split(",")[0]
        sub = " · ".join(x for x in (how, f"{asker} ({SHORT.get(f, f)})" if f else asker,
                                     (q["ressort"] or "").removeprefix("Bundesministerium ")) if x)  # fmt: skip
        rows.append(_row(urls.frage(q["id"]).removeprefix("regierung/"), q["date"], q["title"], e(sub), q["status"],
                         {"fraktion": tok, "weg": w, "ressort": r, "stand": STATUS_SLUG.get(q["status"], "offen"),
                          "w": _week(q["date"])}))  # fmt: skip
    ways = [(k, label, way[k]) for k, label in (("schriftlich", "schriftlich"), ("muendlich", "mündlich")) if way[k]]
    ressorts = [(slug, label.removeprefix("Bundesministerium "), k) for (slug, label), k in rs.most_common()]
    lists = controls.scope(
        controls.toolbar("Wörter im Titel oder Name …")
        + controls.view("weg", "Mündlich oder schriftlich", controls.segmented("weg", ways, "Weg", "Fragen"),
                        controls.segmented_table(ways, "Weg", "Fragen"))
        + _fraction_chips(fr, "Fraktion der fragenden Person")
        + controls.block("Ressort", controls.sized_chips("ressort", ressorts, "Ressort"))
        + _status_chips(items)
        + controls.activity([q["date"] for q in items], sitting_dates, "Fragen", "Frage", "Datum")
        + controls.rows(rows, "einzelfragen", "Keine Fragen im Datenbestand."), "Fragen", "Frage")  # fmt: skip
    body = (
        '<h1>Einzelfragen</h1><p class="lead">Jedes Mitglied des Bundestages kann der Bundesregierung einzelne Fragen '
        "stellen (§ 105 und Anlage 4 GO-BT): mündlich für die Fragestunde oder schriftlich. Beides ist ein Instrument "
        "mit zwei Wegen der Antwort. Hier steht jede Frage des 21. Bundestages mit ihrer Antwort im Wortlaut, die "
        "neueste zuerst. Eine mündliche Frage, die die Fragestunde nicht erreicht hat, wird schriftlich beantwortet "
        "und bleibt eine mündliche Frage.</p>"
        '<p class="explain">Das Datum ist das der Drucksache, in der die Frage steht. Die Fraktion ist die heutige '
        "der fragenden Person.</p>" + lists
    )
    return _page("Einzelfragen", "einzelfragen", root, body,
                 "Alle mündlichen und schriftlichen Fragen des 21. Bundestages mit Antworten im Wortlaut.",
                 "p-questions")  # fmt: skip


# ---------------------------------------------------------------- Regierungsbefragung


def _questioned(b: dict, cards: set[str], root: str) -> str:
    return "; ".join(f"{_person(p, cards, root)}, {e(p['office'])}" for p in b["questioned"]) or "nicht erkannt"


def befragung_page(b: dict, cards: set[str]) -> str:
    root = "../../"
    parts = []
    if b["intro"]:
        parts.append('<section class="q-thread"><h2>Einleitung</h2>'
                     + "".join(turn_html(t, cards, root) for t in b["intro"]) + "</section>")  # fmt: skip
    for i, th in enumerate(b["threads"], 1):
        ask = th[0]
        parts.append(f'<section class="q-thread" id="frage-{i}"><h3>{i}. Frage von {e(ask["name"])}'
                     f'{f" ({e(SHORT.get(ask['group'], ask['group']))})" if ask["group"] else ""}</h3>'
                     + "".join(turn_html(t, cards, root) for t in th) + "</section>")  # fmt: skip
    lines = [f'<span class="k">Befragt</span> {_questioned(b, cards, root)}',
             f'<span class="k">Fragen</span> {n(len(b["threads"]))}',
             f'<span class="k">Sitzung</span> <a href="{root}{e(urls.sitting(b["sitting"], b["position"]))}">'
             f'{b["number"]}. Sitzung</a>']  # fmt: skip
    title = f"Regierungsbefragung am {long_date(b['date'])}"
    head = entity_header(title, lines, when="Befragung der Bundesregierung", cls="sp-head")
    body = (crumbs((f"{root}{urls.BEFRAGUNGEN}", "Regierungsbefragung"), (None, short_date(b["date"])))
            + head + '<p class="explain">Jede Frage mit ihrer Antwort, den Nachfragen der fragenden Person und den '
            "Zusatzfragen anderer Abgeordneter, in der Reihenfolge des Protokolls. Welche Beiträge zu einer Frage "
            "gehören, folgt aus den Worten der Sitzungsleitung.</p>" + "".join(parts))  # fmt: skip
    return _page(title, "befragung", root, body,
                 f"{title}: {', '.join(p['name'] for p in b['questioned'])}. Alle Fragen und Antworten im Wortlaut.",
                 "p-question")  # fmt: skip


def befragungen_page(items: list[dict], cards: set[str]) -> str:
    root = "../"
    entries = []
    for b in items:
        fr = Counter(th[0]["group"] for th in b["threads"] if th[0]["group"])
        by = " · ".join(f"{dot(f)}{e(SHORT.get(f, f))} {k}" for f, k in sorted(fr.items(), key=lambda x: -x[1]))
        href = urls.befragung(b["sitting"]).removeprefix("regierung/")
        qs = "".join(f'<li><a href="{e(href)}#frage-{i}">{e(th[0]["name"])}</a>'
                     f'{f" ({e(SHORT.get(th[0]['group'], th[0]['group']))})" if th[0]["group"] else ""}: '
                     f'{e(_lead(th[0]["text"]))}</li>' for i, th in enumerate(b["threads"], 1))  # fmt: skip
        entries.append(
            f'<section class="bf card"><h2><a href="{e(href)}">{e(long_date(b["date"]))}</a></h2>'
            f'<div class="who">Befragt: {_questioned(b, cards, root)}</div>'
            f'<div class="who">{n(len(b["threads"]))} Fragen · {by}</div>'
            f"<details><summary>Die Fragen</summary><ol>{qs}</ol></details></section>"
        )
    body = (
        '<h1>Regierungsbefragung</h1><p class="lead">In der Befragung der Bundesregierung (§ 106 Abs. 2 GO-BT) '
        "stellen sich Mitglieder der Bundesregierung in der Sitzungswoche den Fragen der Abgeordneten, ohne dass "
        "die Fragen vorher eingereicht werden. Hier steht jede Befragung des 21. Bundestages, die neueste zuerst, "
        "mit den Befragten und ihren Fragen. Ein Klick führt zu allen Fragen und Antworten im Wortlaut.</p>"
        + "".join(entries)
    )
    return _page("Regierungsbefragung", "befragung", root, body,
                 "Jede Regierungsbefragung des 21. Bundestages: wer befragt wurde, alle Fragen und Antworten.",
                 "p-questions")  # fmt: skip


def _lead(text: str | None, limit: int = 160) -> str:
    """The start of a question, without the thanks to the chair it usually opens with."""
    from research.data import excerpt

    paras = _paragraphs(text)
    body = " ".join(paras)
    for opener in ("Vielen Dank", "Danke", "Herzlichen Dank", "Sehr geehrte", "Sehr geehrter", "Frau Präsidentin",
                   "Herr Präsident", "Frau Vizepräsidentin", "Herr Vizepräsident"):  # fmt: skip
        if body.startswith(opener):
            cut = body.find(". ", 0, 120)
            if cut > 0:
                body = body[cut + 2 :].lstrip("– ").strip()
            break
    return excerpt(body, limit)


# ---------------------------------------------------------------- write


def write(conn: sqlite3.Connection, out: Path, cards: set[str], sitting_dates: list[str]) -> dict[str, int]:
    """Write the three subpages and a page per question; returns the counts, {} without the question tables. The
    Vorgang pages of the Mündliche Fragen (vorgaenge/<id>.html) forward to the question's page."""
    if not available(conn):
        return {}
    d = out / "regierung"
    people = _people(conn)
    af = anfragen(conn)
    (d / "anfragen").mkdir(parents=True, exist_ok=True)
    for a in af:
        (out / urls.anfrage(a["id"])).write_text(anfrage_page(a, cards), encoding="utf-8")
    (out / urls.ANFRAGEN).write_text(anfragen_page(af, sitting_dates), encoding="utf-8")
    ef = einzelfragen(conn)
    (d / "fragen").mkdir(parents=True, exist_ok=True)
    for q in ef:
        (out / urls.frage(q["id"])).write_text(frage_page(q, cards, people), encoding="utf-8")
        if q["type"] == "Mündliche Frage":
            redirects.write(out, urls.vorgang(q["id"]), urls.frage(q["id"]), q["title"])
    (out / urls.EINZELFRAGEN).write_text(einzelfragen_page(ef, people, sitting_dates), encoding="utf-8")
    bf = befragungen(conn)
    (d / "regierungsbefragung").mkdir(parents=True, exist_ok=True)
    for b in bf:
        (out / urls.befragung(b["sitting"])).write_text(befragung_page(b, cards), encoding="utf-8")
    (out / urls.BEFRAGUNGEN).write_text(befragungen_page(bf, cards), encoding="utf-8")
    return {"anfragen": len(af), "einzelfragen": len(ef), "befragungen": len(bf)}
