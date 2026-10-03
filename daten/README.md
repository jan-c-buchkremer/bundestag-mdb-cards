# Bundestag-Daten: offener Export

Stand: 2026-10-03T03:48:20Z · letzte Sitzung im Export: 2026-09-25

Alle Tabellen der [bundestag-data-foundation](https://github.com/jan-c-buchkremer/bundestag-data-foundation) als gzip-komprimierte CSV-Dateien (UTF-8, Kopfzeile,
nach Primärschlüssel sortiert; leeres Feld = kein Wert). `datapackage.json` beschreibt jede Tabelle nach dem
[Frictionless-Data-Package-Standard](https://datapackage.org/): Spalten mit Typ und Beschreibung (englisch),
Primär- und Fremdschlüssel, Quellen und Lizenzen je Tabelle.

Jede Zeile, die aus einer Quelle stammt, nennt sie: `source_url` (Dokument oder API-Datensatz),
`source_document_id` (zitierfähig, z. B. „BT-PlPr. 21/94“, „BT-Drs. 21/7300“) und `retrieved_at`.

| Datei | Zeilen | Größe |
|---|---:|---:|
| `agenda_item.csv.gz` | 1.089 | 116.8 KB |
| `agenda_item_paragraph.csv.gz` | 23.468 | 808.3 KB |
| `agenda_item_vorlage.csv.gz` | 2.719 | 33.7 KB |
| `agenda_sub_item.csv.gz` | 421 | 19.1 KB |
| `aw_profile.csv.gz` | 630 | 16.5 KB |
| `constituency.csv.gz` | 299 | 7.6 KB |
| `constituency_municipality.csv.gz` | 10.993 | 149.7 KB |
| `constituency_result.csv.gz` | 7.357 | 110.8 KB |
| `decision.csv.gz` | 1.289 | 111.6 KB |
| `decision_fraction.csv.gz` | 5.720 | 16.9 KB |
| `drucksache.csv.gz` | 8.312 | 511.2 KB |
| `drucksache_author.csv.gz` | 64.154 | 1.2 MB |
| `election_candidacy.csv.gz` | 630 | 21.8 KB |
| `government_role.csv.gz` | 61 | 3.4 KB |
| `individual_vote.csv.gz` | 44.726 | 618.8 KB |
| `interjection.csv.gz` | 155.490 | 2.1 MB |
| `mandate.csv.gz` | 13.046 | 148.8 KB |
| `membership.csv.gz` | 16.955 | 186.7 KB |
| `person.csv.gz` | 4.630 | 117.9 KB |
| `person_photo.csv.gz` | 644 | 62.0 KB |
| `roll_call_vote.csv.gz` | 71 | 5.5 KB |
| `side_job.csv.gz` | 4.633 | 239.8 KB |
| `sitting.csv.gz` | 97 | 3.2 KB |
| `speech.csv.gz` | 15.446 | 14.0 MB |
| `speech_paragraph.csv.gz` | 274.336 | 17.5 MB |
| `vorgang.csv.gz` | 17.632 | 973.2 KB |
| `vorgang_drucksache.csv.gz` | 21.376 | 67.9 KB |
| `vorgang_position.csv.gz` | 30.933 | 678.0 KB |

## Quellen und Pflichtangaben

Wer die Daten weitergibt oder veröffentlicht, nennt je Quelle, was dort verlangt ist:

- **Deutscher Bundestag: Open Data (Plenarprotokolle, MdB-Stammdaten, Namentliche Abstimmungen)** (https://www.bundestag.de/services/opendata), Lizenz: Nutzungsbedingungen des Deutschen Bundestages; Plenarprotokolle sind amtliche Werke (§ 5 UrhG) (https://www.bundestag.de/nutzungsbedingungen).  
  Quelle: "Deutscher Bundestag", bei Plenarprotokollen mit Nummer (BT-PlPr. 21/94). Keine Nutzung für Werbezwecke.
- **Deutscher Bundestag/Bundesrat: DIP (Dokumentations- und Informationssystem für Parlamentsmaterialien)** (https://dip.bundestag.de), Lizenz: Nutzungsbedingungen für das DIP (27.02.2023) (https://github.com/jan-c-buchkremer/bundestag-data-foundation/blob/main/docs/nutzungsbedingungen_dip.pdf).  
  "Deutscher Bundestag/Bundesrat – DIP", bei Drucksachen und Plenarprotokollen mit Nummer (BT-Drs. 21/7300, BT-PlPr. 21/94). Änderungen sind zu kennzeichnen. Bei kommerzieller Nutzung: Hinweis, dass die Daten unter dip.bundestag.de kostenfrei verfügbar sind.
- **abgeordnetenwatch.de API v2** (https://www.abgeordnetenwatch.de/api), Lizenz: CC0 1.0 Universal (https://creativecommons.org/publicdomain/zero/1.0/).  
  Keine Pflicht; Nennung von abgeordnetenwatch.de erbeten.
- **Die Bundeswahlleiterin: Open Data Bundestagswahl 2025** (https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata.html), Lizenz: Datenlizenz Deutschland – Namensnennung – Version 2.0 (https://www.govdata.de/dl-de/by-2-0).  
  "© Die Bundeswahlleiterin, Wiesbaden 2025", mit Link auf die Lizenz; Änderungen sind zu kennzeichnen.
- **Wikidata** (https://www.wikidata.org), Lizenz: CC0 1.0 Universal (https://creativecommons.org/publicdomain/zero/1.0/).  
  Keine Pflicht.
- **Porträts: bundestag.de (Abgeordnetenbiografien) und Wikimedia Commons** (https://www.bundestag.de/abgeordnete), Lizenz: Je Bild: Rechteinhaber laut person_photo.credit; Commons-Dateien meist CC BY-SA 4.0 (Lizenz auf der Dateiseite, source_url) (https://github.com/jan-c-buchkremer/bundestag-data-foundation/blob/main/docs/licences.md#portraits-bundestagde-wikimedia-commons).  
  Bei jedem Bild die Angabe aus person_photo.credit; bei Commons-Bildern zusätzlich Lizenz mit Link auf die Dateiseite. Der Export enthält nur Bild-URLs und Credits, keine Bilder; die Rechte an den Fotos sind nicht einzeln geprüft.

Zusammenfassung der Nutzungsbedingungen, keine Rechtsberatung. Einzelheiten:
[docs/licences.md](https://github.com/jan-c-buchkremer/bundestag-data-foundation/blob/main/docs/licences.md). Datenmodell und Spaltenbedeutung:
[docs/design.md](https://github.com/jan-c-buchkremer/bundestag-data-foundation/blob/main/docs/design.md).

Die Daten werden automatisch aus den Quellen gelesen (Protokoll-XML, XLSX, APIs); Fehler beim Einlesen sind möglich.
Maßgeblich ist das Originaldokument unter `source_url`.
