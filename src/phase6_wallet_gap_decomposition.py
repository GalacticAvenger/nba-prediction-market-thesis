"""Accounting decomposition of selected 2025-26 Polymarket buy gaps by profile.

This is a descriptive allocation of the selected trade-price gap across
time-indexed wallet behavior profiles. It is not a causal counterfactual.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/interim/phase6/prior_game_behavior/target_buys_with_prior_game_profiles.parquet"
OUT = ROOT / "data/interim/phase6/prior_game_behavior/gap_decomposition"
PROFILE_COLUMN = "prior_behavior_profile"
N_BOOT = 2000
SEED = 20261023
PROFILE_ORDER = [
    "limited_prior_history", "high_prior_activity", "established_mixed",
    "maker_record_dominant", "taker_record_dominant",
]
WEIGHTS = {"trade_count": "_unit_weight", "shares": "size", "usd_notional": "notional"}
GAPS = {
    "price_minus_outcome": "price_minus_y",
    "price_minus_Pstar": "price_minus_pstar",
    "outcome_minus_Pstar": "y_minus_pstar",
}


def load_data() -> pd.DataFrame:
    q = pd.read_parquet(INPUT)
    required = {"wallet", "game_id", "price", "y_own", "pstar_own", "size",
                PROFILE_COLUMN}
    missing = required.difference(q.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    q = q.dropna(subset=list(required)).copy()
    q["wallet"] = q.wallet.astype(str).str.lower()
    q["game_id"] = q.game_id.astype(str)
    q[PROFILE_COLUMN] = q[PROFILE_COLUMN].astype(str)
    q["notional"] = q["size"] * q["price"]
    q["_unit_weight"] = 1.0
    q["price_minus_y"] = q.price - q.y_own
    q["price_minus_pstar"] = q.price - q.pstar_own
    q["y_minus_pstar"] = q.y_own - q.pstar_own
    q = q.loc[q[PROFILE_COLUMN].isin(PROFILE_ORDER)].copy()
    if q.empty or q[[*WEIGHTS.values(), *GAPS.values()]].isna().any().any():
        raise ValueError("No usable observations or missing weights/outcomes")
    if (q[list(WEIGHTS.values())] < 0).any().any():
        raise ValueError("Weight variables must be nonnegative")
    return q


def point_decomposition(q: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    overall_rows: list[dict] = []
    for weight_name, weight_col in WEIGHTS.items():
        for gap_name, gap_col in GAPS.items():
            z = q.copy()
            z["weighted_gap"] = z[weight_col] * z[gap_col]
            profile_totals = z.groupby(PROFILE_COLUMN, observed=True).agg(
                records=(gap_col, "size"), wallets=("wallet", "nunique"),
                games=("game_id", "nunique"), weight=(weight_col, "sum"),
                numerator=("weighted_gap", "sum"),
            )
            all_weight = float(z[weight_col].sum())
            pooled_total = float(z.weighted_gap.sum() / all_weight)
            gp = z.groupby(["game_id", PROFILE_COLUMN], observed=True).agg(
                weight=(weight_col, "sum"), numerator=("weighted_gap", "sum"))
            gden = z.groupby("game_id", observed=True)[weight_col].sum()
            equal_total = float((z.groupby("game_id", observed=True).weighted_gap.sum() / gden).mean())
            overall_rows.extend([
                {"weighting": weight_name, "gap": gap_name, "estimator": "pooled",
                 "gap_pp": pooled_total * 100, "games": int(q.game_id.nunique()),
                 "records": int(len(q)), "total_weight": all_weight},
                {"weighting": weight_name, "gap": gap_name, "estimator": "equal_game",
                 "gap_pp": equal_total * 100, "games": int(q.game_id.nunique()),
                 "records": int(len(q)), "total_weight": all_weight},
            ])

            # For pooled rows, each group's weighted numerator divided by the
            # full sample's weight is its additive contribution. For equal-game
            # rows, decompose separately within each game, then average games.
            game_profile_numerators = gp.numerator.unstack(
                PROFILE_COLUMN).reindex(
                    index=gden.index, columns=PROFILE_ORDER, fill_value=0.0).fillna(0.0)
            comp_eq = game_profile_numerators.div(gden, axis=0).mean()
            for profile in PROFILE_ORDER:
                t = profile_totals.loc[profile] if profile in profile_totals.index else None
                group_gap = (float(t.numerator / t.weight) if t is not None and t.weight else np.nan)
                pooled_comp = (float(t.numerator / all_weight) if t is not None else 0.0)
                eq_comp = float(comp_eq.get(profile, 0.0))
                active_games = int(gp.loc[(slice(None), profile), :].shape[0]) if profile in gp.index.get_level_values(1) else 0
                game_equal_group_gap = np.nan
                if active_games:
                    subset = gp.xs(profile, level=PROFILE_COLUMN)
                    game_equal_group_gap = float((subset.numerator / subset.weight).mean())
                rows.extend([
                    {"weighting": weight_name, "gap": gap_name, "estimator": "pooled",
                     "profile": profile, "records": int(t.records) if t is not None else 0,
                     "wallets": int(t.wallets) if t is not None else 0,
                     "games_with_profile": int(t.games) if t is not None else 0,
                     "global_weight_share": float(t.weight / all_weight) if t is not None else 0.0,
                     "profile_gap_pp": group_gap * 100,
                     "additive_contribution_pp": pooled_comp * 100,
                     "share_of_total_gap_pct": pooled_comp / pooled_total * 100 if abs(pooled_total) > 1e-12 else np.nan},
                    {"weighting": weight_name, "gap": gap_name, "estimator": "equal_game",
                     "profile": profile, "records": int(t.records) if t is not None else 0,
                     "wallets": int(t.wallets) if t is not None else 0,
                     "games_with_profile": int(t.games) if t is not None else 0,
                     "global_weight_share": float(t.weight / all_weight) if t is not None else 0.0,
                     "profile_gap_pp": game_equal_group_gap * 100,
                     "additive_contribution_pp": eq_comp * 100,
                     "share_of_total_gap_pct": eq_comp / equal_total * 100 if abs(equal_total) > 1e-12 else np.nan},
                ])
    return pd.DataFrame(rows), pd.DataFrame(overall_rows)


def two_way_bootstrap(q: pd.DataFrame) -> pd.DataFrame:
    """Pigeonhole bootstrap by game and wallet; multiplicities multiply."""
    rng = np.random.default_rng(SEED)
    games, gi = np.unique(q.game_id.to_numpy(), return_inverse=True)
    wallets, wi = np.unique(q.wallet.to_numpy(), return_inverse=True)
    profiles = np.array(PROFILE_ORDER)
    pi = pd.Categorical(q[PROFILE_COLUMN], categories=profiles).codes
    if (pi < 0).any():
        raise ValueError("Unexpected profile label")
    gcount, wcount = len(games), len(wallets)
    game_profile_code = gi * len(profiles) + pi
    base_weights = {name: q[col].to_numpy(float) for name, col in WEIGHTS.items()}
    gaps = {name: q[col].to_numpy(float) for name, col in GAPS.items()}
    draws: dict[tuple[str, str, str], list[np.ndarray]] = {
        (w, gap, est): [] for w in WEIGHTS for gap in GAPS
        for est in ("pooled", "equal_game")}

    for _ in range(N_BOOT):
        gm = np.bincount(rng.integers(0, gcount, size=gcount), minlength=gcount)
        wm = np.bincount(rng.integers(0, wcount, size=wcount), minlength=wcount)
        mult = gm[gi] * wm[wi]
        if not mult.any():
            continue
        for weight_name, basew in base_weights.items():
            roww = mult * basew
            denom_game = np.bincount(gi, weights=roww, minlength=gcount)
            denom_total = float(denom_game.sum())
            if denom_total <= 0:
                continue
            for gap_name, gap in gaps.items():
                numer_gp = np.bincount(game_profile_code, weights=roww * gap,
                                       minlength=gcount * len(profiles)).reshape(gcount, len(profiles))
                pooled = numer_gp.sum(axis=0) / denom_total
                valid = (gm > 0) & (denom_game > 0)
                per_game_comp = np.zeros((gcount, len(profiles)), dtype=float)
                per_game_comp[valid] = numer_gp[valid] / denom_game[valid, None]
                equal = np.average(per_game_comp[valid], axis=0, weights=gm[valid])
                draws[(weight_name, gap_name, "pooled")].append(pooled)
                draws[(weight_name, gap_name, "equal_game")].append(equal)

    rows = []
    for (weighting, gap, estimator), samples in draws.items():
        a = np.asarray(samples) * 100
        if len(a) < N_BOOT * 0.95:
            raise RuntimeError(f"Too many invalid bootstrap replicates: {(weighting, gap, estimator)} n={len(a)}")
        for j, profile in enumerate(PROFILE_ORDER):
            rows.append({"weighting": weighting, "gap": gap, "estimator": estimator,
                         "profile": profile, "bootstrap_draws": int(len(a)),
                         "ci95_low_pp": float(np.quantile(a[:, j], .025)),
                         "ci95_high_pp": float(np.quantile(a[:, j], .975)),
                         "bootstrap_method": "two-way pigeonhole resampling of games and wallets; row multiplicity is their product",
                         "seed": SEED})
        total = a.sum(axis=1)
        rows.append({"weighting": weighting, "gap": gap, "estimator": estimator,
                     "profile": "ALL_PROFILES_TOTAL", "bootstrap_draws": int(len(a)),
                     "ci95_low_pp": float(np.quantile(total, .025)),
                     "ci95_high_pp": float(np.quantile(total, .975)),
                     "bootstrap_method": "two-way pigeonhole resampling of games and wallets; row multiplicity is their product",
                     "seed": SEED})
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    q = load_data()
    decomposition, overall = point_decomposition(q)
    bootstrap = two_way_bootstrap(q)
    result = decomposition.merge(bootstrap, on=["weighting", "gap", "estimator", "profile"],
                                 how="left", validate="one_to_one")
    result.to_csv(OUT / "profile_gap_contributions.csv", index=False)
    total_boot = bootstrap.loc[bootstrap.profile.eq("ALL_PROFILES_TOTAL"),
                               ["weighting", "gap", "estimator", "ci95_low_pp",
                                "ci95_high_pp", "bootstrap_draws", "bootstrap_method", "seed"]]
    overall = overall.merge(total_boot, on=["weighting", "gap", "estimator"],
                            how="left", validate="one_to_one")
    overall.to_csv(OUT / "overall_gaps.csv", index=False)
    bootstrap.to_csv(OUT / "bootstrap_intervals.csv", index=False)

    summary = {
        "data_file": str(INPUT.relative_to(ROOT)),
        "profile_column": PROFILE_COLUMN,
        "sample": {
            "rows": int(len(q)), "wallets": int(q.wallet.nunique()),
            "games": int(q.game_id.nunique()),
            "definition": "time-indexed prior-game profile BUY records in final five regulation minutes, 5-20 cent own-token price, and own-token P* below 50 percent",
        },
        "profile_definitions": ({
            "limited_prior_history": "under 20 prior NBA-market participant records or under 3 prior NBA games",
            "high_prior_activity": "at least 20 prior records per prior active UTC day, after adequate history",
            "maker_record_dominant": "at least 75 percent prior maker-role records, after high activity rule",
            "taker_record_dominant": "at most 25 percent prior maker-role records, after high activity rule",
            "established_mixed": "other adequately observed accounts",
        } if PROFILE_COLUMN == "prior_behavior_profile" else {
            "limited_prior_history": "fewer than 20 prior distinct wallet-transaction events or fewer than 3 prior NBA games",
            "rapid_cycle_proxy": "at least 20 prior transactions per active day and median within-day gap no more than 30 seconds",
            "large_ticket_low_frequency_proxy": "median prior transaction notional at least $100 and no more than 5 prior transactions per active day, after rapid-cycle rule",
            "other_observed_style": "other adequately observed transaction styles",
        }),
        "weights": {
            "trade_count": "one per participant-side buy record",
            "shares": "token shares purchased",
            "usd_notional": "shares multiplied by execution price",
        },
        "gap_definitions": {
            "price_minus_outcome": "execution price minus realized token payoff; positive is realized overpayment",
            "price_minus_Pstar": "execution price minus estimated market-free benchmark",
            "outcome_minus_Pstar": "realized token payoff minus estimated benchmark",
        },
        "estimators": {
            "pooled": "aggregate weighted numerator divided by aggregate weight; additive profile contributions sum to total",
            "equal_game": "within-game additive contributions averaged equally across games; profile contributions sum to total",
        },
        "bootstrap": {
            "replicates": N_BOOT, "seed": SEED,
            "method": "two-way pigeonhole bootstrap over games and wallets with multiplicative cluster weights; percentile 95 percent intervals",
        },
        "limitations": [
            "Accounting contribution and profile association are descriptive; they are not causal effects or counterfactual market-price impact.",
            "Profiles are observable prior-season NBA-market behavior, not verified bot, retail, professional, or market-maker identities.",
            "The unit is a participant-side Activity API BUY record, not a unique matched market transaction; one taker transaction can correspond to multiple maker fill records.",
            "The selected final-five longshot BUY cohort is not representative of all trades or of each wallet's whole portfolio.",
            "Profile-component confidence intervals are exploratory percentile intervals and are not adjusted for the many profile, weighting, outcome, and estimator combinations.",
            "price minus realized payoff is noisy one-season calibration, not by itself an ex-ante mispricing measure.",
            "P* is estimated and is not the true probability.",
            "No historical 2025-26 Polymarket order-book midpoint series is assembled in this project; a third-party vendor advertises minute-level L2 history from August 2025, but coverage and licensing have not been audited. Comparable Kalshi wallet identities are unavailable.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print("\nEQUAL-GAME price-minus-outcome profile contributions (pp):")
    print(result.loc[result.weighting.eq("trade_count") & result.gap.eq("price_minus_outcome")
                     & result.estimator.eq("equal_game"),
                     ["profile", "global_weight_share", "profile_gap_pp",
                      "additive_contribution_pp", "ci95_low_pp", "ci95_high_pp"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
