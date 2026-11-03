"""Outcome-free transaction-cadence and ticket-size wallet profiles.

The purpose is to study observable trading styles, not to identify real people
or prove that an account is automated. One wallet/transaction is one event:
multiple maker fills sharing a transaction hash are collapsed before cadence
and ticket-size features are computed. All history ends before the target
game's first play and excludes any transaction in the target game.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
P2 = ROOT / "data/interim/phase2"
P6 = ROOT / "data/interim/phase6/prior_game_behavior"
TARGET = P6 / "target_buys_with_prior_game_profiles.parquet"
MAKER = P2 / "polymarket_maker_fills_season_raw.parquet"
TAKER = P2 / "polymarket_taker_rows_season.parquet"
OUT = P6 / "execution_style"
MIN_PRIOR_TRANSACTIONS = 20
MIN_PRIOR_GAMES = 3
RAPID_TRANSACTIONS_PER_DAY = 20
RAPID_MEDIAN_GAP_SECONDS = 30
LARGE_MEDIAN_TICKET_USD = 100
LOW_FREQUENCY_TRANSACTIONS_PER_DAY = 5


def load_target_pairs() -> tuple[pd.DataFrame, set[str]]:
    target = pd.read_parquet(TARGET, columns=["wallet", "game_id", "target_game_start_ts"])
    target["wallet"] = target.wallet.astype(str).str.lower()
    target["game_id"] = target.game_id.astype(str)
    target["target_game_start_ts"] = pd.to_numeric(target.target_game_start_ts).astype("int64")
    pairs = target.drop_duplicates().reset_index(drop=True)
    return pairs, set(pairs.wallet.unique())


def load_transaction_events(wallets: set[str]) -> pd.DataFrame:
    """Read only target wallets in Arrow batches, then deduplicate transaction legs."""
    selected = ["proxyWallet", "timestamp", "transactionHash", "espn_game_id", "size", "price"]
    chunks = []
    for path in (MAKER, TAKER):
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(columns=selected, batch_size=250_000):
            q = batch.to_pandas()
            q["wallet"] = q.proxyWallet.astype("string").str.lower()
            q = q.loc[q.wallet.isin(wallets)].copy()
            if q.empty:
                continue
            q["game_id"] = q.espn_game_id.astype("string")
            q["timestamp"] = pd.to_numeric(q.timestamp, errors="coerce")
            q["size"] = pd.to_numeric(q["size"], errors="coerce")
            q["price"] = pd.to_numeric(q.price, errors="coerce")
            q = q.dropna(subset=["wallet", "game_id", "timestamp", "transactionHash", "size", "price"])
            q = q.loc[q["size"].gt(0) & q.price.gt(0) & q.price.lt(1)]
            if q.empty:
                continue
            q["notional"] = q["size"] * q["price"]
            q = q[["wallet", "game_id", "timestamp", "transactionHash", "notional"]]
            # Reduce each input batch before retaining it in memory.
            q = q.groupby(["wallet", "game_id", "transactionHash"], as_index=False,
                          observed=True).agg(timestamp=("timestamp", "min"),
                                             notional=("notional", "sum"))
            chunks.append(q)
    if not chunks:
        raise ValueError("No transaction records found for target wallets")
    events = pd.concat(chunks, ignore_index=True)
    events = events.groupby(["wallet", "game_id", "transactionHash"], as_index=False,
                            observed=True).agg(timestamp=("timestamp", "min"),
                                               notional=("notional", "sum"))
    events["timestamp"] = events.timestamp.astype("int64")
    events["day"] = (events.timestamp // 86400).astype("int32")
    return events.sort_values(["wallet", "timestamp", "transactionHash"], kind="mergesort")


def build_features(pairs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    by_wallet = {str(w): q.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
                 for w, q in events.groupby("wallet", sort=False, observed=True)}
    result = []
    for p in pairs.itertuples(index=False):
        h = by_wallet.get(str(p.wallet))
        if h is None:
            prior = h
        else:
            prior = h.loc[(h.timestamp < int(p.target_game_start_ts)) &
                          (h.game_id.astype(str) != str(p.game_id))]
        if prior is None or prior.empty:
            n = games = days = 0
            per_day = med_gap = fast5 = fast30 = med_ticket = p90_ticket = np.nan
        else:
            n = int(len(prior))
            games = int(prior.game_id.nunique())
            days = int(prior.day.nunique())
            per_day = n / days if days else np.nan
            med_ticket = float(prior.notional.median())
            p90_ticket = float(prior.notional.quantile(.90))
            # Use only within-active-day gaps. Overnight and between-game gaps
            # are not evidence of slow execution cadence.
            gap_frame = prior[["timestamp", "day"]].copy()
            gap_frame["prev_ts"] = gap_frame.timestamp.shift()
            gap_frame["prev_day"] = gap_frame.day.shift()
            gaps = (gap_frame.loc[gap_frame.day.eq(gap_frame.prev_day), "timestamp"] -
                    gap_frame.loc[gap_frame.day.eq(gap_frame.prev_day), "prev_ts"]).dropna()
            if len(gaps):
                med_gap = float(gaps.median())
                fast5 = float((gaps <= 5).mean())
                fast30 = float((gaps <= 30).mean())
            else:
                med_gap = fast5 = fast30 = np.nan

        adequate = n >= MIN_PRIOR_TRANSACTIONS and games >= MIN_PRIOR_GAMES
        if not adequate:
            profile = "limited_prior_history"
        elif (per_day >= RAPID_TRANSACTIONS_PER_DAY and
              pd.notna(med_gap) and med_gap <= RAPID_MEDIAN_GAP_SECONDS):
            profile = "rapid_cycle_proxy"
        elif (med_ticket >= LARGE_MEDIAN_TICKET_USD and
              per_day <= LOW_FREQUENCY_TRANSACTIONS_PER_DAY):
            profile = "large_ticket_low_frequency_proxy"
        else:
            profile = "other_observed_style"
        result.append({
            "wallet": str(p.wallet), "game_id": str(p.game_id),
            "target_game_start_ts": int(p.target_game_start_ts),
            "prior_distinct_transactions": n, "prior_transaction_games": games,
            "prior_transaction_active_days": days,
            "prior_transactions_per_active_day": per_day,
            "prior_median_within_day_gap_seconds": med_gap,
            "prior_gap_share_le_5_seconds": fast5,
            "prior_gap_share_le_30_seconds": fast30,
            "prior_median_transaction_notional_usd": med_ticket,
            "prior_p90_transaction_notional_usd": p90_ticket,
            "execution_style_profile": profile,
        })
    return pd.DataFrame(result)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pairs, wallets = load_target_pairs()
    events = load_transaction_events(wallets)
    features = build_features(pairs, events)
    target = pd.read_parquet(TARGET)
    target["wallet"] = target.wallet.astype(str).str.lower()
    target["game_id"] = target.game_id.astype(str)
    target = target.merge(features, on=["wallet", "game_id", "target_game_start_ts"],
                          how="left", validate="many_to_one")
    if target.execution_style_profile.isna().any():
        raise ValueError("Some target records lack transaction-level execution-style features")
    target.to_parquet(OUT / "target_buys_with_execution_styles.parquet", index=False)
    features.to_csv(OUT / "wallet_game_execution_styles.csv", index=False)
    counts = target.groupby("execution_style_profile", observed=True).agg(
        records=("wallet", "size"), wallets=("wallet", "nunique"),
        games=("game_id", "nunique"),
        avg_transactions_per_day=("prior_transactions_per_active_day", "mean"),
        median_ticket_usd=("prior_median_transaction_notional_usd", "median"),
        median_gap_seconds=("prior_median_within_day_gap_seconds", "median"),
    ).reset_index()
    counts.to_csv(OUT / "execution_style_counts.csv", index=False)

    # Outcome-free sensitivity grid: these are descriptive reclassifications,
    # not alternative models selected by which one yields the largest gap.
    sensitivity = []
    for rate_cut in (5, 20, 60):
        for gap_cut in (5, 30, 60):
            for ticket_cut in (25, 100, 500):
                for low_rate in (1, 2, 5):
                    eligible = features.prior_distinct_transactions.ge(MIN_PRIOR_TRANSACTIONS) & features.prior_transaction_games.ge(MIN_PRIOR_GAMES)
                    rapid = eligible & features.prior_transactions_per_active_day.ge(rate_cut) & features.prior_median_within_day_gap_seconds.le(gap_cut)
                    large = eligible & ~rapid & features.prior_median_transaction_notional_usd.ge(ticket_cut) & features.prior_transactions_per_active_day.le(low_rate)
                    sensitivity.append({
                        "rapid_rate_cut_tx_per_active_day": rate_cut,
                        "rapid_median_gap_cut_seconds": gap_cut,
                        "large_median_ticket_cut_usd": ticket_cut,
                        "low_frequency_cut_tx_per_active_day": low_rate,
                        "eligible_wallet_game_pairs": int(eligible.sum()),
                        "rapid_wallet_game_pairs": int(rapid.sum()),
                        "large_low_frequency_wallet_game_pairs": int(large.sum()),
                        "other_eligible_wallet_game_pairs": int((eligible & ~rapid & ~large).sum()),
                        "limited_history_wallet_game_pairs": int((~eligible).sum()),
                    })
    pd.DataFrame(sensitivity).to_csv(OUT / "execution_style_threshold_sensitivity.csv", index=False)
    summary = {
        "sample": {"target_buy_records": int(len(target)),
                   "wallet_game_pairs": int(len(features)),
                   "target_wallets": int(target.wallet.nunique()),
                   "games": int(target.game_id.nunique()),
                   "prior_transaction_events": int(len(events))},
        "unit": "unique participant-wallet x transaction hash x NBA game after collapsing participant fill rows",
        "features": ["distinct prior transactions per active day",
                     "median and percentile transaction notional in USD",
                     "median within-active-day inter-transaction gap",
                     "shares of within-day gaps no longer than 5 or 30 seconds"],
        "classification": {
            "limited_prior_history": f"fewer than {MIN_PRIOR_TRANSACTIONS} distinct transactions or fewer than {MIN_PRIOR_GAMES} prior NBA games",
            "rapid_cycle_proxy": f"at least {RAPID_TRANSACTIONS_PER_DAY} transactions per active day and median within-day gap no more than {RAPID_MEDIAN_GAP_SECONDS} seconds",
            "large_ticket_low_frequency_proxy": f"median transaction notional at least ${LARGE_MEDIAN_TICKET_USD} and no more than {LOW_FREQUENCY_TRANSACTIONS_PER_DAY} transactions per active day, provided rapid-cycle rule does not apply",
            "other_observed_style": "adequate history not satisfying either proxy rule",
        },
        "timing": "Every feature uses records strictly before the target game's first ESPN play and excludes the target game entirely.",
        "limitations": [
            "Rapid-cycle behavior is not verified automation; fast human trading, market-making, smart contracts, or multiple fills within one transaction can produce similar patterns.",
            "Large-ticket/low-frequency behavior is not verified professional or retail status.",
            "Dollar transaction notional is aggregated over a wallet's participant fills within a transaction and can contain multiple fill legs.",
            "The extract covers assembled 2025-26 NBA-market activity only; off-platform activity and other markets are unobserved.",
            "Thresholds are researcher-defined and the outcome associations are exploratory; see the full threshold grid.",
            "The output target cohort consists of selected late-game longshot BUY records and is not representative of all account activity.",
        ],
        "profile_counts": counts.to_dict("records"),
    }
    (OUT / "execution_style_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
