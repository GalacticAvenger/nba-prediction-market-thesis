"""Audit recorded pre-target token inventory in the stratified API sample.

Balances here are explicitly partial: Activity may omit transferred or
initially held ERC-1155 positions, and timestamp resolution is one second.
"""
from __future__ import annotations

import json
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P6 = ROOT / "data/interim/phase6"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p6-dir", type=Path, default=P6)
    p6 = parser.parse_args().p6_dir
    targets = pd.read_parquet(p6 / "polymarket_wallet_late5_target_trades.parquet")
    design = pd.read_csv(p6 / "polymarket_wallet_history_sample_design.csv")
    targets["wallet"] = targets.wallet.astype(str).str.lower()
    targets["conditionId"] = targets.conditionId.astype(str).str.lower()
    design["wallet"] = design.wallet.astype(str).str.lower()
    design["conditionId"] = design.conditionId.astype(str).str.lower()
    targets = targets.merge(
        design[["wallet", "conditionId", "role", "profile_stratum", "month"]],
        on=["wallet", "conditionId"], how="inner", validate="many_to_one",
        suffixes=("", "_sample"))
    targets = targets.loc[targets.role.eq(targets.role_sample)].copy()
    targets = targets.sort_values(["timestamp", "transactionHash"]).drop_duplicates(
        ["wallet", "conditionId"])
    history = pd.read_parquet(p6 / "polymarket_wallet_history_sample.parquet")
    groups = {(w, c): g.sort_values(["timestamp", "transactionHash"])
              for (w, c), g in history.groupby(["sample_wallet", "sample_condition_id"])}
    output = []
    for target in targets.to_dict("records"):
        key = (target["wallet"], target["conditionId"])
        g = groups.get(key)
        if g is None:
            continue
        target_rows = g.loc[g.asset.astype(str).eq(str(target["asset"]))]
        if target_rows.empty:
            continue
        own_outcome = str(target_rows.iloc[0].outcome)
        other_outcomes = set(g.loc[g.type.eq("TRADE"), "outcome"].dropna().astype(str)) - {own_outcome}
        other_outcome = next(iter(other_outcomes), "")
        earlier = g.loc[g.timestamp.lt(int(target["timestamp"]))]
        balances = {own_outcome: 0.0}
        if other_outcome:
            balances[other_outcome] = 0.0
        unsupported_before = 0
        for row in earlier.to_dict("records"):
            kind = str(row.get("type", "")).upper()
            qty = float(row.get("size") or 0)
            if kind == "TRADE":
                outcome = str(row.get("outcome", ""))
                if outcome in balances and str(row.get("side", "")).upper() in {"BUY", "SELL"}:
                    balances[outcome] += qty * (1 if str(row["side"]).upper() == "BUY" else -1)
            elif kind == "MERGE":
                for outcome in balances:
                    balances[outcome] -= qty
            elif kind == "SPLIT":
                for outcome in balances:
                    balances[outcome] += qty
            elif kind not in {"REDEEM"}:
                unsupported_before += 1
        first_ts = int(g.timestamp.min()) if len(g) else None
        output.append({
            "wallet": key[0], "conditionId": key[1], "game_id": target["game_id"],
            "target_timestamp": int(target["timestamp"]),
            "target_transactionHash": target["transactionHash"],
            "target_asset": str(target["asset"]), "target_outcome": own_outcome,
            "sample_role": str(g.sample_role.iloc[0]),
            "profile_stratum": str(g.sample_profile_stratum.iloc[0]),
            "market_month": str(g.sample_month.iloc[0]),
            "target_trade_role": str(target["role"]),
            "target_token_recorded_net_before_trade": balances.get(own_outcome, 0.0),
            "other_token_recorded_net_before_trade": balances.get(other_outcome) if other_outcome else None,
            "first_observed_market_activity_timestamp": first_ts,
            "prior_observed_history_exists": bool(first_ts is not None and first_ts < int(target["timestamp"])),
            "same_second_activity_rows": int(g.timestamp.eq(int(target["timestamp"])).sum()),
            "unsupported_event_rows_before_target": unsupported_before,
            "inventory_status": "partial observed trade/merge net; not a verified position",
        })
    result = pd.DataFrame(output)
    result.to_csv(p6 / "polymarket_wallet_position_sample.csv", index=False)

    # Positive redemptions provide a separate payout reconciliation. Compare
    # the recorded winning-token net immediately before the first positive claim
    # with the total amount claimed for that outcome.
    payout = []
    for (wallet, condition), g in history.groupby(["sample_wallet", "sample_condition_id"]):
        red = g.loc[g.type.eq("REDEEM") & pd.to_numeric(g["size"], errors="coerce").gt(0)]
        if red.empty:
            continue
        for outcome, rgroup in red.groupby("outcome"):
            redeemed = float(pd.to_numeric(rgroup["size"]).sum())
            first_claim_ts = int(rgroup.timestamp.min())
            q = 0.0
            for row in g.loc[g.timestamp.le(first_claim_ts)].to_dict("records"):
                qty = float(row.get("size") or 0)
                if row.get("type") == "TRADE" and row.get("outcome") == outcome:
                    q += qty * (1 if row.get("side") == "BUY" else -1)
                elif row.get("type") == "MERGE":
                    q -= qty
                elif row.get("type") == "SPLIT":
                    q += qty
            payout.append({"wallet": wallet, "conditionId": condition, "outcome": outcome,
                           "reconstructed_winner_net": q, "reported_redeemed_size": redeemed,
                           "recorded_net_minus_claimed_amount": q - redeemed,
                           "recorded_net_equals_claimed_amount_1e-5": abs(q - redeemed) < 1e-5})
    pd.DataFrame(payout).to_csv(p6 / "polymarket_wallet_payout_reconciliation_sample.csv", index=False)
    summary = {
        "sampled_wallet_market_pairs_with_target": int(len(result)),
        "pairs_with_strictly_earlier_api_activity": int(result.prior_observed_history_exists.sum()),
        "pairs_with_same_second_api_activity": int(result.same_second_activity_rows.gt(0).sum()),
        "positive_recorded_own_token_net_before_target": int(result.target_token_recorded_net_before_trade.gt(1e-6).sum()),
        "zero_recorded_own_token_net_before_target": int(result.target_token_recorded_net_before_trade.abs().le(1e-6).sum()),
        "positive_recorded_other_token_net_before_target": int(result.other_token_recorded_net_before_trade.gt(1e-6).sum()),
        "payout_reconciliation_rows": len(payout),
        "recorded_net_equals_claimed_amount_1e-5": int(sum(
            row["recorded_net_equals_claimed_amount_1e-5"] for row in payout)),
        "limits": [
            "Target pair selection is a stratified feasibility sample, not a representative sample of all target trades.",
            "Activity histories contained TRADE, MERGE, and REDEEM only in this sample; absence of SPLIT/TRANSFER rows does not prove no such on-chain position changes occurred.",
            "Activity timestamps are second-resolution. Same-second pre-trade ordering is not reconstructed.",
            "Zero recorded net is not evidence of a fresh position; positive recorded net is a lower-bound proxy, not a verified wallet balance.",
            "A recorded token balance larger than a redemption claim may reflect partial redemption; it does not by itself prove missing activity or a balance error.",
            "Redemption amount validation against chain receipts is reported separately and does not prove full position histories.",
        ],
    }
    (p6 / "polymarket_wallet_position_sample.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
