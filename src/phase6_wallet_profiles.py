"""Outcome-free Polymarket NBA wallet activity profiles for Phase 6.

This intentionally does not label accounts as bots, retail, or market makers.
It describes only activity visible in the current in-game Data API extract.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P2 = ROOT / "data/interim/phase2"
OUT = ROOT / "data/interim/phase6"
MAKER_FILE = P2 / "polymarket_maker_fills_season_raw.parquet"
TAKER_FILE = P2 / "polymarket_taker_rows_season.parquet"
CONFIG_FILE = ROOT / "config.yaml"


def load_participant_rows() -> pd.DataFrame:
    common = ["proxyWallet", "side", "asset", "conditionId", "size",
              "price", "timestamp", "transactionHash", "espn_game_id"]
    makers = pd.read_parquet(MAKER_FILE, columns=common)
    takers = pd.read_parquet(TAKER_FILE, columns=common)
    makers["role"] = "maker"
    takers["role"] = "taker"
    data = pd.concat([makers, takers], ignore_index=True)
    data["wallet"] = data.proxyWallet.astype("string").str.lower()
    data["game_id"] = data.espn_game_id.astype("string")
    data["timestamp"] = pd.to_numeric(data.timestamp, errors="coerce")
    data["size"] = pd.to_numeric(data["size"], errors="coerce")
    data["price"] = pd.to_numeric(data["price"], errors="coerce")
    data["day_utc"] = pd.to_datetime(data.timestamp, unit="s", utc=True,
                                     errors="coerce").dt.strftime("%Y-%m-%d")
    data = data.loc[
        data.wallet.notna() & data.wallet.ne("") & data.day_utc.notna()
        & data.game_id.notna() & data["size"].gt(0) & data["price"].gt(0)
        & data["price"].lt(1)
    ].copy()
    data["notional"] = data["size"] * data["price"]
    data["maker_shares"] = data["size"].where(data.role.eq("maker"), 0.0)
    data["maker_records"] = data.role.eq("maker").astype("int8")
    return data


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_participant_rows()
    try:
        import yaml
        cfg = yaml.safe_load(CONFIG_FILE.read_text())
    except Exception as exc:  # keep the analysis dependencies explicit
        raise RuntimeError(f"Could not read locked wallet thresholds: {exc}") from exc
    thresholds = cfg["phase4"]["wallet_classification_thresholds"]

    agg = rows.groupby("wallet", sort=False).agg(
        activity_records=("wallet", "size"),
        games=("game_id", "nunique"),
        active_days=("day_utc", "nunique"),
        maker_records=("maker_records", "sum"),
        maker_shares=("maker_shares", "sum"),
        total_shares=("size", "sum"),
        total_notional=("notional", "sum"),
        median_record_notional=("notional", "median"),
        median_record_size=("size", "median"),
    ).reset_index()
    agg["records_per_active_day"] = agg.activity_records / agg.active_days
    agg["maker_record_share"] = agg.maker_records / agg.activity_records
    agg["maker_share_volume"] = agg.maker_shares / agg.total_shares
    agg["games_per_active_day"] = agg.games / agg.active_days
    agg["notional_per_active_day"] = agg.total_notional / agg.active_days

    for cut in thresholds["trades_per_active_day"]:
        agg[f"high_activity_ge_{cut}_per_active_day"] = agg.records_per_active_day.ge(cut)
    for cut in thresholds["maker_share"]:
        agg[f"maker_record_share_ge_{cut:g}"] = agg.maker_record_share.ge(cut)
        agg[f"taker_record_share_ge_{cut:g}"] = (1 - agg.maker_record_share).ge(cut)

    # Stable sort makes the file reproducible; wallet IDs remain pseudonymous.
    agg.sort_values(["activity_records", "wallet"], ascending=[False, True],
                    inplace=True, kind="mergesort")
    agg.to_csv(OUT / "polymarket_wallet_behavior_profiles.csv", index=False)

    # Transaction-level checks are descriptive reconciliation diagnostics.
    makers = pd.read_parquet(MAKER_FILE, columns=[
        "transactionHash", "proxyWallet", "size", "takerWallet", "takerSide"])
    takers = pd.read_parquet(TAKER_FILE, columns=[
        "transactionHash", "proxyWallet", "side", "size"])
    makers["tx"] = makers.transactionHash.astype("string").str.lower()
    takers["tx"] = takers.transactionHash.astype("string").str.lower()
    takers["proxyWallet"] = takers.proxyWallet.astype("string").str.lower()
    makers["takerWallet"] = makers.takerWallet.astype("string").str.lower()
    taker_tx = set(takers.tx.dropna())
    maker_tx = set(makers.tx.dropna())
    maker_by_tx = makers.groupby("tx", sort=False).agg(
        maker_fills=("size", "size"), maker_shares=("size", "sum"),
        taker_wallet=("takerWallet", "first"), stored_taker_side=("takerSide", "first"),
        maker_identities=("takerWallet", "nunique"),
    )
    taker_by_tx = takers.groupby("tx", sort=False).agg(
        taker_rows=("size", "size"), taker_shares=("size", "sum"),
        taker_wallet=("proxyWallet", "first"), api_taker_side=("side", "first"),
        taker_identities=("proxyWallet", "nunique"),
    )
    paired = maker_by_tx.join(taker_by_tx, how="inner", lsuffix="_maker", rsuffix="_api")
    size_rel_error = ((paired.maker_shares - paired.taker_shares).abs()
                      / paired.maker_shares.clip(lower=1e-9))
    checks = {
        "maker_activity_rows": int(len(makers)),
        "taker_activity_rows": int(len(takers)),
        "maker_wallets": int(makers.proxyWallet.nunique()),
        "taker_wallets": int(takers.proxyWallet.nunique()),
        "maker_transactions": int(len(maker_tx)),
        "taker_transactions": int(len(taker_tx)),
        "shared_transactions": int(len(maker_tx & taker_tx)),
        "taker_transactions_missing_from_maker_table": int(len(taker_tx - maker_tx)),
        "maker_transactions_missing_from_taker_table": int(len(maker_tx - taker_tx)),
        "joined_taker_wallet_match_share": float(
            paired.taker_wallet_maker.str.lower().eq(paired.taker_wallet_api).mean()),
        "joined_taker_side_match_share": float(
            paired.stored_taker_side.eq(paired.api_taker_side).mean()),
        "tx_with_multiple_maker_fills_share": float(paired.maker_fills.gt(1).mean()),
        "tx_with_multiple_taker_wallets_share": float(paired.taker_identities.gt(1).mean()),
        "maker_vs_taker_share_volume_match_within_1e-5_share": float(
            size_rel_error.lt(1e-5).mean()),
        "maker_taker_share_volume_relative_error_p95": float(size_rel_error.quantile(.95)),
        "data_scope": "in-game 2025-26 NBA regular-season Polymarket activity only",
        "wallet_profile_unit": "participant-side Data API activity row",
        "wallet_labels": "none; observable profiles only",
    }

    role_stats = rows.groupby("role").agg(
        records=("wallet", "size"), wallets=("wallet", "nunique"),
        games=("game_id", "nunique"), notional=("notional", "sum"),
        median_notional=("notional", "median"), median_shares=("size", "median"),
    )
    wallet_quantiles = {
        col: {str(q): float(agg[col].quantile(q)) for q in (.5, .9, .99)}
        for col in ("activity_records", "games", "active_days",
                    "records_per_active_day", "total_notional",
                    "median_record_notional", "maker_record_share",
                    "maker_share_volume")
    }
    # Within-role top-account shares are useful concentration diagnostics. The
    # row unit differs by role (maker fill vs taker order), so report each
    # separately and do not combine them as platform market share.
    role_concentration = {}
    for role, q in rows.groupby("role", sort=False):
        wallet_counts = q.groupby("wallet", sort=False).size().sort_values(ascending=False)
        n_top = max(1, math.ceil(len(wallet_counts) * .01))
        role_concentration[role] = {
            "wallets": int(len(wallet_counts)),
            "top_1pct_wallet_count": n_top,
            "top_1pct_record_share": float(wallet_counts.head(n_top).sum() / wallet_counts.sum()),
        }
    summary = {
        "data_quality": checks,
        "activity_rows_total": int(len(rows)),
        "distinct_wallets_across_either_role": int(rows.wallet.nunique()),
        "role_summary": {role: {k: float(v) if k != "records" and k != "wallets" and k != "games" else int(v)
                                  for k, v in role_stats.loc[role].items()}
                         for role in role_stats.index},
        "role_concentration": role_concentration,
        "wallet_quantiles": wallet_quantiles,
        "config_thresholds": thresholds,
        "profile_interpretation": {
            "high_activity": "within-sample in-game NBA records per active day",
            "maker_dominant": "share of participant-side activity records observed in maker role",
            "maker_volume_share": "reported as a diagnostic only; maker and taker rows do not reconcile in every transaction",
            "low_stake": "observed notional only; not a verified retail identity",
            "bot_like": "not assigned in this descriptive stage",
            "market_maker": "not assigned; no full order-placement/cancellation book",
        },
    }
    (OUT / "polymarket_wallet_behavior_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
