#!/usr/bin/env python3
"""Surgical re-extraction of the 40 EYE plates (Left Eye + Right Eye).

Diagnosis (Fable, 16-jul, verified visually — do NOT re-derive): the 40 eye plates
carry (a) surviving colour motes and (b) EROSION of the trait (bites out of
all-seeing-eye, holes in dead-man, ghosts in asymmetrical). Root cause: the eyes
live under the frequent footprint of Head (top layer) -> few visible samples per
pixel after the occlusion mask -> with n=30 the ">=40% + floor 3" threshold both
lets casual agreements through (motes) AND drops real content on split votes
(erosion). The fix is STRONGER STATISTICS, not more aggressive filtering.

Rules for these categories (override the generic cleaning pass):
  * n = 100 samples per value (streaming download -> process -> delete; cache < 500MB).
  * a pixel is ELIGIBLE only if it has >= 10 visible (unoccluded) samples, else
    transparent (MIN_VALID = 10).
  * the exact-match winner (tol <= 2) wins the pixel if it has >= 75% of the visible
    samples AND an absolute floor of >= 6 exact agreers (MIN_AGREE = 6).
  * connected-component hygiene + skeleton v2 identical to the cleaning pass.

Why 75% and not the cleaning pass's 40% (measured on Right Eye / Spare Coin, n=100):
the support (votes/visible) distribution is BIMODAL — true trait pixels sit at
~0.95-1.0 (every sample of the value paints the same colour where visible) while
cross-layer contamination sits at ~0.45-0.55. At 40% two artifact families passed:
(a) a dark-navy blob at the LEFT-pupil position on Right Eye plates (Right Eye's only
occluder is Head, so left-eye-region pixels are never masked, and ~half the
collection's Left Eye values share the same dark navy there), and (b) phantom
eyebrow-arc fragments that are BASE-owned (only ~half the bases draw them; verified
0/5 random Spare Coin tokens carry the arc — the earlier 3/3 was selection bias).
0.75 splits the two modes with margin on both sides. Erosion does NOT come back:
the n=30 erosion was caused by the weak absolute floor (3), not by the fraction —
a true trait pixel visible in only 12/100 samples still has 12/12 = 100% support.

Optional: if erosion PERSISTS with n=100, reduce the Head-footprint dilation used
for the eyes' occlusion mask from 2px to 1px (HEAD_DILATE=1) -- documented.

Usage:
  python3 clean_eyes.py                 # clean 40 eye plates (resumable) + QA + proofs
  python3 clean_eyes.py --head-dilate 1 # same, but 1px Head dilation for eye occlusion
  python3 clean_eyes.py qa              # QA recompose + zoomed eye contact sheet only
"""
import os, sys, glob, json, math, subprocess, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_library as bl
import clean_library as cl

H = W = 768
EYE_CATS = ["Right Eye", "Left Eye"]          # build order: Right Eye occludes Left Eye
CAP_EYE  = 100
PROGRESS = "/tmp/cs_eyes_progress.json"

# ---- eye-specific vote knobs (override clean_library module globals) ----------
cl.MIN_VALID = 10     # pixel eligible only with >= 10 visible samples
cl.MIN_AGREE = 6      # absolute floor of exact agreers
cl.VALID_FRAC = 0.75  # bimodal support: trait ~0.95+, cross-layer dirt ~0.5 (see above)
cl.EXACT_TOL = 2      # exact colour match tolerance
cl.DEF_CAP = CAP_EYE  # eyes are not in CAP{}, so DEF_CAP drives the sample count

# ---- per-category occluder dilation override (default 2px, as the cleaning pass)
DIL = {}   # e.g. {"Head": 1} to soften the Head footprint for eye occlusion only


def patched_plate_alpha(cat, val):
    key = (cat, val)
    if key not in bl._PLATE_ALPHA:
        p = os.path.join(bl.LAYERS, bl.slug(cat), f"{bl.slug(val)}.png")
        a = np.asarray(Image.open(p).convert("RGBA"))[:, :, 3] > 0
        bl._PLATE_ALPHA[key] = bl._dilate(a, DIL.get(cat, 2))
    return bl._PLATE_ALPHA[key]


bl.plate_alpha = patched_plate_alpha    # so bl._occluded honours DIL


# ============================================================ progress / resume
def _load_progress():
    if os.path.exists(PROGRESS):
        try:
            return set(tuple(x) for x in json.load(open(PROGRESS)))
        except Exception:
            return set()
    return set()


