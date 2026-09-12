#!/bin/bash
# STYLE ATLAS launcher — starts the server (and merges catalog if needed)
cd "$(dirname "$0")"
if [ ! -f catalog/atlas.json ] || [ "$(python3 -c "import json;print(json.load(open('catalog/atlas.json'))['meta']['count'])" 2>/dev/null)" = "0" ]; then
  echo "catalog empty — merging findings…"
  python3 scripts/merge_catalog.py
fi
exec python3 atlas_server.py "$@"
