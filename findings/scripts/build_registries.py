#!/usr/bin/env python3
"""
REGISTRY IMPORT — convert existing machine-readable style registries
into the Style Atlas catalog schema (see findings/BRIEF.md).

Sources (transcribed faithfully; nothing invented):
  1. trade.sydney/design_system/CATALOG.json   -> registry "design_system"
  2. trade.sydney/brand_x10_au/design_studio/STYLE_INDEX.json -> "style_index"
  3. trade.sydney/brand_x10_au/design_studio/styles/*/tokens.json -> "tokens"
  4. gmux_site_design/examples/README.md changelog table -> "gmux_readme"
  5. tradez_x10_biz/brand/X10_SITE_STYLES.md + X10_DESIGN_SYSTEM.md -> "x10_styles"
  6. reps_with_friends/design/style-library/README.md -> "reps_readme"

Mapping rules (documented, mechanical):
  - palette slots are filled ONLY from hexes present in the source; whenever the
    source's own token key names are non-standard, the verbatim token dict is
    kept in an extra field (tokens / hexes / paletteVerbatim) so nothing is lost.
  - mode computed from bg luminance per BRIEF recipe (dark if luminance < 0.35)
    where the source has no explicit darkness field.
Output: findings/_registries.json  (single JSON array)
"""

import json, glob, os, re

TRADEZ = "/home/fivelidz/projects/trade.sydney"
OUT = "/home/fivelidz/projects/GLM_projects/UI_frontend_collection/findings/_registries.json"
CATALOG = f"{TRADEZ}/design_system/CATALOG.json"
STYLE_INDEX = f"{TRADEZ}/brand_x10_au/design_studio/STYLE_INDEX.json"
GMUX_README = "/home/fivelidz/projects/gmux_site_design/examples/README.md"
X10_STYLES_MD = "/home/fivelidz/projects/tradez_x10_biz/brand/X10_SITE_STYLES.md"
X10_SYSTEM_MD = "/home/fivelidz/projects/tradez_x10_biz/brand/X10_DESIGN_SYSTEM.md"
RWF_README = "/home/fivelidz/projects/reps_with_friends/design/style-library/README.md"


# ---------------------------------------------------------------- helpers
def luminance(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) >= 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return None


def mode_of(bg_hex):
    if not bg_hex:
        return None
    try:
        lum = luminance(bg_hex)
        return "dark" if lum is not None and lum < 0.35 else "light"
    except Exception:
        return None


def entry(**kw):
    e = {
        "name": kw.get("name"),
        "nativeId": kw.get("nativeId"),
        "project": kw.get("project"),
        "prefix": kw.get("prefix"),
        "category": kw.get("category"),
        "useCases": kw.get("useCases"),
        "source": kw.get("source"),
        "externalUrl": kw.get("externalUrl", None),
        "palette": kw.get("palette"),
        "fonts": kw.get("fonts"),
        "mode": kw.get("mode"),
        "tags": list(dict.fromkeys(kw.get("tags", []) or [])),
        "status": kw.get("status", "candidate"),
        "lineage": kw.get("lineage"),
        "signature": kw.get("signature"),
        "description": kw.get("description"),
    }
    # optional keys only when set
    for k in ("mount",):
        if kw.get(k):
            e[k] = kw[k]
    # extra fields (kept last)
    for k in (
        "registry",
        "refs",
        "tokens",
        "hexes",
        "paletteVerbatim",
        "fontsRaw",
        "googleFonts",
        "energy",
        "imagery",
        "animation",
        "sections",
        "provenance",
        "pairsWellWith",
        "avoidOn",
        "temperature",
        "saturation",
        "animationFit",
        "intensity",
        "technique",
        "axis",
        "logoFamily",
        "sectionVariants",
        "sector",
        "categories",
        "mood",
        "path",
        "recommendedCategories",
        "typeScale",
        "notes",
    ):
        if kw.get(k) is not None:
            e[k] = kw[k]
    return e


def first_present(d, keys):
    for k in keys:
        if k in d and isinstance(d[k], str) and d[k].startswith("#"):
            return d[k], k
    return None, None


BG_KEYS = ["bg", "paper", "cream", "bone", "sand", "void", "night"]
SURFACE_KEYS = [
    "surface",
    "panel",
    "paper_2",
    "paper-2",
    "bg_2",
    "bg-2",
    "surface_2",
    "cream_2",
    "bone-2",
    "night_2",
    "sand",
]
INK_KEYS = ["ink", "text"]
LINE_KEYS = [
    "line",
    "line-2",
    "rule",
    "border",
    "grid",
    "dim",
    "muted",
    "light",
    "soft",
    "pink_soft",
    "green_soft",
    "rust_soft",
    "clay_soft",
    "gum_soft",
    "slate",
    "cyan_2",
    "orange_2",
    "coral_2",
    "red_2",
    "green_2",
    "yellow_2",
    "violet_2",
    "navy_2",
    "navy_3",
    "gold_2",
    "gum_2",
    "ink_2",
    "slate_2",
    "clay_dark",
    "gold_glow",
    "accent_soft",
    "deep",
    "ocean",
    "fg",
    "fg_2",
]
ACCENT_ORDER = [
    "accent",
    "acid",
    "neon",
    "lime",
    "green",
    "teal",
    "blue",
    "cyan",
    "violet",
    "fuchsia",
    "indigo",
    "coral",
    "orange",
    "red",
    "amber",
    "yellow",
    "gold",
    "brass",
    "oxblood",
    "maroon",
    "plum",
    "terra",
    "clay",
    "rust",
    "forest",
    "sage",
    "pink",
    "lav",
    "green",
    "slate",
]


def map_tokens_to_palette(tokens, darkness=None):
    """Best-effort mapping of a verbatim token dict into schema palette slots.
    Every value comes verbatim from the source dict; leftovers -> extra."""
    if not tokens:
        return None, None
    pal, used = {}, []
    bg_keys = BG_KEYS
    if darkness == "dark":
        # prefer known dark background keys first when the style is documented dark
        bg_keys = [k for k in ("void", "night", "deep", "bg") if k in tokens] + [
            k for k in BG_KEYS if k not in ("void", "night", "deep")
        ]
    bg, k = first_present(tokens, bg_keys)
    used.append(k)
    surface, k = first_present(
        tokens, [x for x in SURFACE_KEYS if x not in used or x == "surface"]
    )
    used.append(k)
    ink, k = first_present(tokens, INK_KEYS)
    used.append(k)
    line, k = first_present(tokens, LINE_KEYS)
    used.append(k)
    rest = [kk for kk in tokens if kk not in used and isinstance(tokens[kk], str)]
    rest.sort(key=lambda kk: ACCENT_ORDER.index(kk) if kk in ACCENT_ORDER else 99)
    accent = tokens[rest[0]] if rest else None
    rest.pop(0) if rest else None
    accent2 = tokens[rest[0]] if rest else None
    rest.pop(0) if rest else None
    pal = {
        "bg": bg,
        "surface": surface,
        "ink": ink,
        "accent": accent,
        "accent2": accent2,
        "extra": [tokens[kk] for kk in rest] + ([line] if line else []),
    }
    pal = {k2: v2 for k2, v2 in pal.items() if v2 is not None}
    return pal or None, tokens


