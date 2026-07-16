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

## Global-skeleton decision

The contour skeleton (facial square, neck line, ear-with-X) is constant across the whole collection, so every plate's variance mask captures it. We subtract it (make it transparent) from all categories **except Art Background and Base**:

- **Base** legitimately owns the character/face outline, so the skeleton must live there and be the single source of those pixels on recompose.

- **Art Background** is the bottom layer; its skeleton region is always painted over by Base during recomposition, so keeping it is harmless and removing it risks eroding legitimate background edges.

- All higher categories (Clothes, Head, Mouth, Nose, Left/Right Eye) have the skeleton removed so they contribute only their own trait pixels.
