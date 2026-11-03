"""Resumable public Kalshi NBA game-market trades and one-minute candles."""
from __future__ import annotations

import argparse
import json
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

from common import RAW, ROOT, get_json, make_session, safe_name, write_json

BASE = "https://api.elections.kalshi.com/trade-api/v2"
NY = ZoneInfo("America/New_York")
EVENT_RE = re.compile(r"KXNBAGAME-(\d{2})([A-Z]{3})(\d{2})([A-Z]{6})")
ESPN_TO_KALSHI = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
                  "UTAH": "UTA", "WSH": "WAS"}


def event_date_and_teams(event_ticker: str) -> tuple[date | None, set[str]]:
    match = EVENT_RE.fullmatch(event_ticker)
    if not match:
        return None, set()
    year = 2000 + int(match.group(1))
    month = datetime.strptime(match.group(2), "%b").month
    code = match.group(4)
    return date(year, month, int(match.group(3))), {code[:3], code[3:]}


def fetch_all_markets(session: requests.Session) -> list[dict[str, Any]]:
    markets, cursor, page = [], "", 0
    while True:
        params = {"series_ticker": "KXNBAGAME", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        url = requests.Request("GET", f"{BASE}/historical/markets", params=params).prepare().url
        cache = RAW / "kalshi" / "markets" / "historical" / f"page_{page:04d}.json"
        payload = get_json(session, url, cache, min_interval=0.12)
        markets.extend(payload.get("markets", []))
        cursor = payload.get("cursor", "")
        page += 1
        if not cursor:
            break
    return markets


def load_schedule() -> dict[tuple[date, frozenset[str]], dict[str, Any]]:
    path = ROOT / "data" / "interim" / "espn_games.json"
    if not path.exists():
        raise FileNotFoundError("Run `python src/ingest_pbp.py --schedule-only --seasons 2026` first.")
    index = {}
    for game in json.loads(path.read_text(encoding="utf-8")):
        dt = datetime.fromisoformat(game["event_date_utc"].replace("Z", "+00:00")).astimezone(NY)
        teams = frozenset(ESPN_TO_KALSHI.get(x, x) for x in
                          (game["home_abbreviation"], game["away_abbreviation"]))
        index[(dt.date(), teams)] = game
    return index


def classify_markets(markets: list[dict[str, Any]], schedule: dict[tuple[date, frozenset[str]], dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for market in markets:
        grouped[market["event_ticker"]].append(market)
    matched, unmatched = [], []
    for ticker, rows in grouped.items():
        day, teams = event_date_and_teams(ticker)
        game = schedule.get((day, frozenset(teams))) if day else None
        record = {"event_ticker": ticker, "event_date": day.isoformat() if day else None,
                  "markets": rows, "market_count": len(rows), "team_codes": sorted(teams)}
        if game:
            record["game"] = game
            record["season_type"] = game["season_type"]
            matched.append(record)
        else:
            unmatched.append(record)
    return matched, unmatched


def fetch_trades(session: requests.Session, ticker: str, min_ts: int, max_ts: int) -> list[dict[str, Any]]:
    # Request only the ESPN-observed game window; the API supports unix min_ts/max_ts.
    trades, cursor, page = [], "", 0
    while True:
        params = {"ticker": ticker, "min_ts": min_ts, "max_ts": max_ts,
                  "is_block_trade": "false", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        url = requests.Request("GET", f"{BASE}/historical/trades", params=params).prepare().url
        cache = RAW / "kalshi" / "trades" / safe_name(ticker) / f"inplay_{min_ts}_{max_ts}" / f"page_{page:05d}.json"
        payload = get_json(session, url, cache, min_interval=0.10)
        trades.extend(payload.get("trades", []))
        cursor = payload.get("cursor", "")
        page += 1
        if not cursor:
            break
    return trades


def fetch_candles(session: requests.Session, market: dict[str, Any], min_ts: int, max_ts: int) -> list[dict[str, Any]]:
    ticker = market["ticker"]
    args = f"start_ts={min_ts}&end_ts={max_ts}&period_interval=1"
    url = f"{BASE}/historical/markets/{ticker}/candlesticks?{args}"
    cache = RAW / "kalshi" / "candles_1m" / f"{safe_name(ticker)}.json"
    try:
        payload = get_json(session, url, cache, min_interval=0.10)
    except requests.HTTPError:
        # Markets not yet moved into the archive are served by the current-market route.
        url = f"{BASE}/series/KXNBAGAME/markets/{ticker}/candlesticks?{args}"
        payload = get_json(session, url, cache, min_interval=0.10)
    return payload.get("candlesticks", [])


def normalize_trade(trade: dict[str, Any], market: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    dt = datetime.fromisoformat(trade["created_time"].replace("Z", "+00:00"))
    game = event["game"]
    return {
        "game_id": game["espn_game_id"], "event_ticker": event["event_ticker"],
        "market_ticker": trade.get("ticker", market["ticker"]), "trade_id": trade.get("trade_id"),
        "ts_utc": dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "price": float(trade["yes_price_dollars"]), "count": float(trade.get("count_fp", 0)),
        "taker_side": trade.get("taker_side"), "taker_outcome_side": trade.get("taker_outcome_side"),
        "taker_book_side": trade.get("taker_book_side"),
        "is_block_trade": bool(trade.get("is_block_trade", False)),
        "settlement_result": market.get("result"),
        "settlement_value_dollars": market.get("settlement_value_dollars"),
        "yes_sub_title": market.get("yes_sub_title"), "no_sub_title": market.get("no_sub_title"),
        "season": game["season"], "season_type": game["season_type"],
    }


def write_partition(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path, compression="zstd")


_local = threading.local()


def worker_session() -> requests.Session:
    if not hasattr(_local, "session"):
        _local.session = make_session()
    return _local.session


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-candles", action="store_true")
    parser.add_argument("--max-markets", type=int, help="diagnostic subset only")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    session = make_session()
    markets = fetch_all_markets(session)
    schedule = load_schedule()
    matched, unmatched = classify_markets(markets, schedule)
    selected = [e for e in matched if e["game"]["season"] == 2026 and e["game"]["season_type"] in (2, 3)]
    if args.max_markets:
        selected = selected[:args.max_markets]
    output = ROOT / "data" / "interim"
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "kalshi_event_match.json", [{k: v for k, v in e.items() if k != "markets"} for e in selected])
    write_json(output / "kalshi_unmatched_events.json", [{k: v for k, v in e.items() if k != "markets"} for e in unmatched])
    metadata, all_candle_count, all_trade_count = [], 0, 0
    trades_dir = output / "kalshi_trades"
    candles_dir = output / "kalshi_candles_1m"
    raw_markets = [m for event in selected for m in event["markets"]]
    event_map = {event["event_ticker"]: event for event in selected}
    # ESPN wall clocks identify each game's observed action interval. Pad by two
    # minutes for API retrieval, then retain only trades between first and last play.
    windows = {}
    for event in selected:
        gid = event["game"]["espn_game_id"]
        raw_summary = ROOT / "data" / "raw" / "espn" / "summaries" / f"{gid}.json"
        if not raw_summary.exists():
            continue
        payload = json.loads(raw_summary.read_text(encoding="utf-8"))
        stamps = []
        for play in payload.get("plays", []):
            value = play.get("wallclock")
            if value:
                try:
                    stamps.append(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
                except ValueError:
                    pass
        if stamps:
            windows[gid] = (int(min(stamps)), int(max(stamps)))
    def process_market(market: dict[str, Any]) -> tuple[dict[str, Any] | None, int, int]:
        event = event_map[market["event_ticker"]]
        window = windows.get(event["game"]["espn_game_id"])
        if window is None:
            return None, 0, 0
        start_ts, end_ts = window
        current_session = worker_session()
        trades = fetch_trades(current_session, market["ticker"], start_ts - 120, end_ts + 120)
        clean = [normalize_trade(t, market, event) for t in trades if not t.get("is_block_trade", False)]
        clean = [t for t in clean if start_ts <= datetime.fromisoformat(t["ts_utc"].replace("Z", "+00:00")).timestamp() <= end_ts]
        partition_path = trades_dir / f"{safe_name(market['ticker'])}.parquet"
        if clean:
            write_partition(clean, partition_path)
        elif partition_path.exists():
            partition_path.unlink()
        candle_count = 0
        fields = ["ticker", "event_ticker", "title", "subtitle", "yes_sub_title", "no_sub_title",
                  "created_time", "open_time", "close_time", "occurrence_datetime", "result",
                  "settlement_value_dollars", "settlement_ts", "volume_fp", "fee_type_override", "fee_multiplier_override"]
        if not args.skip_candles:
            market_candles = [{"ticker": market["ticker"], **c} for c in fetch_candles(current_session, market, start_ts - 60, end_ts + 60)]
            write_partition(market_candles, candles_dir / f"{safe_name(market['ticker'])}.parquet")
            candle_count = len(market_candles)
        record = {**{k: market.get(k) for k in fields}, "game_id": event["game"]["espn_game_id"],
                  "season": event["game"]["season"], "season_type": event["game"]["season_type"]}
        return record, len(clean), candle_count

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(process_market, m) for m in raw_markets]
        for i, future in enumerate(as_completed(futures), 1):
            record, trade_count, candle_count = future.result()
            if record is not None:
                metadata.append(record)
            all_trade_count += trade_count
            all_candle_count += candle_count
            if i % 25 == 0 or i == len(raw_markets):
                print(f"Kalshi markets {i}/{len(raw_markets)}; non-block in-play trades={all_trade_count}; candles={all_candle_count}", flush=True)
    pd.DataFrame(metadata).to_parquet(output / "kalshi_market_metadata.parquet", index=False)
    print(f"Historical market objects={len(markets)}; matched={len(matched)}; selected={len(selected)}; unmatched={len(unmatched)}")
    print(f"Ingested markets={len(metadata)}; non-block trade rows={all_trade_count}; candles={all_candle_count}")


if __name__ == "__main__":
    main()
