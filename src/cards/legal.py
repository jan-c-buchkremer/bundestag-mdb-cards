"""The two legal pages at the site root: impressum.html (who runs the site, how to reach him) and datenschutz.html
(what happens to a visitor's data). Every footer links both (ui.LEGAL). The privacy page describes the deployment in
the infra repo: Cloudflare in front, a Caddy without access logs behind it, fonts and scripts from the site itself.
Change it when that changes."""

from __future__ import annotations

from pathlib import Path

from cards.ui import FOOTER, shell

NAME = "Jan Buchkremer"
MAIL = "jan.c.buchkremer@gmail.com"
REPO = "https://github.com/jan-c-buchkremer/bundestag-mdb-cards"
AS_OF = "Oktober 2026"
CONTACT = f'{NAME}<br>E-Mail: <a href="mailto:{MAIL}">{MAIL}</a>'

STYLE = """<style>
.qs ul { padding-left: 20px; }
.qs li { margin: 4px 0; }
.qs p { max-width: 72ch; }
</style>"""


def impressum() -> str:
    body = f"""<section class="card"><h1>Impressum</h1><div class="lines">
<div>Ein privates, nicht-kommerzielles Projekt ohne Werbung.</div></div></section>
<div class="qs">
<h2>Anbieter und verantwortlich für den Inhalt</h2>
<p>{CONTACT}</p>
<h2>Inhalte</h2>
<p>Die Seiten werden automatisch aus öffentlichen Daten erzeugt, vor allem aus den Open Data des Deutschen
Bundestages; welche Quellen unter welcher Lizenz verwendet werden, steht unter <a href="daten.html">Über die
Daten</a>. Die Aufbereitung ist sorgfältig, aber nicht fehlerfrei. Maßgeblich sind die verlinkten Originalquellen.
Hinweise auf Fehler bitte per E-Mail oder als <a href="{REPO}/issues">Issue auf GitHub</a>.</p>
<h2>Links auf andere Seiten</h2>
<p>Für die Inhalte verlinkter Seiten sind ausschließlich deren Betreiber verantwortlich. Wird mir eine
Rechtsverletzung auf einer verlinkten Seite bekannt, entferne ich den Link.</p>
<h2>Lizenzen</h2>
<p>Der Code der Seite steht unter der MIT-Lizenz (<a href="{REPO}">bundestag-mdb-cards</a>). Für die Daten gelten
die Lizenzen ihrer Quellen (<a href="daten.html">Über die Daten</a>). Die Schrift Inter steht unter der SIL Open Font
License 1.1.</p>
<h2>Datenschutz</h2>
<p>Siehe <a href="datenschutz.html">Datenschutzerklärung</a>.</p>
</div>
<footer>{FOOTER}</footer>"""
    return shell(root="", kind="p-legal", active="", title="Impressum",
                 desc="Wer plenar-radar.de betreibt und wie er zu erreichen ist.",
                 body=body, data={"kind": "legal"}, head=STYLE)  # fmt: skip


def datenschutz() -> str:
    body = f"""<section class="card"><h1>Datenschutzerklärung</h1><div class="lines">
<div>Keine Cookies, kein Tracking, keine Statistik über Besuche.</div><div>Stand: {AS_OF}</div></div></section>
<div class="qs">
<h2>Verantwortlich</h2>
<p>{CONTACT}</p>
<h2>Kurz gesagt</h2>
<ul>
<li>Die Seite setzt keine Cookies, speichert nichts in Ihrem Browser und zählt keine Besuche.</li>
<li>Schrift und Skripte kommen von dieser Seite selbst; beim Aufruf werden keine Inhalte von anderen Servern
nachgeladen.</li>
<li>Es gibt keine Konten und keine Formulare. Die Suche läuft vollständig in Ihrem Browser.</li>
<li>Links auf andere Seiten (etwa den Bundestag oder GitHub) sind gewöhnliche Links: Erst wenn Sie einem folgen,
erfährt die andere Seite von Ihrem Besuch, und es gilt deren Datenschutzerklärung.</li>
</ul>
<h2>Auslieferung über Cloudflare</h2>
<p>Die Seite wird über das Netzwerk von Cloudflare ausgeliefert (Cloudflare, Inc., 101 Townsend St., San Francisco,
CA 94107, USA). Dabei verarbeitet Cloudflare die Daten, die bei jedem Abruf einer Webseite technisch anfallen: Ihre
IP-Adresse, Datum und Uhrzeit, die aufgerufene Adresse, die Kennung Ihres Browsers (User-Agent) und die zuvor besuchte
Seite (Referrer). Cloudflare nutzt diese Daten, um die Seite auszuliefern, zwischenzuspeichern und vor Angriffen zu
schützen; zur Abwehr automatisierter Zugriffe kann Cloudflare ein technisch notwendiges Cookie setzen.</p>
<p>Rechtsgrundlage ist Art. 6 Abs. 1 lit. f DSGVO: mein berechtigtes Interesse an einer schnellen und sicheren
Auslieferung der Seite. Cloudflare verarbeitet die Daten als Auftragsverarbeiter nach Art. 28 DSGVO. Eine
Übermittlung in die USA ist möglich; Cloudflare ist nach dem EU-US Data Privacy Framework zertifiziert, für das ein
Angemessenheitsbeschluss der EU-Kommission besteht (Art. 45 DSGVO). Mehr dazu in der
<a href="https://www.cloudflare.com/privacypolicy/">Datenschutzerklärung von Cloudflare</a>.</p>
<h2>Server</h2>
<p>Hinter Cloudflare liegt die Seite auf einem eigenen Server in Deutschland. Er speichert keine Zugriffsprotokolle
und damit auch keine IP-Adressen der Besucher.</p>
<h2>E-Mail</h2>
<p>Wenn Sie mir schreiben, verwende ich Ihre Adresse und Ihre Nachricht nur, um zu antworten, und lösche sie, wenn
sie dafür nicht mehr nötig sind (Art. 6 Abs. 1 lit. f DSGVO). Das Postfach liegt bei Google (Gmail).</p>
<h2>Ihre Rechte</h2>
<p>Sie haben das Recht auf Auskunft (Art. 15 DSGVO), Berichtigung (Art. 16), Löschung (Art. 17), Einschränkung der
Verarbeitung (Art. 18), Datenübertragbarkeit (Art. 20) und Widerspruch gegen die Verarbeitung (Art. 21). Eine
E-Mail genügt. Außerdem können Sie sich bei einer Datenschutz-Aufsichtsbehörde beschweren (Art. 77 DSGVO), etwa bei
der Ihres Wohnorts.</p>
</div>
<footer>{FOOTER}</footer>"""
    return shell(root="", kind="p-legal", active="", title="Datenschutzerklärung",
                 desc="Welche Daten beim Besuch von plenar-radar.de anfallen und was mit ihnen geschieht.",
                 body=body, data={"kind": "legal"}, head=STYLE)  # fmt: skip


def write(out: Path) -> None:
    (out / "impressum.html").write_text(impressum(), encoding="utf-8")
    (out / "datenschutz.html").write_text(datenschutz(), encoding="utf-8")
