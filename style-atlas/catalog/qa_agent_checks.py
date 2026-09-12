#!/usr/bin/env python3
"""QA checks for Style Atlas catalog (read-only; prints JSON results).

Part of the QA pass 2026-09-12. Palettes/HTTP are checked by the agent's
bash layer; this script handles: mounts, broken values, coverage, sampling.
Seeded (seed=42) so the sample is reproducible.
"""

import json, os, random, re, sys

CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atlas.json")
SEED = 42
MOUNT_SAMPLE = 30
PALETTE_SAMPLE = 15

d = json.load(open(CATALOG))
E = d["entries"]

# ---------- 1. MOUNT verification (random sample, mix prefixes) ----------
random.seed(SEED)
mounted = [
    e
    for e in E
    if e.get("mount")
    and e.get("mount", {}).get("dir")
    and e.get("mount", {}).get("file")
]
# mix prefixes: pick per-prefix round-robin-ish then shuffle
by_prefix = {}
for e in mounted:
    by_prefix.setdefault(e.get("prefix", e["code"].split("-")[0]), []).append(e)
sample = []
prefixes = list(by_prefix)
random.shuffle(prefixes)
i = 0
while len(sample) < min(MOUNT_SAMPLE, len(mounted)):
    p = prefixes[i % len(prefixes)]
    if by_prefix[p]:
        sample.append(by_prefix[p].pop(random.randrange(len(by_prefix[p]))))
    else:
        prefixes.remove(p)
        if not prefixes:
            break
        continue
    i += 1

mount_failures, mount_ok = [], []
for e in sample:
    m = e["mount"]
    path = os.path.join(m["dir"], m["file"])
    ok = os.path.isfile(path)
    (mount_ok if ok else mount_failures).append(
        {
            "code": e["code"],
            "path": path,
            "exists": ok,
            "source_field": e.get("source"),
        }
    )

# ---------- 2. BROKEN VALUES (full scan, cheap) ----------
broken: dict = {
    "source_path_missing": [],  # source non-null but not a file
    "source_null": [],  # no source at all
    "era_null": [],
    "empty_name": [],
    "empty_description_or_lineage": [],
    "mount_dir_missing_on_disk": [],
    "no_palette": [],
}
for e in E:
    src = e.get("source")
    if src is None:
        broken["source_null"].append(e["code"])
    elif not os.path.isfile(src):
        broken["source_path_missing"].append({"code": e["code"], "source": src})
    if e.get("era") is None:
        broken["era_null"].append(e["code"])
    if not (e.get("name") or "").strip():
        broken["empty_name"].append(e["code"])
    if not (e.get("description") or e.get("lineage") or "").strip():
        broken["empty_description_or_lineage"].append(e["code"])
    m = e.get("mount") or {}
    if m.get("dir") and not os.path.isdir(m["dir"]):
        broken["mount_dir_missing_on_disk"].append({"code": e["code"], "dir": m["dir"]})
    if not e.get("palette"):
        broken["no_palette"].append(e["code"])
for key, hits in broken.items():
    broken[key] = {"count": len(hits), "items": hits[:12]}

# ---------- 3. PALETTE sample selection (for rg in bash layer) ----------
pal_sample = []
pal_pool = [e for e in E if e.get("palette")]
random.shuffle(pal_pool)
seen_prefix = set()
for e in pal_pool:
    p = e.get("prefix", e["code"].split("-")[0])
    pal_sample.append(e)
    if len(pal_sample) >= PALETTE_SAMPLE:
        break

# ---------- 4. COVERAGE ----------
cov = {}


def seq_gaps(prefix):
    nums = sorted(
        int(m.group(1)) for e in E if (m := re.fullmatch(prefix + r"-(\d+)", e["code"]))
    )
    if not nums:
        return None
    missing = [n for n in range(nums[0], nums[-1] + 1) if n not in set(nums)]
    return {"min": nums[0], "max": nums[-1], "count": len(nums), "gaps": missing}


for pfx in ["TZ", "TX", "GM", "ED", "QA", "RW", "TP", "HL", "CR", "GO"]:
    cov[pfx] = seq_gaps(pfx) or {"count": 0}

# gmux v1..v16 detection (name/nativeId/tags mention of vN)
gmux_versions = set()
for e in E:
    if e.get("prefix") == "GM":
        hay = " ".join(
            [
                e.get("name", ""),
                e.get("nativeId", "") or "",
                " ".join(e.get("tags", [])),
            ]
        )
        for m in re.finditer(r"\bv(?:ersion)?\s?-?(\d{1,2})\b", hay, re.I):
            gmux_versions.add(int(m.group(1)))
