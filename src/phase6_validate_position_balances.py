"""Query historical Conditional Tokens balances before sampled trade blocks."""
from __future__ import annotations

import json
import argparse
import hashlib
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
P2 = ROOT / "data/interim/phase2"
P6 = ROOT / "data/interim/phase6"
RAW = ROOT / "data/raw/polymarket/wallet_preblock_balance_sample"
RPC = "https://polygon.drpc.org"
CTF = "0x4d97dcd97ec945f40cf65f87097ace5ea0476045"
PAGE = 3
TRANSFER_SINGLE = "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62"
TRANSFER_BATCH = "0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb"


def rpc_batch(session, items):
    for attempt in range(8):
        payload = [{"jsonrpc": "2.0", "id": i, "method": method, "params": params}
                   for i, (method, params) in enumerate(items)]
        response = session.post(RPC, json=payload, timeout=90)
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(min(30, 2 ** attempt))
            continue
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict):
            body = [body]
        by_id = {int(x["id"]): x for x in body}
        if any("error" in by_id[i] for i in range(len(items))):
            raise RuntimeError(f"Polygon RPC error: {body}")
        return [by_id[i].get("result") for i in range(len(items))]
    raise RuntimeError("Polygon RPC retry limit reached")


def balance_call(wallet, token):
    data = ("0x00fdd58e" + wallet.lower().removeprefix("0x").zfill(64)
            + f"{int(token):064x}")
    return {"to": CTF, "data": data}


