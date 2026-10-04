# Deploy

The site runs on server-jan and is public at https://plenar-radar.de/ through a Cloudflare Tunnel. The deployment
lives in the infra repo, `apps/bundestag` (`compose.yml`, `update.sh`, `release.sh`), and is described in its README
(Apps → bundestag, Public site); how code gets there is in [`release.md`](release.md).

In short: the compose service `research` runs `ghcr.io/jan-c-buchkremer/bundestag-research-platform:release` (moved
by a version tag, `release.md`) next to `bdf` (the foundation) and `radar`. The nightly `update.sh` runs `bdf update`,
`radar build --all`, the foundation's open-data export and `research build`; `release.sh` then assembles a release of
the public site from what was rebuilt (`releases/<time>/research` at `/`, `releases/<time>/radar` at
`/themenlandschaft/`), checks it and switches to it atomically.

```yaml
  research:
    image: ghcr.io/jan-c-buchkremer/bundestag-research-platform:release
    volumes:
      - ./data/foundation:/foundation      # writable: SQLite needs the -shm file of a WAL store even to read
      - ./data/research:/work/data         # out/: the pages, JSON exports, search index
      - ./data/radar/out:/landscape:ro     # the Themenlandschaft's per-speech JSON; blocks are left out without it
```

Built by hand on server-jan:

```sh
cd /srv/apps/bundestag && docker compose pull -q research && docker compose run --rm -T research build \
  && ./release.sh research
```

The GitHub Pages copy (2026-09-28 to 2026-10-05) is gone; plenar-radar.de is the only site.
