"""Speech pages: `reden/<id>.html`, one per rede with its full text as the protocol prints it.

A rede split at interruptions (`ID…`, `ID…-2`, …) is one page, named after its first part; the parts by others
(Zwischenfragen, Kurzinterventionen, the questions of the Regierungsbefragung) keep their place in it, each part
with its id as anchor. Comments of the protocol (Beifall, Zurufe) and the chair's words stay inline but set apart.
The page is plain HTML with the shared stylesheet and no data of its own; `data-pagefind-*` marks what the search
indexes (see search.py)."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path

from cards.data import WP, _fraction, display_speaker, has_speech_kind, page_id, top_label
from cards.titles import short_title
from cards.ui import FOOTER, LANDSCAPE, TOKEN, e, long_date, n, search_marks, shell, short_date

HERE = Path(__file__).parent
SIMILAR = 5


def _sql(conn: sqlite3.Connection) -> str:
    kind_col = "s.kind" if has_speech_kind(conn) else "'rede' AS kind"
    return f"""
SELECT s.id, s.position, s.person_id, s.speaker_name, s.speaker_role, s.fraction, s.text, s.source_document_id,
       st.id AS sitting_id, st.number, st.date, st.pdf_url, p.party, a.position AS top_position, a.top_id,
       a.title AS agenda_title, {kind_col}
FROM speech s
JOIN sitting st ON st.id = s.sitting_id
JOIN person p ON p.id = s.person_id
LEFT JOIN agenda_item a ON a.id = s.agenda_item_id
WHERE st.wahlperiode = ?
ORDER BY st.date, st.number, s.position
"""


def rede_id(speech_id: str) -> str:
    """ "ID1-3" -> "ID1": the speech a part belongs to. Its page is `reden/<page_id(rede_id)>.html`, since a
    Fragestunde turn's id ("21/3/5/f1") has slashes."""
    return re.sub(r"-\d+$", "", speech_id)


def load(conn: sqlite3.Connection) -> list[dict]:
    """Every rede of WP 21 in protocol order: its sitting and agenda item, and its parts with their paragraphs
    (kind text, comment or chair; a part without paragraphs in the store falls back to its clean text)."""
    paragraphs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in conn.execute("SELECT speech_id, kind, text FROM speech_paragraph ORDER BY speech_id, position"):
        paragraphs[r["speech_id"]].append((r["kind"], r["text"]))
    redes: dict[str, dict] = {}
    for r in conn.execute(_sql(conn), (WP,)):
        rid = rede_id(r["id"])
        part = {
            "id": r["id"], "person": r["person_id"], "name": display_speaker(r), "fraction": _fraction(r),
            "role": r["speaker_role"],
            "paragraphs": paragraphs.get(r["id"]) or [("text", t) for t in r["text"].split("\n\n") if t.strip()],
        }  # fmt: skip
        if rid in redes:
            redes[rid]["parts"].append(part)
            continue
        redes[rid] = {
            "id": rid, "sitting": r["sitting_id"], "number": r["number"], "date": r["date"], "pdf": r["pdf_url"],
            "cite": r["source_document_id"], "top_position": r["top_position"], "label": top_label(r["top_id"]),
            "title": short_title(r["agenda_title"], r["top_id"] or "") if r["agenda_title"] else None,
            "parts": [part], "kind": r["kind"],
        }  # fmt: skip
    return list(redes.values())


def neighbours(path: str | os.PathLike | None = None) -> dict[str, list[str]]:
    """Similar speeches per speech, {speech id: [speech id, …]} most similar first, from the JSON in
    LANDSCAPE_NEIGHBOURS. Empty when it is not set or not readable: the pages then leave out "Ähnliche Reden"."""
    path = path or os.environ.get("LANDSCAPE_NEIGHBOURS")
    if not path or not Path(path).is_file():
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        print(f"{path}: not readable ({err}), speech pages without similar speeches")
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): [str(x) for x in v] for k, v in raw.items() if isinstance(v, list)}