def parse_fonts_string(s):
    """'Inter 800 headings / Inter 400 body' -> {'display':..,'body':..}"""
    if not s:
        return None, None
    display = body = mono = None
    for part in s.split("/"):
        part = part.strip()
        m = re.match(r"([A-Z][A-Za-z0-9 ]+?)(?:\s+\d|$)", part)
        fam = m.group(1).strip() if m else part
        fam = re.sub(
            r"\s+(headings?|heading|display|body|ui|numerals?)\s*$", "", fam, flags=re.I
        ).strip()
        if not fam:
            continue
        low = part.lower()
        if "mono" in low:
            mono = fam
        elif "heading" in low or "display" in low:
            display = fam
        elif "body" in low:
            body = fam
        elif display is None:
            display = fam
        else:
            body = fam
    fonts = {}
    if display:
        fonts["display"] = display
    if body:
        fonts["body"] = body
    if mono:
        fonts["mono"] = mono
    return (fonts or None), s


def gf_family(gf):
    fam = gf.split(":")[0]
    return fam.replace("+", " ")


def mount_for(dirpath, file="index.html"):
    if os.path.isfile(os.path.join(dirpath, file)):
        return {
            "dir": dirpath,
            "file": file,
            "data": None,
            "assets": None,
            "shared": None,
        }
    return None


entries = []

# ================================================================ 1. CATALOG
cat = json.load(open(CATALOG))
CAT_SRC = CATALOG

for s in cat["styles"]:
    brand = s.get("brand")
    prefix = "TZ" if brand == "tradez" else "TX"
    project = "tradez.au" if brand == "tradez" else "x10.au"
    pal, verbatim = map_tokens_to_palette(s.get("tokens"), s.get("darkness"))
    fonts, fonts_raw = parse_fonts_string(s.get("fonts"))
    refs = [r for r in (s.get("tokens_source"), s.get("renderer")) if r]
    entries.append(
        entry(
            name=s["name"],
            nativeId=s["id"],
            project=project,
            prefix=prefix,
            category="website",
            useCases=s.get("industry_fit"),
            source=CAT_SRC,
            palette=pal,
            fonts=fonts,
            mode=s.get("darkness"),
            tags=list(s.get("mood_tags", [])),
            status="candidate",
            lineage=f"family: {s['family']}" if s.get("family") else None,
            description=s.get("reads_as"),
            registry="design_system",
            refs=refs,
            tokens=verbatim,
            fontsRaw=fonts_raw,
            energy=s.get("energy"),
            imagery=s.get("imagery"),
            animation=s.get("animation"),
            sections=s.get("sections"),
        )
    )

for p in cat["palettes"]:
    hx = p.get("hexes", {})
    bg = hx.get("bg")
    surface = hx.get("bg_2", hx.get("surface"))
    ink = hx.get("ink", hx.get("fg"))
    accent = hx.get("accent", hx.get("primary"))
    accent2 = hx.get("accent_2")
    extra = [
        hx[k]
        for k in (
            "primary",
            "primary_2",
            "primary_3",
            "muted",
            "line",
            "accent_soft",
            "fg_2",
            "border",
            "bg_3",
        )
        if hx.get(k)
    ]
    pal = {
        "bg": bg,
        "surface": surface,
        "ink": ink,
        "accent": accent,
        "accent2": accent2,
        "extra": extra or None,
    }
    tags = list(p.get("mood_tags", []))
    for k in ("temperature", "saturation"):
        if p.get(k):
            tags.append(p[k])
    entries.append(
        entry(
            name=p["label"],
            nativeId=p["id"],
            project="tradez.au",
            prefix="TZ",
            category="theme-kit",
            useCases=None,
            source=CAT_SRC,
            palette={k: v for k, v in pal.items() if v is not None},
            fonts=None,
            mode=p.get("darkness"),
            tags=tags,
            status="candidate",
            lineage=None,
            description=p.get("reads_as"),
            registry="design_system",
            refs=[p.get("src")] if p.get("src") else None,
            hexes=hx,
            provenance=p.get("provenance"),
            pairsWellWith=p.get("pairs_well_with"),
            avoidOn=p.get("avoid_on"),
            temperature=p.get("temperature"),
            saturation=p.get("saturation"),
        )
    )

for lf in cat["logo_families"]:
    lid = lf["id"]
    name = lid.replace("_", " ").title()
    used_by = lf.get("used_by_styles")
    entries.append(
        entry(
            name=name,
            nativeId=lid,
            project="x10.au",
            prefix="TX",
            category="logo",
            useCases=None,
            source=CAT_SRC,
            palette=None,
            fonts=None,
            mode=None,
            tags=list(lf.get("mood", [])),
            status="candidate",
            lineage=("used by styles: " + ", ".join(used_by)) if used_by else None,
            description=lf.get("geometry"),
            registry="design_system",
            refs=[cat["sources"]["logo_families"]]
            if "logo_families" in cat["sources"]
            else None,
            animationFit=lf.get("animation_fit"),
        )
    )
LOGO_BEST_FOR = {lf["id"]: lf.get("best_for") for lf in cat["logo_families"]}
for e in entries:
    if (
        e["registry"] == "design_system"
        and e["category"] == "logo"
        and e["nativeId"] in LOGO_BEST_FOR
    ):
        bf = LOGO_BEST_FOR[e["nativeId"]]
        e["useCases"] = [x.strip() for x in bf.split(",")] if bf else None

for axis_name, ax in cat["hero_axes"].items():
    for o in ax["options"]:
        entries.append(
            entry(
                name=o["name"],
                nativeId=o["id"],
                project="tradez.au",
                prefix="HL",
                category="hero-module",
                useCases=None,
                source=CAT_SRC,
                palette=None,
                fonts=None,
                mode=None,
                tags=[axis_name],
                status="candidate",
                lineage=f"hero axis '{axis_name}' — {ax.get('description')}",
                description=o.get("description"),
                registry="design_system",
                refs=[cat["sources"]["hero_axes"]]
                if "hero_axes" in cat["sources"]
                else None,
                intensity=o.get("intensity"),
                technique=ax.get("technique"),
                axis=axis_name,
            )
        )

