#!/usr/bin/env python3
"""Generate rarity/rarity.json for Cubist Souls (10000 tokens).

Method: rarity score = sum over 8 trait categories of 1/relative_frequency.
Absent value in a category is treated as its own "None" value with its own
frequency. Rank 1 = rarest (highest score); ties broken by tokenId ascending.
Tiers by rank percentile. The 4 honorary 1/1 tokens are forced to tier 4.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATS = ['Art Background', 'Base', 'Clothes', 'Mouth', 'Head',
        'Left Eye', 'Nose', 'Right Eye']
HONORARIES = [90, 163, 294, 600]
N = 10000

TIER_NAMES = ["Collection", "Catalogued", "Featured", "Exhibition", "Masterpiece"]
TIER_MULT = [1.0, 1.15, 1.3, 1.5, 2.0]
TIER_EMOJI = ["\U0001F9F1", "\U0001F4CB", "\U0001F3AF", "\U0001F5BC", "\U0001F3FA"]
TIER_COUNTS = [6000, 2500, 1000, 400, 100]  # tier 0..4
# cumulative cut points from rarest: tier4=top100, tier3=next400(->500),
# tier2=next1000(->1500), tier1=next2500(->4000), tier0=rest(6000)

d = json.load(open(os.path.join(ROOT, 'meta-all.json')))

# token -> {cat: value} using "None" for absent
tokens = {}
from collections import Counter
freq = {c: Counter() for c in CATS}
for i in range(1, N + 1):
    v = d[str(i)]
    attrs = {a['trait_type']: a['value'] for a in v['attributes']}
    vals = {}
    for c in CATS:
        val = attrs.get(c, 'None')
        vals[c] = val
        freq[c][val] += 1
    tokens[i] = vals

# rarity score
scores = {}
for i in range(1, N + 1):
    s = 0.0
    for c in CATS:
        rel = freq[c][tokens[i][c]] / N
        s += 1.0 / rel
    scores[i] = s

# rank: sort by score desc, tokenId asc
order = sorted(range(1, N + 1), key=lambda i: (-scores[i], i))
rank = {}
for idx, tid in enumerate(order):
    rank[tid] = idx + 1  # 1-based

# assign tiers by rank thresholds (rarest first)
# rank 1..100 -> tier4, 101..500 -> tier3, 501..1500 -> tier2,
# 1501..4000 -> tier1, 4001..10000 -> tier0
def tier_for_rank(r):
    if r <= 100: return 4
    if r <= 500: return 3
    if r <= 1500: return 2
    if r <= 4000: return 1
    return 0

tier = {i: tier_for_rank(rank[i]) for i in range(1, N + 1)}

# Force honoraries to tier 4 (they already rank top due to unique 1/1, but guard).
for h in HONORARIES:
    tier[h] = 4

# ranks array position i = rank of tokenId i+1
ranks = [rank[i] for i in range(1, N + 1)]
tiers_str = ''.join(str(tier[i]) for i in range(1, N + 1))

out = {
    "version": 1,
    "generated": "2026-07-19",
    "method": "sum of inverse trait frequency over 8 categories; tiers by rank percentile",
    "tierNames": TIER_NAMES,
    "tierMultipliers": TIER_MULT,
    "tierEmoji": TIER_EMOJI,
    "tierCounts": TIER_COUNTS,
    "tiers": tiers_str,
    "ranks": ranks,
}

os.makedirs(os.path.join(ROOT, 'rarity'), exist_ok=True)
with open(os.path.join(ROOT, 'rarity', 'rarity.json'), 'w') as f:
    json.dump(out, f, separators=(',', ':'))

# stats for report
vals = sorted(scores.values())
mn, mx = vals[0], vals[-1]
med = (vals[N // 2 - 1] + vals[N // 2]) / 2
print(f"score min={mn:.3f} max={mx:.3f} median={med:.3f}")
print("top10 (rank, tokenId, score):")
for tid in order[:10]:
    print(f"  {rank[tid]:>3} #{tid} score={scores[tid]:.2f} tier={tier[tid]} {d[str(tid)]['name']}")
print("wrote rarity/rarity.json")
