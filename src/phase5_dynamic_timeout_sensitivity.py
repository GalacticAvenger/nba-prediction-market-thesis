"""Post-hoc sensitivity for timeout eligibility before a later foul/free throw.

Run from this repository's root when the original project data are in the
parent directory:
    python src/phase5_dynamic_timeout_sensitivity.py \
        --root .. \
        --output TIMING_SENSITIVITY.json

Requires the existing Phase 2 PBP/timeout cache and Phase 5 late-trade cache.
This is an exploratory timing sensitivity, a sensitivity analysis for the
project-designated outcome estimate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _epoch(series: pd.Series) -> np.ndarray:
    return pd.to_datetime(series, utc=True, errors="coerce", format="mixed").astype("int64").to_numpy() / 1e9


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draws", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=681103)
    args = parser.parse_args()
    root = args.root
    interim = root / "data/interim"

    # The Phase 5 cache contains all trades in the late-five window, not only
    # trades that pass Phase 4's quiet-stoppage flag.
    trades = pd.read_parquet(
        interim / "phase5/phase5_late_trades.parquet",
        columns=["game_id", "ts", "late5", "quiet_timeout", "longshot_price", "longshot_y"],
    )
    trades = trades.loc[
        trades.late5 & trades.longshot_price.between(.05, .20, inclusive="both")
    ].copy().reset_index(drop=True)
    trades["game_id"] = trades.game_id.astype(str)
    trades["ts_s"] = _epoch(trades.ts)

    # Match Phase 4's market-game universe and its existing Phase 2 interval
    # screens. The Phase 2 screen itself remains retrospective.
    matched_games = set(
        pd.read_csv(interim / "phase4/selected_team_by_game.csv").game_id.astype(str)
    )
    intervals = pd.read_csv(interim / "phase2/timeout_intervals.csv")
    intervals = intervals.loc[
        intervals.survives_selected_buffer.fillna(False).astype(bool)
        & intervals.game_id.astype(str).isin(matched_games)
    ].copy()
    intervals["game_id"] = intervals.game_id.astype(str)
    intervals["start_s"] = _epoch(intervals.onset_wall)
    intervals["restart_s"] = _epoch(intervals.restart_wall_est)
    intervals["end_s"] = (
        intervals.restart_s
        - intervals.quiet_window_end_buffer_selected.fillna(5).to_numpy(float)
    )

    pbp = pd.read_parquet(
        interim / "phase2/pbp_derived_regular.parquet",
        columns=["game_id", "ts_wall_utc", "action_type"],
    )
    pbp["game_id"] = pbp.game_id.astype(str)
    pbp["ts_s"] = _epoch(pbp.ts_wall_utc)
    kinds = pbp.action_type.fillna("").str.lower()
    event_rows = pbp.loc[
        kinds.str.contains("foul|free throw", regex=True), ["game_id", "ts_s"]
    ].dropna().sort_values(["game_id", "ts_s"])
    event_times = {
        game_id: block.ts_s.to_numpy(float)
        for game_id, block in event_rows.groupby("game_id", sort=False)
    }

    first_event = np.full(len(intervals), np.nan)
    for pos, row in enumerate(intervals.itertuples(index=False)):
        values = event_times.get(row.game_id)
        if values is None:
            continue
        j = np.searchsorted(values, row.start_s, side="left")
        if j < len(values) and values[j] <= row.end_s:
            first_event[pos] = values[j]
    intervals["first_foul_ft_s"] = first_event
    # End at the first future foul/FT if it occurs before the existing buffer
    # endpoint; otherwise keep the original buffered endpoint.
    intervals["dynamic_end_s"] = np.where(
        np.isfinite(first_event),
        np.minimum(intervals.end_s.to_numpy(float), np.nextafter(first_event, -np.inf)),
        intervals.end_s.to_numpy(float),
    )
    by_game = {
        game_id: block.sort_values("start_s")[["start_s", "dynamic_end_s"]].to_numpy(float)
        for game_id, block in intervals.groupby("game_id", sort=False)
    }
    dynamic_timeout = np.zeros(len(trades), dtype=bool)
    for game_id, positions in trades.groupby("game_id", sort=False).groups.items():
        candidates = by_game.get(game_id)
        if candidates is None or not len(candidates):
            continue
        positions = np.asarray(list(positions), dtype=int)
        times = trades.loc[positions, "ts_s"].to_numpy(float)
        j = np.searchsorted(candidates[:, 0], times, side="right") - 1
        valid = j >= 0
        dynamic_timeout[positions[valid]] = times[valid] <= candidates[j[valid], 1]

    # Preserve the original Phase 4 quiet flag, including clean timeouts and
    # event-free quarter breaks, and add pre-event trades in flagged timeouts.
    existing = trades.quiet_timeout.fillna(False).to_numpy(bool)
    expanded = existing | dynamic_timeout
    added = dynamic_timeout & ~existing

    def summary(mask: np.ndarray) -> dict[str, object]:
        sample = trades.loc[mask, ["game_id", "longshot_price", "longshot_y"]].copy()
        sample["gap"] = sample.longshot_price - sample.longshot_y
        game_means = sample.groupby("game_id", sort=False).gap.mean().to_numpy(float)
        rng = np.random.default_rng(args.seed)
        draws = rng.integers(0, len(game_means), size=(args.draws, len(game_means)))
        bootstrap = game_means[draws].mean(axis=1)
        return {
            "trades": int(len(sample)),
            "games": int(len(game_means)),
            "equal_game_price_minus_payoff": float(game_means.mean()),
            "game_bootstrap_95_ci": [float(x) for x in np.quantile(bootstrap, [.025, .975])],
        }

    result = {
        "status": "post-hoc sensitivity to timeout eligibility; exact project-designated outcome-estimator/filter chronology is unverified",
        "definition": (
            "Preserves the existing Phase 2 interval exclusions and five-second restart buffer. "
            "For intervals containing a later foul/free-throw before the buffered endpoint, "
            "adds trades strictly before the first such PBP event. Existing eligible quiet "
            "timeout and quarter-break trades remain included."
        ),
        "inference": {"draws": args.draws, "seed": args.seed, "unit": "game-cluster bootstrap"},
        "candidate_timeout_intervals_in_matched_games": int(len(intervals)),
        "intervals_with_foul_or_free_throw_before_buffered_endpoint": int(np.isfinite(first_event).sum()),
        "current_primary_rule": summary(existing),
        "dynamic_cutoff_sensitivity": summary(expanded),
        "added_pre_event_trades": int(added.sum()),
        "games_with_added_pre_event_trades": int(trades.loc[added, "game_id"].nunique()),
        "limitations": [
            "The sensitivity retains Phase 2 interval-level exclusions and the five-second restart buffer, both of which use later event or restart information.",
            "ESPN wall-clock timestamps have one-second resolution and their common absolute lag relative to market timestamps is unknown.",
            "This is a post-hoc timing sensitivity, not a fully trade-time-identifiable estimate.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
