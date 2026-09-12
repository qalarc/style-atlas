# STYLE ATLAS — Master Plan
*One system to showcase, filter, cycle and choose from every UI style/theme ever built across all qalarc projects.*

Created: 2026-09-12 · Location: `~/projects/GLM_projects/UI_frontend_collection/style-atlas/`

---

## 1. MISSION

Hundreds of designs exist across the project landscape — websites, phone apps, chat
systems, games, dashboards, logos, theme kits. Most were "great but not selected".
Today they're scattered across dozens of folders with three competing naming
conventions and no way to browse, compare or reuse them.

**Style Atlas** = a local web app that catalogs them ALL with stable codes, live
previews, rich filters, arrow-key cycling, and an AI chatbot that narrows options
by style/color/use-case questions.

---

## 2. WHAT THE RESEARCH FOUND (planning inputs)

### 2.1 The real inventory (distinct styles, not page instances)

| Farm | Location | Distinct styles | Nature |
|---|---|---|---|
| tradez.au templates | `trade.sydney/brand_tradez_au/` | **17** full styles (`v01_trade_classic`…`v17_pulse`) + **3** palette variants (`a-gumleaf`, `b-harbour`, `c-hivis`) | trade-business site templates |
| x10 design studio | `trade.sydney/brand_x10_au/design_studio/` | **12** named styles (atelier, blueprint, contour, counsel, datum, halcyon, ledger, meridian, quorum, sigil, solace, terrace) + 4 iterations + font sampler | each has `tokens.json`! |
| x10 biz styles | `tradez_x10_biz/` (docs) + `public/` | **7** documented (Ledger, Counsel, Advisory, Practice, Boutique, Modern Firm, Compliance) + live pages | professional-services verticals |
| gmux site versions | `gmux_site_design/examples/` | **16** frozen versions (`v1-claude-cream`…`v16-wide-canvas`) + archive a–q (17) + a–m (13) + branding dirs | self-contained sites w/ changelog |
| gmux app themes | `gmux_v4…v7`, `gmux-master`, `gmuxtest` | **~10** `data-theme` themes (nerv, nerv-muted, nerv-blue, terminal, paper, light-wood, obsidian, gruvbox, ayu, dark/light) + **4** UI systems (A-ambient-glass…D-command-grid) | desktop app themes |
| endispute concepts | `Endispute_dynamic_sites/` | **18** (aurora, courtroom v1–3, mosaic, fable5: ledger/verdict/atrium/quill/meridian, fable6: clause/constellation/convergence/equilibrium/tribunal, legacy v1–5) | Next.js apps + legacy HTML |
| reps material kits | `reps_with_friends/design/style-library/` | **26** theme kits (caveman, n64, goldeneye, neobrut×5, forest, mycelial, track, …) | full material languages, `data-theme` |
| airtree logos | `MASTER_PROJECTS/airtree_pathfinder/logos/` | **~40** (15 concepts × 6 palettes + tp07 family + finals) | SVG marks incl. the lost `tp07_gumleaf` lineage |
| hero-lab options | `hero-lab/` | **43** (c1–c9, e1–e15, s1–s10, h1–h9) | combinable hero axes, file:// capable |
| qalarc demos | `qalarc.ai/projects/` | **~18+** demo dirs + qals + rule-the-city + city-battle | mixed web experiments |
| crypto themegallery | `GLM_projects/crypto_currency/website/themegallery/` + `brand/` | ~10 | crypto/trading site themes |
| sahha blogs/EAP | `sahha_work/` | ~5 blog builds + 5 EAP tailwind variants | health/wellness |
| goetica themes | `goetica/site/assets/theme/`, `goetica_phone/app/themes/` | ~8 | chat/community app themes |
| misc sites | bella, volkus.net, fivelidz, resume, epic-mission, banner-variations, demo-sites, mempalace, museall, GLM apps | ~20 | one-offs |
| **TOTAL** | | **≈ 270–320 catalog entries** | |

### 2.2 Canonical registries that ALREADY exist (import, don't re-extract)
- `trade.sydney/design_system/CATALOG.json` — counts: 29 styles, 10 palettes, 6 logo families, 45 hero options
- `brand_x10_au/design_studio/STYLE_INDEX.json` + per-style `tokens.json` (palette/fonts/scale/spacing!)
- `gmux_site_design/examples/README.md` changelog table (lineage + rejection reasons)
- `X10_SITE_STYLES.md` / `X10_DESIGN_SYSTEM.md` (7 vertical styles)
- `reps_with_friends/design/style-library/README.md` (26-kit contract)

### 2.3 Prior art to evolve (not rebuild)
- `style_chooser_server.py` (479 lines, port 1340): `MOUNTS` dict + `resolve()` path-remapping engine → heterogeneous trees serve on one port; letter-code vocabulary; chat-gate + local AI fallback
- `hero-lab`: hub contact-sheet, id ladders, hash deep-links (`#e3`), zero-build file:// operation
- `gmux_site_design`: frozen versions, changelog-as-catalog with lineage + rejection reasons
- `projects-showcase-site`: flat-JSON schema + category/status/search filters, slug deep-links

