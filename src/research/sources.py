"""Über die Daten: `daten.html` with sources and licences, the date of the data, known gaps, and the foundation's
export under `daten/` (copied from FOUNDATION_EXPORT when set)."""

from __future__ import annotations

import datetime as dt
import os
import shutil
import sqlite3
from pathlib import Path

from research import data, urls
from research.questions import fragestunden
from research.ui import FOOTER, e, long_date, n, shell, short_date

STALE_AFTER_DAYS = 90  # as the foundation's government.STALE_AFTER_DAYS

SOURCES = (
    ("Plenarprotokolle, MdB-Stammdaten, namentliche Abstimmungen", "bundestag.de Open Data",
     "https://www.bundestag.de/services/opendata",
     "Amtliche Werke (§ 5 Abs. 2 UrhG) bzw. Nutzungsbedingungen von bundestag.de; frei für Berichterstattung, "
     "Bildung und Kultur, nicht für Werbung.", "„Deutscher Bundestag“ und die Dokumentnummer (BT-PlPr. 21/94)"),
    ("Drucksachen, Vorgänge, Urheberschaft, Fragen und Antworten", "DIP", "https://dip.bundestag.de",
     "Nutzungsbedingungen für das DIP (27.02.2023): maschinenlesbare Daten dürfen umfassend genutzt und "
     "weiterverarbeitet werden; PDFs sind amtliche Werke und werden nicht verändert.",
     "„Deutscher Bundestag/Bundesrat – DIP“ und BT-Drs./BT-PlPr. mit Nummer"),
    ("Abgeordneten-Profile, Bürgerfragen", "abgeordnetenwatch.de API", "https://www.abgeordnetenwatch.de/api",
     "CC0 1.0", "keine Pflicht; abgeordnetenwatch.de wird genannt"),
    ("Wahlergebnisse und Wahlkreise der Bundestagswahl 2025", "Die Bundeswahlleiterin",
     "https://www.bundeswahlleiterin.de", "Datenlizenz Deutschland – Namensnennung 2.0",
     "„© Die Bundeswahlleiterin, Wiesbaden 2025“; Karte mit GeoBasis-DE / BKG 2024"),
    ("Regierungsämter", "Wikidata", "https://www.wikidata.org", "CC0 1.0", "keine Pflicht"),
    ("Porträts", "bundestag.de Biografien, Wikimedia Commons", "https://commons.wikimedia.org",
     "Fotos sind Werke Dritter; Rechte nicht einzeln geprüft, Commons meist CC BY-SA 4.0",
     "der Bildnachweis unter jedem Foto, mit Link zur Quelle"),
)  # fmt: skip


def stale_roles(conn: sqlite3.Connection, days: int = STALE_AFTER_DAYS) -> list[dict]:
    """Government roles only the protocols show, still counted as current although no protocol has printed them for
    more than `days` before the newest sitting (the foundation's queries.stale_roles, read here from what the site
    shows: `data.government`)."""
    newest = conn.execute("SELECT max(date) FROM sitting").fetchone()[0]
    if newest is None:
        return []
    cutoff = (dt.date.fromisoformat(newest) - dt.timedelta(days=days)).isoformat()
    rows = [
        {**g, "days": (dt.date.fromisoformat(newest) - dt.date.fromisoformat(g["seen"])).days}
        for g in data.government(conn)
        if g["evidence"] and g["seen"] and g["seen"] < cutoff
    ]
    return sorted(rows, key=lambda g: (g["seen"], g["name"]))


def copy_export(out: Path, src: str | None = None) -> list[dict]:
    """Copy the foundation's export (`bdf export`: gzipped CSVs, datapackage.json, README.md) from FOUNDATION_EXPORT
    into out/daten/; returns the files there with their size. Without the variable or folder: what is already there."""
    src = src if src is not None else os.environ.get("FOUNDATION_EXPORT")
    dest = out / "daten"
    if src and Path(src).is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    if not dest.is_dir():
        return []
    return [{"path": p.relative_to(out).as_posix(), "name": p.relative_to(dest).as_posix(), "size": p.stat().st_size}
            for p in sorted(dest.rglob("*")) if p.is_file()]  # fmt: skip