# ============================================================ 2. STYLE_INDEX
si = json.load(open(STYLE_INDEX))
SI_DIR = os.path.dirname(STYLE_INDEX)
for s in si["styles"]:
    hx = s.get("palette", {})
    bg, k = first_present(hx, ["paper", "bone", "bg", "sand"])
    surface, k = first_present(hx, ["paper-2", "bone-2", "bg-2", "surface", "paper_2"])
    ink, k = first_present(hx, INK_KEYS)
    used = {kk for kk in (bg and [x for x in hx if hx[x] == bg] or [])}
    lineish = [kk for kk in hx if kk in LINE_KEYS]
    rest = [
        kk
        for kk in hx
        if kk not in lineish
        and kk
        not in (
            "paper",
            "bone",
            "bg",
            "sand",
            "paper-2",
            "bone-2",
            "bg-2",
            "surface",
            "ink",
            "text",
        )
    ]
    rest.sort(key=lambda kk: ACCENT_ORDER.index(kk) if kk in ACCENT_ORDER else 99)
    accent = hx[rest[0]] if rest else None
    accent2 = hx[rest[1]] if len(rest) > 1 else None
    extra = [hx[kk] for kk in hx if kk in lineish or kk in rest[2:]]
    pal = {
        k2: v2
        for k2, v2 in {
            "bg": bg,
            "surface": surface,
            "ink": ink,
            "accent": accent,
            "accent2": accent2,
            "extra": extra or None,
        }.items()
        if v2 is not None
    }
    gfs = s.get("google_fonts", [])
    fams = [gf_family(g) for g in gfs]
    fonts = {}
    if fams:
        fonts["display"] = fams[0]
    if len(fams) > 1:
        fonts["body"] = fams[1]
    if len(fams) > 2 and "mono" in fams[2].lower():
        fonts["mono"] = fams[2]
    st_dir = os.path.join(SI_DIR, "styles", s["id"])
    entries.append(
        entry(
            name=s["name"],
            nativeId=s["id"],
            project="x10.au",
            prefix="TX",
            category="website",
            useCases=s.get("professions"),
            source=STYLE_INDEX,
            palette=pal or None,
            fonts=fonts or None,
            mode=mode_of(bg),
            tags=[s["sector"].lower()] if s.get("sector") else [],
            status="candidate",
            lineage=None,
            description=s.get("one_liner"),
            signature=s.get("signature"),
            mount=mount_for(st_dir),
            registry="style_index",
            googleFonts=gfs or None,
            paletteVerbatim=hx,
            logoFamily=s.get("logo_family"),
            sectionVariants=s.get("section_variants"),
            sector=s.get("sector"),
            categories=s.get("categories"),
            mood=s.get("mood"),
            path=s.get("path"),
        )
    )

# ================================================================ 3. tokens.json
TOK_BASE = f"{TRADEZ}/brand_x10_au/design_studio"
for tf in sorted(glob.glob(f"{TOK_BASE}/styles/*/tokens.json")):
    t = json.load(open(tf))
    hx = t.get("palette", {})
    bg = hx.get("bg")
    surface = hx.get("surface")
    ink = hx.get("ink")
    accent = hx.get("acid")
    if not accent:
        for k in ACCENT_ORDER:
            if k in hx and k not in ("bg", "surface", "ink", "line"):
                accent = hx[k]
                break
    accent2 = hx.get("line")
    leftover = [
        v
        for k, v in hx.items()
        if v not in (bg, surface, ink, accent, accent2)
        and k not in ("bg", "surface", "ink", "acid", "line")
    ]
    pal = {
        k2: v2
        for k2, v2 in {
            "bg": bg,
            "surface": surface,
            "ink": ink,
            "accent": accent,
            "accent2": accent2,
            "extra": leftover or None,
        }.items()
        if v2 is not None
    }
    f = t.get("fonts", {})
    fonts = {k: f[k] for k in ("display", "body", "mono") if f.get(k)} or None
    sid = t.get("style_id") or os.path.basename(os.path.dirname(tf))
    st_dir = os.path.dirname(tf)
    entries.append(
        entry(
            name=t.get("name", sid),
            nativeId=sid,
            project="x10.au",
            prefix="TX",
            category="website",
            useCases=t.get("recommended_professions"),
            source=tf,
            palette=pal or None,
            fonts=fonts,
            mode=mode_of(bg),
            tags=[],
            status="candidate",
            lineage=None,
            description=t.get("one_liner"),
            signature=t.get("signature_element"),
            mount=mount_for(st_dir),
            registry="tokens",
            paletteVerbatim=hx,
            googleFonts=f.get("google_families"),
            logoFamily=t.get("logo_family"),
            sectionVariants=t.get("section_variants"),
            recommendedCategories=t.get("recommended_categories"),
            mood=t.get("mood"),
            typeScale=t.get("type_scale"),
        )
    )