### 2.4 Technical facts
- **Thumbnails**: `/usr/bin/chromium --headless --screenshot` (playwright 1.60 under python3.11 also OK)
- **Serving**: python3 stdlib; **port 1340 free**
- **Chatbot backend**: local Ollama on :11434 with `glm-4.7-flash:32k` (OpenAI-compatible `/v1`) — real AI, offline, free; rule-based fallback
- **Self-containedness**: ~80% of HTML files are inline-CSS; worst case = CDN font fallback (layout survives); some need `/assets` root-remapping (resolve() handles)
- **Next.js farms** (endispute, some sahha): can't statically mount → mark `preview: external-url` (live gallery links exist in READMEs) or `palette-only`

---

## 3. SYSTEM DESIGN

### 3.1 Directory layout
```
UI_frontend_collection/
├── PLAN.md                       ← this file
├── findings/                     ← Phase-1 scan output (raw, per cluster)
├── style-atlas/
│   ├── atlas_server.py           # evolved style_chooser_server engine
│   ├── hub/
│   │   ├── index.html            # the app shell
│   │   ├── app.js                # gallery, filters, keyboard, theater
│   │   ├── chatbot.js            # chat drawer + filter actions
│   │   └── styles.css
│   ├── catalog/
│   │   ├── atlas.json            # MASTER catalog (generated + curated)
│   │   └── picks.json            # starred shortlist (persisted)
│   ├── thumbs/                   # CODE.png screenshots (chromium)
│   └── scripts/
│       ├── import_registries.py  # CATALOG.json / STYLE_INDEX.json / tokens.json / changelogs
│       ├── merge_catalog.py      # findings + imports → atlas.json (codes, dedupe, QA)
│       ├── gen_thumbs.py         # batch screenshots via mounted server
│       └── swatch_page.py        # palette/token mock renderer for non-HTML entries
```

### 3.2 Catalog schema (atlas.json)
```json
{
  "code": "TZ-007",                    // stable short code (the vocabulary)
  "name": "Garden Organic",
  "nativeId": "v07_garden_organic",    // original id where one exists
  "project": "tradez.au",
  "category": "website",               // see taxonomy §3.3
  "useCases": ["trade business site", "plumber", "electrician"],
  "source": "/home/fivelidz/projects/trade.sydney/brand_tradez_au/...",
  "mount": {                            // only when statically servable
    "dir": "...", "file": "index.html",
    "data": "...", "assets": "...", "shared": "..."
  },
  "externalUrl": null,                  // or live URL (Next.js farms)
  "preview": "live",                    // live | external | swatch | svg
  "thumb": "thumbs/TZ-007.png",
  "palette": { "bg": "#0B0E0B", "surface": "#…", "ink": "#…",
               "accent": "#…", "accent2": "#…", "extra": ["#…"] },
  "fonts": { "display": "Fraunces", "body": "Inter", "mono": "JetBrains Mono" },
  "mode": "dark",                       // dark | light | both
  "tags": ["organic","warm","serif","rounded"],
  "era": "2026-08",                     // file mtime
  "status": "candidate",               // candidate | final | rejected | shipped
  "lineage": "branches from TZ-003",
  "signature": "tendril dividers",      // x10 protocol concept
  "description": "1–2 sentence visual description"
}
```

### 3.3 Code prefixes & taxonomy

**Prefixes**: `TZ` tradez.au · `TX` x10 design studio · `XB` tradez_x10_biz ·
`GM` gmux site versions · `GT` gmux app themes · `GS` gmux UI systems ·
`ED` endispute · `QA` qalarc demos · `RW` reps_with_friends · `TP` airtree logos ·
`HL` hero-lab (axis-embedded: `HL-C05`, `HL-E11`, `HL-S02`, `HL-H09`) ·
`CR` crypto · `SA` sahha/health · `GO` goetica · `PH` phone games ·
`MI` misc sites · `GL` GLM apps.

**Categories** (filter axis): `website` · `landing` · `directory` · `phone-app` ·
`chat-app` · `game` · `dashboard` · `theme-kit` · `logo` · `hero-module` ·
`font-system` · `email` · `terminal` · `poster` · `business-card` · `3d`.

**Derived filters**: mode (dark/light), hue family (12 buckets computed from
palette), tag cloud, project, era, status, use-case.

### 3.4 Server (atlas_server.py) — evolution of style_chooser_server.py
- Loads `catalog/atlas.json`; startup `OK/MISSING` mount sanity check (lesson from chooser)
- `GET /` → hub UI
- `GET /p/<CODE>/` → **live mounted preview** via `resolve()` remapping (global
  `/shared/`,`/assets/`,`/data/` fallbacks + per-entry overrides + `safe_join`)
- `GET /api/catalog` → atlas.json · `GET/POST /api/picks` → picks.json
- `POST /api/chat` → Ollama `glm-4.7-flash:32k` proxy (system prompt = compact
  catalog) with **rule-based fallback** if Ollama is down
- `GET /thumbs/<CODE>.png`; `Cache-Control: no-store` on previews

