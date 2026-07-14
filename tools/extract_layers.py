#!/usr/bin/env python3
"""Recover Pikkazo trait layers from the flattened art + trait labels.

The original per-trait transparent PNGs were never published (IPFS only holds the
10000 flattened 768x768 images and their metadata). But every trait value appears
on many tokens, and it composites pixel-identically each time. So if we stack all
tokens that share one trait value, that trait has ~zero per-pixel variance while
the rest of the character varies. Threshold on variance -> the isolated layer.

This is honest reconstruction (pure arithmetic on art the holders already own),
not AI inpainting. Limitation: anything ALWAYS occluded (background behind the
torso) can't be recovered — it shows as a transparent hole.

Proof of concept run 2026-07-15 on #136 (Emerald Tiles bg, 16 tokens; White
Hoodie garment, 9 tokens). To scale to a full trait library: build the index
over all 10000 metadata, then run extract() for every (category, value).

Usage:
  python3 extract_layers.py index            # fetch metadata -> trait index json
  python3 extract_layers.py plate "Art Background" "Emerald Tiles" out.png
  python3 extract_layers.py cutout 136 "Art Background" "Emerald Tiles" char.png
"""
import sys, os, json, glob, urllib.request
import numpy as np
from PIL import Image

META_CID = "QmPXUAzyddsQYPUjY2E7WDWedx7vMgdJGyj8a84rzFWmed"
IMG_CID = "QmVgPQtmUBVFK4YqiTQHSFuF1yWcWF3BKGvpXYwFFHfiBm"
GW = "https://ipfs.io/ipfs"
IMG_PROXY = "https://cubistsouls.vercel.app/api/img?id="  # reliable, edge-cached
CACHE = os.path.expanduser("~/.cache/pikkazo")
STD_THRESHOLD = 14.0  # px std below this => part of the shared (constant) layer


def _get(url, path, timeout=45):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    urllib.request.urlretrieve(url, path)
    return path


def img(tid):
    p = f"{CACHE}/img/{tid}.png"
    if not (os.path.exists(p) and os.path.getsize(p)):
        try:
            _get(f"{GW}/{IMG_CID}/{tid}", p)
            Image.open(p).convert("RGB").load()
        except Exception:
            _get(f"{IMG_PROXY}{tid}", p)
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)


def build_index(n=10000):
    idx = {}
    for tid in range(1, n + 1):
        p = f"{CACHE}/meta/{tid}.json"
        try:
            _get(f"{GW}/{META_CID}/{tid}", p, timeout=20)
            d = json.load(open(p))
            for a in d["attributes"]:
                idx.setdefault(a["trait_type"], {}).setdefault(a["value"], []).append(tid)
        except Exception:
            pass
    json.dump(idx, open(f"{CACHE}/index.json", "w"))
    print("index ->", f"{CACHE}/index.json",
          "categories:", list(idx.keys()))
    return idx


def _std_and_median(ids):
    stack = np.stack([img(i) for i in ids], 0)  # N,H,W,3
    return stack.std(0).mean(2), np.median(stack, 0)  # H,W ; H,W,3


def plate(cat, val, out=None, thr=STD_THRESHOLD):
    ids = json.load(open(f"{CACHE}/index.json"))[cat][val]
    std, med = _std_and_median(ids)
    alpha = ((std < thr) * 255).astype(np.uint8)
    rgba = np.dstack([med.astype(np.uint8), alpha])
    if out:
        Image.fromarray(rgba, "RGBA").save(out)
        print(f"{cat}/{val}: {len(ids)} tokens -> {out}")
    return rgba


def cutout(tid, cat, val, out=None, thr=STD_THRESHOLD):
    """Isolate a token's character by removing a known background layer."""
    ids = json.load(open(f"{CACHE}/index.json"))[cat][val]
    std, _ = _std_and_median(ids)
    alpha = ((std >= thr) * 255).astype(np.uint8)  # high variance = character
    rgba = np.dstack([img(tid).astype(np.uint8), alpha])
    if out:
        Image.fromarray(rgba, "RGBA").save(out)
        print(f"character #{tid} (bg {val} removed) -> {out}")
    return rgba


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "index"
    if cmd == "index":
        build_index()
    elif cmd == "plate":
        plate(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "cutout":
        cutout(int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5])
    else:
        print(__doc__)
