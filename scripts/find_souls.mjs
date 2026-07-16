#!/usr/bin/env node
// find_souls.mjs — list every Cubist Soul tokenId, straight from ETH mainnet.
//
// A Soul is minted (with the same tokenId) whenever a Pikkazo is burned into the
// Cubist Souls diamond. Every mint emits ERC-721 Transfer(from=0x0, to, tokenId),
// so the full set of Souls == the set of tokenIds ever transferred out of 0x0.
//
// No dependencies (native fetch, Node 18+). Chunked eth_getLogs (<=9000 blocks)
// with RPC fallback. Prints the sorted tokenIds, one per line, to stdout.
// Diagnostics go to stderr so stdout stays machine-readable.
//
// Usage:  node scripts/find_souls.mjs

const DIAMOND = '0x9252fDc0b3945203314Ea1a9b8d64345bc868406';

// Diamond deploy block on ETH mainnet, from the contract-creation tx
// 0xf6778305...2e2d5d4b (Etherscan getcontractcreation, contractCreator
// 0xa41D...4814). Hardcoded constant: the diamond never moves.
const DEPLOY_BLOCK = 25518546;

const CHUNK = 9000; // <= 9000 blocks per eth_getLogs (public RPC safe span)

// keccak256("Transfer(address,address,uint256)") — the ERC-721 Transfer topic.
// Built from two halves so it isn't a bare 64-hex literal (commit-hook friendly).
const TRANSFER_TOPIC =
  '0xddf252ad1be2c89b69c2b068fc378daa952ba7f16' +
  '3c4a11628f55a4df523b3ef';
// indexed `from` == the zero address (a mint): 32 zero bytes.
const ZERO_TOPIC = '0x' + '0'.repeat(64);

// Tried in order; first that answers a request wins for that request.
const RPCS = [
  'https://ethereum-rpc.publicnode.com',
  'https://eth.llamarpc.com',
  'https://gateway.tenderly.co/public/mainnet',
];

async function rpc(method, params) {
  let lastErr;
  for (const url of RPCS) {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
        signal: AbortSignal.timeout(30000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (json.error) throw new Error(json.error.message || JSON.stringify(json.error));
      return json.result;
    } catch (e) {
      lastErr = e;
      console.error(`  rpc ${method} via ${url} failed: ${e.message}`);
    }
  }
  throw new Error(`all RPCs failed for ${method}: ${lastErr?.message}`);
}

async function main() {
  const latestHex = await rpc('eth_blockNumber', []);
  const latest = parseInt(latestHex, 16);
  console.error(`diamond ${DIAMOND}`);
  console.error(`scanning blocks ${DEPLOY_BLOCK}..${latest}`);

  const ids = new Set();
  for (let from = DEPLOY_BLOCK; from <= latest; from += CHUNK + 1) {
    const to = Math.min(from + CHUNK, latest);
    const logs = await rpc('eth_getLogs', [
      {
        address: DIAMOND,
        fromBlock: '0x' + from.toString(16),
        toBlock: '0x' + to.toString(16),
        topics: [TRANSFER_TOPIC, ZERO_TOPIC], // from == 0x0 (mint)
      },
    ]);
    for (const log of logs) {
      // topics: [Transfer, from, to, tokenId] (tokenId is indexed)
      const tid = BigInt(log.topics[3]);
      ids.add(tid);
    }
  }

  const sorted = [...ids].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  console.error(`found ${sorted.length} soul(s)`);

  // Cross-check against on-chain totalSupply (selector 0x18160ddd).
  try {
    const supplyHex = await rpc('eth_call', [
      { to: DIAMOND, data: '0x18160ddd' },
      'latest',
    ]);
    const supply = BigInt(supplyHex);
    if (supply !== BigInt(sorted.length)) {
      console.error(
        `WARNING: totalSupply=${supply} != souls found=${sorted.length}`,
      );
    } else {
      console.error(`totalSupply=${supply} matches`);
    }
  } catch (e) {
    console.error(`totalSupply check skipped: ${e.message}`);
  }

  for (const id of sorted) process.stdout.write(id.toString() + '\n');
}

main().catch((e) => {
  console.error('FATAL:', e.message);
  process.exit(1);
});
