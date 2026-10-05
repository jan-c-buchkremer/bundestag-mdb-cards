"""Render the static site: one page and one JSON export per card, the index, and the shared assets."""

from __future__ import annotations

import datetime as dt
import html
import json
import shutil
from pathlib import Path

from research import cohesion, compass, facts, legal, pages, ui
from research.data import DIP_DOC, VOTE_CHOICES, index_row, page_id
from research.ui import VOTE, e, long_date, n

HERE = Path(__file__).parent
# wahlkreise.json: the map, fetched on demand
ASSETS = (
    "shell.css",
    "cards.css",
    "card.js",
    "pages.js",
    "parliament.js",
    "controls.js",
    "wahlkreise.json",
    "search.js",
    "nav.js",
    "places.js",
    "wkmap.js",
    "fragen.js",
    "landing.css",
    "landing.js",
)


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


# ---------------------------------------------------------------- the card's fact tabs (facts.py, D13)

SMALL_GROUP = 10  # up to this many names a Drucksache is a small group's, not the whole fraction's (as card.js)


def _tab(key: str, body: str) -> str:
    return f'<section class="tab" id="tab-{key}">{body}</section>'


def _h2(key: str, title: str, count: int) -> str:
    return f'<h2 id="{key}">{title} <span class="n">{n(count)}</span></h2>'


def _newest(xs: list[dict]) -> list[dict]:
    return sorted(xs, key=lambda x: (x["date"] or "", x["id"]), reverse=True)


def reden_tab(c: dict) -> str:
    """Reden, short contributions, Zwischenfragen, Befragung and Fragestunde turns, each list by facts.speech."""

    def lst(key: str, rows: list[dict], kind: str | None) -> str:
        rows = [{**r, "kind": kind or r.get("kind"), "name": c["name"], "person": c["id"]} for r in _newest(rows)]
        return facts.speech_list(rows, "", f"l-{key}", speaker=False, empty="Keine Reden.")

    parts = [
        '<div class="tools"><input type="search" class="fq" placeholder="Reden durchsuchen: Tagesordnungspunkt, '
        'Datum …" aria-label="Reden durchsuchen"></div>'
        '<p class="explain">Eine Rede ist ein Beitrag von mindestens 500 Zeichen zu einem Tagesordnungspunkt, wie ihn '
        'das Plenarprotokoll '
        "führt. Zwischenfragen anderer gehören zu der Rede, in der sie gestellt wurden. Die "
        "Länge ist in Wörtern angegeben, da das Protokoll keine Redezeit enthält. „Text“ öffnet die ganze Rede, "
        "„Themenlandschaft“ die Rede in der Themenlandschaft ihrer Sitzungswoche.</p>",
        _h2("reden-reden", "Reden", len(c["reden"])) + lst("reden", c["reden"], "rede"),
    ]  # fmt: skip
    if c["kurz"]:
        parts.append(_h2("reden-kurz", "Kurze Wortbeiträge", len(c["kurz"]))
                     + '<p class="explain">Beiträge unter 500 Zeichen, etwa ein Amtseid, eine Erklärung zur Abstimmung '
                     "in einem Satz oder ein Hinweis zur Geschäftsordnung. Sie zählen hier und in der "
                     "Themenlandschaft nicht als Rede.</p>" + lst("kurz", c["kurz"], "kurz"))  # fmt: skip
    if c["fragen"]:
        parts.append(
            _h2("reden-fragen", "Zwischenfragen und Kurzinterventionen", len(c["fragen"]))
            + lst("fragen", c["fragen"], None)
        )
    if c["befragung"]:
        parts.append(_h2("reden-befragung", "Regierungsbefragung", len(c["befragung"]))
                     + '<p class="explain">In der Regierungsbefragung ist jede Frage und jede Antwort ein eigener '
                     "Beitrag im Protokoll; sie zählen deshalb nicht als Reden.</p>"
                     + lst("befragung", c["befragung"], "befragung"))  # fmt: skip
    if c["fragestunde"]:
        parts.append(_h2("reden-fragestunde", "Fragestunde", len(c["fragestunde"]))
                     + '<p class="explain">In der Fragestunde ist jede Frage, jede Antwort und jede Nachfrage ein '
                     "eigener Beitrag im Protokoll; sie zählen deshalb nicht als Reden.</p>"
                     + lst("fragestunde", c["fragestunde"], "fragestunde"))  # fmt: skip
    return _tab("reden", "".join(parts))


def _vote_decision(v: dict, decisions: dict[str, dict]) -> dict:
    """The decision a member's roll-call vote belongs to; without the foundation's decisions, one made from the
    vote list itself, linked to the list."""
    d = decisions.get(v["id"])
    if d is not None:
        return d
    return {"id": v["id"], "page": page_id(v["id"]), "kind": "namentlich", "date": v["date"], "title": v["title"],
            "result": v["outcome"], "result_from": v["outcome_from"], "counts": v["result"], "fractions": None,
            "house": None, "drucksachen": [], "agenda": None, "sitting": None, "subject": None,
            "href": v["pdf"] or v["xlsx"]}  # fmt: skip


