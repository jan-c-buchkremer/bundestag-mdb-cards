"""Render the static site: one page and one JSON export per card, the index, and the shared assets."""

from __future__ import annotations

import datetime as dt
import html
import json
import shutil
from pathlib import Path

from cards import cohesion, pages, search
from cards.data import index_row

HERE = Path(__file__).parent
# wahlkreise.json: the map, fetched on demand
ASSETS = ("cards.css", "card.js", "pages.js", "parliament.js", "wahlkreise.json")


def _json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", r"<\/")


def description(c: dict) -> str:
    """One plain sentence for <meta description> and link previews; the page itself renders from the data."""
    if c["kind"] == "speaker" and c.get("government") and not c["reden"]:
        return f"{c['name']}, {c['role']}: Ämter in der Bundesregierung während der 21. Wahlperiode, mit Quellen."
    if c["kind"] == "speaker":
        return f"{c['name']}, {c['role'] or 'Rednerin/Redner'} im 21. Deutschen Bundestag: Reden mit Quellen."
    m = c["mandate"] or {}
    where = f", Wahlkreis {m['number']} {m['constituency']}" if m.get("type") == "Direktwahl" else ""
    return (
        f"{c['name']} ({c['fraction'] or 'fraktionslos'}{where}), Mitglied des 21. Deutschen Bundestages: "
        "Reden, namentliche Abstimmungen und Ausschüsse, jede Angabe mit Quelle."
    )


def render_card(c: dict, meta: dict) -> str:
    title = f"{c['name']} – {c['fraction'] or c['role'] or 'Bundestag'}"
    return (
        (HERE / "card.html")
        .read_text(encoding="utf-8")
        .replace("__TITLE__", html.escape(title))
        .replace("__DESC__", html.escape(description(c)))
        .replace("__ID__", html.escape(c["id"]))
        .replace("__CARD__", _json(c))
        .replace("__META__", _json(meta))
        .replace("__HEADER__", pages.site_header("", "cards"))
        .replace("__SEARCH__", search.card_block(c, description(c)))
    )


def render_index(
    cards: list[dict],
    meta: dict,
    constituencies: list[dict],
    government: list[dict] | None = None,
    last_sitting: dict | None = None,
) -> str:
    government = government or []
    by_id = {g["id"]: g for g in government}
    rows = [index_row(c, by_id) for c in cards]
    ids = {c["id"] for c in cards}
    payload = {
        "cards": rows, "meta": meta, "constituencies": constituencies,
        "government": [{**g, "card": g["id"] in ids} for g in government],
        "last_sitting": last_sitting,
    }  # fmt: skip
    return (
        (HERE / "index.html")
        .read_text(encoding="utf-8")
        .replace("__HEADER__", pages.site_header("", "cards"))
        .replace("__DATA__", _json(payload))
    )


def write_site(
    cards: list[dict],
    meta: dict,
    out: Path,
    constituencies: list[dict] | None = None,
    government: list[dict] | None = None,
    last_sitting: dict | None = None,
    decisions: list[dict] | None = None,
    members: dict[str, list[list]] | None = None,
    sittings: list[dict] | None = None,
    clusters: dict[str, dict] | None = None,
) -> dict[str, int]:
    """Write the site; returns the number of vote and sitting pages (empty without the foundation's decisions)."""
    meta = {**meta, "built": dt.date.today().isoformat()}
    out.mkdir(parents=True, exist_ok=True)
    for c in cards:
        (out / f"{c['id']}.html").write_text(render_card(c, meta), encoding="utf-8")
        (out / f"{c['id']}.json").write_text(json.dumps(c, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index = render_index(cards, meta, constituencies or [], government, last_sitting)
    (out / "index.html").write_text(index, encoding="utf-8")
    for name in ASSETS:
        shutil.copyfile(HERE / name, out / name)
    if sittings:
        written = pages.write_pages(out, decisions or [], members or {}, sittings, meta, clusters)
        written["abstimmungen"] += cohesion.write_page(out, decisions or [], members or {})
        return written
    return {}