# ================================================================ 4. gmux README
GMUX_BASE = "/home/fivelidz/projects/gmux_site_design/examples"
GMUX_ROWS = [
    (
        "v1",
        "v1-claude-cream",
        None,
        "Original one-shot. Warm Claude cream + coral, floating terminal windows in hero, hand-indicator blob drifting across.",
    ),
    (
        "v2",
        "v2-studio-projector",
        None,
        "Matte playful primary palette, theme selector (6 palettes, accent-only), new hero: person silhouette in front of a projected wall of 6 agent cards with readiness + live todo list + beam to focused agent.",
    ),
    (
        "v3",
        "v3-full-site-themes",
        None,
        "Projector scene locked to its best dark look (no longer shifts with theme). Theme selector now restyles the whole site (neutrals + accents) with 8 palettes: Studio, Playground, Forest, Citrus, Ocean, Rose, Graphite, Midnight. Scenario 4 rewritten to be gesture-first (\u201cgesture to the next agent together\u201d).",
    ),
    (
        "v4",
        "v4-forest-fonts",
        None,
        "Forest is now default. Title-font selector added (7 options: Fraunces, Instrument Serif, Playfair, DM Serif, Cormorant, Space Grotesk, Inter Tight), each chip previews its own face. Em-dashes removed throughout visitor copy. Scenario 4 redrawn as a richer two-people-with-shared-screen SVG scene, hand waves on a 6s cadence and cycles the highlighted agent. Note: picker logic broke the hero projector scene; v5 branches from v3 instead.",
    ),
    (
        "v5",
        "v5-title-alternation",
        "branched from v3 (not v4) so the projector hero is guaranteed intact",
        "Theme & font pickers removed. Forest palette locked in. Three hero title words (agents, beautifully, naturally) gently rotate through 5 faces (Fraunces italic, Pacifico, Cabin Sketch, Exo 2 italic, Viga), staggered and zero-layout-shift thanks to JS width measurement. Scenario 4 art massively upgraded: richer SVG people with hair details, waving arm, nodding partner, 3-card shared screen with selected-card highlight + ticking todo, dynamically-aimed dashed voice lines from both people, sequenced speech bubbles, floor-glow thread.",
    ),
    (
        "v6",
        "v6-exo-ttl",
        None,
        "Interest section muted (text steps down from 100% cream to ~76%/88%/62% mixes; glow radials softened; ticker panel border pulled back). Title font alternation removed \u2014 back to Fraunces only for all titles. Confirmed Fraunces is safe (Anthropic uses proprietary Anthropic Sans/Serif/Mono, not Fraunces). All four decorative webfonts, the .alt-word CSS, and the font-cycling JS cleaned out.",
    ),
    (
        "v7",
        "v7-phone-seo-logo",
        None,
        "Phone-control card overlap fixed (cell reserves padding for the phone, shrinks on medium widths, drops to flow below 900px). \u201cGesture-based terminal multiplexer\u201d added for SEO: hero pill, footer line, <title>, meta description, keywords, Open Graph + Twitter tags, JSON-LD structured data. Logo hand enlarged (viewBox 80\u219248, hand fills ~85%, ~1.5\u00d7 visual size) and new logo-options.html gallery with 13 lockup variations across type / terminal-native / banner-at-scale groups.",
    ),
    (
        "v8",
        "v8-mobile-gesture-form",
        None,
        "Logo G adopted (wordmark over tagline in nav). Real gesture engine ported from qalarc.com showcase: full-page overlay, corner widget with smoothing/sensitivity sliders, palm-size-normalised pinch, lerp-smoothed scroll target, 2.5s-frame watchdog, CapsLock pause. Mobile pass: hides oversight card + layouts section + gesture demo on phones; promotes Phone-control card to full-width first-position with new on-the-go copy and an \u201cAR glasses coming\u201d pill note. Notify-me \u2192 Google Form: direct POST to a Google Form you own, responses land in a Sheet; full setup walkthrough in GOOGLE_FORM_SETUP.md. Worker simplified: drops /email and /admin/emails, keeps /count, /vote, /admin/stats.",
    ),
    (
        "v9",
        "v9-gesture-fixed",
        None,
        "Gesture widget jitter + post-disable scroll persistence fixed. One-Euro filter on dY (kills rest-tremor, lets fast moves through cleanly), bigger dead-zone (0.018), calmer defaults (sens 2.5 / smooth 0.10), smoothTarget resync on pinchStart/End and manual scroll, pause now cancels lerp and clears canvases, new \u2715 stop button for full teardown (releases camera stream + all RAFs + state), render cadence halved for full-screen overlay, maxNumHands: 1, stricter confidence. Copy is explicit about right-hand-only everywhere.",
    ),
    (
        "v10",
        "v10-gesture-playground",
        None,
        "Scroll-hijack abandoned. Replaced with a fullscreen gesture playground: mycelium background art always on behind the page (branching filaments + twinkling tips), both hands tracked simultaneously with skeleton + gesture-label pill (PINCH, OPEN PALM, FIST, POINT, PEACE, THUMBS UP), pinch spawns glowing energy orbs that drift with gravity and fade; mycelium grows curved tendrils toward nearby orbs in real time. Widget simplified to pause + stop. No scrolling hijacked, no sliders, no filter.",
    ),
    (
        "v11",
        "v11-organic-mycelium",
        "mycelium rebuilt in the demo-organic.doof.ing style",
        "Hands now actually render (v10 had a gmxActive ordering bug that killed the render loop on its first frame). Gesture labels promoted to HTML pills for guaranteed visibility. Mycelium canvas promoted to z-index 700 with mix-blend-mode: multiply so it shows over the whole site, not hidden behind opaque section bgs. Mycelium rebuilt in the demo-organic.doof.ing style: edge-spawned networks with BFS growth queue, 60-frame fade-in, 500-900 frame life, signal pulses, drifting spores. Fingertip chase: new growth biased toward fingertips. Problem: too dark (multiply blend) and too laggy.",
    ),
    (
        "v12",
        "v12-snappy",
        "mycelium replaced with a drifting point cloud",
        "Mycelium replaced with a drifting point cloud. ~70 glowing points drift in a sin/cos loop, connected by proximity lines (ONE beginPath+stroke for all lines). Additive blending (globalCompositeOperation:'lighter') gives a light/glowy look on cream, palette bumped to bright honey / sage / cream / coral. Fingertip chase is visibly immediate: points within 200px pull toward the fingertip each frame, plus bright cream glow lines from the fingertip to its 6 nearest points. Frame cap 30fps idle / 60fps tracked. O(N) per frame, no per-frame allocations. Snappy on any modern machine.",
    ),
    (
        "v13",
        "v13-zoom-launcher",
        None,
        "Crash recovery rebuilt: 1.2s hard timeout per MediaPipe frame via Promise.race, escalating watchdog (trip 1: kick loop, trip 2: recreate Hands instance, trip 3: full teardown). Art reveals only on enable: canvas opacity 0 at load, 0.85 on activation, 0 on stop; loop gated by gmxActive so zero CPU cost until needed. Camera zoom slider (1.0-2.5\u00d7, default 1.5) under the thumbnail \u2014 CSS scale on both video and glove canvas to help hands stay centred on widescreens. Pinch-drag launcher: drag path recorded during pinch, velocity computed on release, launches a flying orb with the flick momentum. Orbs die faster (10s \u2192 3.5s, cap 40 \u2192 24). Zoom slider went the wrong direction \u2014 fixed in v14.",
    ),
    (
        "v14",
        "v14-amplify",
        "branched from v13 lineage but rejected",
        "Overscan amplification replaces v13's zoom. Hand-overlay canvas extends 18vmin past every viewport edge (negative CSS inset, canvas sized to innerWidth + 2*os). MediaPipe's full [0,1] camera range maps onto the extended canvas, so camera edges land off-screen and small hand movements cover a lot of viewport. New gmxMpToVx/Vy module helpers keep the HTML label pills, mycelium chase targets, and pinch-launcher seeds aligned with where the glove visually renders. Zoom slider + --cam-zoom removed. Thumbnail stays raw so user can see real-frame position. Rejected: crashed, and the \u201chand-off-screen but still rendering\u201d behaviour was wrong.",
    ),
    (
        "v15",
        "v15-auto-restart",
        "branched from v13 (v14 was rejected)",
        "Fixes the chronic \u201chands disappear and never come back\u201d bug. Branched from v13 (v14 was rejected). v13's in-process MediaPipe recreation didn't work because WASM/WebGL state stays corrupted across recreation. v15 replaces it with a full pipeline restart: stop MediaStream, close Hands instance, wait 400ms, re-init from scratch. Detects TWO failure modes \u2014 freeze (onResults not firing for 3s) and blind (onResults firing but no hand landmarks for 12s). Widget UI stays visible during the ~1-2s restart; user sees \u201crestarting\u2026\u201d briefly.",
    ),
    (
        "v16",
        "v16-wide-canvas",
        None,
        "Hand overlay extends 12vw past each viewport edge (desktop only) so hands at the camera's sides slide off-screen smoothly instead of clipping. New mpToVx/Vy helpers keep label pills, mycelium chase, and pinch-launcher seeds aligned. Counter stays hidden until 200 real votes have landed \u2014 drift is no longer displayed as engagement. Hardware/OS details captured per vote (screen, dpr, platform, lang, cores, memory, touch, reduced-motion, prefers-dark, timezone, gesture-tried) with a clearly visible privacy disclosure on the page. New worker GET /admin/hw aggregates the breakdown. Enable button in the try section replaces the external link to qalarc showcase.",
    ),
]
GMUX_TAGS = {
    "v1": ["light", "warm", "terminal", "cream", "coral"],
    "v2": ["playful", "matte", "theme-selector"],
    "v3": ["dark", "theme-selector", "playful"],
    "v4": ["forest", "green", "font-picker", "serif"],
    "v5": ["forest", "green", "animated", "typographic"],
    "v6": ["forest", "green", "serif", "muted"],
    "v7": ["forest", "green", "seo", "logo"],
    "v8": ["forest", "gesture", "mobile"],
    "v9": ["gesture", "camera", "hand-tracking"],
    "v10": ["gesture", "mycelium", "playground", "dark"],
    "v11": ["mycelium", "organic", "dark"],
    "v12": ["point-cloud", "glow", "light", "snappy"],
    "v13": ["gesture", "camera", "launcher"],
    "v14": ["gesture", "overscan"],
    "v15": ["gesture", "camera", "resilient"],
    "v16": ["gesture", "wide-canvas", "privacy"],
}
for ver, folder, lineage, what in GMUX_ROWS:
    d = os.path.join(GMUX_BASE, folder)
    status = "rejected" if ver in ("v11", "v14") else "candidate"
    entries.append(
        entry(
            name=folder,
            nativeId=folder,
            project="gmux.ai",
            prefix="GM",
            category="website",
            useCases=None,
            source=d if os.path.isdir(d) else GMUX_README,
            palette=None,
            fonts=None,
            mode=None,
            tags=GMUX_TAGS[ver],
            status=status,
            lineage=lineage,
            signature=None,
            description=what,
            mount=mount_for(d),
            registry="gmux_readme",
        )
    )

