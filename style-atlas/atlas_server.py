#!/usr/bin/env python3
"""
STYLE ATLAS — every UI style/theme ever built across all qalarc projects,
showcased under one port. Evolved from style_chooser_server.py.

Run:   python3 atlas_server.py [--port 1340]
Open:  http://localhost:1340/

Routes:
  /                    hub UI (gallery, filters, keyboard nav, chat)
  /projects            landing page for the library
  /<CODE>/             LIVE mounted preview of that style (path-remapped)
  /swatch/<CODE>/      generated swatch/mock preview (theme-kits, tokens, logos)
  /thumbs/<CODE>.png   screenshot thumbnail
  /api/catalog         the full atlas.json
  /api/picks           GET/POST starred shortlist (persisted)
  /api/chat            POST -> Ollama glm-4.7-flash:32k w/ catalog-aware
                       system prompt; rule-based fallback if Ollama down
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(HERE, "catalog", "atlas.json")
PICKS_PATH = os.path.join(HERE, "catalog", "picks.json")
HUB_DIR = os.path.join(HERE, "hub")
THUMBS_DIR = os.path.join(HERE, "thumbs")
STATIC_DIRS = {"hub": HUB_DIR, "thumbs": THUMBS_DIR}

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
# glm-4.7-flash:32k loops on this box (verified 2026-09-12) — coder-7b is the
# fast, reliable concierge; override with ATLAS_MODEL=<name> to try others.
CHAT_MODEL = os.environ.get("ATLAS_MODEL", "qwen2.5-coder:7b")

import mimetypes

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def load_catalog():
    if not os.path.exists(CATALOG_PATH):
        return {"entries": [], "meta": {"generated": None, "count": 0}}
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


CATALOG = load_catalog()
ENTRIES = CATALOG.get("entries", [])
BY_CODE = {e["code"]: e for e in ENTRIES}

# mounts: CODE -> {dir,file,data,assets,shared,label}
MOUNTS = {}
for e in ENTRIES:
    m = e.get("mount")
    if m and m.get("dir") and m.get("file"):
        MOUNTS[e["code"]] = {
            "dir": m["dir"],
            "file": m["file"],
            "data": m.get("data"),
            "assets": m.get("assets"),
            "shared": m.get("shared"),
            "label": e.get("name", e["code"]),
        }


def safe_join(base, *parts):
    """Join and verify the result stays under base."""
    path = os.path.abspath(os.path.join(base, *[p for p in parts if p]))
    base = os.path.abspath(base)
    if path != base and not path.startswith(base + os.sep):
        return None
    return path


# ---------------------------------------------------------------------------
# Path resolution engine (evolved from style_chooser_server.py resolve())
# ---------------------------------------------------------------------------
# Entries are served at one path level: /<CODE>/  — so pages that use
# ../shared/foo.css resolve to /shared/foo.css (global fallback chain), and
# absolute /assets/x, /data/x requests carry a Referer telling us which
# mount's iframe asked, so we try that mount's dirs before global fallbacks.

GLOBAL_SHARED_CANDIDATES = [
    os.path.expanduser("~/projects/trade.sydney/brand_tradez_au/samples/v2/shared"),
    os.path.expanduser("~/projects/trade.sydney/brand_tradez_au/assets"),
    os.path.expanduser("~/projects/trade.sydney/brand_x10_au/assets"),
]
GLOBAL_ASSET_CANDIDATES = [
    os.path.expanduser("~/projects/trade.sydney/brand_tradez_au/assets"),
    os.path.expanduser("~/projects/trade.sydney/brand_x10_au/assets"),
    os.path.expanduser("~/projects/tradez_x10_biz/public/assets"),
]
GLOBAL_DATA_CANDIDATES = [
    os.path.expanduser("~/projects/trade.sydney/brand_tradez_au/data"),
]


def referer_code(headers):
    ref = headers.get("Referer", "")
    m = re.match(r"https?://[^/]+/([A-Z0-9]+(?:-[A-Z0-9]+)*)/", ref)
    if m and m.group(1) in MOUNTS:
        return m.group(1)
    return None


def try_first_existing(candidates, rel):
    for base in candidates:
        if not base:
            continue
        p = safe_join(base, rel)
        if p and os.path.isfile(p):
            return p
    return None


def resolve(path):
    """Map a URL path to a local file, or None."""
    # --- mounted entry space: /<CODE>/... ---
    m = re.match(r"^/([A-Z0-9]+(?:-[A-Z0-9]+)*)(/.*)?$", path)
    if m and m.group(1) in MOUNTS:
        code, rest = m.group(1), (m.group(2) or "/")
        mount = MOUNTS[code]
        if rest in ("/", ""):
            p = safe_join(mount["dir"], mount["file"])
            return p if p and os.path.isfile(p) else None
        rel = rest.lstrip("/")
        # explicit namespaces
        for ns, key, cands in (
            ("data/", "data", [mount.get("data")] + GLOBAL_DATA_CANDIDATES),
            ("assets/", "assets", [mount.get("assets")] + GLOBAL_ASSET_CANDIDATES),
            ("shared/", "shared", [mount.get("shared")] + GLOBAL_SHARED_CANDIDATES),
        ):
            if rel.startswith(ns):
                p = try_first_existing(cands, rel[len(ns) :])
                if p:
                    return p
        # sibling file inside the entry dir
        p = safe_join(mount["dir"], rel)
        if p and os.path.isfile(p):
            return p
        # ../shared style requests arrive here as /shared/... (see below)
        return None

    # --- global namespaces (/assets/, /data/, /shared/) are handled in the
    #     request handler, which has Referer headers for mount preference ---
    if path.startswith(("/assets/", "/data/", "/shared/")):
        return None

    # --- hub static files ---
    if path.startswith("/thumbs/"):
        p = safe_join(THUMBS_DIR, path[len("/thumbs/") :])
        return p if p and os.path.isfile(p) else None
    p = safe_join(HUB_DIR, path.lstrip("/"))
    return p if p and os.path.isfile(p) else None


# ---------------------------------------------------------------------------
# Swatch pages — generated previews for token-only entries (theme kits,
# palettes, logos). Renders a mini-UI in that style's tokens.
# ---------------------------------------------------------------------------


def hex_lum(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return 0.5

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


SWATCH_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{code} — {name}</title>
<style>
  :root {{
    --bg: {bg}; --surface: {surface}; --ink: {ink};
    --accent: {accent}; --accent2: {accent2};
    --muted: {muted}; --line: {line};
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:var(--bg); color:var(--ink);
         font-family:{body}, system-ui, sans-serif; padding:0; }}
  .wrap {{ max-width:880px; margin:0 auto; padding:56px 32px; }}
  .kicker {{ font-family:{mono}, monospace; font-size:12px; letter-spacing:2px;
             color:var(--accent); text-transform:uppercase; margin-bottom:14px; }}
  h1 {{ font-family:{display}, Georgia, serif; font-size:52px; line-height:1.05;
        margin-bottom:18px; color:var(--ink); }}
  p.lead {{ color:var(--muted); font-size:17px; max-width:56ch; margin-bottom:32px; }}
  .card {{ background:var(--surface); border:1px solid var(--line);
           border-radius:{radius}px; padding:26px; margin-bottom:22px; }}
  .row {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
  .btn {{ background:var(--accent); color:{on_accent}; border:none; padding:13px 26px;
          border-radius:{radius}px; font-weight:700; font-size:15px;
          font-family:{body}, system-ui; cursor:pointer; }}
  .btn.ghost {{ background:transparent; color:var(--accent);
                border:1.5px solid var(--accent); }}
  .chat {{ display:flex; flex-direction:column; gap:10px; }}
  .bubble {{ max-width:70%; padding:12px 16px; border-radius:{radius}px; font-size:15px; }}
  .bubble.me {{ align-self:flex-end; background:var(--accent); color:{on_accent}; }}
  .bubble.them {{ align-self:flex-start; background:var(--surface);
                  border:1px solid var(--line); }}
  .stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
  .stat {{ background:var(--surface); border:1px solid var(--line);
           border-radius:{radius}px; padding:18px; }}
  .stat b {{ display:block; font-size:30px; font-family:{display}, Georgia, serif;
             color:var(--accent); }}
  .stat span {{ color:var(--muted); font-size:13px; }}
  .strip {{ display:flex; height:64px; border-radius:{radius}px; overflow:hidden;
            border:1px solid var(--line); margin-bottom:26px; }}
  .strip div {{ flex:1; }}
  .mono {{ font-family:{mono}, monospace; font-size:12px; color:var(--muted); }}
  .badge {{ display:inline-block; font-family:{mono}, monospace; font-size:11px;
            border:1px solid var(--accent); color:var(--accent); border-radius:99px;
            padding:4px 12px; margin:2px 4px 2px 0; }}
</style></head>
<body><div class="wrap">
  <div class="kicker">{project} · {category} · {code}</div>
  <h1>{name}</h1>
  <p class="lead">{desc}</p>
  <div class="strip">{swatches}</div>
  <div class="row" style="margin-bottom:30px">
    <button class="btn">Primary action</button>
    <button class="btn ghost">Secondary</button>
    <span class="mono">{fontline}</span>
  </div>
  <div class="card"><div class="chat">
    <div class="bubble them">This style rendered from extracted tokens.</div>
    <div class="bubble me">Palette, type and radii are real values.</div>
    <div class="bubble them">Used as reference {usecase}</div>
  </div></div>
  <div class="stats">
    <div class="stat"><b>24</b><span>STAT CARDS</span></div>
    <div class="stat"><b>{mode}</b><span>MODE</span></div>
    <div class="stat"><b>{ncolors}</b><span>COLORS</span></div>
  </div>
  <div style="margin-top:26px">{badges}</div>
</div></body></html>"""

