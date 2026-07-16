#!/usr/bin/env python3
"""Build the full Cubist Souls / Pikkazo trait library by variance-differencing.

The original per-trait transparent PNGs were never published (IPFS only holds the
10000 flattened 768x768 images + their metadata). But every trait value composits
pixel-identically on every token it appears on. Stack N tokens that share one
value: the shared trait has ~zero per-pixel variance while everything else varies.
Threshold the variance (std < 14) and take the per-pixel median -> the isolated
layer plate (RGBA, transparent where variance is high = not part of this trait).

Method validated in tools/extract_layers.py (PoC on #136). This script scales it
to the whole collection: 8 categories, 145 values, cap 25 samples/value.

Global-skeleton fix: the high layers all capture the "contour skeleton" common to
the WHOLE collection (facial square, neck line, ear-with-X) because those pixels
are constant on every token. We estimate that skeleton from ~50 maximally-diverse
tokens (std < 14 across them = globally constant) and subtract it (make it
transparent) from every plate EXCEPT Art Background and Base, where the outline
legitimately belongs and is harmless (see layers/QA.md for the reasoning).

Usage:
  python3 build_library.py            # full build: fetch, plates, manifest
  python3 build_library.py qa         # QA only (assumes plates already built)
"""
import sys, os, io, json, time, random, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from PIL import Image

CACHE   = os.path.expanduser("~/.cache/pikkazo")
IMG_DIR = f"{CACHE}/img"
IDX     = json.load(open(f"{CACHE}/index.json"))
PROXY   = "https://cubistsouls.vercel.app/api/img?id="
STD     = 14.0          # px std below this => part of a constant (shared) layer
CAP     = 25            # samples per value
H = W   = 768

REPO    = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LAYERS  = os.path.join(REPO, "layers")

# Categories in z-order (bottom -> top). Head is the TOP layer: hair falls over
# eyes, shirt and everything else — proven by erosion patterns (Head plates come
# out complete under strict variance, while Clothes/Eyes erode exactly where hair
# fringes fall) and validated by recomposition QA (see layers/QA.md).
ZORDER  = ["Art Background", "Base", "Clothes", "Mouth", "Nose", "Left Eye", "Right Eye", "Head"]
CATS    = ["Art Background", "Base", "Clothes", "Mouth", "Head", "Left Eye", "Nose", "Right Eye"]
# Build order: top layer first — each category's recovered footprint becomes the
# occlusion mask for the categories below it.
BUILD_ORDER = ["Head", "Right Eye", "Left Eye", "Nose", "Mouth", "Clothes",
               "Base", "Art Background"]
KEEP_SKELETON = {"Art Background", "Base"}   # do NOT subtract the global skeleton here
# Every category except the top one (Head) can be occluded by the layers above it,
# so strict low-variance (std<14) erodes the plate wherever the occluders vary
# across samples (union-of-silhouettes holes -> uncovered gaps on recompose).
# Fix: occluder-aware per-pixel MODE — since the upper plates are recovered first
# (BUILD_ORDER is top-down), we know exactly which pixels each sample's own upper
# layers cover, exclude them from the vote, and keep a pixel when enough visible
# samples agree on the same colour. See _mode_plate.
MODE_FILL = {"Art Background", "Base", "Clothes", "Mouth", "Nose", "Left Eye", "Right Eye"}
MODE_TOL  = 10.0   # mean-abs-channel-diff for two samples to "agree"
# Samples per category: rarely-visible pixels (forehead under most hairstyles)
# need many samples so >=3 unoccluded ones exist. Stratified picks only where the
# occluder diversity matters (they cost fresh downloads).
MODE_CAP  = {"Art Background": 60, "Base": 60, "Clothes": 40}   # default: CAP (25)
STRATIFY  = {"Art Background", "Base", "Clothes"}
HONORARIES    = [90, 163, 294, 600]           # 1/1 tokens: flat PNG is the final piece

os.makedirs(IMG_DIR, exist_ok=True)


def slug(s):
    return s.lower().replace(" ", "-")


# ---------------------------------------------------------------- downloading
def _valid(p):
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        return False
    try:
        Image.open(p).convert("RGB").load()
        return True
    except Exception:
        return False


