#!/usr/bin/env bash
# mirror_missing.sh — ensure every burned Cubist Soul has a durable local copy.
#
# For each tokenId reported by find_souls.mjs (i.e. every Soul on-chain), if
# img/<id>.png is missing we download the original 768x768 Pikkazo art; if
# meta/<id>.json is missing we extract it from the local meta-all.json (never
# from the network — the 10000 originals are already consolidated in-repo).
#
# Idempotent: tokens already present are skipped. No secrets, no deps beyond
# node + curl (jq optional).
#
# Usage:  ./scripts/mirror_missing.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"   # repo root
cd "$DIR"

# Image sources, tried in order:
#  1) the live Vercel proxy (fast, always fresh) — https://cubistsouls.vercel.app/api/img?id=<id>
#  2) IPFS gateways over the Pikkazo image CID (same as mirror.sh).
IMG_CID="QmVgPQtmUBVFK4YqiTQHSFuF1yWcWF3BKGvpXYwFFHfiBm"
GATEWAYS=(
  "https://ipfs.io/ipfs"
  "https://gateway.pinata.cloud/ipfs"
  "https://4everland.io/ipfs"
)

# True if $1 is a real PNG/JPEG (magic bytes), false otherwise.
is_image() {
  local f="$1"
  [ -s "$f" ] || return 1
  local sig
  sig="$(head -c 8 "$f" | od -An -tx1 | tr -d ' \n')"
  case "$sig" in
    89504e470d0a1a0a*) return 0 ;; # PNG
    ffd8ff*)           return 0 ;; # JPEG
    *)                 return 1 ;;
  esac
}

download_img() {
  local id="$1" out="$2" tmp url tries
  tmp="$(mktemp)"
  # attempt list: proxy first, then each gateway
  local urls=( "https://cubistsouls.vercel.app/api/img?id=${id}" )
  local gw
  for gw in "${GATEWAYS[@]}"; do urls+=( "${gw}/${IMG_CID}/${id}" ); done

  for url in "${urls[@]}"; do
    for tries in 1 2; do
      if curl -fsSL --max-time 60 -o "$tmp" "$url"; then
        if is_image "$tmp"; then
          mv "$tmp" "$out"
          echo "    img <- $url"
          return 0
        else
          echo "    not an image (retry): $url" >&2
        fi
      fi
      sleep 1
    done
  done
  rm -f "$tmp"
  echo "    FAILED to fetch a valid image for #$id from all sources" >&2
  return 1
}

extract_meta() {
  local id="$1" out="$2"
  node -e '
    const fs = require("fs");
    const id = process.argv[1], out = process.argv[2];
    const all = JSON.parse(fs.readFileSync("meta-all.json", "utf8"));
    const m = all[id];
    if (!m) { console.error("    #" + id + " not in meta-all.json"); process.exit(2); }
    fs.writeFileSync(out, JSON.stringify(m));
  ' "$id" "$out"
  echo "    meta <- meta-all.json"
}

ids="$(node "$DIR/scripts/find_souls.mjs")"
if [ -z "$ids" ]; then
  echo "no souls found (RPCs down?) — aborting without changes" >&2
  exit 1
fi

changed=0
for id in $ids; do
  need_img=0; need_meta=0
  [ -f "img/${id}.png" ]  || need_img=1
  [ -f "meta/${id}.json" ] || need_meta=1
  if [ "$need_img" -eq 0 ] && [ "$need_meta" -eq 0 ]; then
    continue
  fi
  echo "mirroring #$id ..."
  if [ "$need_img" -eq 1 ];  then download_img "$id" "img/${id}.png";  changed=1; fi
  if [ "$need_meta" -eq 1 ]; then extract_meta "$id" "meta/${id}.json"; changed=1; fi
done

if [ "$changed" -eq 0 ]; then
  echo "all souls already mirrored — nothing to do"
else
  echo "done."
fi
