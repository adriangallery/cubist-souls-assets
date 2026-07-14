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