### 3.5 Hub UI
- **Top bar**: search (name/code/tags/description), sort (code·project·hue·era·name), count
- **Left sidebar**: filters — category, project, mode, hue family, tags, status, use-case
- **Gallery grid**: cards = thumbnail (or generated swatch-mock), code badge,
  name, project chip, mode dot, palette strip, tags
- **Theater mode** (click card or Enter): full-viewport live preview iframe +
  side panel (big code, palette w/ click-to-copy hex, fonts, tags, lineage,
  source path, open-live button). **← / → cycles through the filtered set**
  (the core requirement), Esc exits
- **Keyboard map**: `←/→` cycle · `↑/↓` grid move · `Enter` theater · `Esc` close ·
  `/` search · `S` star/pick · `C` chat · `R` random · `?` help overlay
- **Picks view**: starred entries persisted to picks.json with optional notes
- **Compare** (stretch): two codes side-by-side split view

### 3.6 Chatbot ("Atlas Concierge")
- Drawer UI bottom-right; quick-prompt chips ("dark + gold", "chat app", "logo concepts")
- **Backend**: Ollama glm-4.7-flash:32k; system prompt embeds compact catalog
  (code, name, category, mode, top-3 colors, tags) + instruction to emit an
  optional JSON filter action, e.g. `{"filter":{"mode":"dark","tags":["gold"]}}`
- Hub applies filter actions live → chat literally narrows the gallery
- Rule-based fallback parser (color words, categories, tags) when Ollama is down
- Can answer "what palette does ED-004 use?", "which chat themes are light?",
  "give me 5 warm dark options for a law firm"

### 3.7 Previews & thumbnails
1. `live` — statically mountable HTML (≈80% of entries) → iframe + chromium screenshot
2. `external` — Next.js farms with live URLs → iframe to URL (screenshot best-effort)
3. `swatch` — theme kits / token-only entries → generated swatch page (palette +
   typography + component mock: chat bubbles for chat-app, stat cards for
   dashboard, hero block for website, HUD for game) → then screenshotted
4. `svg` — logos → direct render

---

## 4. EXECUTION PHASES

| Phase | What | Who | Output |
|---|---|---|---|
| **0. Plan** | this document | done | PLAN.md |
| **1. Scan** | 13 parallel Flash agents, one per cluster, unified brief + JSON schema | sub-agents | `findings/*.json` (~270+ entries) |
| **2. Import** | ingest existing registries (CATALOG.json, STYLE_INDEX.json, tokens.json, gmux changelog) | 1 Flash agent + script | `findings/_registries.json` |
| **3. Merge** | dedupe by source path, assign codes, normalize palette/fonts/tags/mode/hue, categorize, QA report | orchestrator (me) | `catalog/atlas.json` + QA log |
| **4. Thumbs** | gen_thumbs.py via mounted server + swatch fallback | script (background) | `thumbs/CODE.png` |
| **5. Server** | evolve atlas_server.py from style_chooser_server.py | orchestrator | working :1340 server |
| **6. Hub UI** | gallery, filters, theater, keyboard nav, picks | orchestrator (+ Flash for chatbot.js draft) | `hub/` |
| **7. Chatbot** | Ollama proxy + fallback + drawer + filter actions | orchestrator + Flash | chatbot.js + /api/chat |
| **8. QA + docs** | dead-mount check, keyboard test, chat test, README + launch script | 1 QA Flash agent + me | done system |

**Safeguards**: read-only scanning (no source projects touched); every write
confined to `UI_frontend_collection/`; scripts preserved (CLAUDE.md rule);
nothing deleted; original naming preserved in `nativeId`.

---

## 5. WHY THIS DESIGN (traced to evidence)
- **Codes as vocabulary** — chooser letters (A–H), hero-lab ids (c5+e11+s2+h9), gmux vN all converged on short stable ids; the atlas generalizes with project prefixes
- **MOUNTS + resolve()** — proven to serve heterogeneous trees on one port (chooser ran it live); reuse verbatim, generalize from inline dict to catalog-driven
- **Import registries first** — trade.sydney and x10 already have machine-readable token data; hand-extraction would be inferior + wasteful
- **Status/lineage fields** — gmux changelog records rejections & branch points; capturing this turns the atlas into institutional memory, not just a gallery
- **Ollama chatbot** — research confirmed glm-4.7-flash:32k local + OpenAI-compatible endpoint; the chatbot is real AI with zero cost and offline operation, with deterministic fallback
- **Swatch previews** — 26 reps kits and token-only styles have no page; generated mocks make EVERY entry visual (uniform reference cards)
- **No obfuscation** — showcase-site's anti-scrape layers would cripple iteration (their own protocol says never obfuscate index pages)

---

## 6. OPEN QUESTIONS (defaults chosen, flag to override)
1. Default port **1340** (free, matches existing chooser) — OK?
2. Include `rejected`/`shipped` entries? → **Yes**, filterable (institutional memory)
3. Thumbnails at 1280×900 → grid renders at card size — OK?
4. Scan scope: template-level styles + notable page-level demos (not 68k customer instances) — confirmed by research