def _save_progress(done):
    json.dump(sorted(done), open(PROGRESS, "w"))


# ============================================================ clean one eye plate
def clean_eye_plate(cat, val, skel_d):
    ids = cl.clean_samples(cat, val, CAP_EYE)
    su8 = cl.stack_u8(ids)
    color, alpha = cl.exact_vote(su8, ids, cat, cl.VALID_FRAC)
    alpha = alpha & (~skel_d)             # eyes are never in KEEP_SKELETON
    alpha = cl.hygiene(alpha)
    rgba = np.dstack([color, (alpha * 255).astype(np.uint8)])
    cl._drop_imgs(ids)
    bl._PLATE_ALPHA.pop((cat, val), None)
    return rgba, len(ids), float(alpha.mean() * 100.0)


def clean_all_eyes():
    cl._clear_img_dir()
    bl._PLATE_ALPHA.clear()
    done = _load_progress()
    print(f"== clean 40 eye plates (n={CAP_EYE}, MIN_VALID={cl.MIN_VALID}, "
          f"MIN_AGREE={cl.MIN_AGREE}, HEAD_DILATE={DIL.get('Head', 2)}) ==", flush=True)
    print(f"   resume: {len(done)} plates already done", flush=True)
    skel = cl.skeleton_v2(save_preview=False)
    skel_d = bl._dilate(skel, 1)
    for cat in EYE_CATS:
        cdir = os.path.join(bl.LAYERS, bl.slug(cat))
        for val in sorted(bl.IDX[cat].keys()):
            if (cat, val) in done:
                continue
            rgba, n, cov = clean_eye_plate(cat, val, skel_d)
            Image.fromarray(rgba, "RGBA").save(
                os.path.join(cdir, f"{bl.slug(val)}.png"))
            a = rgba[:, :, 3] > 0
            print(f"  [{cat}] {val:<20} n={n:3d} alpha={cov:5.1f}% "
                  f"mini<50={cl.mini_count(a)}", flush=True)
            done.add((cat, val))
            _save_progress(done)
    cl._clear_img_dir()
    print("== eye clean done ==", flush=True)


# ============================================================ before snapshot (git)
def _extract_before():
    tmp = tempfile.mkdtemp(prefix="cs_eyes_before_")
    for cat in EYE_CATS:
        d = os.path.join(tmp, bl.slug(cat))
        os.makedirs(d, exist_ok=True)
        for val in sorted(bl.IDX[cat].keys()):
            rel = f"layers/{bl.slug(cat)}/{bl.slug(val)}.png"
            with open(os.path.join(d, f"{bl.slug(val)}.png"), "wb") as f:
                subprocess.run(["git", "-C", bl.REPO, "show", f"HEAD:{rel}"],
                               stdout=f, check=True)
    return tmp


# ============================================================ metrics
def eye_mini_total(root):
    tot, per = 0, {}
    for cat in EYE_CATS:
        for val in sorted(bl.IDX[cat].keys()):
            p = os.path.join(root, bl.slug(cat), f"{bl.slug(val)}.png")
            a = np.asarray(Image.open(p).convert("RGBA"))[:, :, 3] > 0
            m = cl.mini_count(a)
            per[(cat, val)] = m
            tot += m
    return tot, per


# ============================================================ zoomed contact sheet
def _content_bbox(alpha, min_comp=80, margin=12):
    """Square bbox of the principal content (components >= min_comp px) + margin."""
    lbl, n = ndimage.label(alpha)
    if n == 0:
        return (0, 0, W, H)
    counts = np.bincount(lbl.ravel())
    keep = [l for l in range(1, n + 1) if counts[l] >= min_comp]
    mask = np.isin(lbl, keep) if keep else (alpha > 0)
    ys, xs = np.where(mask)
    if len(xs) == 0:
        ys, xs = np.where(alpha > 0)
    x0, x1 = xs.min(), xs.max() + 1
    y0, y1 = ys.min(), ys.max() + 1
    x0, y0 = max(0, x0 - margin), max(0, y0 - margin)
    x1, y1 = min(W, x1 + margin), min(H, y1 + margin)
    # make square around the centre
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = max(x1 - x0, y1 - y0)
    hx = side / 2
    nx0 = int(max(0, min(cx - hx, W - side)))
    ny0 = int(max(0, min(cy - hx, H - side)))
    side = int(min(side, W))
    return (nx0, ny0, min(nx0 + side, W), min(ny0 + side, H))


