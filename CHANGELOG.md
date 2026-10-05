# Changelog

One entry per release (`docs/release.md`). Each starts with one sentence: what can a reader do now that they could
not before? If that sentence is hard to write, the release is not a finished vertical slice yet.

## Unreleased

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
