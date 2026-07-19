# Cubist Souls — Rarity dataset (`rarity.json`)

Rarity data for the 10,000-token Cubist Souls collection, feeding the
**Museum Hours** points system.

## Method

1. **Trait frequency** — for each of the 8 categories (`Art Background`, `Base`,
   `Clothes`, `Mouth`, `Head`, `Left Eye`, `Nose`, `Right Eye`), count how often
   each value appears across all 10,000 tokens. A missing value in a category is
   treated as its own value `"None"` with its own frequency.
2. **Rarity score** — per token, `score = Σ (1 / relative_frequency)` over its 8
   traits (classic inverse-frequency rarity score). Higher = rarer.
3. **Rank** — tokens sorted by score descending (rank 1 = rarest). Ties broken by
   `tokenId` ascending. Ranks are a permutation of `1..10000`.
4. **Tiers** — assigned by rank percentile:

   | Tier | Name        | Emoji | Rank range   | Count | Multiplier |
   |------|-------------|-------|--------------|-------|------------|
   | 4    | Masterpiece | 🏺    | 1–100        | 100   | 2.0        |
   | 3    | Exhibition  | 🖼    | 101–500      | 400   | 1.5        |
   | 2    | Featured    | 🎯    | 501–1500     | 1000  | 1.3        |
   | 1    | Catalogued  | 📋    | 1501–4000    | 2500  | 1.15       |
   | 0    | Collection  | 🧱    | 4001–10000   | 6000  | 1.0        |

The 4 honorary **1/1** tokens (`#90`, `#163`, `#294`, `#600`) carry a single
`1/1` attribute instead of the 8 categories; their unique-value frequency puts
them at the top of the ranking, and they are additionally pinned to tier 4.

## Format (`rarity.json`)

```jsonc
{
  "version": 1,
  "generated": "2026-07-19",
  "method": "sum of inverse trait frequency over 8 categories; tiers by rank percentile",
  "tierNames":       ["Collection","Catalogued","Featured","Exhibition","Masterpiece"], // index = tier
  "tierMultipliers": [1.0, 1.15, 1.3, 1.5, 2.0],
  "tierEmoji":       ["🧱","📋","🎯","🖼","🏺"],
  "tierCounts":      [6000, 2500, 1000, 400, 100],
  "tiers": "<10000-char string of digits 0-4; position i = tier of tokenId i+1>",
  "ranks": [ /* 10000 ints; position i = rank of tokenId i+1; values 1..10000, no repeats */ ]
}
```

Lookup for token `id` (1-based): `tier = tiers[id-1]`, `rank = ranks[id-1]`.

## Regenerate / verify

```bash
python3 scripts/gen_rarity.py   # writes rarity/rarity.json
python3 scripts/qa_rarity.py    # verifies counts, permutation, coherence, honoraries
```