def _download_one(tid):
    p = f"{IMG_DIR}/{tid}.png"
    if _valid(p):
        return tid, True
    for attempt in range(4):
        try:
            req = urllib.request.Request(PROXY + str(tid),
                                         headers={"User-Agent": "cubist-souls-builder"})
            data = urllib.request.urlopen(req, timeout=60).read()
            Image.open(io.BytesIO(data)).convert("RGB").load()  # validate before write
            with open(p, "wb") as f:
                f.write(data)
            return tid, True
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return tid, False


def fetch_all(ids):
    ids = sorted(set(int(i) for i in ids))
    todo = [i for i in ids if not _valid(f"{IMG_DIR}/{i}.png")]
    if not todo:
        return
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(_download_one, i): i for i in todo}
        for n, fut in enumerate(as_completed(futs), 1):
            _, good = fut.result()
            ok += good
            fail += (not good)
            if n % 50 == 0 or n == len(todo):
                print(f"    download {n}/{len(todo)} (ok={ok} fail={fail})", flush=True)
    if fail:
        print(f"    WARNING: {fail} images failed after retries", flush=True)


def arr(tid):
    im = Image.open(f"{IMG_DIR}/{tid}.png").convert("RGB")
    if im.size != (W, H):
        im = im.resize((W, H), Image.LANCZOS)  # a few tokens are served at 2048px
    return np.asarray(im, dtype=np.float32)


_TRAITS_CACHE = {}


def token_traits(tid):
    if tid not in _TRAITS_CACHE:
        m = json.load(open(f"{CACHE}/meta/{tid}.json"))
        _TRAITS_CACHE[tid] = {a["trait_type"]: a["value"] for a in m["attributes"]}
    return _TRAITS_CACHE[tid]


def stratified_ids(cat, val, cap):
    """Deterministic greedy pick of `cap` ids of (cat,val) maximizing diversity of
    the OTHER categories' values, so no single occluder silhouette/colour can
    dominate the per-pixel vote at any point of the canvas."""
    pool = [t for t in IDX[cat][val] if t not in HONORARIES]
    seen = {c: {} for c in CATS if c != cat}
    chosen = []
    remaining = list(pool)
    for _ in range(min(cap, len(pool))):
        best_t, best_score = None, None
        for t in remaining:
            tr = token_traits(t)
            score = sum(seen[c].get(tr.get(c), 0) for c in seen)
            if best_score is None or score < best_score:
                best_t, best_score = t, score
                if score == 0:
                    break
        chosen.append(best_t)
        remaining.remove(best_t)
        tr = token_traits(best_t)
        for c in seen:
            v = tr.get(c)
            seen[c][v] = seen[c].get(v, 0) + 1
    return chosen


def valid_sample_ids(cat, val, cap=None):
    """Sample ids for a plate, skipping corrupt downloads (tops up on failures).
    Deep categories use a bigger, stratified sample; the rest use the first CAP
    ids (reproducible)."""
    if cap is None:
        cap = MODE_CAP.get(cat, CAP)
    ids = stratified_ids(cat, val, cap * 2) if cat in STRATIFY else IDX[cat][val]
    chosen = []
    i = 0
    while len(chosen) < cap and i < len(ids):
        need = cap - len(chosen)
        batch = ids[i:i + need]
        fetch_all(batch)
        for t in batch:
            if _valid(f"{IMG_DIR}/{t}.png"):
                chosen.append(t)
        i += len(batch)
    return chosen


# ---------------------------------------------------------------- global mask
def diverse_tokens(n=50, seed=42):
    """Pick n maximally-diverse tokens: each contributes a distinct value from a
    (mostly) distinct category, so only truly global-constant pixels stay low-std."""
    random.seed(seed)
    pairs = [(c, v) for c in CATS for v in IDX[c]]
    random.shuffle(pairs)
    chosen, seen = [], set()
    for c, v in pairs:
        for tid in IDX[c][v]:
            if tid not in seen and tid not in HONORARIES:
                seen.add(tid)
                chosen.append(tid)
                break
        if len(chosen) >= n:
            break
    return chosen


def global_skeleton():
    toks = diverse_tokens()
    print(f"  global skeleton from {len(toks)} diverse tokens: {sorted(toks)}", flush=True)
    fetch_all(toks)
    stack = np.stack([arr(t) for t in toks], 0)
    std = stack.std(0).mean(2)
    skel = std < STD
    print(f"  skeleton covers {skel.mean()*100:.1f}% of the canvas", flush=True)
    return skel


