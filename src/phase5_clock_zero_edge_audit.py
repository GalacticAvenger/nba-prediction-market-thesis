"""Quantify sensitivity to Q4 0:00 trades after the final recorded Q4 play.

This is a diagnostic, not an asserted correction: timestamps do not establish
whether play had ended. It uses the Phase 5 late-trade cache and derived ESPN
play-by-play timestamps, and reports the main equal-game/pooled contrast with
and without the flagged rows.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

BANDS = ((0.05, 0.20, "5_20c", 6_102_126), (0.10, 0.40, "10_40c", 6_102_127))
DRAWS = 10_000


def interval(draws: np.ndarray) -> tuple[float, float]:
    return tuple(np.quantile(draws, [0.025, 0.975]).astype(float))


def summarize(rows: pd.DataFrame, band: str, excluded: bool) -> dict:
    game = rows.groupby("game_id", sort=True).agg(
        mean_a=("A", "mean"), rows=("A", "size")
    )
    mean_a = game.mean_a.to_numpy(float)
    n = game.rows.to_numpy(float)
    equal = mean_a.mean()
    pooled = np.average(mean_a, weights=n)
    rng = np.random.default_rng(dict((b, s) for _, _, b, s in BANDS)[band])
    draws = np.empty(DRAWS)
    for start in range(0, DRAWS, 500):
        stop = min(start + 500, DRAWS)
        idx = rng.integers(0, len(game), size=(stop - start, len(game)))
        nn, mm = n[idx], mean_a[idx]
        draws[start:stop] = mm.mean(axis=1) - (mm * nn).sum(axis=1) / nn.sum(axis=1)
    lo, hi = interval(draws)
    return {
        "band": band,
        "rows_excluded": bool(excluded),
        "trade_rows": int(len(rows)),
        "games": int(len(game)),
        "game_equal_pp": float(equal * 100),
        "pooled_trade_row_pp": float(pooled * 100),
        "equal_minus_pooled_pp": float((equal - pooled) * 100),
        "contrast_ci95_low_pp": float(lo * 100),
        "contrast_ci95_high_pp": float(hi * 100),
        "bootstrap_draws": DRAWS,
        "seed": dict((b, s) for _, _, b, s in BANDS)[band],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", required=True, help="Path to phase5_late_trades.parquet")
    parser.add_argument("--pbp", required=True, help="Path to pbp_derived_regular.parquet")
    parser.add_argument("--output", required=True, help="Output CSV path")
    args = parser.parse_args()

    trades = pd.read_parquet(args.trades, columns=[
        "game_id", "ts", "late5", "period", "clock_s_remaining",
        "longshot_price", "longshot_y",
    ])
    trades = trades.loc[trades.late5.astype(bool)].copy()
    trades["ts"] = pd.to_datetime(trades.ts, utc=True, errors="coerce")
    trades["A"] = trades.longshot_price - trades.longshot_y

    pbp = pd.read_parquet(args.pbp, columns=["game_id", "period", "ts_wall_utc"])
    pbp = pbp.loc[pbp.period.eq(4)].copy()
    pbp["ts_wall_utc"] = pd.to_datetime(pbp.ts_wall_utc, utc=True, errors="coerce")
    last_q4_play = pbp.dropna(subset=["ts_wall_utc"]).groupby("game_id").ts_wall_utc.max()
    trades["last_q4_play_ts"] = trades.game_id.map(last_q4_play)
    trades["clock_zero_after_last_q4_play"] = (
        trades.period.eq(4)
        & trades.clock_s_remaining.eq(0)
        & trades.last_q4_play_ts.notna()
        & trades.ts.gt(trades.last_q4_play_ts)
    )

    results: list[dict] = []
    for lower, upper, band, _ in BANDS:
        cohort = trades.loc[trades.longshot_price.between(lower, upper, inclusive="both")]
        edge = cohort.loc[cohort.clock_zero_after_last_q4_play]
        for trimmed, sample in ((False, cohort), (True, cohort.loc[~cohort.clock_zero_after_last_q4_play])):
            result = summarize(sample, band, trimmed)
            result["flagged_rows_in_full_cohort"] = int(len(edge))
            result["flagged_games_in_full_cohort"] = int(edge.game_id.nunique())
            results.append(result)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(output, index=False)
    print(pd.DataFrame(results).to_string(index=False))


if __name__ == "__main__":
    main()
