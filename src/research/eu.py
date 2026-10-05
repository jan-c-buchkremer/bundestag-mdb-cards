"""EU-Vorlagen (docs/plan.md, "Current goal" 2): `vorgaenge/eu-vorlagen.html`. An EU-Vorlage is a kind of Vorgang
in DIP: a document of the European Union that reaches the Bundestag as an Unterrichtung. The kind says where it comes
from, a Sachgebiet what it is about; in DIP the EU-Vorlagen have almost never a Sachgebiet, so they get this page
beside the Sachgebiete and are linked with the Sachgebiet "Europapolitik und Europäische Union".

Per EU-Vorlage: its date, title (some are English, as DIP has them), the Unterrichtung (DIP and PDF) and a Stand read
from DIP's steps (`vorgang_position`): referred to committees under § 93 GO-BT, a Mitteilung of the lead committee,
or no referral. The committees each went to need the foundation's referral table (`REFERRAL`); until the store has it
the column shows "–". The Stand is a row of steps and the lead committees are chips, sized by count; both filter the
list, as does the activity strip (controls.py)."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path

from research import controls, facts, urls
from research.data import WP, _has_column, drucksache_pdf, has_table, iso_week
from research.procedures import DIP_DOC, DIP_VORGANG, STYLE, _json_list
from research.subjects import EUROPE
from research.ui import FOOTER, PROCEDURE_TABS, e, n, shell, short_date, subtabs

KIND = "EU-Vorlage"
# the foundation's referral table (task sachgebiete-foundation): {vorgang_id, committee, lead (1 for the lead one)}
REFERRAL = "vorgang_referral"
# the Stand of an EU-Vorlage from its DIP steps, the furthest first (one per Vorgang)
MITTEILUNG = "Mitteilung des federführenden Ausschusses"
REFERRED = "an Ausschüsse überwiesen"
NOT_REFERRED = "keine Ausschussüberweisung"
UNKNOWN = "ohne Angabe im DIP"
STANDS = (MITTEILUNG, REFERRED, NOT_REFERRED, UNKNOWN)
# the Stand as a row of steps, in the order of the procedure (§ 93 GO-BT); without any step in DIP, apart
STEPS = (NOT_REFERRED, REFERRED, MITTEILUNG)
LEAD = " (federführend)"
_REFERRAL = re.compile(r"überw(ies|eis)", re.I)
_NEGATED = re.compile(r"\b(nicht|keine?|ohne)\b[^.;]*überw|abgesehen", re.I)


def stand(positions: list[dict]) -> str:
    """The furthest step of an EU-Vorlage in DIP: a Mitteilung of the lead committee, a referral to committees
    (§ 93 GO-BT), or none (steps, but no referral among them); without any step, no Stand."""
    if not positions:
        return UNKNOWN
    texts = [" ".join([p["position"] or "", *p["tenors"]]) for p in positions]
    if any("Mitteilung" in t and "Ausschuss" in t for t in texts):
        return MITTEILUNG
    if any(_REFERRAL.search(t) and not _NEGATED.search(t) for t in texts):
        return REFERRED
    return NOT_REFERRED


def committees(conn: sqlite3.Connection) -> dict[str, list[str]] | None:
    """{vorgang id: the committees it went to, the lead one first and marked "(federführend)"}; None while the store
    has no referral table."""
    if not has_table(conn, REFERRAL):
        return None
    lead = "lead" if _has_column(conn, REFERRAL, "lead") else "0"
    out: dict[str, list[str]] = {}
    rows = conn.execute(f"SELECT vorgang_id, committee, {lead} AS lead FROM {REFERRAL} "
                        f"ORDER BY vorgang_id, {lead} DESC, committee")  # fmt: skip
    for r in rows:
        names = out.setdefault(r["vorgang_id"], [])
        name = r["committee"] + (LEAD if r["lead"] else "")
        if name not in names and r["committee"] not in names:  # several positions name the same committee
            names.append(name)
    return out


def load(conn: sqlite3.Connection) -> list[dict]:
    """Every EU-Vorlage of the Wahlperiode, newest first: {id, title, date, stand, docs, committees}. `docs` are its
    Unterrichtungen as facts.drucksache takes them; `committees` is None without the referral table."""
    if not has_table(conn, "vorgang"):
        return []
    eu = {
        r["id"]: {"id": r["id"], "title": r["title"], "docs": [], "positions": []}
        for r in conn.execute("SELECT id, title FROM vorgang WHERE wahlperiode = ? AND type = ?", (WP, KIND))
    }
    if has_table(conn, "vorgang_drucksache") and has_table(conn, "drucksache"):
        for r in conn.execute(
            """SELECT vd.vorgang_id, d.id, d.number, d.type, d.date, d.pdf_url, d.publisher, d.source_document_id
               FROM vorgang_drucksache vd JOIN drucksache d ON d.id = vd.drucksache_id ORDER BY d.date, d.number"""
        ):
            if r["vorgang_id"] in eu:
                bt = (r["publisher"] or "BT") == "BT"
                eu[r["vorgang_id"]]["docs"].append({
                    "number": r["number"], "type": r["type"] or "Drucksache", "date": r["date"],
                    "url": DIP_DOC.format(r["id"]), "cite": r["source_document_id"],
                    "pdf": r["pdf_url"] or (drucksache_pdf(r["number"]) if bt else None),
                })  # fmt: skip
    if has_table(conn, "vorgang_position"):
        for r in conn.execute("SELECT * FROM vorgang_position ORDER BY date, id"):
            if r["vorgang_id"] in eu:
                tenors = [str(x.get("beschlusstenor")) for x in _json_list(r["decisions"])
                          if isinstance(x, dict) and x.get("beschlusstenor")]  # fmt: skip
                eu[r["vorgang_id"]]["positions"].append({
                    "date": r["date"], "position": r["position"], "kind": r["document_kind"],
                    "number": r["document_number"], "url": r["pdf_url"], "tenors": tenors,
                })  # fmt: skip
    referred = committees(conn)
    out = []
    for v in eu.values():
        docs = v["docs"]
        if not docs:  # the Unterrichtung from DIP's steps when vorgang_drucksache has none
            docs = [{"number": p["number"], "type": "Unterrichtung", "date": p["date"], "url": None, "pdf": p["url"]}
                    for p in v["positions"] if p["kind"] == "Drucksache" and p["number"]][:1]  # fmt: skip
        dates = [d["date"] for d in docs if d.get("date")] + [p["date"] for p in v["positions"] if p["date"]]
        out.append({
            "id": v["id"], "title": v["title"], "date": min(dates)[:10] if dates else "", "docs": docs,
            "stand": stand(v["positions"]),
            "committees": None if referred is None else referred.get(v["id"], []),
        })  # fmt: skip
    out.sort(key=lambda v: (v["date"], v["id"]), reverse=True)
    return out


def lead(v: dict) -> str | None:
    """The lead committee of an EU-Vorlage, when the store names one."""
    first = (v["committees"] or [""])[0]
    return first.removesuffix(LEAD) if first.endswith(LEAD) else None


def eu_row(v: dict) -> str:
    """One EU-Vorlage in the list, with its values for the controls (`data-stand`, `data-ausschuss`, `data-w`)."""
    unterrichtung = " · ".join(
        f"Drs. {facts.drucksache(d, '../', compact=True)}"
        + (f' (<a href="{e(d["pdf"])}">PDF</a>)' if d.get("pdf") else "")
        for d in v["docs"]
    ) if v["docs"] else '<span class="faint">keine Drucksache im Datenbestand</span>'  # fmt: skip
    committee = e(", ".join(v["committees"])) if v["committees"] else "–"
    date = short_date(v["date"]) if v["date"] else ""
    lead_slug = urls.slug(lead(v) or "")
    return (
        f'<div class="row" data-stand="{urls.slug(v["stand"])}" data-ausschuss="{lead_slug}" '
        f'data-w="{iso_week(v["date"]) if v["date"] else ""}"><span class="d">{date}</span>'
        f'<span class="t"><span class="ti"><a href="{DIP_VORGANG.format(e(v["id"]))}">{e(v["title"])}</a> '
        f'<span class="faint">↗</span></span><span class="sub">Unterrichtung {unterrichtung} · Ausschuss: '
        f'{committee}</span></span><span class="l"><span class="st">{e(v["stand"])}</span></span></div>'
    )


def page(eu: list[dict], procs: list[dict], europe: bool, sitting_dates: list[str] | None = None) -> str:
    """The EU-Vorlagen; `procs` the Vorgänge with a page (an EU-Vorlage debated or decided would be one), `europe`
    whether the Sachgebiet page "Europapolitik und Europäische Union" was written, `sitting_dates` the days of the
    sittings (marked on the activity strip)."""
    ids = {v["id"] for v in eu}
    debated = sum(1 for b in procs if b["id"] in ids and b["debates"])
    decided = sum(1 for b in procs if b["id"] in ids and b["decisions"])
    plenum = ("Keine davon wurde im Plenum beraten oder abgestimmt." if not debated and not decided else
              f"{n(debated)} davon wurden im Plenum beraten, über {n(decided)} wurde abgestimmt.")  # fmt: skip
    sg = f'<a href="../{e(urls.subject(EUROPE))}">{e(EUROPE)}</a>' if europe else e(EUROPE)
    stands = Counter(v["stand"] for v in eu)
    table = controls.table(["Stand", "EU-Vorlagen"], [[e(s), n(stands[s])] for s in STANDS if stands[s]])
    steps = controls.pipeline("stand", [(urls.slug(s), s, stands[s]) for s in STEPS], [], "Stand der EU-Vorlagen",
                              rest=(urls.slug(UNKNOWN), UNKNOWN, stands[UNKNOWN]))  # fmt: skip
    known = any(v["committees"] is not None for v in eu)
    if known:
        leads = Counter(x for v in eu if (x := lead(v)))
        committees = controls.block(
            "Federführender Ausschuss",
            controls.sized_chips(
                "ausschuss", [(urls.slug(c), c, k) for c, k in leads.most_common()], "Federführender Ausschuss"
            ),
        )
    else:
        committees = ('<p class="explain">An welche Ausschüsse eine Vorlage ging, enthält der Datenbestand noch nicht. '
                      "Die Spalte Ausschuss zeigt deshalb „–“. Im DIP steht es beim Vorgang.</p>")  # fmt: skip
    lists = controls.scope(
        controls.toolbar("Titel oder Drucksache …")
        + controls.view("stand", "Stand", steps, table)
        + committees
        + controls.activity([v["date"] for v in eu], sitting_dates or [], "EU-Vorlagen", "EU-Vorlage", "Eingegangen")
        + controls.rows((eu_row(v) for v in eu), "eu", "Keine EU-Vorlagen im Datenbestand."),
        "EU-Vorlagen", "EU-Vorlage",
    )  # fmt: skip
    body = f"""{subtabs("../", PROCEDURE_TABS, "eu")}<div class="bills"><h1>EU-Vorlagen</h1>
