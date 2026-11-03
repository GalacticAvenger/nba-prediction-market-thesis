"""Refine sampled pre-trade balances to uniquely matched token receipt logs.

The 210-pair sample contains BUY records. Match each selected Activity record
to the V1 CTF Exchange OrderFilled event using wallet, token ID, share quantity,
and price, then require a unique inbound ERC-1155 transfer bundle
of the same token and quantity. Bundles may be one exact-size transfer or the
observed 90%/10% two-part pattern, with the 90% leg before the fill and the
10% leg after it. For unique matches, reconstruct the target-token balance
immediately before the first inbound leg using the transaction-start balance
plus earlier ERC-1155 logs in the same receipt.
"""
from __future__ import annotations

import glob
import json
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P6 = ROOT / "data/interim/phase6"
RAW = ROOT / "data/raw/polymarket/wallet_preblock_balance_sample"
CTF = "0x4d97dcd97ec945f40cf65f87097ace5ea0476045"
TRANSFER_SINGLE = "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62"
TRANSFER_BATCH = "0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb"
CTF_EXCHANGE = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"
ORDER_FILLED = "0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6"


def decode_transfers(log):
    topics = log.get("topics", [])
    if len(topics) < 4:
        return []
    data = log.get("data", "")[2:]
    words = [int(data[i:i + 64], 16) for i in range(0, len(data), 64)]
    sender, recipient = "0x" + topics[2][-40:].lower(), "0x" + topics[3][-40:].lower()
    kind = topics[0].lower()
    if kind == TRANSFER_SINGLE and len(words) >= 2:
        return [(sender, recipient, str(words[0]), words[1])]
    if kind != TRANSFER_BATCH or len(words) < 4:
        return []
    id_offset, value_offset = words[0] // 32, words[1] // 32
    if id_offset >= len(words) or value_offset >= len(words):
        return []
    n_ids, n_values = words[id_offset], words[value_offset]
    ids = words[id_offset + 1:id_offset + 1 + n_ids]
    values = words[value_offset + 1:value_offset + 1 + n_values]
    return [(sender, recipient, str(token), amount)
            for token, amount in zip(ids, values)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p6-dir", type=Path, default=P6)
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    args = parser.parse_args()
    p6 = args.p6_dir
    pos = pd.read_csv(p6 / "polymarket_wallet_position_sample.csv")
    bal = pd.read_csv(p6 / "polymarket_wallet_pretransaction_balances.csv")
    design = pd.read_csv(p6 / "polymarket_wallet_history_sample_design.csv")
    target = pd.read_parquet(p6 / "polymarket_wallet_late5_target_trades.parquet")
    for frame in (pos, design, target):
        frame["wallet"] = frame.wallet.astype(str).str.lower()
        frame["conditionId"] = frame.conditionId.astype(str).str.lower()
    pos["target_transactionHash"] = pos.target_transactionHash.astype(str).str.lower()
    target["transactionHash"] = target.transactionHash.astype(str).str.lower()
    target = target.merge(
        design[["wallet", "conditionId", "role"]], on=["wallet", "conditionId", "role"],
        how="inner", validate="many_to_one")
    target = target.sort_values(["timestamp", "transactionHash"]).drop_duplicates(
        ["wallet", "conditionId"])
    target = target.merge(
        pos[["wallet", "conditionId", "target_transactionHash", "target_asset",
             "profile_stratum"]],
        left_on=["wallet", "conditionId", "transactionHash", "asset"],
        right_on=["wallet", "conditionId", "target_transactionHash", "target_asset"],
        how="inner", validate="one_to_one")
    bal["wallet"] = bal.wallet.astype(str).str.lower()
    bal["target_transactionHash"] = bal.target_transactionHash.astype(str).str.lower()
    target = target.merge(
        bal[["wallet", "conditionId", "target_transactionHash",
             "onchain_target_balance_pretransaction"]],
        on=["wallet", "conditionId", "target_transactionHash"],
        how="left", validate="one_to_one")

    receipts = {}
    for path in glob.glob(str(args.raw_dir / "target_receipts_*.json")):
        for item in json.loads(Path(path).read_text()):
            if item.get("result"):
                receipts[str(item["transactionHash"]).lower()] = item["result"]

    rows = []
    for row in target.to_dict("records"):
        receipt = receipts.get(str(row["transactionHash"]).lower())
        candidates = []
        order_events = []
        if receipt:
            for log in receipt.get("logs", []):
                if (log.get("address", "").lower() == CTF_EXCHANGE
                        and log.get("topics", [""])[0].lower() == ORDER_FILLED):
                    maker = "0x" + log["topics"][2][-40:].lower()
                    taker = "0x" + log["topics"][3][-40:].lower()
                    data = log.get("data", "")[2:]
                    words = [int(data[i:i + 64], 16)
                             for i in range(0, len(data), 64)]
                    if len(words) >= 5:
                        maker_asset, taker_asset, maker_amount, taker_amount = words[:4]
                        buy = None
                        if (maker == row["wallet"] and maker_asset == 0
                                and str(taker_asset) == str(row["asset"])):
                            buy = (taker_amount / 1e6, maker_amount / taker_amount,
                                   "chain_maker")
                        elif (taker == row["wallet"] and str(maker_asset) == str(row["asset"])
                              and taker_asset == 0):
                            buy = (maker_amount / 1e6, taker_amount / maker_amount,
                                   "chain_taker")
                        if (buy and abs(buy[0] - float(row["size"])) < 1e-6
                                and abs(buy[1] - float(row["price"])) < 1e-7):
                            order_events.append({"log_index": int(log["logIndex"], 16),
                                                 "chain_role": buy[2]})
                if log.get("address", "").lower() != CTF:
                    continue
                for sender, recipient, token, amount in decode_transfers(log):
                    if token == str(row["asset"]) and recipient == row["wallet"]:
                        candidates.append({
                            "log_index": int(log["logIndex"], 16),
                            "amount": amount / 1e6,
                        })
        size = float(row["size"])
        exact = [x for x in candidates if abs(x["amount"] - size) < 1e-6]
        bundles = []
        if len(order_events) == 1 and not exact:
            fill_index = order_events[0]["log_index"]
            before = [x for x in candidates if x["log_index"] < fill_index
                      and abs(x["amount"] - .9 * size) < 1e-6]
            after = [x for x in candidates if x["log_index"] > fill_index
                     and abs(x["amount"] - .1 * size) < 1e-6]
            bundles = [(a, b) for a in before for b in after]
        direct_match = len(order_events) == 1 and len(exact) == 1 and exact[0]["log_index"] < order_events[0]["log_index"]
        split_match = len(order_events) == 1 and len(exact) == 0 and len(bundles) == 1
        ordered = direct_match or split_match
        matched_logs = [exact[0]] if direct_match else list(bundles[0]) if split_match else []
        first_match_index = min((x["log_index"] for x in matched_logs), default=None)
        out = {
            "wallet": row["wallet"], "conditionId": row["conditionId"],
            "game_id": row["game_id"], "role": row["role"],
            "profile_stratum": row["profile_stratum"],
            "transactionHash": row["transactionHash"], "target_asset": str(row["asset"]),
            "target_trade_size": float(row["size"]), "inbound_target_token_logs": len(candidates),
            "target_trade_price": float(row["price"]),
            "exact_size_transfer_matches": len(exact),
            "matched_log_index": first_match_index,
            "matched_transfer_bundle_size": len(matched_logs),
            "matched_transfer_bundle_amount": sum(x["amount"] for x in matched_logs) if matched_logs else None,
            "wallet_asset_size_price_orderfilled_matches": len(order_events),
            "matched_orderfilled_log_index": order_events[0]["log_index"] if len(order_events) == 1 else None,
            "matched_onchain_participant_role": order_events[0]["chain_role"] if len(order_events) == 1 else None,
            "balance_at_transaction_start": row["onchain_target_balance_pretransaction"],
            "balance_immediately_before_matched_transfer": None,
            "status": "unique_order_and_transfer" if ordered else
                      "ambiguous_fill_or_transfer" if len(exact) > 1 or len(order_events) > 1 or len(bundles) > 1 else
                      "no_unique_order_transfer_pair",
        }
        if ordered and receipt:
            running = float(row["onchain_target_balance_pretransaction"])
            match_index = first_match_index
            for log in sorted(receipt.get("logs", []), key=lambda x: int(x["logIndex"], 16)):
                if int(log["logIndex"], 16) >= match_index:
                    break
                if log.get("address", "").lower() != CTF:
                    continue
                for sender, recipient, token, amount in decode_transfers(log):
                    if token != str(row["asset"]):
                        continue
                    if sender == row["wallet"]:
                        running -= amount / 1e6
                    if recipient == row["wallet"]:
                        running += amount / 1e6
            out["balance_immediately_before_matched_transfer"] = running
        rows.append(out)

    result = pd.DataFrame(rows)
    result.to_csv(p6 / "polymarket_wallet_exact_fill_balance_sample.csv", index=False)
    n_unique = int(result.status.eq("unique_order_and_transfer").sum())
    matched = result.loc[result.status.eq("unique_order_and_transfer")]
    by_profile = matched.groupby("profile_stratum", sort=True).agg(
        uniquely_matched_pairs=("wallet", "size"),
        positive_pretransfer_target_balance=(
            "balance_immediately_before_matched_transfer",
            lambda values: int(values.gt(1e-6).sum())),
    ).reset_index()
    by_profile["positive_share_among_matched"] = (
        by_profile.positive_pretransfer_target_balance / by_profile.uniquely_matched_pairs)
    summary = {
        "sample_pairs": int(len(result)),
        "unique_wallet_asset_size_price_orderfilled_and_transfer_bundle_pairs": n_unique,
        "unique_exact_single_transfer_pairs": int((result.status.eq("unique_order_and_transfer") & result.matched_transfer_bundle_size.eq(1)).sum()),
        "unique_90_10_split_transfer_bundle_pairs": int((result.status.eq("unique_order_and_transfer") & result.matched_transfer_bundle_size.eq(2)).sum()),
        "ambiguous_fill_or_transfer": int(result.status.eq("ambiguous_fill_or_transfer").sum()),
        "no_unique_order_transfer_pair": int(result.status.eq("no_unique_order_transfer_pair").sum()),
        "unique_matches_with_positive_target_inventory_before_transfer": int(
            result.loc[result.status.eq("unique_order_and_transfer"),
                       "balance_immediately_before_matched_transfer"].gt(1e-6).sum()),
        "unique_matches_positive_balance_share": float(
            result.loc[result.status.eq("unique_order_and_transfer"),
                       "balance_immediately_before_matched_transfer"].gt(1e-6).mean()),
        "matched_profile_strata": by_profile.to_dict("records"),
        "interpretation": "The selected Activity BUY is matched by wallet, target token ID, filled share quantity, and price to a unique V1 OrderFilled event; the event participant is recorded as maker or taker under the contract ABI, independently of the Activity API row label. An inbound ERC-1155 transfer bundle for the same token and quantity must also be unique: either one exact-size transfer before the event, or one 90% transfer before and 10% transfer after the event. The reported balance is immediately before the first matched inbound leg, after earlier same-transaction ERC-1155 movements.",
        "limits": [
            "The sample is stratified and is not representative of all buyers.",
            "Activity API row labels and the exchange contract's maker/taker event fields are distinct concepts; the match uses the wallet and economic BUY fields rather than treating those labels as identical.",
            "Only the observed 90%/10% split pattern is accepted; unmatched or ambiguous bundles remain unresolved.",
        ],
    }
    (p6 / "polymarket_wallet_exact_fill_balance_sample.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
