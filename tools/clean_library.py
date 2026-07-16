#!/usr/bin/env python3
"""Cleaning pass (phase 2) for the Cubist Souls trait library.

build_library.py recovers the 145 plates by an occluder-aware per-pixel MODE with a
loose colour tolerance (~10). That tolerance lets the vote agree by accident, which
leaves three families of dirt on the plates (diagnosed 16-jul, verified visually):

  (a) floating colour motes far from the trait (random agreements of the loose vote);
  (b) thin stray lines / fragments (contour-skeleton residue + splinters of neighbour
      traits' edges);
  (c) grey "ghosts" inside the Base plates, in the eye/mouth/nose regions, where a
      feature almost always sits on top so the vote is contaminated.

This script re-derives every plate deterministically (NO generative / inpainting —
must stay faithful to the original art) with tighter rules, in this order:

  1. EXACT re-vote. The art composites pixel-identically, so the interior is exact and
     only anti-aliased edges wobble. We re-vote each plate with an exact RGB match
     (max channel diff <= EXACT_TOL=2, vs ~10 before): a pixel is kept when >= 40% of
     the VISIBLE (non-occluded, same as build_library) samples agree exactly. Samples
     are re-downloaded in STREAMING per value (download -> process -> delete) so the
     img cache never grows past a few tens of MB (disk directive: <500 MB, wipe after).
     n = 60 base/art-background, 40 clothes, 30 the rest.
  2. Connected-component hygiene (scipy.ndimage): drop alpha components < 40 px whose
     centroid/pixels sit > 60 px from the nearest principal (large) component — the
     distance guard protects legit multi-piece traits (earrings, design motes, ears);
     when in doubt, keep. Also drop line components (bbox min side <= 2 and area < 80).
  3. Skeleton v2: recompute the global contour mask by EXACT vote over 60 random
     tokens, dilate 1 px, and subtract it from every category except Art Background
     and Base (where the outline legitimately lives).
  4. Base de-ghosting: on the Base plates, pixels whose winning vote has < 55% support
     among visible samples go transparent (an honest hole the upper feature covers on
     recompose beats a grey smear).
  5. QA: (i) recompose the 10 QA tokens (head-top order) — mean must stay >= 97%;
     (ii) two contact sheets over a checkerboard (before from git, after) + a worst-case
     before/after diff. Cleanliness metric = total sub-50px components across 145 plates.

Usage:
  python3 clean_library.py             # full clean + QA + proofs
  python3 clean_library.py skel        # just compute/preview skeleton v2 (tuning)
  python3 clean_library.py test <Cat> <Val>   # clean one plate, print stats (no save)
  python3 clean_library.py qa          # QA recompose + contact sheets only
"""
import os, sys, glob, math, random, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_library as bl

H = W = 768

# ---- exact re-vote ------------------------------------------------------------
EXACT_TOL   = 2       # max per-channel diff for two samples to be "exactly" equal
VALID_FRAC  = 0.40    # keep a pixel if >= this fraction of visible samples agree
BASE_FRAC   = 0.55    # base de-ghosting: stricter support on the Base plates
MIN_VALID   = 3       # need at least this many visible (unoccluded) samples
MIN_AGREE   = 3       # and at least this many that agree EXACTLY (kills the sparse-
                      # region coincidences that a bare 40%-of-few-samples lets in)
CAP         = {"Art Background": 60, "Base": 60, "Clothes": 40}
DEF_CAP     = 30
STRATIFY    = {"Art Background", "Base", "Clothes"}
KEEP_SKELETON = {"Art Background", "Base"}
BUILD_ORDER = bl.BUILD_ORDER          # top-down: occlusion masks read cleaned plates
ZORDER      = bl.ZORDER

# ---- skeleton v2 --------------------------------------------------------------
SKEL_TOKENS = 60
SKEL_FRAC   = 0.50    # global-constant frac; 0.50 -> ~0.7% canvas == original std<14
SKEL_SEED   = 123

