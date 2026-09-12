#!/usr/bin/env python3
"""
merge_catalog.py — findings/*.json  →  catalog/atlas.json

- merges all scan-agent findings files + registry imports
- dedupes by source path (registries win over scans; explicit mount wins over none)
- assigns stable codes  <PREFIX>-<NNN>   (hero-lab keeps axis codes like HL-C05)
- normalizes: mode (from bg luminance), palette hexes, era from mtime
- emits a QA report to stdout and catalog/qa_report.json

Re-runnable: existing atlas.json entries are kept (codes are stable); new
sources are appended. This is what scripts/update_catalog.py wraps.

Usage: python3 scripts/merge_catalog.py [--findings DIR] [--out catalog/atlas.json]
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # style-atlas/
FINDINGS_DIR = os.path.join(os.path.dirname(HERE), "findings")  # sibling findings/
OUT_PATH = os.path.join(HERE, "catalog", "atlas.json")
QA_PATH = os.path.join(HERE, "catalog", "qa_report.json")

CATEGORIES = {
    "website",
    "landing",
    "directory",
    "phone-app",
    "chat-app",
    "game",
    "dashboard",
    "theme-kit",
    "logo",
    "hero-module",
    "font-system",
    "email",
    "terminal",
    "poster",
    "business-card",
    "3d",
}


def hex_lum(h):
    h = (h or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h or ""):
        return None
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def norm_hex(c):
    if not c or not isinstance(c, str):
        return None
    c = c.strip().lower()
    m = re.fullmatch(r"#?([0-9a-f]{6}|[0-9a-f]{3})", c)
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(x * 2 for x in h)
    return "#" + h


def era_from_mtime(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m")
    except OSError:
        return None


def norm_palette(pal):
    if not isinstance(pal, dict):
        return {}
    out = {}
    for k in ("bg", "surface", "ink", "accent", "accent2"):
        v = norm_hex(pal.get(k))
        if v:
            out[k] = v
    extra = [norm_hex(x) for x in (pal.get("extra") or [])]
    extra = [x for x in extra if x]
    if extra:
        out["extra"] = extra[:8]
    return out


def infer_mode(pal, declared):
    if declared in ("dark", "light", "both"):
        return declared
    lum = hex_lum(pal.get("bg"))
    if lum is None:
        return "dark"
    return "dark" if lum < 0.35 else "light"


def hero_axis_code(prefix, native):
    """hero-lab codes keep their axis: c5/C5 -> HL-C05."""
    m = re.fullmatch(r"([ceshCESH])(\d+)", native or "")
    if m:
        return f"{prefix}-{m.group(1).upper()}{int(m.group(2)):02d}"
    return None


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:40] or "unnamed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", default=FINDINGS_DIR)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.findings, "*.json")))
    # registries last so they override scans on same source
    files.sort(key=lambda f: 0 if "_registries" not in os.path.basename(f) else 1)

    raw = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                for e in data:
                    e["_from"] = os.path.basename(f)
                raw.extend(data)
            else:
                print(f"  skip (not a list): {f}")
        except (json.JSONDecodeError, OSError) as ex:
            print(f"  ERROR reading {f}: {ex}")

    qa = {
        "files": {os.path.basename(f): 0 for f in files},
        "dropped": [],
        "no_palette": [],
        "bad_mount": [],
        "renamed_prefix": {},
    }

    def norm_native(nid):
        """Normalize a nativeId so registries and scans can match:
        'trade.sydney/v07_garden_organic' == 'v07_garden_organic' == 'V07_Garden_Organic'"""
        if not nid:
            return None
        s = str(nid).strip().lower()
        s = re.sub(r"^(trade\.sydney|tradez|x10)/", "", s)
        s = re.sub(r"\.(html?|css|svg|py|md|json)$", "", s)
        s = s.strip("/")
        return s or None

    def score(e):
        return (2 if e.get("registry") else 0) + (1 if e.get("mount") else 0)

    # Identity: (prefix, normalized nativeId) when a nativeId exists — keeps
    # same-file variants distinct (43 hero options live in 4 gallery files,
    # 6 logo families in one showcase). Falls back to the source path.
    by_key = {}
    order = []
    for e in raw:
        if not e.get("source") and not e.get("nativeId"):
            qa["dropped"].append({"name": e.get("name"), "why": "no source/nativeId"})
            continue
        e["_src"] = os.path.normpath(e.get("source") or "")
        nn = norm_native(e.get("nativeId"))
        if nn:
            key = ("id", (e.get("prefix") or "XX").upper(), nn)
        else:
            key = ("src", e["_src"])
        # same-file entries without nativeIds sharing a key (variant pages in
        # one file): keep both by extending the key with the name slug
        if key in by_key and by_key[key].get("_from") == e.get("_from") and not nn:
            base, n = key, 2
            while key in by_key and n < 60:
                key = (base[0], f"{base[1]}::{slugify(e.get('name'))}#{n}")
                n += 1
        if key in by_key:
            old = by_key[key]
            # keep the better record: registry-sourced > mounted > plain
            if score(e) > score(old):
                by_key[key] = e
            continue
        by_key[key] = e
        order.append(key)

    # existing catalog entries keep their codes — matched by identity
    existing = {}
    existing_by_ident = {}
    if os.path.exists(args.out):
        try:
            with open(args.out, "r", encoding="utf-8") as fh:
                existing = {x["code"]: x for x in json.load(fh).get("entries", [])}
            for c, x in existing.items():
                if x.get("ident"):
                    try:
                        existing_by_ident[tuple(json.loads(x["ident"]))] = c
                        continue
                    except json.JSONDecodeError:
                        pass
                nn = norm_native(x.get("nativeId"))
                ident = ("id", x.get("prefix", "XX"), nn) if nn else ("src", x.get("source", ""))
                existing_by_ident[ident] = c
        except (json.JSONDecodeError, OSError):
            existing = {}
    used_codes = set(existing)

    # group by prefix for numbering
    counters = {}
    for code in used_codes:
        m = re.match(r"^([A-Z]+)-", code)
        if m:
            counters[m.group(1)] = counters.get(m.group(1), 0) + 1

    entries = []
    for key in order:
        e = by_key[key]
        prefix = (e.get("prefix") or "XX").upper()
        if not re.fullmatch(r"[A-Z]{1,4}", prefix):
            qa["renamed_prefix"][e.get("name", "?")] = prefix
            prefix = re.sub(r"[^A-Z]", "", prefix)[:4] or "XX"

        category = e.get("category")
        if category not in CATEGORIES:
            category = category or "website"
            if category not in CATEGORIES:
                category = "website"

        nn_id = norm_native(e.get("nativeId"))
        base_ident = ("id", prefix, nn_id) if nn_id else ("src", e["_src"])
        code = existing_by_ident.get(base_ident) or existing_by_ident.get(key)
        if not code:
            code = hero_axis_code(prefix, e.get("nativeId"))
            if code and code in used_codes:
                code = None
        if not code:
            code = hero_axis_code(prefix, e.get("nativeId"))
            if code and code in used_codes:
                code = None
        if not code:
            n = counters.get(prefix, 0) + 1
            while f"{prefix}-{n:03d}" in used_codes:
                n += 1
            code = f"{prefix}-{n:03d}"
            counters[prefix] = n
        used_codes.add(code)

        pal = norm_palette(e.get("palette"))
        mount = e.get("mount")
        if mount and isinstance(mount, dict):
            if not (mount.get("dir") and mount.get("file")):
                mount = None
            else:
                entry_path = os.path.join(mount["dir"], mount["file"])
                if not os.path.isfile(entry_path):
                    qa["bad_mount"].append({"code": code, "path": entry_path})
                    mount = None

        src_path = e["_src"]
        if os.path.isdir(src_path):  # dir sources (Next.js farms): dir mtime
            era = era_from_mtime(src_path)
        elif os.path.isfile(src_path):
            era = era_from_mtime(src_path)
        else:
            era = e.get("era")
        if not pal:
            qa["no_palette"].append(code)

        entry = {
            "code": code,
            "ident": json.dumps(list(key)),
            "name": e.get("name") or slugify(e.get("nativeId")) or code,
            "nativeId": e.get("nativeId"),
            "project": e.get("project") or "unknown",
            "prefix": prefix,
            "category": category,
            "useCases": [u for u in (e.get("useCases") or []) if u][:6],
            "source": e["_src"],
            "mount": mount,
            "externalUrl": e.get("externalUrl"),
            "palette": pal,
            "fonts": {k: v for k, v in (e.get("fonts") or {}).items() if v},
            "mode": infer_mode(pal, e.get("mode")),
            "tags": sorted({t.lower() for t in (e.get("tags") or []) if t})[:12],
            "era": era,
            "status": e.get("status")
            if e.get("status") in ("candidate", "final", "rejected", "shipped")
            else "candidate",
            "lineage": e.get("lineage"),
            "signature": e.get("signature"),
            "description": (e.get("description") or "").strip()[:400],
        }
        if e.get("registry"):
            entry["registry"] = e["registry"]
        entries.append(entry)
        qa["files"][e.get("_from", "?")] = qa["files"].get(e.get("_from", "?"), 0) + 1

    entries.sort(key=lambda x: x["code"])
    out = {
        "meta": {
            "name": "Style Atlas",
            "generated": datetime.now().isoformat(timespec="seconds"),
            "count": len(entries),
            "projects": sorted({x["project"] for x in entries}),
            "categories": sorted({x["category"] for x in entries}),
        },
        "entries": entries,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    with open(QA_PATH, "w", encoding="utf-8") as f:
        json.dump(qa, f, indent=1, ensure_ascii=False)

    print(
        f"atlas.json: {len(entries)} entries "
        f"({len(out['meta']['projects'])} projects, "
        f"{len(out['meta']['categories'])} categories)"
    )
    print(
        f"QA: no-palette={len(qa['no_palette'])} bad-mount={len(qa['bad_mount'])} "
        f"dropped={len(qa['dropped'])}"
    )
    for b in qa["bad_mount"][:10]:
        print("  bad mount:", b["code"], b["path"])


if __name__ == "__main__":
    main()
