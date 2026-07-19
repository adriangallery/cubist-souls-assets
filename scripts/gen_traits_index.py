#!/usr/bin/env python3
"""Generate traits/index.json for Cubist Souls (10000 tokens).

Compact, client-side friendly trait dataset for the gallery filter.

Format (see traits/README.md):
  {
    "version": 1,
    "generated": "YYYY-MM-DD",
    "count": 10000,
    "categories": ["Art Background", ...],          # 8 categories, fixed order
    "values": { "<category>": ["Alpha", "Beta", ..., "1 of 1"] },
    "tokens": { "<category>": "<10000-char string>" }
  }

For each category `tokens[cat]` is a string of exactly 10000 chars; char at
position i encodes the value index of tokenId (i+1) as chr(48 + index).
Decode in JS:  values[cat][ str.charCodeAt(i) - 48 ]

The 4 honorary 1/1 tokens (#90 #163 #294 #600) carry no standard traits, so a
synthetic "1 of 1" value is appended to every category and those tokens point
to it in all 8 categories.
"""
import json, os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATS = ['Art Background', 'Base', 'Clothes', 'Mouth', 'Head',
        'Left Eye', 'Nose', 'Right Eye']
HONORARIES = {90, 163, 294, 600}
ONE_OF_ONE = '1 of 1'
N = 10000
BASE = 48  # index -> chr(BASE + index); keeps every char printable & JSON-safe

d = json.load(open(os.path.join(ROOT, 'meta-all.json')))

# Collect the distinct values per category from the standard tokens.
value_sets = {c: set() for c in CATS}
for i in range(1, N + 1):
    tok = d[str(i)]
    attrs = {a['trait_type']: a['value'] for a in tok['attributes']}
    for c in CATS:
        if c in attrs:
            value_sets[c].add(attrs[c])

# Sorted value list per category, with the synthetic 1/1 value appended last.
values = {}
val_index = {}
for c in CATS:
    ordered = sorted(value_sets[c]) + [ONE_OF_ONE]
    values[c] = ordered
    val_index[c] = {v: k for k, v in enumerate(ordered)}
    if len(ordered) - 1 > (126 - BASE):
        raise SystemExit(f"category {c!r} has too many values for single-char encoding")

# Build the per-category index strings.
tokens = {c: [] for c in CATS}
for i in range(1, N + 1):
    tok = d[str(i)]
    attrs = {a['trait_type']: a['value'] for a in tok['attributes']}
    for c in CATS:
        if i in HONORARIES:
            idx = val_index[c][ONE_OF_ONE]
        else:
            idx = val_index[c][attrs[c]]
        tokens[c].append(chr(BASE + idx))

tokens_str = {c: ''.join(tokens[c]) for c in CATS}

out = {
    "version": 1,
    "generated": "2026-07-19",
    "count": N,
    "base": BASE,
    "categories": CATS,
    "values": values,
    "tokens": tokens_str,
}

os.makedirs(os.path.join(ROOT, 'traits'), exist_ok=True)
path = os.path.join(ROOT, 'traits', 'index.json')
with open(path, 'w') as f:
    json.dump(out, f, separators=(',', ':'), ensure_ascii=False)

size = os.path.getsize(path)
print(f"wrote {path}  ({size} bytes, {size/1024:.1f} KB)")
print("values per category:")
for c in CATS:
    print(f"  {c:<16} {len(values[c])} values (incl. '1 of 1')")
