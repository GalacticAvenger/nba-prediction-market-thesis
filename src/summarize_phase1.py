"""Recompute Phase 1 coverage, trade-quality, and candle-check summaries."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from common import ROOT


def main() -> None:
    interim = ROOT / "data" / "interim"
    metadata = pd.read_parquet(interim / "kalshi_market_metadata.parquet")
    market_meta = metadata.set_index("ticker")
    valid_tickers = set(metadata["ticker"])
    summary: dict = {"sample": {}, "trades": {}, "candles": {}, "pbp": {}, "candle_ask_check": {}}

    schedule = json.loads((interim / "espn_games.json").read_text(encoding="utf-8"))
    matched_events = json.loads((interim / "kalshi_event_match.json").read_text(encoding="utf-8"))
    for st in (2, 3):
        summary["sample"][f"schedule_type_{st}"] = sum(
            int(g["season"]) == 2026 and int(g["season_type"]) == st for g in schedule
        )
        selected = metadata[metadata.season_type == st]
        summary["sample"][f"windowed_markets_type_{st}"] = int(len(selected))
        summary["sample"][f"windowed_games_type_{st}"] = int(selected.game_id.nunique())
        summary["sample"][f"kalshi_matched_games_type_{st}"] = sum(
            int(event["season_type"]) == st for event in matched_events
        )

    counts_by_type: dict[int, list[np.ndarray]] = defaultdict(list)
    traded_games: dict[int, set[str]] = defaultdict(set)
    trade_stats: dict[int, Counter] = defaultdict(Counter)
    side_tuples: Counter = Counter()
    price_min, price_max = 1.0, 0.0
    trade_files = sorted((interim / "kalshi_trades").glob("*.parquet"))
    for path in trade_files:
        if path.stem not in valid_tickers:
            continue
        frame = pq.ParquetFile(path).read(columns=[
            "game_id", "trade_id", "ts_utc", "price", "count",
            "taker_side", "taker_outcome_side", "taker_book_side",
        ]).to_pandas()
        if frame.empty:
            continue
        st = int(market_meta.loc[path.stem, "season_type"])
        stats = trade_stats[st]
        stats["rows"] += len(frame)
        stats["markets_with_trades"] += 1
        traded_games[st].add(str(frame.game_id.iloc[0]))
        stats["timestamp_nunique_sum_by_market"] += int(frame.ts_utc.nunique())
        stats["timestamp_duplicate_rows_by_market"] += int(frame.ts_utc.duplicated().sum())
        stats["trade_id_duplicate_rows_by_market"] += int(frame.trade_id.duplicated().sum())
        values = frame["count"].to_numpy(dtype=np.float64)
        counts_by_type[st].append(values)
        stats["fractional_count_rows"] += int(np.count_nonzero(np.abs(values - np.rint(values)) > 1e-9))
        price_min = min(price_min, float(frame.price.min()))
        price_max = max(price_max, float(frame.price.max()))
        side_tuples.update(zip(
            frame.taker_side.fillna("NA"), frame.taker_outcome_side.fillna("NA"),
            frame.taker_book_side.fillna("NA"),
        ))

    for st in (2, 3):
        values = np.concatenate(counts_by_type[st]) if counts_by_type[st] else np.array([])
        trade_stats[st]["games_with_trades"] = len(traded_games[st])
        if len(values):
            trade_stats[st]["median_count"] = float(np.median(values))
            trade_stats[st]["count_q25"] = float(np.quantile(values, 0.25))
            trade_stats[st]["count_q75"] = float(np.quantile(values, 0.75))
        summary["trades"][f"season_type_{st}"] = dict(trade_stats[st])
    summary["trades"]["side_tuples"] = [
        {"taker_side": k[0], "taker_outcome_side": k[1], "taker_book_side": k[2], "rows": v}
        for k, v in sorted(side_tuples.items())
    ]
    summary["trades"]["price_min"] = price_min
    summary["trades"]["price_max"] = price_max
    summary["trades"]["unique_trade_partition_count"] = len(trade_files)

    for st in (2, 3):
        candle_rows = candle_markets = 0
        for path in (interim / "kalshi_candles_1m").glob("*.parquet"):
            if path.stem not in valid_tickers or int(market_meta.loc[path.stem, "season_type"]) != st:
                continue
            candle_markets += 1
            candle_rows += pq.ParquetFile(path).metadata.num_rows
        summary["candles"][f"season_type_{st}"] = {"markets": candle_markets, "rows": candle_rows}

    action_rows: Counter = Counter()
    wallclock_rows: Counter = Counter()
    wallclock_games: dict[int, set[str]] = defaultdict(set)
    timeout_types: dict[int, Counter] = defaultdict(Counter)
    for path in (interim / "espn_pbp").glob("season=2026/season_type=*/batch_*.parquet"):
        frame = pq.ParquetFile(path).read(columns=["game_id", "season_type", "action_type", "ts_wall_utc"]).to_pandas()
        if frame.empty:
            continue
        st = int(frame.season_type.iloc[0])
        action_rows[st] += len(frame)
        wallclock_rows[st] += int(frame.ts_wall_utc.notna().sum())
        wallclock_games[st].update(frame.loc[frame.ts_wall_utc.notna(), "game_id"].astype(str))
        timeout_frame = frame[frame.action_type.fillna("").str.contains("timeout", case=False)]
        timeout_types[st].update(timeout_frame.action_type.value_counts().to_dict())
    summary["pbp"]["actions_type_2"] = action_rows[2]
    summary["pbp"]["actions_type_3"] = action_rows[3]
    summary["pbp"]["wallclock_actions_type_2"] = wallclock_rows[2]
    summary["pbp"]["wallclock_actions_type_3"] = wallclock_rows[3]
    summary["pbp"]["games_with_wallclock_type_2"] = len(wallclock_games[2])
    summary["pbp"]["games_with_wallclock_type_3"] = len(wallclock_games[3])
    summary["pbp"]["timeout_types_type_2"] = dict(timeout_types[2])
    summary["pbp"]["timeout_types_type_3"] = dict(timeout_types[3])

    # Deterministic sample: 35 markets in SHA-256 ticker order and up to 100
    # trades per market, using pandas seed 11. Compare acquired-outcome price
    # to the corresponding one-minute candle ask OHLC range.
    sample_paths = sorted(
        [p for p in trade_files if p.stem in valid_tickers],
        key=lambda p: hashlib.sha256(p.stem.encode("utf-8")).hexdigest(),
    )[:35]
    distances: list[float] = []
    tuples_sample: Counter = Counter()
    for path in sample_paths:
        candle_path = interim / "kalshi_candles_1m" / f"{path.stem}.parquet"
        if not candle_path.exists():
            continue
        trades = pq.ParquetFile(path).read(columns=[
            "ts_utc", "price", "taker_side", "taker_outcome_side", "taker_book_side",
        ]).to_pandas()
        candles = pq.ParquetFile(candle_path).read().to_pandas().set_index("end_period_ts")
        if trades.empty or candles.empty:
            continue
        for _, trade in trades.sample(min(100, len(trades)), random_state=11).iterrows():
            ts = int(pd.Timestamp(trade.ts_utc).timestamp())
            candidate = candles.index[candles.index >= ts]
            if not len(candidate) or candidate[0] > ts + 60:
                continue
            quote = candles.loc[candidate[0]]
            try:
                yes_bid_low, yes_bid_high = float(quote.yes_bid["low"]), float(quote.yes_bid["high"])
                yes_ask_low, yes_ask_high = float(quote.yes_ask["low"]), float(quote.yes_ask["high"])
            except (TypeError, ValueError):
                continue
            outcome = trade.taker_outcome_side
            acquired_price = float(trade.price) if outcome == "yes" else 1 - float(trade.price)
            ask_low, ask_high = (yes_ask_low, yes_ask_high) if outcome == "yes" else (1 - yes_bid_high, 1 - yes_bid_low)
            bid_low, bid_high = (yes_bid_low, yes_bid_high) if outcome == "yes" else (1 - yes_ask_high, 1 - yes_ask_low)
            ask_distance = max(ask_low - acquired_price, 0.0, acquired_price - ask_high)
            bid_distance = max(bid_low - acquired_price, 0.0, acquired_price - bid_high)
            distances.append(ask_distance)
            tuples_sample[(trade.taker_side, trade.taker_outcome_side, trade.taker_book_side)] += 1
            # Keep a separate bid counter as the one-minute spread may be too
            # narrow for ask and bid ranges to distinguish in this sample.
            if bid_distance <= 0.011:
                summary["candle_ask_check"]["bid_within_1_1c"] = summary["candle_ask_check"].get("bid_within_1_1c", 0) + 1
    summary["candle_ask_check"].update({
        "markets_selected": len(sample_paths),
        "trades_matched": len(distances),
        "ask_within_1_1c": sum(distance <= 0.011 for distance in distances),
        "ask_within_1_1c_share": sum(distance <= 0.011 for distance in distances) / len(distances) if distances else None,
        "median_distance_to_ask_range": float(np.median(distances)) if distances else None,
        "sample_field_tuples": [
            {"taker_side": k[0], "taker_outcome_side": k[1], "taker_book_side": k[2], "rows": v}
            for k, v in sorted(tuples_sample.items())
        ],
    })

    destination = interim / "phase1_summary.json"
    destination.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(destination)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
