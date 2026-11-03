"""Reconcile every in-game maker row in the May 1 V2 market to Polygon receipts.

The Data API raw pages and receipt batches are immutable cache checkpoints. The
public dRPC endpoint is used only to obtain receipts for this validation market.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from common import ROOT, write_json

RAW = ROOT / "data/raw/polymarket/v2_validation_may01"
OUT = ROOT / "data/interim/phase2"
RPC = "https://polygon.drpc.org"
V2 = "0xe111180000d2663c0091e4f400237545b87b996b"
ORDER_FILLED = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"
ORDERS_MATCHED = "0x174b3811690657c217184f89418266767c87e4805d09680c39fc9c031c0cab7c"


def key(row):
    return (str(row["transactionHash"]).lower(), str(row["proxyWallet"]).lower(),
            str(row["asset"]), float(row["size"]), float(row["price"]))


def rpc_batch(tx_hashes, batch_path):
    if batch_path.exists():
        return json.loads(batch_path.read_text())
    s = requests.Session()
    body = [{"jsonrpc": "2.0", "id": i, "method": "eth_getTransactionReceipt",
             "params": [tx]} for i, tx in enumerate(tx_hashes)]
    for attempt in range(9):
        response = s.post(RPC, json=body, timeout=90)
        if response.status_code == 429 or response.status_code == 503 or response.status_code >= 500:
            time.sleep(float(response.headers.get("Retry-After", min(60, 2 ** attempt))))
            continue
        response.raise_for_status()
        result = response.json()
        if isinstance(result, list) and all("error" not in x for x in result):
            batch_path.parent.mkdir(parents=True, exist_ok=True)
            batch_path.write_text(json.dumps(result, separators=(",", ":")))
            return result
        if isinstance(result, list) and any("error" in x for x in result):
            raise RuntimeError(f"JSON-RPC batch item error in {batch_path.name}: {result[:2]}")
        raise RuntimeError(f"Unexpected batch response: {str(result)[:500]}")
    raise RuntimeError(f"RPC retry limit exceeded for {batch_path.name}")


def decode_maker(log, tx_hash):
    topics = log.get("topics") or []
    if len(topics) < 4 or (log.get("address") or "").lower() != V2:
        return None
    if topics[0].lower() != ORDER_FILLED or "0x" + topics[3][-40:].lower() == V2:
        return None
    words = [int(log["data"][2+i*64:2+(i+1)*64], 16)
             for i in range(len(log["data"][2:]) // 64)]
    if len(words) < 4:
        return None
    side_num, token, maker_amt, taker_amt = words[:4]
    # V2 event side is the maker's side. BUY pays makerAmount for takerAmount
    # token shares; SELL gives makerAmount token shares for takerAmount collateral.
    if side_num == 0:
        side, size, cash = "BUY", taker_amt, maker_amt
    else:
        side, size, cash = "SELL", maker_amt, taker_amt
    if size == 0:
        return None
    return {
        "transactionHash": tx_hash.lower(),
        "logIndex": int(log.get("logIndex", "0x0"), 16),
        "proxyWallet": "0x" + topics[2][-40:].lower(),
        "asset": str(token), "side": side, "size": size / 1e6,
        "price": cash / size,
    }


def main():
    api = json.loads((RAW / "api_rows_deduped.json").read_text())
    all_rows = api["both"]
    taker_rows = api["taker"]
    # Per instruction, collapse duplicate maker identity rows before validation.
    api_by_key = {}
    duplicate_count = 0
    for row in all_rows:
        k = key(row)
        if k in api_by_key:
            duplicate_count += 1
        else:
            api_by_key[k] = row
    taker_counts = Counter(key(row) for row in taker_rows)
    maker_rows = []
    for k, row in api_by_key.items():
        if taker_counts[k]:
            taker_counts[k] -= 1
        else:
            maker_rows.append(row)

    tx_hashes = sorted({str(r["transactionHash"]).lower() for r in taker_rows})
    receipt_root = RAW / "receipts"
    receipts = {}
    # The free dRPC tier rejects JSON-RPC batches above three calls.
    batch_size = 3
    chunks = list(range(0, len(tx_hashes), batch_size))
    def fetch_batch(first):
        chunk = tx_hashes[first:first+batch_size]
        path = receipt_root / f"batch_{first//batch_size:04d}.json"
        return first, chunk, rpc_batch(chunk, path)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch_batch, first) for first in chunks]
        completed = 0
        for future in as_completed(futures):
            first, chunk, batch = future.result()
            completed += 1
            by_id = {int(r["id"]): r.get("result") for r in batch}
            for i, tx in enumerate(chunk):
                receipt = by_id.get(i)
                if receipt and receipt.get("transactionHash"):
                    receipts[tx] = receipt
            if completed % 100 == 0 or completed == len(futures):
                print(f"receipt batches {completed}/{len(futures)}; receipts {len(receipts)}/{len(tx_hashes)}", flush=True)

    onchain = []
    matched_logs = 0
    for tx, receipt in receipts.items():
        for log in receipt.get("logs", []):
            if (log.get("address") or "").lower() == V2 and \
                    (log.get("topics") or [""])[0].lower() == ORDERS_MATCHED:
                matched_logs += 1
            fill = decode_maker(log, tx)
            if fill:
                onchain.append(fill)

    def identity(row):
        return (str(row["transactionHash"]).lower(), str(row["proxyWallet"]).lower(),
                str(row["asset"]), str(row["side"]).upper())
    api_groups = {}
    for r in maker_rows:
        api_groups.setdefault(identity(r), []).append(r)
    chain_groups = {}
    for r in onchain:
        chain_groups.setdefault(identity(r), []).append(r)
    matched = 0
    api_used = set()
    chain_used = set()
    missing_chain, missing_api = [], []
    for ident in sorted(set(api_groups) | set(chain_groups)):
        arows, crows = api_groups.get(ident, []), chain_groups.get(ident, [])
        taken_chain = set()
        for ai, a in enumerate(arows):
            ci = next((j for j, c in enumerate(crows) if j not in taken_chain
                       and abs(float(a["size"])-float(c["size"])) <= 1e-5
                       and abs(float(a["price"])-float(c["price"])) <= 1e-5), None)
            if ci is None:
                missing_chain.append(a)
            else:
                taken_chain.add(ci); matched += 1
        for ci, c in enumerate(crows):
            if ci not in taken_chain:
                missing_api.append(c)

    summary = {
        "market": "nba-det-orl-2026-05-01", "espn_game_id": "401869417",
        "season_type": 3, "note": "May 1 is a playoff market; no May/June regular-season games exist in the 2025-26 NBA calendar.",
        "api_both_rows_before_dedup": len(all_rows), "api_duplicate_rows_removed": duplicate_count,
        "api_deduplicated_rows": len(api_by_key), "api_taker_rows": len(taker_rows),
        "api_maker_rows": len(maker_rows), "unique_taker_transactions": len(tx_hashes),
        "receipts_fetched": len(receipts), "missing_receipts": len(tx_hashes)-len(receipts),
        "orders_matched_logs": matched_logs, "decoded_maker_orderfilled_logs": len(onchain),
        "maker_rows_matched": matched, "api_maker_rows_unmatched": len(missing_chain),
        "onchain_maker_logs_unmatched": len(missing_api),
        "tolerance": 1e-5,
    }
    write_json(OUT / "polymarket_v2_may01_reconciliation.json", summary)
    (RAW / "v2_may01_reconciliation_detail.json").write_text(json.dumps({
        "summary": summary, "api_maker_unmatched": missing_chain,
        "onchain_maker_unmatched": missing_api,
    }, separators=(",", ":")))
    (RAW / "v2_may01_onchain_maker_fills.json").write_text(json.dumps(onchain, separators=(",", ":")))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
