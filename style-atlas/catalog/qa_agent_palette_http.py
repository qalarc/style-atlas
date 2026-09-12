#!/usr/bin/env python3
"""QA palette-truth + HTTP checks for Style Atlas (2026-09-12).

Palette logic: for each sampled entry, every palette hex is searched in the
entry's `source` (file or dir) with `rg` (timeout 30):
  1. literal '#<hex>' (preferred form)
  2. bare '<hex>' with \\b word boundaries (some sources omit '#')
Fallback: sibling *.css/*.html/*.js/*.json under mount.dir.
Verdict: OK (all found) / PARTIAL / SUSPECT-0-HITS (all missing = invented).
NOTE: palette hexes already include '#'; strip before searching (## bug).
HTTP: curl --max-time 10 against hub http://localhost:1340/.
Sample seed 42, 15 entries — results in qa_agent_report.json.
"""

import json, os, subprocess

CAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atlas.json")
HUB = "http://localhost:1340"
E = json.load(open(CAT))["entries"]


def rg(args, t=30):
    return subprocess.run(["rg", *args], capture_output=True, text=True, timeout=t)


def search_hex(h, target):
    if rg(["-i", "--no-messages", "-F", "#" + h, target]).stdout.strip():
        return "#"
    if rg(["-i", "--no-messages", rf"\b{h}\b", target]).stdout.strip():
        return "bare"
    return None


sample = [
    "MI-011",
    "TP-026",
    "QA-042",
    "TZ-003",
    "TP-023",
    "CR-003",
    "ED-023",
    "CR-012",
    "RW-030",
    "ED-021",
    "XB-028",
    "GM-031",
    "ED-019",
    "GM-039",
    "MI-007",
]
pal = []
for code in sample:
    e = next(x for x in E if x["code"] == code)
    hexes = [h.lower().lstrip("#") for h in e["palette"].values() if isinstance(h, str)]
    hexes += [
        h.lower().lstrip("#")
        for h in e["palette"].get("extra", [])
        if isinstance(h, str)
    ]
    src, mdir = e.get("source"), (e.get("mount") or {}).get("dir")
    found = {}
    for t in [src] if src and os.path.exists(src) else []:
        for h in hexes:
            if h in found:
                continue
            f = search_hex(h, t)
            if f:
                found[h] = f
    if mdir and os.path.isdir(mdir):
        for h in hexes:
            if h in found:
                continue
            r = rg(
                [
                    "-i",
                    "--no-messages",
                    "-g",
                    "*.css",
                    "-g",
                    "*.html",
                    "-g",
                    "*.js",
                    "-g",
                    "*.json",
                    "-e",
                    "#" + h,
                    "-e",
                    rf"\b{h}\b",
                    mdir,
                ]
            )
            if r.stdout.strip():
                found[h] = "sibling"
    missing = [h for h in hexes if h not in found]
    pal.append(
        {
            "code": code,
            "total": len(hexes),
            "found": len(found),
            "missing": missing,
            "verdict": "OK"
            if not missing
            else ("PARTIAL" if found else "SUSPECT-0-HITS"),
        }
    )

urls = [
    HUB + u for u in ("/api/catalog", "/", "/projects", "/CR-001/", "/swatch/CR-001/")
]
http = {}
for u in urls:
    r = subprocess.run(
        ["curl", "--max-time", "10", "-s", "-o", "/dev/null", "-w", "%{http_code}", u],
        capture_output=True,
        text=True,
        timeout=15,
    )
    http[u] = int(r.stdout) if r.stdout.isdigit() else None

print(json.dumps({"palette": pal, "http": http}, indent=1))
