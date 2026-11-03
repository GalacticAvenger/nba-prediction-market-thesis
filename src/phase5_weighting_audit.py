"""Audit final-five estimand contrasts, trade-count weighting, and first-time ties.

The script uses the existing Phase 5 late-trade cache. It reports the two
longshot price bands in PREDICTIONS.md (folded to the lower-priced contract),
paired game-cluster bootstrap contrasts, game-level row-count diagnostics, and
the ambiguity created when multiple eligible trades share a game's earliest
recorded timestamp.

These are descriptive analyses. They do not establish prospective
specification or causal effects.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

DRAWS = 10_000
SEED = 6_102_126
BANDS = ((0.05, 0.20, "5_20c"), (0.10, 0.40, "10_40c"))


def pct_interval(draws: np.ndarray) -> tuple[float, float]:
    return tuple(np.quantile(draws, [0.025, 0.975]).astype(float))


def bootstrap_band(games: pd.DataFrame, band: str, eligible_rows: int,
                   panel_games: int, late5_games: int) -> tuple[list[dict], dict, pd.DataFrame]:
    games = games.sort_values("game_id", kind="stable").reset_index(drop=True)
    n = games["trade_rows"].to_numpy(float)
    mean_a = games["game_mean_price_minus_payoff"].to_numpy(float)
    first_ts = games["earliest_timestamp_mean"].to_numpy(float)
    tie_min = games["earliest_timestamp_min"].to_numpy(float)
    tie_max = games["earliest_timestamp_max"].to_numpy(float)
    g = len(games)

    points = {
        "equal_game": mean_a.mean(),
        "pooled_trade_row": np.average(mean_a, weights=n),
        "earliest_timestamp_game_mean": first_ts.mean(),
        "earliest_timestamp_single_row_min_bound": tie_min.mean(),
        "earliest_timestamp_single_row_max_bound": tie_max.mean(),
    }
    names = list(points)
    bootstrap = {name: np.empty(DRAWS) for name in names}
    contrasts = {
        "equal_game_minus_pooled_trade_row": np.empty(DRAWS),
        "equal_game_minus_earliest_timestamp_game_mean": np.empty(DRAWS),
        "pooled_trade_row_minus_earliest_timestamp_game_mean": np.empty(DRAWS),
    }
    correlation = {"pearson_log_trade_rows": np.empty(DRAWS),
                   "spearman_log_trade_rows": np.empty(DRAWS)}
    log_n = np.log(n)
    rng = np.random.default_rng(SEED + (0 if band == "5_20c" else 1))

    start = 0
    batch_size = 500
    while start < DRAWS:
        stop = min(start + batch_size, DRAWS)
        idx = rng.integers(0, g, size=(stop - start, g))
        nn = n[idx]
        mm = mean_a[idx]
        ff = first_ts[idx]
        lo = tie_min[idx]
        hi = tie_max[idx]
        eq = mm.mean(axis=1)
        pool = (mm * nn).sum(axis=1) / nn.sum(axis=1)
        first = ff.mean(axis=1)
        bootstrap["equal_game"][start:stop] = eq
        bootstrap["pooled_trade_row"][start:stop] = pool
        bootstrap["earliest_timestamp_game_mean"][start:stop] = first
        bootstrap["earliest_timestamp_single_row_min_bound"][start:stop] = lo.mean(axis=1)
        bootstrap["earliest_timestamp_single_row_max_bound"][start:stop] = hi.mean(axis=1)
        contrasts["equal_game_minus_pooled_trade_row"][start:stop] = eq - pool
        contrasts["equal_game_minus_earliest_timestamp_game_mean"][start:stop] = eq - first
        contrasts["pooled_trade_row_minus_earliest_timestamp_game_mean"][start:stop] = pool - first

        xx = np.log(nn)
        yy = mm
        xc = xx - xx.mean(axis=1, keepdims=True)
        yc = yy - yy.mean(axis=1, keepdims=True)
        denom = np.sqrt((xc * xc).sum(axis=1) * (yc * yc).sum(axis=1))
        correlation["pearson_log_trade_rows"][start:stop] = (xc * yc).sum(axis=1) / denom
        xr = rankdata(xx, axis=1)
        yr = rankdata(yy, axis=1)
        xrc = xr - xr.mean(axis=1, keepdims=True)
        yrc = yr - yr.mean(axis=1, keepdims=True)
        rdenom = np.sqrt((xrc * xrc).sum(axis=1) * (yrc * yrc).sum(axis=1))
        correlation["spearman_log_trade_rows"][start:stop] = (xrc * yrc).sum(axis=1) / rdenom
        start = stop

    records = []
    for name, point in points.items():
        low, high = pct_interval(bootstrap[name])
        rows_used = int(games["earliest_timestamp_rows"].sum()) if name.startswith("earliest_timestamp_") else eligible_rows
        records.append({"band": band, "result_type": "estimator", "name": name,
                        "estimate_pp": point * 100, "ci95_low_pp": low * 100,
                        "ci95_high_pp": high * 100, "band_cohort_rows": eligible_rows,
                        "rows_used_by_estimator": rows_used,
                        "games": g, "bootstrap_draws": DRAWS,
                        "seed": SEED + (0 if band == "5_20c" else 1)})
    contrast_points = {
        "equal_game_minus_pooled_trade_row": points["equal_game"] - points["pooled_trade_row"],
        "equal_game_minus_earliest_timestamp_game_mean": points["equal_game"] - points["earliest_timestamp_game_mean"],
        "pooled_trade_row_minus_earliest_timestamp_game_mean": points["pooled_trade_row"] - points["earliest_timestamp_game_mean"],
    }
    for name, point in contrast_points.items():
        low, high = pct_interval(contrasts[name])
        records.append({"band": band, "result_type": "paired_contrast", "name": name,
                        "estimate_pp": point * 100, "ci95_low_pp": low * 100,
                        "ci95_high_pp": high * 100, "band_cohort_rows": eligible_rows,
                        "rows_used_by_estimator": None,
                        "games": g, "bootstrap_draws": DRAWS,
                        "seed": SEED + (0 if band == "5_20c" else 1)})

    # Exact decomposition: pooled minus equal-game = Cov(n_g, A_g) / mean(n_g).
    covariance_term = np.mean((n - n.mean()) * (mean_a - mean_a.mean())) / n.mean()
    loo_equal = (mean_a.sum() - mean_a) / (g - 1)
    loo_pooled = (np.sum(n * mean_a) - n * mean_a) / (n.sum() - n)
    diagnostics = {
        "band": band,
        "eligible_trade_rows": int(eligible_rows),
        "panel_games": int(panel_games),
        "games_with_at_least_one_late5_trade": int(late5_games),
        "eligible_games": int(g),
        "share_of_late5_trade_games_with_band_trade": float(g / late5_games),
        "mean_eligible_trade_rows_per_game": float(n.mean()),
        "median_eligible_trade_rows_per_game": float(np.median(n)),
        "top_1_game_share_of_trade_rows": float(np.max(n) / n.sum()),
        "top_5_games_share_of_trade_rows": float(np.sort(n)[-5:].sum() / n.sum()),
        "top_10_games_share_of_trade_rows": float(np.sort(n)[-10:].sum() / n.sum()),
        "equal_game_minus_pooled_trade_row_pp": float((points["equal_game"] - points["pooled_trade_row"]) * 100),
        "equal_minus_pooled_covariance_identity_pp": float(-covariance_term * 100),
        "leave_one_game_out_equal_game_range_pp": [float(loo_equal.min() * 100), float(loo_equal.max() * 100)],
        "leave_one_game_out_pooled_trade_row_range_pp": [float(loo_pooled.min() * 100), float(loo_pooled.max() * 100)],
        "pearson_log_trade_rows_vs_game_gap": float(np.corrcoef(np.log(n), mean_a)[0, 1]),
        "pearson_log_trade_rows_vs_game_gap_ci95": list(map(float, pct_interval(correlation["pearson_log_trade_rows"]))),
        "spearman_log_trade_rows_vs_game_gap": float(pd.Series(np.log(n)).corr(pd.Series(mean_a), method="spearman")),
        "spearman_log_trade_rows_vs_game_gap_ci95": list(map(float, pct_interval(correlation["spearman_log_trade_rows"]))),
        "games_with_multiple_rows_at_earliest_timestamp": int((games["earliest_timestamp_rows"] > 1).sum()),
        "games_with_different_outcomes_across_earliest_timestamp_ties": int((games["earliest_timestamp_max"] - games["earliest_timestamp_min"] > 1e-12).sum()),
        "max_rows_tied_at_earliest_timestamp": int(games["earliest_timestamp_rows"].max()),
        "single_row_tie_break_point_bound_pp": [float(points["earliest_timestamp_single_row_min_bound"] * 100), float(points["earliest_timestamp_single_row_max_bound"] * 100)],
        "bootstrap_draws": DRAWS,
        "seed": SEED + (0 if band == "5_20c" else 1),
        "interpretation": "Descriptive, post hoc estimand audit; intervals are nominal and unadjusted across bands and estimands.",
    }
    game_export = games[["game_id", "trade_rows", "game_mean_price_minus_payoff",
                         "earliest_timestamp_rows", "earliest_timestamp_mean",
                         "earliest_timestamp_min", "earliest_timestamp_max"]].copy()
    game_export.insert(0, "band", band)
    return records, diagnostics, game_export


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to phase5_late_trades.parquet")
    parser.add_argument("--output-dir", required=True, help="Directory for summary and game-level CSVs")
    args = parser.parse_args()
    frame = pd.read_parquet(args.input, columns=["game_id", "trade_id", "ts", "late5", "longshot_price", "longshot_y"])
    frame = frame.loc[frame["late5"].astype(bool)].copy()
    frame["A"] = frame["longshot_price"] - frame["longshot_y"]
    panel_games = int(frame["game_id"].nunique())
    records: list[dict] = []
    diagnostics: dict[str, dict] = {}
    game_exports: list[pd.DataFrame] = []
    volume_deciles: list[pd.DataFrame] = []
    for lower, upper, label in BANDS:
        sample = frame.loc[frame["longshot_price"].between(lower, upper, inclusive="both")].copy()
        if sample.empty:
            raise ValueError(f"No observations for band {label}")
        sample["ts"] = pd.to_datetime(sample["ts"], utc=True, errors="coerce")
        earliest = sample.groupby("game_id", sort=True)["ts"].transform("min")
        first_time_rows = sample.loc[sample["ts"].eq(earliest)]
        first_summary = first_time_rows.groupby("game_id", sort=True).agg(
            earliest_timestamp_rows=("A", "size"),
            earliest_timestamp_mean=("A", "mean"),
            earliest_timestamp_min=("A", "min"),
            earliest_timestamp_max=("A", "max"),
        )
        game_summary = sample.groupby("game_id", sort=True).agg(
            trade_rows=("A", "size"),
            game_mean_price_minus_payoff=("A", "mean"),
        ).join(first_summary, how="inner").reset_index()
        game_summary["trade_row_decile"] = pd.qcut(
            game_summary["trade_rows"], 10, labels=False, duplicates="drop"
        ) + 1
        for decile, subset in game_summary.groupby("trade_row_decile", observed=True, sort=True):
            volume_deciles.append({
                "band": label,
                "trade_row_decile": int(decile),
                "games": int(len(subset)),
                "trade_rows_min": int(subset.trade_rows.min()),
                "trade_rows_median": float(subset.trade_rows.median()),
                "trade_rows_max": int(subset.trade_rows.max()),
                "equal_game_mean_price_minus_payoff_pp": float(subset.game_mean_price_minus_payoff.mean() * 100),
                "pooled_trade_row_price_minus_payoff_pp": float(np.average(
                    subset.game_mean_price_minus_payoff, weights=subset.trade_rows
                ) * 100),
            })
        band_records, band_diagnostics, game_export = bootstrap_band(
            game_summary, label, len(sample), panel_games, panel_games)
        records.extend(band_records)
        diagnostics[label] = band_diagnostics
        game_exports.append(game_export)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(output / "phase5_final5_estimand_contrasts.csv", index=False)
    pd.concat(game_exports, ignore_index=True).to_csv(output / "phase5_final5_game_diagnostics.csv", index=False)
    pd.DataFrame(volume_deciles).to_csv(output / "phase5_final5_trade_row_deciles.csv", index=False)
    (output / "phase5_final5_estimand_diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    print(json.dumps(diagnostics, indent=2))


if __name__ == "__main__":
    main()
