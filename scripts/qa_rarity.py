#!/usr/bin/env python3
"""QA verification for rarity/rarity.json. Exits non-zero on any failure."""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
r = json.load(open(os.path.join(ROOT, 'rarity', 'rarity.json')))
d = json.load(open(os.path.join(ROOT, 'meta-all.json')))
N = 10000
HON = [90, 163, 294, 600]
TIER_COUNTS = [6000, 2500, 1000, 400, 100]
CUM_MAXRANK = {4: 100, 3: 500, 2: 1500, 1: 4000, 0: 10000}
fail = []

tiers = r['tiers']
ranks = r['ranks']

# 1. tiers length + charset + counts
if len(tiers) != N: fail.append(f"tiers len {len(tiers)} != {N}")
if any(c not in '01234' for c in tiers): fail.append("tiers has non 0-4 char")
from collections import Counter
tc = Counter(tiers)
for t in range(5):
    if tc.get(str(t), 0) != TIER_COUNTS[t]:
        fail.append(f"tier {t} count {tc.get(str(t),0)} != {TIER_COUNTS[t]}")

# 2. ranks permutation of 1..N
if len(ranks) != N: fail.append(f"ranks len {len(ranks)} != {N}")
if sorted(ranks) != list(range(1, N + 1)): fail.append("ranks not a permutation of 1..N")

# 3. honoraries tier 4
for h in HON:
    if tiers[h - 1] != '4': fail.append(f"honorary #{h} tier={tiers[h-1]} != 4")

# 4. coherence: token in tier T has rank <= cum max for T
for i in range(N):
    t = int(tiers[i])
    if ranks[i] > CUM_MAXRANK[t]:
        fail.append(f"token #{i+1} tier{t} rank {ranks[i]} > {CUM_MAXRANK[t]}")
        if len([f for f in fail if 'coherence' in f]) > 3: break

# metadata field checks
assert r['tierCounts'] == TIER_COUNTS, "tierCounts field mismatch"
assert r['version'] == 1
assert len(r['tierNames']) == 5 and len(r['tierMultipliers']) == 5 and len(r['tierEmoji']) == 5

if fail:
    print("QA FAILED:")
    for f in fail[:20]:
        print("  -", f)
    sys.exit(1)
print("QA PASSED: all checks green")
print(f"  tiers counts: {[tc[str(t)] for t in range(5)]}")
print(f"  ranks: permutation of 1..{N} OK")
print(f"  honoraries {HON} all tier 4 OK")

# sample 3 tokens per tier for visual sanity (by rank within tier)
CATS = ['Art Background','Base','Clothes','Mouth','Head','Left Eye','Nose','Right Eye']
by_tier = {t: [] for t in range(5)}
for i in range(N):
    by_tier[int(tiers[i])].append((ranks[i], i + 1))
for t in range(4, -1, -1):
    lst = sorted(by_tier[t])
    picks = [lst[0], lst[len(lst)//2], lst[-1]]
    print(f"\n=== Tier {t} ({['Collection','Catalogued','Featured','Exhibition','Masterpiece'][t]}) samples ===")
    for rk, tid in picks:
        v = d[str(tid)]
        attrs = {a['trait_type']: a['value'] for a in v['attributes']}
        tr = ', '.join(f"{c}:{attrs.get(c,'None')}" for c in CATS) if 'Art Background' in attrs else v['name']+' (honorary 1/1)'
        print(f"  rank {rk} #{tid} [{v['name']}] {tr}")
