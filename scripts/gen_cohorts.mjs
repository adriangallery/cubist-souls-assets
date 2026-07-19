#!/usr/bin/env node
// gen_cohorts.mjs — snapshot cohortOf() for every FREED Cubist Soul.
//
// cohortOf(tokenId) is IMMUTABLE once a soul is freed (fixed at convert()),
// so this dataset only ever grows: the script is incremental — it scans the
// freed set from mainnet logs (Transfer from=0x0), keeps every cohort already
// in cohorts/cohorts.json, and eth_calls only the NEW ids in JSON-RPC batches.
//
// Output: cohorts/cohorts.json
//   { "updated": "<ISO>", "block": <int>, "count": <int>,
//     "cohorts": { "<tokenId>": <0-4>, ... } }
//
// No dependencies (native fetch, Node 18+). Runs in GitHub Actions on the
// 6h mirror schedule. NOTE runner gotcha: publicnode/llamarpc 403 datacenter
// IPs — the Tenderly gateway goes FIRST here.
//
// Usage:  node scripts/gen_cohorts.mjs

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const OUT = join(ROOT, 'cohorts', 'cohorts.json');

const DIAMOND = '0x9252fDc0b3945203314Ea1a9b8d64345bc868406';
const DEPLOY_BLOCK = 25518546;
const CHUNK = 9000; // eth_getLogs block span, public-RPC safe
const CALL_BATCH = 100; // eth_call JSON-RPC batch size
const COHORT_SELECTOR = '0xd5b0e035'; // cast sig "cohortOf(uint256)"

// keccak256("Transfer(address,address,uint256)"), split so it isn't a bare
// 64-hex literal (commit-hook friendly).
const TRANSFER_TOPIC =
  '0xddf252ad1be2c89b69c2b068fc378daa952ba7f16' +
  '3c4a11628f55a4df523b3ef';
const ZERO_TOPIC = '0x' + '0'.repeat(64);

// Tenderly FIRST: the only gateway that answers from GitHub runner IPs.
const RPCS = [
  'https://gateway.tenderly.co/public/mainnet',
  'https://ethereum-rpc.publicnode.com',
  'https://eth.llamarpc.com',
];

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function post(body) {
  let lastErr;
  for (const url of RPCS) {
    // 3 tries per endpoint with backoff — on GitHub runners only Tenderly
    // answers, and it rate-limits bursts with 429s.
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(30000),
        });
        if (res.status === 429) { await sleep(1200 * (attempt + 1)); continue; }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (e) {
        lastErr = e;
        console.error(`  rpc via ${url} failed: ${e.message}`);
        break; // non-429 failure: move to next endpoint
      }
    }
  }
  throw new Error(`all RPCs failed: ${lastErr?.message || '429s'}`);
}

async function rpc(method, params) {
  const json = await post({ jsonrpc: '2.0', id: 1, method, params });
  if (json.error) throw new Error(json.error.message || JSON.stringify(json.error));
  return json.result;
}

async function freedIds(latest) {
  const ids = new Set();
  for (let from = DEPLOY_BLOCK; from <= latest; from += CHUNK + 1) {
    const to = Math.min(from + CHUNK, latest);
    const logs = await rpc('eth_getLogs', [{
      address: DIAMOND,
      fromBlock: '0x' + from.toString(16),
      toBlock: '0x' + to.toString(16),
      topics: [TRANSFER_TOPIC, ZERO_TOPIC],
    }]);
    for (const log of logs) ids.add(Number(BigInt(log.topics[3])));
  }
  return [...ids].sort((a, b) => a - b);
}

async function cohortsFor(ids) {
  const out = {};
  for (let i = 0; i < ids.length; i += CALL_BATCH) {
    const chunk = ids.slice(i, i + CALL_BATCH);
    const batch = chunk.map((id, j) => ({
      jsonrpc: '2.0', id: j,
      method: 'eth_call',
      params: [{ to: DIAMOND, data: COHORT_SELECTOR + id.toString(16).padStart(64, '0') }, 'latest'],
    }));
    const res = await post(batch);
    if (!Array.isArray(res)) throw new Error('batch eth_call unsupported by RPC');
    for (const r of res) {
      if (r.error || !r.result) { console.error(`  cohortOf(#${chunk[r.id]}) failed: ${JSON.stringify(r.error)}`); continue; }
      out[chunk[r.id]] = Number(BigInt(r.result));
    }
    console.error(`  cohorts ${Math.min(i + CALL_BATCH, ids.length)}/${ids.length}`);
    if (i + CALL_BATCH < ids.length) await sleep(400); // pace Tenderly
  }
  return out;
}

async function main() {
  const latest = parseInt(await rpc('eth_blockNumber', []), 16);
  console.error(`scanning freed set up to block ${latest}`);
  const freed = await freedIds(latest);
  console.error(`freed souls: ${freed.length}`);

  let prev = {};
  if (existsSync(OUT)) {
    try { prev = JSON.parse(readFileSync(OUT, 'utf8')).cohorts || {}; } catch {}
  }
  const missing = freed.filter(id => !(id in prev));
  console.error(`already snapshotted: ${Object.keys(prev).length}, new: ${missing.length}`);
  if (!missing.length && Object.keys(prev).length === freed.length) {
    console.error('snapshot already complete — nothing to write');
    return;
  }

  const fresh = missing.length ? await cohortsFor(missing) : {};
  const cohorts = { ...prev };
  for (const [id, c] of Object.entries(fresh)) cohorts[id] = c;

  // keep only freed ids, sorted numerically for stable diffs
  const freedSet = new Set(freed);
  const sorted = {};
  for (const id of Object.keys(cohorts).map(Number).sort((a, b) => a - b)) {
    if (freedSet.has(id)) sorted[id] = cohorts[id];
  }

  const snapshot = {
    updated: new Date().toISOString(),
    block: latest,
    count: Object.keys(sorted).length,
    cohorts: sorted,
  };
  mkdirSync(dirname(OUT), { recursive: true });
  writeFileSync(OUT, JSON.stringify(snapshot));
  console.error(`wrote ${OUT} (${Object.keys(sorted).length} cohorts, +${Object.keys(fresh).length} new)`);
}

main().catch((e) => { console.error('FATAL:', e.message); process.exit(1); });
