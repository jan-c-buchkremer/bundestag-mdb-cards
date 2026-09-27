"""Render the static site: one page and one JSON export per card, the index, and the shared assets."""

from __future__ import annotations

import datetime as dt
import html
import json
import shutil
from pathlib import Path

from cards.data import index_row

HERE = Path(__file__).parent
ASSETS = ("cards.css", "card.js")


def _json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", r"<\/")


def description(c: dict) -> str:
    """One plain sentence for <meta description> and link previews; the page itself renders from the data."""
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
    )


def render_index(cards: list[dict], meta: dict, constituencies: list[dict]) -> str:
    rows = [index_row(c) for c in cards]
    payload = {"cards": rows, "meta": meta, "constituencies": constituencies}
    return (HERE / "index.html").read_text(encoding="utf-8").replace("__DATA__", _json(payload))


def write_site(cards: list[dict], meta: dict, out: Path, constituencies: list[dict] | None = None) -> None:
    meta = {**meta, "built": dt.date.today().isoformat()}
    out.mkdir(parents=True, exist_ok=True)
    for c in cards:
        (out / f"{c['id']}.html").write_text(render_card(c, meta), encoding="utf-8")
        (out / f"{c['id']}.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "index.html").write_text(render_index(cards, meta, constituencies or []), encoding="utf-8")
    for name in ASSETS:
        shutil.copyfile(HERE / name, out / name)
