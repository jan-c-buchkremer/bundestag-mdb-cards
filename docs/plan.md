# Plan: an info card for every MdB

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
