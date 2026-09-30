"""Vorgänge (procedures): `vorgaenge/index.html` and one page per DIP Vorgang that reaches the plenum,
`vorgaenge/<vorgang id>.html` (docs/plan.md section 11, D14): every Gesetzgebung, and every other Vorgang (Antrag,
Entschließungsantrag, Beschlussempfehlung, …) with a debate or a decision in the store. The former Gesetze pages
(`gesetze/`) are stubs to these.

A Vorgang page is an entity page: a header, then its timeline (tabled → Beratungen → Ausschuss → Abstimmungen →
Bundesrat → Verkündung) with every decision on it as a point with the full vote (#abst-<page id>, D15), its
speeches by debate and its Drucksachen. An agenda item can carry Vorlagen of several Vorgänge, a Vorgang is debated
under several agenda items or sub-items, and a decision is a point here only when it belongs to this Vorgang alone:
the links come from data.sittings (the Vorgänge of each item and sub-item) and data.decisions (the Vorgänge of each
decision), not from assuming TOP = Vorgang or vote = Vorgang. With the foundation's `vorgang_position` the steps are
DIP's Vorgangsablauf (Bundesrat included); without it they are made from the Drucksachen and debates in the store.
Links go only to pages that were written."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from cards import facts, redirects, urls
from cards.data import WP, _has_column, drucksache_pdf, has_table, page_id
from cards.ui import FOOTER, crumbs, e, entity_header, facet, frac_link, n, shell, short_date

GESETZ = "Gesetzgebung"
CHAMBER = {"BT": "Bundestag", "BR": "Bundesrat", "BV": "Bundesversammlung", "EP": "Europäisches Parlament"}
_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})
_SLUG = re.compile(r"[^a-z0-9]+")
DIP_VORGANG = "https://dip.bundestag.de/vorgang/{}"
DIP_DOC = "https://dip.bundestag.de/drucksache/x/{}"
# the phases of the timeline, in the order of the procedure; steps of one day are sorted by them
PHASES = ("Eingebracht", "Beratung", "Ausschuss", "Abstimmung", "Bundesrat", "Verkündung")

# DIP's Beratungsstand values for Gesetzgebung (checked against the dev store, 21. WP: 14 values plus the "unbekannt"
# fallback for a Vorgang without one), in the order of "So entsteht ein Gesetz" below. Sources: see GLOSSARY_SOURCES.
STATUS_GLOSSARY = {
    "Noch nicht beraten": "Der Entwurf kommt aus der Mitte des Bundestages – von einer Fraktion oder mindestens "
        "5 % der Abgeordneten – und wartet auf seine erste Beratung im Plenum.",
    "Dem Bundestag zugeleitet - Noch nicht beraten": "Der Entwurf kommt von der Bundesregierung oder vom "
        "Bundesrat und ist dem Bundestag förmlich zugeleitet (Art. 76 GG); bei einem Regierungsentwurf ist dem "
        "meist der „1. Durchgang“ im Bundesrat vorausgegangen. Die erste Beratung im Plenum steht noch aus.",
    "1. Durchgang im Bundesrat abgeschlossen": "Ein Regierungsentwurf geht zuerst zur Stellungnahme an den "
        "Bundesrat, der dafür sechs, bei umfangreichen Vorhaben neun Wochen Zeit hat (Art. 76 Abs. 2 GG). Dieser "
        "„erste Durchgang“ ist beendet; die Bundesregierung leitet den Entwurf jetzt mit ihrer Gegenäußerung an "
        "den Bundestag weiter.",
    "In der Beratung (Einzelheiten siehe Vorgangsablauf)": "Ein Sammelstand des DIP für einen laufenden "
        "Verfahrensschritt, der sich keinem der anderen Stände zuordnen lässt; die Einzelheiten stehen im Ablauf "
        "auf dieser Seite oder im Vorgang im DIP.",
    "Überwiesen": "Nach der ersten Beratung hat der Bundestag den Entwurf zur weiteren Beratung an einen oder "
        "mehrere Ausschüsse überwiesen. Dort wird er im Detail beraten, oft mit einer öffentlichen Anhörung von "
        "Sachverständigen, bevor der federführende Ausschuss dem Plenum eine Beschlussempfehlung vorlegt.",
    "Beschlussempfehlung liegt vor": "Der federführende Ausschuss hat seine Beratung mit einer "
        "Beschlussempfehlung und einem Bericht an das Plenum abgeschlossen. In der zweiten und dritten Beratung "
        "stimmt der Bundestag über diese – gegebenenfalls geänderte – Fassung ab, nicht mehr über den "
        "ursprünglichen Entwurf.",
    "Verabschiedet": "Der Bundestag hat den Entwurf in der Schlussabstimmung der dritten Beratung beschlossen. "
        "Er ist noch kein Gesetz: Er geht jetzt zum Bundesrat (der „zweite Durchgang“) und muss danach noch "
        "ausgefertigt und verkündet werden.",
    "Abgelehnt": "Der Bundestag hat den Entwurf in der Schlussabstimmung abgelehnt. Das Verfahren ist damit "
        "beendet.",
    "Für erledigt erklärt": "Der Bundestag hat die Beratung ausdrücklich beendet, ohne in der Sache zu "
        "entscheiden, etwa weil ein anderer, weitergehender Entwurf zum selben Thema angenommen wurde. Spätestens "
        "am Ende der Wahlperiode gilt ohnehin die Diskontinuität (§ 125 GO-BT): Unerledigte Vorlagen verfallen "
        "dann und müssten im neuen Bundestag neu eingebracht werden.",
    "Bundesrat hat Vermittlungsausschuss nicht angerufen": "Nach der Verabschiedung im Bundestag konnte der "
        "Bundesrat den Vermittlungsausschuss anrufen, hat das aber nicht getan. Bei einem Zustimmungsgesetz muss "
        "er trotzdem noch ausdrücklich zustimmen; bei einem Einspruchsgesetz kann er jetzt keinen Einspruch mehr "
        "einlegen, denn dafür müsste zuvor ein Vermittlungsverfahren stattgefunden haben.",
    "Bundesrat hat zugestimmt": "Ein Zustimmungsgesetz braucht die ausdrückliche Zustimmung des Bundesrates, "
        "sonst kommt es nicht zustande. Der Bundesrat hat zugestimmt; das Gesetz kann jetzt vom Bundespräsidenten "
        "ausgefertigt und verkündet werden.",
    "Bundesrat hat Zustimmung versagt": "Der Bundesrat hat die für ein Zustimmungsgesetz nötige Zustimmung "
        "verweigert. Ohne sie kommt ein Zustimmungsgesetz nicht zustande – anders als bei einem Einspruchsgesetz "
        "kann der Bundestag das nicht überstimmen. Das Verfahren ist gescheitert.",
    "Vermittlungsvorschlag liegt vor": "Der Vermittlungsausschuss – mit gleich vielen Mitgliedern aus Bundestag "
        "und Bundesrat – hat einen Einigungsvorschlag erarbeitet. Darüber muss der Bundestag erneut abstimmen, "
        "bei einem Zustimmungsgesetz danach auch der Bundesrat.",
    "Verkündet": "Der Bundespräsident hat das Gesetz nach Gegenzeichnung ausgefertigt, es ist im "
        "Bundesgesetzblatt verkündet (Art. 82 GG). Das Verfahren ist abgeschlossen; ohne ein anderes Datum im "
        "Gesetz tritt es 14 Tage nach der Ausgabe des Bundesgesetzblatts in Kraft.",
    "unbekannt": "Für diesen Vorgang nennt das DIP keinen Beratungsstand.",
}  # fmt: skip
GLOSSARY_STEPS = (
    ("Einbringung", "Ein Gesetzentwurf kommt von der Bundesregierung, aus der Mitte des Bundestages (einer "
        "Fraktion oder mindestens 5 % der Abgeordneten) oder vom Bundesrat (Art. 76 GG)."),
    ("1. Beratung", "Erste Lesung im Plenum, meist ohne Sachdebatte; entscheidend ist die Überweisung an die "
        "Ausschüsse."),
    ("Ausschuss", "Beratung im Detail, oft mit einer Anhörung von Sachverständigen; endet mit der "
        "Beschlussempfehlung an das Plenum."),
    ("2./3. Beratung", "Aussprache und Abstimmung über die Beschlussempfehlung, zuletzt die Schlussabstimmung."),
    ("Bundesrat", "Zweiter Durchgang: Zustimmung, Anrufung des Vermittlungsausschusses oder – bei einem "
        "Einspruchsgesetz – Einspruch (Art. 77, 78 GG)."),
    ("Ausfertigung durch den Bundespräsidenten", "Prüfung, ob das Gesetz verfassungsgemäß zustande gekommen ist, "
        "dann Unterschrift nach Gegenzeichnung durch Bundeskanzler oder zuständigen Minister (Art. 82 GG)."),
    ("Verkündung im Bundesgesetzblatt", "Amtliche Bekanntgabe des Gesetzestextes."),
    ("Inkrafttreten", "Am im Gesetz genannten Tag, sonst am 14. Tag nach der Ausgabe des Bundesgesetzblatts."),
)  # fmt: skip
GLOSSARY_SOURCES = (
    ("https://www.bundestag.de/parlament/aufgaben/gesetzgebung_neu/gesetzgebung/weg-255468",
     "Bundestag: Weg der Gesetzgebung"),
    ("https://www.bundestag.de/services/glossar/glossar/G/gesgeb-245440", "Bundestag: Glossar „Gesetzgebung“"),
    ("https://www.bundestag.de/services/glossar/glossar/B/beschlussempfehlung-245344",
     "Bundestag: Glossar „Beschlussempfehlung“"),
    ("https://www.bundesrat.de/DE/aufgaben/gesetzgebung/verfahren/verfahren-node.html",
     "Bundesrat: Ablauf des Verfahrens"),
    ("https://www.bundesrat.de/DE/aufgaben/gesetzgebung/zust-einspr/zust-einspr-node.html",
     "Bundesrat: Zustimmungs- und Einspruchsgesetze"),
    ("https://www.bundesrat.de/SharedDocs/texte/17/20170719-diskontinuitaet.html", "Bundesrat: Diskontinuität"),
    ("https://www.gesetze-im-internet.de/gg/art_76.html", "Grundgesetz Art. 76 (Einbringung)"),
    ("https://www.gesetze-im-internet.de/gg/art_77.html", "Grundgesetz Art. 77 (Vermittlungsausschuss, Einspruch)"),
    ("https://www.gesetze-im-internet.de/gg/art_78.html", "Grundgesetz Art. 78 (Zustandekommen der Gesetze)"),
    ("https://www.gesetze-im-internet.de/gg/art_82.html", "Grundgesetz Art. 82 (Ausfertigung, Verkündung)"),
)  # fmt: skip
STYLE = """<style>
.bills .row .l { white-space: normal; max-width: 40vw; }
.bills .st { display: inline-block; font-size: 12px; padding: 1px 7px; border-radius: 9px;
  background: var(--chip, #eef0f3); color: var(--muted); }
.bills ol.tl { list-style: none; padding: 0; margin: 8px 0; border-left: 2px solid var(--line, #dde); }
.bills ol.tl > li { margin: 0 0 12px; padding-left: 12px; position: relative; font-size: 14px; }
.bills ol.tl > li::before { content: ""; position: absolute; left: -6px; top: 6px; width: 10px; height: 10px;
  border-radius: 50%; background: var(--muted, #888); }
.bills ol.tl > li.BR::before { background: #b45309; }
.bills ol.tl > li.p-Abstimmung::before { background: var(--accent); }
.bills ol.tl .d { font-variant-numeric: tabular-nums; color: var(--muted); margin-right: 6px; }
.bills ol.tl .ph { font-size: 11px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase;
  color: var(--faint); margin-right: 6px; }
.bills ol.tl .ch { font-size: 12px; color: var(--muted); }
.bills ol.tl .dec { margin-top: 6px; }
.bills .deb { margin: 0 0 14px; }
.bills .deb h3 { font-size: 14px; font-weight: 500; margin: 0 0 6px; }
.bills dl.def dt { font-weight: 600; margin-top: 10px; }
.bills dl.def dd { margin: 2px 0 0; }
.bills ol.steps { padding-left: 20px; }
.bills ol.steps li { margin: 0 0 4px; }
.bills .glossary-sources { font-size: 13px; color: var(--muted); }
</style>"""


def _status_slug(status: str) -> str:
    return _SLUG.sub("-", status.translate(_UMLAUT).lower()).strip("-")


FILTER_JS = """<script>
(() => {
  const q = document.getElementById("bq"), st = document.getElementById("bst"), ty = document.getElementById("bty");
  const count = document.getElementById("bcount");
  const rows = [...document.querySelectorAll("#bills a.row")];
  function apply() {
    const words = q.value.toLowerCase().split(/\\s+/).filter(Boolean);
    let shown = 0;
    for (const r of rows) {
      const text = r.textContent.toLowerCase();
      const ok = (!st.value || r.dataset.status === st.value) && (!ty.value || r.dataset.type === ty.value)
        && words.every((w) => text.includes(w));
      r.hidden = !ok;
      shown += ok;
    }
    count.textContent = shown === rows.length ? `${rows.length} Vorgänge` : `${shown} von ${rows.length}`;
  }
  q.addEventListener("input", apply);
  st.addEventListener("change", apply);
  ty.addEventListener("change", apply);
  apply();
})();
</script>"""


def _json_list(s: str | None) -> list:
    try:
        v = json.loads(s or "[]")
    except ValueError:
        return []
    return v if isinstance(v, list) else []


def load(conn: sqlite3.Connection, sittings: list[dict], decisions: list[dict]) -> list[dict]:
    """Every Vorgang of the Wahlperiode that reaches the plenum, with its Drucksachen, debates (agenda items and
    sub-items that carry one of its Vorlagen, with their speeches), decisions and DIP positions (None when the store
    has no `vorgang_position`), newest activity first. Empty without the `vorgang` table."""
    if not has_table(conn, "vorgang"):
        return []
    has_verk = _has_column(conn, "vorgang", "verkuendung")  # foundation PR #16, older stores don't have it yet
    has_inkraft = _has_column(conn, "vorgang", "inkrafttreten")
    procs = {
        r["id"]: {
            "id": r["id"], "type": r["type"] or "Vorgang", "title": r["title"], "status": r["status"] or "unbekannt",
            "subjects": _json_list(r["subjects"]), "initiators": _json_list(r["initiators"]),
            "source": r["source_url"], "docs": [], "debates": [], "decisions": [], "positions": None,
            "verkuendung": _json_list(r["verkuendung"]) if has_verk else [],
            "inkrafttreten": _json_list(r["inkrafttreten"]) if has_inkraft else [],
        }
        for r in conn.execute("SELECT * FROM vorgang WHERE wahlperiode = ? ORDER BY id", (WP,))
    }  # fmt: skip
    if not procs:
        return []
    if has_table(conn, "vorgang_drucksache"):
        for r in conn.execute(
            """SELECT vd.vorgang_id, d.id, d.number, d.type, d.title, d.date, d.pdf_url, d.publisher, d.originators,
                      d.source_document_id
               FROM vorgang_drucksache vd JOIN drucksache d ON d.id = vd.drucksache_id ORDER BY d.date, d.number"""
        ):
            if r["vorgang_id"] in procs:
                bt = (r["publisher"] or "BT") == "BT"
                procs[r["vorgang_id"]]["docs"].append({
                    "number": r["number"], "type": r["type"] or "Drucksache", "date": r["date"],
                    "title": r["title"].strip().split("\n")[-1].strip(" -–") if r["title"] else None,
                    "url": DIP_DOC.format(r["id"]),
                    "pdf": r["pdf_url"] or (drucksache_pdf(r["number"]) if bt else None),
                    "publisher": r["publisher"] or "BT", "originators": _json_list(r["originators"]),
                    "cite": r["source_document_id"],
                })  # fmt: skip
    for s in sittings:
        for i in s["items"]:
            where = {"sitting": s["id"], "date": s["date"], "position": i["position"], "label": i["label"]}
            for v in i.get("vorgaenge") or []:
                if v["id"] in procs:
                    procs[v["id"]]["debates"].append({**where, "sub": None, "title": i["title"],
                                                      "speeches": i["speeches"]})  # fmt: skip
            for sub in i.get("sub_items") or []:
                for v in sub.get("vorgaenge") or []:
                    if v["id"] in procs:
                        procs[v["id"]]["debates"].append({**where, "sub": sub["label"], "title": sub["title"],
                                                          "speeches": sub["speeches"]})  # fmt: skip
    for d in decisions:
        for v in d.get("vorgaenge") or []:
            if v in procs:
                procs[v]["decisions"].append(d)
    if has_table(conn, "vorgang_position"):
        for b in procs.values():
            b["positions"] = []
        for r in conn.execute("SELECT * FROM vorgang_position ORDER BY date, id"):
            if r["vorgang_id"] in procs:
                procs[r["vorgang_id"]]["positions"].append({
                    "date": r["date"], "position": r["position"], "chamber": r["chamber"],
                    "kind": r["document_kind"], "number": r["document_number"], "doc_type": r["document_type"],
                    "url": r["pdf_url"], "pages": r["pages"], "originators": _json_list(r["originators"]),
                    "decisions": _json_list(r["decisions"]),
                })  # fmt: skip
    out = [b for b in procs.values() if b["type"] == GESETZ or b["debates"] or b["decisions"]]
    for b in out:
        b["decisions"].sort(key=lambda d: (d["date"], d["order"]))
        b["timeline"] = timeline(b)
        b["latest"] = max((t["date"] for t in b["timeline"]), default="")
    out.sort(key=lambda b: (b["latest"], b["id"]), reverse=True)
    return out


def phase(what: str, chamber: str | None, kind: str | None = None) -> str:
    """Which phase of the procedure a DIP step belongs to (PHASES)."""
    if chamber == "BR":
        return "Bundesrat"
    if re.search(r"Verkünd|Ausfertig|Inkraft", what):
        return "Verkündung"
    if re.search(r"Beschlussempfehlung|Bericht|Ausschuss", what):
        return "Ausschuss"
    if "Beratung" in what or kind == "Plenarprotokoll":
        return "Beratung"
    return "Eingebracht"


def timeline(b: dict) -> list[dict]:
    """Steps by date and phase: DIP's positions when the store has them, else the Drucksachen and the debates; in
    both cases every decision on the Vorgang as a point of its own (D15), and the Verkündung (date, Fundstelle,
    linked to the Bundesgesetzblatt PDF) and Inkrafttreten when the store has them (`vorgang.verkuendung`/
    `inkrafttreten`, independent of `vorgang_position`).
    Each step is {date, phase, chamber, what, doc (label, url) or None, sitting (id, position, sub label) or None,
    note, decision or None}."""
    steps = []

    def step(date: str, ph: str, what: str, chamber: str = "", doc=None, sitting=None, note: str = "", dec=None):
        steps.append({"date": date[:10], "phase": ph, "chamber": chamber, "what": what, "doc": doc,
                      "sitting": sitting, "note": note, "decision": dec})  # fmt: skip

    if b["positions"] is not None:
        top = {}  # sitting -> the first agenda item (or sub-item) there that carries one of the Vorgang's Vorlagen
        for a in b["debates"]:
            top.setdefault(a["sitting"], (a["position"], a["sub"]))
        for p in b["positions"]:
            doc = None
            if p["number"]:
                label = "Drucksache" if p["kind"] == "Drucksache" else "Plenarprotokoll"
                prefix = "BR-" if p["chamber"] == "BR" else ""
                pages = f", S. {p['pages']}" if p["pages"] else ""
                doc = (f"{prefix}{label} {p['number']}{pages}", p["url"])
            sitting = None
            if p["kind"] == "Plenarprotokoll" and p["chamber"] == "BT" and p["number"]:
                sitting = (p["number"], *top.get(p["number"], (None, None)))
            tenor = "; ".join(
                str(x["beschlusstenor"]) + (f" ({x['dokumentnummer']})" if x.get("dokumentnummer") else "")
                for x in p["decisions"] if isinstance(x, dict) and x.get("beschlusstenor")
            )  # fmt: skip
            step(p["date"], phase(p["position"], p["chamber"], p["kind"]), p["position"], p["chamber"] or "", doc,
                 sitting, tenor)  # fmt: skip
    else:
        for d in b["docs"]:
            step(d["date"], phase(d["type"], "BR" if d["publisher"] == "BR" else None), d["type"], d["publisher"],
                 (f"Drucksache {d['number']}", d["url"]))  # fmt: skip
        for a in b["debates"]:
            label = a["label"] + (f" › {a['sub']}" if a["sub"] else "")
            step(a["date"], "Beratung", f"Beratung im Plenum ({label})", "BT",
                 sitting=(a["sitting"], a["position"], a["sub"]))  # fmt: skip
    for d in b["decisions"]:
        what = "Namentliche Abstimmung" if d["kind"] == "namentlich" else "Abstimmung per Handzeichen"
        step(d["date"], "Abstimmung", what, "BT", dec=d)
    for v in b["verkuendung"]:
        if not v.get("verkuendungsdatum"):
            continue
        fundstelle = v.get("fundstelle") or "Verkündung"
        note = f"Ausgefertigt am {short_date(v['ausfertigungsdatum'])}" if v.get("ausfertigungsdatum") else ""
        step(v["verkuendungsdatum"], "Verkündung", "Verkündet", doc=(fundstelle, v.get("pdf_url")), note=note)
    for i in b["inkrafttreten"]:
        if i.get("datum"):
            step(i["datum"], "Verkündung", "Inkrafttreten", note=i.get("erlaeuterung") or "")
    return sorted(steps, key=lambda s: (s["date"], PHASES.index(s["phase"])))


# ---------------------------------------------------------------- pages


def _link(href: str | None, text: str) -> str:
    return f'<a href="{e(href)}">{text}</a>' if href else text


def _how(b: dict) -> str:
    has_verk = bool(b["verkuendung"])
    if b["positions"] is not None:
        has_br = any(p["chamber"] == "BR" for p in b["positions"])
        if has_br and has_verk:
            how = "Die Schritte stammen aus dem Vorgangsablauf im DIP, auch die im Bundesrat und die Verkündung."
        elif has_br:
            how = ("Die Schritte stammen aus dem Vorgangsablauf im DIP, auch die im Bundesrat. Die Verkündung ist "
                   "noch nicht im Datenbestand, sie steht im DIP.")  # fmt: skip
        elif has_verk:
            how = ("Die Schritte stammen aus dem Vorgangsablauf im DIP, auch die Verkündung. Schritte im Bundesrat "
                   "sind noch nicht im Datenbestand, sie stehen im DIP.")  # fmt: skip
        else:
            how = ("Die Schritte stammen aus dem Vorgangsablauf im DIP. Schritte im Bundesrat und die Verkündung "
                   "sind noch nicht im Datenbestand, sie stehen im DIP.")  # fmt: skip
    elif has_verk:
        how = ("Zusammengestellt aus den Daten der Drucksachen, den Tagesordnungspunkten und den Beschlüssen im "
               "Datenbestand, dazu die Verkündung. Schritte im Bundesrat fehlen hier, sie stehen im DIP.")  # fmt: skip
    else:
        how = ("Zusammengestellt aus den Daten der Drucksachen, den Tagesordnungspunkten und den Beschlüssen im "
               "Datenbestand; Schritte im Bundesrat und die Verkündung fehlen hier, sie stehen im DIP.")  # fmt: skip
    return (how + " Jede Abstimmung steht mit ihrem Ergebnis im Ablauf, eine namentliche mit der Stimme jedes "
            "Mitglieds.")  # fmt: skip


def procedure_page(b: dict, have: set[str], members: dict[str, list[list]]) -> str:
    """One Vorgang; `have` holds the site paths ("sitzungen/21-88.html") that exist, so every link resolves."""

    def sitting_href(sid: str, position: int | None, sub: str | None = None) -> str | None:
        path = f"sitzungen/{page_id(sid)}.html"
        return f"../{urls.sitting(sid, position, sub)}" if path in have else None

    status = e(b["status"])
    if b["type"] == GESETZ:
        status = f'<a class="st" href="index.html#status-{e(_status_slug(b["status"]))}">{status}</a>'
    lines = [f'<span class="k">Art</span> {e(b["type"])}', f'<span class="k">Stand</span> {status}']
    if b["initiators"]:
        lines.append(f'<span class="k">Eingebracht von</span> {", ".join(frac_link(x) for x in b["initiators"])}')
    if b["subjects"]:
        lines.append(f'<span class="k">Sachgebiete</span> {e(", ".join(b["subjects"]))}')
    parts = [
        crumbs(("index.html", "Vorgänge"), (None, b["type"])),
        entity_header(b["title"], lines, [f'<a href="{DIP_VORGANG.format(e(b["id"]))}">Vorgang im DIP ↗</a>']),
    ]
    steps = []
    for s in b["timeline"]:
        d = s["decision"]
        if d is not None:
            body = facts.decision(d, "../", point=True, detail=True, members=members.get(d["id"]), when=False)
            steps.append(f'<li class="BT p-Abstimmung"><span class="d">{short_date(s["date"])}</span>'
                         f'<span class="ph">{e(s["phase"])}</span>{e(s["what"])}{body}</li>')  # fmt: skip
            continue
        steps.append(
            f'<li class="{e(s["chamber"])} p-{e(s["phase"])}"><span class="d">{short_date(s["date"])}</span>'
            f'<span class="ph">{e(s["phase"])}</span>'
            + _link(sitting_href(*s["sitting"]) if s["sitting"] else None, e(s["what"]))
            + (f' <span class="ch">{e(CHAMBER.get(s["chamber"], s["chamber"]))}</span>' if s["chamber"] else "")
            + (f" · {_link(s['doc'][1], e(s['doc'][0]))}" if s["doc"] else "")
            + (f" · {e(s['note'])}" if s["note"] else "")
            + "</li>"
        )
    parts.append(facet("abstimmungen", "Ablauf, Abstimmungen und Beschlüsse", f'<ol class="tl">{"".join(steps)}</ol>',
                       len(b["decisions"]), _how(b)))  # fmt: skip
    debates = []
    for k, a in enumerate(b["debates"]):
        num = a["sitting"].split("/")[1]
        label = a["label"] + (f" › {a['sub']}" if a["sub"] else "")
        head = (f'<h3><b>{short_date(a["date"])}</b>, '
                f'{_link(sitting_href(a["sitting"], a["position"], a["sub"]), f"{e(num)}. Sitzung, {e(label)}")}: '
                f'{e(a["title"])}</h3>')  # fmt: skip
        sps = [sp for sp in a["speeches"] if f"reden/{page_id(urls.rede(sp['id']))}.html" in have]
        debates.append(f'<div class="deb">{head}'
                       + facts.speech_list(sps, "../", f"deb-{k}", where=False, limit=10,
                                           empty="Keine Reden im Datenbestand.")
                       + "</div>")  # fmt: skip
    n_speeches = sum(len(a["speeches"]) for a in b["debates"])
    parts.append(facet("reden", "Reden", "".join(debates) or '<p class="explain">Noch nicht im Plenum beraten.</p>',
                       n_speeches, "Tagesordnungspunkte und Unterpunkte, die eine Drucksache dieses Vorgangs "
                       "aufrufen, mit ihren Reden." if debates else ""))  # fmt: skip
    parts.append(facet("drucksachen", "Drucksachen", facts.drucksache_list(b["docs"], "../", "drs", compact=False,
                                                                           limit=50), len(b["docs"])))  # fmt: skip
    parts.append(f"<footer>{FOOTER}</footer>")
    charts = any(members.get(d["id"]) or (d.get("fractions") and d.get("house")) for d in b["decisions"])
    head = STYLE + ('<script src="../parliament.js"></script>' if charts else "")
    return shell(root="../", kind="p-bill", active="bills", title=b["title"][:120],
                 desc=f"{b['type']} im 21. Bundestag: {b['title'][:200]}. Stand: {b['status']}.",
                 body=f'<div class="bills">{"".join(parts)}</div>', data={"kind": "procedure", "id": b["id"]},
                 head=head)  # fmt: skip


def _glossary(statuses: set[str]) -> str:
    """ "So entsteht ein Gesetz" and the DIP Beratungsstand values that occur in `statuses`, each linkable as
    "#status-<slug>" from a Vorgang page's status. Sources under the glossary, see GLOSSARY_SOURCES."""
    steps = "".join(f"<li><b>{e(name)}</b> – {e(text)}</li>" for name, text in GLOSSARY_STEPS)
    known = [s for s in STATUS_GLOSSARY if s in statuses]
    terms = "".join(f'<dt id="status-{e(_status_slug(s))}">{e(s)}</dt><dd>{e(STATUS_GLOSSARY[s])}</dd>' for s in known)
    sources = " · ".join(f'<a href="{e(u)}">{e(t)}</a>' for u, t in GLOSSARY_SOURCES)
    return f"""<section id="glossar"><h2>So entsteht ein Gesetz</h2>
<ol class="steps">{steps}</ol>
<h2>Glossar: Beratungsstand im DIP</h2>
<p class="explain">Was der Stand, den das DIP für einen Gesetzgebungsvorgang festhält, jeweils bedeutet, in der
Reihenfolge des Verfahrens oben.</p>
<dl class="def">{terms}</dl>
<p class="glossary-sources">Quellen: {sources}.</p>
</section>"""


def _status_label(s: str) -> str:
    """The status, linked to its glossary entry when it has one."""
    label = e(s)
    return f'<a href="#status-{e(_status_slug(s))}">{label}</a>' if s in STATUS_GLOSSARY else label


def index_page(procs: list[dict]) -> str:
    bills = [b for b in procs if b["type"] == GESETZ]
    status = Counter(b["status"] for b in bills)
    types = Counter(b["type"] for b in procs)
    options = "".join(
        f'<option value="{e(s)}">{e(s)} ({k})</option>' for s, k in Counter(b["status"] for b in procs).most_common()
    )
    type_options = "".join(f'<option value="{e(t)}">{e(t)} ({k})</option>' for t, k in types.most_common())
    table = "".join(f'<tr><td class="l">{_status_label(s)}</td><td>{n(k)}</td></tr>' for s, k in status.most_common())
    rows = "".join(
        f'<a class="row" href="{e(b["id"])}.html" data-status="{e(b["status"])}" data-type="{e(b["type"])}">'
        f'<span class="d">{short_date(b["latest"]) if b["latest"] else ""}</span><span class="t"><span class="ti">'
        f'{e(b["title"])}</span><span class="sub">{e(b["type"])} · {e(", ".join(b["initiators"][:3]))}'
        f'{" …" if len(b["initiators"]) > 3 else ""}</span></span><span class="l"><span class="st">{e(b["status"])}'
        "</span></span></a>"
        for b in procs
    )
    body = f"""<div class="bills"><h1>Vorgänge</h1>
<p class="lead">Ein Vorgang ist im Dokumentationssystem DIP alles, was zu einer Vorlage gehört: ein Gesetzentwurf mit seinen Beratungen, Beschlussempfehlungen und Abstimmungen, ein Antrag, ein Entschließungsantrag. Hier stehen alle {n(types[GESETZ])} Gesetzgebungsvorgänge des 21. Bundestages und alle weiteren Vorgänge, die im Plenum beraten oder abgestimmt wurden ({n(len(procs) - types[GESETZ])}), der zuletzt bewegte zuerst. Ein Gesetz beginnt als Gesetzentwurf – von der Bundesregierung, aus der Mitte des Bundestages (meist von Fraktionen) oder vom Bundesrat. Der Bundestag berät es in der Regel dreimal im Plenum und dazwischen in den Ausschüssen, dann stimmt er ab. Danach ist der Bundesrat dran; zuletzt wird das Gesetz ausgefertigt und im Bundesgesetzblatt verkündet.</p>
<details class="open"><summary>Wie viele Gesetzesvorhaben in welchem Stand sind</summary><div class="rows"><table class="plenum"><thead><tr><th>Stand im DIP</th><th>Vorgänge</th></tr></thead><tbody>{table}</tbody></table></div></details>
<div class="filters"><input type="search" id="bq" placeholder="Titel oder Einbringer …" autocomplete="off"><select id="bty"><option value="">jede Art</option>{type_options}</select><select id="bst"><option value="">jeder Stand</option>{options}</select></div>
<div class="count" id="bcount"></div>
<div class="rows" id="bills">{rows}</div>
{_glossary(set(status))}</div>
<footer>{FOOTER}</footer>
{FILTER_JS}"""  # noqa: E501
    return shell(root="../", kind="p-bills", active="bills", title="Vorgänge im Bundestag",
                 desc="Alle Gesetzgebungsvorgänge und alle im Plenum beratenen Vorgänge des 21. Deutschen Bundestages "
                      "mit Stand, Drucksachen, Debatten und Abstimmungen.", body=body, data={"kind": "procedures"},
                 head=STYLE)  # fmt: skip


def write(conn: sqlite3.Connection, out: Path, sittings: list[dict], decisions: list[dict],
          members: dict[str, list[list]]) -> list[dict]:  # fmt: skip
    """Write vorgaenge/ and the stubs of the pages it replaces: gesetze/<id>.html and gesetze/index.html, and
    abstimmungen/<page id>.html of every decision that is now a point on a Vorgang's timeline. Call after the sitting,
    vote and speech pages so the links can be checked against them. Returns the Vorgänge written."""
    procs = load(conn, sittings, decisions)
    have = {
        f"{d}/{p.name}"
        for d in ("sitzungen", "abstimmungen", "reden")
        if (out / d).is_dir()
        for p in (out / d).iterdir()
    }
    d = out / "vorgaenge"
    d.mkdir(parents=True, exist_ok=True)
    for b in procs:
        (d / f"{b['id']}.html").write_text(procedure_page(b, have, members), encoding="utf-8")
        if b["type"] == GESETZ:
            redirects.write(out, f"gesetze/{b['id']}.html", urls.vorgang(b["id"]), b["title"])
    (d / "index.html").write_text(index_page(procs), encoding="utf-8")
    redirects.write(out, "gesetze/index.html", urls.PROCEDURES, "Vorgänge")
    written = {b["id"] for b in procs}
    for dec in decisions:
        target = urls.decision(dec)
        if target.startswith("vorgaenge/") and dec["vorgaenge"][0] in written:
            redirects.write(out, f"abstimmungen/{dec['page']}.html", target, dec["title"],
                            redirects.any_fragment(f"abst-{dec['page']}"))  # fmt: skip
    return procs
