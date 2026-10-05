# Changelog

One entry per release (`docs/release.md`). Each starts with one sentence: what can a reader do now that they could
not before? If that sentence is hard to write, the release is not a finished vertical slice yet.

## Unreleased

- UI check (`scripts/ui_check.py`, `scripts/ui_check.sh`, `tests/test_ui.py`, in CI): every kind of page at desktop
  and phone width, errors and screenshot comparison. Its first run found and this release fixes:
  - the Orte page's script did not run: a line was split inside its JavaScript, so no place search and no map;
  - the week strip's bars and the calendar's week cards shared the class `.wk`: on Sitzungen the sittings of a week
    stood side by side and the page was 1,819 px wide (the strip's bars are now `.swk`);
  - Radar links did not wrap: on a phone the front page was 802 px wide.

Readers pick by seeing: on the Vorgänge, Sachgebiete, EU-Vorlagen, Abstimmungen, Fragen, Geschlossenheit,
Debattenkultur and Gremien pages every chart is also a filter, the filters combine, and the selection is in the
address, so it can be shared and the back button undoes it.

- `controls.py` and `controls.js` (new): tile field, fraction chips, pipeline, segmented bar, stacked bar rows and an
  activity strip, drawn in Python at build time, each part a button, each chart with "Als Tabelle". Without
  JavaScript the page shows the chart, its table and the full list.
- `vorgaenge/index.html`: the kinds as a segmented bar, the Gesetzgebungsvorgänge as a pipeline from "Eingebracht" to
  "Verkündet" with the branch "beendet ohne Gesetz" (the DIP Stände mapped in `procedures.STAGE`), the Einbringer as
  chips, a strip of the weeks. The selects "jede Art" and "jeder Stand" are gone. Long lists show the newest 30 and
  "mehr anzeigen".
- `sachgebiete/index.html`: a tile per Sachgebiet, its width by its Vorgänge, the table behind "Als Tabelle".
  `sachgebiete/<slug>.html`: the Einbringer as stacked bar rows that filter the Vorgänge, and the controls of the
  Vorgänge index.
- `vorgaenge/eu-vorlagen.html`: the Stand as a row of steps, the lead committees as chips (once the store has the
  referral table), the strip. `abstimmungen/index.html`: chips for namentlich, per Handzeichen, angenommen and
  abgelehnt instead of the two selects, and the strip; old `#art=…&ergebnis=…` links keep working.
- `regierung/index.html` (Fragen): the statistics are charts, and a click on one opens its list filtered (the
  Kleine Anfragen of a fraction or a month, the turns of one Regierungsbefragung). Each kind's list has chips for
  Fraktion, Ressort and Stand, the answer time as a bar and a column per month instead of the five selects.
- `abstimmungen/geschlossenheit.html`: a fraction's row of the small multiples shows its dissents; chips for
  Fraktion and own vote and the strip instead of the select.
- `debatte/index.html`: small multiples per fraction instead of the three tables of "Ton und Ordnung" (the tables
  behind "Als Tabelle"); the Ordnungsmaßnahmen are a list filtered by a card, kind, fraction and week.
- `gremien/index.html`: a tile per Gremium, its width by its current members, the bar its fractions, filtered by
  kind and name, "Als Liste" for a plain list. A Gremium's page filters its members by fraction, role and name.
- A Vorgang's date in lists is its latest step until the build date, so a law with an Inkrafttreten in 2030 no
  longer sorts first; the row says "tritt am … in Kraft".
- CI installs Node, and the tests that run the page scripts in Node fail there instead of being skipped.

Readers can open any of DIP's Sachgebiete and see what the 21st Bundestag did in it: the Vorgänge by kind and
Einbringer, the speeches, the decisions and the Drucksachen; the EU-Vorlagen have a page of their own.

- `sachgebiete/index.html` (`subjects.py`): every Sachgebiet with its Vorgänge (Gesetzgebung, Anträge, Kleine
  Anfragen), how many were debated, and the decisions, largest first. Below it what has no Sachgebiet: Fragen,
  EU-Vorlagen, Petitionen, and the plenary business without a Vorgang.
- `sachgebiete/<slug>.html`: an entity page per Sachgebiet with the facets Einbringer, Vorgänge (filterable, a
  Vorgang without a page here links DIP), Reden, Abstimmungen und Beschlüsse, Drucksachen.
- `vorgaenge/eu-vorlagen.html` (`eu.py`): every EU-Vorlage with its Unterrichtung and a Stand from DIP's steps,
  filterable, linked with the Sachgebiet "Europapolitik und Europäische Union". The Ausschuss column waits for the
  foundation's referral table.
- Vorgänge has the sub-tabs Vorgänge | Sachgebiete | EU-Vorlagen. The Sachgebiete on a Vorgang page link their pages;
  the search finds Sachgebiete; the front page has a Sachgebiete tile; the Thema pages link the Sachgebiete.

Readers arriving at plenar-radar.de land on a front page that shows what the site offers and takes them there in
one click, and every page shows by its colour whether it states checkable facts (Recherche, blue) or selects and
interprets (Radar, violet).

- Front page `index.html` (`landing.py`): the house as it sits today, every seat linked to its card; the record in
  numbers; Recherche and Radar side by side; the latest sitting week and roll-call votes. The Abgeordnete list moved
  to `abgeordnete.html`, and old `/#…` links are forwarded there.
- `shell.css` (new, linked before `cards.css`): tokens, the header with its mode and the Radar elements. The top bar
  has the site's name in the centre and a violet Radar entry at the end.
- Kompass and Themen are Radar pages, with a method note above the footer. Every link into the Themenlandschaft
  and every topic chip is a Radar element.
- The Themen index no longer squeezes titles into the date column.

## v0.1.0 (2026-10-04)

Readers can look up every member of the 21st Bundestag at plenar-radar.de – speeches, votes, Drucksachen, committees,
their Wahlkreis – and follow every Vorgang, sitting and decision, each fact linked to its source.

The first tag: the site as it is live on 2026-10-04, with the compass on the foundation's stable decision ids.
