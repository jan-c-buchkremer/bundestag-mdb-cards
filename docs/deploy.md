# Deploy (phase 5, not yet applied)

The cards run like the landscape: an image from CI, a compose service next to `bdf` and `landscape` in
`/srv/apps/bundestag` (source: `infra/apps/bundestag`; batch jobs run with `docker compose run`, no long-running service), rebuilt by the daily `update.sh` after `bdf update`, and
published to GitHub Pages. Nothing below is applied yet; it waits for the MVP branch to be merged and pushed, which
lets CI publish `ghcr.io/jan-c-buchkremer/bundestag-mdb-cards:main`.

## Image

`Dockerfile` builds a 187 MB image (stdlib only). Tested locally on 2026-09-27:

```sh
docker build -t bundestag-mdb-cards:local .
docker run --rm -v /srv/apps/bundestag/data/foundation:/foundation -v "$PWD/data":/work/data bundestag-mdb-cards:local build
```

The foundation directory is mounted writable although it is only read: the store is in WAL mode and SQLite must
create the `-shm` file even for a `mode=ro` connection (same as the landscape).

## compose.yml

```yaml
  cards:
    image: ghcr.io/jan-c-buchkremer/bundestag-mdb-cards:main
    volumes:
      - ./data/foundation:/foundation
      - ./data/cards:/work/data        # out/: pages, JSON exports, index
```

## update.sh

After the landscape step, so a failure there does not block the cards and vice versa:

```sh
docker compose run --rm -T cards build && ./publish-cards.sh || status=$?
```

## Publishing

Same pattern as `publish.sh` for the landscape (one fresh force-pushed `gh-pages` commit per run, a deploy key with
write access to this one repo), with two differences: the cards need `cards.css`, `card.js` and the `*.json`
exports next to the pages, and the Pages URL becomes `jan-c-buchkremer.github.io/bundestag-mdb-cards/`.
653 pages plus exports are about 58 MB per build.

Open before this goes live:

- a deploy key for `bundestag-mdb-cards` (`ssh-keygen` + `gh repo deploy-key add --allow-write`);
- GitHub Pages enabled on the `gh-pages` branch;
- `infra/apps/bundestag` has drifted from the live directory (live `update.sh` differs, `publish.sh` exists only
  live); bring the repo up to date before adding the cards there.
