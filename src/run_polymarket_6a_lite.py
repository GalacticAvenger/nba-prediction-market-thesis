"""Game-clock 6a-lite diagnostic for the fully receipt-cached Oct. 21 test market."""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import ROOT, write_json
from game_windows import is_final_regulation_window, is_overtime

RAW = ROOT / "data/raw/polymarket"
OUT = ROOT / "data/interim/phase2"
FILLED_V1 = "0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6"
MATCHED_V1 = "0x63bf4d16b7fa898ef4c4b2b6d90fd201e9c56313b65638af6088d149d2ce956c"
EXCHANGE = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"


def main():
    data_api = []
    for path in glob.glob(str(RAW / "trades_nba-hou-okc-2025-10-21_offset*.json")):
        obj = json.loads(Path(path).read_text())
        if isinstance(obj, list):
            data_api.extend(obj)
    api = pd.DataFrame(data_api).drop_duplicates(
        ["transactionHash", "proxyWallet", "asset", "size", "price", "timestamp"])
    token_outcomes = dict(zip(api.asset.astype(str), api.outcome))
    pbp_paths = glob.glob(str(ROOT / "data/interim/espn_pbp/season=2026/season_type=2/*.parquet"))
    pbp = pd.concat([pd.read_parquet(p) for p in pbp_paths], ignore_index=True)
    pbp = pbp[pbp.game_id.astype(str) == "401809243"].dropna(subset=["ts_wall_utc"]).copy()
    pbp["ts"] = pd.to_datetime(pbp.ts_wall_utc, utc=True)
    pbp = pbp.sort_values("ts")
    timeline = pbp.dropna(subset=["clock_s_remaining", "period"])[["ts", "period", "clock_s_remaining"]].copy()
    api_rows = {str(r.transactionHash).lower(): r
                for r in api.sort_values("timestamp").itertuples(index=False)}
    txs = set(api_rows)
    receipts = {}
    for path in glob.glob(str(RAW / "onchain_receipts/batch_*.json")):
        for item in json.loads(Path(path).read_text()):
            rec = item.get("result") or {}
            tx = rec.get("transactionHash", "").lower()
            if tx in txs:
                receipts[tx] = rec
    fills = []
    for tx, receipt in receipts.items():
        taker_wallet = None
        for log in receipt.get("logs", []):
            topics = log.get("topics") or []
            if len(topics) > 2 and topics[0].lower() == MATCHED_V1:
                taker_wallet = "0x" + topics[2][-40:].lower()
                break
        if not taker_wallet:
            continue
        ts = pd.to_datetime(int(api_rows[tx].timestamp), unit="s", utc=True)
        for log in receipt.get("logs", []):
            topics = log.get("topics") or []
            if (log.get("address", "").lower() != EXCHANGE or len(topics) < 4
                    or topics[0].lower() != FILLED_V1
                    or "0x" + topics[3][-40:].lower() == EXCHANGE):
                continue
            words = [int(log["data"][2 + 64*i:2 + 64*(i+1)], 16) for i in range(5)]
            maker_asset, taker_asset, maker_amount, taker_amount, _fee = words
            if maker_asset:
                token, shares, cash, maker_side = maker_asset, maker_amount, taker_amount, "SELL"
            else:
                token, shares, cash, maker_side = taker_asset, taker_amount, maker_amount, "BUY"
            token = str(token)
            if token not in token_outcomes or shares == 0:
                continue
            fills.append({"transaction_hash": tx, "log_index": int(log["logIndex"], 16),
                          "ts": ts, "token": token, "outcome": token_outcomes[token],
                          "maker": "0x" + topics[2][-40:].lower(), "taker": taker_wallet,
                          "maker_side": maker_side, "price": cash / shares,
                          "size": shares / 1e6})
    f = pd.DataFrame(fills)
    f = pd.merge_asof(f.sort_values("ts"), timeline.sort_values("ts"), on="ts", direction="backward")
    f.to_csv(OUT / "polymarket_oct21_onchain_maker_fills.csv", index=False)
    late_mask = [is_final_regulation_window(p, c, 10)
                 for p, c in zip(f.period, f.clock_s_remaining)]
    ot_mask = [is_overtime(p) for p in f.period]
    late = f[late_mask].copy()
    # The ESPN final score identifies Oklahoma City as the winner in this fixture.
    late["y"] = (late.outcome == "Thunder").astype(int)
    bins = np.arange(0.0, 1.0001, 0.05)
    late["price_bin"] = pd.cut(late.price, bins, right=False, include_lowest=True)
    summary = (late.groupby("price_bin", observed=False)
               .agg(fills=("price", "size"), mean_price=("price", "mean"),
                    realized_win_rate=("y", "mean"))
               .dropna().reset_index())
    summary["price_bin"] = summary.price_bin.astype(str)
    result = {
        "sample": "single validation market only; not the season-wide 6a-lite estimate",
        "market": "nba-hou-okc-2025-10-21", "espn_game_id": "401809243",
        "definition": "shared is_final_regulation_window(period, clock_s_remaining, 10); overtime reported separately",
        "max_period": int(pbp.period.max()), "overtime_maker_fills_separate": int(sum(ot_mask)),
        "maker_orderfilled_fills_in_receipts": int(len(f)),
        "maker_fills_in_final_10_game_minutes": int(len(late)),
        "final_10_game_minutes_taker_sell_fills": int((late.maker_side == "BUY").sum()),
        "price_bin_rows": summary.to_dict(orient="records"),
        "fit": "not estimated from one game: a game-level realized outcome cannot identify a season calibration curve",
    }
    write_json(OUT / "polymarket_6a_lite_gameclock.json", result)
    summary.to_csv(OUT / "polymarket_6a_lite_gameclock_bins.csv", index=False)
    print(json.dumps({k: v for k, v in result.items() if k != "price_bin_rows"}, indent=2))


if __name__ == "__main__":
    main()
