"""Weak-alignment exclusion and leave-one-game-out checks for the primary estimate."""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from common import ROOT

OUT = ROOT / "data/interim/phase5"
PRIMARY = OUT / "phase5_primary_trades.parquet"
FLAGS = ROOT / "data/interim/phase2/alignment_game_flags.csv"
SEED = 20261022
DRAWS = 10_000


def summarize(z: pd.DataFrame, label: str, rng: np.random.Generator) -> dict:
    game_gap = z.groupby("game_id", sort=False).gap_longshot.mean()
    # Registered A is price minus realized outcome; gap_longshot is Y minus price.
    game_a = -game_gap.to_numpy(float)
    boot = game_a[rng.integers(0, len(game_a), size=(DRAWS, len(game_a)))].mean(axis=1)
    return {
        "sample": label, "trades": int(len(z)), "games": int(len(game_a)),
        "weak_alignment_games": int(z.groupby("game_id").weak_alignment.first().sum()),
        "A_price_minus_realized_outcome": float(game_a.mean()),
        "bootstrap_ci95": np.quantile(boot, [.025, .975]).tolist(),
        "bootstrap_draws": DRAWS,
    }


def main() -> None:
    d = pd.read_parquet(PRIMARY)
    flags = pd.read_csv(FLAGS, dtype={"game_id": str})
    weak = set(flags.loc[
        flags.weak_alignment_gt5_backward_steps.fillna(False).astype(bool), "game_id"
    ].astype(str))
    d["game_id"] = d.game_id.astype(str)
    d["weak_alignment"] = d.game_id.isin(weak)
    rng = np.random.default_rng(SEED)
    samples = [summarize(d, "all_registered_primary_games", rng),
               summarize(d.loc[~d.weak_alignment], "exclude_weak_alignment_games", rng)]
    game_gap = d.groupby("game_id", sort=False).gap_longshot.mean()
    loo = np.array([-game_gap.drop(g).mean() for g in game_gap.index], dtype=float)
    influence = {
        "n_leave_one_game_out_estimates": int(len(loo)),
        "minimum_A": float(loo.min()), "minimum_omitted_game_id": str(game_gap.index[loo.argmin()]),
        "maximum_A": float(loo.max()), "maximum_omitted_game_id": str(game_gap.index[loo.argmax()]),
        "positive_estimate_count": int((loo > 0).sum()),
    }
    result = {
        "estimand": "equal-game average of trade-level longshot price minus realized outcome",
        "weak_flag_definition": "more than five backward ESPN wall-clock steps in the game",
        "samples": samples, "leave_one_game_out": influence,
        "limitations": [
            "This exclusion checks sensitivity to the existing weak-alignment flag; it does not estimate or resolve a common absolute timestamp lag.",
            "Bootstrap resamples games and is a precision diagnostic, not a new registered test.",
        ],
    }
    (OUT / "phase5_primary_influence_diagnostic.json").write_text(json.dumps(result, indent=2) + "\n")
    rows = []
    for row in samples:
        rows.append({k: v for k, v in row.items() if k != "bootstrap_ci95"} |
                    {"ci95_low": row["bootstrap_ci95"][0], "ci95_high": row["bootstrap_ci95"][1]})
    pd.DataFrame(rows).to_csv(OUT / "phase5_primary_influence_diagnostic.csv", index=False)
    (OUT / "phase5_primary_influence_diagnostic_loo.json").write_text(json.dumps(influence, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