def clip(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + " …"


def speaker(p: dict, cards: set[str]) -> str:
    """The speaker's name, linked to the card when there is one, and fraction or office."""
    name = f'<a href="../{e(p["person"])}.html">{e(p["name"])}</a>' if p["person"] in cards else e(p["name"])
    sub = p["role"] or p["fraction"]
    return f"{name}" + (f' <span class="sub">{e(sub)}</span>' if sub else "")


def paragraph(kind: str, text: str) -> str:
    if kind == "comment":
        return f'<p class="rc">{e(text)}</p>'
    if kind == "chair":
        return f'<p class="rch"><span class="k">Präsidium</span> {e(text)}</p>'
    return f"<p>{e(text)}</p>"


def speech_page(r: dict, cards: set[str], clusters: dict[str, dict], similar: list[dict]) -> str:
    main = r["parts"][0]
    sitting = f"../sitzungen/{page_id(r['sitting'])}.html"
    item = f"{sitting}#top-{r['top_position']}" if r["top_position"] is not None else sitting
    topic = r["title"] or "Plenarsitzung"
    words = sum(len(t.split()) for p in r["parts"] if p["person"] == main["person"] for k, t in p["paragraphs"]
                if k == "text")  # fmt: skip
    cluster = clusters.get(r["id"])
    fs = r.get("kind") == "fragestunde"  # a question, answer or Nachfrage, searchable apart from the Reden
    links = [f'<a href="{e(r["pdf"])}">Plenarprotokoll {e(r["cite"])} (PDF)</a>']
    if cluster:
        links.append(f'<a href="{LANDSCAPE}{e(cluster["week"])}.html#cluster={e(cluster["cluster_id"])}">Thema: '
                     f'{e(cluster["label"])} ↗</a>')  # fmt: skip
    marks = search_marks("Fragestunde" if fs else "Rede", r["date"], Person=main["name"], Fraktion=main["fraction"],
                         Thema=cluster["label"] if cluster else None)  # fmt: skip
    parts = []
    for p in r["parts"]:
        who = "" if p is main else f'<div class="rp-who">{speaker(p, cards)}</div>'
        own = " own" if p["person"] == main["person"] else ""
        parts.append(f'<div class="rp{own}" id="{e(p["id"])}">{who}'
                     f'{"".join(paragraph(k, t) for k, t in p["paragraphs"])}</div>')  # fmt: skip
    body = f"""<p class="crumbs"><a href="../sitzungen/index.html">Sitzungen</a> › <a href="{sitting}">{r["number"]}. Sitzung</a>{f' › <a href="{item}">{e(r["label"])}</a>' if r["label"] else ""}</p>
<article data-pagefind-body>
{marks}
<span hidden data-pagefind-meta="date">{e(r["date"])}</span>
<section class="card sp-head" style="--c:var(--{TOKEN.get(main["fraction"] or "", "reg")})">
  <div class="when">{e(long_date(r["date"], True))} · {r["number"]}. Sitzung</div>
  <h1 data-pagefind-meta="title">{e(main["name"])}: {e(topic)}</h1>
  <div class="lines">{speaker(main, cards)} · <a href="{item}">{e(r["label"] or "Tagesordnung")}</a> · {n(words)} Wörter</div>
  <div class="links">{"".join(links)}</div>
</section>
<div class="speech">{"".join(parts)}</div>
</article>
{similar_block(similar)}
<p class="explain">Der Text folgt dem Plenarprotokoll. Beifall, Zurufe und andere Vermerke des Protokolls sind grau
gesetzt, Worte der Sitzungsleitung mit „Präsidium“ markiert.</p>
<footer>{FOOTER}</footer>"""  # noqa: E501
    what = "Beitrag in der Fragestunde" if fs else "Rede"
    desc = f"{what} von {main['name']} am {long_date(r['date'])} im Bundestag: {clip(topic, 110)}. Volltext mit Quelle."
    head = '<link rel="stylesheet" href="../reden.css">'
    return shell(root="../", kind="p-speech", active="sittings", title=clip(f"{main['name']}: {topic}", 100), desc=desc,
                 body=body, data={"kind": "speech"}, head=head)  # fmt: skip


def similar_block(similar: list[dict]) -> str:
    if not similar:
        return ""
    rows = "".join(
        f'<a class="row" href="{e(page_id(s["id"]))}.html"><span class="d">{short_date(s["date"])}</span>'
        '<span class="t">'
        f'<span class="ti">{e(s["title"] or "Plenarsitzung")}</span><span class="sub">'
        f"{e(' · '.join(x for x in (s['parts'][0]['name'], s['parts'][0]['fraction']) if x))}</span></span></a>"
        for s in similar
    )
    return f'<section class="similar"><h2>Ähnliche Reden</h2><div class="rows">{rows}</div></section>'


def write_pages(out: Path, redes: list[dict], cards: set[str], clusters: dict[str, dict] | None = None,
                similar: dict[str, list[str]] | None = None) -> int:  # fmt: skip
    """Write reden/ and its stylesheet; returns the number of pages."""
    clusters, similar = clusters or {}, similar or {}
    by_id = {r["id"]: r for r in redes}
    folder = out / "reden"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "reden.css", out / "reden.css")
    for r in redes:
        # the neighbours may name a part of a rede: its page is the rede's
        near = list({rede_id(x): by_id[rede_id(x)] for x in similar.get(r["id"], []) if rede_id(x) in by_id}.values())
        near = [s for s in near if s is not r][:SIMILAR]
        (folder / f"{page_id(r['id'])}.html").write_text(speech_page(r, cards, clusters, near), encoding="utf-8")
    return len(redes)
