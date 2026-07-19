#!/usr/bin/env python3
"""QA for traits/index.json against meta-all.json.

Checks:
  - 8 categories present, each with exactly 10000 encoded entries
  - every encoded index is within its category value list
  - the 4 honoraries decode to "1 of 1" in every category
  - spot-check 5 tokens: decoded value == meta-all.json attribute value
Exits non-zero on any failure.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATS = ['Art Background', 'Base', 'Clothes', 'Mouth', 'Head',
        'Left Eye', 'Nose', 'Right Eye']
HONORARIES = {90, 163, 294, 600}
ONE_OF_ONE = '1 of 1'
N = 10000

d = json.load(open(os.path.join(ROOT, 'meta-all.json')))
idx = json.load(open(os.path.join(ROOT, 'traits', 'index.json')))
BASE = idx['base']

fail = 0
def check(cond, msg):
    global fail
    if not cond:
        print("FAIL:", msg); fail += 1

check(idx['categories'] == CATS, "category list mismatch")
check(idx['count'] == N, "count != 10000")

def decode(cat, tid):
    ch = idx['tokens'][cat][tid - 1]
    vi = ord(ch) - BASE
    return idx['values'][cat][vi]

for c in CATS:
    s = idx['tokens'][c]
    check(len(s) == N, f"{c}: {len(s)} entries, expected {N}")
    nvals = len(idx['values'][c])
    bad = [i for i, ch in enumerate(s) if not (0 <= ord(ch) - BASE < nvals)]
    check(not bad, f"{c}: {len(bad)} out-of-range indices")
    check(idx['values'][c][-1] == ONE_OF_ONE, f"{c}: last value is not '1 of 1'")

# Honoraries -> 1 of 1 everywhere
for h in HONORARIES:
    for c in CATS:
        check(decode(c, h) == ONE_OF_ONE, f"honorary #{h} {c} != '1 of 1'")

# Spot-check 5 tokens against meta-all.json
for tid in [1, 2, 5000, 7777, 9999]:
    attrs = {a['trait_type']: a['value'] for a in d[str(tid)]['attributes']}
    for c in CATS:
        expected = attrs.get(c, ONE_OF_ONE)
        got = decode(c, tid)
        check(got == expected, f"#{tid} {c}: got {got!r} expected {expected!r}")
    print(f"spot-check #{tid} OK ({d[str(tid)]['name']})")

if fail:
    print(f"\n{fail} check(s) FAILED"); sys.exit(1)
print("\nALL QA CHECKS PASSED")