# ================================================================ 5. XB docs
X10_BASE = {
    "bg": "#FAF8F5",
    "surface": "#F3EFE9",
    "ink": "#1A1A1A",
    "accent": "#0D9488",
    "accent2": "#5EEAD4",
    "extra": ["#0F1E2E", "#2A4A6B", "#E2DDD4", "#5C5C5C", "#8A8A8A"],
}


def x10_pal(overrides=None, extra_add=None):
    pal = dict(X10_BASE)
    pal["extra"] = list(X10_BASE["extra"])
    if extra_add:
        pal["extra"] += extra_add
    if overrides:
        for k, v in overrides.items():
            if v is None:
                pal[k] = None
            elif k == "extra":
                pal["extra"] = v
            else:
                pal[k] = v
    return {k: v for k, v in pal.items() if v}


XB_STYLES = [
    {
        "nativeId": "ledger",
        "name": "Ledger",
        "oneLiner": "The clean accounting minimal. Named for the ledger book \u2014 precise, orderly, no-nonsense. For firms that want to look sharp and modern without any decoration \u2014 clean fintech energy (Xero, QuickBooks, Stripe).",
        "mood": ["precise", "orderly", "modern-minimal"],
        "vertical": ["Accounting firms", "Bookkeepers", "Tax agents"],
        "signature": "A subtle grid-line background pattern (like ledger paper rules) at very low opacity in the hero section \u2014 a barely-visible nod to the accounting heritage.",
        "fonts": {"display": "Inter", "body": "Inter"},
        "serif": "No",
        "darkSections": "Minimal",
        "heroPhoto": "No (geometric)",
        "palette": x10_pal(),
        "tags": [
            "minimal",
            "clean",
            "corporate",
            "light",
            "sans",
            "geometric",
            "fintech",
        ],
    },
    {
        "nativeId": "counsel",
        "name": "Counsel",
        "oneLiner": "The refined legal serif. The most traditional, formal style \u2014 for law firms, conveyancers, and any practice conveying established authority with a modern sensibility.",
        "mood": ["established", "authoritative", "traditional-but-current"],
        "vertical": ["Law firms", "Conveyancers", "Notaries", "Estate planners"],
        "signature": "A thin gold-bronze rule (1px) beneath each centred section heading \u2014 editorial, publication-like feel.",
        "fonts": {
            "display": "Fraunces",
            "body": "Fraunces",
            "note": "Inter for UI elements (nav, buttons, forms)",
        },
        "serif": "Yes (heavy)",
        "darkSections": "Yes (hero)",
        "heroPhoto": "No",
        "palette": x10_pal(
            {"accent": "#92785B", "accent2": "#C4A882"}, extra_add=["#0F1E2E dark hero"]
        ),
        "tags": [
            "serif",
            "editorial",
            "traditional",
            "premium",
            "elegant",
            "both",
            "legal",
        ],
    },
    {
        "nativeId": "advisory",
        "name": "Advisory",
        "oneLiner": "The modern consulting. The most \u201cpremium consulting\u201d style \u2014 McKinsey/BCG/Deloitte energy, smaller and more approachable. For business advisors, virtual CFOs, management consultants, strategy firms.",
        "mood": ["strategic", "premium", "insight-driven", "confident"],
        "vertical": [
            "Business advisors",
            "Virtual CFOs",
            "Management consultants",
            "Strategy firms",
        ],
        "signature": "Full-width \u201cinsight bands\u201d \u2014 teal-background sections carrying a single large statistic or provocative quote, breaking up the page and creating rhythm.",
        "fonts": {
            "display": "Fraunces",
            "body": "Inter",
            "note": "dramatic type scale, H1 at 4rem",
        },
        "serif": "Yes (display)",
        "darkSections": "Yes (insight bands)",
        "heroPhoto": "No",
        "palette": x10_pal(
            {"accent": "#0D9488"}, extra_add=["#0D9488 as bold section fills"]
        ),
        "tags": ["premium", "corporate", "editorial", "confident", "both", "teal"],
    },
    {
        "nativeId": "practice",
        "name": "Practice",
        "oneLiner": "The warm approachable bookkeeper. For solo and small-team bookkeepers, BAS agents and small practices that want to feel friendly, accessible and human \u2014 \u201cyour trusted local bookkeeper\u201d.",
        "mood": ["warm", "approachable", "helpful", "human", "local"],
        "vertical": [
            "Bookkeepers",
            "BAS agents",
            "Small accounting practices",
            "Payroll services",
        ],
        "signature": "A \u201cHow we work\u201d section with 3\u20134 numbered steps, each with a warm illustration or icon; FAQ accordion at the bottom.",
        "fonts": {
            "display": "Inter",
            "body": "Inter",
            "note": "Inter 600 headings (softer), body 1.0625rem",
        },
        "serif": "No",
        "darkSections": "No",
        "heroPhoto": "Yes (headshot)",
        "palette": x10_pal(
            {"accent2": "#5EEAD4"},
            extra_add=["#C2410C terracotta secondary accent, used sparingly"],
        ),
        "tags": ["warm", "friendly", "light", "soft", "human", "rounded"],
    },
    {
        "nativeId": "boutique",
        "name": "Boutique",
        "oneLiner": "The premium small-firm. The most visually luxurious style \u2014 a boutique private bank or high-end family law firm. For specialist tax advisors, wealth management, premium legal practices, family offices.",
        "mood": ["luxurious", "exclusive", "meticulous", "discreet"],
        "vertical": [
            "Specialist tax advisors",
            "Wealth management",
            "Premium law firms",
            "Family offices",
        ],
        "signature": "Extreme whitespace \u2014 sections have 128px+ vertical padding, content max-width 800px. The restraint IS the design.",
        "fonts": {
            "display": "Fraunces",
            "body": "Inter",
            "note": "H1 4rem+, letter-spacing -0.03em, body 0.9375rem/1.7",
        },
        "serif": "Yes (large)",
        "darkSections": "Yes (extensive)",
        "heroPhoto": "Optional",
        "palette": x10_pal(
            {"accent": "#92785B", "ink": "#0A1620"},
            extra_add=["#0A1620 even-darker navy primary"],
        ),
        "tags": [
            "luxury",
            "premium",
            "dark",
            "minimal",
            "elegant",
            "serif",
            "restraint",
        ],
    },
    {
        "nativeId": "modern_firm",
        "name": "Modern Firm",
        "oneLiner": "The contemporary multi-partner practice. The most \u201ccomplete website\u201d style \u2014 handles complexity gracefully for mid-sized firms (5\u201320 people) with multiple partners, service lines and office locations.",
        "mood": ["professional", "comprehensive", "structured", "capable"],
        "vertical": [
            "Mid-sized accounting firms",
            "Multi-partner law firms",
            "Financial planning practices",
        ],
        "signature": "A \u201cTeam\u201d / \u201cPartners\u201d section with photos, names, titles and credentials per partner \u2014 the credibility centre of a multi-partner firm.",
        "fonts": {
            "display": "Fraunces",
            "body": "Inter",
            "note": "Fraunces H1\u2013H3, Inter H4/body/UI, standard x10 scale",
        },
        "serif": "Yes (headings)",
        "darkSections": "Minimal",
        "heroPhoto": "Yes (office/team)",
        "palette": x10_pal(),
        "tags": ["corporate", "professional", "structured", "light", "comprehensive"],
    },
    {
        "nativeId": "compliance",
        "name": "Compliance",
        "oneLiner": "The no-frills regulatory-forward style. For firms where compliance and regulatory authority are the primary trust signals \u2014 registered tax agents, SMSF specialists, AFSL holders, audit firms.",
        "mood": ["authoritative", "regulated", "transparent", "no-nonsense"],
        "vertical": [
            "Registered tax agents",
            "SMSF specialists",
            "Audit firms",
            "AFSL-holding practices",
        ],
        "signature": "A \u201cRegulatory Standing\u201d section listing every registration with its number, status, and a link to verify (e.g. the TPB register). Maximum transparency.",
        "fonts": {
            "display": "Fraunces",
            "body": "Inter",
            "note": "Fraunces only for H1; Inter everywhere else; tabular figures for registration numbers and fee disclosures",
        },
        "serif": "No (H1 only)",
        "darkSections": "No",
        "heroPhoto": "No",
        "palette": x10_pal(
            {"accent": "#0D9488"},
            extra_add=["#0D9488 for regulatory badges and status indicators"],
        ),
        "tags": [
            "corporate",
            "structured",
            "document-like",
            "light",
            "transparent",
            "tabular",
        ],
    },
]
# normalise: palette "extra" must contain pure hexes only; any annotation text
# after the hex is moved into a "notes" field (info preserved, not invented)
for st in XB_STYLES:
    _ex = st.get("palette", {}).get("extra")
    if _ex:
        _clean, _notes = [], []
        for _v in _ex:
            _m = re.match(r"(#[0-9a-fA-F]{3,8})\s*(.*)", str(_v))
            if _m:
                if _m.group(1) not in _clean:
                    _clean.append(_m.group(1))
                if _m.group(2):
                    _notes.append(_m.group(2))
        st["palette"]["extra"] = _clean
        if _notes:
            st["notes"] = "; ".join(_notes)

