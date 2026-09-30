# bundestag-mdb-cards

One info card per member of the 21st Bundestag: who they are, what they do in the plenary, how they vote,
what they put their name to — every fact with a link to its source document.

**Status: MVP in progress.** The site is organised around the entities parliament consists of, one canonical page
each (entity model, URL scheme and redirect table in [`docs/plan.md`](docs/plan.md) section 11); the decisions are
logged in [`docs/decisions.md`](docs/decisions.md).

## Pages

Every entity page is the same template: a header, then the same facets (Mitglieder, Reden, Abstimmungen und
Beschlüsse, Drucksachen), each filtered by the entity. Each kind of fact has one rendering component in
`src/cards/facts.py` (`speech`, `vote`, `decision`, `drucksache`), used by every page.

| Entity | Pages |
|---|---|
| Person | `<person id>.html` (the card, with its JSON export `<person id>.json` and portrait `fotos/<person id>.jpg`) |
| Group | `fraktionen/<token>.html`, `gremien/<slug>.html`, `gremien/bundesregierung.html`, index `gremien/index.html` |
| Procedure | `vorgaenge/<vorgang id>.html` for every Gesetzgebung and every Vorgang debated or decided in the plenum, with its timeline; index and Beratungsstand glossary `vorgaenge/index.html` |
| Place | `orte/index.html` (Bund), `orte/<land>.html`, `orte/wahlkreis-<nr>.html` |
| Time | `sitzungen/index.html` (Wahlperiode) → `woche/<YYYY-Www>.html` → `sitzungen/<wp>-<n>.html` → `#top-<pos>` (→ `#top-<pos>-<label>`) |
| Topic | `themen/<theme id>.html`, only with `LANDSCAPE_THEMES`; the address is not permanent |

A decision that belongs to exactly one Vorgang is a point on its timeline (`vorgaenge/<id>.html#abst-<page id>`); the
others keep `abstimmungen/<page id>.html`. Moved pages (`gesetze/…`, the vote pages of such decisions,
`woche/index.html`) are HTML stubs that redirect and keep the fragment. `suche.html` resolves persons, groups, places
(with the Gemeinden), Vorgänge, topics and sitting weeks from `suche.json`, and shows full-text hits in speeches below.
The index map, its Wahlkreise list and `wahlkreise/suche.html` lead to the place pages.

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
with its speeches' topic clusters. Without it the block is left out. `LANDSCAPE_THEMES` points to its
`speech_themes.json` (`{"<speech id>": {"theme_id", "label"}}`); with it the build writes the topic pages in `themen/`,
speech pages link their theme and the search's Thema filter uses it.

Every rede has its own page in `reden/<speech id>.html`: the full text as the protocol prints it, with Beifall, Zurufe
and the chair's words inline, the Zwischenfragen in their place, and links to the card, the agenda item on the sitting
page and the protocol PDF. `LANDSCAPE_NEIGHBOURS` points to a JSON `{"<speech id>": ["<speech id>", …]}` of similar
speeches (most similar first); with it each speech page lists up to five "Ähnliche Reden", without it the list is left
out. The last build step is the search: `suche.json`, the entity index, and [Pagefind](https://pagefind.app) (the
Python package brings its binary), which indexes the speech pages into `pagefind/`; `suche.html` is the search page.

```sh
uv run python scripts/check_links.py data/out --anchors   # every internal href/src in the built HTML resolves
```

`tests/test_e2e.py` does the same on the test fixture: it writes it to a SQLite file, runs `cards build` against it and
`check_links.py --anchors`, and follows every old URL of the redirect table.

**Debattenkultur** (`debatte/`) compares groups, never single members: words spoken per fraction against seats,
by gender, age and first term, the government apart; the chair's Ordnungsrufe and Rügen, Zwischenfragen and
interruptions; applause and Zurufe between fractions. `LANDSCAPE_THEMES` may point to a JSON
`{"<speech id>": {"theme_id", "label"}}`; with it the page adds words per theme and fraction, without it the table is
left out.

The index opens on **Plenum**, a seating chart of the house (`parliament.js`, shared with the vote points) that the
search and chips filter, with a toggle for everyone who spoke in the latest sitting and a link to that week in the
Themenlandschaft. **Abgeordnete** is the searchable list, **Wahlkreise** the list of all 299 Wahlkreise next to a map,
each leading to its place page.
Cards show portraits (downscaled into `fotos/` from the foundation's raw folder: `BDF_RAW`, else `raw/` next to the store) and, for members of the government, their offices. The Regierungsbank, the "Regierung" badge and filter appear once the store has the foundation's `government_role`
table.

**Fragen** (`regierung/`) counts Kleine Anfragen with answer times, Schriftliche and Mündliche Fragen and the
Regierungsbefragung per fraction; **Daten** (`daten.html`) lists sources, licences, the date of the data and known gaps.
`FOUNDATION_EXPORT` points to the foundation's `bdf export` folder; the build copies it to `daten/` and lists the files
there as downloads. Without it the page says that no export is included.

**Vorgänge** (`vorgaenge/`, formerly `gesetze/`) has one page per DIP Vorgang of type Gesetzgebung and per other
Vorgang that was debated or decided, with its status, Drucksachen, the agenda items and sub-items that carry its
Vorlagen (with their speeches) and a timeline from tabling to Verkündung on which every decision is a point with its
vote. The steps are DIP's Vorgangsablauf when the store has the foundation's `vorgang_position`, else they are made
from Drucksachen and debates.

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