# ---------------------------------------------------------------- plates
def _dilate(mask, r=2):
    """Binary dilation with a (2r+1)^2 square, pure numpy."""
    out = mask.copy()
    for _ in range(r):
        m = out.copy()
        m[1:, :] |= out[:-1, :]
        m[:-1, :] |= out[1:, :]
        m[:, 1:] |= out[:, :-1]
        m[:, :-1] |= out[:, 1:]
        out = m
    return out


_PLATE_ALPHA = {}


def plate_alpha(cat, val):
    """Dilated footprint (alpha) of an already-built plate, cached."""
    key = (cat, val)
    if key not in _PLATE_ALPHA:
        p = os.path.join(LAYERS, slug(cat), f"{slug(val)}.png")
        a = np.asarray(Image.open(p).convert("RGBA"))[:, :, 3] > 0
        _PLATE_ALPHA[key] = _dilate(a, 2)
    return _PLATE_ALPHA[key]


# Which categories occlude each one = everything ABOVE it in ZORDER. Plates are
# built top-down (BUILD_ORDER) so the occluders' footprints always exist already.
OCCLUDERS = {cat: ZORDER[ZORDER.index(cat) + 1:] for cat in ZORDER}


def _occluded(tid, cat):
    """Union of the dilated footprints of tid's layers that sit ABOVE cat."""
    tr = token_traits(tid)
    occ = np.zeros((H, W), dtype=bool)
    for c in OCCLUDERS[cat]:
        if c in tr:
            occ |= plate_alpha(c, tr[c])
    return occ


def _mode_plate(stack, ids, cat):
    """Occluder-aware per-pixel MODE. For each sample we know exactly which pixels
    its own upper layers cover (their recovered plate footprints), so those pixels
    are excluded from the vote. Where the layer is visible it composites
    pixel-identically, so the visible samples agree near-exactly: quantize to //8
    buckets, pack RGB into one int, and vote. A pixel is kept when >= MIN_VALID
    unoccluded samples exist and >= VALID_FRAC of them agree; colour = mean of the
    agreeing samples (averages away AA noise)."""
    MIN_VALID, VALID_FRAC = 3, 0.6
    n = stack.shape[0]
    valid = np.stack([~_occluded(t, cat) for t in ids], 0)      # N,H,W
    q = (stack / 8).astype(np.uint8)
    packed = ((q[..., 0].astype(np.uint32) << 16) |
              (q[..., 1].astype(np.uint32) << 8) | q[..., 2])   # N,H,W
    agree = np.zeros((n, H, W), dtype=np.uint8)
    for i in range(n):
        agree[i] = ((packed == packed[i]) & valid).sum(0)
        agree[i][~valid[i]] = 0
    best = agree.argmax(0)                                      # H,W
    votes = agree.max(0).astype(np.float32)
    nvalid = valid.sum(0).astype(np.float32)
    alpha = (nvalid >= MIN_VALID) & (votes >= MIN_VALID) & \
            (votes / np.clip(nvalid, 1, None) >= VALID_FRAC)
    modal = np.take_along_axis(stack, best[None, :, :, None], axis=0)[0]  # H,W,3
    inlier = (np.abs(stack - modal).mean(3) <= MODE_TOL) & valid          # N,H,W
    wsum = (stack * inlier[..., None]).sum(0)
    color = wsum / np.clip(inlier.sum(0)[..., None], 1, None)
    return color, alpha


def build_plate(cat, val, skel):
    ids = valid_sample_ids(cat, val)
    stack = np.stack([arr(t) for t in ids], 0)     # N,H,W,3
    if cat in MODE_FILL:
        med, alpha = _mode_plate(stack, ids, cat)
    else:
        med = np.median(stack, 0)
        alpha = stack.std(0).mean(2) < STD
    if cat not in KEEP_SKELETON:
        alpha = alpha & (~skel)
    rgba = np.dstack([med.astype(np.uint8), (alpha * 255).astype(np.uint8)])
    return rgba, len(ids), float(alpha.mean() * 100.0)