for st in XB_STYLES:
    entries.append(
        entry(
            name=st["name"],
            nativeId=st["nativeId"],
            project="x10.au",
            prefix="XB",
            category="website",
            useCases=st["vertical"],
            source=X10_STYLES_MD,
            palette=st["palette"],
            fonts=st["fonts"],
            mode="both" if st["darkSections"].startswith("Yes") else "light",
            tags=st["tags"],
            status="candidate",
            lineage="design brief derived from X10_DESIGN_SYSTEM.md; implementation target client_sites/templates/ (one renderer per style)",
            signature=st["signature"],
            description=st["oneLiner"],
            registry="x10_styles",
            refs=[X10_SYSTEM_MD],
            mood=st["mood"],
            notes=st.get("notes"),
        )
    )

# ================================================================ 6. RWF kits
RWF_SRC = RWF_README
RWF_KITS = [
    # --- 18 built for RWF (id, name, describe-it-as, group)
    (
        "lime",
        "Lime Athletic",
        "a steel weight-room floor under fluorescent light \u2014 matte charcoal, one lime stripe, technical type.",
        "built for RWF",
        ["dark", "industrial", "technical", "mono", "high-contrast"],
        None,
        None,
        None,
    ),
    (
        "gold",
        "Gold Arcade",
        "a late-night arcade cabinet \u2014 deep purple shell, marquee-gold buttons, Anton capitals.",
        "built for RWF",
        ["dark", "playful", "retro", "arcade"],
        None,
        None,
        None,
    ),
    (
        "sunset",
        "Sunset Swiss",
        "a Swiss-designed race timing sheet \u2014 flat warm paper, hairline ink rules on a faint alignment grid, one vermillion accent doing functional work. No shadow exists in this kit.",
        "built for RWF",
        ["light", "swiss", "minimal", "warm", "flat"],
        None,
        None,
        None,
    ),
    (
        "neon",
        "Midnight Neon",
        "an esports broadcast desk \u2014 blue-black glass, cyan + magenta rim-light, mono numerals.",
        "built for RWF",
        ["dark", "neon", "glassmorphism", "esports", "mono"],
        None,
        None,
        None,
    ),
    (
        "forest",
        "Forest Retro",
        "a 1970s family board-game box \u2014 walnut tones, mustard + burnt-orange, soft rounded everything.",
        "built for RWF",
        ["retro", "warm", "rounded", "vintage"],
        None,
        None,
        None,
    ),
    (
        "board",
        "Stadium Board",
        "a flip-scoreboard stadium \u2014 split-flap numerals, lane-paint stripes, starting-block buttons, photo-finish tape.",
        "built for RWF",
        ["sport", "split-flap", "retro"],
        None,
        None,
        None,
    ),
    (
        "mycelial",
        "Mycelial",
        "a bioluminescent root network \u2014 tendril dividers, spore-drift air, fungus-cap buttons, growth-ring progress. Everything breathes.",
        "built for RWF",
        ["organic", "bioluminescent", "animated"],
        None,
        None,
        None,
    ),
    (
        "techy",
        "Mission Control",
        "a flight telemetry console \u2014 brushed metal, corner rivets, scanlines, LED numerals, guarded switches, boot-up reveals.",
        "built for RWF",
        ["industrial", "terminal", "techy", "mono"],
        None,
        None,
        None,
    ),
    (
        "track",
        "Track & Field",
        "stadium signage \u2014 condensed timing type, painted lane rows, race-bib ranks, chalk grids.",
        "built for RWF",
        ["sport", "signage", "condensed"],
        None,
        None,
        None,
    ),
    (
        "cardtable",
        "Card Table",
        "green felt and bone \u2014 brushed felt noise, dealer-chip buttons, cream letterpress cards, brass hairlines.",
        "built for RWF",
        ["vintage", "textured", "warm"],
        None,
        None,
        None,
    ),
    (
        "caveman",
        "Caveman",
        "carved stone and fire \u2014 ROCK buttons with chiselled facets, ochre cave-paint walls, bone-white type, fire-glow danger.",
        "built for RWF",
        ["playful", "textured", "primitive", "warm"],
        None,
        None,
        None,
    ),
    (
        "n64",
        "N64",
        "a low-poly fog console \u2014 vertex-gradient washes, stepped bevels, cartridge-slot buttons, square avatars, fog reveals.",
        "built for RWF",
        ["retro", "low-poly", "playful", "gradient"],
        None,
        None,
        None,
    ),
    (
        "goldeneye",
        "GoldenEye",
        "a spy dossier HUD \u2014 gunmetal notched panels, watch gauges, typewriter objectives under redaction, reticle focus.",
        "built for RWF",
        ["dark", "techy", "spy", "typewriter"],
        None,
        None,
        None,
    ),
    (
        "neobrut",
        "Sports Poster \u00b7 original",
        "a neo-brutalist sports poster with a soft underbelly \u2014 huge duotone type shouting on warm cream, halftone dots, thick ink rules, sticker badges, an exposed grid \u2014 then every corner underneath is rounded, every press soft, every hover gentle. The founder-named favourite; the baseline the four variants below riff on.",
        "built for RWF",
        ["brutalist", "poster", "high-contrast", "playful", "light"],
        None,
        None,
        "founder-named favourite; baseline for the four neobrut-* variants",
    ),
    (
        "neobrut-field",
        "Sports Poster \u00b7 Field Day",
        "the SPORTS side dominant \u2014 a stadium day-poster: giant condensed scoreboard type on ink modules, team-badge roundels, ticket-stub chips with punched perforations, halftone crowd haze, mown-stripe rules \u2014 and the underbelly is cream paper, corners rounded under, one warm clay plate shadow, buttery 0.4s eases.",
        "built for RWF",
        ["brutalist", "poster", "sport", "condensed"],
        None,
        None,
        "variant of neobrut (Sports Poster \u00b7 original): SPORTS side dominant",
    ),
    (
        "neobrut-zine",
        "Sports Poster \u00b7 Fan Zine",
        "the POSTER side dominant \u2014 the club fanzine photocopied at 3am: heavy copier grain, plates misregistered 2\u20133px into cyan + riso-pink, hand-torn panels, typewriter headlines with marker swipes, rubber-stamp toggles \u2014 and the underbelly is pastel risograph inks and a gentle wobble.",
        "built for RWF",
        ["brutalist", "zine", "risograph", "textured"],
        None,
        None,
        "variant of neobrut (Sports Poster \u00b7 original): POSTER side dominant",
    ),
    (
        "neobrut-ticket",
        "Sports Poster \u00b7 Wayfinding",
        "the STRUCTURAL side \u2014 the venue as a signage system: departure-board numerals flipping amber on ink modules, numbered-section badges, pictogram rings, dashed platform rules with floor arrows \u2014 and the underbelly is soft paper, 16px corners on every hard module, ink softened off pure black.",
        "built for RWF",
        ["brutalist", "signage", "wayfinding", "mono"],
        None,
        None,
        "variant of neobrut (Sports Poster \u00b7 original): STRUCTURAL side",
    ),
    (
        "neobrut-locker",
        "Sports Poster \u00b7 Clubhouse",
        "the CLUBHOUSE side (the agent's own fourth reading) \u2014 the equipment room after training: vent-slot lockers, screwed-on nameplates, jersey numbers on mesh bibs, sports-tape rules, wristband toggles \u2014 everything towel-soft, rounded, comfortably worn in.",
        "built for RWF",
        ["brutalist", "soft", "rounded", "sport"],
        None,
        None,
        "variant of neobrut (Sports Poster \u00b7 original): CLUBHOUSE side",
    ),
    # --- 8 mined kits (hexes verbatim from README DNA column)
    (
        "x10",
        "Gum Professional",
        "near-black green with gum green + gold \u2014 the 200px inset vignette, gold focus rings, zebra listing rows, 6\u20138px radii. (from x10.au)",
        "mined from x10.au live CSS 2026-09-03",
        ["dark", "premium", "organic", "mono", "australian"],
        {
            "bg": "#0b0e0b",
            "surface": "#141a14",
            "accent": "#6E9A6A",
            "accent2": "#C9A24E",
        },
        {"display": "Space Grotesk", "mono": "JetBrains Mono"},
        "mined from x10.au live CSS 2026-09-03",
    ),
    (
        "doof",
        "Void Rave",
        "the void, sacred trinity purple/orange/cyan, ritual 135\u00b0 gradients, 30px glow shadows, blob radii, gradient-clipped headings. (from doof.ing)",
        "mined from doof.ing live CSS 2026-09-03",
        ["dark", "neon", "gradient", "glow", "rave"],
        {
            "bg": "#0a0a0f",
            "accent": "#a855f7",
            "accent2": "#f97316",
            "extra": ["#22d3ee"],
        },
        None,
        "mined from doof.ing live CSS 2026-09-03",
    ),
    (
        "qalarc",
        "Pastel Studio",
        "cream + ink, the pastel garden (blush, lavender, sky, mint, peach), glass cards + blur, 16/8/100px radii, DM Serif Display + Space Mono. (from qalarc.com)",
        "mined from qalarc.com live CSS 2026-09-03",
        ["light", "pastel", "glassmorphism", "soft", "friendly"],
        {
            "bg": "#fdf6ee",
            "ink": "#2a2035",
            "accent": "#f2c4ce",
            "accent2": "#c9b8e8",
            "extra": ["#a8d8ea", "#b8e8c8"],
        },
        {"display": "DM Serif Display", "mono": "Space Mono"},
        "mined from qalarc.com live CSS 2026-09-03",
    ),
    (
        "tradez",
        "Warm Trade",
        "warm sand, gum-leaf green (AA-deepened), gold, chunky Fraunces 800/900 wonky-cut headlines, zebra rows, dark-green CTA blocks, honest 6\u201310px radii. (from tradez.au)",
        "mined from tradez.au live CSS 2026-09-03",
        ["light", "warm", "organic", "australian", "serif"],
        {"bg": "#FBF8EF", "accent": "#3d5c3a", "accent2": "#C9A24E"},
        {"display": "Fraunces", "body": "Inter", "mono": "JetBrains Mono"},
        "mined from tradez.au live CSS 2026-09-03",
    ),
    (
        "gmux",
        "Forest Terminal",
        "sage-ivory + paper, forest/clay/honey, JetBrains-Mono-everything, 22px dot grid, dashed rules, segmented progress, ok/wait/alert/idle status-dot grammar. (from gmux.ai)",
        "mined from gmux.ai live CSS 2026-09-03",
        ["light", "terminal", "mono", "forest", "geometric"],
        {
            "bg": "#edefe6",
            "surface": "#fafbf3",
            "accent": "#2e6b40",
            "accent2": "#9c4a2b",
            "extra": ["#8a6414"],
        },
        {
            "display": "JetBrains Mono",
            "body": "JetBrains Mono",
            "mono": "JetBrains Mono",
        },
        "mined from gmux.ai live CSS 2026-09-03",
    ),
    (
        "volkus",
        "Humanist",
        "quiet black, warm brown (\u201cthe mixed skin tone\u201d), pale warm, Georgia + Courier New (system), and the eight-step skin-tone ramp as dividers/progress/rank plates. (from volkus.net)",
        "mined from volkus.net live CSS 2026-09-03",
        ["dark", "warm", "humanist", "system-fonts"],
        {
            "bg": "#0d0d0d",
            "accent": "#c27840",
            "accent2": "#f0c49a",
            "extra": ["#F5D5B8", "#2C1506"],
        },
        {"display": "Georgia", "mono": "Courier New"},
        "mined from volkus.net live CSS 2026-09-03",
    ),
    (
        "endispute",
        "Legal Brief",
        "cream + ink, gold rules (deep gold wherever text needs AA), Cormorant Garamond + IBM Plex Mono, radius ZERO (the only sharp light kit), certificate double-rule frames, [ bracketed ] chips, ledger rows. (from endispute.com.au)",
        "mined from endispute.com.au live CSS 2026-09-03",
        ["light", "editorial", "serif", "sharp", "legal"],
        {"bg": "#f4eedf", "ink": "#0a0a0a", "accent": "#d4a14a", "accent2": "#7d5a0e"},
        {"display": "Cormorant Garamond", "mono": "IBM Plex Mono"},
        "mined from endispute.com.au live CSS 2026-09-03",
    ),
    (
        "steddi",
        "Steddi \u2014 from your page",
        "warm near-black with plum hairlines, the red/maroon signal incl. 655nm laser, the fine 8px blueprint grid under a drifting red 96px major grid, KPI numerals gradient-clipped in JetBrains Mono, dimension-line dividers with ticks + arrowheads, callout panels with the 2px red datum edge, Class-2 laser sweep every 11s. Type: Sora \u00b7 Inter \u00b7 JBMono. (from qalarc.com/projects/steddi-overlap)",
        "mined from qalarc.com/projects/steddi-overlap live CSS 2026-09-03",
        ["dark", "blueprint", "technical", "mono", "laser-red"],
        {
            "bg": "#0f0b0d",
            "surface": "#191217",
            "ink": "#f1e8e6",
            "accent": "#d94a3d",
            "accent2": "#ff6a55",
            "extra": ["#7c2736", "#ff3b2f"],
        },
        {"display": "Sora", "body": "Inter", "mono": "JetBrains Mono"},
        "mined from qalarc.com/projects/steddi-overlap (styles.css?v=32) 2026-09-03",
    ),
]
for kid, kname, kdesc, kgroup, ktags, kpal, kfonts, klineage in RWF_KITS:
    mode = mode_of(kpal.get("bg")) if kpal else None
    entries.append(
        entry(
            name=kname,
            nativeId=kid,
            project="reps_with_friends",
            prefix="RW",
            category="theme-kit",
            useCases=None,
            source=RWF_SRC,
            palette=kpal,
            fonts=kfonts,
            mode=mode,
            tags=ktags,
            status="candidate",
            lineage=klineage,
            description=kdesc,
            registry="reps_readme",
            provenance=kgroup,
        )
    )

# ================================================================ write
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    json.dump(entries, fh, indent=1, ensure_ascii=False)

# ------------------------------------------------------------- report
from collections import Counter

print("TOTAL ENTRIES:", len(entries))
print("\nper registry:")
for k, v in Counter(e["registry"] for e in entries).most_common():
    print(f"  {k:14s} {v}")
print("\nper prefix:")
for k, v in sorted(Counter(e["prefix"] for e in entries).items()):
    print(f"  {k} {v}")
print("\nper category:")
for k, v in Counter(e["category"] for e in entries).most_common():
    print(f"  {k:12s} {v}")
print("\nper project:")
for k, v in Counter(e["project"] for e in entries).most_common():
    print(f"  {k:20s} {v}")
print("\nstatus:")
for k, v in Counter(e["status"] for e in entries).most_common():
    print(f"  {k} {v}")
