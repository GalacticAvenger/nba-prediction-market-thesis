"""Resumable, cached in-game Polymarket maker-fill ingest via the public Data API."""
from __future__ import annotations

import json
import argparse
import time
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path

import pandas as pd
import requests

from common import ROOT, write_json

MAP = ROOT / "data/interim/phase2/polymarket_nba_2025_26_market_map.json"
PBP_DIR = ROOT / "data/interim/espn_pbp/season=2026/season_type=2"
RAW = ROOT / "data/raw/polymarket/data_api_season"
OUT = ROOT / "data/interim/phase2"
BASE = "https://data-api.polymarket.com/trades"
PAGE = 1000
MAX_OFFSET = 9000


def row_key(r):
    return (str(r.get("transactionHash", "")).lower(),
            str(r.get("proxyWallet", "")).lower(), str(r.get("asset", "")),
            round(float(r.get("size", 0)), 10), round(float(r.get("price", 0)), 10))


def cached_get(session, slug, role, start, end, offset):
    path = RAW / slug / f"{role}_{start}_{end}_off{offset}.json"
    if path.exists():
        return json.loads(path.read_text())
    params = {"market": _MARKET[slug], "takerOnly": str(role == "taker").lower(),
              "start": start, "end": end, "limit": PAGE, "offset": offset}
    for attempt in range(10):
        response = session.get(BASE, params=params, timeout=90)
        if response.status_code == 429 or response.status_code >= 500:
            delay = response.headers.get("Retry-After")
            time.sleep(float(delay) if delay else min(90, 2 ** attempt))
            continue
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected Data API payload for {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, separators=(",", ":")))
        time.sleep(0.08)
        return data
    raise RuntimeError(f"Data API retry limit reached: {params}")


def fetch_interval(session, slug, role, start, end):
    rows = []
    for offset in range(0, MAX_OFFSET + 1, PAGE):
        page = cached_get(session, slug, role, start, end, offset)
        rows.extend(page)
        if len(page) < PAGE:
            return rows, 0
    # An exactly full final page means the interval may have been capped.
    if start == end:
        raise RuntimeError(f"one-second interval still saturated: {slug} {role} {start}")
    midpoint = (start + end) // 2
    left, dl = fetch_interval(session, slug, role, start, midpoint)
    right, dr = fetch_interval(session, slug, role, midpoint + 1, end)
    return left + right, dl + dr + len(rows)


def load_games():
    mapping = json.loads(MAP.read_text())
    markets = mapping["markets"]
    pbp = pd.concat([pd.read_parquet(p) for p in PBP_DIR.glob("*.parquet")],
                    ignore_index=True)
    pbp["game_id"] = pbp.game_id.astype(str)
    pbp["wall"] = pd.to_datetime(pbp.ts_wall_utc, utc=True, errors="coerce")
    bounds = pbp.dropna(subset=["wall"]).groupby("game_id").wall.agg(["min", "max"])
    rows = []
    for m in markets:
        gid = str(m["espn_game_id"])
        if gid not in bounds.index:
            continue
        # Bound collection to ESPN's wall-clock span of game play.
        start = int(bounds.loc[gid, "min"].timestamp())
        end = int(bounds.loc[gid, "max"].timestamp())
        event = m.get("gamma_event") or {}
        market = next((x for x in (event.get("markets") or [])
                       if str(x.get("conditionId", "")).lower() ==
                       str(m.get("condition_id", "")).lower()), None)
        if not market:
            continue
        rows.append({**m, "start_ts": start, "end_ts": end,
                     "outcomes": json.loads(market["outcomes"]),
                     "token_ids": json.loads(market["clobTokenIds"])})
    return rows, pbp