# ---- component hygiene --------------------------------------------------------
MINI_AREA     = 50    # the cleanliness metric counts components smaller than this
SMALL_AREA    = 40    # candidate motes to drop when far from a principal component
FAR_DIST      = 60    # ...only if this far (px) from the nearest principal pixel
PRINCIPAL_MIN = 100   # a component this big or bigger anchors legit geometry
LINE_AREA     = 80    # line fragments: bbox min side <= 2 and area < this
LINE_SIDE     = 2

SLUG = bl.slug


# ============================================================ streaming samples
def _drop_imgs(ids):
    for t in ids:
        try:
            os.remove(f"{bl.IMG_DIR}/{t}.png")
        except OSError:
            pass


def _clear_img_dir():
    for p in glob.glob(f"{bl.IMG_DIR}/*.png"):
        try:
            os.remove(p)
        except OSError:
            pass


def clean_samples(cat, val, cap):
    """Download (streaming) up to `cap` valid samples of (cat,val)."""
    ids = bl.stratified_ids(cat, val, cap * 2) if cat in STRATIFY else IDX_LOCAL(cat, val)
    chosen, i = [], 0
    while len(chosen) < cap and i < len(ids):
        need = cap - len(chosen)
        batch = ids[i:i + need]
        bl.fetch_all(batch)
        for t in batch:
            if bl._valid(f"{bl.IMG_DIR}/{t}.png"):
                chosen.append(t)
        i += len(batch)
    return chosen


def IDX_LOCAL(cat, val):
    return [t for t in bl.IDX[cat][val] if t not in bl.HONORARIES]


def stack_u8(ids):
    return np.stack([bl.arr(t).astype(np.uint8) for t in ids], 0)   # N,H,W,3


# ============================================================ exact vote
def exact_vote(su8, ids, cat, frac):
    """Occluder-aware EXACT per-pixel vote. Returns (color uint8 HxWx3, alpha bool HxW).

    For each sample we exclude the pixels its own upper layers cover (same occlusion
    model as build_library). A pixel is kept when, among the VISIBLE samples, the most
    popular exact colour is shared by >= `frac` of them (and by >= MIN_AGREE samples,
    with >= MIN_VALID visible). Colour = mean of the agreeing samples (kills AA noise)."""
    n = su8.shape[0]
    valid = np.stack([~bl._occluded(t, cat) for t in ids], 0)        # N,H,W bool
    s16 = su8.astype(np.int16)
    agree = np.zeros((n, H, W), dtype=np.int16)
    for i in range(n):
        m = (np.abs(s16 - s16[i]).max(3) <= EXACT_TOL) & valid       # N,H,W
        m &= valid[i]                                                # both visible
        cnt = m.sum(0).astype(np.int16)
        cnt[~valid[i]] = 0
        agree[i] = cnt
    best = agree.argmax(0)                                           # H,W anchor sample
    votes = agree.max(0).astype(np.float32)
    nvalid = valid.sum(0).astype(np.float32)
    alpha = (nvalid >= MIN_VALID) & (votes >= MIN_AGREE) & \
            (votes / np.clip(nvalid, 1, None) >= frac)
    anchor = np.take_along_axis(s16, best[None, :, :, None], 0)[0]   # H,W,3
    inlier = (np.abs(s16 - anchor[None]).max(3) <= EXACT_TOL) & valid
    color = (su8.astype(np.float32) * inlier[..., None]).sum(0) / \
            np.clip(inlier.sum(0)[..., None], 1, None)
    return color.astype(np.uint8), alpha