def build_all():
    print("== Cubist Souls trait library build ==", flush=True)
    # prefetch the whole working set up front (parallel, validated)
    need = set()
    for c in CATS:
        cap = MODE_CAP.get(c, CAP)
        for v in IDX[c]:
            need.update(stratified_ids(c, v, cap) if c in STRATIFY
                        else IDX[c][v][:cap])
    need.update(diverse_tokens())
    print(f"prefetching {len(need)} unique source images ...", flush=True)
    fetch_all(need)

    skel = global_skeleton()

    summary = []
    total_plates = 0
    for cat in BUILD_ORDER:
        cdir = os.path.join(LAYERS, slug(cat))
        os.makedirs(cdir, exist_ok=True)
        for val in sorted(IDX[cat].keys()):
            rgba, n, cov = build_plate(cat, val, skel)
            fn = f"{slug(val)}.png"
            Image.fromarray(rgba, "RGBA").save(os.path.join(cdir, fn))
            total_plates += 1
            summary.append((cat, val, n, cov))
            print(f"  [{cat}] {val:<24} n={n:2d} alpha={cov:5.1f}%  -> {slug(cat)}/{fn}", flush=True)

    manifest_cats = [{
        "id": slug(cat), "label": cat, "dir": f"layers/{slug(cat)}",
        "options": [{"file": f"{slug(val)}.png", "label": val,
                     "count": len(IDX[cat][val])} for val in sorted(IDX[cat].keys())],
    } for cat in CATS]

    # manifest.json at repo root
    manifest = {
        "collection": "Cubist Souls",
        "note": "Trait layers recovered by variance-differencing the 10000 flattened "
                "Pikkazo images. See README.md 'Trait library' and layers/QA.md.",
        "canvas": {"width": W, "height": H},
        "zOrder": [slug(c) for c in ZORDER],
        "zOrderLabels": ZORDER,
        "categories": manifest_cats,
        "honoraries": _honoraries(),
    }
    with open(os.path.join(REPO, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n== {total_plates} plates written to {LAYERS} ==", flush=True)
    print("manifest.json written", flush=True)
    return summary


def _honoraries():
    out = []
    for tid in HONORARIES:
        m = json.load(open(f"{CACHE}/meta/{tid}.json"))
        out.append({"id": tid, "name": m.get("name", f"#{tid}"),
                    "image": f"img/{tid}.png"})
    return out


# ---------------------------------------------------------------- QA
def _load_plate(cat, val):
    p = os.path.join(LAYERS, slug(cat), f"{slug(val)}.png")
    return np.asarray(Image.open(p).convert("RGBA"), dtype=np.float32)


def _composite(traits, order):
    """Alpha-composite the 8 plates for one token in the given bottom->top order."""
    out = np.zeros((H, W, 4), dtype=np.float32)
    for cat in order:
        top = _load_plate(cat, traits[cat])
        ta = top[:, :, 3:4] / 255.0
        ba = out[:, :, 3:4] / 255.0
        oa = ta + ba * (1 - ta)
        orgb = (top[:, :, :3] * ta + out[:, :, :3] * ba * (1 - ta)) / np.clip(oa, 1e-6, None)
        out[:, :, :3] = orgb
        out[:, :, 3:4] = oa * 255.0
    return out


def _traits_of(tid):
    m = json.load(open(f"{CACHE}/meta/{tid}.json"))
    return {a["trait_type"]: a["value"] for a in m["attributes"]}


def _match_pct(comp, orig):
    """% of pixels whose max channel diff <= 10, ignoring a 1px border."""
    c = comp[:, :, :3]
    diff = np.abs(c - orig).max(2)
    good = diff <= 10
    good = good[1:-1, 1:-1]
    return float(good.mean() * 100.0)


def qa(save_proofs=True):
    # 10 varied tokens incl. #136 (known control)
    qa_ids = [136, 1, 17, 42, 231, 512, 1337, 2600, 5000, 8888]
    qa_ids = [t for t in qa_ids if t not in HONORARIES]
    for t in qa_ids:
        fetch_all([t])

    orders = {
        "hypothesis (AB>Base>Clothes>Head>Mouth>Nose>LEye>REye)":
            ["Art Background", "Base", "Clothes", "Head", "Mouth", "Nose", "Left Eye", "Right Eye"],
        "eyes-below-head":
            ["Art Background", "Base", "Clothes", "Left Eye", "Right Eye", "Nose", "Mouth", "Head"],
        "head-top":
            ["Art Background", "Base", "Clothes", "Mouth", "Nose", "Left Eye", "Right Eye", "Head"],
        "clothes-over-head":
            ["Art Background", "Base", "Head", "Clothes", "Mouth", "Nose", "Left Eye", "Right Eye"],
    }

    results = {}
    for name, order in orders.items():
        scores = []
        for t in qa_ids:
            comp = _composite(_traits_of(t), order)
            scores.append(_match_pct(comp, arr(t)))
        results[name] = (order, scores, sum(scores) / len(scores))
        print(f"[{name}] avg={results[name][2]:.2f}%", flush=True)

    best = max(results, key=lambda k: results[k][2])
    best_order, best_scores, best_avg = results[best]
    print(f"\nBEST z-order: {best}  avg={best_avg:.2f}%", flush=True)

    # proofs for 3 tokens with the best order
    proof_dir = os.path.join(REPO, "proof")
    os.makedirs(proof_dir, exist_ok=True)
    if save_proofs:
        for t in [136, 42, 1337]:
            if t in HONORARIES:
                continue
            comp = _composite(_traits_of(t), best_order)
            comp_rgb = Image.fromarray(comp[:, :, :3].astype(np.uint8), "RGB")
            orig = Image.open(f"{IMG_DIR}/{t}.png").convert("RGB")
            side = Image.new("RGB", (W * 2 + 12, H), (17, 17, 17))
            side.paste(orig, (0, 0))
            side.paste(comp_rgb, (W + 12, 0))
            side.save(os.path.join(proof_dir, f"recompose_{t}.png"))
            print(f"  proof/recompose_{t}.png", flush=True)

    _write_qa_md(qa_ids, results, best, best_order, best_scores, best_avg)
    return results


def _write_qa_md(qa_ids, results, best, best_order, best_scores, best_avg):
    lines = []
    lines.append("# Trait library QA — z-order validation\n")
    lines.append("Recomposition test: for each token, alpha-composite its 8 recovered "
                 "plates and compare pixel-by-pixel against the original flattened PNG.\n")
    lines.append("**Metric:** % of pixels whose max RGB channel difference is <= 10, "
                 "ignoring a 1px anti-aliasing border.\n")
    lines.append(f"## Final z-order (bottom -> top)\n\n`{ ' > '.join(best_order) }`\n")
    lines.append(f"Selected as **{best}** — highest average match "
                 f"(**{best_avg:.2f}%**) across {len(qa_ids)} varied tokens "
                 f"(incl. #136, the known control).\n")
    lines.append("## Per-token match (best z-order)\n")
    lines.append("| token | match % |")
    lines.append("|------:|--------:|")
    for t, s in zip(qa_ids, best_scores):
        tag = " (control)" if t == 136 else ""
        lines.append(f"| #{t}{tag} | {s:.2f}% |")
    lines.append("")
    lines.append("## Orders tried\n")
    lines.append("| order | avg match % |")
    lines.append("|-------|------------:|")
    for name, (order, scores, avg) in sorted(results.items(), key=lambda kv: -kv[1][2]):
        lines.append(f"| {name} | {avg:.2f}% |")
    lines.append("")
    lines.append("## Global-skeleton decision\n")
    lines.append("The contour skeleton (facial square, neck line, ear-with-X) is constant "
                 "across the whole collection, so every plate's variance mask captures it. "
                 "We subtract it (make it transparent) from all categories **except Art "
                 "Background and Base**:\n")
    lines.append("- **Base** legitimately owns the character/face outline, so the skeleton "
                 "must live there and be the single source of those pixels on recompose.\n")
    lines.append("- **Art Background** is the bottom layer; its skeleton region is always "
                 "painted over by Base during recomposition, so keeping it is harmless and "
                 "removing it risks eroding legitimate background edges.\n")
    lines.append("- All higher categories (Clothes, Head, Mouth, Nose, Left/Right Eye) have "
                 "the skeleton removed so they contribute only their own trait pixels.\n")
    with open(os.path.join(LAYERS, "QA.md"), "w") as f:
        f.write("\n".join(lines))
    print("layers/QA.md written", flush=True)


def rebuild_categories(cats):
    """Regenerate the plates of specific categories only (layers/ already built)."""
    cats = sorted(cats, key=BUILD_ORDER.index)   # occlusion masks need this order
    skel = global_skeleton()
    for cat in cats:
        cdir = os.path.join(LAYERS, slug(cat))
        os.makedirs(cdir, exist_ok=True)
        for val in sorted(IDX[cat].keys()):
            rgba, n, cov = build_plate(cat, val, skel)
            Image.fromarray(rgba, "RGBA").save(os.path.join(cdir, f"{slug(val)}.png"))
            print(f"  [{cat}] {val:<24} n={n:2d} alpha={cov:5.1f}%", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "qa":
        qa()
    elif cmd == "rebuild":
        rebuild_categories(sys.argv[2:])
    else:
        build_all()
        qa()