<p class="lead">Eine EU-Vorlage ist im DIP eine Art von Vorgang. Es ist ein Dokument der Europäischen Union, das
dem Bundestag als Unterrichtung zugeht. Die Art sagt, woher ein Vorgang kommt. Ein Sachgebiet sagt, worum es geht.
Deshalb haben die EU-Vorlagen diese eigene Seite unter den Vorgängen. Die Europapolitik als Thema hat das
Sachgebiet {sg}.
Im 21. Bundestag sind es {n(len(eu))} EU-Vorlagen. {plenum}</p>
<p class="explain">Der Stand kommt aus dem Ablauf im DIP. Nach § 93 GO-BT wird eine EU-Vorlage an die Ausschüsse
überwiesen, oder von einer Überweisung wird abgesehen. Der federführende Ausschuss kann danach eine Mitteilung
machen. Die Titel stehen so, wie das DIP sie führt, manche auf Englisch. Ein Klick auf einen Stand, einen Ausschuss
oder eine Woche zeigt unten nur diese EU-Vorlagen.</p>
{lists}
</div>
<footer>{FOOTER}</footer>"""
    return shell(root="../", kind="p-eu", active="bills", title="EU-Vorlagen im Bundestag",
                 desc="Alle EU-Vorlagen des 21. Deutschen Bundestages mit Unterrichtung und Stand der Überweisung an "
                      "die Ausschüsse.", body=body, data={"kind": "eu"}, head=STYLE + controls.head("../"))  # fmt: skip


def write(conn: sqlite3.Connection, out: Path, procs: list[dict], europe: bool,
          sittings: list[dict] | None = None) -> list[dict]:  # fmt: skip
    """Write vorgaenge/eu-vorlagen.html (also without EU-Vorlagen in the store: the sub-tab links it). Returns them."""
    eu = load(conn)
    (out / "vorgaenge").mkdir(parents=True, exist_ok=True)
    (out / urls.EU).write_text(page(eu, procs, europe, [s["date"] for s in sittings or []]), encoding="utf-8")
    return eu
