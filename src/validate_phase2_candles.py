"""Compare a deterministic trade sample with same-minute Kalshi candle closes."""
from __future__ import annotations

import hashlib
import json
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from common import ROOT


def close_value(value):
    return value.get("close") if isinstance(value, dict) else value


def main():
    trades = glob.glob(str(ROOT / "data/interim/kalshi_trades/*.parquet"))
    observations = []
    for path in trades:
        ticker = Path(path).stem
        try:
            frame = pd.read_parquet(path, columns=["ts_utc", "price", "taker_outcome_side", "is_block_trade"])
            candles = pd.read_parquet(ROOT / "data/interim/kalshi_candles_1m" / f"{ticker}.parquet",
                                     columns=["end_period_ts", "yes_ask", "yes_bid"])
        except FileNotFoundError:
            continue
        if frame.empty:
            continue
        seed = int(hashlib.sha256(path.encode()).hexdigest()[:8], 16)
        frame = frame.sample(n=min(100, len(frame)), random_state=seed)
        candles["ask_close"] = pd.to_numeric(candles.yes_ask.map(close_value), errors="coerce")
        candles["bid_close"] = pd.to_numeric(candles.yes_bid.map(close_value), errors="coerce")
        candles = candles.dropna(subset=["ask_close", "bid_close"])
        if candles.empty:
            continue
        seconds = pd.to_datetime(frame.ts_utc, utc=True, format="mixed").astype("int64") // 1_000_000_000
        frame["end_period_ts"] = (seconds // 60 + 1) * 60
        frame = frame.merge(candles[["end_period_ts", "ask_close", "bid_close"]], on="end_period_ts", how="inner")
        for row in frame.itertuples():
            if bool(row.is_block_trade):
                continue
            quote = row.ask_close if row.taker_outcome_side == "yes" else row.bid_close
            observations.append((row.taker_outcome_side, abs(float(row.price) - float(quote))))
    distances = np.asarray([x[1] for x in observations], dtype=float)
    result = {
        "method": "up to 100 trades per market, deterministic SHA-256 seed; compare YES taker to same-minute yes_ask.close and NO taker to yes_bid.close; blocks excluded",
        "matched_trade_candle_observations": len(observations),
        "yes_taker_observations": sum(x[0] == "yes" for x in observations),
        "no_taker_observations": sum(x[0] == "no" for x in observations),
        "median_absolute_distance": float(np.median(distances)) if len(distances) else None,
        "within_1_cent_share": float((distances <= .01 + 1e-9).mean()) if len(distances) else None,
        "within_2_cent_share": float((distances <= .02 + 1e-9).mean()) if len(distances) else None,
    }
    output = ROOT / "data/interim/phase2/kalshi_candle_close_check.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
