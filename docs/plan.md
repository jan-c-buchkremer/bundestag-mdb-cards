# Plan: an info card for every MdB

## Current goal

Goals in the order they are worked on, each from the reader's side. No dates: how much time there is varies, so the
order is the plan. The first unfinished goal is the current one; every change is reviewed against it. Ideas that
don't serve it go on "Not now", not into code.

1. **Front page and the two parts of the site** (in review: research #55, radar #16). A reader who arrives at
   plenar-radar.de lands on a front page that shows what the site offers and takes them there in one click, and on
   every page can tell by its look whether they are in Research (checkable facts, blue) or on the Radar (selection
   and interpretation, violet; docs/architecture.md, "Telling Radar apart").
   - The front page at `/`, the Abgeordnete list at `abgeordnete.html` (old `/#…` links forward there).
   - One shell with a mode (`shell.css`): Recherche or Radar in the header; Kompass and Themen are Radar pages with
     a method note; Radar links inside Research pages are Radar elements; the Themenlandschaft takes the same header.
2. **Sachgebiete as an entity** (merged: research #56). A reader can open any of DIP's 28 Sachgebiete and see what the Bundestag did in
   it: the Vorgänge by kind, the Drucksachen, the debates with their speeches, the decisions and roll-call votes,
   and which fractions were active, each with its source. A Sachgebiet is the Bundestag's own classification, so it
   is Research, not Radar.
   - EU-Vorlagen get their own page as a kind of Vorgang (not beside the Sachgebiete: a Sachgebiet says what
     something is about, an EU-Vorlage where it comes from), with the committee each went to, linked with the
     Sachgebiet "Europapolitik und Europäische Union".
   - Vorgänge without a Sachgebiet (Fragen, EU-Vorlagen, petitions) and plenary business without a Vorgang
     (Aktuelle Stunden, Regierungsbefragung, Fragestunde) are named as such, not hidden.
3. **Choose by seeing.** A reader picks what to look at by seeing it, not by reading a dropdown: the data itself is
   the control. The big Sachgebiete are big tiles, the fractions are coloured chips, a bill's way through the
   procedure is a pipeline whose stages they click, a strip of weeks narrows the time. Every chart is also a filter
   (click, keyboard), filters combine, the state lives in the URL fragment (shareable, the back button works), one
   "zurücksetzen". Every chart has "Als Liste" or "Als Tabelle" for what was there before; without JavaScript the
   page shows the chart, its table and the full list. Sizes and order come from counts only (no rankings of people,
   no ratings). Everything here is Research: the accent and the fraction colours, never the Radar's violet.
   - The components (`controls.py`, drawn in Python at build time as HTML with inline sizes, one button per
     clickable part; `controls.js`, the one shared script): tile field, fraction chips, pipeline, segmented bar,
     stacked bar rows, activity strip (a bar per calendar week, the sitting weeks marked; long lists show the newest
     30 of the filter result and "mehr anzeigen"), month columns, small multiples. The chart/table switch is
     `ansicht=<chart>` in the fragment.
   - The pipeline's stages and which DIP Beratungsstand belongs to each: one table, `procedures.STAGE`. The exact
     DIP Stand stays on every row and in the pipeline's table.
   - A Vorgang's date in lists is its latest step that has happened by the build date; a later Inkrafttreten is
     named on the row.
   - Built in this order. Merged (research #57): `vorgaenge/index.html`, `sachgebiete/index.html`,
     `sachgebiete/<slug>.html`, `vorgaenge/eu-vorlagen.html`, `abstimmungen/index.html`. In review, the second round:
     - Fragen (`questions.py`): the statistics are charts that choose a list and filter it (a click on a fraction's
       row of the Kleine Anfragen opens their list for that fraction); each kind's list has chips for Fraktion,
       Ressort and Stand, the answer time as a segmented bar and a column per month instead of the selects. The
       lists still load from `regierung/<kind>.json`; `questions.facets` and `fragen.js` derive the same filter
       values from it (checked in Node), and `#liste=<kind>` still opens a kind.
     - Geschlossenheit (`cohesion.py`): each fraction's row of the small multiples filters the dissents; chips for
       Fraktion and own vote, the strip.
     - Debattenkultur (`debate.py`): small multiples per fraction (Ordnungsmaßnahmen, Zwischenfragen, interruptions
       per month on one scale) instead of the three tables of "Ton und Ordnung", each card a filter of the
       Ordnungsmaßnahmen below.
     - Gremien (`bodies.py`): a tile per Gremium by current members with its fractions, filtered by kind and name;
       on a Gremium's page the composition, role chips and name filter the members.
   - Not yet: the Fraktion pages (`fraktionen/<token>.html`) and the Redeanteile of Debattenkultur, which are bar
     charts in tables already.

## Not now

Ideas that don't serve the current goal. Each names what it would give a reader.

- Members per Sachgebiet: which Abgeordnete work on a Sachgebiet, from the Drucksachen they signed and the speeches
  they gave on its Vorgänge. It would show a reader who to follow on a subject. Not now: a Fraktionsantrag names the
  whole fraction as Urheber, so a count per member mostly measures fraction size and misleads. It needs the
  signatories who actually drafted a document, which DIP does not separate.
- Building one card or one section alone (a fast path for `cards preview`): the build has no subset mode; a full
  preview build takes about 2 minutes.

---

Status: **concept, decisions taken 2026-09-27** (section 9). Sections 1–8 describe what is possible; section 9 lists the decisions
we take together before any code is written, each with options and a recommendation. Decided points move to
`decisions.md` and get marked here.

All numbers below were measured on the live foundation store on 2026-09-27 (95 sittings, 2025-03-25 to
2026-09-23). The DIP backfill for the whole Wahlperiode was running that day, so DIP figures are still to come.

---

## 1. Goal

One page per member of the 21st Bundestag that answers, with a source for every fact:

- **Who is this?** Person, party, constituency or list, how long in the Bundestag, which committees.
- **What do they do in the plenary?** Speeches, topics, questions, interjections, how the house reacts.
- **How do they vote?** Every roll-call vote, own vote next to the fraction's line.
- **What do they put their name to?** Anträge, Gesetzentwürfe, Kleine Anfragen, Schriftliche Fragen.

### Audience: two layers

| Layer | Reader | Promise | Form |
|---|---|---|---|
| 1 — Card | interested citizens, "who is my MdB?" | readable in 30 seconds, plain German sentences, few numbers, each with context | one screen, phone first |
| 2 — Detail | journalists, researchers, the curious | every number can be opened down to the source document; lists, filters, export | tabs below the card |

The layers are one page, not two products: the card is the top of the detail view, and every sentence on the
card links to the tab that proves it.

### Non-goals

- No ranking of members ("most active", "laziest"). Comparisons only with context (section 7).
- No evaluation of positions (left/right scores, sentiment of speeches).
- No private data beyond what the Bundestag and abgeordnetenwatch publish about the public office.
- No writing into the foundation store; new facts are added to the foundation itself (section 8).

---

## 2. What the data holds today

### Persons and mandates

| What | Count | Source |
|---|---|---|
| Persons with a WP 21 mandate | 635 (630 sitting now, 5 left) | Stammdaten |
| Mandate type (Stammdaten) | 276 Direktwahl, 359 Landesliste | Stammdaten |
| How won (abgeordnetenwatch) | 272 constituency, 348 list, 10 moved up | aw `electoral_data` |
| Constituency result in % | 272 | aw (raw only) |
| List position | 525 | aw (raw only) |
| Gender | 428 männlich, 206 weiblich, 1 divers | Stammdaten |
| Wahlperioden served (incl. 21) | 227 first-termers, 159 in their 2nd, 96 in their 3rd … one in their 10th | Stammdaten mandate history since WP 1 |
| Wikidata QID, abgeordnetenwatch id | 626 of 635 | aw, validated by name and birth year |
| Education / occupation text | 526 / 556 | aw (raw only) |
| Citizen questions on abgeordnetenwatch | 19,375 asked, 13,484 answered (all 630 current members have figures) | aw (raw only) |

Also per person: birth date and place, academic title, name prefix, party.

### Memberships

1,992 committee memberships in 33 committees, with role: Ordentliches Mitglied (1,473), Stellvertretendes
Mitglied (1,354), Obfrau/Obmann (158), Vorsitz and stellvertretender Vorsitz (256). Plus 641 fraction memberships
and 1,384 others (Gremien, Parlamentariergruppen, …), each with from/to dates.

### Plenary

| What | Count |
|---|---|
| Speeches | 13,024 (12,642 by WP 21 MdBs, 296 by non-MdBs such as ministers without mandate and Länder representatives) |
| Speeches per MdB | average 20, maximum 161, 15 MdBs without any |
| Paragraphs | 250,988, of which 90,868 are `comment` (applause, interjections, laughter) |
| Applause paragraphs | 55,622 ("Beifall bei der SPD und bei Abgeordneten der CDU/CSU") |
| Named interjections | ≈ 37,800 by a first pattern ("Friedrich Merz [CDU/CSU]: Reden Sie mal …"); not yet validated |
| Zwischenfragen / Kurzinterventionen | derivable from split speech ids; the landscape counts 613 in WP 21 (509 announced as question, 3 as Kurzintervention, 104 unannounced) |

### Votes

71 roll-call votes, 630 rows each (44,726 rows, 4 not matched to a person). Per vote: own vote, fraction
majority, totals, XLSX and PDF source. The link vote → Drucksache/Vorgang comes from DIP (see below).

### DIP (backfill in progress)

The first real week (6–10 July 2026) gave 251 Drucksachen with 2,015 activities. Per member this yields:

- **Authored:** Antrag, Kleine Anfrage, Entschließungsantrag, Änderungsantrag, Gesetzentwurf, Frage (Schriftliche Fragen).
- **Rapporteur:** Berichterstattung on a Beschlussempfehlung, a separate role, not authorship.
- **Topics:** Vorgang `sachgebiet` (the Bundestag's own subject index) for every authored document.
- **Vote link:** which Drucksache a roll-call vote decided (all 10 votes of that week linked).

### Topic landscape

For every week the landscape has a topic cluster per speech (`data/landscape/out/<week>.json`: cluster, agenda
item, five most similar speeches) and an embedding cache (`landscape.sqlite`, multilingual-e5-base, one vector per
speech text). Two limits matter here: cluster ids are **per week** and not comparable across weeks, and the JSON
carries the speaker name, not the MdB id.

---

## 3. Layer 1 — the card

A sketch; wording and order to be decided (D2, D6).

```
┌──────────────────────────────────────────────────────────────┐
│ [Foto]  Dr. Beispiel Muster                     SPD           │
│         Wahlkreis 14 · Rostock – Landkreis Rostock II         │
│         direkt gewählt (38,2 %) · im Bundestag seit 2017      │
│                                                              │
│  Ausschüsse  Gesundheit (Obfrau) · Arbeit und Soziales (Stv.) │
│                                                              │
│  • hat 23 Reden gehalten, meist zu Gesundheit und Pflege      │
│  • stimmte in 2 von 71 namentlichen Abstimmungen anders       │
│    als die eigene Fraktion                                   │
│  • hat 14 Kleine Anfragen und 3 Anträge mitgezeichnet         │
│  • beantwortete 95 von 107 Fragen auf abgeordnetenwatch.de    │
│                                                              │
│  Zuletzt im Plenum  8. Juli · Pflegereform (Rede, 6 min) →    │
└──────────────────────────────────────────────────────────────┘
```

Rules for the card:

- Every bullet is a sentence, not a bare number, and links to its tab.
- A bullet only appears when it says something. A minister's card does not lead with "0 Kleine Anfragen" but with the office.
- **Role-aware context line** for members whose plenary behaviour follows their office: ministers and parliamentary state
  secretaries, Präsidium (they chair instead of speaking), fraction chairs and parliamentary managers.
- "Seit" from the mandate history; gaps (left and came back) are shown in the detail layer, not on the card.

---

## 4. Layer 2 — the detail view

| Tab | Content | Source |
|---|---|---|
| **Reden** | every speech: date, agenda item, topic, length, applause received, link to PDF; filter by topic and period | protocols, landscape |
| **Abstimmungen** | every roll-call vote: own vote, fraction majority and split, whole-house result, decided Drucksache; deviations highlighted; absences listed without judgement | vote XLSX, DIP |
| **Drucksachen** | authored documents grouped by type and `sachgebiet`, with co-author count; rapporteur roles in their own list | DIP |
| **Ausschüsse & Funktionen** | memberships with role and dates, as a timeline | Stammdaten |
| **Im Plenum** | Zwischenfragen asked and received (with whom), Kurzinterventionen, named interjections made, applause received by fraction, laughter and objections | protocols (`comment` paragraphs) |
| **Laufbahn** | mandate history since the first Wahlperiode, constituency results, list positions, moved-up dates | Stammdaten, aw |
| **Quellen** | every source used on the page with retrieval date and licence line | all |

Exports: CSV/JSON per tab for layer-2 readers (cheap if pages are built from JSON anyway, D1).

---

## 5. Derived views and ideas

Each of these needs a caveat on the page; section 7 lists them.

1. **Percentiles within the own fraction**, not rankings: "spricht mehr als 80 % ihrer Fraktionskolleginnen".
   Fractions divide speaking time by size and role, so comparing across fractions measures the fraction, not the person.
2. **Deviation list.** Votes where the member went against the fraction majority, with the Drucksache. The most
   telling item for journalists; rare, so it needs a "nie abgewichen" state that does not read as a flaw.
3. **Topic fingerprint.** The subjects a member works on, from two independent sources: DIP `sachgebiet` of authored
   documents (the Bundestag's own index) and the topics of their speeches. Agreement between the two is a quality signal.
4. **Ähnliche Abgeordnete.** Nearest members by mean speech embedding, deliberately showing cross-fraction neighbours
   ("spricht über ähnliche Themen wie …"). Needs a guard against pure agenda overlap (same committee, same debates).
5. **Interjection and applause network.** Who interjects on whom, and which fractions applaud whom. Cross-fraction
   applause is a rare, readable signal of consensus. Needs the structured interjections (section 8).
6. **Activity timeline.** Speeches, documents and votes per sitting week as a strip; shows parental leave, office changes
   and moved-up dates without comment.
7. **Constituency view.** All members connected to one Wahlkreis: the directly elected one and the list members who
   stood there. This is how citizens actually ask the question.
8. **Office changes.** Members who became ministers or state secretaries during the term: the card switches its
   context line from that date.

---

## 6. Entry points

- **Index:** all members as a sortable, filterable list: name search, fraction, state, committee, first-termer,
  direct/list. Static, one JSON bundle.
- **Mein Wahlkreis:** constituency list (299 Wahlkreise) → the members connected to it (idea 7). Built with a map of the Wahlkreise (2026-09-28).
- **Plenum:** the seating chart as the default entry (2026-09-28), filtered by the same search and chips as the list.
- **Postcode search:** needs a new source (Bundeswahlleiterin: Gemeinde/PLZ → Wahlkreis; postcodes can span
  several constituencies, so the answer is sometimes "one of these two"). D8.
- **Deep links:** `/<mdb-id>.html#abstimmungen` and from the landscape: a click on a speaker could open their card.

---

## 7. Fairness and pitfalls

These decide whether the cards are trustworthy; each has a concrete consequence for the design.

| Pitfall | Consequence |
|---|---|
| Activity is not quality. Many speeches can mean many small debates. | No rankings; counts always in sentences with context; percentiles only within the fraction (D6). |
| Office changes behaviour: ministers answer rather than ask, Präsidium members chair rather than speak, fraction leaders speak in the big debates. | Role-aware context line; comparisons exclude or mark members with such roles. |
| Absence has reasons the data does not show: illness, parental leave, pairing agreements, official travel. | Absences listed, never scored; one sentence on the page says why. |
| Only 71 votes are roll-call votes; most decisions are by show of hands, recorded per fraction only. | Say so next to every vote statistic ("71 namentliche Abstimmungen, nicht alle Beschlüsse"). |
| Fraction Anträge are often signed by the whole fraction. | Show co-author count; separate "eine von 3" from "eine von 120"; no totals on the card that are just fraction size. |
| Kleine Anfragen are an opposition instrument; coalition members file few. | Never compare across government/opposition without saying so. |
| Name matching errors (4 unmatched vote rows, Nachrücker missing from Stammdaten). | Show the foundation's match status; a "Fehler melden" link per card. |
| Photos: licences differ per image; some members have none. | Licence line under each photo; a neutral placeholder, not a silhouette that suggests something. |
| Personal data: birth date and place are public in the Stammdaten. | Full date and place are shown (D11); nothing beyond the Stammdaten and abgeordnetenwatch. |
| Topic labels from clustering can be wrong or unfortunate. | Prefer DIP `sachgebiet` on the card; cluster labels only in the detail view. |

---

## 8. Data work, and where it belongs

The foundation rule stays: **facts with provenance go into the foundation; aggregates and presentation live here.**

| Work | Where | Needed for |
|---|---|---|
| abgeordnetenwatch `electoral_data` (result %, list position, how won), education, occupation, question statistics into the store | foundation | card, Laufbahn |
| Structured interjections: parse `comment` paragraphs into rows (who: fraction or named person; kind: Beifall, Zuruf, Heiterkeit, Widerspruch, Lachen; target speech) | foundation | Im Plenum, network (idea 5) |
| Zwischenfrage / Kurzintervention flag as a column (today the landscape derives it) | foundation | Im Plenum; removes duplicate logic |
| Page numbers from `druckseitennummer` markers | foundation | deep links into the PDF |
| Photos: Wikidata P18 → Wikimedia Commons file + licence, or Bundestag photos (licence to check) | foundation (as a fetch source) | card |
| Office periods (minister, state secretary, Präsidium) | already in the store as Stammdaten memberships (kind `other`), used by the MVP | role-aware context line |
| PLZ → Wahlkreis | foundation (new source) | postcode search (D8) |
| WP-wide topic per speech with a person id | landscape (export) or here | topic fingerprint (idea 3) |
| Percentiles, deviation lists, similarity, timelines | here | layer 1 and 2 |

---

## 9. Open decisions

Mark each with **Entscheidung:** and a date when settled.

**D1 — Stack.**
(a) Static site: Python build reads the store, writes one HTML page per member + index + JSON bundle, published
to GitHub Pages like the landscape, rebuilt daily after `bdf update`. (b) Small server app (FastAPI/Datasette)
querying the store live.
*Recommendation: (a).* Same deployment path as the landscape, no running service, pages keep working if the
server is down. 635 pages at ~100–300 KB is well within Pages limits.
**Entscheidung:** (a) static site, Python build, GitHub Pages, rebuilt daily after `bdf update`. (2026-09-27)

**D2 — MVP scope.**
(a) Card + Reden + Abstimmungen + Ausschüsse first, the rest in later phases. (b) Everything at once.
*Recommendation: (a).* Those three need no foundation extension beyond what exists; Drucksachen follows as soon as
the DIP backfill is ingested.
**Entscheidung:** (a) card + Reden + Abstimmungen + Ausschüsse first; Drucksachen once the DIP backfill is ingested. (2026-09-27)

**D3 — Topics.**
(a) Reuse the landscape's embedding cache and compute a WP-wide clustering here (the landscape's per-week clusters
are not comparable across weeks). (b) The landscape exports a WP-wide topic per speech with person id, and cards read it.
(c) Only DIP `sachgebiet`, no speech topics.
*Recommendation: (c) for the MVP card, (b) afterwards.* The landscape owns embeddings and topic modelling;
duplicating it here would drift.
**Entscheidung:** (c) DIP `sachgebiet` only for the MVP, (b) a landscape export afterwards. (2026-09-27)

**D4 — Foundation extensions, order.**
*Recommendation:* 1. abgeordnetenwatch electoral data and statistics (small, raw files already there),
2. office periods (role-aware line), 3. structured interjections (largest, unlocks "Im Plenum"), 4. photos,
5. page numbers.
**Entscheidung:** order as recommended; item 4 means Bundestag photos (D5). (2026-09-27)

**D5 — Photos.**
(a) Wikidata/Commons with licence line. (b) Bundestag portrait photos, if the licence allows reuse. (c) No photos in the MVP.
*Recommendation: (c) for the MVP, then (a).* Photos are the most visible and the most legally fiddly part.
**Entscheidung:** (b) Bundestag portrait photos. Their reuse licence is checked before any photo is published; if it does not allow reuse, this decision is reopened. (2026-09-27)

**D6 — Comparisons on the card.**
(a) None, absolute sentences only. (b) Percentile within the own fraction. (c) Percentile across the Bundestag.
*Recommendation: (a) on the card, (b) in the detail layer.* Layer 1 should not invite ranking.
**Entscheidung:** (a) no comparisons on the card, (b) percentiles within the own fraction in the detail layer. (2026-09-27)

**D7 — Language.**
*Recommendation:* German UI (as in the landscape), English code and docs (as in all three repos).
**Entscheidung:** German UI, English code and docs. (2026-09-27)

**D8 — Postcode search.**
(a) Yes, with a new Bundeswahlleiterin source. (b) Constituency list and map only.
*Recommendation: (b) first, (a) later.* Constituency is exact; postcodes are ambiguous.
**Entscheidung:** (b) constituency list and map first, postcode search later. (2026-09-27)

**D9 — Who gets a card.**
(a) The 635 WP 21 MdBs, including those who left. (b) Also non-MdB speakers (ministers without mandate). (c) Also
former members of earlier Wahlperioden.
*Recommendation: (a).* A minister without mandate has no votes and no documents; a slim "Regierungsmitglied" card later.
**Entscheidung:** (a) + (b): the 635 WP 21 MdBs, including those who left, plus non-MdB speakers. On 2026-09-27 the store has 14 of them with 296 speeches (federal ministers and Staatsminister without mandate, Länder representatives). Their cards show office and speeches only: no votes, no documents, and no birth data, which the store does not have for them. (2026-09-27) *Built:* the final split is 639 member cards (including 4 Nachrücker found only in the vote lists) and 14 speaker cards; see `decisions.md`.

**D10 — Look.**
(a) Reuse the landscape's visual language: Inter, light theme, fraction colours, card and bar-chart components.
(b) Something new.
*Recommendation: (a).* The two apps link to each other; they should look related.
**Entscheidung:** (a) reuse the landscape's visual language. (2026-09-27)

**D11 — Birth date on the card.**
(a) Year of birth. (b) Full date and place. (c) Age only.
*Recommendation: (a).*
**Entscheidung:** (b) full birth date and place (in the store for all MdBs except 2 missing places). (2026-09-27)

---

## 10. Phases

| Phase | Content | Done when |
|---|---|---|
| 0 | Repository, this plan | pushed ✓ |
| 1 | Decide D1–D11 here | every decision has an Entscheidung line and an entry in `decisions.md` ✓ |
| 2 | Foundation extensions from D4, first two items | new tables/columns with provenance, tests on fixtures |
| 3 | MVP: build, card, Reden, Abstimmungen, Ausschüsse, index (built on branch `mvp`; spot-check done against abgeordnetenwatch, see `decisions.md`) | all 635 member pages and the non-MdB speaker pages build; spot-check 10 cards against bundestag.de |
| 4 | Drucksachen, Im Plenum, Laufbahn, Quellen, exports | built 2026-09-28 (Im Plenum on the foundation's `interjection` table) |
| 5 | Container, compose service in `/srv/apps/bundestag`, Pages publish, `update.sh` hook (live since 2026-09-28) | the daily timer rebuilds and publishes the cards |
| 6 | Topics (D3 b), photos, similar members, network | — |
| 7 | Round 2: Plenum seating chart as the index entry (with last-sitting speakers and the Regierungsbank), Wahlkreis map; vote and sitting pages, photos and government cards follow in their own branches | Plenum and map built 2026-09-28 |

---

## 11. Entity model (restructure, 2026-09-30)

The site grew page by page, so the same fact can be reached several ways, some worse than others: a place typed
into the index filter, picked in the Wahlkreise view or found through the Gemeinde search gives three different
member lists; a vote is a page of its own and a list item on a bill page; a speech is drawn by `card.js`, by
`pages.speech_row` and by the bill page, each differently. From here on the site is organised around the
real-world entities parliament consists of, under two rules:

- **one entity, one canonical URL** (every other way in is an entry point or a redirect to it), and
- **one kind of fact, one rendering component** (`facts.py`), parameterised by the entity that filters it.

Every entity page is the same template: a header, then the same facets in the same order, each filtered by the
entity: *Mitglieder* (people with dates; for groups and places), *Reden*, *Abstimmungen und Beschlüsse*,
*Drucksachen*, and for places an empty *Erwähnungen* slot. A facet that does not apply to an entity says why
instead of disappearing (the Bundesregierung does not vote as a group; a committee holds no speeches).

### 11.1 Entities

| Entity | What it is | Source | Canonical page |
|---|---|---|---|
| **Person** | an MdB of WP 21, a minister or Staatssekretär, a speaker without a mandate (D9) | `person`, `mandate`, `government_role`, `speech` | `<person id>.html` |
| **Group** | a Fraktion (`membership` kind fraction), the Bundesregierung (`government_role`), an Ausschuss or other Gremium (`membership` kind committee/other) | Stammdaten, Wikidata | `fraktionen/<token>.html`, `gremien/bundesregierung.html`, `gremien/<slug>.html` |
| **Procedure** | a DIP Vorgang that reaches the plenum: every Gesetzgebung, and every other Vorgang (Antrag, Beschlussempfehlung, Entschließungsantrag, …) with a debate or a decision in the store | `vorgang`, `vorgang_drucksache`, `vorgang_position`, `agenda_item_vorlage`, `decision`, `decision_fraction`, `roll_call_vote`, `individual_vote` | `vorgaenge/<vorgang id>.html` |
| **Place** | Bund ⊃ Land ⊃ Wahlkreis (the 299 Wahlkreise of the 2025 election) | `constituency`, `constituency_result`, `election_candidacy`, `mandate` | `orte/index.html`, `orte/<land slug>.html`, `orte/wahlkreis-<nr>.html` |
| **Time** | Wahlperiode ⊃ Sitzungswoche ⊃ Sitzung ⊃ Tagesordnungspunkt (⊃ Unterpunkt) | `sitting`, `agenda_item`, `agenda_sub_item` | `sitzungen/index.html`, `woche/<YYYY-Www>.html`, `sitzungen/<wp>-<n>.html`, `…#top-<pos>`, `…#top-<pos>-<label>` |
| **Topic** | a period theme of the Themenlandschaft | `speech_themes.json` (`LANDSCAPE_THEMES`) | `themen/<theme id>.html` (not permanent, see 11.6) |

Atomic facts, each with one component in `facts.py`:

| Fact | Component | Filters it is used with |
|---|---|---|
| Speech (Rede, kurzer Beitrag, Zwischenfrage, Befragung, Fragestunde) | `facts.speech` / `facts.speech_list` | person (card), group, place, procedure (debates), sitting (agenda items), topic |
| Vote (how it was voted: roll call or show of hands) | `facts.vote` | procedure (timeline point), sitting, person (own vote on the card), group (fraction line), place (the place's members) |
| Decision (what was decided, with result) | `facts.decision` (embeds `facts.vote`) | procedure, sitting, week, group, person |
| Drucksache | `facts.drucksache` / `facts.drucksache_list` | person (authored, reported), group (Fraktion or Bundesregierung as Urheber, committee Beschlussempfehlungen), procedure, sitting (Vorlagen), place |

A speech component shows a short excerpt and links the full text on `reden/<id>.html`, which stays the canonical
full-text view (it covers every speech; the landscape only the ones on its map). A speech on the landscape's map
also links `<YYYY-Www>.html#rede=<speech id>` for its topic context.

**Agenda item ≠ Vorgang ≠ vote.** An agenda item can carry several Vorlagen of several Vorgänge; a block item has
sub-items, each with its own Vorlagen, decisions and (with `speech.sub_item_id`) speeches; a Vorgang is debated
under several agenda items in several sittings; a decision may concern a Drucksache that belongs to no Vorgang or to
several. The pages link these many-to-many: an agenda item lists its Vorlagen with a link to each Vorgang, a Vorgang
lists every agenda item (or sub-item anchor) that named one of its Drucksachen, and a decision is a point on a
Vorgang's timeline only when it belongs to exactly one Vorgang.

### 11.2 URL scheme

| Entity | URL | Status |
|---|---|---|
| Person | `<person id>.html`, `<person id>.json`, `fotos/<person id>.jpg`; tabs as `#reden`, `#abstimmungen`, … | unchanged |
| Fraktion | `fraktionen/<token>.html` (`cdu`, `spd`, `afd`, `gru`, `lin`, `frl`) | unchanged, extended |
| Ausschuss, Gremium | `gremien/<slug>.html`; index `gremien/index.html` | unchanged, extended |
| Bundesregierung | `gremien/bundesregierung.html` | new |
| Vorgang | `vorgaenge/<vorgang id>.html`; index `vorgaenge/index.html` (glossary `#status-<slug>`, `#glossar`) | new, replaces `gesetze/` |
| Decision on a Vorgang | `vorgaenge/<vorgang id>.html#abst-<page id>` | new |
| Decision without exactly one Vorgang | `abstimmungen/<page id>.html` | unchanged |
| Abstimmungen overview, Geschlossenheit | `abstimmungen/index.html`, `abstimmungen/geschlossenheit.html` | unchanged |
| Bund | `orte/index.html` | new |
| Land | `orte/<land slug>.html` (`bayern`, `baden-wuerttemberg`, …) | new |
| Wahlkreis | `orte/wahlkreis-<nr>.html` (numbers of the 2025 Wahlkreiseinteilung) | new |
| Gemeinde lookup (entry point) | `wahlkreise/suche.html` | unchanged URL, now leads to place pages |
| Wahlperiode | `sitzungen/index.html` | unchanged, is the period level |
| Sitzungswoche | `woche/<YYYY-Www>.html`, `woche/feed.xml` (entry ids unchanged) | unchanged |
| Sitzung | `sitzungen/<wp>-<n>.html` | unchanged |
| Tagesordnungspunkt, Unterpunkt | `sitzungen/<wp>-<n>.html#top-<pos>`, `#top-<pos>-<label>` | unchanged |
| Speech | `reden/<page id>.html`, parts as `#<part id>` | unchanged |
| Topic | `themen/index.html`, `themen/<theme id>.html` | new, only with `LANDSCAPE_THEMES`, not permanent |
| Sachgebiet (DIP) | `sachgebiete/<slug>.html` (lowercase ASCII, ä→ae, other characters → `-`); index `sachgebiete/index.html` | new |
| EU-Vorlagen | `vorgaenge/eu-vorlagen.html` | new |
| Search | `suche.html?q=…` (entity index `suche.json`, speeches in `pagefind/`) | unchanged URL |

### 11.3 Redirect table

GitHub Pages is static, so a moved page leaves a stub at the old path (`redirects.py`): a meta refresh, a
canonical link, a visible link, and a `location.replace` that carries `location.hash` over and maps old fragments
to the new target. The live `out/` folder is never emptied, so every old page that is not rebuilt as a page must be
rebuilt as a stub, or it would keep serving stale content.

| Old URL | New URL | Fragments | How |
|---|---|---|---|
| `gesetze/<id>.html` | `vorgaenge/<id>.html` | kept | stub for every Gesetzgebung Vorgang |
| `gesetze/index.html`, `#status-<slug>`, `#glossar` | `vorgaenge/index.html`, same fragment | kept | stub |
| `abstimmungen/<page id>.html`, decision of exactly one Vorgang | `vorgaenge/<vorgang id>.html#abst-<page id>` | any old fragment → `#abst-<page id>` (vote pages had no anchors) | stub |
| `abstimmungen/<page id>.html`, no or several Vorgänge | unchanged | – | page |
| `woche/index.html` | `sitzungen/index.html` | kept | stub |
| `sitzungen/<wp>-<n>.html#top-<pos>`, `#top-<pos>-<label>` (the landscape) | unchanged | ids unchanged | page |
| `<person id>.html`, `.json`, `fotos/<id>.jpg`, `#<tab>` | unchanged | – | page |
| `reden/<id>.html`, `#<part id>` | unchanged | – | page |
| `woche/<week>.html`, `woche/feed.xml` | unchanged; feed entry ids stay `…/woche/<week>.html` | – | page |
| `fraktionen/…`, `gremien/…` | unchanged | – | page |
| `wahlkreise/suche.html` | `orte/index.html#suche` (moved 2026-10-01, 12.6) | query `?q=` kept | stub |
| `suche.html?q=…` | unchanged: `q` fills the entity search and the Reden section | – | page |
| `index.html#ansicht=…&q=…&state=…&wk=<nr>…` | `ansicht=wahlkreise` goes to the place pages, other states stay (12.6) | view state | page script |
| `kompass.html`, `abstimmungen/geschlossenheit.html` | unchanged; links to votes go to the canonical target directly | – | page |

`tests/test_e2e.py` builds the fixture store and checks that every row of this table resolves in the output, stubs
included, with `scripts/check_links.py --anchors` over the whole site.

### 11.4 Places

- **Direct mandates by Wahlkreis**: the winner of `election_candidacy` (`elected_via = constituency`); without the
  election tables, the Stammdaten mandate of type Direktwahl.
- **List mandates by Land**: `election_candidacy.list_state`, else the Stammdaten `mandate.state` (Nachrücker have
  no row in the Bundeswahlleiterin's file). Every list member is listed on the Land page and on *every* Wahlkreis
  page of that Land, marked "Landesliste"; the one who stood in that Wahlkreis is marked "hat hier kandidiert".
  A member whose Land is unknown (a Nachrücker only in the vote lists) is listed on the Bund page, so nobody drops
  out of the regional views.
- **Moved up or left, with dates**: from the WP 21 mandate's `from_date` (after the constituent sitting) and
  `to_date`, as the Karrieren page.
- **A Wahlkreis without a direct member says why**: no Zweitstimmendeckung (with the strongest party's first-vote
  share), or the direct member left and the seat passed to the Land list.
- The map, the list of Wahlkreise and the place search live on the place hub `orte/index.html` (12.2); the
  Abgeordnete page filters by a place with the same membership and links the place page.
- Mentions of places in speeches: an empty facet slot (11.8).

### 11.5 Time

One hierarchy with breadcrumbs up and links down: `sitzungen/index.html` (Wahlperiode) → `woche/<week>.html` →
`sitzungen/<wp>-<n>.html` → `#top-<pos>` → `#top-<pos>-<label>`. The week page is the week entity; it links the
landscape's week page (`<YYYY-Www>.html`) for the topic map and no longer lists the week's clusters itself. A sitting
page is the zoom level below the week, not a concept of its own; agenda items stay anchors on it.

### 11.6 Topics

The landscape's period theme is the topic entity, read from `speech_themes.json` (`LANDSCAPE_THEMES`). Week clusters
are not entities: their ids change with every rebuild of a week. **The period theme's id is not stable either**
(checked in `bundestag-topic-landscape/src/landscape/period.py`: `model()` numbers themes by size, and the model is
recomputed whenever the set of speeches changes, i.e. after every new sitting week). So `themen/<theme id>.html`
is built only when `LANDSCAPE_THEMES` is set, says on the page that its address may change, and nothing links to it
from outside the site. **Landscape requirement:** stable theme ids across rebuilds (e.g. match each new theme to the
previous model's theme with the largest speech overlap and keep its id, new ids only for new themes), with a
retired-id list so the cards site can write stubs.

### 11.7 Search

`suche.html` resolves entities first, client-side, from `suche.json` (written by the build): persons, groups,
places (Länder, Wahlkreise, Gemeinden → their Wahlkreis), Vorgänge, topics and sitting weeks, grouped by type,
each linking its canonical page. Below the entities, one "Reden" section with Pagefind full-text hits in speeches,
with the filters Fraktion, Person, Monat and Thema. `suche.html?q=…` keeps working. Pagefind now indexes only the
speech pages; the other pages are found as entities.

### 11.8 Out of scope, designed only

**Place mentions in speeches.** Needs a gazetteer with disambiguation, built in the foundation (facts with
provenance): Gemeinden and Kreise from `constituency_municipality` (AGS, Kreis, Land), Länder, and the Wahlkreis
names. Candidates are capitalised tokens and n-grams matching a gazetteer name, skipping sentence starts. Ambiguity
is the normal case: 30+ "Neustadt", "Halle (Saale)" vs. "Halle (Westf.)", and names that are ordinary words
("Essen", "Weil", "Bühl"). A mention counts only when (a) the name is unique in the gazetteer and not a dictionary
word, or (b) a qualifier in the same sentence resolves it ("in Halle an der Saale", "Neustadt an der Weinstraße",
the Kreis or Land named nearby), or (c) it follows a locative preposition ("in", "aus", "nach") and the speaker's
own Wahlkreis or Land contains exactly one candidate. Everything else stays unresolved and is not shown. Foundation
table `place_mention(speech_id, paragraph, ags, surface, method, confidence, …)`; the cards site fills the empty
*Erwähnungen* facet on place pages from it, with each mention linking the paragraph on the speech page.

*Extended 2026-10-01 (the owner's design): an ambiguity registry and a small local decider.* Implemented later in the
foundation, against the real speeches; nothing here is built. The project uses local models only, no external API.

1. **Candidates** as above: gazetteer names (Gemeinden and Kreise from `constituency_municipality` with AGS, Kreis
   and Land; the 16 Länder; Wahlkreis names), matched as capitalised tokens and n-grams.
2. **Unambiguous names resolve by the gazetteer alone**: a name with exactly one AGS that is not in the registry
   becomes a mention with `method = 'gazetteer'`, `confidence = 1.0`, no model involved.
3. **Registry of ambiguous names**, a reviewed file kept like today's denylist (`data/place_registry.tsv` in the
   foundation, one name per line with a short reason): names with several AGS ("Neustadt" 30+, "Halle", "Mühlheim"),
   names that are ordinary words or surnames ("Essen", "Weil", "Bühl", "Hof", "Lohr", "Kirchheim" as a name), and
   names shared with a Land or a region ("Hessen" the Land vs. the Gemeinde). A hit on the registry never resolves by
   rule; it goes to the decider.
4. **Decider**: a very small local model gets about two sentences around the hit (the sentence with the name and the
   one before it; the speaker's name, fraction and Wahlkreis/Land as metadata) and the candidate list. It answers in a
   fixed JSON shape: is this a place at all, and if so which candidate (by AGS), with a confidence.
   - *Candidate models* that run on 12 CPU cores without a GPU, quantised (GGUF, llama.cpp or Ollama): Qwen2.5 1.5B
     and 3B Instruct, Llama 3.2 3B Instruct, Phi-3.5-mini (3.8B), Gemma 2 2B; as a non-generative baseline a German
     NER model (e.g. a GermEval-trained BERT via spaCy/flair) for "is this a place" plus the rules of the base design
     for "which one". Expected cost: a 1.5–3B model at Q4 answers a two-sentence prompt in roughly 0.3–1.5 s on 12
     cores; with a few tens of thousands of registry hits across WP 21 that is a one-off run of hours, then only new
     protocols each day. Pick the smallest model that meets the accuracy bar below.
   - *Prompt shape* (German context, JSON out, temperature 0, grammar-constrained output where the runtime offers it):

     ```
     System: Du ordnest Ortsnamen in Bundestagsreden zu. Antworte nur mit JSON.
     User: Redner: <Name> (<Fraktion>), Wahlkreis <Nr> <Name>, <Land>.
     Text: "<Satz davor> <Satz mit dem Namen>"
     Wort: "<Halle>"
     Kandidaten: [{"ags": "15002000", "name": "Halle (Saale), Stadt", "kreis": "Halle (Saale)", "land": "ST"},
                  {"ags": "05754012", "name": "Halle (Westf.), Stadt", "kreis": "Gütersloh", "land": "NW"}]
     Frage: Ist das Wort hier ein Ort? Wenn ja, welcher Kandidat?
     Antwortformat: {"ort": true|false, "ags": "<ags>"|null, "sicherheit": 0.0-1.0}
     ```
5. **Confident answers become mentions** with provenance: `method = 'model'`, the model name and version, the prompt
   version, the confidence. **Uncertain answers are not hidden and not guessed**: below the threshold the row keeps
   `ags = NULL`, `status = 'uncertain'` and its `candidates`; the place page shows it in the Erwähnungen facet of every
   candidate place as "unsicher", with a dropdown of the candidates (each linking its place page) and the paragraph.
   "Not a place" answers are kept with `status = 'rejected'` for the evaluation, never shown.
6. **Measured before anything is published**: a hand-labelled sample of registry hits, stratified by name (every
   registry name, at least 20 hits each where they exist, plus 300 random hits), each labelled by hand with
   place/not a place and the AGS, double-labelled on a subset to know the agreement. The decider runs on the sample;
   report precision and recall of "is a place", accuracy of the AGS, and the calibration of the confidence
   (accuracy per confidence bucket). The publication threshold is the lowest confidence at which the sample's
   precision is at least 0.95; below it a hit is "unsicher". The sample, its labels and the report live in the
   foundation and are rerun when the model or the prompt changes.
7. **Table shape** (foundation):
   `place_mention(id, speech_id, paragraph, start, end, surface, ags NULL, status ('resolved' | 'uncertain' |
   'rejected'), method ('gazetteer' | 'qualifier' | 'locative' | 'model'), model NULL, prompt_version NULL,
   confidence REAL, candidates TEXT (JSON [{ags, name, kreis, land, p}]), source_url, source_document_id,
   retrieved_at)`, indexed by `ags` and `speech_id`.
8. **On the cards site**: the place pages already have the empty *Erwähnungen* facet (`places.py`, explained as
   "noch nicht erfasst"). With the table it lists, per place (a Wahlkreis aggregates its Gemeinden' AGS, a Land its
   own), the resolved mentions (newest first, D23) linking the paragraph on the speech page, then the uncertain ones
   marked "unsicher" with their candidates; `data.has_table('place_mention')` keeps older stores working.

**Cross-period search ("what did member X say about Y").** Needs earlier Wahlperioden in the foundation
(protocols from WP 1 are on bundestag.de), person ids across periods (the Stammdaten have them), and topics that
span periods, which the landscape's per-period model does not give. Design: the search resolves X to a person
entity and Y to a topic entity or free text, then runs Pagefind with the filters `Person` and `Thema` (or the text)
and a new `Wahlperiode` filter; results grouped by Wahlperiode. Requires stable topic ids (11.6) and one Pagefind
index per period, merged with Pagefind's multisite search.

**Postcode search.** Postponed (D8). Needs PLZ → Gemeinde (AGS) from OpenPLZ in the foundation as
`postcode_municipality(plz, ags, …)`; a PLZ can span several Gemeinden and a Gemeinde several Wahlkreise, so the
answer is a short list of Wahlkreise, each linking its place page, never a single guess.

**Foundation and landscape changes** are made there, not here. Requirements found while building this:

- Landscape: stable period theme ids (11.6).
- Foundation: the decision parser misses "Linksfraktion" (e.g. 21/47/h2 has no position for Die Linke); the pages
  show what the store has and do not patch it.
- Foundation: a normalised Urheber → Fraktion field on `drucksache` (today the cards match DIP's `originators`
  titles such as "Fraktion der SPD" by name, `data.originator_group`).
- Foundation: the Land of a Nachrücker's list (the Bundeswahlleiterin's file has no row for them; the Stammdaten
  `mandate.state` is used, and is missing for Nachrücker not yet in the Stammdaten).

## 12. Navigation, entity-owned views, the calendar, Fragen, missing protocols (2026-10-01)

The entity model of section 11 had the right pages but the wrong ways in: the top bar had 11 items, Orte was a plain
list, and the map of the Wahlkreise sat on the Abgeordnete page, so a place was shown by a second view of members
instead of by its own page. This round makes the navigation follow the entities.

### 12.1 The top bar

`[Suche] · Orte · Gremien · **Abgeordnete** · Vorgänge · Sitzungen · Fragen · Debattenkultur · Daten` (D26).

- **Suche** is a search field at the left end, not a link. Enter, or a suggestion, goes to `suche.html?q=…`.
  Suggestions come from `suche-kurz.json` (the entity index without the Gemeinden, labels cut to 110 characters),
  fetched on the first keystroke, grouped by type and ranked by `search.js`'s `resolve()`, so the bar and the search
  page agree (`nav.js`).
- **Abgeordnete** is the landing page and the home item: alone in the centre column of a three-column grid, so it
  stays centred whatever the sides hold; emphasised as a bordered pill.
- **Debattenkultur** stays, second to last, set quieter (lighter weight and colour): a statistics page, not a
  research tool. **Daten** is the last item, at the right end.
- **Themenlandschaft** leaves the bar. Its links stay where they are in context (week, sitting, speech pages, the
  plenum's speaker toggle) and it is in the footer of every page.
- Below 1080 px the bar is one row that scrolls sideways (as before, D "nav-fix"); the search icon and Abgeordnete
  come first and are pinned (`position: sticky`), so both are reachable without scrolling. The icon opens the field
  over the bar.
- **Abstimmungen** is no longer a top item: it is a sub-tab of Sitzungen (`Sitzungswochen | Abstimmungen`), with
  Geschlossenheit and `kompass.html` under it; `abstimmungen/index.html` keeps its URL (D27).

### 12.2 An entity's page owns its views (the general pattern)

**Rule (D25):** every view *of* an entity lives on that entity's page. Another page may *filter by* an entity, but
then it uses the same membership function the entity's page uses (computed once, in Python, and shipped in the
payload; never recomputed in JavaScript) and links to the entity's page.

Places are the first case:

- **`orte/index.html` is the place hub**: the map of the 299 Wahlkreise (`wkmap.js`, moved from the index, with its
  legend; the colours computed in `places.seat_fraction`), the Länder with their Wahlkreise, and a place search
  matching Land, Wahlkreis name or number, and Gemeinde (the former Gemeinde lookup), over one place index,
  `orte/orte.json` (`places.place_index`, searched by `places.js` `search`). Every result, map click and list row
  leads to the canonical place page. A mouse click on the map opens the Wahlkreis; on a touch screen the first tap
  selects it and shows the link, a second tap opens it. `#wk=<nr>` and `#land=<code>` select or zoom on the map (the
  place pages' "Auf der Karte"), `?q=` fills the search.
- **Membership** is `places.people(rep, key)`: for a Land the direct members of its Wahlkreise, then its list members;
  for a Wahlkreis its direct members (the one who left included), then the list members of its Land. The place pages
  list exactly this; `places.membership` gives the ids; `places.compact` ships them in the index payload without
  repeating a Land's list on each Wahlkreis (a reference `@<Land>:liste` that `places.js` `expand` resolves).
- **The Abgeordnete page filters by a place** (Land or Wahlkreis, picked from the same place index): plenum and list
  show exactly the place page's members (former members appear in the list, as on the place page, and are counted
  apart in the plenum, having no seat). With a place picked the page shows "Zur Seite von <Ort>". A Land or Wahlkreis
  typed into the name filter offers the place filter instead of matching text. Each place page has "Im Plenum
  zeigen" (`index.html#ort=<key>`). The Kompass's Wahlkreis lookup uses the same membership.
- The Wahlkreise view and the Land menu leave the Abgeordnete page; old states redirect (12.6).

Not yet moved to the pattern, for a later round: the index's committee filter and fraction chips filter by the cards'
current memberships, the same `membership` rows the Gremium and Fraktion pages read, but through no shared
function, and they do not link the Gremium's page when one is picked. The next step is a `bodies.members(key)` used
by both, shipped like `places.compact`, and a "Zur Seite von <Gremium>" link.

### 12.3 The Abgeordnete page

Opens on the plenum; the list is a secondary toggle ("Als Liste"). Below the plenum the **Rollen** section
(`#rollen`, `careers.py`, D28): Präsidium (members of the Gremium "Präsidium"), Fraktionsvorsitz (current fraction role
"Vorsitzende/r"), the chairs of the Ausschüsse and Gremien, the members in the government today, how long the members
have served (per fraction), Nachrücker and Ausgeschiedene, fraction switches. Every role links the entity that owns it
(Gremium, Fraktion, Bundesregierung). Dropped from the old Karrieren page: the full list of government offices with
dates (the Bundesregierung page owns it, with sources). `karrieren/index.html` is a stub to `#rollen`.

### 12.4 Sitzungen as a calendar, Abstimmungen inside

`sitzungen/index.html` (the Wahlperiode) is a calendar (D29) in the landscape's visual language (D10): per year a strip
of twelve months with the ISO weeks, sitting weeks linked; then a card per sitting week (landscape-style grid) with its
sittings. Toggles, per week (CSS `:has`, no script needed) or for all weeks, reveal each sitting's **Abstimmungen**
(`facts.decision`: result badge, roll call or show of hands, linking the canonical target) and the **Vorgänge that
moved forward** that day (`weekly.moves`: debated under an agenda item, decided, or a DIP step in the Bundestag),
each linked to its page. Clicking goes to `woche/<week>.html` and `sitzungen/<wp>-<n>.html` as before. A week card
keeps `id="<YYYY-Www>"`, so a deeper link from the landscape (`sitzungen/index.html#2026-W28`) can land on it later.

Vorgänge stay a top-level entity (they span weeks). A vote is shown under its sitting and on the timeline of the
Vorgang it belongs to, both by `facts.vote`/`facts.decision`; there is no third renderer. The week page gets a
*Vorgänge* facet beside *Abstimmungen und Beschlüsse*. The Abstimmungen tab and every Vorgang page explain the
relation in one paragraph with counts from the store (`facts.relation_note`): a Vorgang often has several votes; a
vote of exactly one Vorgang is a point on its timeline (D15); the rest keep their own page.

### 12.5 Fragen as a research tool

`regierung/index.html` keeps its statistics on top and adds the list of every single question below (`#liste`, D30):
Kleine Anfragen, Schriftliche Fragen, Mündliche Fragen, Fragestunde turns, Regierungsbefragung turns. One JSON per
kind (`regierung/<kind>.json`, `questions.research`), loaded only when its tab is opened, with per-file tables of
persons, ministries, statuses and Drucksachen that rows refer to by index. Filters: words in the title, Fraktion,
member, ministry (or the answering role), month, status, and for Kleine Anfragen the answer time. Rows link the
Drucksache in DIP and as PDF, the Vorgang in DIP, the asker's card, the answer, and for oral questions the Fragestunde
item and the protocol, for turns the speech page.

Size on the live data's shape (2,740 Kleine Anfragen with ~15 signers, 9,038 Schriftliche Fragen, 3,047 Befragung
turns; `tests/test_questions.py`): Schriftliche Fragen about 1.3 MB as written, the largest file; GitHub Pages serves
JSON gzip-compressed, a fraction of that. To check on the real build.

**Foundation requirements found here:**
- *Full text of Kleine Anfragen and Schriftliche Fragen*: the store has titles only; the question text is in the
  Drucksache PDF (and DIP's `drucksache-text`). Needed: the text per question, for Schriftliche Fragen split out of
  the Sammeldrucksache.
- *The asker per question*: DIP names the askers of Schriftliche and Mündliche Fragen per Sammeldrucksache
  (`drucksache_author`, activity "Frage"); the Aktivität records carry a `vorgangsbezug` to the single question, which
  the foundation drops. Needed: `drucksache_author.vorgang_id` (or a table `question_asker`). Until then a question
  names its asker only when its Sammeldrucksache names exactly one, and the page says so. Meanwhile each row names who answered: the
  answerers of the question's ministry in its Sammeldrucksache (DIP's "Antwort" activity names the ministry) or in
  the Fragestunde (the speaker role names it), linked to their cards and to the speech with the answer (D30).
- *The Ressort of a Frage*: on the live store (2026-10-01) the DIP steps of Schriftliche and Mündliche Fragen carry no
  `ressort` (Kleine Anfragen do: 2,635 of 2,747), so the answerer match above finds nothing yet. Needed:
  `vorgang_position.ressort` for the Fragen, or the ministry from the Sammeldrucksache.

### 12.6 Vorgänge whose debate is missing from the protocols

Diagnosed on the server: the Bundestag still served the preliminary XML for 17 of 97 protocols ("Der gesamte und
damit endgültige Stenografische Bericht … wird am … veröffentlicht"); 8 of them (21/14, 21/31, 21/37, 21/59, 21/80,
21/83, 21/89, 21/96) lack their last 33–82 pages, about 441 pages, the late-evening debates. Example: the
SGB VI-Anpassungsgesetz (`vorgaenge/325338.html`), 1st Beratung 21/31 pp. 3392–3396, 2nd/3rd 21/37 pp. 4220–4228 with
four decisions.

In this repo (D31): a BT step of `vorgang_position` in a Plenarprotokoll with pages, in whose sitting no agenda item
names one of the Vorgang's Drucksachen, shows the step with the protocol and pages linked to the protocol PDF (DIP's
link, else `https://dserver.bundestag.de/btp/<wp>/<wp><nnn>.pdf`), DIP's decisions for it (`beschlusstenor`,
Drucksache, page) marked "Beschlüsse laut DIP" and kept apart from the votes parsed from the protocol, and the note
that the protocol text of this debate is not in the data. `daten.html` lists these steps by sitting under "Bekannte
Lücken", derived from the store (`procedures.missing_debates`), not a constant. The rule can also catch a debate whose
agenda item names a different Drucksache; the note says what is known (no agenda item names one) rather than the
cause. Only steps whose position is a Beratung count (not a Mitteilung, a change of committee or a
Geschäftsordnungsantrag). On the live store (2026-10-01) that gives 262 Beratungen in 44 sittings, more than the 8
truncated protocols: e.g. sitting 21/40 has no agenda item for the 2nd/3rd Beratung of the e-Akte and
Tierarzneimittel bills that DIP places there. To check in the foundation whether those protocols are preliminary
too, or whether the parser drops items.

**Foundation requirement:** detect the preliminary marker in a protocol; re-fetch it until the final version is
served; flag incomplete sittings in the store (e.g. `sitting.preliminary`, `sitting.final_fetched_at`); and fall back to
DIP's `plenarprotokoll-text` or the PDF for the missing pages until the final XML is out.

### 12.7 Redirect table, extended

Rows added to 11.3 by this round; every one is followed by `tests/test_e2e.py` (stubs through their fragment rules,
view states through `places.js` `legacyTarget` in Node):

| Old URL | New URL | Fragments | How |
|---|---|---|---|
| `karrieren/index.html` | `index.html#rollen` | any → `#rollen` (the page had no anchors) | stub |
| `wahlkreise/suche.html` | `orte/index.html#suche` | `?q=` kept, fills the place search | stub |
| `index.html#ansicht=wahlkreise` | `orte/index.html` | – | the index's script (`location.replace`) |
| `index.html#ansicht=wahlkreise&…wk=<nr>` | `orte/wahlkreis-<nr>.html` | – | the index's script |
| `index.html#ansicht=wahlkreise&state=<Land>` | `orte/<land slug>.html` | – | the index's script |
| `index.html#…state=<Land>` (other views) | `index.html#ort=<Land>` (the place filter) | – | the index's script |
| `index.html#ansicht=personen` | unchanged: the list toggle | – | page |
| `abstimmungen/index.html`, `abstimmungen/geschlossenheit.html`, `kompass.html` | unchanged, now under Sitzungen | – | page |
| `sitzungen/index.html#<YYYY-Www>` | unchanged: the week's card in the calendar | ids unchanged | page |

URLs the Themenlandschaft links to are unchanged: `<person id>.html`, `fotos/<person id>.jpg`,
`sitzungen/<wp>-<n>.html#top-<pos>` and `#top-<pos>-<label>`, `abstimmungen/<page id>.html` (stub or page).

