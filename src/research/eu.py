"""EU-Vorlagen (docs/plan.md, "Current goal" 2): `vorgaenge/eu-vorlagen.html`. An EU-Vorlage is a kind of Vorgang
in DIP: a document of the European Union that reaches the Bundestag as an Unterrichtung. The kind says where it comes
from, a Sachgebiet what it is about; in DIP the EU-Vorlagen have almost never a Sachgebiet, so they get this page
beside the Sachgebiete and are linked with the Sachgebiet "Europapolitik und Europäische Union".

Per EU-Vorlage: its date, title (some are English, as DIP has them), the Unterrichtung (DIP and PDF) and a Stand read
from DIP's steps (`vorgang_position`): referred to committees under § 93 GO-BT, a Mitteilung of the lead committee,
or no referral. The committees each went to need the foundation's referral table (`REFERRAL`); until the store has it
the column shows "–"."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path

from research import facts, urls
from research.data import WP, _has_column, drucksache_pdf, has_table
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
_REFERRAL = re.compile(r"überw(ies|eis)", re.I)
_NEGATED = re.compile(r"\b(nicht|keine?|ohne)\b[^.;]*überw|abgesehen", re.I)

FILTER = """<script>
(() => {
  const q = document.getElementById("eq"), st = document.getElementById("est");
  const count = document.getElementById("ecount");
  const rows = [...document.querySelectorAll("#eu > .row")];
  function apply() {
    const words = q.value.toLowerCase().split(/\\s+/).filter(Boolean);
    let shown = 0;
    for (const r of rows) {
      const text = r.textContent.toLowerCase();
      const ok = (!st.value || r.dataset.stand === st.value) && words.every((w) => text.includes(w));
      r.hidden = !ok;
      shown += ok;
    }
    count.textContent = shown === rows.length ? `${rows.length} EU-Vorlagen` : `${shown} von ${rows.length}`;
  }
  q.addEventListener("input", apply);
  st.addEventListener("change", apply);
  apply();
})();
</script>"""


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
        name = r["committee"] + (" (federführend)" if r["lead"] else "")
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


def page(eu: list[dict], procs: list[dict], europe: bool) -> str:
    """The EU-Vorlagen; `procs` the Vorgänge with a page (an EU-Vorlage debated or decided would be one), `europe`
    whether the Sachgebiet page "Europapolitik und Europäische Union" was written."""
    ids = {v["id"] for v in eu}
    debated = sum(1 for b in procs if b["id"] in ids and b["debates"])
    decided = sum(1 for b in procs if b["id"] in ids and b["decisions"])
    plenum = ("Keine davon wurde im Plenum beraten oder abgestimmt." if not debated and not decided else
              f"{n(debated)} davon wurden im Plenum beraten, über {n(decided)} wurde abgestimmt.")  # fmt: skip
    sg = f'<a href="../{e(urls.subject(EUROPE))}">{e(EUROPE)}</a>' if europe else e(EUROPE)
    stands = Counter(v["stand"] for v in eu)
    options = "".join(f'<option value="{e(s)}">{e(s)} ({n(stands[s])})</option>' for s in STANDS if stands[s])
    table = "".join(f'<tr><td class="l">{e(s)}</td><td class="num">{n(stands[s])}</td></tr>'
                    for s in STANDS if stands[s])  # fmt: skip
    rows = []
    for v in eu:
        unterrichtung = " · ".join(
            f"Drs. {facts.drucksache(d, '../', compact=True)}"
            + (f' (<a href="{e(d["pdf"])}">PDF</a>)' if d.get("pdf") else "")
            for d in v["docs"]
        ) if v["docs"] else '<span class="faint">keine Drucksache im Datenbestand</span>'  # fmt: skip
        committee = e(", ".join(v["committees"])) if v["committees"] else "–"
        date = short_date(v["date"]) if v["date"] else ""
        rows.append(
            f'<div class="row" data-stand="{e(v["stand"])}"><span class="d">{date}</span>'
            f'<span class="t"><span class="ti"><a href="{DIP_VORGANG.format(e(v["id"]))}">{e(v["title"])}</a> '
            f'<span class="faint">↗</span></span><span class="sub">Unterrichtung {unterrichtung} · Ausschuss: '
            f'{committee}</span></span><span class="l"><span class="st">{e(v["stand"])}</span></span></div>'
        )
    no_committees = ("" if any(v["committees"] is not None for v in eu) else
                     " An welche Ausschüsse eine Vorlage ging, enthält der Datenbestand noch nicht. Die Spalte "
                     "Ausschuss zeigt deshalb „–“. Im DIP steht es beim Vorgang.")  # fmt: skip
    body = f"""{subtabs("../", PROCEDURE_TABS, "eu")}<div class="bills"><h1>EU-Vorlagen</h1>
<p class="lead">Eine EU-Vorlage ist im DIP eine Art von Vorgang. Es ist ein Dokument der Europäischen Union, das
dem Bundestag als Unterrichtung zugeht. Die Art sagt, woher ein Vorgang kommt. Ein Sachgebiet sagt, worum es geht.
Deshalb haben die EU-Vorlagen diese eigene Seite unter den Vorgängen. Die Europapolitik als Thema hat das
Sachgebiet {sg}.
Im 21. Bundestag sind es {n(len(eu))} EU-Vorlagen. {plenum}</p>
<p class="explain">Der Stand kommt aus dem Ablauf im DIP. Nach § 93 GO-BT wird eine EU-Vorlage an die Ausschüsse
überwiesen, oder von einer Überweisung wird abgesehen. Der federführende Ausschuss kann danach eine Mitteilung
machen. Die Titel stehen so, wie das DIP sie führt, manche auf Englisch.{no_committees}</p>
<details class="open"><summary>EU-Vorlagen nach Stand</summary><div class="rows"><table class="plenum"><thead><tr>
<th>Stand</th><th>EU-Vorlagen</th></tr></thead><tbody>{table}</tbody></table></div></details>
<div class="filters"><input type="search" id="eq" placeholder="Titel oder Drucksache …" autocomplete="off"
aria-label="Titel oder Drucksache"><select id="est" aria-label="Stand"><option value="">jeder Stand</option>{options}
</select></div>
<div class="count" id="ecount"></div>
<div class="rows" id="eu">{"".join(rows) or '<div class="empty">Keine EU-Vorlagen im Datenbestand.</div>'}</div>
</div>
<footer>{FOOTER}</footer>
{FILTER}"""
    return shell(root="../", kind="p-eu", active="bills", title="EU-Vorlagen im Bundestag",
                 desc="Alle EU-Vorlagen des 21. Deutschen Bundestages mit Unterrichtung und Stand der Überweisung an "
                      "die Ausschüsse.", body=body, data={"kind": "eu"}, head=STYLE)  # fmt: skip


def write(conn: sqlite3.Connection, out: Path, procs: list[dict], europe: bool) -> list[dict]:
    """Write vorgaenge/eu-vorlagen.html (also without EU-Vorlagen in the store: the sub-tab links it). Returns them."""
    eu = load(conn)
    (out / "vorgaenge").mkdir(parents=True, exist_ok=True)
    (out / urls.EU).write_text(page(eu, procs, europe), encoding="utf-8")
    return eu
