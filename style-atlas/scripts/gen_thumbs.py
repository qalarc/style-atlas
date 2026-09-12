#!/usr/bin/env python3
"""
gen_thumbs.py — screenshot every catalog entry into thumbs/<CODE>.png

Strategy:
  - entries with a mount  → screenshot http://localhost:<port>/<CODE>/
  - entries without       → screenshot the generated /swatch/<CODE>/ page
  - externalUrl-only      → skipped (live sites; may add later)
  - logo SVGs             → screenshot inlined swatch page

Runs its own atlas_server.py on a scratch port (default 1349) so it can run
alongside the real one. Headless chromium, 4 workers, ~10s cap per shot.

Usage: python3 scripts/gen_thumbs.py [--only PREFIX] [--force] [--workers 4]
"""

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(HERE, "catalog", "atlas.json")
THUMBS = os.path.join(HERE, "thumbs")
CHROMIUM = "/usr/bin/chromium"
PORT = 1349


def shot(url, out_path, width=1280, height=860, timeout=25):
    cmd = [
        CHROMIUM,
        "--headless",
        "--no-sandbox",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
        f"--screenshot={out_path}",
        url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return os.path.isfile(out_path) and os.path.getsize(out_path) > 3000
    except subprocess.TimeoutExpired:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="only codes with this prefix, e.g. TZ")
    ap.add_argument("--force", action="store_true", help="overwrite existing")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    if not os.path.exists(CHROMIUM):
        sys.exit("chromium not found at " + CHROMIUM)

    with open(CATALOG, "r", encoding="utf-8") as f:
        entries = json.load(f)["entries"]

    os.makedirs(THUMBS, exist_ok=True)

    # start scratch server
    print("starting scratch atlas server on :%d …" % PORT)
    srv = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "atlas_server.py"), "--port", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.2)

    jobs = []
    for e in entries:
        if (
            args.only
            and not e["code"].startswith(args.only + "-")
            and not e["code"].startswith(args.only)
        ):
            continue
        out = os.path.join(THUMBS, e["code"] + ".png")
        if os.path.exists(out) and not args.force:
            continue
        if e.get("mount"):
            url = f"http://localhost:{PORT}/{e['code']}/"
        elif e.get("category") == "logo" or not e.get("externalUrl"):
            url = f"http://localhost:{PORT}/swatch/{e['code']}/"
        else:
            continue  # external-only: skip
        jobs.append((e["code"], url, out))

    print(f"{len(jobs)} thumbnails to capture…")
    ok = fail = 0
    failed = []

    def work(j):
        code, url, out = j
        return code, shot(url, out)

    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(work, j) for j in jobs]
            for i, fut in enumerate(as_completed(futs)):
                code, good = fut.result()
                if good:
                    ok += 1
                else:
                    fail += 1
                    failed.append(code)
                if (i + 1) % 20 == 0:
                    print(f"  {i + 1}/{len(jobs)}  ({time.time() - t0:.0f}s)")
    finally:
        srv.terminate()

    print(f"done: {ok} ok, {fail} failed, in {time.time() - t0:.0f}s")
    if failed:
        print("failed:", " ".join(failed[:40]))


if __name__ == "__main__":
    main()