def size(b: int) -> str:
    for unit in ("Bytes", "KB", "MB"):
        if b < 1024 or unit == "MB":
            return f"{b:.0f} {unit}" if unit == "Bytes" else f"{b:.1f} {unit}".replace(".", ",")
        b /= 1024
    return ""


def missing_gap(missing: dict[str, list[dict]]) -> str:
    """The Beratungen DIP records whose protocol text is not in the store (procedures.missing_debates), by sitting."""
    rows = "".join(
        f"<li>Sitzung {e(sid)}: " + "; ".join(
            f'<a href="{e(urls.vorgang(x["vorgang"]))}">{e(x["title"][:90])}</a> ({e(x["what"])}, '
            f'<a href="{e(x["pdf"])}">S. {e(x["pages"])}</a>)' for x in xs) + "</li>"
        for sid, xs in missing.items()
    )  # fmt: skip
    k = sum(len(xs) for xs in missing.values())
    return (
        f"<li>Beratungen ohne Protokolltext: {n(k)} Beratungen in {n(len(missing))} Sitzungen, die das DIP im "
        "Plenarprotokoll verzeichnet, unter denen aber kein Tagesordnungspunkt im Datenbestand eine Drucksache des "
        "Vorgangs nennt. Ein bekannter Grund: Der Bundestag gab manche Protokolle beim Einlesen noch in der "
        "vorläufigen Fassung aus, der die Debatten am späten Abend fehlen; das endgültige PDF enthält sie. Die "
        f"Seiten der Vorgänge zeigen diese Schritte mit den Beschlüssen laut DIP.<ul>{rows}</ul></li>"
    )