# ============================================================ skeleton v2
def skeleton_v2(save_preview=False):
    all_ids = [t for t in range(1, 10001) if t not in bl.HONORARIES]
    random.seed(SKEL_SEED)
    toks = sorted(random.sample(all_ids, SKEL_TOKENS))
    print(f"  skeleton v2: exact vote over {len(toks)} random tokens", flush=True)
    bl.fetch_all(toks)
    s16 = np.stack([bl.arr(t).astype(np.int16) for t in toks], 0)    # N,H,W,3
    n = s16.shape[0]
    agree = np.zeros((H, W), dtype=np.int16)
    for i in range(n):
        cnt = (np.abs(s16 - s16[i]).max(3) <= EXACT_TOL).sum(0).astype(np.int16)  # H,W
        agree = np.maximum(agree, cnt)
    skel = (agree.astype(np.float32) / n) >= SKEL_FRAC
    print(f"  skeleton covers {skel.mean()*100:.1f}% of the canvas "
          f"(frac>={SKEL_FRAC})", flush=True)
    _drop_imgs(toks)
    if save_preview:
        prev = np.zeros((H, W, 4), np.uint8)
        prev[skel] = (255, 0, 0, 255)
        Image.fromarray(prev, "RGBA").save(os.path.join(bl.REPO, "proof", "skeleton_v2.png"))
    return skel


# ============================================================ component hygiene
def hygiene(alpha):
    a = alpha.copy()
    lbl, n = ndimage.label(a)
    if n == 0:
        return a
    counts = np.bincount(lbl.ravel())
    principal_labels = [l for l in range(1, n + 1) if counts[l] >= PRINCIPAL_MIN]
    if principal_labels:
        principal = np.isin(lbl, principal_labels)
        dist = ndimage.distance_transform_edt(~principal)
    else:
        dist = None
    slices = ndimage.find_objects(lbl)
    remove = []
    for c in range(1, n + 1):
        sl = slices[c - 1]
        if sl is None:
            continue
        area = int(counts[c])
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if area < LINE_AREA and min(h, w) <= LINE_SIDE:
            remove.append(c)
        elif area < SMALL_AREA and dist is not None:
            sub = lbl[sl] == c
            if dist[sl][sub].min() > FAR_DIST:
                remove.append(c)
    if remove:
        a[np.isin(lbl, remove)] = False
    return a


def mini_count(alpha, thr=MINI_AREA):
    lbl, n = ndimage.label(alpha)
    if n == 0:
        return 0
    counts = np.bincount(lbl.ravel())[1:]
    return int((counts < thr).sum())


# ============================================================ one plate
def clean_plate(cat, val, skel_d):
    cap = CAP.get(cat, DEF_CAP)
    ids = clean_samples(cat, val, cap)
    su8 = stack_u8(ids)
    frac = BASE_FRAC if cat == "Base" else VALID_FRAC
    color, alpha = exact_vote(su8, ids, cat, frac)
    if cat not in KEEP_SKELETON:
        alpha = alpha & (~skel_d)
    alpha = hygiene(alpha)
    rgba = np.dstack([color, (alpha * 255).astype(np.uint8)])
    _drop_imgs(ids)
    bl._PLATE_ALPHA.pop((cat, val), None)
    return rgba, len(ids), float(alpha.mean() * 100.0)


# ============================================================ contact sheets
def _load_rgba(p):
    return np.asarray(Image.open(p).convert("RGBA"))


