"""Close-time NBA window check for March 1--May 15, 2026.

Uses the same Kalshi market-YES coordinate and calibration/Prelec routines as
phase5a.py. The thesis draft is not read or modified.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from common import ROOT, RAW, get_json, make_session, safe_name
from ingest_kalshi import BASE
from phase5a import summarize, pbp_last


META = ROOT / "data/interim/kalshi_market_metadata.parquet"
TRADES = ROOT / "data/interim/kalshi_trades"
OUT = ROOT / "data/interim/phase5/close_time_window_march_midmay_2026.json"
POST_FILE = ROOT / "data/interim/phase5/post_game_trades/post_game_trades.parquet"
START = pd.Timestamp("2026-03-01")
END_EXCLUSIVE = pd.Timestamp("2026-05-16")
BOOTSTRAP_DRAWS = 2_000
SEED = 5132026


def fetch_postclose_candidate_rows(market: pd.Series) -> list[dict]:
    """Fetch post-final-play trades through market close, using cached API pages."""
    start = pd.Timestamp(market["last_espn_play"])
    close = pd.Timestamp(market["close"])
    if close <= start:
        return []
    lo, hi = int(start.timestamp()), int(close.timestamp())
    rows: list[dict] = []
    cursor = ""
    page = 0
    session = make_session()
    while True:
        params = {
            "ticker": market["ticker"], "min_ts": lo, "max_ts": hi,
            "is_block_trade": "false", "limit": 1000,
        }
        if cursor:
            params["cursor"] = cursor
        url = requests.Request(
            "GET", f"{BASE}/historical/trades", params=params
        ).prepare().url
        cache = (
            RAW / "kalshi" / "trades_postgame" / safe_name(market["ticker"])
            / f"{lo}_{hi}" / f"page_{page:05d}.json"
        )
        payload = get_json(session, url, cache, min_interval=0.12)
        for trade in payload.get("trades", []):
            rows.append({
                "game_id": str(market["game_id"]),
                "market_ticker": market["ticker"],
                "trade_id": trade.get("trade_id"),
                "ts": pd.to_datetime(trade.get("created_time"), utc=True, errors="coerce", format="mixed"),
                "price": pd.to_numeric(trade.get("yes_price_dollars"), errors="coerce"),
                "is_block_trade": bool(trade.get("is_block_trade", False)),
                "y": int(market["result"] == "yes"),
                "last_espn_play": start,
            })
        cursor = payload.get("cursor", "")
        page += 1
        if not cursor:
            break
    return rows


def ticker_game_date(ticker: str) -> pd.Timestamp | pd.NaT:
    """Extract the scheduled NBA game date from KXNBAGAME-YYMMMDD..."""
    match = re.search(r"KXNBAGAME-(\d{2})([A-Z]{3})(\d{2})", str(ticker))
    if not match:
        return pd.NaT
    yy, mon, day = match.groups()
    return pd.to_datetime(f"20{yy}-{mon}-{day}", format="%Y-%b-%d", errors="coerce")


def game_cluster_bootstrap_mean(frame: pd.DataFrame) -> dict:
    """Pooled trade-row mean with a percentile game-cluster bootstrap CI."""
    d = frame.dropna(subset=["game_id", "A"]).copy()
    by_game = d.groupby("game_id").A.agg(["sum", "count"])
    game_ids = by_game.index.to_numpy()
    sums = by_game["sum"].to_numpy(float)
    counts = by_game["count"].to_numpy(float)
    point = float(sums.sum() / counts.sum())
    rng = np.random.default_rng(SEED)
    draws = np.empty(BOOTSTRAP_DRAWS, dtype=float)
    n_games = len(game_ids)
    for j in range(BOOTSTRAP_DRAWS):
        sample = rng.integers(0, n_games, size=n_games)
        draws[j] = sums[sample].sum() / counts[sample].sum()
    return {
        "trades": int(len(d)),
        "games": int(n_games),
        "mean_A": point,
        "mean_A_percentage_points": point * 100,
        "ci95_A": np.quantile(draws, [0.025, 0.975]).tolist(),
        "ci95_percentage_points": (100 * np.quantile(draws, [0.025, 0.975])).tolist(),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_cluster": "game; pooled trade-row mean recomputed in each resample",
        "bootstrap_seed": SEED,
    }


def main() -> None:
    meta = pd.read_parquet(META)
    meta = meta.loc[
        meta.season.eq(2026)
        & meta.season_type.isin([2, 3])
        & meta.ticker.astype(str).str.startswith("KXNBAGAME")
    ].copy()
    meta["game_id"] = meta.game_id.astype(str)
    meta["game_date"] = meta.ticker.map(ticker_game_date)
    meta["close"] = pd.to_datetime(meta.close_time, utc=True, errors="coerce", format="mixed")
    meta["result"] = meta.result.astype(str).str.lower()
    meta = meta.loc[
        meta.game_date.ge(START)
        & meta.game_date.lt(END_EXCLUSIVE)
        & meta.close.notna()
        & meta.result.isin(["yes", "no"])
    ].drop_duplicates("ticker")

    last = {str(k): pd.Timestamp(v) for k, v in pbp_last().items()}
    meta["last_espn_play"] = meta.game_id.map(last)
    meta = meta.dropna(subset=["last_espn_play"])

    parts: list[pd.DataFrame] = []
    missing_trade_files = []
    windows: dict[str, pd.Series] = {}
    for market in meta.itertuples(index=False):
        windows[market.ticker] = pd.Series({
            "game_id": str(market.game_id), "game_date": market.game_date,
            "close": market.close, "last_espn_play": market.last_espn_play,
        "result": market.result, "season_type": int(market.season_type),
        })
        path = TRADES / f"{market.ticker}.parquet"
        if not path.exists():
            missing_trade_files.append(market.ticker)
            continue
        x = pd.read_parquet(path, columns=[
            "game_id", "trade_id", "ts_utc", "price", "is_block_trade", "settlement_result"
        ])
        if x.empty:
            continue
        x["ts"] = pd.to_datetime(x.ts_utc, utc=True, errors="coerce", format="mixed")
        x["price"] = pd.to_numeric(x.price, errors="coerce")
        x = x.loc[~x.is_block_trade.fillna(False)].copy()
        x = x.loc[x.settlement_result.astype(str).str.lower().eq(market.result)].copy()
        x = x.dropna(subset=["ts", "price"])
        x = x.loc[(x.ts > market.close - pd.Timedelta(minutes=10)) & (x.ts <= market.close)].copy()
        if x.empty:
            continue
        x["game_id"] = str(market.game_id)
        x["market_ticker"] = market.ticker
        x["season_type"] = int(market.season_type)
        x["game_date"] = pd.Timestamp(market.game_date).strftime("%Y-%m-%d")
        x["close"] = market.close
        x["last_espn_play"] = pd.Timestamp(market.last_espn_play)
        x["y"] = int(market.result == "yes")
        x["A"] = x.price - x.y
        x["after_last_espn_play"] = x.ts > x.last_espn_play
        parts.append(x[[
            "game_id", "market_ticker", "season_type", "trade_id", "game_date", "ts", "close",
            "last_espn_play", "price", "y", "A", "after_last_espn_play"
        ]])

    # The in-game parquet stops at the last ESPN play. Reuse the already saved
    # regular-season postgame archive, and fill the missing playoff archive from
    # Kalshi's public historical-trades endpoint (cached per ticker/time range).
    if POST_FILE.exists():
        post = pd.read_parquet(POST_FILE)
        post["market_ticker"] = post.market_ticker.astype(str)
        post["ts"] = pd.to_datetime(post.ts_utc, utc=True, errors="coerce", format="mixed")
        post["price"] = pd.to_numeric(post.price, errors="coerce")
        post["trade_id"] = post.trade_id.astype(str)
        post["game_id"] = post.game_id.astype(str)
        post["y"] = post.settlement_result.astype(str).str.lower().eq("yes").astype("int8")
        for ticker, w in windows.items():
            if ticker not in set(post.market_ticker):
                continue
            z = post.loc[post.market_ticker.eq(ticker) & ~post.is_block_trade.fillna(False)].copy()
            if z.empty:
                continue
            z = z.loc[(z.ts > w.close - pd.Timedelta(minutes=10)) & (z.ts <= w.close)].copy()
            if z.empty:
                continue
            z["game_date"] = pd.Timestamp(w.game_date).strftime("%Y-%m-%d")
            z["season_type"] = int(w.season_type)
            z["close"] = w.close
            z["last_espn_play"] = w.last_espn_play
            z["A"] = z.price - z.y
            z["after_last_espn_play"] = z.ts > z.last_espn_play
            parts.append(z[[
                "game_id", "market_ticker", "season_type", "trade_id", "game_date", "ts", "close",
                "last_espn_play", "price", "y", "A", "after_last_espn_play"
            ]])

    # The saved archive covers the regular season. Fetch only playoff markets
    # without saved postgame rows, using the same cached query bounds.
    archived_tickers = set(post.market_ticker) if POST_FILE.exists() else set()
    playoff_meta = meta.loc[meta.season_type.eq(3)]
    fetch_rows: list[dict] = []
    jobs = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        for _, row in playoff_meta.iterrows():
            if row.ticker in archived_tickers:
                continue
            if row.close <= row.last_espn_play:
                continue
            jobs.append(executor.submit(fetch_postclose_candidate_rows, row))
        for future in as_completed(jobs):
            fetch_rows.extend(future.result())
    if fetch_rows:
        p = pd.DataFrame(fetch_rows)
        p = p.loc[~p.is_block_trade.fillna(False)].dropna(subset=["ts", "price"])
        for ticker, z in p.groupby("market_ticker"):
            w = windows[ticker]
            z = z.loc[(z.ts > w.close - pd.Timedelta(minutes=10)) & (z.ts <= w.close)].copy()
            if z.empty:
                continue
            z["game_date"] = pd.Timestamp(w.game_date).strftime("%Y-%m-%d")
            z["season_type"] = int(w.season_type)
            z["close"] = w.close
            z["A"] = z.price - z.y
            z["after_last_espn_play"] = z.ts > z.last_espn_play
            parts.append(z[[
                "game_id", "market_ticker", "season_type", "trade_id", "game_date", "ts", "close",
                "last_espn_play", "price", "y", "A", "after_last_espn_play"
            ]])

    trades = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["game_id", "market_ticker", "season_type", "trade_id", "game_date", "ts", "close",
                 "last_espn_play", "price", "y", "A", "after_last_espn_play"]
    )
    if not trades.empty:
        trades = trades.drop_duplicates(["market_ticker", "trade_id"], keep="last")
    if trades.empty:
        raise RuntimeError("No trades found in requested close-time sample.")

    # Same one-cent calibration and two-parameter Prelec fitting pipeline as
    # the thesis's phase5a comparison; output includes both raw and isotonic fits.
    fit_summary, _ = summarize(
        trades[["game_id", "price", "y"]].copy(),
        "NBA_Mar01_May15_close_time_window",
        draws=BOOTSTRAP_DRAWS,
        rng=np.random.default_rng(SEED),
        bin_width=1,
    )

    longshot = trades.loc[trades.price.between(0.05, 0.20, inclusive="both")].copy()
    gap = game_cluster_bootstrap_mean(longshot)

    after_n = int(trades.after_last_espn_play.sum())
    type_breakdown = {}
    for season_type, group in trades.groupby("season_type"):
        type_breakdown["regular_season" if int(season_type) == 2 else "playoffs"] = {
            "trade_rows": int(len(group)),
            "games": int(group.game_id.nunique()),
            "after_last_espn_play_rows": int(group.after_last_espn_play.sum()),
            "after_last_espn_play_percent": float(100 * group.after_last_espn_play.mean()),
        }
    result = {
        "scope": {
            "league": "NBA",
            "season": "2025-26",
            "season_types": {"2": "regular season", "3": "playoffs"},
            "scheduled_game_dates_inclusive": ["2026-03-01", "2026-05-15"],
            "game_date_rule": "Date parsed from the NBA Kalshi game ticker (scheduled game date).",
            "requested_window": "last 10 minutes before each market's recorded close_time; close-10m < trade timestamp <= close",
            "markets": "both team YES markets when available; market-YES price and settlement outcome",
            "trade_unit": "trade rows, not contract quantity; block trades excluded; resolved markets only; regular-season postgame archive reused and missing playoff postgame rows fetched from the public Kalshi historical-trades endpoint",
            "all_price_count_rule": "No price-band restriction; all recorded prices retained for the count and after-last-play share.",
            "prelec_price_rule": "Same phase5a pipeline: one-cent bins, trade-weighted calibration; raw and isotonic two-parameter Prelec-II fits. Prices exactly 0 or 1 are omitted from the curve fit only, if present.",
            "longshot_gap_rule": "A = p - Y for market-YES trades with 5c <= p <= 20c, pooled equally across trade rows.",
            "gap_interval": "2,000 percentile bootstrap draws resampling games and recomputing the pooled trade-row mean.",
        },
        "coverage": {
            "eligible_market_rows": int(len(meta)),
            "eligible_games_with_espn_end_marker": int(meta.game_id.nunique()),
            "eligible_games_with_close_window_trades": int(trades.game_id.nunique()),
            "markets_with_trade_file_missing": missing_trade_files,
            "markets_in_window_with_trades": int(trades.market_ticker.nunique()),
        },
        "close_window_all_prices": {
            "trade_rows": int(len(trades)),
            "games": int(trades.game_id.nunique()),
            "after_last_espn_play_rows": after_n,
            "after_last_espn_play_share": after_n / len(trades),
            "after_last_espn_play_percent": 100 * after_n / len(trades),
            "by_season_type": type_breakdown,
        },
        "prelec_fit": fit_summary,
        "longshot_pooled_gap": gap,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