def votes_tab(c: dict, meta: dict, decisions: dict[str, dict]) -> str:
    votes = _newest(c["votes"])
    cast = [v for v in votes if v["vote"] in VOTE_CHOICES]
    with_line = [v for v in cast if v["line"]]
    dev = [v for v in votes if v["deviates"]]
    passed = sum(1 for v in votes if v["outcome"] == "angenommen")
    own = " · ".join(f"<b>{n(k)}</b> {VOTE[x] if x != 'absent' else 'nicht abgestimmt'}"
                     for x in (*VOTE_CHOICES, "absent") if (k := sum(1 for v in votes if v["vote"] == x)))  # fmt: skip
    stats = (f'<div class="vstats"><div><span class="k">Ergebnis im Bundestag</span><b>{n(passed)}</b> angenommen · '
             f"<b>{n(sum(1 for v in votes if v['outcome'] == 'abgelehnt'))}</b> abgelehnt</div>"
             f'<div><span class="k">Eigene Stimme</span>{own}</div>'
             + (f'<div><span class="k">Mit der eigenen Fraktion</span><b>{n(len(with_line) - len(dev))}</b>-mal wie '
                f"die Mehrheit · <b>{n(len(dev))}</b>-mal abweichend</div>"
                if c["fraction"] != "fraktionslos" and with_line else "") + "</div>")  # fmt: skip
    absent = sum(1 for v in votes if v["vote"] == "absent")
    body = (
        f'<p class="explain">Namentlich abgestimmt wird nur, wenn eine Fraktion oder 5 % der Mitglieder es verlangen, '
        f"seit {e(long_date(meta['sittings']['from']))} {n(meta['votes'])}-mal. Jede Zeile zeigt das Ergebnis "
        "im ganzen Haus und rechts die eigene Stimme mit dem Hinweis, ob sie der Mehrheit der eigenen Fraktion "
        "entsprach. Der Titel führt zur Abstimmung.</p>" + stats
        + (f'<p class="explain">„Nicht abgestimmt“ ({n(absent)}-mal) nennt keinen Grund. Krankheit, '
           "Elternzeit, Dienstreisen und Pairing-Absprachen stehen nicht in den Listen.</p>" if absent else "")
        + f'<div class="tools"><label><input type="checkbox" class="fonly"> nur Abweichungen von der '
        f"Fraktionsmehrheit ({n(len(dev))})</label></div>"
        + facts.decision_list([_vote_decision(v, decisions) for v in votes], "", "l-votes", limit=100,
                              empty="Keine namentlichen Abstimmungen.", own_by_id={v["id"]: v for v in votes})
    )  # fmt: skip
    return _tab("abstimmungen", body)


def documents_tab(c: dict, meta: dict) -> str:
    dip = meta["dip"]
    span = (f"Drucksachen aus DIP vom {long_date(dip['from'])} bis {long_date(dip['to'])}" if dip["n"]
            else "Noch keine Drucksachen aus DIP geladen")  # fmt: skip

    def rows(xs: list[dict]) -> list[dict]:
        return [{**d, "url": DIP_DOC.format(d["id"])} for d in _newest(xs)]

    docs = [d for d in c["authored"] if d["activity"] != "Frage"]
    questions = [d for d in c["authored"] if d["activity"] == "Frage"]
    small = sum(1 for d in docs if d["authors"] and d["authors"] <= SMALL_GROUP)
    parts = [
        f'<p class="explain">{e(span)}. Eine Drucksache zählt hier, wenn DIP diese Person als Urheber führt (Antrag, '
        "Kleine Anfrage, Entschließungs- und Änderungsantrag, Gesetzentwurf, schriftliche Frage). Fraktionsanträge "
        "tragen oft die Namen der ganzen Fraktion. Die Zahl der Namen zeigt, ob eine Drucksache von wenigen oder von "
        "allen stammt.</p>",
        "" if dip["complete"] else '<p class="explain">Die Drucksachen aus DIP werden gerade für die '
        "ganze Wahlperiode nachgeladen. Bis dahin fehlen einzelne Monate, deshalb nennt der Steckbrief oben noch keine "
        "Zahlen.</p>",
        _h2("drucksachen-eigene", "Anträge, Anfragen, Gesetzentwürfe", len(docs)),
        (f'<div class="tools"><label><input type="checkbox" class="fonly"> nur Drucksachen mit höchstens '
         f"{SMALL_GROUP} Namen ({n(small)})</label></div>" if docs else ""),
        facts.drucksache_list(rows(docs), "", "l-drs", compact=False, own=True),
    ]  # fmt: skip
    if questions:
        parts.append(_h2("drucksachen-fragen", "Schriftliche Fragen", len(questions))
                     + '<p class="explain">Schriftliche Fragen erscheinen gesammelt in einer Drucksache je Woche. Der '
                     "Link führt zu dieser Sammlung.</p>"
                     + facts.drucksache_list(rows(questions), "", "l-fragen", compact=False, own=True))  # fmt: skip
    if c["reported"]:
        parts.append(_h2("drucksachen-berichte", "Berichterstattung", len(c["reported"]))
                     + '<p class="explain">Als Berichterstatterin oder Berichterstatter eines Ausschusses auf einer '
                     "Beschlussempfehlung genannt. Berichterstattung ist eine Aufgabe im Ausschuss und zählt nicht "
                     "als Urheberschaft.</p>"
                     + facts.drucksache_list(rows(c["reported"]), "", "l-berichte", compact=False))  # fmt: skip
    return _tab("drucksachen", "".join(parts))


