#!/usr/bin/env python3
"""
update_catalog.py — the front door for ADDING styles to the Style Atlas.

Future projects add their styles by writing a findings JSON (schema in
AGENTS.md / findings/BRIEF.md) and running:

    python3 scripts/update_catalog.py findings/myproject.json
    python3 scripts/update_catalog.py --rescan findings/     # everything
    python3 scripts/update_catalog.py --thumbs               # then screenshots

Idempotent: dedupes by source path, keeps existing codes stable, only appends.
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="*", help="findings JSON file(s) to merge")
    ap.add_argument(
        "--rescan", action="store_true", help="merge every *.json in findings/"
    )
    ap.add_argument(
        "--thumbs",
        action="store_true",
        help="generate thumbnails for new entries afterwards",
    )
    args = ap.parse_args()

    merge = os.path.join(HERE, "scripts", "merge_catalog.py")
    if args.rescan or not args.inputs:
        r = subprocess.run([sys.executable, merge])
    else:
        # merge_catalog already scans findings/*.json — inputs must live there
        ok = True
        for inp in args.inputs:
            dst = os.path.join(HERE, "findings", os.path.basename(inp))
            if os.path.abspath(inp) != os.path.abspath(dst):
                import shutil

                shutil.copy2(inp, dst)
        r = subprocess.run([sys.executable, merge])
    if r.returncode != 0:
        sys.exit(r.returncode)

    if args.thumbs:
        t = subprocess.run(
            [sys.executable, os.path.join(HERE, "scripts", "gen_thumbs.py")]
        )
        sys.exit(t.returncode)
    print(
        "\nNext: restart atlas_server.py (or it hot-reads on next start) and "
        "optionally run scripts/gen_thumbs.py"
    )


if __name__ == "__main__":
    main()
