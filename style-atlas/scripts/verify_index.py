#!/usr/bin/env python3
"""
verify_index.py — health check for the Style Atlas index (atlas.json).

Checks:
  1. structural: unique codes, valid categories, prefix matches code, idents
  2. referential: mount files exist, thumbs exist, sources exist
  3. search/filter simulation: category/mode/project/tag/search hits + timing
  4. stability precondition: every entry has an ident (re-merge safe)

Exit code 1 on any FAIL. Usage: python3 scripts/verify_index.py
"""

import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(HERE, "catalog", "atlas.json")
THUMBS = os.path.join(HERE, "thumbs")

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
MODES = {"dark", "light", "both"}
STATUSES = {"candidate", "final", "rejected", "shipped"}

fails = []
warns = []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def main():
    d = json.load(open(CATALOG, encoding="utf-8"))
    es = d["entries"]
    print(
        f"catalog: {len(es)} entries, {len(d['meta']['projects'])} projects, "
        f"{len(d['meta']['categories'])} categories\n"
    )

    print("1) STRUCTURE")
    codes = [e["code"] for e in es]
    check("unique codes", len(codes) == len(set(codes)), f"{len(codes)} codes")
    bad_cat = [e["code"] for e in es if e["category"] not in CATEGORIES]
    check("valid categories", not bad_cat, ",".join(bad_cat[:5]))
    bad_mode = [e["code"] for e in es if e.get("mode") not in MODES]
    check("valid modes", not bad_mode, ",".join(bad_mode[:5]))
    bad_status = [e["code"] for e in es if e.get("status") not in STATUSES]
    check("valid statuses", not bad_status, ",".join(bad_status[:5]))
    bad_prefix = [
        e["code"] for e in es if not e["code"].startswith(e.get("prefix", "?") + "-")
    ]
    check("code starts with prefix", not bad_prefix, ",".join(bad_prefix[:5]))
    no_ident = [e["code"] for e in es if not e.get("ident")]
    check(
        "identity keys present (re-merge safe)",
        not no_ident,
        f"{len(no_ident)} missing",
    )
    no_name = [e["code"] for e in es if not (e.get("name") or "").strip()]
    check("names present", not no_name, ",".join(no_name[:5]))
    idents = [json.dumps(e.get("ident")) for e in es]
    check("unique identity keys", len(idents) == len(set(idents)))

    print("\n2) REFERENTIAL")
    mounts = [e for e in es if e.get("mount")]
    bad_mounts = [
        e["code"]
        for e in mounts
        if not os.path.isfile(os.path.join(e["mount"]["dir"], e["mount"]["file"]))
    ]
    check(
        f"mount files exist ({len(mounts)} mounted)",
        not bad_mounts,
        ",".join(bad_mounts[:8]),
    )
    thumbs_missing = [
        e["code"]
        for e in es
        if not os.path.isfile(os.path.join(THUMBS, e["code"] + ".png"))
    ]
    check(
        "thumbnails exist for every entry",
        not thumbs_missing,
        f"{len(thumbs_missing)} missing: " + ",".join(thumbs_missing[:8]),
    )
    src_missing = [
        e["code"] for e in es if e.get("source") and not os.path.exists(e["source"])
    ]
    check(
        "source paths exist",
        not src_missing,
        f"{len(src_missing)} missing: " + ",".join(src_missing[:8]),
    )
    pal_less = [e["code"] for e in es if not e.get("palette")]
    if pal_less:
        warns.append(f"{len(pal_less)} entries without palette (swatch defaults used)")

    print("\n3) SEARCH / FILTER SIMULATION (same logic as hub app.js)")

    def sim_filter(category=None, mode=None, project=None, tag=None, search=""):
        t0 = time.perf_counter()
        out = [
            e
            for e in es
            if (not category or e["category"] == category)
            and (not mode or e["mode"] == mode)
            and (not project or e["project"] == project)
            and (not tag or tag in (e.get("tags") or []))
            and (
                not search
                or search.lower()
                in " ".join(
                    [
                        e["code"],
                        e.get("name", ""),
                        e.get("project", ""),
                        e.get("description", ""),
                        " ".join(e.get("tags") or []),
                        json.dumps(e.get("palette") or {}),
                    ]
                ).lower()
            )
        ]
        return out, (time.perf_counter() - t0) * 1000

    for label, kw in [
        ("category=website", dict(category="website")),
        ("mode=dark", dict(mode="dark")),
        ("project=gmux.ai", dict(project="gmux.ai")),
        ("tag=neon", dict(tag="neon")),
        ('search="gold"', dict(search="gold")),
        ('search="TZ-"', dict(search="TZ-")),
        ("combined dark+website", dict(mode="dark", category="website")),
    ]:
        out, ms = sim_filter(**kw)
        check(
            f"filter {label} → {len(out)} results ({ms:.1f}ms)",
            len(out) > 0 and ms < 100,
        )

    # hue families computable
    def hue(hexv):
        h = (hexv or "").lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", h or ""):
            return "neutral"
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
        mx, mn = max(r, g, b), min(r, g, b)
        if mx == mn:
            return "neutral"
        dd = mx - mn
        hh = 0
        if mx == r:
            hh = ((g - b) / dd) % 6
        elif mx == g:
            hh = (b - r) / dd + 2
        else:
            hh = (r - g) / dd + 4
        hh *= 60
        if hh < 0:
            hh += 360
        if hh < 15 or hh >= 345:
            return "red"
        for name, lo, hi in [
            ("orange", 15, 40),
            ("amber", 40, 65),
            ("yellow", 65, 80),
            ("green", 80, 160),
            ("teal", 160, 195),
            ("cyan", 195, 215),
            ("blue", 215, 255),
            ("indigo", 255, 285),
            ("purple", 285, 320),
            ("pink", 320, 345),
        ]:
            if lo <= hh < hi:
                return name
        return "neutral"

    hues = {}
    for e in es:
        p = e.get("palette") or {}
        hues[hue(p.get("accent") or p.get("accent2") or p.get("bg"))] = (
            hues.get(hue(p.get("accent") or p.get("accent2") or p.get("bg")), 0) + 1
        )
    check(
        "hue families computed for all entries",
        sum(hues.values()) == len(es),
        str(hues),
    )

    print("\n4) COVERAGE")
    per_prefix = {}
    for e in es:
        per_prefix[e["prefix"]] = per_prefix.get(e["prefix"], 0) + 1
    expect_min = {
        "TZ": 20,
        "TX": 12,
        "XB": 7,
        "GM": 16,
        "GT": 10,
        "GS": 4,
        "ED": 18,
        "QA": 18,
        "RW": 26,
        "TP": 25,
        "HL": 43,
        "CR": 10,
        "SA": 10,
        "GO": 6,
        "PH": 8,
        "MI": 10,
        "GL": 5,
        "TR": 3,
    }
    for p, n in expect_min.items():
        got = per_prefix.get(p, 0)
        check(f"prefix {p} coverage ≥{n}", got >= n, f"got {got}")

    for w in warns:
        print(f"  [warn] {w}")
    print()
    if fails:
        print(f"RESULT: {len(fails)} FAILURES: " + "; ".join(fails))
        sys.exit(1)
    print(f"RESULT: ALL CHECKS PASSED — index is healthy ({len(es)} entries)")


if __name__ == "__main__":
    main()
