"""Independently validate sampled Activity REDEEM amounts against Polygon logs."""
from __future__ import annotations

import json
import time
import argparse
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
P6 = ROOT / "data/interim/phase6"
RAW = ROOT / "data/raw/polymarket/wallet_position_receipts_sample"
RPC = "https://polygon.drpc.org"
PAYOUT_TOPIC = "0x2682012a4a4f1973119f1c9b90745d1bd91fa2bab387344f044cb3586864d18d"
CTF = "0x4d97dcd97ec945f40cf65f87097ace5ea0476045"
PAGE = 3  # public endpoint has a small batch limit


def request_batch(session, hashes):
    for attempt in range(8):
        payload = [{"jsonrpc": "2.0", "id": i, "method": "eth_getTransactionReceipt",
                    "params": [h]} for i, h in enumerate(hashes)]
        response = session.post(RPC, json=payload, timeout=90)
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(min(30, 2 ** attempt))
            continue
        response.raise_for_status()
        result = response.json()
        if isinstance(result, dict):
            result = [result]
        by_id = {int(x["id"]): x for x in result}
        if any("error" in by_id[i] for i in range(len(hashes))):
            raise RuntimeError(f"RPC receipt error: {result}")
        return [by_id[i].get("result") for i in range(len(hashes))]
    raise RuntimeError("Polygon RPC retry limit reached")


def decode(log):
    data = log["data"][2:]
    words = [int(data[i:i+64], 16) for i in range(0, len(data), 64)]
    if len(words) < 4:
        return None
    offset_word = words[1] // 32
    n_sets = words[offset_word] if offset_word < len(words) else 0
    return {
        "redeemer": "0x" + log["topics"][1][-40:].lower(),
        "condition_id": "0x" + f"{words[0]:064x}",
        "payout_usdc": words[2] / 1e6,
        "index_sets": words[offset_word + 1:offset_word + 1 + n_sets],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p6-dir", type=Path, default=P6)
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    args = parser.parse_args()
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    ledger = pd.read_parquet(args.p6_dir / "polymarket_wallet_history_sample.parquet")
    redeems = ledger.loc[ledger.type.eq("REDEEM") & pd.to_numeric(ledger["size"], errors="coerce").gt(0)].copy()
    unique = redeems.drop_duplicates("transactionHash")
    hashes = unique.transactionHash.astype(str).tolist()
    session = requests.Session()
    receipts = {}
    for path in args.raw_dir.glob("receipts_*.json"):
        for item in json.loads(path.read_text()):
            if item.get("result"):
                receipts[str(item["transactionHash"]).lower()] = item["result"]
    missing_hashes = [h for h in hashes if h.lower() not in receipts]
    for start in range(0, len(missing_hashes), PAGE):
        batch = missing_hashes[start:start + PAGE]
        batch_receipts = request_batch(session, batch)
        for tx, receipt in zip(batch, batch_receipts):
            receipts[tx.lower()] = receipt
        (args.raw_dir / f"receipts_{start:04d}.json").write_text(json.dumps(
            [{"transactionHash": tx, "result": receipt}
             for tx, receipt in zip(batch, batch_receipts)], separators=(",", ":")))
        time.sleep(.1)
    rows = []
    for row in redeems.to_dict("records"):
        tx = str(row["transactionHash"]).lower()
        receipt = receipts.get(tx) or {}
        logs = [decode(log) for log in receipt.get("logs", [])
                if (log.get("topics") or [""])[0].lower() == PAYOUT_TOPIC
                and log.get("address", "").lower() == CTF]
        # Proxy wallets can call through an adapter, so the Conditional Tokens
        # event's redeemer may differ from the Activity API proxyWallet.
        exact = [x for x in logs if x
                 and x["condition_id"] == str(row["sample_condition_id"]).lower()]
        amount = sum(x["payout_usdc"] for x in exact)
        rows.append({"wallet": row["sample_wallet"], "conditionId": row["sample_condition_id"],
                     "activity_transaction_hash": tx, "activity_size": float(row["size"]),
                     "receipt_found": bool(receipt), "matching_payout_redemption_logs": len(exact),
                     "onchain_redeemer_addresses": json.dumps(sorted({x["redeemer"] for x in exact})),
                     "onchain_payout_usdc": amount if exact else None,
                     "activity_minus_onchain": float(row["size"]) - amount if exact else None,
                     "amount_matches_1e-6": bool(exact and abs(float(row["size"]) - amount) < 1e-6),
                     "decoded_logs": json.dumps(logs, sort_keys=True)})
    out = pd.DataFrame(rows)
    out.to_csv(args.p6_dir / "polymarket_wallet_redemption_receipt_validation.csv", index=False)
    summary = {"activity_positive_redemption_rows": int(len(out)),
               "unique_redemption_transactions": int(len(unique)),
               "rows_with_matching_onchain_log": int(out.matching_payout_redemption_logs.gt(0).sum()),
               "activity_amount_matches_onchain_within_1e-6": int(out["amount_matches_1e-6"].sum()),
               "unmatched_rows": int(out.matching_payout_redemption_logs.eq(0).sum()),
               "receipt_cache": str(args.raw_dir),
               "event_reference": "ConditionalTokens PayoutRedemption; 6-decimal USDC payout"}
    (args.p6_dir / "polymarket_wallet_redemption_receipt_validation.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
