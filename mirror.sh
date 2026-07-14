#!/usr/bin/env bash
# Mirror one or more burned Pikkazo tokens into this repo (durable copy).
# Usage: ./mirror.sh <id> [<id> ...]
set -euo pipefail

IMG_CID="QmVgPQtmUBVFK4YqiTQHSFuF1yWcWF3BKGvpXYwFFHfiBm"
META_CID="QmPXUAzyddsQYPUjY2E7WDWedx7vMgdJGyj8a84rzFWmed"
GATEWAYS=("https://ipfs.io/ipfs" "https://gateway.pinata.cloud/ipfs" "https://4everland.io/ipfs")
DIR="$(cd "$(dirname "$0")" && pwd)"

fetch() { # <cid>/<path> <out>
  local rel="$1" out="$2" gw
  for gw in "${GATEWAYS[@]}"; do
    if curl -fsS --max-time 45 -o "$out" "$gw/$rel"; then return 0; fi
  done
  echo "FAILED to fetch $rel from all gateways" >&2; return 1
}

for id in "$@"; do
  echo "mirroring #$id ..."
  fetch "$IMG_CID/$id"  "$DIR/img/$id.png"
  fetch "$META_CID/$id" "$DIR/meta/$id.json"
  echo "  ok: img/$id.png  meta/$id.json"
done
echo "done. now: git add img meta && git commit && git push"
