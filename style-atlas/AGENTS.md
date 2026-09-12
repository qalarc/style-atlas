# STYLE ATLAS — how to add & update styles (for humans and agents)

The Style Atlas catalogs every UI style/theme built across all projects.
`catalog/atlas.json` is the source of truth. Codes are stable forever
(`TZ-007` always means the same style).

## Run it

```bash
python3 ~/projects/GLM_projects/UI_frontend_collection/style-atlas/atlas_server.py
# → http://localhost:1340/          gallery (arrow keys to cycle)
# → http://localhost:1340/projects  landing page
```

Chatbot: hosted version uses Z.AI GLM flash (worker secret `ZAI_API_KEY`);
local server defaults to the built-in deterministic matcher (set `ATLAS_MODEL`
to route through local Ollama). Public star ratings: hosted in Cloudflare KV,
local in catalog/ratings.json.

## Add styles from a NEW project (the important part)

1. **Scan it** — either by hand or with a GLM-flash agent. Follow the schema in
   `../findings/BRIEF.md` (one JSON array; every entry: name, nativeId, project,
   prefix, category, source, mount, palette, fonts, mode, tags, status, lineage,
   signature, description).

2. **Pick a prefix** — 2–4 uppercase letters not already used. Existing ones:
   `TZ` tradez.au · `TX` x10 design studio · `XB` x10 biz · `GM` gmux sites ·
   `GT` gmux app themes · `GS` gmux UI systems · `ED` endispute · `QA` qalarc ·
   `RW` reps_with_friends · `TP` airtree logos · `HL` hero-lab · `CR` crypto ·
   `SA` sahha/health · `GO` goetica · `PH` phone games · `MI` misc sites ·
   `GL` GLM apps · `TR` trade.sydney demos

3. **Drop the file** into `findings/` (e.g. `findings/newproject.json`).

4. **Merge & screenshot:**
   ```bash
   cd ~/projects/GLM_projects/UI_frontend_collection/style-atlas
   python3 scripts/update_catalog.py findings/newproject.json --thumbs
   ```
   Idempotent — same `source` path never duplicates; existing codes never move.

5. Restart the server (it reads the catalog at startup).

## Category taxonomy
`website · landing · directory · phone-app · chat-app · game · dashboard ·
theme-kit · logo · hero-module · font-system · email · terminal · poster ·
business-card · 3d`

## Status values
`candidate` (default) · `final` (approved) · `rejected` (kept for memory —
ALWAYS record why in description/lineage) · `shipped` (live)

## Update an EXISTING style's metadata
Edit `catalog/atlas.json` directly (it's generated, but hand-edits to
descriptions/tags survive re-merges ONLY for entries whose source path stays
the same — merge replaces records from findings, so for lasting changes also
update the findings file or make the change in atlas.json after the last
merge). Mounts are sanity-checked at server startup (MISSING lines in log).

## Regenerate everything from scratch
```bash
python3 scripts/merge_catalog.py            # rebuild atlas.json from findings/
python3 scripts/gen_thumbs.py               # rebuild all screenshots
python3 scripts/build_static.py             # static dist/ for Cloudflare Pages
```

## Never forget
- Nothing in source projects is ever modified or deleted by the Atlas.
- Logos: the SVG is the source of truth — generation scripts live beside them
  (see the tp07_gumleaf incident, 2026-03).
