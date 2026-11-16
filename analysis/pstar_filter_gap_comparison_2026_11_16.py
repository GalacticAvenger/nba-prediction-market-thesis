"""Compare market-YES price-minus-payoff gaps before and after the P* screen.

The script uses the saved Phase 4 trade panel and the Phase 5 sample builder.
Pass --data-root when those files live outside this checkout. The JSON reports
pooled trade-weighted and equal-game estimates with game-bootstrap intervals.
""" 
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import phase5a
import phase5_selection_formula as selection
from game_windows import is_final_regulation_window


DRAWS = 2_000
SEEDS = {
    "retrospective_window_before_Pstar": 9_142_026,
    "retrospective_window_after_Pstar": 9_142_027,
    "final_five_regulation_minutes_before_Pstar": 9_142_028,
    "final_five_regulation_minutes_after_Pstar": 9_142_029,
}
PRICE_LOW, PRICE_HIGH = 0.05, 0.20
PSTAR_LOW, PSTAR_HIGH = 0.03, 0.97
OUTPUT = ROOT / "data/interim/phase5/pstar_filter_gap_comparison_2026_11_16.json"


def point_and_intervals(frame, seed: int) -> dict:
    """Bootstrap game clusters; recompute both weighting estimands per draw."""
    grouped = frame.groupby("game_id", sort=True).A.agg(["sum", "mean", "size"])
    sums = grouped["sum"].to_numpy(float)
    means = grouped["mean"].to_numpy(float)
    counts = grouped["size"].to_numpy(float)
    n_games = len(grouped)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, n_games, size=(DRAWS, n_games))
    pooled_boot = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
    equal_boot = means[indices].mean(axis=1)
    return {
        "trades": int(len(frame)),
        "games": int(n_games),
        "pooled_trade_weighted_A_pp": float(100 * sums.sum() / counts.sum()),
        "pooled_trade_weighted_CI95_pp": (100 * np.quantile(pooled_boot, [0.025, 0.975])).tolist(),
        "equal_game_weight_A_pp": float(100 * means.mean()),
        "equal_game_weight_CI95_pp": (100 * np.quantile(equal_boot, [0.025, 0.975])).tolist(),
        "bootstrap_seed": int(seed),
    }


def set_data_root(data_root: Path) -> None:
    """Point the existing Phase 5 builder at a checkout with its data files."""
    phase5a.META = data_root / "data/interim/kalshi_market_metadata.parquet"
    phase5a.PANEL = data_root / "data/interim/phase4/trade_panel"
    phase5a.PBP = data_root / "data/interim/espn_pbp/season=2026"
    phase5a.ASSIGN = data_root / "data/interim/phase4/selected_team_by_game.csv"
    phase5a.OUT = data_root / "data/interim/phase5"
    selection.ROOT = data_root
    selection.META = phase5a.META
    selection.PANEL = phase5a.PANEL


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=ROOT,
                        help="Repository root containing the saved Phase 4/ESPN panels")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    set_data_root(args.data_root.resolve())

    print("Building Phase 5 trade frame…", flush=True)
    _, base, _ = selection.build_phase5_frames()
    base = base.loc[base.price.between(PRICE_LOW, PRICE_HIGH, inclusive="both")].copy()
    base["A"] = base.price - base.y
    base["pstar_supported"] = base.pstar.between(PSTAR_LOW, PSTAR_HIGH, inclusive="both")
    base["retrospective"] = base.ts.ge(base.end_ts - __import__("pandas").Timedelta(minutes=10))
    base["final_five"] = [
        is_final_regulation_window(period, clock, 5)
        for period, clock in zip(base.period, base.clock_s_remaining)
    ]

    definitions = [
        ("retrospective_window_before_Pstar", "retrospective", False),
        ("retrospective_window_after_Pstar", "retrospective", True),
        ("final_five_regulation_minutes_before_Pstar", "final_five", False),
        ("final_five_regulation_minutes_after_Pstar", "final_five", True),
    ]
    samples = {}
    for name, window, apply_pstar in definitions:
        keep = base[window]
        if apply_pstar:
            keep = keep & base.pstar_supported
        selected = base.loc[keep].copy()
        samples[name] = point_and_intervals(selected, SEEDS[name])

    out = {
        "estimand": "A = market YES price minus realized market YES payoff",
        "units": "percentage points",
        "price_side": "market YES",
        "price_band": {"low": PRICE_LOW, "high": PRICE_HIGH, "inclusive": True},
        "Pstar_support": {"low": PSTAR_LOW, "high": PSTAR_HIGH, "inclusive": True},
        "bootstrap": {
            "unit": "game",
            "draws": DRAWS,
            "interval": "percentile 95% interval; resample games with replacement; recompute pooled trade-weighted and equal-game estimates in every draw",
        },
        "source": {
            "sample_construction_code": "src/phase5_selection_formula.py:build_phase5_frames",
            "window_and_support_application": "analysis/pstar_filter_gap_comparison_2026_11_16.py",
            "saved_input": "data/interim/phase4/trade_panel/*.parquet plus saved ESPN PBP and market metadata; block trades excluded upstream",
            "note": "Before-Pstar samples use the same market-YES 5–20 cent price band and window as after-Pstar samples. The after-Pstar samples additionally require P* in [0.03, 0.97].",
        },
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
