# Preview and releases

## Day to day

```sh
uv run research preview              # build from the live data on server-jan (~2 min), serve http://127.0.0.1:8000/
uv run research preview --no-build   # serve the last build again
uv run research preview --port 8001  # when 8000 is taken
scripts/stage.sh                  # share the running preview on the tailnet until Ctrl-C: https://<host>.ts.net:8445/
```

The preview builds from what the nightly run uses (`/srv/apps/bundestag/data`: the foundation store, its raw folder
and export, the Themenlandschaft's JSON) unless the variable is set (`BDF_DB`, `BDF_RAW`, …; `research/preview.py`). It
only reads the store, so it can run while the nightly run writes. It is served over HTTP because the Pagefind search
does not work from file://. Check a change there before proposing a commit.

## What goes live when

The live site (plenar-radar.de) is rebuilt every night by `update.sh` on server-jan, with
the code of the latest **release** of each repo: the images `ghcr.io/jan-c-buchkremer/<repo>:release`. Pushes to
`main` still publish `:main`, but nothing runs it. So data is new every morning; code changes only with a release.

The three repos release the same way: bundestag-data-foundation, bundestag-research-platform, bundestag-radar
(`docs/architecture.md`).
When a consumer needs new foundation data, release the foundation first and let one nightly run ingest before
releasing the consumer.

## Cutting a release

Versions are `v0.MINOR.PATCH`: a minor release is a vertical slice a reader can use, a patch fixes one.

1. Everything for the release is merged to `main`, CI is green, and the preview shows it working.
2. In `CHANGELOG.md`, turn "Unreleased" into `## v0.X.0 (YYYY-MM-DD)`, starting with the sentence: what can a reader
   do now that they could not before? Then the changes, one line each. Leave a fresh empty "Unreleased" above it.
   Commit to `main` ("Release v0.X.0").
3. Tag that commit and push the tag:
   ```sh
   git tag -a v0.X.0 -m "v0.X.0" && git push origin v0.X.0
   ```
   CI tests it and publishes the image as `:0.X.0` and `:release`.
4. It goes live with the next nightly run. To publish at once, on server-jan:
   ```sh
   cd /srv/apps/bundestag && docker compose pull -q research && docker compose run --rm -T research build \
     && ./release.sh research
   ```
   (`radar` the same way with `build --all`; the foundation's next ingest is the nightly one.)

Rolling back: re-run the CI run of the previous tag (`gh run list --branch v0.X.0`, then `gh run rerun <id>`); it moves
`:release` back to that version.
