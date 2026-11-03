"""Summarize the original and nonoverlapping on-chain inventory samples."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P6 = ROOT / "data/interim/phase6"


def main() -> None:
    original = pd.read_csv(P6 / "polymarket_wallet_exact_fill_balance_sample.csv")
    extension = pd.read_csv(
        P6 / "inventory_extension/polymarket_wallet_exact_fill_balance_sample.csv")
    key = ["wallet", "conditionId"]
    overlap = set(map(tuple, original[key].astype(str).to_numpy())) & set(
        map(tuple, extension[key].astype(str).to_numpy()))
    if overlap:
        raise ValueError(f"Original and extension samples overlap on {len(overlap)} pairs")
    payout_a = pd.read_csv(P6 / "polymarket_wallet_redemption_receipt_validation.csv")
    payout_b = pd.read_csv(
        P6 / "inventory_extension/polymarket_wallet_redemption_receipt_validation.csv")
    payout_tx_overlap = set(payout_a.activity_transaction_hash.astype(str).str.lower()) & set(
        payout_b.activity_transaction_hash.astype(str).str.lower())
    if payout_tx_overlap:
        raise ValueError(f"Original and extension redemption receipts overlap on {len(payout_tx_overlap)} transactions")
    ledgers_a = pd.read_csv(P6 / "polymarket_wallet_payout_reconciliation_sample.csv")
    ledgers_b = pd.read_csv(
        P6 / "inventory_extension/polymarket_wallet_payout_reconciliation_sample.csv")
    ledgers = pd.concat([ledgers_a, ledgers_b], ignore_index=True)
    rows = pd.concat([original, extension], ignore_index=True)
    rows["matched"] = rows.status.eq("unique_order_and_transfer")
    rows["positive_inventory"] = rows.matched & pd.to_numeric(
        rows.balance_immediately_before_matched_transfer, errors="coerce").gt(1e-6)
    rows["balance_to_buy_ratio"] = pd.to_numeric(
        rows.balance_immediately_before_matched_transfer, errors="coerce") / pd.to_numeric(
            rows.target_trade_size, errors="coerce")
    targets = pd.read_parquet(P6 / "polymarket_wallet_late5_target_trades.parquet")
    for column in ("wallet", "conditionId", "transactionHash", "asset"):
        targets[column] = targets[column].astype(str).str.lower()
    matched = rows.loc[rows.matched].merge(
        targets,
        left_on=["wallet", "conditionId", "transactionHash", "target_asset",
                 "target_trade_price", "target_trade_size"],
        right_on=["wallet", "conditionId", "transactionHash", "asset", "price", "size"],
        how="left", validate="one_to_one")
    if matched.y_own.isna().any():
        raise ValueError("Some exact-fill matches did not join to a unique audited outcome row")
    matched["preexisting_inventory"] = pd.to_numeric(
        matched.balance_immediately_before_matched_transfer, errors="coerce").gt(1e-6)

    def outcome_block(frame: pd.DataFrame) -> dict:
        return {
            "n": int(len(frame)),
            "mean_realized_outcome": float(frame.y_own.mean()),
            "mean_purchase_price": float(frame.price.mean()),
            "mean_market_free_Pstar": float(frame.pstar_own.mean()),
            "mean_Y_minus_price_percentage_points": float((frame.y_own - frame.price).mean() * 100),
            "mean_Y_minus_Pstar_percentage_points": float((frame.y_own - frame.pstar_own).mean() * 100),
        }

    summary = {
        "original_pairs": int(len(original)),
        "extension_pairs": int(len(extension)),
        "overlap_pairs": int(len(overlap)),
        "combined_pairs": int(len(rows)),
        "unique_fill_transfer_matches": int(rows.matched.sum()),
        "ambiguous_or_unmatched": int((~rows.matched).sum()),
        "positive_inventory_before_matched_transfer": int(rows.positive_inventory.sum()),
        "interpretation": (
            "Descriptive estimates for two hash-ranked, stratified validation samples. "
            "They are not population estimates, and the match-restricted inventory rate "
            "is reported alongside worst-case bounds for unresolved matches."
        ),
        "profile_strata": [],
        "purchase_outcomes_by_preexisting_inventory": {
            "not_preexisting": outcome_block(matched.loc[~matched.preexisting_inventory]),
            "preexisting": outcome_block(matched.loc[matched.preexisting_inventory]),
            "by_profile_stratum": [],
            "interpretation": "Descriptive only: the selected wallet-market sample is stratified and is not a representative sample or causal comparison.",
        },
        "redemption_validation": {
            "nonoverlapping_positive_redemption_rows": int(len(payout_a) + len(payout_b)),
            "activity_payouts_matching_onchain_PayoutRedemption": int(
                payout_a["amount_matches_1e-6"].sum() + payout_b["amount_matches_1e-6"].sum()),
            "recorded_trade_merge_net_equals_claim": int(
                ledgers["recorded_net_equals_claimed_amount_1e-5"].sum()),
            "recorded_trade_merge_comparisons": int(len(ledgers)),
            "interpretation": "The payout field is validated against the matching on-chain payout event; trade/merge equality remains an incomplete-ledger diagnostic and does not validate the full position.",
        },
    }
    for (profile, preexisting), group in matched.groupby(
            ["profile_stratum", "preexisting_inventory"], sort=True):
        summary["purchase_outcomes_by_preexisting_inventory"]["by_profile_stratum"].append({
            "profile_stratum": profile, "preexisting_inventory": bool(preexisting),
            **outcome_block(group),
        })
    for profile, group in rows.groupby("profile_stratum", sort=True):
        n = len(group)
        matched = int(group.matched.sum())
        positive = int(group.positive_inventory.sum())
        unresolved = n - matched
        ratios = group.loc[group.matched, "balance_to_buy_ratio"]
        summary["profile_strata"].append({
            "profile_stratum": profile,
            "sampled_pairs": n,
            "matched_pairs": matched,
            "ambiguous_or_unmatched": unresolved,
            "positive_pretransfer_inventory_among_matches": positive,
            "positive_share_among_matches": positive / matched if matched else None,
            "worst_case_positive_share_all_sampled_lower": positive / n if n else None,
            "worst_case_positive_share_all_sampled_upper": (positive + unresolved) / n if n else None,
            "positive_balance_at_least_10pct_of_buy_size": int(ratios.ge(.1).sum()),
            "positive_balance_at_least_buy_size": int(ratios.ge(1).sum()),
            "median_balance_to_buy_ratio_among_positive_matches": (
                float(ratios[ratios.gt(1e-6)].median()) if ratios.gt(1e-6).any() else None),
        })

    high = summary["profile_strata"]
    high = next(row for row in high if row["profile_stratum"] == "high_activity")
    other = [row for row in summary["profile_strata"]
             if row["profile_stratum"] != "high_activity"]
    other_n = sum(row["sampled_pairs"] for row in other)
    other_positive = sum(row["positive_pretransfer_inventory_among_matches"] for row in other)
    other_unresolved = sum(row["ambiguous_or_unmatched"] for row in other)
    summary["high_activity_vs_other_sample_bounds"] = {
        "high_activity_sampled": high["sampled_pairs"],
        "high_activity_known_positive": high["positive_pretransfer_inventory_among_matches"],
        "high_activity_unresolved": high["ambiguous_or_unmatched"],
        "high_activity_positive_share_bounds_if_unresolved_are_all_zero_or_all_one": [
            high["worst_case_positive_share_all_sampled_lower"],
            high["worst_case_positive_share_all_sampled_upper"]],
        "other_profiles_sampled": other_n,
        "other_profiles_known_positive": other_positive,
        "other_profiles_unresolved": other_unresolved,
        "other_profiles_positive_share_bounds_if_unresolved_are_all_zero_or_all_one": [
            other_positive / other_n, (other_positive + other_unresolved) / other_n],
        "minimum_gap_high_minus_other_under_worst_case_match_status": (
            high["worst_case_positive_share_all_sampled_lower"]
            - (other_positive + other_unresolved) / other_n),
        "note": "Bounds cover unresolved receipt joins within these stratified samples only; they do not cover sampling uncertainty or identify population prevalence.",
    }

    out = P6 / "polymarket_wallet_inventory_extension_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    pd.DataFrame(summary["profile_strata"]).to_csv(
        P6 / "polymarket_wallet_inventory_extension_summary.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