def page(meta: dict, stale: list[dict], fragestunden: tuple[int, int], files: list[dict], built: str,
         missing: dict[str, list[dict]] | None = None) -> str:  # fmt: skip
    rows = "".join(
        f'<tr><td class="l">{e(what)}</td><td class="l"><a href="{e(url)}">{e(who)}</a></td><td class="l">{e(terms)}'
        f'</td><td class="l">{e(credit)}</td></tr>'
        for what, who, url, terms, credit in SOURCES
    )
    sit = meta.get("sittings") or {}
    dip = meta.get("dip") or {}
    gaps = []
    if fragestunden[0] and not fragestunden[1]:
        gaps.append(
            f"<li>Fragestunden: {n(fragestunden[0])} stehen in der Tagesordnung, die mündlichen Fragen und "
            "Antworten fehlen im Datenbestand (vor dem nächsten Einlesen der Protokolle).</li>"
        )
    if dip and not dip.get("complete"):
        gaps.append("<li>DIP-Drucksachen sind noch nicht für jeden Sitzungsmonat geladen; Karten nennen deshalb "
                    "keine Summen für Drucksachen.</li>")  # fmt: skip
    if stale:
        items = "".join(
            f"<li>{e(g['name'])}, {e(g['office'])}: zuletzt belegt am {short_date(g['seen'])} "
            f"({n(g['days'])} Tage)</li>"
            for g in stale
        )
        gaps.append(
            f"<li>Regierungsämter, die nur die Plenarprotokolle belegen und seit mehr als {STALE_AFTER_DAYS} Tagen "
            f"vor der letzten Sitzung nicht mehr genannt wurden; sie gelten weiter als aktuell:<ul>{items}</ul></li>"
        )
    if missing:
        gaps.append(missing_gap(missing))
    gaps.append(
        "<li>Kleine Anfragen und Schriftliche Fragen: nur der Titel, nicht der Wortlaut der Frage; und die "
        "Fragenden einer Schriftlichen oder Mündlichen Frage nennt DIP je Sammeldrucksache, nicht je "
        'Frage (<a href="regierung/index.html#liste">Fragen</a>).</li>'
    )
    gaps.append("<li>Die Sitzordnung im Plenum ist ein Schema der Fraktionen, nicht der echte Sitzplan.</li>")
    if files:
        downloads = (
            '<p class="explain">Der Datenbestand von bundestag-data-foundation als Tabellen (CSV, gzip) mit '
            "Beschreibung (datapackage.json, README.md). Es gelten die Lizenzen und Quellenangaben oben.</p><ul>"
            + "".join(
                f'<li><a href="{e(f["path"])}">{e(f["name"])}</a> <span class="faint">{size(f["size"])}</span></li>'
                for f in files
            )  # fmt: skip
            + "</ul>"
        )
    else:
        downloads = '<p class="explain">In diesem Build liegt kein Export bei.</p>'
    body = f"""<section class="card"><h1>Über die Daten</h1><div class="lines">
<div>Letzte Sitzung im Datenbestand: <b>{e(long_date(sit["to"]) if sit.get("to") else "–")}</b>
({n(sit.get("n") or 0)} Sitzungen seit {e(short_date(sit["from"]) if sit.get("from") else "–")})</div>
<div>Drucksachen bis {e(short_date(dip["to"]) if dip.get("to") else "–")} · erstellt am {e(built)}</div></div></section>
<div class="qs"><h2>Quellen und Lizenzen</h2>
<div class="rows"><table class="plenum"><thead><tr><th>Was</th><th>Quelle</th><th>Bedingungen</th><th>Quellenangabe</th>
</tr></thead><tbody>{rows}</tbody></table></div>
<p class="explain">Zusammenfassung ohne Rechtsberatung, nach docs/licences.md von
<a href="https://github.com/jan-c-buchkremer/bundestag-data-foundation">bundestag-data-foundation</a>. Der Code ist MIT.
Kein Einsatz in verzerrendem oder herabsetzendem Zusammenhang (DIP-Nutzungsbedingungen Nr. 5).</p>
<h2>Bekannte Lücken</h2><ul>{"".join(gaps)}</ul>
<h2>Wie gezählt wird</h2><ul>
<li><a href="index.html">Abgeordnete</a>: eine Karte je Mitglied, jede Angabe mit Quelle; das Plenum, gefiltert nach
Fraktion, Ort oder Ausschuss, und die <a href="index.html#rollen">Rollen</a>.</li>
<li><a href="abstimmungen/index.html">Abstimmungen</a>: namentliche Abstimmungen und Beschlüsse per Handzeichen, diese
regelbasiert aus dem Text der Sitzungsleitung gelesen.</li>
<li><a href="sitzungen/index.html">Sitzungen</a>: die Sitzungswochen als Kalender, Tagesordnung und Reden je
Plenarprotokoll.</li>
<li><a href="vorgaenge/index.html">Vorgänge</a>: Gesetzgebung und alle im Plenum beratenen Vorlagen mit
ihrem Ablauf.</li>
<li><a href="orte/index.html">Orte</a>: Länder und Wahlkreise und wer sie vertritt, mit Karte und Suche nach Land,
Wahlkreis oder Gemeinde.</li>
<li><a href="gremien/index.html">Gremien</a>: Fraktionen, Ausschüsse und die Bundesregierung.</li>
<li><a href="regierung/index.html">Fragen an die Regierung</a>: Kleine Anfragen, Fragen und Regierungsbefragung nach
Fraktionen, und jede einzelne Frage zum Durchsuchen.</li>
<li>Entscheidungen und Regeln im Einzelnen:
<a href="https://github.com/jan-c-buchkremer/bundestag-research-platform/blob/main/docs/decisions.md">docs/decisions.md</a>.</li>
</ul>
<h2>Downloads</h2>{downloads}</div>
<footer>{FOOTER}</footer>"""
    return shell(root="", kind="p-data", active="data", title="Über die Daten",
                 desc="Quellen, Lizenzen, Stand und bekannte Lücken der Daten zum 21. Deutschen Bundestag.",
                 body=body, data={"kind": "data"}, head=STYLE)  # fmt: skip


STYLE = """<style>
.qs table.plenum td.l, .qs table.plenum th { text-align: left; white-space: normal; }
.qs .rows { overflow-x: auto; }
.qs ul { padding-left: 20px; }
.qs li { margin: 4px 0; }
</style>"""


def write(
    conn: sqlite3.Connection, out: Path, meta: dict, missing: dict[str, list[dict]] | None = None
) -> dict[str, int]:
    """Write daten.html (and copy the export into daten/); returns the number of downloadable files. `missing`:
    procedures.missing_debates, for the known gaps."""
    files = copy_export(out)
    built = dt.datetime.now().astimezone().strftime("%d.%m.%Y, %H:%M Uhr")
    html = page(meta, stale_roles(conn), fragestunden(conn), files, built, missing)
    (out / "daten.html").write_text(html, encoding="utf-8")
    return {"daten": len(files)}
