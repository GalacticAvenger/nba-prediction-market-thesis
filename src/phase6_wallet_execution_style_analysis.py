"""Compare extreme pre-game trading styles within matched game-state cells."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from phase6_wallet_common_support import fit_many  # noqa: E402

P6 = ROOT / "data/interim/phase6/prior_game_behavior/execution_style"
INPUT = P6 / "target_buys_with_execution_styles.parquet"
OUT = P6
CELL_KEYS = ["game_id", "minute", "pbin", "role"]
OUTCOMES = ("price_minus_realized_payoff", "benchmark_overpayment",
            "outcome_minus_benchmark")


def main() -> None:
    q = pd.read_parquet(INPUT)
    q = q.loc[
        q.prior_distinct_transactions.ge(20) &
        q.prior_transaction_games.ge(3)
    ].copy()
    q["price_minus_realized_payoff"] = -q.settlement_payoff_minus_cost
    pair = q.drop_duplicates(["wallet", "game_id"])
    cuts = {
        "cadence_p25": float(pair.prior_transactions_per_active_day.quantile(.25)),
        "cadence_p75": float(pair.prior_transactions_per_active_day.quantile(.75)),
        "ticket_p25_usd": float(pair.prior_median_transaction_notional_usd.quantile(.25)),
        "ticket_p75_usd": float(pair.prior_median_transaction_notional_usd.quantile(.75)),
    }
    q["cadence_extreme"] = np.select(
        [q.prior_transactions_per_active_day.le(cuts["cadence_p25"]),
         q.prior_transactions_per_active_day.ge(cuts["cadence_p75"])],
        ["lower_cadence_quartile", "higher_cadence_quartile"], default="middle")
    q["ticket_extreme"] = np.select(
        [q.prior_median_transaction_notional_usd.le(cuts["ticket_p25_usd"]),
         q.prior_median_transaction_notional_usd.ge(cuts["ticket_p75_usd"])],
        ["smaller_ticket_quartile", "larger_ticket_quartile"], default="middle")

    results, group_counts = [], []
    comparisons = [
        ("higher_vs_lower_cadence_quartile", q.cadence_extreme.eq("higher_cadence_quartile"),
         q.cadence_extreme.eq("lower_cadence_quartile")),
        ("larger_vs_smaller_ticket_quartile", q.ticket_extreme.eq("larger_ticket_quartile"),
         q.ticket_extreme.eq("smaller_ticket_quartile")),
    ]
    for name, high, low in comparisons:
        frame = q.loc[high | low].copy()
        frame["high_style"] = high.loc[frame.index].astype(bool)
        support = frame.groupby(CELL_KEYS, observed=True).high_style.agg(["min", "max"])
        support = support.loc[(support["min"] == 0) & (support["max"] == 1)].index
        common = frame.set_index(CELL_KEYS).loc[lambda z: z.index.isin(support)].reset_index()
        estimates, matched, cells = fit_many(common, OUTCOMES, "high_style", name, CELL_KEYS)
        for x in estimates:
            x["profile_threshold"] = cuts
            x["interpretation"] = "high-minus-low style association; positive price-minus-payoff means greater realized overpayment"
        results.extend(estimates)
        for group, z in matched.groupby("high_style", observed=True):
            group_counts.append({"comparison": name, "high_style": bool(group),
                                 "rows": int(len(z)), "wallets": int(z.wallet.nunique()),
                                 "games": int(z.game_id.nunique()), "cells": int(cells),
                                 "mean_price_minus_realized_payoff_pp": float(z.price_minus_realized_payoff.mean() * 100),
                                 "mean_price_minus_benchmark_pp": float(z.benchmark_overpayment.mean() * 100),
                                 "mean_outcome_minus_benchmark_pp": float(z.outcome_minus_benchmark.mean() * 100)})

    pd.DataFrame(results).to_csv(OUT / "execution_style_extreme_contrasts.csv", index=False)
    pd.DataFrame(group_counts).to_csv(OUT / "execution_style_extreme_group_means.csv", index=False)
    summary = {
        "design": "Outcome-free prior-game wallet characteristics; extreme quartiles compared within game x final-five minute x P* band x participant role common-support cells. Two-way game/wallet clustered uncertainty.",
        "quartile_cutoffs_equal_weight_wallet_game_pairs": cuts,
        "eligible_buy_records": int(len(q)), "eligible_wallets": int(q.wallet.nunique()),
        "games": int(q.game_id.nunique()),
        "results": results,
        "limits": [
            "These are conditional associations within a selected late-game longshot-buy cohort, not causal effects.",
            "Higher cadence is only a proxy for automation; ticket size is only a proxy for account scale.",
            "Extreme-quartile comparisons discard middle observations and can have limited common support.",
            "One realized outcome is shared by all records in a game; game and wallet clustering accounts for this dependence asymptotically.",
            "The analyses are exploratory and not multiplicity-adjusted; the transaction-style contribution decomposition is a separate accounting exercise.",
        ],
    }
    (OUT / "execution_style_extreme_contrasts.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
