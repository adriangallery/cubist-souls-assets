# Cubist Souls — assets mirror

Durable copy of the original Pikkazo art + metadata for the tokens that have
been burned and freed as **Cubist Souls**.

Pikkazo's art lives on IPFS pinned by the original founder. If that pin ever
disappears, the Souls would lose their art. This repo is our own copy, served
for free and permanently via `raw.githubusercontent.com`, so each Soul keeps the
art of its particular token regardless of what happens to the Pikkazo pin.

## Layout

- `img/<id>.png`  — the original 768×768 Pikkazo artwork for token `<id>`.
- `meta/<id>.json` — the original Pikkazo metadata (source of the 8 cubist
  traits shown on each Soul).

Raw URLs (used by the `cubistsouls.vercel.app` metadata/image endpoints):

```
https://raw.githubusercontent.com/adriangallery/cubist-souls-assets/main/img/136.png
https://raw.githubusercontent.com/adriangallery/cubist-souls-assets/main/meta/136.json
```

## Trait library (`layers/` + `manifest.json` + `meta-all.json`)

The original per-trait transparent PNGs were never published — IPFS only holds
the 10000 flattened 768×768 images and their metadata. This repo now contains a
**recovered trait library**: the 145 trait values of the 8 categories as
individual RGBA 768×768 plates, rebuilt by *variance-differencing* the flattened
art (see `tools/build_library.py`):

- Every trait value composites pixel-identically on every token it appears on,
  so stacking samples of one value and keeping the pixels where the samples
  agree isolates the layer. Pure arithmetic on art the holders already own —
  no AI inpainting.
- Layers below the top can be occluded, so plates are recovered **top-down**:
  each category's recovered footprint becomes the occlusion mask for the
  categories below it, and occluded pixels are excluded from the per-pixel vote.
- A global "contour skeleton" mask (constant across the whole collection) is
  subtracted from every category except Art Background and Base.

**Z-order (bottom → top), validated by pixel-level recomposition QA
(`layers/QA.md`):**

```
Art Background > Base > Clothes > Mouth > Nose > Left Eye > Right Eye > Head
```

Head is the TOP layer — hair falls over eyes, shirt and everything else.

**To recompose a token**: read its 8 traits from `meta/<id>.json` (or
`meta-all.json`), then alpha-composite
`layers/<category-slug>/<value-slug>.png` in the z-order above
(slug = lowercase, spaces → hyphens). The 4 honorary 1/1s (#90 Mattie,
#163 Mich, #294 H0ld Sats, #600 Jereziz) are NOT compositions — their flat PNG
is the final piece; they are listed in `manifest.json.honoraries`.

`meta-all.json` maps `"<id>" → original metadata object` for all 10000 tokens.
Together with `layers/`, it is a **recomposable backup of the entire
collection** that no longer depends on the founder's IPFS pin.

## Adding a newly burned token

The Vercel endpoints reveal any burned token instantly by proxying IPFS, so a
new Soul is never blank. This repo is the *durability* layer — mirror each new
burn here so it no longer depends on Pikkazo's pin:

```sh
./mirror.sh 4321 8765      # ids to copy
git add img meta && git commit -m "mirror #4321 #8765" && git push
```

## Source CIDs (Pikkazo, ETH mainnet `0x6478b94dfa32F3eab600970D04B34615eE97484e`)

- images:   `QmVgPQtmUBVFK4YqiTQHSFuF1yWcWF3BKGvpXYwFFHfiBm`
- metadata: `QmPXUAzyddsQYPUjY2E7WDWedx7vMgdJGyj8a84rzFWmed`
