# STYLE ATLAS

Every UI style, theme and design variant ever built across the qalarc project
family — cataloged, coded, previewable, filterable, and browsable with arrow keys.

## LIVE HOSTED
**https://atlas.qalarc.com** — full gallery, chatbot (Z.AI GLM
flash), and public star ratings (Cloudflare KV). Deploy updates:
`cd dist && npx wrangler deploy` (build first with `python3 scripts/build_static.py`).

## Quick start

```bash
./launch.sh          # or: python3 atlas_server.py
# → http://localhost:1340/          the Atlas
# → http://localhost:1340/projects  library landing page
```

## What's inside

- `atlas_server.py` — serves the hub, live-mounts every style at `/<CODE>/`,
  generates swatch previews, proxies the chatbot to local Ollama
- `hub/` — the web app (gallery · collections · picks · theater · concierge)
- `catalog/atlas.json` — THE catalog (source of truth)
- `catalog/picks.json` — your starred shortlist (notes supported)
- `thumbs/` — chromium screenshots, one per style
- `findings/../` (one level up) — raw scan output per project cluster
- `scripts/` — merge / thumbnails / static build / update pipeline

## Keys

`←/→` cycle styles · `↑/↓` grid · `Enter` open · `S` star · `C` chat ·
`R` random · `/` search · `G/V/P` views · `?` help

## Adding styles (future projects)

See `AGENTS.md`. Short version: drop a findings JSON, run
`python3 scripts/update_catalog.py findings/x.json --thumbs`, restart.

## Hosting

- Local (full experience incl. LIVE mounted previews + picks): `./launch.sh`
- Hosted (live now): `python3 scripts/build_static.py && cd dist && npx wrangler deploy`
  — chat via Z.AI GLM flash (key = worker secret `ZAI_API_KEY`), public star
  ratings in KV namespace `RATINGS` (id a5e0962dd18446d593b6e5d027d6aa41)

## Codes

`TZ` tradez.au · `TX` x10 studio · `XB` x10 biz · `GM` gmux sites ·
`GT` gmux app themes · `GS` gmux UI systems · `ED` endispute · `QA` qalarc ·
`RW` reps_with_friends · `TP` airtree logos · `HL` hero-lab · `CR` crypto ·
`SA` sahha/health · `GO` goetica · `PH` phone games · `MI` misc sites ·
`GL` GLM apps · `TR` trade.sydney demos