def _checker(size, cell=8, c1=(205, 205, 205), c2=(165, 165, 165)):
    idx = (np.indices((size, size)).sum(0) // cell) % 2
    return np.where(idx[..., None] == 0, np.array(c1), np.array(c2)).astype(np.uint8)


def _crop_thumb(rgba, bbox, tsize):
    x0, y0, x1, y1 = bbox
    im = Image.fromarray(rgba, "RGBA").crop((x0, y0, x1, y1)).resize(
        (tsize, tsize), Image.NEAREST)
    bg = Image.fromarray(_checker(tsize), "RGB").convert("RGBA")
    return Image.alpha_composite(bg, im).convert("RGB")


def zoom_diff_sheet(before_dir, after_dir, out_path, tsize=150):
    font = ImageFont.load_default()
    entries = [(cat, val) for cat in EYE_CATS
               for val in sorted(bl.IDX[cat].keys())]
    cols = 5                       # 5 before/after pairs per row
    pair_w = tsize * 2 + 4
    lab_h, gap = 14, 10
    cw, ch = pair_w + gap, tsize + lab_h + gap
    rows = math.ceil(len(entries) / cols)
    canvas = Image.new("RGB", (cols * cw + gap, rows * ch + gap), (22, 22, 22))
    d = ImageDraw.Draw(canvas)
    for i, (cat, val) in enumerate(entries):
        bp = os.path.join(before_dir, bl.slug(cat), f"{bl.slug(val)}.png")
        ap = os.path.join(after_dir, bl.slug(cat), f"{bl.slug(val)}.png")
        ba = np.asarray(Image.open(bp).convert("RGBA"))
        aa = np.asarray(Image.open(ap).convert("RGBA"))
        # shared bbox so before/after are at the same crop
        bx = _content_bbox((ba[:, :, 3] > 0) | (aa[:, :, 3] > 0))
        r, c = divmod(i, cols)
        x, y = gap + c * cw, gap + r * ch
        canvas.paste(_crop_thumb(ba, bx, tsize), (x, y))
        canvas.paste(_crop_thumb(aa, bx, tsize), (x + tsize + 4, y))
        canvas.paste(Image.new("RGB", (2, tsize), (255, 90, 0)), (x + tsize + 1, y))
        d.text((x + 1, y + tsize + 2), f"{bl.slug(cat)[0]}e/{val}"[:26],
               fill=(210, 210, 210), font=font)
    canvas.save(out_path)
    print(f"  wrote {out_path} ({len(entries)} eye plates, before|after zoomed)",
          flush=True)


# ============================================================ orchestration
def qa_and_proofs(before_dir=None):
    proof = os.path.join(bl.REPO, "proof")
    os.makedirs(proof, exist_ok=True)
    if before_dir is None:
        before_dir = _extract_before()
    tot_before, _ = eye_mini_total(before_dir)
    tot_after, per_after = eye_mini_total(bl.LAYERS)
    print(f"  eye mini<50: {tot_before} -> {tot_after}", flush=True)
    worst = sorted(per_after, key=lambda k: per_after[k], reverse=True)[:6]
    print("  worst after:", [(f"{c[:1]}e/{v}", per_after[(c, v)]) for c, v in worst],
          flush=True)
    out = os.path.join(proof, "eyes_pass_diff.png")
    zoom_diff_sheet(before_dir, bl.LAYERS, out)
    print("== QA recompose (head-top) ==", flush=True)
    scores, mean = cl.qa_recompose()
    for t in sorted(scores):
        print(f"    #{t}: {scores[t]:.2f}%", flush=True)
    print(f"  QA mean: {mean:.2f}%", flush=True)
    json.dump({"eye_mini_before": tot_before, "eye_mini_after": tot_after,
               "qa_mean": round(mean, 3),
               "qa_scores": {str(k): round(v, 3) for k, v in scores.items()},
               "worst_after": [{"cat": c, "val": v, "mini": per_after[(c, v)]}
                               for c, v in worst],
               "head_dilate": DIL.get("Head", 2)},
              open("/tmp/cs_eyes_summary.json", "w"), indent=2)
    print("  summary -> /tmp/cs_eyes_summary.json", flush=True)
    return tot_before, tot_after, mean


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--head-dilate" in args:
        i = args.index("--head-dilate")
        DIL["Head"] = int(args[i + 1])
        del args[i:i + 2]
    cmd = args[0] if args else "clean"
    if cmd == "qa":
        qa_and_proofs()
    else:
        clean_all_eyes()
        qa_and_proofs()
