# Architecture: three layers behind plenar-radar.de

plenar-radar.de is one site built by three repos with separate concerns. Each layer has one question it answers.
Status: agreed 2026-10-04; the migration (below) is in progress.

| Layer | Repo | Question | Was |
|---|---|---|---|
| Foundation | bundestag-data-foundation | What happened? | (unchanged) |
| Research | bundestag-research-platform | Where can I find it, and how does it connect? | bundestag-mdb-cards |
| Radar | bundestag-radar | What's going on, and what does it mean? | bundestag-topic-landscape |

## Foundation

Ingests the official sources (Bundestag, DIP, abgeordnetenwatch.de, Wikidata, Bundeswahlleiterin), normalizes them, assigns
stable ids and links the entities: which speech belongs to which agenda item, which Drucksache to which Vorgang, which
person to which mandate. Validates against official totals.

Owns the truth of every fact and every link between facts, the canonical definitions (what counts as a speech, a
fraction line, a mover-up), and the official classifications that come with the sources, such as DIP Sachgebiete.

A definition can be a convention people might choose differently; it belongs here as long as it is documented and
applied the same way to every case. Research and Radar use it, they do not redefine it.

Does not present, select, rank or summarize, and runs no models.

## Research

Makes the Foundation explorable: one page per entity (members, places, committees, Vorgänge, sittings, speeches,
votes), navigation between them, filters, full-text search, a source link on every fact, JSON exports, and the counts
and aggregates that are plain queries (per fraction or per entity: counts, sums, medians).

Owns how facts are displayed, linked and navigated, and **the site shell**: the design tokens and styles, the header
and navigation, the footer, Impressum and Datenschutz, the search. Radar takes all of these from Research.

Research is the hard-facts room: what it states can be checked against a source. It is not built to be neutral in
an abstract sense, but it does not decide what matters.

## Radar

Selects, weights and connects: topics and trends across debates, Vorgänge and government answers; what is moving
through the legislative pipeline; where the government and the coalition partners stand; which members work on what;
weekly overviews; the Kompass. Uses embeddings, topic models and summaries where they help.

Owns selection and weighting, topics and clusters and their labels, embeddings and all model output (choosing a
model is an interpretive decision), summaries and positions, and curated selections such as the Kompass questions.

Every Radar result links to its evidence in Research. Radar may be wrong, but never untraceably.

## Where something belongs

Hard facts and plain queries go below; results where interpretation is central go into Radar: labels a model
generated, clusters that change with every rebuild, a hand-picked selection, a summary. Definitions go into the
Foundation, even when they are a choice (see above).

## Dependencies

- The Foundation knows neither Research nor Radar.
- Radar reads the Foundation, links into Research and uses Research's site shell.
- Research never depends on Radar to build or to work. It **may show Radar results** (a topic chip on an agenda
  item, a link to the Kompass, similar speeches), on three conditions:
  1. they are marked as Radar by design (next section);
  2. they come from Radar's published output and are optional: without it the build succeeds and the block is
     simply not there;
  3. Research imports no Radar code.
- New data flows bottom-up but is requested top-down: the Foundation grows only when a Research page or a Radar
  question needs something it lacks, and that page or question is named.

## Telling Radar apart: the design rule

A reader always knows when they are looking at, or about to go to, interpretation.

- **One Radar colour.** Research keeps its accent (`--accent`, blue) for every link between Research pages. Radar has
  its own accent, `--radar` (proposal: violet `#7c3aed`, soft `#f1ebff`; it collides with no fraction, vote or
  government colour), defined in Research's tokens so both sides use the same value.
- **Radar inside Research:** every Radar result or link on a Research page is a Radar element: the Radar colour and
  the Radar mark (a small icon or label, e.g. "Radar"), never a plain blue link. Kompass, Themenlandschaft, topics
  and weekly overviews all look like one family.
- **Radar pages:** the same shell as Research, with the Radar colour as their accent and a header that says the
  reader is on the Radar. Links from a Radar page back into Research are blue again: the evidence.
- **Footer method note:** every Radar page says in its footer, in two or three sentences, how its results were made
  (e.g. "Themen: Reden als Embeddings (multilingual-e5-base), gruppiert mit UMAP und HDBSCAN, benannt nach
  typischen Wörtern") and what that can and cannot tell (e.g. "Themen zeigen Ähnlichkeit der Wortwahl, nicht
  Positionen; sie können sich mit neuen Sitzungswochen ändern").

## URLs

One domain, split by path; the two builds never write the same path and `release.sh` merges them.

- Radar: `/` (the front page, once Radar can carry it; until then Research's index stays there), `/themen/`,
  `/kompass/`, its weekly overviews and the Themenlandschaft.
- Research: the entity paths (`/abgeordnete/`, `/vorgaenge/`, `/sitzungen/`, `/abstimmungen/`, `/orte/`,
  `/gremien/`, `/regierung/`, …), search, `/daten/`, Impressum and Datenschutz.

Research's URL scheme (plan.md 11.2) is a contract: Radar links to it, so changing a URL is a breaking change and
needs a redirect. When a page moves from Research to Radar, Research leaves a redirect.

GitHub Pages copies are dropped; plenar-radar.de is the only site.

## Releases

Each repo releases on its own (`v0.MINOR.PATCH`, a CHANGELOG entry that starts with what a reader can do now;
`docs/release.md`). On top of that:

- The Foundation's schema contract (its `docs/design.md`, from v0.2.0) is what Research and Radar build on; a build
  checks the store's schema version first and stops on a mismatch instead of publishing a broken site.
- Research's URL scheme and site shell are what Radar builds on, versioned with Research's releases.
- `release.json` on the live site records each part's version, image digest and the data date, so what is live can
  always be traced to the code and data that built it.

## Migration

1. This document; README links to it in all three repos.
2. Rename, without changing behaviour: GitHub repos, ghcr images, project and package names, CLIs
   (`cards` → `research`, `landscape` → `radar`), `CARDS_URL` → `RESEARCH_URL`. What names a feature keeps its name:
   the MdB card stays a card, the Themenlandschaft stays `LANDSCAPE_*`. An infra PR for `compose.yml`, `update.sh`, `release.sh`, Gatus; drop the GitHub Pages publishing.
   Rides along with the next release of each repo.
3. The Radar design rule in Research: `--radar` token, the Radar element, existing landscape links and blocks
   converted to it.
4. Radar takes the shell from Research and gets its Radar header and footer method note.
5. Kompass, the topic pages and the week summaries move to Radar; Research keeps redirects and shows them as Radar
   links.
6. Definitions move down when a page needs them: the fraction line (`data.majority`, for the vote pages and
   Geschlossenheit) and the reading of Ordnungsmaßnahmen from the chair's text (`debate.py`, for Debattenkultur).
7. Release checks: schema version check at build start, `release.json` with versions and digests.
8. Radar takes `/` when it has a front page worth arriving at.