def card_tabs(c: dict, meta: dict, decisions: dict[str, dict] | None = None) -> str:
    """The card's fact tabs, written into the page by the shared components; card.js shows and filters them."""
    member = c["kind"] == "member"
    heard = any(c[k] for k in ("reden", "kurz", "fragen", "befragung", "fragestunde"))
    parts = [reden_tab(c)] if member or heard else []
    if member:
        parts += [votes_tab(c, meta, decisions or {}), documents_tab(c, meta)]
    return "".join(parts)


def render_card(c: dict, meta: dict, decisions: dict[str, dict] | None = None) -> str:
    title = f"{c['name']} – {c['fraction'] or c['role'] or 'Bundestag'}"
    return (
        (HERE / "card.html")
        .read_text(encoding="utf-8")
        .replace("__TITLE__", html.escape(title))
        .replace("__DESC__", html.escape(description(c)))
        .replace("__ID__", html.escape(c["id"]))
        .replace("__CARD__", _json(c))
        .replace("__META__", _json(meta))
        .replace("__HEADER__", ui.site_header("", "cards"))
        .replace("__TABS__", card_tabs(c, meta, decisions))
    )


def render_index(
    cards: list[dict],
    meta: dict,
    government: list[dict] | None = None,
    last_sitting: dict | None = None,
    places: dict | None = None,
    roles: str = "",
) -> str:
    """The Abgeordnete page: the plenum (or the list), the filters with the place filter (`places`, places.py
    index_payload) and the Rollen section (`roles`, careers.py), written into the page as HTML."""
    government = government or []
    by_id = {g["id"]: g for g in government}
    rows = [index_row(c, by_id) for c in cards]
    ids = {c["id"] for c in cards}
    places = places or {"lands": {}, "wahlkreise": {}, "members": {}}
    payload = {
        "cards": rows, "meta": meta,
        "government": [{**g, "card": g["id"] in ids} for g in government],
        "last_sitting": last_sitting,
        "places": places,
    }  # fmt: skip
    slugs = {code: x["slug"] for code, x in places["lands"].items()}
    return (
        (HERE / "index.html")
        .read_text(encoding="utf-8")
        .replace("__HEADER__", ui.site_header("", "cards"))
        .replace("__SLUGS__", _json(slugs))
        .replace("__ROLES__", roles)
        .replace("__LANDSCAPE_HREF__", html.escape(ui.LANDSCAPE))
        .replace("__LANDSCAPE__", _json(ui.LANDSCAPE))
        .replace("__DATA__", _json(payload))
    )


def write_site(
    cards: list[dict],
    meta: dict,
    out: Path,
    government: list[dict] | None = None,
    last_sitting: dict | None = None,
    decisions: list[dict] | None = None,
    members: dict[str, list[list]] | None = None,
    sittings: list[dict] | None = None,
    clusters: dict[str, dict] | None = None,
    places: dict | None = None,
    roles: str = "",
) -> dict[str, int]:
    """Write the site; returns the number of vote and sitting pages (empty without the foundation's decisions)."""
    meta = {**meta, "built": dt.date.today().isoformat()}
    out.mkdir(parents=True, exist_ok=True)
    by_id = {d["id"]: d for d in decisions or []}
    for c in cards:
        (out / f"{c['id']}.html").write_text(render_card(c, meta, by_id), encoding="utf-8")
        (out / f"{c['id']}.json").write_text(json.dumps(c, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    index = render_index(cards, meta, government, last_sitting, places, roles)
    (out / "abgeordnete.html").write_text(index, encoding="utf-8")
    for name in ASSETS:
        shutil.copyfile(HERE / name, out / name)
    shutil.copytree(HERE / "fonts", out / "fonts", dirs_exist_ok=True)
    legal.write(out)
    if sittings:
        quiz = compass.questions(decisions or [], members or {})
        written = pages.write_pages(out, decisions or [], members or {}, sittings, meta, clusters, bool(quiz))
        days = [s["date"] for s in sittings]
        written["abstimmungen"] += cohesion.write_page(out, decisions or [], members or {}, days)
        written.update(compass.write(out, quiz, cards, places))
        return written
    return {}
