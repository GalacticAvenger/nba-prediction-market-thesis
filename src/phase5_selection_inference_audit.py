"""Weighting and fixed-prediction cluster-bootstrap audit of cross-fit output.

Reads the game-level OOF predictions already written by the cross-fit analysis.
Intervals condition on those predictions; they do not refit the selection model.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from common import ROOT

INPUTS = {
    "kalshi": ROOT / "data/interim/phase5/phase5_crossfit_selection_diagnostic_games.csv",
    "polymarket": ROOT / "data/interim/phase2/polymarket_crossfit_selection_diagnostic_games.csv",
}
OUTPUT = ROOT / "data/interim/phase5/phase5_selection_inference_audit.json"
DRAWS = 20000
SEED = 334455
FILTERS = {"price_band": "05_20", "window_minutes": 10,
           "coordinate": "price", "bin_width": .05}
FIELDS = ("observed_gap", "base_gap", "predicted_gap", "remainder")


def summarize(values: np.ndarray, draws: np.ndarray) -> dict:
    return {"estimate": float(values.mean()),
            "ci95_fixed_prediction_game_bootstrap": np.quantile(draws, [.025, .975]).tolist()}


def audit(input_path, venue: str) -> dict:
    d = pd.read_csv(input_path)
    for col, value in FILTERS.items():
        d = d.loc[np.isclose(d[col], value) if isinstance(value, float) else d[col].eq(value)]
    n = len(d)
    rng = np.random.default_rng(SEED)
    ids = rng.integers(0, n, size=(DRAWS, n))
    out = {"estimand": "fixed-prediction game-level OOF residual and gap summaries",
           "venue": venue,
           "source": input_path.relative_to(ROOT).as_posix(),
           "filters": FILTERS, "games": n, "trades": int(d.trades.sum()),
           "bootstrap": {"cluster": "game", "draws": DRAWS, "seed": SEED,
                         "limitation": "Conditions on cross-fitted predictions; does not refit training folds. This differs from the original refit bootstrap and should be read as an inference sensitivity, not a replacement primary interval."}}
    for field in FIELDS:
        v = d[field].to_numpy(float)
        equal_draws = v[ids].mean(axis=1)
        trade_draws = ((v * d.trades.to_numpy(float))[ids].sum(axis=1) /
                       d.trades.to_numpy(float)[ids].sum(axis=1))
        out[field] = {
            "equal_game": {"estimate": float(v.mean()),
                           "ci95_fixed_prediction_game_bootstrap": np.quantile(equal_draws, [.025, .975]).tolist()},
            "trade_weighted": {"estimate": float(np.average(v, weights=d.trades)),
                               "ci95_fixed_prediction_game_bootstrap": np.quantile(trade_draws, [.025, .975]).tolist()},
        }
    remainder_contrib = d.remainder.to_numpy(float) * d.trades.to_numpy(float) / d.trades.sum()
    top = int(np.argmax(np.abs(remainder_contrib)))
    loo = ((remainder_contrib.sum() - remainder_contrib) /
           (1 - d.trades.to_numpy(float) / d.trades.sum()))
    out["influence_sensitivity"] = {
        "largest_absolute_weighted_remainder_contribution_game": str(d.iloc[top].game_id),
        "game_trade_share": float(d.iloc[top].trades / d.trades.sum()),
        "game_level_remainder": float(d.iloc[top].remainder),
        "weighted_remainder_contribution": float(remainder_contrib[top]),
        "leave_one_game_out_trade_weighted_remainder_range": [float(loo.min()), float(loo.max())],
        "note": "Leave-one-game-out calculation holds all fitted cross-fit predictions fixed; it diagnoses target-sample concentration, not refitted model influence."
    }
    return out


def main() -> None:
    out = {venue: audit(path, venue) for venue, path in INPUTS.items()}
    OUTPUT.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