def collect_one(session, market):
    slug = market["slug"]
    _MARKET[slug] = market["condition_id"]
    both, both_splits = fetch_interval(session, slug, "both", market["start_ts"], market["end_ts"])
    taker, taker_splits = fetch_interval(session, slug, "taker", market["start_ts"], market["end_ts"])
    # The endpoint's false mode contains both sides. Apply the requested key-level
    # duplicate rule first, then subtract taker rows so calibration has makers only.
    unique = {}
    dup = 0
    for row in both:
        key = row_key(row)
        if key in unique:
            dup += 1
        else:
            unique[key] = row
    taker_counts = Counter(row_key(r) for r in taker)
    makers = []
    for key, row in unique.items():
        if taker_counts[key]:
            taker_counts[key] -= 1
        else:
            makers.append(row)
    taker_by_tx = {}
    for row in taker:
        tx = str(row.get("transactionHash", "")).lower()
        if tx and tx not in taker_by_tx:
            taker_by_tx[tx] = row
    for row in makers:
        taker_row = taker_by_tx.get(str(row.get("transactionHash", "")).lower(), {})
        row["takerWallet"] = taker_row.get("proxyWallet")
        row["takerSide"] = taker_row.get("side")
    return makers, taker, {"slug": slug, "both_rows": len(both), "unique_rows": len(unique),
                           "duplicate_rows_removed": dup, "taker_rows": len(taker),
                           "maker_rows": len(makers),
                           "maker_rows_missing_taker_identity": sum(not r.get("takerWallet") for r in makers),
                           "split_rows": both_splits + taker_splits}


_MARKET = {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nights", nargs="*", help="Eastern date keys for a benchmark subset")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    markets, pbp = load_games()
    if args.nights:
        selected = set(args.nights)
        markets = [m for m in markets if
                   pd.Timestamp(m["start_ts"], unit="s", tz="UTC").tz_convert("America/New_York").strftime("%Y-%m-%d") in selected]
    session = requests.Session()
    all_makers, all_takers, summaries = [], [], []
    manifest = ROOT / "data/interim/phase2/polymarket_data_api_progress.json"
    complete = {}
    if manifest.exists():
        complete = {x["slug"]: x for x in json.loads(manifest.read_text()).get("markets", [])}
    for i, market in enumerate(markets, 1):
        # Rebuild output deterministically from cached raw pages; no cached response
        # is downloaded again when a run resumes.
        began = time.time()
        makers, takers, summary = collect_one(session, market)
        summary.update({"espn_game_id": market["espn_game_id"],
                        "start_ts": market["start_ts"], "end_ts": market["end_ts"],
                        "duration_s": time.time() - began})
        complete[market["slug"]] = summary
        all_makers.extend({**r, "slug": market["slug"],
                           "espn_game_id": market["espn_game_id"]} for r in makers)
        all_takers.extend({**r, "slug": market["slug"],
                           "espn_game_id": market["espn_game_id"]} for r in takers)
        if i % 10 == 0 or i == len(markets):
            write_json(manifest, {"mapped_games_with_pbp": len(markets),
                                  "completed_markets": len(complete),
                                  "markets": list(complete.values())})
            print(f"{i}/{len(markets)} markets; makers={len(all_makers)}; "
                  f"elapsed={sum(x['duration_s'] for x in complete.values() if 'duration_s' in x):.0f}s",
                  flush=True)
    # Attach game-clock state by the last ESPN play at or before each fill.
    pbp = pbp.dropna(subset=["wall", "period", "clock_s_remaining"])
    columns = ["game_id", "wall", "period", "clock_s_remaining"]
    fills = pd.DataFrame(all_makers)
    if not fills.empty:
        fills["timestamp"] = pd.to_numeric(fills.timestamp, errors="coerce")
        fills["ts"] = pd.to_datetime(fills.timestamp, unit="s", utc=True)
        fills = fills.sort_values("ts")
        aligned = []
        for gid, part in fills.groupby("espn_game_id", sort=False):
            timeline = pbp[pbp.game_id.astype(str) == str(gid)][columns].sort_values("wall")
            if timeline.empty:
                part = part.copy()
                part["period"] = pd.NA
                part["clock_s_remaining"] = pd.NA
            else:
                part = pd.merge_asof(part.sort_values("ts"), timeline,
                                     left_on="ts", right_on="wall", direction="backward")
            aligned.append(part)
        fills = pd.concat(aligned, ignore_index=True) if aligned else fills
    fills.to_parquet(OUT / "polymarket_maker_fills_season_raw.parquet", index=False)
    pd.DataFrame(all_takers).to_parquet(OUT / "polymarket_taker_rows_season.parquet", index=False)
    write_json(manifest, {"mapped_games_with_pbp": len(markets),
                          "completed_markets": len(complete), "markets": list(complete.values())})
    print(f"complete {len(markets)} games, maker rows {len(all_makers)}")


if __name__ == "__main__":
    main()
