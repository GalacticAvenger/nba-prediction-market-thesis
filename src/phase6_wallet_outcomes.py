"""Descriptive outcome/benchmark results for observable Polymarket wallet profiles.

This is a screening analysis of purchases, not wallet P&L or causal attribution.
It uses only activity rows whose own asset, action, price and wallet are known.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ingest_polymarket_onchain import TEAM_ALIASES  # noqa: E402
from run_polymarket_selection_analysis import canonical, token_map  # noqa: E402

P2 = ROOT / "data/interim/phase2"
P3 = ROOT / "data/interim/phase3"
P6 = ROOT / "data/interim/phase6"
PBP_DIR = ROOT / "data/interim/espn_pbp/season=2026/season_type=2"
MAKER_FILE = P2 / "polymarket_maker_fills_season_raw.parquet"
TAKER_FILE = P2 / "polymarket_taker_rows_season.parquet"
MAP_FILE = P2 / "polymarket_nba_2025_26_market_map.json"
PROFILE_FILE = P6 / "polymarket_wallet_behavior_profiles.csv"
PSTAR_FILE = P3 / "pstar_2025_26_every_second.parquet"
SEED = 1222026
DRAWS = 2000


def market_crosswalk():
    doc = json.loads(MAP_FILE.read_text())
    result = {}
    errors = []
    for m in doc["markets"]:
        gid = str(m["espn_game_id"])
        try:
            by_team = token_map(m)
            home = canonical(m["home_team"])
            away = canonical(m["away_team"])
            winner = canonical(m["resolved_winner_abbreviation"])
            result[gid] = {
                "home_token": str(by_team[home]),
                "away_token": str(by_team[away]),
                "winner_token": str(by_team[winner]),
            }
        except Exception as exc:
            errors.append({"game_id": gid, "error": str(exc)})
    return result, errors


def playbyplay_timelines():
    files = list(PBP_DIR.glob("*.parquet"))
    parts = [pd.read_parquet(p, columns=["game_id", "period", "clock_s_remaining", "ts_wall_utc"])
             for p in files]
    pbp = pd.concat(parts, ignore_index=True)
    pbp["game_id"] = pbp.game_id.astype(str)
    pbp["ts"] = pd.to_datetime(pbp.ts_wall_utc, utc=True, errors="coerce")
    pbp["period"] = pd.to_numeric(pbp.period, errors="coerce")
    pbp["clock_s_remaining"] = pd.to_numeric(pbp.clock_s_remaining, errors="coerce")
    pbp = pbp.dropna(subset=["ts", "period", "clock_s_remaining"])
    timelines = {}
    for gid, q in pbp.groupby("game_id", sort=False):
        q = q.sort_values("ts")
        timelines[str(gid)] = (
            q.ts.astype("int64").to_numpy() // 10**9,
            q.period.to_numpy(dtype=np.int16),
            q.clock_s_remaining.to_numpy(dtype=float),
        )
    return timelines


def attach_clock(frame, timelines):
    frame["period"] = np.nan
    frame["clock_s_remaining"] = np.nan
    for gid, ix in frame.groupby("game_id", sort=False).groups.items():
        tl = timelines.get(str(gid))
        if tl is None:
            continue
        wall, period, clock = tl
        ts = frame.loc[ix, "timestamp"].to_numpy(dtype=np.int64)
        pos = np.searchsorted(wall, ts, side="right") - 1
        valid = pos >= 0
        idx = np.asarray(ix)
        frame.loc[idx[valid], "period"] = period[pos[valid]]
        frame.loc[idx[valid], "clock_s_remaining"] = clock[pos[valid]]
    return frame


def attach_pstar(frame):
    p = pd.read_parquet(PSTAR_FILE, columns=["game_id", "period", "clock_s_remaining", "pstar"])
    p["game_id"] = p.game_id.astype(str)
    p["period"] = pd.to_numeric(p.period, errors="coerce")
    p["clock_s_remaining"] = pd.to_numeric(p.clock_s_remaining, errors="coerce")
    grid = {}
    for (gid, period), q in p.groupby(["game_id", "period"], sort=False):
        q = q.sort_values("clock_s_remaining", ascending=False)
        grid[(str(gid), int(period))] = (
            q.clock_s_remaining.to_numpy(dtype=int), q.pstar.to_numpy(dtype=float))
    frame["pstar_home"] = np.nan
    for (gid, period), ix in frame.groupby(["game_id", "period"], sort=False).groups.items():
        if pd.isna(period):
            continue
        vals = grid.get((str(gid), int(period)))
        if vals is None:
            continue
        clocks, probs = vals
        remaining = frame.loc[ix, "clock_s_remaining"].to_numpy(dtype=float)
        pos = np.searchsorted(-clocks, -np.rint(remaining).astype(int), side="left")
        pos = np.clip(pos, 0, len(probs) - 1)
        frame.loc[ix, "pstar_home"] = probs[pos]
    return frame


def load_participant_rows():
    cols = ["proxyWallet", "side", "asset", "conditionId", "size", "price",
            "timestamp", "transactionHash", "espn_game_id"]
    makers = pd.read_parquet(MAKER_FILE, columns=cols)
    takers = pd.read_parquet(TAKER_FILE, columns=cols)
    makers["role"] = "maker"
    takers["role"] = "taker"
    rows = pd.concat([makers, takers], ignore_index=True)
    rows["wallet"] = rows.proxyWallet.astype("string").str.lower()
    rows["game_id"] = rows.espn_game_id.astype("string")
    rows["asset"] = rows.asset.astype("string")
    rows["side"] = rows.side.astype("string").str.upper()
    for c in ("size", "price", "timestamp"):
        rows[c] = pd.to_numeric(rows[c], errors="coerce")
    rows = rows.dropna(subset=["wallet", "game_id", "asset", "size", "price", "timestamp"])
    rows = rows.loc[rows["size"].gt(0) & rows["price"].gt(0) & rows["price"].lt(1)].copy()
    rows["timestamp"] = rows.timestamp.astype("int64")
    return rows


def two_way_cluster_mean(frame, value, wallet_equal=False):
    if frame.empty:
        return {"estimate": None, "ci95": [None, None], "se": None,
                "games": 0, "wallets": 0}
    if wallet_equal:
        cells = frame.groupby(["game_id", "wallet"], sort=False)[value].mean().rename("cell_value").reset_index()
        n_wallets = cells.groupby("game_id").wallet.transform("size")
        cells["weight"] = 1.0 / n_wallets
    else:
        cells = frame.groupby(["game_id", "wallet"], sort=False)[value].agg(
            cell_value="mean", records="size").reset_index()
        game_records = frame.groupby("game_id", sort=False).size()
        cells["weight"] = cells.records / cells.game_id.map(game_records)
    values = cells.cell_value.to_numpy(dtype=float)
    weights = cells.weight.to_numpy(dtype=float)
    estimate = float(np.average(values, weights=weights))
    score = pd.Series(weights * (values - estimate), index=cells.index)
    cells["score"] = score
    sg = cells.groupby("game_id").score.sum()
    sw = cells.groupby("wallet").score.sum()
    sc = cells.score
    G, W, C = len(sg), len(sw), len(sc)
    meat = 0.0
    if G > 1:
        meat += (G / (G - 1)) * float((sg * sg).sum())
    if W > 1:
        meat += (W / (W - 1)) * float((sw * sw).sum())
    if C > 1:
        meat -= (C / (C - 1)) * float((sc * sc).sum())
    se = float(np.sqrt(max(0.0, meat) / weights.sum() ** 2))
    return {"estimate": estimate,
            "ci95": [estimate - 1.96 * se, estimate + 1.96 * se],
            "se": se, "games": int(G), "wallets": int(W)}


def main():
    P6.mkdir(parents=True, exist_ok=True)
    markets, mapping_errors = market_crosswalk()
    rows = load_participant_rows()
    print(f"loaded {len(rows):,} activity rows", flush=True)
    rows = rows.loc[rows.game_id.isin(markets)].copy()
    print(f"mapped {len(rows):,} activity rows", flush=True)
    timeline = playbyplay_timelines()
    rows = attach_clock(rows, timeline)
    rows["asset_is_home"] = False
    rows["y_own"] = np.nan
    bad_market, unknown_asset = 0, 0
    for gid, ix in rows.groupby("game_id", sort=False).groups.items():
        m = markets.get(str(gid))
        if not m:
            bad_market += len(ix)
            continue
        assets = rows.loc[ix, "asset"]
        is_home = assets.eq(m["home_token"])
        is_away = assets.eq(m["away_token"])
        unknown_asset += int((~(is_home | is_away)).sum())
        is_winner = assets.eq(m["winner_token"])
        rows.loc[ix, "asset_is_home"] = is_home
        rows.loc[ix, "y_own"] = np.where(is_home | is_away, is_winner.astype(float), np.nan)
    rows = rows.loc[rows.y_own.notna() & rows.period.notna()
                    & rows.clock_s_remaining.notna()].copy()
    rows = attach_pstar(rows)
    rows["pstar_own"] = np.where(rows.asset_is_home, rows.pstar_home, 1 - rows.pstar_home)
    rows["y_own"] = rows.y_own.astype("int8")

    profiles = pd.read_csv(PROFILE_FILE)
    pcols = ["wallet", "records_per_active_day", "maker_record_share",
             "median_record_notional", "high_activity_ge_20_per_active_day",
             "high_activity_ge_100_per_active_day", "high_activity_ge_500_per_active_day",
             "maker_record_share_ge_0.75", "taker_record_share_ge_0.75"]
    profiles["wallet"] = profiles.wallet.astype(str).str.lower()
    p25_stake = float(profiles.median_record_notional.quantile(.25))
    profiles["low_activity_low_stake_proxy"] = (
        profiles.records_per_active_day.le(20)
        & profiles.median_record_notional.le(p25_stake)
    )
    rows = rows.merge(profiles[pcols + ["low_activity_low_stake_proxy"]],
                      on="wallet", how="left", validate="many_to_one")
    rows = rows.loc[rows.records_per_active_day.notna()].copy()

    # The target is a purchase of a market-priced longshot in the locked final-5
    # window, where the independent P* benchmark also considers it an underdog.
    target = rows.loc[
        rows.period.eq(4) & rows.clock_s_remaining.ge(0)
        & rows.clock_s_remaining.le(300) & rows.side.eq("BUY")
        & rows["price"].ge(.05) & rows["price"].le(.20)
        & rows.pstar_own.lt(.5) & rows.pstar_own.gt(0)
    ].copy()
    target["benchmark_overpayment"] = target["price"] - target.pstar_own
    target["settlement_payoff_minus_cost"] = target.y_own - target["price"]
    target["outcome_minus_benchmark"] = target.y_own - target.pstar_own
    target["excess_benchmark_spend"] = target["size"] * target.benchmark_overpayment

    # Preserve the exact target cohort as a research input for the lifecycle
    # position reconstruction. This is a participant-level record, with the
    # account's own token/side/price and transaction hash intact.
    target_cols = [
        "wallet", "game_id", "conditionId", "transactionHash", "timestamp",
        "role", "asset", "side", "price", "size", "period",
        "clock_s_remaining", "asset_is_home", "y_own", "pstar_own",
        "records_per_active_day", "maker_record_share",
        "median_record_notional", "high_activity_ge_20_per_active_day",
        "high_activity_ge_100_per_active_day", "high_activity_ge_500_per_active_day",
        "maker_record_share_ge_0.75", "taker_record_share_ge_0.75",
        "low_activity_low_stake_proxy", "benchmark_overpayment",
        "settlement_payoff_minus_cost", "outcome_minus_benchmark",
    ]
    target[target_cols].to_parquet(
        P6 / "polymarket_wallet_late5_target_trades.parquet", index=False
    )

    profiles_to_report = {
        "all_longshot_buyers": pd.Series(True, index=target.index),
        "high_activity_ge_20_per_day": target.high_activity_ge_20_per_active_day.fillna(False),
        "high_activity_ge_100_per_day": target.high_activity_ge_100_per_active_day.fillna(False),
        "high_activity_ge_500_per_day": target.high_activity_ge_500_per_active_day.fillna(False),
        "maker_record_dominant_ge_75pct": target["maker_record_share_ge_0.75"].fillna(False),
        "taker_record_dominant_ge_75pct": target["taker_record_share_ge_0.75"].fillna(False),
        "low_activity_low_stake_proxy": target.low_activity_low_stake_proxy.fillna(False),
        "maker_role": target.role.eq("maker"),
        "taker_role": target.role.eq("taker"),
    }
    result_rows = []
    for label, mask in profiles_to_report.items():
        q = target.loc[mask].copy()
        mean = two_way_cluster_mean(q, "benchmark_overpayment")
        by_wallet = two_way_cluster_mean(q, "benchmark_overpayment", wallet_equal=True)
        payoff = two_way_cluster_mean(q, "settlement_payoff_minus_cost")
        objective = two_way_cluster_mean(q, "outcome_minus_benchmark")
        result_rows.append({
            "profile": label,
            "activity_rows": int(len(q)),
            "wallets": int(q.wallet.nunique()),
            "games": int(q.game_id.nunique()),
            "participant_role_counts": json.dumps(q.role.value_counts().to_dict(), sort_keys=True),
            "mean_price": float(q["price"].mean()) if len(q) else None,
            "mean_pstar": float(q.pstar_own.mean()) if len(q) else None,
            "trade_weighted_price_minus_pstar": float(q.benchmark_overpayment.mean()) if len(q) else None,
            "game_weighted_price_minus_pstar": mean["estimate"],
            "game_weighted_price_minus_pstar_ci_low": mean["ci95"][0],
            "game_weighted_price_minus_pstar_ci_high": mean["ci95"][1],
            "game_wallet_clustered_price_minus_pstar_se": mean["se"],
            "wallet_equal_within_game_price_minus_pstar": by_wallet["estimate"],
            "wallet_equal_ci_low": by_wallet["ci95"][0],
            "wallet_equal_ci_high": by_wallet["ci95"][1],
            "wallet_equal_two_way_se": by_wallet["se"],
            "game_weighted_y_minus_pstar": objective["estimate"],
            "game_weighted_y_minus_pstar_ci_low": objective["ci95"][0],
            "game_weighted_y_minus_pstar_ci_high": objective["ci95"][1],
            "game_weighted_y_minus_price": payoff["estimate"],
            "game_weighted_y_minus_price_ci_low": payoff["ci95"][0],
            "game_weighted_y_minus_price_ci_high": payoff["ci95"][1],
            "total_bought_shares": float(q["size"].sum()) if len(q) else 0.0,
            "excess_benchmark_spend_usd": float(q.excess_benchmark_spend.sum()) if len(q) else 0.0,
        })
    out = pd.DataFrame(result_rows)
    out.to_csv(P6 / "polymarket_wallet_type_late5_longshot_buys.csv", index=False)
    summary = {
        "estimand": "buyer activity records for own-outcome tokens priced 0.05-0.20 in final 5 regulation minutes, where own-token P* is below 0.50",
        "primary_outcome": "price minus market-free P*; positive means price exceeds the benchmark",
        "secondary_outcome": "settlement payoff minus cost (Y-price) on a purchase; not wallet P&L",
        "uncertainty": "two-way cluster-robust intervals by game and wallet; game-weighted estimates with wallet-equal-within-game sensitivity",
        "n_wallets_panel": int(profiles.wallet.nunique()),
        "n_activity_rows_mapped": int(len(rows)),
        "n_target_buyer_records": int(len(target)),
        "n_target_games": int(target.game_id.nunique()),
        "unmapped_market_rows": int(bad_market),
        "unknown_asset_rows_removed": int(unknown_asset),
        "missing_profile_rows_removed": int((rows.records_per_active_day.isna()).sum()),
        "p25_wallet_median_notional_cutoff_usd": p25_stake,
        "mapping_errors": mapping_errors,
        "limits": [
            "Associations, not causal effects or counterfactual price contributions.",
            "P* is estimated and may contain error.",
            "Settlement payoff minus cost is per purchase record and is not realized wallet profit.",
            "No complete pre-trade inventory history is used; no gain-realization, loss-chasing, or fresh-position claim is identified.",
            "Sample is in-game NBA trades on Polymarket, not each wallet's whole platform portfolio.",
            "Multiple profile comparisons are exploratory and should not be read as confirmatory tests.",
        ],
    }
    (P6 / "polymarket_wallet_type_late5_longshot_buys.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
