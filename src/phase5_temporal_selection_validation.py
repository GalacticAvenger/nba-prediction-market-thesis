"""Chronological holdout validation of the realized-end selection adjustment.

This post-hoc robustness check trains the selection model on the first 70% of
games in date order and evaluates it on the remaining games. It is not a new
confirmatory test and does not change the registered primary estimand.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from common import ROOT
from phase5_selection_formula import build_phase5_frames

OUT = ROOT / "data/interim/phase5"
SEED = 20261023
DRAWS = 2000
TRAIN_SHARE = 0.70
BANDS = {"05_20": (.05, .20)}
COORDINATES = ("price", "pstar")
BIN_WIDTHS = (.05, .10)


def bin_ids(x: np.ndarray, width: float) -> np.ndarray:
    return np.floor(np.asarray(x, dtype=float) / width).astype(int).clip(
        0, int(round(1 / width)) - 1)


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, coord: str,
                width: float, band: tuple[float, float]) -> dict:
    """Fit q, pi0, pi1 on earlier games; predict selected test outcomes."""
    support = ("price", "pstar", coord)
    def keep(x: pd.DataFrame) -> pd.DataFrame:
        mask = x.price.between(*band)
        for col in set(support):
            mask &= x[col].between(.03, .97)
        return x.loc[mask].copy()

    tr, te = keep(train), keep(test)
    nb = int(round(1 / width))
    tr["bin"] = bin_ids(tr[coord].to_numpy(), width)
    te["bin"] = bin_ids(te[coord].to_numpy(), width)
    tr["feature"] = tr.bin * 4 + tr.y.astype(int) * 2 + tr.is_d.astype(int)
    games = pd.Index(tr.game_id.unique())
    gi = games.get_indexer(tr.game_id)
    counts = np.zeros((len(games), nb * 4), dtype=float)
    np.add.at(counts, (gi, tr.feature.to_numpy(int)), 1)

    target = te.loc[te.is_d.astype(bool)].copy()
    if target.empty:
        return {"error": "empty chronological test target"}
    tg = pd.Index(target.game_id.unique())
    tgi = tg.get_indexer(target.game_id)
    target["feature_bin"] = target.bin
    tn = np.zeros((len(tg), nb), dtype=float)
    ty = np.zeros_like(tn)
    tp = np.zeros_like(tn)
    np.add.at(tn, (tgi, target.bin.to_numpy(int)), 1)
    np.add.at(ty, (tgi, target.bin.to_numpy(int)), target.y.to_numpy(float))
    np.add.at(tp, (tgi, target.bin.to_numpy(int)), target[coord].to_numpy(float))

    def probabilities(c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        c = c.reshape(nb, 2, 2)
        b0 = c[:, 0, :].sum(axis=1)
        b1 = c[:, 1, :].sum(axis=1)
        pi0 = (c[:, 0, 1] + .5) / (b0 + 1)
        pi1 = (c[:, 1, 1] + .5) / (b1 + 1)
        q = (b1 + .5) / (b0 + b1 + 1)
        den = q * pi1 + (1 - q) * pi0
        qd = np.divide(q * pi1, den, out=np.full(nb, np.nan), where=den > 0)
        return q, qd

    q, qd = probabilities(counts.sum(axis=0))
    n_target = tn.sum()
    point = {
        "observed_gap": float((ty.sum() - tp.sum()) / n_target),
        "baseline_gap": float((tn.sum(axis=0) @ q - tp.sum()) / n_target),
        "selection_predicted_gap": float((tn.sum(axis=0) @ qd - tp.sum()) / n_target),
        "remainder": float((ty.sum() - tn.sum(axis=0) @ qd) / n_target),
        "trades": int(n_target), "games": int(len(tg)),
        "training_games": int(len(games)),
    }

    rng = np.random.default_rng(SEED + (0 if coord == "price" else 1) + int(width * 1000))
    wt_train = rng.multinomial(len(games), np.full(len(games), 1 / len(games)), size=DRAWS)
    wt_test = rng.multinomial(len(tg), np.full(len(tg), 1 / len(tg)), size=DRAWS)
    train_counts = wt_train @ counts
    target_n = wt_test @ tn
    target_y = wt_test @ ty
    target_p = wt_test @ tp
    boot = {k: np.full(DRAWS, np.nan) for k in point if k in
            ("observed_gap", "baseline_gap", "selection_predicted_gap", "remainder")}
    for i in range(DRAWS):
        qb, qdb = probabilities(train_counts[i])
        den = target_n[i].sum()
        if den <= 0 or not np.isfinite(qdb).all():
            continue
        boot["observed_gap"][i] = (target_y[i].sum() - target_p[i].sum()) / den
        boot["baseline_gap"][i] = (target_n[i] @ qb - target_p[i].sum()) / den
        boot["selection_predicted_gap"][i] = (target_n[i] @ qdb - target_p[i].sum()) / den
        boot["remainder"][i] = (target_y[i].sum() - target_n[i] @ qdb) / den
    point["ci95"] = {k: np.nanquantile(v, [.025, .975]).tolist() for k, v in boot.items()}
    point["successful_bootstrap_draws"] = min(int(np.isfinite(v).sum()) for v in boot.values())
    point["interval"] = "two-way game bootstrap: refit on resampled training games and resample held-out games"
    return point


def main() -> None:
    _frames, base, _weak = build_phase5_frames()
    base = base.loc[base.period.ge(4)].copy()
    game_dates = base.groupby("game_id").end_ts.min().sort_values()
    cutoff_i = int(np.floor(len(game_dates) * TRAIN_SHARE))
    cutoff = game_dates.iloc[cutoff_i]
    train_ids = set(game_dates.index[:cutoff_i])
    test_ids = set(game_dates.index[cutoff_i:])
    train = base.loc[base.game_id.isin(train_ids)].copy()
    test = base.loc[base.game_id.isin(test_ids)].copy()

    rows = {}
    for band_name, band in BANDS.items():
        for coord in COORDINATES:
            for width in BIN_WIDTHS:
                key = f"{band_name}_{coord}_{width:.2f}"
                rows[key] = fit_predict(train, test, coord, width, band)
    result = {
        "estimand": "post-hoc chronological holdout validation of the retrospective-window selection adjustment",
        "split": "first 70% of distinct Q4/OT game end timestamps for training; final 30% held out",
        "cutoff_utc": cutoff.isoformat(),
        "training_games": int(len(train_ids)), "test_games_before_filters": int(len(test_ids)),
        "training_end_range_utc": [game_dates.iloc[0].isoformat(), game_dates.iloc[cutoff_i - 1].isoformat()],
        "test_end_range_utc": [game_dates.iloc[cutoff_i].isoformat(), game_dates.iloc[-1].isoformat()],
        "market_price_bands": {k: list(v) for k, v in BANDS.items()},
        "coordinates": rows,
        "interpretation_limit": "This is a post-hoc same-season transportability check, not an independent-season replication or causal estimate. The registered game-clock primary remains unchanged.",
    }
    out = OUT / "phase5_temporal_selection_validation.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