LOGO_SWATCH_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{code} — {name}</title>
<style>
  body {{ margin:0; display:grid; place-items:center; min-height:100vh;
         background:{bg}; }}
  .logo {{ max-width:min(560px,70vw); max-height:60vh; }}
  .logo svg {{ max-width:100%; max-height:60vh; }}
  .label {{ position:fixed; bottom:16px; left:0; right:0; text-align:center;
            font-family:monospace; font-size:12px; color:{ink}; opacity:.7; }}
</style></head>
<body><div class="logo">{svg}</div>
<div class="label">{code} · {name} · {project}</div></body></html>"""


def build_logo_swatch(code):
    e = BY_CODE.get(code)
    if not e:
        return None, None
    src = e.get("source", "")
    pal = e.get("palette") or {}
    bg = pal.get("bg") or "#F4F1EA"
    ink = pal.get("ink") or "#1A1A1A"
    svg = ""
    try:
        with open(src, "r", encoding="utf-8") as f:
            svg = f.read(400_000)
        if "<svg" not in svg:
            svg = f'<img src="{src}" alt="logo">'  # fallback for non-svg sources
    except OSError:
        svg = "<p style='color:#888'>source file unreadable</p>"
    html = LOGO_SWATCH_TEMPLATE.format(
        code=code,
        name=e.get("name", code),
        project=e.get("project", ""),
        bg=bg,
        ink=ink,
        svg=svg,
    )
    return "text/html", html


def build_swatch(code):
    e = BY_CODE.get(code)
    if not e:
        return None, None
    pal = e.get("palette") or {}
    fonts = e.get("fonts") or {}
    bg = pal.get("bg") or "#101418"
    surface = pal.get("surface") or "#1A2128"
    ink = pal.get("ink") or ("#E8ECEA" if hex_lum(bg) < 0.35 else "#16191C")
    accent = pal.get("accent") or "#7FB069"
    accent2 = pal.get("accent2") or accent
    muted = ink + "99" if ink.startswith("#") else ink
    line = (ink if ink.startswith("#") else "#88888") + "2e"  # 18% border
    on_accent = "#0B0E0B" if hex_lum(accent) > 0.45 else "#FFFFFF"
    radius = 14 if "rounded" in (e.get("tags") or []) else 8
    all_colors = [
        c
        for c in [
            pal.get("bg"),
            pal.get("surface"),
            pal.get("ink"),
            pal.get("accent"),
            pal.get("accent2"),
        ]
        if c
    ]
    all_colors += pal.get("extra") or []
    swatches = "".join(
        f'<div style="background:{c}" title="{c}"></div>' for c in all_colors[:8]
    )
    fontline = " · ".join(f"{k}: {v}" for k, v in fonts.items() if v) or "system fonts"
    badges = "".join(
        f'<span class="badge">{t}</span>' for t in (e.get("tags") or [])[:10]
    )
    # category-appropriate copy
    usecase = {
        "chat-app": "for chat interfaces",
        "game": "for game UIs",
        "dashboard": "for dashboards",
        "logo": "for brand marks",
    }.get(e.get("category"), "across interfaces")
    html = SWATCH_TEMPLATE.format(
        code=code,
        name=e.get("name", code),
        project=e.get("project", ""),
        category=e.get("category", ""),
        desc=e.get("description", ""),
        bg=bg,
        surface=surface,
        ink=ink,
        accent=accent,
        accent2=accent2,
        muted=muted,
        line=line,
        on_accent=on_accent,
        radius=radius,
        swatches=swatches,
        fontline=fontline,
        badges=badges,
        mode=e.get("mode", "?"),
        ncolors=len(all_colors),
        usecase=usecase,
        display=fonts.get("display") or "Georgia",
        body=fonts.get("body") or "system-ui",
        mono=fonts.get("mono") or "monospace",
    )
    return "text/html", html


# ---------------------------------------------------------------------------
# Chat: Ollama proxy with catalog-aware prompt + rule-based fallback
# ---------------------------------------------------------------------------


def compact_catalog():
    lines = []
    for e in ENTRIES:
        lines.append("|".join(str(x) for x in [
            e["code"], e.get("name", "")[:28], e.get("project", ""),
            e.get("category", ""), e.get("mode", ""),
            ",".join((e.get("tags") or [])[:3]),
        ]))
    return "\n".join(lines)


def chat_system_prompt():
    return (
        "You are the Atlas Concierge for a design style catalog. Help the user "
        "choose styles by answering questions about colors, typography, mood and "
        "use-cases.\n\n"
        "CATALOG (code|name|project|category|mode|tags):\n" + compact_catalog()
        + "\n\n"
        "RULES:\n"
        "1. Be brief (2-4 sentences). Cite entries by code.\n"
        "2. When recommending or narrowing styles, ALWAYS finish with a json "
        "filter block. Allowed keys: category (one of the catalog categories), "
        "project (exact project name from catalog), mode (ONLY 'dark', 'light' "
        "or 'both'), tags (list), search (substring), codes (list of catalog "
        "codes you recommend). Never invent values.\n"
        "3. Example:\n```json\n{\"filter\": {\"mode\": \"dark\", "
        "\"codes\": [\"TZ-011\", \"ED-019\"]}}\n```\n"
        "4. Output English only.\n"
    )

def ollama_chat(message, history):
    payload = {
        "model": CHAT_MODEL,
        "stream": False,
        "options": {"temperature": 0.2},
        "messages": [{"role": "system", "content": chat_system_prompt()}]
        + [
            {"role": h.get("role", "user"), "content": h.get("content", "")}
            for h in (history or [])[-8:]
        ]
        + [{"role": "user", "content": message}],
    }
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=150) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("message", {}).get("content", "")


COLOR_WORDS = {
    "red": ["red"],
    "orange": ["orange"],
    "amber": ["amber", "gold", "yellow"],
    "yellow": ["yellow", "gold"],
    "green": ["green", "gumleaf"],
    "teal": ["teal"],
    "cyan": ["cyan"],
    "blue": ["harbour", "blue"],
    "indigo": ["indigo", "navy"],
    "purple": ["purple", "violet"],
    "pink": ["pink"],
    "neutral": ["neutral", "slate", "cream", "paper"],
    "dark": [],
    "light": [],
    "neon": ["neon"],
    "warm": ["warm", "sunset"],
    "cool": ["cool", "harbour"],
}


def rule_chat(message):
    """Deterministic concierge — the default. Understands categories, modes,
    projects, color words and 'show me X' style asks."""
    msg = message.lower()
    filt = {}

    for w in ("dark", "light"):
        if w in msg:
            filt["mode"] = w
            break
    for cat in ("website", "landing", "directory", "phone-app", "chat-app",
                "game", "dashboard", "theme-kit", "logo", "hero-module",
                "font-system", "email", "terminal", "poster", "business-card"):
        if cat in msg or cat.replace("-", " ") in msg:
            filt["category"] = cat
            break
    if not filt.get("category") and "chat" in msg:
        filt["category"] = "chat-app"
    if not filt.get("category") and ("logo" in msg or "brand mark" in msg):
        filt["category"] = "logo"

    proj_words = {
        "tradez": "tradez", "x10": "x10", "gmux": "gmux", "endispute": "endispute",
        "qalarc": "qalarc", "reps": "reps", "airtree": "airtree", "hero": "hero-lab",
        "crypto": "qal-coin", "coin": "qal-coin", "trading": "qal-coin",
        "sahha": "sahha", "health": "sahha", "goetica": "goetica",
        "phone game": "phone games", "bella": "bella",
    }
    for w, proj in proj_words.items():
        if w in msg:
            filt["project"] = proj
            break

    for w in ("gold", "green", "blue", "navy", "neon", "red", "purple", "teal",
              "warm", "cool", "pink", "orange", "violet", "cream", "serif",
              "mono", "minimal", "brutalist", "glass", "retro", "organic",
              "editorial", "premium", "luxury"):
        if w in msg:
            filt["search"] = w
            break

    codes = []
    if filt:
        for e in ENTRIES:
            ok = True
            if filt.get("mode") and e.get("mode") != filt["mode"]:
                ok = False
            if filt.get("category") and e.get("category") != filt["category"]:
                ok = False
            if filt.get("project") and filt["project"].lower() not in e.get("project", "").lower():
                ok = False
            if filt.get("search"):
                hay = " ".join([e.get("name", ""), " ".join(e.get("tags") or []),
                                str(e.get("palette")), str(e.get("fonts"))]).lower()
                if filt["search"] not in hay:
                    ok = False
            if ok:
                codes.append(e["code"])
            if len(codes) >= 16:
                break
    head = ("Showing " + str(len(codes)) + " matching styles." if codes else
            "No exact match — try: 'dark gold', 'chat app', 'logo concepts', "
            "'gmux dark', 'game UIs'.")
    tip = ("\nClick the filter chip to apply, then cycle with arrow keys."
           if codes else "")
    return head + tip, {**filt, **({"codes": codes} if codes else {})}


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "StyleAtlas/1.0"

    def log_message(self, format, *args):  # noqa: A002 — matches base signature
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), format % args))

    # ---- helpers ----
    def send_bytes(self, code, ctype, body, cache=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cache is None:
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, cache=None):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self.send_bytes(404, "text/plain", b"not found")
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_bytes(200, ctype, body, cache)

    def send_json(self, obj, code=200):
        self.send_bytes(
            code,
            "application/json",
            json.dumps(obj, ensure_ascii=False).encode("utf-8"),
        )

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    # ---- routes ----
    def do_GET(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]

        if path in ("/", "/index.html"):
            self.send_file(os.path.join(HUB_DIR, "index.html"))
            return
        if path in ("/projects", "/projects.html", "/projects/"):
            self.send_file(os.path.join(HUB_DIR, "projects.html"))
            return

        if path == "/api/catalog":
            self.send_json(CATALOG)
            return
        if path == "/api/picks":
            self.send_json(load_picks())
            return
        if path == "/api/ratings":
            self.send_json({"ratings": load_ratings()})
            return

        # swatch previews
        m = re.match(r"^/swatch/([A-Za-z0-9-]+)/?$", path)
        if m:
            code = m.group(1)
            e = BY_CODE.get(code)
            if not e:
                self.send_bytes(404, "text/plain", b"unknown code")
                return
            if e.get("category") == "logo" and e.get("source", "").endswith(".svg"):
                ctype, html = build_logo_swatch(code)
            else:
                ctype, html = build_swatch(code)
            if html:
                self.send_bytes(200, ctype, html.encode("utf-8"))
            else:
                self.send_bytes(500, "text/plain", b"swatch build failed")
            return

        # global namespaces with Referer-aware mount preference
        if path.startswith(("/assets/", "/data/", "/shared/")):
            ns = path.split("/")[1]
            rel = path[len("/" + ns + "/") :]
            code = referer_code(self.headers)
            cands = []
            if code:
                mt = MOUNTS[code]
                cands.append(mt.get(ns if ns != "shared" else "shared"))
            cands += {
                "assets": GLOBAL_ASSET_CANDIDATES,
                "data": GLOBAL_DATA_CANDIDATES,
                "shared": GLOBAL_SHARED_CANDIDATES,
            }[ns]
            p = try_first_existing(cands, rel)
            if p:
                self.send_file(p)
            else:
                self.send_bytes(404, "text/plain", b"not found")
            return

        # mounted live previews: /<CODE>/...
        m = re.match(r"^/([A-Z0-9]+(?:-[A-Z0-9]+)*)(/.*)?$", path)
        if m and m.group(1) in MOUNTS:
            p = resolve(path)
            if p:
                self.send_file(p)
            else:
                self.send_bytes(
                    404,
                    "text/plain",
                    ("missing asset for %s: %s" % (m.group(1), path)).encode(),
                )
            return

        # everything else: hub static / thumbs
        p = resolve(path)
        if p:
            self.send_file(
                p, cache="public, max-age=60" if "/thumbs/" in path else None
            )
        else:
            self.send_bytes(404, "text/plain", b"not found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/picks":
            body = self.read_body()
            action, code = body.get("action"), body.get("code")
            picks = load_picks()
            lst = picks.setdefault("picks", [])
            lst[:] = [x for x in lst if x.get("code") != code]
            if action in ("add", "note"):
                lst.insert(
                    0,
                    {
                        "code": code,
                        "note": body.get("note", ""),
                        "ts": int(time.time()),
                    },
                )
            save_picks(picks)
            self.send_json(picks)
            return
        if path == "/api/rate":
            body = self.read_body()
            code = body.get("code", "")
            stars = body.get("stars")
            if code in BY_CODE and isinstance(stars, int) and 1 <= stars <= 5:
                r = load_ratings()
                x = r.setdefault(code, {"s": 0, "c": 0})
                x["s"] += stars
                x["c"] += 1
                save_ratings(r)
                self.send_json({"ratings": r, "your": {"code": code, "stars": stars}})
            else:
                self.send_json({"error": "bad vote"}, code=400)
            return
        if path == "/api/chat":
            body = self.read_body()
            message = body.get("message", "")
            history = body.get("history", [])
            if not message.strip():
                self.send_json({"reply": "Ask me about styles, colors or use-cases."})
                return
            # deterministic matcher is the default concierge (instant,
            # reliable); set ATLAS_MODEL to route through local Ollama instead
            if os.environ.get("ATLAS_MODEL"):
                try:
                    reply = ollama_chat(message, history)
                    filt = extract_filter(reply)
                    self.send_json({"reply": strip_filter_block(reply),
                                    "filter": filt, "model": CHAT_MODEL})
                    return
                except Exception:  # noqa: BLE001 — fall back below
                    pass
            reply, filt = rule_chat(message)
            self.send_json({"reply": reply, "filter": filt, "matcher": "builtin"})
            return
        self.send_bytes(404, "text/plain", b"not found")


ALLOWED_MODES = {"dark", "light", "both"}

def sanitize_filter(f):
    if not isinstance(f, dict):
        return None
    out = {}
    if isinstance(f.get("category"), str):
        for e in ENTRIES:
            if e.get("category") == f["category"]:
                out["category"] = f["category"]
                break
    if isinstance(f.get("project"), str):
        for e in ENTRIES:
            if e.get("project") == f["project"]:
                out["project"] = f["project"]
                break
    if f.get("mode") in ALLOWED_MODES:
        out["mode"] = f["mode"]
    if isinstance(f.get("tags"), list):
        tags = [str(t).lower() for t in f["tags"] if t][:5]
        if tags:
            out["tags"] = tags
    if isinstance(f.get("search"), str) and f["search"].strip():
        out["search"] = f["search"].strip()[:60]
    codes = [c for c in (f.get("codes") or [])
             if isinstance(c, str) and c in BY_CODE][:24]
    if codes:
        out["codes"] = codes
    return out or None

def extract_filter(reply):
    m = re.search(r"```json\s*(\{.*?\})\s*```", reply, re.S)
    obj = None
    if m:
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            obj = None
    if obj is None:  # try to salvage a bare filter object
        m = re.search(r'\{\s*\"filter\"\s*:.*\}', reply, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                obj = None
    if obj is None:  # last resort: salvage a codes list
        m = re.search(r'\"codes\"\s*:\s*\[([^\]]*)\]', reply)
        if m:
            codes = re.findall(r'[A-Z]{1,4}-[A-Z0-9]{1,4}\d{1,3}', m.group(1))
            codes = [c for c in codes if c in BY_CODE][:12]
            if codes:
                return {"codes": codes}
        return None
    f = obj.get("filter", obj)
    return sanitize_filter(f)

def strip_filter_block(reply):
    return re.sub(r"```json\s*\{.*?\}\s*```", "", reply, flags=re.S).strip()


# ---------------------------------------------------------------------------
# picks persistence
# ---------------------------------------------------------------------------


def load_picks():
    if os.path.exists(PICKS_PATH):
        try:
            with open(PICKS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"picks": []}


def save_picks(picks):
    os.makedirs(os.path.dirname(PICKS_PATH), exist_ok=True)
    with open(PICKS_PATH, "w", encoding="utf-8") as f:
        json.dump(picks, f, indent=2, ensure_ascii=False)


RATINGS_PATH = os.path.join(HERE, "catalog", "ratings.json")

def load_ratings():
    if os.path.exists(RATINGS_PATH):
        try:
            with open(RATINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {}

def save_ratings(r):
    os.makedirs(os.path.dirname(RATINGS_PATH), exist_ok=True)
    with open(RATINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1)

# ---------------------------------------------------------------------------
# startup
# ---------------------------------------------------------------------------


def sanity_check():
    ok = miss = 0
    for code, mt in MOUNTS.items():
        entry = safe_join(mt["dir"], mt["file"])
        if entry and os.path.isfile(entry):
            ok += 1
        else:
            miss += 1
            print("  MISSING %-9s %s" % (code, os.path.join(mt["dir"], mt["file"])))
    print("mounts: %d OK, %d MISSING" % (ok, miss))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=1340)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    print("STYLE ATLAS — %d entries, %d live mounts" % (len(ENTRIES), len(MOUNTS)))
    if ENTRIES:
        sanity_check()
    else:
        print("catalog empty — run scripts/merge_catalog.py after scans finish")
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print("serving hub at http://localhost:%d/  (Ctrl-C to stop)" % args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
