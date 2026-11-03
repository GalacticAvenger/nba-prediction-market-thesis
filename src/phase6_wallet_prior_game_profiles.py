"""Test observable Polymarket NBA wallet profiles using only prior-game history.

For every wallet/target-game pair, profile features are computed from that
wallet's NBA-market participant records timestamped before the target game's
first ESPN play. Records from the target game are excluded, including any
pre-tip activity, to avoid using behavior from the game being analyzed.
This is an exploratory association analysis, not account identity or causality.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from phase6_wallet_common_support import fit_many  # noqa: E402

P2 = ROOT / "data/interim/phase2"
P3 = ROOT / "data/interim/phase3"
P6 = ROOT / "data/interim/phase6"
PBP_DIR = ROOT / "data/interim/espn_pbp/season=2026/season_type=2"
MAKER_FILE = P2 / "polymarket_maker_fills_season_raw.parquet"
TAKER_FILE = P2 / "polymarket_taker_rows_season.parquet"
TARGET_FILE = P6 / "polymarket_wallet_late5_target_trades.parquet"
PSTAR_FILE = P3 / "pstar_2025_26_every_second.parquet"
OUT = P6 / "prior_game_behavior"
MIN_PRIOR_RECORDS = 20
MIN_PRIOR_GAMES = 3
HIGH_ACTIVITY_RECORDS_PER_DAY = 20
ROLE_DOMINANCE_SHARE = 0.75


def load_source() -> pd.DataFrame:
    cols = ["proxyWallet", "side", "asset", "conditionId", "size", "price",
            "timestamp", "transactionHash", "espn_game_id"]
    parts = []
    for path, role in ((MAKER_FILE, "maker"), (TAKER_FILE, "taker")):
        q = pd.read_parquet(path, columns=cols)
        q["wallet"] = q.proxyWallet.astype("string").str.lower()
        q["game_id"] = q.espn_game_id.astype("string")
        q["timestamp"] = pd.to_numeric(q.timestamp, errors="coerce")
        q["size"] = pd.to_numeric(q["size"], errors="coerce")
        q["price"] = pd.to_numeric(q.price, errors="coerce")
        q = q.dropna(subset=["wallet", "game_id", "timestamp", "size", "price"])
        q = q.loc[q["size"].gt(0) & q.price.gt(0) & q.price.lt(1)].copy()
        q["timestamp"] = q.timestamp.astype("int64")
        q["notional"] = q["size"] * q.price
        q["maker"] = int(role == "maker")
        q["day"] = pd.to_datetime(q.timestamp, unit="s", utc=True).dt.strftime("%Y-%m-%d")
        q = q[["wallet", "game_id", "conditionId", "timestamp", "notional", "maker", "day"]].copy()
        for col in ("wallet", "game_id", "conditionId", "day"):
            q[col] = q[col].astype("category")
        parts.append(q)
    rows = pd.concat(parts, ignore_index=True)
    return rows


def game_start_times() -> dict[str, int]:
    files = sorted(PBP_DIR.glob("*.parquet"))
    pieces = [pd.read_parquet(p, columns=["game_id", "ts_wall_utc"]) for p in files]
    pbp = pd.concat(pieces, ignore_index=True)
    pbp["game_id"] = pbp.game_id.astype(str)
    pbp["ts"] = pd.to_datetime(pbp.ts_wall_utc, utc=True, errors="coerce")
    pbp = pbp.dropna(subset=["ts"])
    starts = pbp.groupby("game_id").ts.min()
    return {str(g): int(ts.timestamp()) for g, ts in starts.items()}


def prefix_arrays(frame: pd.DataFrame):
    """Sorted timestamp arrays and prefix sums for fast as-of lookups."""
    result = {}
    for wallet, q in frame.groupby("wallet", sort=False, observed=True):
        result[str(wallet)] = {
            "ts": q.timestamp.to_numpy(dtype=np.int64),
            "n": np.arange(1, len(q) + 1, dtype=np.int64),
            "maker": q.maker.to_numpy(dtype=np.int64).cumsum(),
            "notional": q.notional.to_numpy(dtype=float).cumsum(),
        }
    return result


def prior_features(rows: pd.DataFrame, targets: pd.DataFrame,
                   starts: dict[str, int]) -> pd.DataFrame:
    # Sort once, then build compact as-of arrays. Unique first-seen game/day
    # timestamps allow breadth and engagement features without rescanning fills.
    rows = rows.sort_values("timestamp", kind="mergesort")
    wallet_prefix = prefix_arrays(rows)
    game_first_frame = rows.drop_duplicates(["wallet", "game_id"])[
        ["wallet", "game_id", "timestamp"]]
    day_first_frame = rows.drop_duplicates(["wallet", "day"])[
        ["wallet", "day", "timestamp", "game_id"]]
    game_first_lookup = {(str(r.wallet), str(r.game_id)): int(r.timestamp)
                         for r in game_first_frame.itertuples(index=False)}
    day_first_lookup = {(str(r.wallet), str(r.day)):
                        (int(r.timestamp), str(r.game_id))
                        for r in day_first_frame.itertuples(index=False)}
    wallet_game_days = {
        (str(w), str(g)): q.day.astype(str).unique().tolist()
        for (w, g), q in rows.groupby(["wallet", "game_id"], sort=False, observed=True)
    }
    game_first = {str(w): np.sort(q.timestamp.to_numpy(dtype=np.int64))
                  for w, q in game_first_frame.groupby("wallet", sort=False, observed=True)}
    day_first = {str(w): q for w, q in day_first_frame.groupby("wallet", sort=False, observed=True)}
    game_prefix = {
        (str(w), str(g)): {
            "ts": q.timestamp.to_numpy(dtype=np.int64),
            "maker": q.maker.to_numpy(dtype=np.int64).cumsum(),
            "notional": q.notional.to_numpy(dtype=float).cumsum(),
        }
        for (w, g), q in rows.groupby(["wallet", "game_id"], sort=False, observed=True)
    }
    pairs = targets[["wallet", "game_id", "conditionId"]].drop_duplicates().copy()
    pairs["start_ts"] = pairs.game_id.astype(str).map(starts)
    if pairs.start_ts.isna().any():
        missing = int(pairs.start_ts.isna().sum())
        raise ValueError(f"No ESPN start timestamp for {missing} target wallet-game pairs")

    feature_rows = []
    for wallet, wallet_pairs in pairs.groupby("wallet", sort=False, observed=True):
        wallet = str(wallet)
        main = wallet_prefix.get(wallet)
        if main is None:
            continue
        ts = main["ts"]
        main_maker = main["maker"]
        main_notional = main["notional"]
        game_times = game_first.get(wallet, np.array([], dtype=np.int64))
        day_records = day_first.get(wallet)
        for item in wallet_pairs.itertuples(index=False):
            game_id, cutoff = str(item.game_id), int(item.start_ts)
            end = int(np.searchsorted(ts, cutoff, side="left"))
            n_all = end
            maker_all = int(main_maker[end - 1]) if end else 0
            notional_all = float(main_notional[end - 1]) if end else 0.0
            current = game_prefix.get((wallet, game_id))
            if current is None:
                n_current, maker_current, notional_current = 0, 0, 0.0
            else:
                cur_end = int(np.searchsorted(current["ts"], cutoff, side="left"))
                n_current = cur_end
                maker_current = int(current["maker"][cur_end - 1]) if cur_end else 0
                notional_current = float(current["notional"][cur_end - 1]) if cur_end else 0.0
            n = n_all - n_current
            maker_n = maker_all - maker_current
            notional_sum = notional_all - notional_current

            games = int(np.searchsorted(game_times, cutoff, side="left"))
            # If this wallet had pre-tip activity in the target market, remove
            # that game from its own prior-game count.
            own_game_first = game_first_lookup.get((wallet, game_id))
            if own_game_first is not None and own_game_first < cutoff:
                games -= 1
            days = 0
            if day_records is not None:
                days = int(np.searchsorted(day_records.timestamp.to_numpy(dtype=np.int64),
                                           cutoff, side="left"))
                # Remove target-game-only days from the history denominator.
                for day in wallet_game_days.get((wallet, game_id), []):
                    first = day_first_lookup.get((wallet, day))
                    if first is not None and first[0] < cutoff and first[1] == game_id:
                        days -= 1
            days = max(days, 0)
            rate = n / days if days > 0 else np.nan
            maker_share = maker_n / n if n else np.nan
            if n < MIN_PRIOR_RECORDS or games < MIN_PRIOR_GAMES:
                profile = "limited_prior_history"
            elif rate >= HIGH_ACTIVITY_RECORDS_PER_DAY:
                profile = "high_prior_activity"
            elif maker_share >= ROLE_DOMINANCE_SHARE:
                profile = "maker_record_dominant"
            elif maker_share <= 1 - ROLE_DOMINANCE_SHARE:
                profile = "taker_record_dominant"
            else:
                profile = "established_mixed"
            feature_rows.append({
                "wallet": wallet, "game_id": game_id, "target_game_start_ts": cutoff,
                "prior_activity_records": n, "prior_games": max(games, 0),
                "prior_active_days": days,
                "prior_records_per_active_day": rate,
                "prior_maker_record_share": maker_share,
                "prior_mean_record_notional": notional_sum / n if n else np.nan,
                "prior_behavior_profile": profile,
            })
    return pd.DataFrame(feature_rows)


def attach_outcomes(target: pd.DataFrame) -> pd.DataFrame:
    p = pd.read_parquet(PSTAR_FILE, columns=["game_id", "period", "clock_s_remaining", "pstar"])
    p.game_id = p.game_id.astype(str)
    p.period = pd.to_numeric(p.period, errors="coerce")
    p.clock_s_remaining = pd.to_numeric(p.clock_s_remaining, errors="coerce")
    grids = {}
    for (gid, period), q in p.groupby(["game_id", "period"], sort=False):
        q = q.sort_values("clock_s_remaining", ascending=False)
        grids[(str(gid), int(period))] = (q.clock_s_remaining.to_numpy(dtype=int),
                                          q.pstar.to_numpy(dtype=float))
    target = target.copy()
    target["pstar_home"] = np.nan
    target["period"] = pd.to_numeric(target.period, errors="coerce")
    for (gid, period), ix in target.groupby(["game_id", "period"], sort=False).groups.items():
        if pd.isna(period) or (str(gid), int(period)) not in grids:
            continue
        clocks, probs = grids[(str(gid), int(period))]
        rem = np.rint(target.loc[ix, "clock_s_remaining"].to_numpy(dtype=float)).astype(int)
        pos = np.searchsorted(-clocks, -rem, side="left")
        pos = np.clip(pos, 0, len(probs) - 1)
        target.loc[ix, "pstar_home"] = probs[pos]
    target["pstar_own_recomputed"] = np.where(
        target.asset_is_home.astype(bool), target.pstar_home, 1 - target.pstar_home)
    # Guard the new analysis against a silent benchmark-coordinate mismatch.
    diff = (target.pstar_own_recomputed - target.pstar_own).abs()
    if diff.max(skipna=True) > 1e-8:
        raise ValueError(f"Recomputed P* differs from frozen cohort (max {diff.max()})")
    target["minute"] = np.floor((300 - target.clock_s_remaining) / 60).clip(0, 4).astype(int)
    bins = [0, .05, .10, .15, .20, .25, .30, .40, .50]
    target["pbin"] = pd.cut(target.pstar_own, bins=bins, include_lowest=True,
                            labels=False, right=True)
    return target


def estimate_contrast(frame: pd.DataFrame, group_name: str, treatment_mask: pd.Series,
                      control_mask: pd.Series, comparison: str) -> list[dict]:
    q = frame.loc[treatment_mask | control_mask].copy()
    q["treated"] = treatment_mask.loc[q.index].astype(bool)
    keys = ["game_id", "minute", "pbin", "role"]
    support = q.groupby(keys, observed=True).treated.agg(["min", "max"])
    support = support.loc[(support["min"] == 0) & (support["max"] == 1)].index
    common = q.set_index(keys).loc[lambda x: x.index.isin(support)].reset_index()
    outcomes = ("settlement_payoff_minus_cost", "outcome_minus_benchmark",
                "benchmark_overpayment")
    if common.empty:
        return [{"comparison": comparison, "outcome": outcome,
                 "estimate": None, "se_two_way_cluster": None,
                 "ci95_low": None, "ci95_high": None, "rows": 0,
                 "cells": 0, "games": 0, "wallets": 0,
                 "profile_definition": group_name,
                 "pre_support_rows": int(len(q))} for outcome in outcomes]
    estimates, _, _ = fit_many(common, outcomes, "treated", comparison, keys)
    for result in estimates:
        result["profile_definition"] = group_name
        result["pre_support_rows"] = int(len(q))
    return estimates


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_source()
    target = pd.read_parquet(TARGET_FILE)
    target["wallet"] = target.wallet.astype(str).str.lower()
    target["game_id"] = target.game_id.astype(str)
    target = attach_outcomes(target)
    starts = game_start_times()
    features = prior_features(rows, target, starts)
    target = target.merge(features, on=["wallet", "game_id"], how="left",
                          validate="many_to_one")
    if target.prior_behavior_profile.isna().any():
        raise ValueError("Some target buys did not receive a prior-game profile")
    target.to_parquet(OUT / "target_buys_with_prior_game_profiles.parquet", index=False)
    features.to_csv(OUT / "wallet_game_prior_profiles.csv", index=False)

    counts = target.groupby("prior_behavior_profile", observed=True).agg(
        buys=("wallet", "size"), wallets=("wallet", "nunique"), games=("game_id", "nunique"),
        mean_prior_games=("prior_games", "mean"),
        mean_prior_records=("prior_activity_records", "mean"),
        mean_prior_records_per_day=("prior_records_per_active_day", "mean"),
        mean_prior_maker_share=("prior_maker_record_share", "mean"),
    ).reset_index()
    outcomes = []
    profile = target.prior_behavior_profile
    outcomes += estimate_contrast(
        target, "limited_prior_history_vs_established",
        profile.eq("limited_prior_history"), ~profile.eq("limited_prior_history"),
        "limited_prior_history_vs_established")
    established = ~profile.eq("limited_prior_history")
    outcomes += estimate_contrast(
        target, "high_prior_activity_vs_other_established",
        profile.eq("high_prior_activity"), established & ~profile.eq("high_prior_activity"),
        "high_prior_activity_vs_other_established")
    outcomes += estimate_contrast(
        target, "maker_vs_taker_record_dominant_established",
        profile.eq("maker_record_dominant"), profile.eq("taker_record_dominant"),
        "maker_vs_taker_record_dominant_established")
    outcomes_df = pd.DataFrame(outcomes)
    counts.to_csv(OUT / "prior_behavior_profile_counts.csv", index=False)
    outcomes_df.to_csv(OUT / "prior_behavior_profile_common_support.csv", index=False)
    summary = {
        "design": "Exploratory, time-ordered observable profiles; features use participant-side NBA-market records strictly before each game's first ESPN play, excluding the target game.",
        "profile_rules": {
            "limited_prior_history": f"fewer than {MIN_PRIOR_RECORDS} prior participant-side records or fewer than {MIN_PRIOR_GAMES} prior NBA games",
            "high_prior_activity": f"at least {HIGH_ACTIVITY_RECORDS_PER_DAY} prior records per prior UTC active day, among adequately observed wallets",
            "maker_record_dominant": f"prior maker-record share at least {ROLE_DOMINANCE_SHARE:.0%}, after high-activity rule",
            "taker_record_dominant": f"prior maker-record share at most {1-ROLE_DOMINANCE_SHARE:.0%}, after high-activity rule",
            "established_mixed": "all other adequately observed wallets",
        },
        "target_buys": int(len(target)),
        "wallets": int(target.wallet.nunique()),
        "games": int(target.game_id.nunique()),
        "profile_counts": counts.to_dict("records"),
        "contrasts": outcomes,
        "interpretation": "Profiles are behavioral summaries of this NBA-season data, not bots/retail/professional labels. Common-support contrasts condition on game, final-five minute, P* band, and participant role; two-way uncertainty is clustered by game and wallet.",
        "limits": [
            "The history starts with the assembled 2025-26 NBA Polymarket extract; prior activity outside it is unobserved.",
            "Profile rules are researcher-defined and the outcome comparisons are exploratory, not preregistered confirmatory tests.",
            "Participant-side maker/taker record shares are not identity or automation labels.",
            "Contrasts are conditional associations among selected late-game longshot buys, not wallet P&L or causal market impact.",
            "The cohort only includes NBA-market records in the assembled season, not each wallet's full platform portfolio.",
        ],
    }
    (OUT / "prior_behavior_profile_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
