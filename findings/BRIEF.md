# STYLE ATLAS — SCAN BRIEF (read fully before scanning)

You are cataloging UI/design style variants for "Style Atlas", a style reference system.
Your job: find every DISTINCT visual style in your assigned cluster and write ONE JSON file.

## RULES
- RESEARCH + WRITE ONLY the one findings file assigned to you. Never modify source projects.
- Use Read/Glob/Grep tools. If you use bash for searching: ALWAYS `timeout 30` prefix, NEVER `rg --follow`, NEVER `find -L`.
- EXCLUDE: node_modules, .git, dist, build, venv, .venv, target, __pycache__, .opencode, .next, *.min.*
- A "style" = a distinct visual identity. 20 pages sharing one theme = ONE entry. A variants folder with 6 palettes = 6 entries.
- Do NOT iterate tens of thousands of generated instance pages — find the TEMPLATE set and catalog that.
- Real data only. Never invent palettes. If you can't extract a color, use [] / omit the key.
- Read any README.md you find — it often documents style names, status (final/rejected), and lineage.

## HOW TO EXTRACT (quick recipes)
- Colors: `timeout 30 rg -o '#[0-9a-fA-F]{3,8}\b' FILE | sort | uniq -c | sort -rn | head -15`
- CSS variables (best source): look for `--bg, --surface, --ink, --accent, --gold, --hero-bg, --cta, --primary` style tokens at the top of <style> blocks or .css files. Map them into palette fields.
- Fonts: `timeout 30 rg -o "font-family:\s*[^;}]{1,60}" FILE | head -5` and Google Fonts <link> URLs (families= param).
- Mode: compute from bg hex luminance — dark if luminance < 0.35, light otherwise.
- status/lineage: from README changelogs, "FINAL"/"rejected"/"approved" mentions, folder names (final/, archive/, good/).
- If a `tokens.json` or `STYLE_INDEX.json` or `CATALOG.json` exists in your cluster — USE IT (it is canonical, better than re-extracting).

## SCHEMA — write a JSON array to your assigned file. Every entry:
```json
{
  "name": "Garden Organic",                 // human name (from docs, <title>, or folder name)
  "nativeId": "v07_garden_organic",         // original id/filename if one exists, else null
  "project": "tradez.au",                   // ASSIGNED display name (given in your task)
  "prefix": "TZ",                           // ASSIGNED code prefix (given in your task)
  "category": "website",                    // ONE of: website, landing, directory, phone-app, chat-app, game, dashboard, theme-kit, logo, hero-module, font-system, email, terminal, poster, business-card, 3d
  "useCases": ["trade business site"],      // what this style suits
  "source": "/absolute/path/to/entry/file/or/dir",
  "mount": {                                // ONLY if a statically-servable HTML entry exists
    "dir": "/abs/dir/containing/it",
    "file": "index.html",                   // entry file relative to dir
    "data": "/abs/data/dir or null",        // dir mapped to /data/* (if page fetches /data or ./data)
    "assets": "/abs/assets/dir or null",    // dir mapped to /assets/*
    "shared": "/abs/shared/dir or null"     // dir mapped to /shared/* (relative ../shared refs)
  },
  "externalUrl": null,                      // live URL if documented in README (e.g. vercel/gallery links)
  "palette": {
    "bg": "#0B0E0B", "surface": "#16211A", "ink": "#E8EFE9",
    "accent": "#7FB069", "accent2": "#C9A24E",
    "extra": ["#2A3B31", "#8A5A44"]
  },                                        // partial is fine; keys you find, null for missing
  "fonts": { "display": "Fraunces", "body": "Inter", "mono": "JetBrains Mono" },
  "mode": "dark",                           // dark | light | both
  "tags": ["organic", "warm", "serif"],     // visual descriptors; see suggested vocabulary
  "status": "candidate",                    // candidate | final | rejected | shipped (from docs; default candidate)
  "lineage": null,                          // e.g. "branches from v3" / "iteration 2 of courtroom"
  "signature": null,                        // the signature visual element if documented (e.g. "ruled ledger paper + red margin")
  "description": "1-2 sentences describing the look."
}
```

## SUGGESTED TAG VOCABULARY (use what fits, freeform allowed)
dark, light, neon, glassmorphism, gradient, minimal, brutalist, corporate, playful,
rounded, sharp, serif, sans, mono, terminal, retro, vintage, organic, warm, cool,
premium, editorial, geometric, textured, animated, australian, luxury, techy,
soft, industrial, friendly, elegant, high-contrast, muted, vivid, newspaper, blueprint

## FINAL STEP (mandatory)
1. Write the JSON array to your assigned findings path.
2. Validate: `python3 -m json.tool <yourfile> > /dev/null && echo VALID`
3. If a file is huge (>2MB), trim descriptions, keep entries.
4. Report back: entry count, categories breakdown, and any notable discoveries.
