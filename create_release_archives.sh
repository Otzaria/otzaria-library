#!/usr/bin/env bash
# Build the primary release archive from the committed config + lineage.
set -euo pipefail
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WORKSPACE"

python3 "$WORKSPACE/manual_links_packaging.py" package \
  --workspace "$WORKSPACE" \
  --output "$WORKSPACE/otzaria_latest.zip" \
  --result "$WORKSPACE/otzaria_packaging_result.json"

python3 - <<'PY'
import json
from pathlib import Path

result = json.loads(Path("otzaria_packaging_result.json").read_text(encoding="utf-8"))
asset = result["asset"]
print(f"Created {asset['name']}: {asset['size']} bytes, sha256={asset['sha256']}")
PY