def decode_transfer(log):
    topics = log.get("topics", [])
    data = log.get("data", "")[2:]
    words = [int(data[i:i + 64], 16) for i in range(0, len(data), 64)]
    if len(topics) < 4 or len(words) < 2:
        return []
    sender, recipient = "0x" + topics[2][-40:].lower(), "0x" + topics[3][-40:].lower()
    topic = topics[0].lower()
    if topic == TRANSFER_SINGLE:
        return [(sender, recipient, str(words[0]), words[1])]
    if topic != TRANSFER_BATCH or len(words) < 4:
        return []
    id_offset, value_offset = words[0] // 32, words[1] // 32
    if id_offset >= len(words) or value_offset >= len(words):
        return []
    n_ids, n_vals = words[id_offset], words[value_offset]
    ids, values = words[id_offset + 1:id_offset + 1 + n_ids], words[value_offset + 1:value_offset + 1 + n_vals]
    return [(sender, recipient, str(token), amount)
            for token, amount in zip(ids, values)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p6-dir", type=Path, default=P6)
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    args = parser.parse_args()
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    positions = pd.read_csv(args.p6_dir / "polymarket_wallet_position_sample.csv")
    map_doc = json.loads((P2 / "polymarket_nba_2025_26_market_map.json").read_text())
    by_condition = {str(m["condition_id"]).lower(): [str(t) for t in m["token_ids"]]
                    for m in map_doc["markets"]}
    positions["conditionId"] = positions.conditionId.astype(str).str.lower()
    targets = positions.copy()
    targets["other_asset"] = targets.apply(
        lambda r: next((t for t in by_condition.get(r.conditionId, [])
                        if t != str(r.target_asset)), None), axis=1)
    targets = targets.dropna(subset=["other_asset"]).reset_index(drop=True)

    # Receipts identify the mined block containing the observed target fill.
    session = requests.Session()
    receipt_map = {}
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    for path in args.raw_dir.glob("target_receipts_*.json"):
        for item in json.loads(path.read_text()):
            if item.get("result"):
                receipt_map[str(item["transactionHash"]).lower()] = item["result"]
    hashes = targets.target_transactionHash.astype(str).tolist()
    missing = [h for h in hashes if h.lower() not in receipt_map]
    for start in range(0, len(missing), PAGE):
        batch = missing[start:start + PAGE]
        got = rpc_batch(session, [("eth_getTransactionReceipt", [h]) for h in batch])
        for tx, receipt in zip(batch, got):
            if receipt:
                receipt_map[tx.lower()] = receipt
        # Content-address each fetched batch. Numeric offsets alone collide
        # when a later, revised target sample has a different missing-hash
        # list and can overwrite receipts cached for an earlier sample.
        batch_key = hashlib.sha256("|".join(batch).encode()).hexdigest()[:16]
        (args.raw_dir / f"target_receipts_batch_{batch_key}.json").write_text(json.dumps(
            [{"transactionHash": tx, "result": receipt}
             for tx, receipt in zip(batch, got)], separators=(",", ":")))
        time.sleep(.08)

    target_rows = []
    missing_rows = []
    for i, row in targets.iterrows():
        tx = str(row.target_transactionHash).lower()
        receipt = receipt_map.get(tx)
        if not receipt:
            missing_rows.append(i)
            continue
        block = int(receipt["blockNumber"], 16)
        target_rows.append({**row.to_dict(), "target_block": block,
                            "target_transaction_index": int(receipt["transactionIndex"], 16),
                            "pre_block": block - 1})
    q = pd.DataFrame(target_rows)

    calls = []
    call_meta = []
    for i, row in q.iterrows():
        block_tag = hex(int(row.pre_block))
        for side, token in (("target", row.target_asset), ("other", row.other_asset)):
            calls.append(("eth_call", [balance_call(row.wallet, token), block_tag]))
            call_meta.append((i, side))
    balances = {}
    for start in range(0, len(calls), PAGE):
        batch = calls[start:start + PAGE]
        got = rpc_batch(session, batch)
        for meta, value in zip(call_meta[start:start + PAGE], got):
            balances[meta] = int(value, 16) / 1e6
        if (start // PAGE + 1) % 40 == 0:
            print(f"Queried {min(start + PAGE, len(calls))}/{len(calls)} historical balances", flush=True)
        time.sleep(.04)

    q["onchain_target_balance_preblock"] = [balances[(i, "target")] for i in q.index]
    q["onchain_other_balance_preblock"] = [balances[(i, "other")] for i in q.index]
    q["target_balance_matches_recorded_net_1e-5"] = (
        (q.onchain_target_balance_preblock - q.target_token_recorded_net_before_trade).abs() < 1e-5)
    q["other_balance_matches_recorded_net_1e-5"] = (
        (q.onchain_other_balance_preblock - q.other_token_recorded_net_before_trade).abs() < 1e-5)

    # Apply Conditional Tokens transfer logs from earlier transactions in the
    # same block. This yields the on-chain balance at target-transaction start.
    block_logs = {}
    blocks = sorted(set(q.target_block.astype(int)))
    for start in range(0, len(blocks), PAGE):
        batch_blocks = blocks[start:start + PAGE]
        got = rpc_batch(session, [("eth_getLogs", [{"address": CTF,
                              "fromBlock": hex(int(b)), "toBlock": hex(int(b)),
                              "topics": [[TRANSFER_SINGLE, TRANSFER_BATCH]]}])
                          for b in batch_blocks])
        for block, logs in zip(batch_blocks, got):
            block_logs[int(block)] = logs or []
        time.sleep(.04)
    at_tx_target, at_tx_other = [], []
    for _, row in q.iterrows():
        wallet = str(row.wallet).lower()
        tokens = {str(row.target_asset): 0.0, str(row.other_asset): 0.0}
        for log in block_logs.get(int(row.target_block), []):
            if int(log.get("transactionIndex", "0x0"), 16) >= int(row.target_transaction_index):
                continue
            for sender, recipient, token, raw_amount in decode_transfer(log):
                if token not in tokens:
                    continue
                amount = raw_amount / 1e6
                if sender == wallet:
                    tokens[token] -= amount
                if recipient == wallet:
                    tokens[token] += amount
        at_tx_target.append(float(row.onchain_target_balance_preblock) + tokens[str(row.target_asset)])
        at_tx_other.append(float(row.onchain_other_balance_preblock) + tokens[str(row.other_asset)])
    q["onchain_target_balance_pretransaction"] = at_tx_target
    q["onchain_other_balance_pretransaction"] = at_tx_other
    q["pretransaction_target_matches_strict_activity_net_1e-5"] = (
        (q.onchain_target_balance_pretransaction - q.target_token_recorded_net_before_trade).abs() < 1e-5)
    q.to_csv(args.p6_dir / "polymarket_wallet_pretransaction_balances.csv", index=False)

    summary = {
        "target_pairs": int(len(targets)),
        "pairs_with_receipt_and_two_balance_calls": int(len(q)),
        "missing_target_receipts": int(len(missing_rows)),
        "positive_onchain_target_token_balance": int(q.onchain_target_balance_preblock.gt(1e-6).sum()),
        "positive_onchain_other_token_balance": int(q.onchain_other_balance_preblock.gt(1e-6).sum()),
        "both_onchain_outcomes_positive": int((q.onchain_target_balance_preblock.gt(1e-6)
                                                & q.onchain_other_balance_preblock.gt(1e-6)).sum()),
        "target_balance_matches_activity_recorded_net": int(q["target_balance_matches_recorded_net_1e-5"].sum()),
        "other_balance_matches_activity_recorded_net_when_observed": int(
            (q["other_balance_matches_recorded_net_1e-5"] & q.other_token_recorded_net_before_trade.notna()).sum()),
        "target_pretransaction_positive": int(q.onchain_target_balance_pretransaction.gt(1e-6).sum()),
        "other_pretransaction_positive": int(q.onchain_other_balance_pretransaction.gt(1e-6).sum()),
        "both_pretransaction_outcomes_positive": int((q.onchain_target_balance_pretransaction.gt(1e-6)
                                                        & q.onchain_other_balance_pretransaction.gt(1e-6)).sum()),
        "prior_same_block_transfer_logs_applied": True,
        "pretransaction_target_balance_matches_strict_activity_net": int(
            q["pretransaction_target_matches_strict_activity_net_1e-5"].sum()),
        "interpretation": "Balances are reconstructed at the start of the target transaction by querying the prior-block balance and applying earlier ERC-1155 transfer logs in the same block. Activity earlier within the target transaction remains unresolved.",
        "limits": [
            "A token balance query validates on-chain holdings at the stated block; it does not identify when/how the position was acquired.",
            "The target transaction may itself contain earlier fills for the same wallet before the specific selected fill.",
            "This is a deterministic stratified validation sample, not a representative cohort estimate.",
        ],
    }
    (args.p6_dir / "polymarket_wallet_pretransaction_balances.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
