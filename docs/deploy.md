# Deploy (phase 5)

Live since 2026-09-28 at https://jan-c-buchkremer.github.io/bundestag-mdb-cards/, rebuilt and published by the daily
`update.sh` on server-jan. The deployment lives in `infra/apps/bundestag` (merged in infra PR #1, 2026-09-28), which is
the source of truth for `compose.yml`, `update.sh` and `publish-cards.sh`; this file records how it is put together.

The cards run like the landscape: CI publishes `ghcr.io/jan-c-buchkremer/bundestag-mdb-cards:main` (public, pulls
without login), a compose service `cards` sits next to `bdf` and `landscape` in `/srv/apps/bundestag` (batch jobs run
with `docker compose run`, no long-running service), and `update.sh` builds the cards after `bdf update` and the
landscape, then publishes them to GitHub Pages from the `gh-pages` branch.

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

`publish-cards.sh` follows `publish.sh` for the landscape (one fresh force-pushed `gh-pages` commit per run), with two
differences: the cards need `cards.css`, `card.js` and the `*.json` exports next to the pages, and it pushes with its
own deploy key, `~/.ssh/bundestag-cards-pages` on server-jan, which has write access to this one repo. 653 pages plus
exports are about 58 MB per build.

## Manual run

```sh
cd /srv/apps/bundestag
docker compose pull -q cards && docker compose run --rm -T cards build && ./publish-cards.sh
```

Pages was switched on once with
`gh api -X POST repos/jan-c-buchkremer/bundestag-mdb-cards/pages -f 'source[branch]=gh-pages' -f 'source[path]=/'`.
