# bundestag-mdb-cards

One info card per member of the 21st Bundestag: who they are, what they do in the plenary, how they vote,
what they put their name to — every fact with a link to its source document.

**Status: MVP in progress.** The card with the tabs Reden, Abstimmungen, Ausschüsse & Funktionen and Quellen, and
the index with a Wahlkreis view, build from the store. The plan is in [`docs/plan.md`](docs/plan.md); the decisions
are logged in [`docs/decisions.md`](docs/decisions.md).

## Build

```sh
uv sync
BDF_DB=/path/to/bundestag.sqlite uv run cards build   # writes data/out/: one page and JSON per card, index.html
python3 -m http.server -d data/out                     # then open http://localhost:8000
uv run pytest && uv run ruff check .
```

Without `BDF_DB` the store is looked for at `../bundestag-data-foundation/data/bundestag.sqlite`.

`LANDSCAPE_CLUSTERS` points to the Themenlandschaft's `speech_clusters.json` (`{"<speech id>": {"week", "cluster_id",
"label"}}`, written by the landscape build); with it each agenda item on the sitting pages gets a "Worum ging es" block
with its speeches' topic clusters. Without it the block is left out.

The index opens on **Plenum**, a seating chart of the house (`parliament.js`, shared with the vote pages) that the
search and chips filter, with a toggle for everyone who spoke in the latest sitting and a link to that week in the
Themenlandschaft. **Abgeordnete** is the searchable list, **Wahlkreise** the list of all 299 Wahlkreise next to a map.
Cards show portraits (downscaled into `fotos/` from the foundation's raw folder: `BDF_RAW`, else `raw/` next to the store) and, for members of the government, their offices. The Regierungsbank, the "Regierung" badge and filter appear once the store has the foundation's `government_role`
table.

The map outlines in `src/cards/wahlkreise.json` are made once, not in the daily build:

```sh
uv run python scripts/wahlkreise_geo.py    # downloads the Bundeswahlleiterin shapefile, simplifies, writes the JSON
```

Built on [bundestag-data-foundation](https://github.com/jan-c-buchkremer/bundestag-data-foundation), whose SQLite
store is read, never written. Sibling of
[bundestag-topic-landscape](https://github.com/jan-c-buchkremer/bundestag-topic-landscape), the topic map of one
sitting week.

Code is MIT. Data attribution follows the foundation: "Deutscher Bundestag", "Deutscher Bundestag/Bundesrat – DIP",
abgeordnetenwatch.de (CC0 1.0).
The Wahlkreis map: © Die Bundeswahlleiterin, Statistisches Bundesamt, Wiesbaden 2024, Wahlkreiskarte für die Wahl
zum 21. Deutschen Bundestag; Grundlage der Geoinformationen © GeoBasis-DE / BKG 2024; Datenlizenz Deutschland –
Namensnennung – Version 2.0 (dl-de/by-2-0), simplified.