cov["GM_versions_found"] = sorted(gmux_versions)
cov["GM_versions_missing"] = [v for v in range(1, 17) if v not in gmux_versions]

# airtree tp07 family
tp_codes = sorted(e["code"] for e in E if e.get("prefix") == "TP")
cov["TP_has_tp07"] = any(
    "tp07" in (e.get("name", "") + (e.get("nativeId") or "")).lower()
    for e in E
    if e.get("prefix") == "TP"
)
cov["TP_sample_codes"] = tp_codes[:5] + ["..."] + tp_codes[-3:]

# endispute: count ED + any QA entries whose project mentions endispute
ed_qa = [
    e
    for e in E
    if e.get("project", "").lower().find("endispute") >= 0 or e.get("prefix") == "ED"
]
cov["ED_total_including_project_hits"] = len(ed_qa)

# goetica themes named
cov["GO_entries"] = [
    e["code"] + ":" + e.get("name", "")[:40] for e in E if e.get("prefix") == "GO"
]

# qalarc: expected ~59
cov["QA_expected"] = 59

expected = {
    "TZ": {"expected": 17, "label": "tradez 17 styles"},
    "TX": {"expected": 12, "label": "x10 studio 12"},
    "GM": {"expected": 16, "label": "gmux v1-v16"},
    "ED": {"expected": 13, "label": "endispute 13-direction gallery"},
    "RW": {"expected": 26, "label": "reps 26 kits"},
    "TP": {"expected": None, "label": "airtree tp07 family (no count given)"},
    "HL": {"expected": 43, "label": "hero-lab 43"},
    "QA": {"expected": 59, "label": "qalarc demos ~59"},
    "CR": {"expected": None, "label": "crypto themegallery (no count given)"},
    "GO": {"expected": 6, "label": "goetica 6 themes"},
}
coverage = {}
for pfx, info in expected.items():
    c = cov.get(pfx, {})
    n = c.get("count", 0)
    coverage[pfx] = {
        "label": info["label"],
        "expected": info["expected"],
        "in_catalog": n,
        "sequence_range": f"{c.get('min')}-{c.get('max')}" if c.get("min") else None,
        "numbering_gaps": c.get("gaps", []),
        "delta": (n - info["expected"]) if info["expected"] is not None else None,
        "extra_entries_beyond_expected": (n - info["expected"])
        if (info["expected"] is not None and n > info["expected"])
        else 0,
    }
coverage["GM_versions_missing"] = cov["GM_versions_missing"]
coverage["TP_has_tp07"] = cov["TP_has_tp07"]
coverage["ED_total_including_project_hits"] = cov["ED_total_including_project_hits"]
coverage["GO_entries"] = cov["GO_entries"]

# ---------- 5. MISCATEGORIZED heuristics ----------
misc = []
rules = [
    (r"\blogo\b", {"logo", "brand"}, "name mentions logo"),
    (r"\bfavicon\b", {"logo", "icon", "favicon"}, "name mentions favicon"),
    (r"\bicon\b", {"logo", "icon", "favicon"}, "name mentions icon"),
    (r"\bdashboard\b", {"dashboard"}, "name mentions dashboard"),
    (r"\bcard\b", {"business-card"}, "name mentions card"),
]
for e in E:
    name = (e.get("name") or "").lower()
    cat = (e.get("category") or "").lower()
    for pat, ok_cats, why in rules:
        if re.search(pat, name) and cat not in ok_cats and cat not in ("component",):
            misc.append(
                {
                    "code": e["code"],
                    "category": e.get("category"),
                    "name": e.get("name"),
                    "reason": why,
                }
            )
misc = misc[:25]

# ---------- output ----------
out = {
    "sample_seed": SEED,
    "mount_sampled": len(sample),
    "mount_ok_count": len(mount_ok),
    "mount_failures": [f for f in mount_failures],
    "mount_sample_codes": [e["code"] for e in sample],
    "broken": broken,
    "palette_sample": [
        {
            "code": e["code"],
            "source": e.get("source"),
            "mount_dir": (e.get("mount") or {}).get("dir"),
            "hexes": [
                e["palette"].get(k)
                for k in ("bg", "surface", "ink", "accent", "accent2")
                if e["palette"].get(k)
            ]
            + list(e["palette"].get("extra", []))[:4],
        }
        for e in pal_sample
    ],
    "coverage": coverage,
    "miscategorized_heuristic": misc,
}
print(json.dumps(out, indent=1))