def _checker(size, cell=8, c1=(205, 205, 205), c2=(165, 165, 165)):
    idx = (np.indices((size, size)).sum(0) // cell) % 2
    out = np.where(idx[..., None] == 0, np.array(c1), np.array(c2)).astype(np.uint8)
    return out


def _thumb(rgba, tsize):
    im = Image.fromarray(rgba, "RGBA").resize((tsize, tsize), Image.LANCZOS)
    bg = Image.fromarray(_checker(tsize), "RGB").convert("RGBA")
    return Image.alpha_composite(bg, im).convert("RGB")


def _display_entries(root):
    """(label, path) for all 145 plates, ordered by z-order then value."""
    out = []
    for cat in ZORDER:
        for val in sorted(bl.IDX[cat].keys()):
            out.append((f"{cat[:3].lower()}/{val}",
                        os.path.join(root, SLUG(cat), f"{SLUG(val)}.png")))
    return out


def contact_sheet(root, out_path, cols=12, tsize=170):
    entries = _display_entries(root)
    font = ImageFont.load_default()
    lab_h, pad = 13, 4
    cw, ch = tsize + pad, tsize + lab_h + pad
    rows = math.ceil(len(entries) / cols)
    canvas = Image.new("RGB", (cols * cw + pad, rows * ch + pad), (22, 22, 22))
    d = ImageDraw.Draw(canvas)
    for i, (lab, p) in enumerate(entries):
        r, c = divmod(i, cols)
        x, y = pad + c * cw, pad + r * ch
        canvas.paste(_thumb(_load_rgba(p), tsize), (x, y))
        d.text((x + 1, y + tsize + 1), lab[:24], fill=(205, 205, 205), font=font)
    canvas.save(out_path)
    print(f"  wrote {out_path} ({len(entries)} plates)", flush=True)


def diff_sheet(items, out_path, tsize=256):
    """items: list of (cat, val, before_path, after_path, nb, na)."""
    font = ImageFont.load_default()
    cols_pairs, lab_h, gap = 2, 22, 12
    pair_w = tsize * 2 + 6
    cw, ch = pair_w + gap, tsize + lab_h + gap
    rows = math.ceil(len(items) / cols_pairs)
    canvas = Image.new("RGB", (cols_pairs * cw + gap, rows * ch + gap), (22, 22, 22))
    d = ImageDraw.Draw(canvas)
    for i, (cat, val, bp, ap, nb, na) in enumerate(items):
        r, c = divmod(i, cols_pairs)
        x, y = gap + c * cw, gap + r * ch
        canvas.paste(_thumb(_load_rgba(bp), tsize), (x, y))
        canvas.paste(_thumb(_load_rgba(ap), tsize), (x + tsize + 6, y))
        d.text((x + 1, y + tsize + 3),
               f"{cat}/{val}  before {nb} -> after {na} mini-comps",
               fill=(220, 220, 220), font=font)
    canvas.save(out_path)
    print(f"  wrote {out_path} ({len(items)} worst plates)", flush=True)


# ============================================================ QA recompose
def qa_recompose():
    order = ["Art Background", "Base", "Clothes", "Mouth", "Nose",
             "Left Eye", "Right Eye", "Head"]
    qa_ids = [t for t in [136, 1, 17, 42, 231, 512, 1337, 2600, 5000, 8888]
              if t not in bl.HONORARIES]
    scores = {}
    for t in qa_ids:
        bl.fetch_all([t])
        comp = bl._composite(bl._traits_of(t), order)
        scores[t] = bl._match_pct(comp, bl.arr(t))
        _drop_imgs([t])
    mean = sum(scores.values()) / len(scores)
    return scores, mean


# ============================================================ before metrics
def per_plate_mini(root):
    out = {}
    for cat in ZORDER:
        for val in sorted(bl.IDX[cat].keys()):
            a = _load_rgba(os.path.join(root, SLUG(cat), f"{SLUG(val)}.png"))[:, :, 3] > 0
            out[(cat, val)] = mini_count(a)
    return out


# ============================================================ orchestration
def full_clean(before_dir):
    proof = os.path.join(bl.REPO, "proof")
    os.makedirs(proof, exist_ok=True)
    bl._PLATE_ALPHA.clear()
    _clear_img_dir()

    print("== before metrics + contact sheet (from git snapshot) ==", flush=True)
    before_mini = per_plate_mini(before_dir)
    total_before = sum(before_mini.values())
    print(f"  total sub-{MINI_AREA}px components (before): {total_before}", flush=True)
    contact_sheet(before_dir, os.path.join(proof, "contact_before.png"))

    print("== cleaning 145 plates (streaming) ==", flush=True)
    skel = skeleton_v2(save_preview=True)
    skel_d = bl._dilate(skel, 1)
    for cat in BUILD_ORDER:
        cdir = os.path.join(bl.LAYERS, SLUG(cat))
        os.makedirs(cdir, exist_ok=True)
        for val in sorted(bl.IDX[cat].keys()):
            rgba, n, cov = clean_plate(cat, val, skel_d)
            Image.fromarray(rgba, "RGBA").save(os.path.join(cdir, f"{SLUG(val)}.png"))
            print(f"  [{cat}] {val:<24} n={n:2d} alpha={cov:5.1f}%", flush=True)

    print("== after metrics + contact sheet ==", flush=True)
    after_mini = per_plate_mini(bl.LAYERS)
    total_after = sum(after_mini.values())
    contact_sheet(bl.LAYERS, os.path.join(proof, "contact_after.png"))

    worst = sorted(before_mini, key=lambda k: before_mini[k], reverse=True)[:8]
    items = []
    for (cat, val) in worst:
        items.append((cat, val,
                      os.path.join(before_dir, SLUG(cat), f"{SLUG(val)}.png"),
                      os.path.join(bl.LAYERS, SLUG(cat), f"{SLUG(val)}.png"),
                      before_mini[(cat, val)], after_mini[(cat, val)]))
    diff_sheet(items, os.path.join(proof, "cleaning_diff.png"))

    print("== QA recompose (head-top) ==", flush=True)
    scores, mean = qa_recompose()
    for t in sorted(scores):
        print(f"    #{t}: {scores[t]:.2f}%", flush=True)
    print(f"  QA mean: {mean:.2f}%", flush=True)

    reduction = 100.0 * (total_before - total_after) / max(total_before, 1)
    print("\n================ CLEANING SUMMARY ================", flush=True)
    print(f"mini-components (<{MINI_AREA}px): {total_before} -> {total_after} "
          f"({reduction:.1f}% reduction)", flush=True)
    print(f"QA recomposition mean: {mean:.2f}%", flush=True)
    _write_summary_json(total_before, total_after, reduction, scores, mean,
                        before_mini, after_mini)
    _clear_img_dir()
    return total_before, total_after, mean, scores, before_mini, after_mini


def _write_summary_json(tb, ta, red, scores, mean, bm, am):
    worst = sorted(bm, key=lambda k: am[k], reverse=True)[:15]
    out = {
        "mini_before": tb, "mini_after": ta, "reduction_pct": round(red, 2),
        "qa_mean": round(mean, 3),
        "qa_scores": {str(k): round(v, 3) for k, v in scores.items()},
        "worst_after": [{"cat": c, "val": v, "before": bm[(c, v)], "after": am[(c, v)]}
                        for (c, v) in worst],
    }
    with open("/tmp/cs_clean_summary.json", "w") as f:
        json.dump(out, f, indent=2)


def _before_dir(args):
    """Snapshot of the pre-cleaning plates for the before/after comparison.
    Pass a directory as argument, or omit it to extract layers/ from git HEAD
    into a temp dir (valid as long as the cleaned plates are not yet committed)."""
    if args:
        return args[0]
    import subprocess, tempfile
    tmp = tempfile.mkdtemp(prefix="cs_layers_before_")
    subprocess.run(f"git -C '{bl.REPO}' archive HEAD layers | tar -x -C '{tmp}'",
                   shell=True, check=True)
    return os.path.join(tmp, "layers")


def _pending_plates():
    """Plates not yet regenerated by this pass: mtime <= manifest.json's."""
    ref = os.path.getmtime(os.path.join(bl.REPO, "manifest.json"))
    out = []
    for cat in BUILD_ORDER:
        for val in sorted(bl.IDX[cat].keys()):
            p = os.path.join(bl.LAYERS, SLUG(cat), f"{SLUG(val)}.png")
            if (not os.path.exists(p)) or os.path.getmtime(p) <= ref:
                out.append((cat, val))
    return out


def finish(before_dir):
    """After-phases only: metrics, contact_after, diff sheet, QA, summary."""
    proof = os.path.join(bl.REPO, "proof")
    before_mini = per_plate_mini(before_dir)
    total_before = sum(before_mini.values())
    print(f"  total sub-{MINI_AREA}px components (before): {total_before}", flush=True)
    after_mini = per_plate_mini(bl.LAYERS)
    total_after = sum(after_mini.values())
    contact_sheet(bl.LAYERS, os.path.join(proof, "contact_after.png"))
    worst = sorted(before_mini, key=lambda k: before_mini[k], reverse=True)[:8]
    diff_sheet([(c, v,
                 os.path.join(before_dir, SLUG(c), f"{SLUG(v)}.png"),
                 os.path.join(bl.LAYERS, SLUG(c), f"{SLUG(v)}.png"),
                 before_mini[(c, v)], after_mini[(c, v)]) for (c, v) in worst],
               os.path.join(proof, "cleaning_diff.png"))
    print("== QA recompose (head-top) ==", flush=True)
    scores, mean = qa_recompose()
    for t in sorted(scores):
        print(f"    #{t}: {scores[t]:.2f}%", flush=True)
    reduction = 100.0 * (total_before - total_after) / max(total_before, 1)
    print("\n================ CLEANING SUMMARY ================", flush=True)
    print(f"mini-components (<{MINI_AREA}px): {total_before} -> {total_after} "
          f"({reduction:.1f}% reduction)", flush=True)
    print(f"QA recomposition mean: {mean:.2f}%", flush=True)
    _write_summary_json(total_before, total_after, reduction, scores, mean,
                        before_mini, after_mini)
    _clear_img_dir()


def resume(before_dir):
    """Idempotent resume: clean only pending plates (mtime<=manifest), then finish."""
    bl._PLATE_ALPHA.clear()
    pend = _pending_plates()
    print(f"== resume: {len(pend)} pending plates ==", flush=True)
    if pend:
        if any(cat not in KEEP_SKELETON for cat, _ in pend):
            skel = skeleton_v2()
        else:
            skel = np.zeros((H, W), bool)   # KEEP_SKELETON cats never subtract it
        skel_d = bl._dilate(skel, 1)
        for cat, val in pend:
            rgba, n, cov = clean_plate(cat, val, skel_d)
            Image.fromarray(rgba, "RGBA").save(
                os.path.join(bl.LAYERS, SLUG(cat), f"{SLUG(val)}.png"))
            print(f"  [{cat}] {val:<24} n={n:2d} alpha={cov:5.1f}%", flush=True)
    finish(before_dir)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "clean"
    if cmd == "skel":
        _clear_img_dir()
        skeleton_v2(save_preview=True)
        _clear_img_dir()
    elif cmd == "test":
        cat, val = sys.argv[2], sys.argv[3]
        _clear_img_dir()
        skel = skeleton_v2()
        skel_d = bl._dilate(skel, 1)
        rgba, n, cov = clean_plate(cat, val, skel_d)
        a = rgba[:, :, 3] > 0
        print(f"[{cat}] {val}: n={n} alpha={cov:.1f}% mini<50={mini_count(a)}")
        Image.fromarray(rgba, "RGBA").save("/tmp/cs_test_plate.png")
        _clear_img_dir()
    elif cmd == "qa":
        scores, mean = qa_recompose()
        for t in sorted(scores):
            print(f"#{t}: {scores[t]:.2f}%")
        print(f"mean: {mean:.2f}%")
    elif cmd == "resume":
        resume(_before_dir(sys.argv[2:]))
    else:
        full_clean(_before_dir(sys.argv[1:] if cmd != "clean" else sys.argv[2:]))
