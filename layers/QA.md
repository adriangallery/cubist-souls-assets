# Trait library QA — z-order validation

Recomposition test: for each token, alpha-composite its 8 recovered plates and compare pixel-by-pixel against the original flattened PNG.

**Metric:** % of pixels whose max RGB channel difference is <= 10, ignoring a 1px anti-aliasing border.

## Final z-order (bottom -> top)

`Art Background > Base > Clothes > Mouth > Nose > Left Eye > Right Eye > Head`

Selected as **head-top** — highest average match (**97.13%**) across 10 varied tokens (incl. #136, the known control).

## Per-token match (best z-order)

| token | match % |
|------:|--------:|
| #136 (control) | 97.14% |
| #1 | 97.30% |
| #17 | 96.97% |
| #42 | 97.24% |
| #231 | 97.46% |
| #512 | 96.73% |
| #1337 | 96.68% |
| #2600 | 97.49% |
| #5000 | 96.77% |
| #8888 | 97.50% |

## Orders tried

| order | avg match % |
|-------|------------:|
| head-top | 97.13% |
| eyes-below-head | 97.12% |
| hypothesis (AB>Base>Clothes>Head>Mouth>Nose>LEye>REye) | 96.35% |
| clothes-over-head | 96.22% |

## Cleaning pass (tools/clean_library.py — 2026-07-16)

The v1 plates (loose ~10-tolerance mode vote) carried three families of dirt:
(a) floating colour motes far from the trait (random vote agreements),
(b) thin stray lines (contour-skeleton residue + splinters of neighbour traits' edges),
(c) grey "ghosts" inside Base plates where a feature almost always sits on top.

Deterministic fixes, in order (no generative tools — faithful to the original art):

1. **Exact re-vote** — occluder-aware per-pixel vote with EXACT colour match
   (max channel diff <= 2). Keep a pixel when >= 40% of the *visible* samples agree
   exactly, with an absolute floor of >= 3 exact agreers (kills the sparse-region
   coincidences). Samples re-downloaded in streaming per value (n = 60 base &
   art-background, 40 clothes, 30 the rest), cache wiped per plate.
2. **Connected-component hygiene** (scipy.ndimage) — drop alpha components < 40 px
   whose pixels sit > 60 px from the nearest principal (>= 100 px) component
   (distance guard protects legit multi-piece traits: earrings, design motes, ears);
   drop line fragments (bbox min side <= 2 px and area < 80 px).
3. **Skeleton v2** — global contour mask recomputed by exact vote over 60 random
   tokens (>= 50% exact agreement = global-constant; ~0.7% of canvas, same coverage
   as the v1 std<14 estimate), dilated 1 px, subtracted from every category except
   Art Background and Base.
4. **Base de-ghosting** — on Base plates the winning vote needs >= 55% support among
   visible samples; below that the pixel goes transparent (an honest hole that the
   upper feature covers on recompose beats a grey smear).

### Results

- **Mini-components (< 50 px) across the 145 plates: 14,296 -> 695 (-95.1%).**
- **QA recomposition mean: 97.13% -> 97.88%** (exact vote also *improved* fidelity).
- Worst plate after cleaning: 20 mini-components (Right Eye / Amphibious; was 277).
  Residues are AA slivers at trait borders and legit small design pieces kept by the
  conservative distance guard.
- Proofs: `proof/contact_before.png`, `proof/contact_after.png` (145 plates on
  checkerboard), `proof/cleaning_diff.png` (8 worst cases before/after),
  `proof/skeleton_v2.png`.

### Per-token match after cleaning (head-top order)

| token | match % |
|------:|--------:|
| #136 (control) | 97.85% |
| #1 | 97.90% |
| #17 | 97.76% |
| #42 | 97.84% |
| #231 | 98.16% |
| #512 | 97.83% |
| #1337 | 97.57% |
| #2600 | 98.42% |
| #5000 | 97.57% |
| #8888 | 97.92% |

## Global-skeleton decision

The contour skeleton (facial square, neck line, ear-with-X) is constant across the whole collection, so every plate's variance mask captures it. We subtract it (make it transparent) from all categories **except Art Background and Base**:

- **Base** legitimately owns the character/face outline, so the skeleton must live there and be the single source of those pixels on recompose.

- **Art Background** is the bottom layer; its skeleton region is always painted over by Base during recomposition, so keeping it is harmless and removing it risks eroding legitimate background edges.

- All higher categories (Clothes, Head, Mouth, Nose, Left/Right Eye) have the skeleton removed so they contribute only their own trait pixels.

## Eyes pass (tools/clean_eyes.py — 2026-07-16, surgical re-extraction of the 40 eye plates)

The Left/Right Eye plates sit under the frequent footprint of Head (the top layer),
so after occlusion masking few samples stay visible per pixel. With n = 30 the
cleaning pass's ">= 40% of visible + absolute floor 3" rule both let casual
agreements through (surviving colour motes) and dropped real content on split votes
(erosion: bites in All Seeing Eye, holes in Dead Man, ghosts in Asymmetrical).
Fix = stronger statistics, not more aggressive filtering:

- **n = 100 samples per value** (every eye value has >= 464 tokens), streamed
  (download -> vote -> delete; cache stays < 40 MB).
- **Eligibility**: a pixel needs >= 10 visible (unoccluded) samples, else transparent.
- **Vote**: the exact-colour winner (tol <= 2) keeps the pixel with >= 75% of the
  visible samples AND >= 6 exact agreers.
- Component hygiene + skeleton v2 identical to the cleaning pass. Head footprint
  dilation stayed at 2 px (n = 100 alone fixed the erosion; no need to soften it).

**Why 75% here vs the cleaning pass's 40%** — measured on Right Eye / Spare Coin
(n = 100), the support (votes/visible) distribution is bimodal: true trait pixels
sit at ~0.95-1.0 (the trait composites pixel-identically wherever visible) while
~0.45-0.55 holds two artifact families the 40% bar had let in:

1. a dark-navy blob at the LEFT-pupil position of Right Eye plates — Right Eye's
   only occluder is Head, so left-eye-region pixels are never masked, and about
   half the collection's Left Eye values paint the same dark navy there;
2. phantom eyebrow-arc fragments that are BASE-owned (only ~half the bases draw
   them; verified 0/5 random Spare Coin tokens carry the arc — an earlier 3/3
   "confirmation" was selection bias from picking least-Head-occluded tokens).

0.75 splits the modes with margin. Erosion does not return: a true trait pixel
visible in only 12/100 samples still shows 12/12 = 100% support (the n = 30 erosion
came from the weak absolute floor, not from the fraction). Known cost: 1-2 px
outlines blended with varying underlying art (e.g. the thin diamond frame around
Amphibious) have no exact-colour majority at ANY threshold; v1 kept broken dashes
of them, this pass drops most of those dashes — cleaner plates, and the recompose
QA (below) shows fidelity is unaffected.

Verified by eye on the zoomed before/after sheet: All Seeing Eye no longer has
mordiscos (its big triangular notch is REAL trait transparency — the nose shows
through it on every source token), Dead Man's holes are filled, Asymmetrical's
ghosts are gone.

### Results

Eye-only mini-components (<50 px across the 40 eye plates): **206 -> 43** (79% reduction).

Recompose QA (10 tokens, head-top z-order): **mean 97.782%** (>= the 97.5% floor; unchanged fidelity vs the general pass).

Per-token: #136 97.69%, #1 97.698%, #17 97.866%, #42 97.771%, #231 98.093%, #512 97.683%, #1337 97.487%, #2600 98.327%, #5000 97.447%, #8888 97.761%

Worst remaining plates (residual AA slivers / legitimate small pieces the distance guard keeps): Right Eye/Amphibious (17), Right Eye/Spare Coin (5), Right Eye/Eyeshadow (4), Right Eye/Flying Kite (3), Right Eye/Gaze (3), Right Eye/Safe Circuit (3).

Proof: `proof/eyes_pass_diff.png` (worst cases, before | after, zoomed to the
trait bbox). PENDING (separate task): per-option `bbox` in `manifest.json` +
builder change to render zoomed thumbnails for the small facial traits.
