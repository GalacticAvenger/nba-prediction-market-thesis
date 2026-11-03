"""Cell-matched comparisons of observable Polymarket wallet profiles.

This is an exploratory association analysis. It does not identify bots, retail
investors, causal price impact, or wallet profit. The linear contrast adjusts
for exact game, regulation-minute, benchmark-probability band, and participant
role; uncertainty is clustered by game and wallet using a two-way sandwich.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P6 = ROOT / "data/interim/phase6"
INPUT = P6 / "polymarket_wallet_late5_target_trades.parquet"


def fit_many(frame: pd.DataFrame, outcomes: tuple[str, ...], treatment: str,
             comparison: str, cell_keys: list[str]) -> tuple[list[dict], pd.DataFrame, int]:
    """Estimate a cell-fixed-effect contrast and two-way clustered intervals.

    The coefficient is the inverse-variance weighted mean of within-cell
    group differences, exactly equivalent to OLS with a separate intercept
    for every common-support cell and a binary group indicator.
    """
    q = frame.copy()
    agg = {"n": ("wallet", "size")}
    agg.update({f"{outcome}_mean": (outcome, "mean") for outcome in outcomes})
    groups = q.groupby(cell_keys + [treatment], observed=True).agg(**agg).reset_index()
    left = groups.loc[~groups[treatment]].drop(columns=treatment).set_index(cell_keys)
    right = groups.loc[groups[treatment]].drop(columns=treatment).set_index(cell_keys)
    pairs = left.add_suffix("_0").join(right.add_suffix("_1"), how="inner").reset_index()
    pairs["weight"] = pairs.n_0 * pairs.n_1 / (pairs.n_0 + pairs.n_1)
    weight_sum = float(pairs.weight.sum())
    common = q.merge(pairs, on=cell_keys, how="inner", validate="many_to_one")
    is_treated = common[treatment].astype(bool).to_numpy()
    p_cell = common.n_1.to_numpy() / (common.n_0.to_numpy() + common.n_1.to_numpy())
    x_within = is_treated.astype(float) - p_cell
    score_columns = []
    for outcome in outcomes:
        diff = pairs[f"{outcome}_mean_1"] - pairs[f"{outcome}_mean_0"]
        beta = float(np.average(diff, weights=pairs.weight))
        cell_fit = (common[f"{outcome}_mean_0"].to_numpy()
                    + p_cell * (common[f"{outcome}_mean_1"].to_numpy()
                                - common[f"{outcome}_mean_0"].to_numpy() - beta)
                    + beta * is_treated.astype(float))
        residual = common[outcome].to_numpy(dtype=float) - cell_fit
        score_columns.append(x_within * residual / weight_sum)
    score = np.column_stack(score_columns)
    frame_keys = pd.DataFrame({"game": common.game_id.to_numpy(),
                               "wallet": common.wallet.to_numpy()})
    cluster_counts = {}
    meat_diag = np.zeros(len(outcomes))
    for key in ("game", "wallet", "intersection"):
        cluster = (frame_keys.game.astype(str) + "|" + frame_keys.wallet.astype(str)
                   if key == "intersection" else frame_keys[key])
        summed = pd.DataFrame(score).groupby(cluster, sort=False).sum().to_numpy()
        count = len(summed)
        cluster_counts[key] = count
        factor = count / (count - 1) if count > 1 else 1.0
        component = factor * (summed * summed).sum(axis=0)
        meat_diag += -component if key == "intersection" else component
    ses = np.sqrt(np.maximum(meat_diag, 0))
    results = []
    for i, outcome in enumerate(outcomes):
        estimate = float(np.average(pairs[f"{outcome}_mean_1"]
                                    - pairs[f"{outcome}_mean_0"], weights=pairs.weight))
        results.append({"comparison": comparison, "outcome": outcome,
                        "estimate": estimate, "se_two_way_cluster": float(ses[i]),
                        "ci95_low": estimate - 1.96 * float(ses[i]),
                        "ci95_high": estimate + 1.96 * float(ses[i]),
                        "rows": len(common), "cells": len(pairs),
                        "games": int(common.game_id.nunique()),
                        "wallets": int(common.wallet.nunique()), "clusters": cluster_counts})
    return results, common, len(pairs)


def main() -> None:
    df = pd.read_parquet(INPUT)
    df = df.loc[df.high_activity_ge_20_per_active_day.notna()].copy()
    df["high_activity"] = df.high_activity_ge_20_per_active_day.astype(bool)
    df["minute"] = np.floor((300 - df.clock_s_remaining) / 60).clip(0, 4).astype(int)
    # Bins are fixed before outcomes are examined; all bins lie within the
    # selected underdog region and preserve finer benchmark states.
    bins = [0, .05, .10, .15, .20, .25, .30, .40, .50]
    df["pbin"] = pd.cut(df.pstar_own, bins=bins, include_lowest=True,
                        labels=False, right=True)
    keys = ["game_id", "minute", "pbin", "role"]
    support = df.groupby(keys, observed=True).high_activity.agg(["min", "max"])
    support = support.loc[(support["min"] == 0) & (support["max"] == 1)].index
    common = df.set_index(keys).loc[lambda x: x.index.isin(support)].reset_index()
    outcomes = ("settlement_payoff_minus_cost", "outcome_minus_benchmark",
                "benchmark_overpayment")
    contrasts = [{"comparison": "high_activity_vs_other_accounts",
                  "frame": common, "treatment": "high_activity",
                  "eligible_rows": len(df)}]

    # Maker- and taker-record-dominant profiles are mutually exclusive under
    # the 75% record-share cutoff. Remove other accounts before defining support.
    role = df.loc[df["maker_record_share_ge_0.75"].fillna(False)
                  | df["taker_record_share_ge_0.75"].fillna(False)].copy()
    role["maker_dominant"] = role["maker_record_share_ge_0.75"].fillna(False).astype(bool)
    role["taker_dominant"] = role["taker_record_share_ge_0.75"].fillna(False).astype(bool)
    role_keys = ["game_id", "minute", "pbin", "role"]
    role_support = role.groupby(role_keys, observed=True).maker_dominant.agg(["min", "max"])
    role_support = role_support.loc[(role_support["min"] == 0)
                                    & (role_support["max"] == 1)].index
    role_common = role.set_index(role_keys).loc[
        lambda x: x.index.isin(role_support)].reset_index()
    contrasts.append({"comparison": "maker_dominant_vs_taker_dominant",
                      "frame": role_common, "treatment": "maker_dominant",
                      "eligible_rows": len(role)})

    all_results, group_summaries = [], []
    for contrast in contrasts:
        frame = contrast["frame"]
        fitted, frame, n_cells = fit_many(frame, outcomes, contrast["treatment"],
                                          contrast["comparison"], keys)
        all_results.extend(fitted)
        counts = frame.groupby(contrast["treatment"]).agg(
        rows=("wallet", "size"), wallets=("wallet", "nunique"),
        games=("game_id", "nunique"),
        mean_y_minus_price=("settlement_payoff_minus_cost", "mean"),
        mean_y_minus_pstar=("outcome_minus_benchmark", "mean"),
        mean_price_minus_pstar=("benchmark_overpayment", "mean"),
        ).reset_index().to_dict("records")
        group_summaries.append({"comparison": contrast["comparison"],
                                "support_rows": len(frame),
                                "support_cells": n_cells,
                                "eligible_rows": contrast["eligible_rows"],
                                "support_share_of_eligible": len(frame) / contrast["eligible_rows"],
                                "groups": counts})
    summary = {
        "design": "Common-support OLS contrasts with game, final-five regulation-minute, fixed P* band, and participant-role fixed effects; two-way game/wallet clustered standard errors.",
        "support_cells": len(support), "support_keys": keys,
        "support_rows": len(common), "support_share_of_screen": len(common) / len(df),
        "group_summaries": group_summaries, "results": all_results,
        "limitations": [
            "This is a conditional association, not a causal effect or identity classification.",
            "The comparison is high-activity versus a heterogeneous remainder; activity profiles can overlap with other behavioral dimensions.",
            "P* is estimated, and the target cohort is selected on price, clock, side, and P*.",
            "The two-way cluster sandwich uses game, wallet, and their intersection; intervals are asymptotic.",
        ],
    }
    (P6 / "polymarket_wallet_common_support.json").write_text(json.dumps(summary, indent=2) + "\n")
    pd.DataFrame(all_results).to_csv(P6 / "polymarket_wallet_common_support.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
