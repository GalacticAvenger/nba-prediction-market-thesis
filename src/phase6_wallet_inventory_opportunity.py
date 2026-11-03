"""Audit whether sampled pre-transaction inventory tracks prior same-token buys.

This is a descriptive follow-up to the hash-ranked Phase 6 validation sample.
It uses only strictly earlier Activity API rows to measure prior purchase
opportunity, and the independently reconstructed on-chain balance at the start
of the selected buy transaction to measure pre-existing inventory.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P6 = ROOT / "data/interim/phase6"
OUT = P6 / "polymarket_wallet_inventory_opportunity"
MATCHED_STATUS = "unique_order_and_transfer"
EPS = 1e-6


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    exact_parts = [
        pd.read_csv(P6 / "polymarket_wallet_exact_fill_balance_sample.csv"),
        pd.read_csv(P6 / "inventory_extension/polymarket_wallet_exact_fill_balance_sample.csv"),
    ]
    exact = pd.concat(exact_parts, ignore_index=True)
    histories = pd.concat([
        pd.read_parquet(P6 / "polymarket_wallet_history_sample.parquet"),
        pd.read_parquet(P6 / "inventory_extension/polymarket_wallet_history_sample.parquet"),
    ], ignore_index=True)

    for col in ("wallet", "conditionId", "transactionHash", "target_asset"):
        exact[col] = exact[col].astype(str).str.lower()
    exact["balance_at_transaction_start"] = pd.to_numeric(
        exact.balance_at_transaction_start, errors="coerce")
    exact["target_trade_size"] = pd.to_numeric(exact.target_trade_size, errors="coerce")
    exact["target_trade_price"] = pd.to_numeric(exact.target_trade_price, errors="coerce")
    exact = exact.loc[exact.status.eq(MATCHED_STATUS)].copy()

    target = pd.read_parquet(P6 / "polymarket_wallet_late5_target_trades.parquet")
    for col in ("wallet", "conditionId", "transactionHash", "asset"):
        target[col] = target[col].astype(str).str.lower()
    target = target.rename(columns={
        "asset": "target_asset", "size": "target_trade_size",
        "price": "target_trade_price", "timestamp": "target_timestamp",
    })
    key = ["wallet", "conditionId", "transactionHash", "target_asset",
           "target_trade_size", "target_trade_price"]
    exact = exact.merge(
        target[key + ["target_timestamp", "y_own", "pstar_own"]],
        on=key, how="left", validate="one_to_one")
    if exact.target_timestamp.isna().any():
        raise ValueError("Some exact on-chain matches did not join to their target trade")

    histories["sample_wallet"] = histories.sample_wallet.astype(str).str.lower()
    histories["sample_condition_id"] = histories.sample_condition_id.astype(str).str.lower()
    histories["asset"] = histories.asset.astype(str)
    histories["type"] = histories.type.astype(str).str.upper()
    histories["side"] = histories.side.astype(str).str.upper()
    histories["timestamp"] = pd.to_numeric(histories.timestamp, errors="coerce")
    histories["size"] = pd.to_numeric(histories["size"], errors="coerce").fillna(0.0)
    return exact, histories


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    exact, histories = load_inputs()
    history_groups = {
        (wallet, condition): group.sort_values(["timestamp", "transactionHash"])
        for (wallet, condition), group in histories.groupby(
            ["sample_wallet", "sample_condition_id"], sort=False)
    }

    rows: list[dict] = []
    for target in exact.to_dict("records"):
        group = history_groups.get((target["wallet"], target["conditionId"]))
        if group is None:
            prior = histories.iloc[0:0]
            first_ts = np.nan
        else:
            # Activity timestamps are only second-resolution. Excluding all rows
            # at the target second avoids inventing within-second ordering.
            prior = group.loc[group.timestamp.lt(int(target["target_timestamp"]))]
            first_ts = group.timestamp.min()
        own = prior.loc[prior.asset.eq(target["target_asset"])]
        own_trades = own.loc[own.type.eq("TRADE")]
        prior_buys = own_trades.loc[own_trades.side.eq("BUY")]
        prior_sells = own_trades.loc[own_trades.side.eq("SELL")]
        positive = bool(target["balance_at_transaction_start"] > EPS)
        rows.append({
            "wallet": target["wallet"],
            "conditionId": target["conditionId"],
            "game_id": target["game_id"],
            "transactionHash": target["transactionHash"],
            "profile_stratum": target["profile_stratum"],
            "sample_role": target["role"],
            "chain_participant_role": target["matched_onchain_participant_role"],
            "target_timestamp": int(target["target_timestamp"]),
            "target_trade_size": target["target_trade_size"],
            "target_trade_price": target["target_trade_price"],
            "y_own": target["y_own"],
            "pstar_own": target["pstar_own"],
            "pretransaction_target_balance": target["balance_at_transaction_start"],
            "positive_pretransaction_target_balance": positive,
            "prior_activity_rows_strict_seconds": int(len(prior)),
            "prior_same_token_buy_records_strict_seconds": int(len(prior_buys)),
            "prior_same_token_sell_records_strict_seconds": int(len(prior_sells)),
            "prior_same_token_buy_shares_api": float(prior_buys["size"].sum()),
            "first_observed_market_activity_timestamp": first_ts,
            "observed_market_exposure_days": (
                (int(target["target_timestamp"]) - first_ts) / 86400
                if pd.notna(first_ts) else np.nan),
        })

    detail = pd.DataFrame(rows)
    detail["has_prior_same_token_buy"] = detail[
        "prior_same_token_buy_records_strict_seconds"].gt(0)
    detail["pretransaction_balance_to_buy_ratio"] = (
        detail.pretransaction_target_balance / detail.target_trade_size)
    detail["y_minus_price_pp"] = (
        detail.y_own - detail.target_trade_price) * 100
    detail["y_minus_pstar_pp"] = (detail.y_own - detail.pstar_own) * 100
    detail.to_csv(OUT / "wallet_inventory_opportunity_detail.csv", index=False)

    by_profile = []
    for profile, group in detail.groupby("profile_stratum", sort=True):
        prior = group.loc[group.has_prior_same_token_buy]
        no_prior = group.loc[~group.has_prior_same_token_buy]
        positive = group.loc[group.positive_pretransaction_target_balance]
        by_profile.append({
            "profile_stratum": profile,
            "unique_chain_matched_pairs": int(len(group)),
            "positive_pretransaction_inventory": int(group.positive_pretransaction_target_balance.sum()),
            "positive_share": float(group.positive_pretransaction_target_balance.mean()),
            "pairs_with_prior_same_token_buy": int(len(prior)),
            "share_with_prior_same_token_buy": float(group.has_prior_same_token_buy.mean()),
            "mean_prior_same_token_buy_records": float(group.prior_same_token_buy_records_strict_seconds.mean()),
            "median_prior_same_token_buy_records": float(group.prior_same_token_buy_records_strict_seconds.median()),
            "positive_inventory_share_given_prior_buy": float(prior.positive_pretransaction_target_balance.mean()) if len(prior) else None,
            "positive_inventory_share_without_recorded_prior_buy": float(no_prior.positive_pretransaction_target_balance.mean()) if len(no_prior) else None,
            "median_inventory_to_buy_ratio_if_positive": float(
                positive.pretransaction_balance_to_buy_ratio.median()) if len(positive) else None,
            "mean_y_minus_price_pp": float(group.y_minus_price_pp.mean()),
            "mean_y_minus_pstar_pp": float(group.y_minus_pstar_pp.mean()),
        })

    high = detail.profile_stratum.eq("high_activity")
    nonhigh = ~high
    conditional = {}
    for label, mask in [("high_activity", high), ("other_sampled_profiles", nonhigh)]:
        group = detail.loc[mask]
        prior = group.loc[group.has_prior_same_token_buy]
        no_prior = group.loc[~group.has_prior_same_token_buy]
        conditional[label] = {
            "n": int(len(group)),
            "pretransaction_inventory_positive": int(group.positive_pretransaction_target_balance.sum()),
            "positive_inventory_share": float(group.positive_pretransaction_target_balance.mean()),
            "prior_buy_records_mean": float(group.prior_same_token_buy_records_strict_seconds.mean()),
            "prior_buy_records_median": float(group.prior_same_token_buy_records_strict_seconds.median()),
            "share_with_prior_same_token_buy": float(group.has_prior_same_token_buy.mean()),
            "n_with_prior_same_token_buy": int(len(prior)),
            "positive_share_with_prior_same_token_buy": float(prior.positive_pretransaction_target_balance.mean()) if len(prior) else None,
            "n_without_recorded_prior_same_token_buy": int(len(no_prior)),
            "positive_share_without_recorded_prior_same_token_buy": float(no_prior.positive_pretransaction_target_balance.mean()) if len(no_prior) else None,
        }

    inventory_outcomes = {}
    for label, mask in [
        ("no_positive_pretransaction_balance", ~detail.positive_pretransaction_target_balance),
        ("positive_pretransaction_balance", detail.positive_pretransaction_target_balance),
    ]:
        group = detail.loc[mask]
        inventory_outcomes[label] = {
            "n": int(len(group)),
            "mean_y_minus_price_pp": float(group.y_minus_price_pp.mean()),
            "mean_y_minus_pstar_pp": float(group.y_minus_pstar_pp.mean()),
            "mean_purchase_price_pp": float(group.target_trade_price.mean() * 100),
            "mean_pstar_pp": float(group.pstar_own.mean() * 100),
        }

    summary = {
        "sample": {
            "unique_fill_and_transfer_matches": int(len(detail)),
            "profile_design": "hash-ranked, balanced sample across month × observable profile × Activity-record-role cells; not population-representative",
            "inventory_measure": "on-chain target-token balance at the start of the target transaction, before any same-transaction transfers or fills",
            "prior_purchase_measure": "strictly earlier, second-resolution Activity API TRADE/BUY records for the same target token",
        },
        "high_activity_vs_other_sampled_profiles": conditional,
        "profile_results": by_profile,
        "outcomes_by_pretransaction_inventory": inventory_outcomes,
        "limits": [
            "The sample is balanced by design across profile strata and is not population weighted.",
            "Profile differences are descriptive and are not causal effects.",
            "Prior Activity API buys measure recorded purchase opportunity, not complete prior trading; transfers, same-second ordering, and missing records can remain.",
            "A prior same-token buy does not reveal cost basis or whether the position was losing, so it cannot identify loss chasing.",
            "The inventory-performance comparisons are descriptive sample means without inferential intervals.",
        ],
    }
    (OUT / "wallet_inventory_opportunity_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    pd.DataFrame(by_profile).to_csv(OUT / "wallet_inventory_opportunity_by_profile.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
