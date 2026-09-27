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

Built on [bundestag-data-foundation](https://github.com/jan-c-buchkremer/bundestag-data-foundation), whose SQLite
store is read, never written. Sibling of
[bundestag-topic-landscape](https://github.com/jan-c-buchkremer/bundestag-topic-landscape), the topic map of one
sitting week.

Code is MIT. Data attribution follows the foundation: "Deutscher Bundestag", "Deutscher Bundestag/Bundesrat – DIP",
abgeordnetenwatch.de (CC0 1.0).
