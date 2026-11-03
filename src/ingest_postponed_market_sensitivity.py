"""Fetch one omitted postponed-market history as an isolated sensitivity.

The Jan. 24 GSW–MIN contract says it resolves on the game originally scheduled
for that date. ESPN records that postponed game under the completed Jan. 25
game ID 401857824. This script stores only sidecar inputs; it does not alter
the canonical matched-market sample.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from common import ROOT, RAW, make_session, safe_name, write_json
from ingest_kalshi import fetch_trades, fetch_candles, normalize_trade

EVENT_TICKER = "KXNBAGAME-26JAN24GSWMIN"
GAME_ID = "401857824"
OUT = ROOT / "data/interim/phase4_postponed_market_sensitivity"


def main() -> None:
    market_rows = []
    for path in (RAW / "kalshi/markets/historical").glob("*.json"):
        payload = json.loads(path.read_text())
        market_rows.extend(m for m in payload.get("markets", [])
                           if m.get("event_ticker") == EVENT_TICKER)
    if len(market_rows) != 2:
        raise ValueError(f"Expected two contract records for {EVENT_TICKER}; found {len(market_rows)}")

    game = pd.read_parquet(ROOT / "data/interim/espn_games.parquet")
    g = game.loc[game.espn_game_id.astype(str).eq(GAME_ID)].iloc[0].to_dict()
    summary_path = RAW / f"espn/summaries/{GAME_ID}.json"
    summary = json.loads(summary_path.read_text())
    stamps = [datetime.fromisoformat(p["wallclock"].replace("Z", "+00:00")).timestamp()
              for p in summary.get("plays", []) if p.get("wallclock")]
    if not stamps:
        raise ValueError("Completed-game ESPN summary has no wall-clock play timestamps")
    start, end = min(stamps), max(stamps)
    event = {"event_ticker": EVENT_TICKER, "event_date": "2026-01-24",
             "game": {"espn_game_id": GAME_ID, "event_date_utc": g["event_date_utc"],
                      "event_name": g["event_name"], "season": 2026, "season_type": 2,
                      "home_team_id": str(g["home_team_id"]), "home_abbreviation": g["home_abbreviation"],
                      "home_team": g["home_team"], "away_team_id": str(g["away_team_id"]),
                      "away_abbreviation": g["away_abbreviation"], "away_team": g["away_team"],
                      "status": g["status"]}, "season_type": 2}
    session = make_session()
    metadata, trade_manifest = [], []
    trade_dir = OUT / "kalshi_trades"
    candle_dir = OUT / "kalshi_candles_1m"
    for market in market_rows:
        ticker = market["ticker"]
        trades = fetch_trades(session, ticker, int(start) - 120, int(end) + 120)
        clean = [normalize_trade(t, market, event) for t in trades
                 if not t.get("is_block_trade", False)
                 and start <= datetime.fromisoformat(t["created_time"].replace("Z", "+00:00")).timestamp() <= end]
        p = trade_dir / f"{safe_name(ticker)}.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(clean), p, compression="zstd")
        candle_rows = [{"ticker": ticker, **c} for c in
                       fetch_candles(session, market, int(start) - 60, int(end) + 60)]
        cp = candle_dir / f"{safe_name(ticker)}.parquet"
        cp.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(candle_rows), cp, compression="zstd")
        metadata.append({**{k: market.get(k) for k in (
            "ticker", "event_ticker", "title", "subtitle", "yes_sub_title", "no_sub_title",
            "created_time", "open_time", "close_time", "occurrence_datetime", "result",
            "settlement_value_dollars", "settlement_ts", "volume_fp", "fee_type_override",
            "fee_multiplier_override")}, "game_id": GAME_ID, "season": 2026, "season_type": 2})
        trade_manifest.append({"ticker": ticker, "raw_api_rows": len(trades),
                               "in_game_nonblock_rows": len(clean), "candle_rows": len(candle_rows),
                               "in_game_start_utc": datetime.fromtimestamp(start, timezone.utc).isoformat(),
                               "in_game_end_utc": datetime.fromtimestamp(end, timezone.utc).isoformat(),
                               "market_close_time": market.get("close_time"),
                               "market_result": market.get("result"), "market_rules": market.get("rules_primary")})
    pd.DataFrame(metadata).to_parquet(OUT / "kalshi_market_metadata.parquet", index=False)
    write_json(OUT / "ingest_manifest.json", {
        "event_ticker": EVENT_TICKER, "original_scheduled_date": "2026-01-24",
        "completed_game_id": GAME_ID, "reason": "ESPN schedule/PBP identifies the rescheduled fixture; Kalshi rules name the Jan. 24 scheduled game and settlement follows the Jan. 25 completion.",
        "market_records": trade_manifest,
        "scope": "isolated sensitivity inputs; canonical Phase 1/Phase 4 data are not overwritten"})
    print(json.dumps(trade_manifest, indent=2))


if __name__ == "__main__":
    main()
