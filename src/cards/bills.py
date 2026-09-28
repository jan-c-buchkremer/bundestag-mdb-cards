"""Gesetze: `gesetze/index.html` and one page per DIP Vorgang of type Gesetzgebung, `gesetze/<vorgang id>.html`.

A bill page joins what the store has on the Vorgang: its Drucksachen, the agenda items that name one of them (with
their speeches), the decisions and roll-call votes on them, and a timeline. With the foundation's `vorgang_position`
the timeline is DIP's Vorgangsablauf (Bundesrat and Verkündung included); without it, the timeline is made from the
Drucksache dates, the debates and the decisions in the store. Links go only to pages that were written."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from cards.data import WP, drucksache_pdf, has_table, page_id, top_label
from cards.pages import FOOTER, e, n, positions_line, shell, short_date
from cards.speeches import rede_id
from cards.titles import short_title

KIND = "Gesetzgebung"
_PARTY = re.compile(r"\s*\([^)]*\)\s*$")  # "Stefan Möller (AfD)" -> "Stefan Möller"
CHAMBER = {"BT": "Bundestag", "BR": "Bundesrat", "BV": "Bundesversammlung", "EP": "Europäisches Parlament"}
STYLE = """<style>
.bills .row .l { white-space: normal; max-width: 40vw; }
.bills .st { display: inline-block; font-size: 12px; padding: 1px 7px; border-radius: 9px;
  background: var(--chip, #eef0f3); color: var(--muted); }
.bills table.plenum td.l { text-align: left; white-space: normal; }
.bills ol.tl { list-style: none; padding: 0; margin: 8px 0; border-left: 2px solid var(--line, #dde); }
.bills ol.tl li { margin: 0 0 10px; padding-left: 12px; position: relative; font-size: 14px; }
.bills ol.tl li::before { content: ""; position: absolute; left: -6px; top: 6px; width: 10px; height: 10px;
  border-radius: 50%; background: var(--muted, #888); }
.bills ol.tl li.BR::before { background: #b45309; }
.bills ol.tl .d { font-variant-numeric: tabular-nums; color: var(--muted); margin-right: 6px; }
.bills ol.tl .ch { font-size: 12px; color: var(--muted); }
.bills .deb details { margin: 4px 0 10px; font-size: 13px; }
.bills .deb summary { cursor: pointer; color: var(--muted); }
.bills .deb ol { padding-left: 20px; margin: 6px 0; }
.bills .meta div { margin: 2px 0; }
</style>"""
FILTER_JS = """<script>
(() => {
  const q = document.getElementById("bq"), st = document.getElementById("bst");
  const count = document.getElementById("bcount");
  const rows = [...document.querySelectorAll("#bills a.row")];
  function apply() {
    const words = q.value.toLowerCase().split(/\\s+/).filter(Boolean);
    let shown = 0;
    for (const r of rows) {
      const text = r.textContent.toLowerCase();
      const ok = (!st.value || r.dataset.status === st.value) && words.every((w) => text.includes(w));
      r.hidden = !ok;
      shown += ok;
    }
    count.textContent = shown === rows.length ? `${rows.length} Gesetzesvorhaben` : `${shown} von ${rows.length}`;
  }
  q.addEventListener("input", apply);
  st.addEventListener("change", apply);
  apply();
})();
</script>"""


def _json_list(s: str | None) -> list:
    try:
        v = json.loads(s or "[]")
    except ValueError:
        return []
    return v if isinstance(v, list) else []


def load(conn: sqlite3.Connection) -> list[dict]:
    """Every Gesetzgebung Vorgang of the Wahlperiode with its Drucksachen, debates, decisions, roll-call votes and
    positions (None when the store has no `vorgang_position`), newest activity first."""
    bills = {
        r["id"]: {
            "id": r["id"], "title": r["title"], "status": r["status"] or "unbekannt",
            "subjects": _json_list(r["subjects"]), "initiators": _json_list(r["initiators"]),
            "source": r["source_url"], "docs": [], "debates": [], "decisions": [], "votes": [], "positions": None,
        }
        for r in conn.execute("SELECT * FROM vorgang WHERE wahlperiode = ? AND type = ? ORDER BY id", (WP, KIND))
    }  # fmt: skip
    if not bills:
        return []
    for r in conn.execute(
        """SELECT vd.vorgang_id, d.number, d.type, d.date, d.pdf_url, d.publisher,
                  (SELECT count(*) FROM vorgang_drucksache x WHERE x.drucksache_id = d.id) AS shared
           FROM vorgang_drucksache vd JOIN drucksache d ON d.id = vd.drucksache_id ORDER BY d.date, d.number"""
    ):
        if r["vorgang_id"] in bills:
            url = r["pdf_url"] or (drucksache_pdf(r["number"]) if (r["publisher"] or "BT") == "BT" else None)
            bills[r["vorgang_id"]]["docs"].append({
                "number": r["number"], "type": r["type"] or "Drucksache", "date": r["date"], "url": url,
                # an Unterrichtung shared by several Vorgänge lists referred bills (§ 80 GO-BT): not matched
                "publisher": r["publisher"] or "BT", "collective": r["type"] == "Unterrichtung" and r["shared"] > 1,
            })  # fmt: skip
    by_number: dict[str, set[str]] = defaultdict(set)
    for b in bills.values():
        for d in b["docs"]:
            if d["publisher"] == "BT" and not d["collective"]:
                by_number[d["number"]].add(b["id"])

    redes: dict[str, list[dict]] = defaultdict(list)
    seen: set[str] = set()
    for r in conn.execute(
        "SELECT id, agenda_item_id, speaker_name, fraction FROM speech ORDER BY sitting_id, position"
    ):
        rid = rede_id(r["id"])
        if r["agenda_item_id"] and rid not in seen:
            seen.add(rid)
            name = _PARTY.sub("", r["speaker_name"]).split(",")[0].strip()
            redes[r["agenda_item_id"]].append({"id": rid, "name": name, "fraction": r["fraction"]})
    for r in conn.execute(
        """SELECT a.id, a.sitting_id, a.position, a.top_id, a.title, a.drucksache_numbers, s.date FROM agenda_item a
           JOIN sitting s ON s.id = a.sitting_id WHERE s.wahlperiode = ? ORDER BY s.date, a.position""",
        (WP,),
    ):
        numbers = [x for x in _json_list(r["drucksache_numbers"]) if x in by_number]
        for vid in sorted({v for x in numbers for v in by_number[x]}):
            bills[vid]["debates"].append({
                "id": r["id"], "sitting": r["sitting_id"], "position": r["position"], "date": r["date"],
                "label": top_label(r["top_id"]), "title": short_title(r["title"], r["top_id"]),
                "numbers": numbers, "speeches": redes.get(r["id"], []),
            })  # fmt: skip

    rcv = {r["id"]: r for r in conn.execute("SELECT * FROM roll_call_vote")}
    covered: set[str] = set()
    if has_table(conn, "decision"):
        positions: dict[str, dict[str, str]] = defaultdict(dict)
        for r in conn.execute("SELECT decision_id, fraction, position FROM decision_fraction"):
            positions[r["decision_id"]][r["fraction"]] = r["position"]
        for r in conn.execute(
            """SELECT d.*, s.date FROM decision d JOIN sitting s ON s.id = d.sitting_id ORDER BY s.date, d.position"""
        ):
            v = rcv.get(r["roll_call_vote_id"] or "")
            vids = set(by_number.get(r["drucksache_number"] or "", ()))
            if v is not None and v["vorgang_id"] in bills:
                vids.add(v["vorgang_id"])
            if v is not None:
                covered.add(v["id"])
            for vid in vids:
                bills[vid]["decisions"].append({
                    "id": r["id"], "date": r["date"], "kind": r["kind"], "subject": r["subject"],
                    "number": r["drucksache_number"], "result": r["result"], "fractions": positions.get(r["id"], {}),
                    "counts": None if v is None else {c: v[c] for c in ("yes", "no", "abstain")},
                })  # fmt: skip
    for v in rcv.values():
        if v["id"] in covered:
            continue
        vids = set(by_number.get(v["drucksache_number"] or "", ()))
        if v["vorgang_id"] in bills:
            vids.add(v["vorgang_id"])
        for vid in vids:
            bills[vid]["votes"].append({"id": v["id"], "date": v["date"], "title": v["title"],
                                        "counts": {c: v[c] for c in ("yes", "no", "abstain")}})  # fmt: skip

    if has_table(conn, "vorgang_position"):
        for b in bills.values():
            b["positions"] = []
        for r in conn.execute("SELECT * FROM vorgang_position ORDER BY date, id"):
            if r["vorgang_id"] in bills:
                bills[r["vorgang_id"]]["positions"].append({
                    "date": r["date"], "position": r["position"], "chamber": r["chamber"],
                    "kind": r["document_kind"], "number": r["document_number"], "doc_type": r["document_type"],
                    "url": r["pdf_url"], "pages": r["pages"], "originators": _json_list(r["originators"]),
                    "decisions": _json_list(r["decisions"]),
                })  # fmt: skip
    out = list(bills.values())
    for b in out:
        b["timeline"] = timeline(b)
        b["latest"] = max((t["date"] for t in b["timeline"]), default="")
    out.sort(key=lambda b: (b["latest"], b["id"]), reverse=True)
    return out


def timeline(b: dict) -> list[dict]:
    """Steps by date: DIP's positions when the store has them, else Drucksachen, debates and decisions.
    Each step is {date, chamber, what, doc (label, url) or None, sitting (id, position) or None, note}."""
    steps = []
    if b["positions"] is not None:
        top = {}  # sitting -> position of the first agenda item there that names one of the bill's Drucksachen
        for a in b["debates"]:
            top.setdefault(a["sitting"], a["position"])
        for p in b["positions"]:
            doc = None
            if p["number"]:
                label = "Drucksache" if p["kind"] == "Drucksache" else "Plenarprotokoll"
                prefix = "BR-" if p["chamber"] == "BR" else ""
                pages = f", S. {p['pages']}" if p["pages"] else ""
                doc = (f"{prefix}{label} {p['number']}{pages}", p["url"])
            sitting = None
            if p["kind"] == "Plenarprotokoll" and p["chamber"] == "BT" and p["number"]:
                sitting = (p["number"], top.get(p["number"]))
            tenor = "; ".join(
                str(x["beschlusstenor"]) + (f" ({x['dokumentnummer']})" if x.get("dokumentnummer") else "")
                for x in p["decisions"] if isinstance(x, dict) and x.get("beschlusstenor")
            )  # fmt: skip
            steps.append({"date": p["date"], "chamber": p["chamber"] or "", "what": p["position"], "doc": doc,
                          "sitting": sitting, "note": tenor})  # fmt: skip
        return steps
    for d in b["docs"]:
        steps.append({"date": d["date"], "chamber": d["publisher"], "what": d["type"],
                      "doc": (f"Drucksache {d['number']}", d["url"]), "sitting": None, "note": ""})  # fmt: skip
    for a in b["debates"]:
        steps.append({"date": a["date"], "chamber": "BT", "what": f"Beratung im Plenum ({a['label']})", "doc": None,
                      "sitting": (a["sitting"], a["position"]), "note": ""})  # fmt: skip
    for d in b["decisions"]:
        steps.append({"date": d["date"], "chamber": "BT", "what": "Beschluss" + (f" über {d['number']}" if d["number"]
                      else ""), "doc": None, "sitting": None, "note": d["result"] or ""})  # fmt: skip
    for v in b["votes"]:
        steps.append({"date": v["date"], "chamber": "BT", "what": "Namentliche Abstimmung", "doc": None,
                      "sitting": None, "note": ""})  # fmt: skip
    return sorted(steps, key=lambda s: s["date"])


# ---------------------------------------------------------------- pages


def _link(href: str | None, text: str) -> str:
    return f'<a href="{e(href)}">{text}</a>' if href else text


def _counts(c: dict | None) -> str:
    if not c:
        return ""
    return f" · {n(c['yes'])} Ja, {n(c['no'])} Nein, {n(c['abstain'])} Enthaltungen"


def bill_page(b: dict, have: set[str]) -> str:
    """One bill; `have` holds the site paths ("sitzungen/21-88.html") that exist, so every link resolves."""

    def sitting_href(sid: str, position: int | None) -> str | None:
        path = f"sitzungen/{page_id(sid)}.html"
        if path not in have:
            return None
        return f"../{path}" + (f"#top-{position}" if position is not None else "")

    def vote_href(vid: str) -> str | None:
        path = f"abstimmungen/{page_id(vid)}.html"
        return f"../{path}" if path in have else None

    meta = [f'<div><span class="k">Stand</span> <span class="st">{e(b["status"])}</span></div>']
    if b["initiators"]:
        meta.append(f'<div><span class="k">Eingebracht von</span> {e(", ".join(b["initiators"]))}</div>')
    if b["subjects"]:
        meta.append(f'<div><span class="k">Sachgebiete</span> {e(", ".join(b["subjects"]))}</div>')
    dip = f"https://dip.bundestag.de/vorgang/{e(b['id'])}"
    parts = [
        f'<p class="crumbs"><a href="index.html">Gesetze</a></p><section class="card"><h1>{e(b["title"])}</h1>'
        f'<div class="lines meta">{"".join(meta)}</div><div class="links"><a href="{dip}">Vorgang im DIP ↗</a>'
        "</div></section>"
    ]
    steps = "".join(
        f'<li class="{e(s["chamber"])}"><span class="d">{short_date(s["date"])}</span> '
        + _link(sitting_href(*s["sitting"]) if s["sitting"] else None, e(s["what"]))
        + (f' <span class="ch">{e(CHAMBER.get(s["chamber"], s["chamber"]))}</span>' if s["chamber"] else "")
        + (f" · {_link(s['doc'][1], e(s['doc'][0]))}" if s["doc"] else "")
        + (f" · {e(s['note'])}" if s["note"] else "")
        + "</li>"
        for s in b["timeline"]
    )
    if b["positions"] is not None:
        how = "Die Schritte stammen aus dem Vorgangsablauf im DIP"
        if any(p["chamber"] == "BR" for p in b["positions"]):
            how += ", auch die im Bundesrat."
        else:
            how += ". Schritte im Bundesrat und die Verkündung sind noch nicht im Datenbestand, sie stehen im DIP."
    else:
        how = (
            "Zusammengestellt aus den Daten der Drucksachen, den Tagesordnungspunkten und den Beschlüssen im "
            "Datenbestand; Schritte im Bundesrat und die Verkündung fehlen hier, sie stehen im DIP."
        )
    parts.append(f'<h2>Ablauf</h2><p class="explain">{how}</p><ol class="tl">{steps}</ol>')
    if b["docs"]:
        rows = "".join(
            f'<tr><td>{short_date(d["date"])}</td><td class="l">{e(d["type"])}</td>'
            f"<td>{_link(d['url'], e(d['number']))}</td></tr>"
            for d in b["docs"]
        )
        parts.append('<h2>Drucksachen</h2><div class="rows"><table class="plenum"><thead><tr><th>Datum</th>'
                     f"<th>Art</th><th>Nummer</th></tr></thead><tbody>{rows}</tbody></table></div>")  # fmt: skip
    if b["debates"]:
        items = []
        for a in b["debates"]:
            num = a["sitting"].split("/")[1]
            head = (f'<b>{short_date(a["date"])}</b>, {_link(sitting_href(a["sitting"], a["position"]),
                    f"{e(num)}. Sitzung, {e(a['label'])}")}: {e(a["title"])}')  # fmt: skip
            sp = a["speeches"]
            if sp:
                lis = "".join(
                    "<li>" + _link(f"../reden/{e(s['id'])}.html" if f"reden/{s['id']}.html" in have else None,
                                   e(s["name"])) + (f" ({e(s['fraction'])})" if s["fraction"] else "") + "</li>"
                    for s in sp
                )  # fmt: skip
                word = "Rede" if len(sp) == 1 else "Reden"
                head += f"<details><summary>{n(len(sp))} {word}</summary><ol>{lis}</ol></details>"
            else:
                head += '<div class="faint">keine Reden im Datenbestand</div>'
            items.append(f"<div>{head}</div>")
        parts.append(
            '<h2>Beratungen im Plenum</h2><p class="explain">Tagesordnungspunkte, die eine Drucksache dieses '
            f'Vorgangs nennen.</p><div class="deb">{"".join(items)}</div>'
        )
    if b["decisions"] or b["votes"]:
        rows = []
        for d in b["decisions"]:
            how = "namentlich" if d["kind"] == "namentlich" else "per Handzeichen"
            line = positions_line(d["fractions"]) if d["fractions"] else ""
            subj = f"{e(d['subject'])}" + (f" (Drs. {e(d['number'])})" if d["number"] else "")
            rows.append(
                f"<li><b>{short_date(d['date'])}</b> "
                + _link(vote_href(d["id"]), f"{e(d['result'] or 'ohne Ergebnis')}, {how}")
                + f": {subj}{_counts(d['counts'])}"
                + (f"<br>{line}" if line else "")
                + "</li>"
            )
        for v in b["votes"]:
            rows.append(f"<li><b>{short_date(v['date'])}</b> " + _link(vote_href(v["id"]), "namentliche Abstimmung")
                        + f": {e(v['title'])}{_counts(v['counts'])}</li>")  # fmt: skip
        parts.append(
            '<h2>Beschlüsse</h2><p class="explain">Beschlüsse des Bundestages über eine Drucksache dieses Vorgangs, '
            "wie sie im Plenarprotokoll stehen; bei Handzeichen nur die Haltung der Fraktionen.</p>"
            f'<ul class="decl">{"".join(rows)}</ul>'
        )
    parts.append(f"<footer>{FOOTER}</footer>")
    return shell(root="../", kind="p-bill", active="bills", title=b["title"][:120],
                 desc=f"Gesetzgebung im 21. Bundestag: {b['title'][:200]}. Stand: {b['status']}.",
                 body=f'<div class="bills">{"".join(parts)}</div>', data={"kind": "bill", "id": b["id"]},
                 head=STYLE)  # fmt: skip


def index_page(bills: list[dict]) -> str:
    status = Counter(b["status"] for b in bills)
    options = "".join(f'<option value="{e(s)}">{e(s)} ({k})</option>' for s, k in status.most_common())
    table = "".join(f'<tr><td class="l">{e(s)}</td><td>{n(k)}</td></tr>' for s, k in status.most_common())
    rows = "".join(
        f'<a class="row" href="{e(b["id"])}.html" data-status="{e(b["status"])}"><span class="d">'
        f'{short_date(b["latest"]) if b["latest"] else ""}</span><span class="t"><span class="ti">{e(b["title"])}'
        f'</span><span class="sub">{e(", ".join(b["initiators"][:3]))}'
        f'{" …" if len(b["initiators"]) > 3 else ""}</span></span><span class="l"><span class="st">{e(b["status"])}'
        "</span></span></a>"
        for b in bills
    )
    body = f"""<div class="bills"><h1>Gesetze</h1>
<p class="lead">Ein Gesetz beginnt als Gesetzentwurf – von der Bundesregierung, aus der Mitte des Bundestages (meist von Fraktionen) oder vom Bundesrat. Der Bundestag berät es in der Regel dreimal im Plenum und dazwischen in den Ausschüssen, dann stimmt er ab. Danach ist der Bundesrat dran; zuletzt wird das Gesetz ausgefertigt und im Bundesgesetzblatt verkündet. Hier stehen alle {n(len(bills))} Gesetzgebungsvorgänge des 21. Bundestages aus dem DIP, der zuletzt bewegte zuerst, mit ihren Drucksachen, Debatten und Abstimmungen.</p>
<details class="open"><summary>Wie viele Vorhaben in welchem Stand sind</summary><div class="rows"><table class="plenum"><thead><tr><th>Stand im DIP</th><th>Vorgänge</th></tr></thead><tbody>{table}</tbody></table></div></details>
<div class="filters"><input type="search" id="bq" placeholder="Titel oder Einbringer …" autocomplete="off"><select id="bst"><option value="">jeder Stand</option>{options}</select></div>
<div class="count" id="bcount"></div>
<div class="rows" id="bills">{rows}</div></div>
<footer>{FOOTER}</footer>
{FILTER_JS}"""  # noqa: E501
    return shell(root="../", kind="p-bills", active="bills", title="Gesetze im Bundestag",
                 desc="Alle Gesetzgebungsvorgänge des 21. Deutschen Bundestages mit Stand, Drucksachen, Debatten und "
                      "Abstimmungen.", body=body, data={"kind": "bills"}, head=STYLE)  # fmt: skip


def write(conn: sqlite3.Connection, out: Path) -> dict[str, int]:
    """Write gesetze/; call after the sitting, vote and speech pages so the links can be checked against them.
    Returns {"gesetze": pages}, or {} when the store has no Vorgang of type Gesetzgebung."""
    if not has_table(conn, "vorgang"):
        return {}
    bills = load(conn)
    if not bills:
        return {}
    have = {
        f"{d}/{p.name}"
        for d in ("sitzungen", "abstimmungen", "reden")
        if (out / d).is_dir()
        for p in (out / d).iterdir()
    }
    d = out / "gesetze"
    d.mkdir(parents=True, exist_ok=True)
    for b in bills:
        (d / f"{b['id']}.html").write_text(bill_page(b, have), encoding="utf-8")
    (d / "index.html").write_text(index_page(bills), encoding="utf-8")
    return {"gesetze": len(bills) + 1}
