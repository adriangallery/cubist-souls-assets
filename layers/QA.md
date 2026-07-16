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
