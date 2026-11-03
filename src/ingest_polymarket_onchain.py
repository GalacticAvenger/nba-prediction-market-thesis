"""Enumerate 2025-26 NBA regular-season Polymarket markets and cache exchange logs.

Raw Gamma pages and RPC log pages are immutable cache entries. Re-running resumes
at the first missing page/event. Set POLYGON_RPC_URL to choose a Polygon JSON-RPC.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from common import ROOT, make_session, write_json

RAW = ROOT / "data/raw/polymarket"
INTERIM = ROOT / "data/interim/phase2"
GAMMA = "https://gamma-api.polymarket.com/events"
RPC = os.getenv("POLYGON_RPC_URL", "https://polygon-bor-rpc.publicnode.com")
SEASON = 2026
SERIES_ID = "10345"
V1 = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"
V2 = "0xe111180000d2663c0091e4f400237545b87b996b"
# CTF Exchange V1 event topics. V2's compact event format uses a distinct topic.
TOPICS = {
    "order_filled_v1": "0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6",
    "orders_matched_v1": "0x63bf4d16b7fa898ef4c4b2b6d90fd201e9c56313b65638af6088d149d2ce956c",
    "order_filled_v2": "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee",
    "orders_matched_v2": "0x174b3811690657c217184f89418266767c87e4805d09680c39fc9c031c0cab7c",
}
TEAM_ALIASES = {
    "GS": "gsw", "NO": "nop", "NY": "nyk", "SA": "sas", "WSH": "was",
    "UTAH": "uta", "PHO": "phx", "PHX": "phx", "BRK": "bkn",
}


def rpc(session, method, params):
    for attempt in range(8):
        try:
            response = session.post(RPC, json={"jsonrpc": "2.0", "id": 1,
                                                "method": method, "params": params}, timeout=60)
            response.raise_for_status()
            obj = response.json()
            if "error" in obj:
                raise RuntimeError(obj["error"])
            return obj["result"]
        except Exception:
            if attempt == 7:
                raise
            time.sleep(min(30, 2 ** attempt))


def gamma_events(session):
    all_events = []
    offset = 0
    while True:
        path = RAW / f"gamma_nba_series_{SERIES_ID}_offset{offset}.json"
        if path.exists():
            rows = json.loads(path.read_text())
        else:
            response = session.get(GAMMA, params={"series_id": SERIES_ID, "limit": 100,
                                                  "offset": offset, "order": "startDate",
                                                  "ascending": "true"}, timeout=60)
            response.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            rows = response.json()
        if not rows:
            break
        all_events.extend(rows)
        if len(rows) < 100:
            break
        offset += len(rows)
    return all_events


def season_games():
    games = pd.read_parquet(ROOT / "data/interim/espn_games.parquet")
    games = games[(games.season == SEASON) & (games.season_type == 2)].copy()
    fixture = json.loads((INTERIM / "sample_fixtures.json").read_text())
    excluded = set(map(str, fixture.get("drop_ids", [])))
    games = games[~games.espn_game_id.astype(str).isin(excluded)]
    return games


def event_slug(game):
    a = TEAM_ALIASES.get(game.away_abbreviation, game.away_abbreviation.lower())
    h = TEAM_ALIASES.get(game.home_abbreviation, game.home_abbreviation.lower())
    date = pd.Timestamp(game.event_date_utc).tz_convert("America/New_York").strftime("%Y-%m-%d")
    return f"nba-{a}-{h}-{date}"


def map_markets(events, games):
    lookup = {event_slug(row): row for row in games.itertuples(index=False)}
    mapped = []
    for event in events:
        slug = event.get("slug", "")
        game = lookup.get(slug)
        if game is None:
            continue
        markets = event.get("markets") or []
        market = next((m for m in markets if m.get("clobTokenIds")), None)
        if not market:
            continue
        try:
            token_ids = json.loads(market["clobTokenIds"])
        except (TypeError, json.JSONDecodeError):
            continue
        if len(token_ids) != 2:
            continue
        mapped.append({"slug": slug, "espn_game_id": str(game.espn_game_id),
                       "event_date_utc": game.event_date_utc,
                       "away_team": game.away_abbreviation, "home_team": game.home_abbreviation,
                       "market_id": str(market.get("id", "")),
                       "condition_id": market.get("conditionId"), "token_ids": token_ids,
                       "game_start_time": market.get("gameStartTime") or event.get("startTime"),
                       "gamma_event": event})
    return mapped


_pbp_by_game = None


def game_time_bounds(game_id, market):
    """Use already cached ESPN wall-clock play records as read-only timing bounds."""
    global _pbp_by_game
    if _pbp_by_game is None:
        paths = list((ROOT / "data/interim/espn_pbp/season=2026/season_type=2").glob("*.parquet"))
        frames = [pd.read_parquet(p, columns=["game_id", "ts_wall_utc"]) for p in paths]
        data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        data = data.dropna(subset=["ts_wall_utc"])
        data["ts_epoch"] = pd.to_datetime(data.ts_wall_utc, utc=True).astype("int64") // 10**9
        _pbp_by_game = data.groupby(data.game_id.astype(str)).ts_epoch.agg(["min", "max"])
    data = _pbp_by_game.loc[str(game_id)] if str(game_id) in _pbp_by_game.index else None
    if data is not None:
        return int(data["min"]) - 60, int(data["max"]) + 60
    start = pd.to_datetime(market.get("game_start_time"), utc=True)
    return int(start.timestamp()) - 60, int(start.timestamp()) + 4 * 3600


def block_at(session, timestamp, cache):
    key = str(timestamp)
    if key not in cache:
        cache[key] = int(rpc(session, "eth_getBlockByNumber", ["latest", False])["number"], 16)
        # Find the first block whose timestamp is at least the requested second.
        lo, hi = 0, cache[key]
        while lo < hi:
            mid = (lo + hi) // 2
            b = rpc(session, "eth_getBlockByNumber", [hex(mid), False])
            if int(b["timestamp"], 16) < timestamp:
                lo = mid + 1
            else:
                hi = mid
        cache[key] = lo
        write_json(RAW / "block_timestamp_index.json", cache)
    return cache[key]


def collect_logs(session, market, start_ts, end_ts, block_cache):
    start_block, end_block = block_at(session, start_ts, block_cache), block_at(session, end_ts, block_cache)
    directory = RAW / "onchain_logs" / market["slug"]
    directory.mkdir(parents=True, exist_ok=True)
    # Small ranges keep public Polygon RPC providers below eth_getLogs range limits.
    logs = []
    for exchange, topics in ((V1, [TOPICS["order_filled_v1"], TOPICS["orders_matched_v1"]]),
                             (V2, [TOPICS["order_filled_v2"], TOPICS["orders_matched_v2"]])):
        for first in range(start_block, end_block + 1, 500):
            last = min(end_block, first + 499)
            path = directory / f"{exchange}_{first}_{last}.json"
            if path.exists():
                continue
            result = rpc(session, "eth_getLogs", [{"address": exchange, "fromBlock": hex(first),
                                                    "toBlock": hex(last), "topics": [topics]}])
            # One raw response per bounded block range is the resume checkpoint.
            write_json(path, result)
    token_set = {str(t) for t in market["token_ids"]}
    return {"market": market["slug"], "from_block": start_block, "to_block": end_block,
            "token_ids": sorted(token_set), "logs_cached": True}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    session = make_session()
    events = gamma_events(session)
    games = season_games()
    markets = map_markets(events, games)
    mapped_ids = {m["espn_game_id"] for m in markets}
    unmatched = [{"espn_game_id": str(r.espn_game_id), "event_name": r.event_name,
                 "event_date_utc": r.event_date_utc, "gamma_slug": event_slug(r)}
                for r in games.itertuples(index=False) if str(r.espn_game_id) not in mapped_ids]
    write_json(INTERIM / "polymarket_nba_2025_26_market_map.json", {
        "gamma_events_seen": len(events), "espn_regular_season_games": len(games),
        "mapped_markets": len(markets), "unmatched_espn_games": unmatched,
        "markets": markets})
    cache_file = RAW / "block_timestamp_index.json"
    block_cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    for idx, market in enumerate(markets, 1):
        start_ts, end_ts = game_time_bounds(market["espn_game_id"], market)
        collect_logs(session, market, start_ts, end_ts, block_cache)
        if idx % 25 == 0:
            print(f"cached exchange logs for {idx}/{len(markets)} markets", flush=True)
    print(f"Mapped {len(markets)} markets from {len(events)} Gamma events to {len(games)} ESPN games")


if __name__ == "__main__":
    main()
