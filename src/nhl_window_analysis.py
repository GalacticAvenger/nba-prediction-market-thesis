"""Full-season NHL extension of the late-game window comparison.

Downloads/caches 2025-26 NHL regular-season ESPN play-by-play and Kalshi
historical trades, applies the same 5-20c contract-price rule as the pilot,
and makes a harmonized comparison to NBA trades on the same calendar dates.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from common import ROOT, get_json, make_session

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
START = date(2025, 10, 7)
END = date(2026, 4, 16)
RAW = ROOT / "data/raw/nhl_2025_26"
OUT = ROOT / "data/interim/nhl_2025_26_window_analysis"
SEED = 20261104
DRAWS = 10_000


def cached(session, url, path, interval=.05):
    return get_json(session, url, path, min_interval=interval)


def parse_utc(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def parse_period(value):
    if isinstance(value, dict):
        value = value.get("number")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_clock(value):
    if isinstance(value, dict):
        value = value.get("displayValue")
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"\s*(\d+):(\d{2}(?:\.\d+)?)\s*", value)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    if re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", value):
        n = float(value)
        return n if 0 <= n < 60 else None
    return None


def fetch_scoreboard(session, day):
    key = day.strftime("%Y%m%d")
    payload = cached(session, f"{ESPN}/scoreboard?dates={key}", RAW / "espn" / f"scoreboard_{key}.json")
    rows = []
    for event in payload.get("events", []):
        comp = event.get("competitions", [{}])[0]
        teams = comp.get("competitors", [])
        home = next((x for x in teams if x.get("homeAway") == "home"), {})
        away = next((x for x in teams if x.get("homeAway") == "away"), {})
        if home and away:
            rows.append({"game_id": str(event["id"]), "date": key,
                         "name": event.get("name"),
                         "home_code": str(home.get("team", {}).get("abbreviation", "")).upper(),
                         "away_code": str(away.get("team", {}).get("abbreviation", "")).upper(),
                         "home_name": home.get("team", {}).get("displayName"),
                         "away_name": away.get("team", {}).get("displayName"),
                         "status": comp.get("status", {}).get("type", {}).get("name"),
                         "season_type": (event.get("season") or {}).get("type")})
    return rows


def kalshi_key(event_ticker):
    m = re.fullmatch(r"KXNHLGAME-(\d{2})([A-Z]{3})(\d{2})([A-Z]+)", str(event_ticker))
    if not m:
        return None
    yy, mon, dd, codes = m.groups()
    return f"20{yy}{datetime.strptime(mon, '%b').month:02d}{int(dd):02d}", codes


def fetch_catalog(session):
    rows, cursor, page = [], "", 0
    while True:
        params = {"series_ticker": "KXNHLGAME", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        req = requests.Request("GET", f"{KALSHI}/historical/markets", params=params).prepare()
        payload = cached(session, req.url, RAW / "kalshi" / f"markets_{page:03d}.json", .1)
        rows.extend(payload.get("markets", []))
        cursor = payload.get("cursor", "")
        page += 1
        if not cursor:
            break
    return rows


def match_games(espn, markets):
    by_key = {}
    for m in markets:
        key = kalshi_key(m.get("event_ticker"))
        if key:
            by_key.setdefault(key, []).append(m)
    matched = []
    for g in espn:
        codes = g["home_code"] + g["away_code"]
        rev = g["away_code"] + g["home_code"]
        ms = by_key.get((g["date"], codes)) or by_key.get((g["date"], rev))
        if ms:
            matched.append((g, ms))
    return matched


def fetch_plays(session, game):
    payload = cached(session, f"{ESPN}/summary?event={game['game_id']}",
                     RAW / "espn" / f"summary_{game['game_id']}.json")
    raw_plays = payload.get("plays", [])
    end_markers = [parse_utc(p.get("wallclock")) for p in raw_plays
                   if str(p.get("text", "")).strip().lower() == "game end"]
    end_markers = [x for x in end_markers if x is not None]
    explicit_end = max(end_markers) if end_markers else None
    source_times = [parse_utc(p.get("wallclock")) for p in raw_plays]
    source_times = [x for x in source_times if x is not None]
    rows = []
    dropped_after_end = 0
    for p in raw_plays:
        ts, period, clock = parse_utc(p.get("wallclock")), parse_period(p.get("period")), parse_clock(p.get("clock"))
        if ts is not None and period is not None and clock is not None:
            if explicit_end is not None and ts > explicit_end:
                dropped_after_end += 1
                continue
            rows.append({"ts": ts, "period": period, "clock": clock,
                         "type": (p.get("type") or {}).get("text") if isinstance(p.get("type"), dict) else None})
    payload["_explicit_game_end_ts"] = explicit_end
    payload["_plays_dropped_after_game_end"] = dropped_after_end
    payload["_timestamps_monotonic_in_source_order"] = all(a <= b for a, b in zip(source_times, source_times[1:]))
    return pd.DataFrame(rows).sort_values("ts", kind="stable").reset_index(drop=True), payload


def fetch_trades(session, ticker, lo, hi):
    rows, cursor, page = [], "", 0
    while True:
        params = {"ticker": ticker, "min_ts": int(lo), "max_ts": int(hi),
                  "is_block_trade": "false", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        req = requests.Request("GET", f"{KALSHI}/historical/trades", params=params).prepare()
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", ticker)
        payload = cached(session, req.url, RAW / "kalshi" / "trades" / safe / f"{page:04d}.json", .08)
        rows.extend(payload.get("trades", []))
        cursor = payload.get("cursor", "")
        page += 1
        if not cursor:
            return rows


def process_game(session, game, markets):
    plays, summary = fetch_plays(session, game)
    if plays.empty:
        return {"game_id": game["game_id"], "error": "no timestamped plays"}, []
    first, last = float(plays.ts.min()), float(plays.ts.max())
    last_period = int(plays.iloc[-1].period)
    comp = summary.get("header", {}).get("competitions", [{}])[0]
    competitors = comp.get("competitors", [])
    espn_winner = next((str(x.get("team", {}).get("abbreviation", "")).upper()
                        for x in competitors if x.get("winner")), None)
    espn_status = comp.get("status", {}).get("type", {}).get("name")
    teams = {game["home_code"], game["away_code"]}
    rows, market_codes = [], set()
    for m in markets:
        ticker = str(m.get("ticker", ""))
        yes_code = ticker.rsplit("-", 1)[-1].upper()
        if yes_code not in teams:
            continue
        market_codes.add(yes_code)
        result = str(m.get("result", "")).lower()
        if result not in {"yes", "no"}:
            continue
        for tr in fetch_trades(session, ticker, first - 120, last + 120):
            if tr.get("is_block_trade"):
                continue
            ts = parse_utc(tr.get("created_time"))
            try:
                yes_price = float(tr["yes_price_dollars"])
            except (KeyError, TypeError, ValueError):
                continue
            if ts is None or not 0 <= yes_price <= 1:
                continue
            lp = min(yes_price, 1 - yes_price)
            if not .05 <= lp <= .20:
                continue
            y = int((result == "yes") if yes_price <= .5 else (result != "yes"))
            rows.append({"game_id": game["game_id"], "date": game["date"], "ticker": ticker,
                         "ts": ts, "yes_price": yes_price, "longshot_price": lp,
                         "longshot_y": y, "gap_y_minus_p": y - lp})
    t = pd.DataFrame(rows)
    clock_stale = []
    if not t.empty:
        t = t.sort_values("ts", kind="stable").reset_index(drop=True)
        pts = plays.ts.to_numpy(float)
        ti = t.ts.to_numpy(float)
        idx = np.searchsorted(pts, ti, side="right") - 1
        valid = (idx >= 0) & (ti < last)
        t["valid_pre_final_play"] = valid
        t["lag_from_play_s"] = np.where(valid, ti - pts[np.maximum(idx, 0)], np.nan)
        t["period"] = np.where(valid, plays.period.to_numpy(int)[np.maximum(idx, 0)], -1)
        t["clock_remaining_s"] = np.where(valid, plays.clock.to_numpy(float)[np.maximum(idx, 0)], np.nan)
        # Keep the original NBA convention: final five minutes of regulation.
        # In overtime games this is intentionally distinct from the retrospective
        # final ten minutes, and is reported separately.
        t["retrospective"] = valid & (ti >= last - 600)
        t["clock_final5_reg"] = valid & (t.period.to_numpy(int) == 3) & (t.clock_remaining_s.to_numpy(float) <= 300)
        for threshold in (60, 180):
            t[f"clock_final5_reg_lag{threshold}"] = (valid & (t.lag_from_play_s.to_numpy(float) <= threshold)
                                                       & (t.period.to_numpy(int) == 3)
                                                       & (t.clock_remaining_s.to_numpy(float) <= 300))
        clock_stale = t.loc[valid, "lag_from_play_s"].to_list()
        rows = t.to_dict("records")
    result_map = {str(m.get("ticker", "")).rsplit("-", 1)[-1].upper(): str(m.get("result", "")).lower()
                  for m in markets if str(m.get("ticker", "")).rsplit("-", 1)[-1].upper() in teams}
    winners = [x for x, v in result_map.items() if v == "yes"]
    return {"game_id": game["game_id"], "date": game["date"], "name": game["name"],
                  "status": espn_status, "last_play_period": last_period,
                  "explicit_game_end_marker": summary.get("_explicit_game_end_ts") is not None,
                  "plays_after_game_end_dropped": int(summary.get("_plays_dropped_after_game_end", 0)),
                  "regulation_end": last_period == 3, "went_overtime": last_period > 3,
                  "timestamped_plays": len(plays), "play_times_monotonic": bool(summary.get("_timestamps_monotonic_in_source_order")),
                  "first_play_utc": datetime.fromtimestamp(first, timezone.utc).isoformat(),
                  "last_play_utc": datetime.fromtimestamp(last, timezone.utc).isoformat(),
                  "matched_markets": len(market_codes), "trade_rows_5_20c": len(rows),
                  "kalshi_yes_winner": winners[0] if len(winners) == 1 else None,
                  "espn_winner": espn_winner,
                  "settlement_matches_espn": bool(espn_winner and winners == [espn_winner]),
                  "markets_complementary": len(result_map) == 2 and sorted(result_map.values()) == ["no", "yes"],
                  "n_trades_pre_final": int(t.valid_pre_final_play.sum()) if not t.empty else 0,
                  "median_play_lag_s": float(np.median(clock_stale)) if clock_stale else None,
                  "p90_play_lag_s": float(np.quantile(clock_stale, .9)) if clock_stale else None}, rows


def game_summaries(trades, window_map):
    rows = []
    d = pd.DataFrame(trades)
    if d.empty:
        return pd.DataFrame()
    for gid, g in d.groupby("game_id", sort=False):
        r = {"game_id": gid}
        for name, col in window_map.items():
            z = g.loc[g[col].astype(bool)]
            r[f"{name}_n"] = len(z)
            r[f"{name}_gap"] = z.gap_y_minus_p.mean() if len(z) else np.nan
            r[f"{name}_sum"] = z.gap_y_minus_p.sum() if len(z) else 0.0
        rows.append(r)
    out = pd.DataFrame(rows)
    out["paired_effect_clock_minus_retro"] = out.clock_final5_reg_gap - out.retrospective_gap
    return out


def boot_mean(x, seed=SEED, draws=DRAWS):
    a = np.asarray(x, float)
    a = a[np.isfinite(a)]
    if not len(a):
        return {"n_games": 0, "estimate": None, "ci95": [None, None]}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(draws, len(a)))
    b = a[idx].mean(axis=1)
    return {"n_games": len(a), "estimate": float(a.mean()),
            "ci95": [float(v) for v in np.quantile(b, [.025, .975])], "draws": draws}


def boot_difference(a, b, seed=SEED + 7):
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    rng = np.random.default_rng(seed)
    ai = rng.integers(0, len(a), size=(DRAWS, len(a)))
    bi = rng.integers(0, len(b), size=(DRAWS, len(b)))
    draws = a[ai].mean(axis=1) - b[bi].mean(axis=1)
    return {"estimate_nba_minus_nhl": float(a.mean() - b.mean()),
            "ci95": [float(v) for v in np.quantile(draws, [.025, .975])],
            "nba_games": len(a), "nhl_games": len(b), "draws": DRAWS}


def boot_trade_weighted(games, window, seed=SEED + 20):
    z = games.loc[games[f"{window}_n"] > 0]
    sums = z[f"{window}_sum"].to_numpy(float)
    counts = z[f"{window}_n"].to_numpy(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(z), size=(DRAWS, len(z)))
    estimate = sums.sum() / counts.sum()
    draws = sums[idx].sum(axis=1) / counts[idx].sum(axis=1)
    return {"trades": int(counts.sum()), "games": int(len(z)), "estimate": float(estimate),
            "ci95": [float(v) for v in np.quantile(draws, [.025, .975])], "draws": DRAWS}


def boot_marginal_delta(games, seed=SEED + 40):
    retro = games.retrospective_gap.dropna().to_numpy(float)
    clock = games.clock_final5_reg_gap.dropna().to_numpy(float)
    rng = np.random.default_rng(seed)
    ir = rng.integers(0, len(retro), size=(DRAWS, len(retro)))
    ic = rng.integers(0, len(clock), size=(DRAWS, len(clock)))
    draws = clock[ic].mean(axis=1) - retro[ir].mean(axis=1)
    return {"estimate_clock_minus_retrospective": float(clock.mean() - retro.mean()),
            "ci95": [float(v) for v in np.quantile(draws, [.025, .975])],
            "retrospective_games": len(retro), "clock_games": len(clock), "draws": DRAWS}


def boot_marginal_cross_sport(nhl, nba, seed=SEED + 50):
    nr = nhl.retrospective_gap.dropna().to_numpy(float)
    nc = nhl.clock_final5_reg_gap.dropna().to_numpy(float)
    br = nba.retrospective_gap.dropna().to_numpy(float)
    bc = nba.clock_final5_reg_gap.dropna().to_numpy(float)
    rng = np.random.default_rng(seed)
    ir = rng.integers(0, len(nr), size=(DRAWS, len(nr)))
    ic = rng.integers(0, len(nc), size=(DRAWS, len(nc)))
    jr = rng.integers(0, len(br), size=(DRAWS, len(br)))
    jc = rng.integers(0, len(bc), size=(DRAWS, len(bc)))
    draws = (nc[ic].mean(axis=1) - nr[ir].mean(axis=1)
             - bc[jc].mean(axis=1) + br[jr].mean(axis=1))
    return {"estimate_nhl_minus_nba_marginal_window_difference": float(
                nc.mean() - nr.mean() - bc.mean() + br.mean()),
            "ci95": [float(v) for v in np.quantile(draws, [.025, .975])],
            "nhl_retrospective_games": len(nr), "nhl_clock_games": len(nc),
            "nba_retrospective_games": len(br), "nba_clock_games": len(bc), "draws": DRAWS}


def load_nba_dates(start_key, end_key):
    schedule = pd.read_parquet(ROOT / "data/interim/espn_games.parquet")
    schedule = schedule.loc[(schedule.season == 2026) & (schedule.season_type == 2)].copy()
    schedule["date"] = pd.to_datetime(schedule.event_date_utc, utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y%m%d")
    schedule = schedule.loc[schedule.date.between(start_key, end_key)]
    meta = pd.read_parquet(ROOT / "data/interim/kalshi_market_metadata.parquet")
    meta = meta.loc[(meta.season == 2026) & (meta.season_type == 2)]
    meta = meta.loc[meta.game_id.astype(str).isin(schedule.espn_game_id.astype(str))]
    results, coverage = [], []
    for gid, group in meta.groupby("game_id", sort=False):
        dates = schedule.loc[schedule.espn_game_id.astype(str) == str(gid), "date"]
        if not len(dates):
            continue
        last_path = ROOT / "data/raw/espn/summaries" / f"{gid}.json"
        if not last_path.exists():
            continue
        summary = json.loads(last_path.read_text(encoding="utf-8"))
        times = [parse_utc(p.get("wallclock")) for p in summary.get("plays", [])]
        times = [v for v in times if v is not None]
        if not times:
            continue
        ends = [parse_utc(p.get("wallclock")) for p in summary.get("plays", [])
                if str(p.get("text", "")).strip().lower() == "game end"]
        ends = [v for v in ends if v is not None]
        last = max(ends) if ends else max(times)
        r, window = [], []
        for m in group.itertuples(index=False):
            path = ROOT / "data/interim/phase4/trade_panel" / f"{m.ticker}.parquet"
            if not path.exists() or str(m.result).lower() not in {"yes", "no"}:
                continue
            x = pd.read_parquet(path)
            if x.empty:
                continue
            ts = pd.to_datetime(x.ts_utc, utc=True, errors="coerce").astype("int64").to_numpy() / 1e9
            selected = pd.to_numeric(x.selected_contract_price, errors="coerce").to_numpy(float)
            lp = pd.to_numeric(x.longshot_price, errors="coerce").to_numpy(float)
            yes_result = int(str(m.result).lower() == "yes")
            same = x.ticker_yes_is_home.fillna(False).astype(bool).to_numpy() == x.selected_team_is_home.fillna(False).astype(bool).to_numpy()
            selected_y = np.where(same, yes_result, 1-yes_result)
            longshot_y = np.where(selected <= .5, selected_y, 1-selected_y)
            period = pd.to_numeric(x.period, errors="coerce").fillna(-1).to_numpy(int)
            clock = pd.to_numeric(x.clock_s_remaining, errors="coerce").to_numpy(float)
            good = np.isfinite(lp) & (lp >= .05) & (lp <= .20) & (ts < last)
            masks = {"retrospective": good & (ts >= last-600),
                     "clock_final5_reg": good & (period == 4) & (clock >= 0) & (clock <= 300)}
            for name, mask in masks.items():
                for gap in (longshot_y - lp)[mask]:
                    r.append((str(gid), name, float(gap)))
            if good.any():
                window.append(True)
        if r:
            gdf = pd.DataFrame(r, columns=["game_id", "window", "gap"])
            grouped = gdf.groupby(["game_id", "window"]).gap.agg(["mean", "sum", "count"]).reset_index()
            gm = None
            for stat, suffix in [("mean", "gap"), ("sum", "sum"), ("count", "n")]:
                wide = grouped.pivot(index="game_id", columns="window", values=stat).reset_index()
                wide = wide.rename(columns={c: f"{c}_{suffix}" for c in wide.columns if c != "game_id"})
                gm = wide if gm is None else gm.merge(wide, on="game_id", how="outer")
            for col in ("retrospective_gap", "clock_final5_reg_gap"):
                if col not in gm.columns:
                    gm[col] = np.nan
            for col in ("retrospective_n", "clock_final5_reg_n", "retrospective_sum", "clock_final5_reg_sum"):
                if col not in gm.columns:
                    gm[col] = 0
            gm["paired_effect_clock_minus_retro"] = gm.clock_final5_reg_gap - gm.retrospective_gap
            periods = [parse_period(p.get("period")) for p in summary.get("plays", [])
                       if parse_utc(p.get("wallclock")) is not None and parse_utc(p.get("wallclock")) <= last]
            last_period = max((x or 0 for x in periods), default=0)
            gm["regulation_end"] = (last_period == 4)
            results.append(gm)
            coverage.append({"game_id": str(gid), "date": dates.iloc[0], "market_rows": len(group),
                             "explicit_game_end_marker": bool(ends)})
    return (pd.concat(results, ignore_index=True) if results else pd.DataFrame()), pd.DataFrame(coverage)


def main():
    session = make_session()
    espn = []
    day = START
    while day <= END:
        espn.extend(fetch_scoreboard(session, day))
        day += timedelta(days=1)
    # ESPN's schedule queries include any non-regular event, so explicitly keep
    # regular-season games and settled markets only.
    espn = [g for g in espn if g.get("season_type") in (2, "2") and g.get("status") == "STATUS_FINAL"]
    markets = fetch_catalog(session)
    matched = match_games(espn, markets)
    games = [(g, [m for m in ms if str(m.get("result", "")).lower() in {"yes", "no"}])
             for g, ms in matched]
    games = [(g, ms) for g, ms in games if len(ms) == 2]
    print(f"Matched {len(games)} completed regular-season games; downloading trades…", flush=True)
    trades, coverage = [], []
    for i, (g, ms) in enumerate(games, 1):
        cov, rows = process_game(session, g, ms)
        coverage.append(cov)
        trades.extend(rows)
        if i % 50 == 0 or i == len(games):
            print(f"Processed {i}/{len(games)}; eligible trades={len(trades)}", flush=True)
    if not trades:
        raise RuntimeError("No eligible NHL trades; check API coverage and cache.")
    frame = pd.DataFrame(trades)
    # High-signal windows, no post-final-play trades.
    for window in ["retrospective", "clock_final5_reg"]:
        frame[window] = frame[window].astype(bool)
    all_gm = game_summaries(trades, {"retrospective": "retrospective", "clock_final5_reg": "clock_final5_reg"})
    covdf = pd.DataFrame(coverage)
    gm = all_gm.merge(covdf[["game_id", "regulation_end", "went_overtime", "settlement_matches_espn", "markets_complementary", "median_play_lag_s", "p90_play_lag_s"]], on="game_id", how="left")
    # Same-date NBA comparator, same price-only rule and same window definitions.
    start_key, end_key = START.strftime("%Y%m%d"), END.strftime("%Y%m%d")
    nba_gm, nba_cov = load_nba_dates(start_key, end_key)
    paired_nhl = gm.dropna(subset=["retrospective_gap", "clock_final5_reg_gap"])
    paired_nba = nba_gm.dropna(subset=["retrospective_gap", "clock_final5_reg_gap"])
    nhl_all = {"retrospective": {"game_equal": boot_mean(gm.retrospective_gap),
                                  "trade_weighted": boot_trade_weighted(gm, "retrospective", SEED+31)},
               "clock_final5_reg": {"game_equal": boot_mean(gm.clock_final5_reg_gap, SEED+1),
                                    "trade_weighted": boot_trade_weighted(gm, "clock_final5_reg", SEED+32)},
               "paired_window_difference": boot_mean(paired_nhl.paired_effect_clock_minus_retro, SEED+2)}
    nba_all = {"retrospective": {"game_equal": boot_mean(nba_gm.retrospective_gap, SEED+3),
                                 "trade_weighted": boot_trade_weighted(nba_gm, "retrospective", SEED+33)},
               "clock_final5_reg": {"game_equal": boot_mean(nba_gm.clock_final5_reg_gap, SEED+4),
                                    "trade_weighted": boot_trade_weighted(nba_gm, "clock_final5_reg", SEED+34)},
               "paired_window_difference": boot_mean(paired_nba.paired_effect_clock_minus_retro, SEED+5)}
    def effect(g):
        return g.dropna(subset=["paired_effect_clock_minus_retro"]).paired_effect_clock_minus_retro.to_numpy(float)
    league_diff = boot_difference(effect(nba_gm), effect(gm))
    nba_reg = nba_gm.loc[nba_gm.regulation_end.fillna(False)]
    nhl_reg = gm.loc[gm.regulation_end.fillna(False)]
    league_diff_regulation_only = boot_difference(effect(nba_reg), effect(nhl_reg), SEED+8)
    marginal_nhl = boot_marginal_delta(gm, SEED+41)
    marginal_nba = boot_marginal_delta(nba_gm, SEED+42)
    marginal_league_diff = boot_marginal_cross_sport(gm, nba_gm, SEED+51)
    marginal_regulation_diff = boot_marginal_cross_sport(nhl_reg, nba_reg, SEED+52)
    clock_lag_sensitivity = {}
    for threshold in (60, 180):
        strict = frame.copy()
        strict["clock_strict"] = strict[f"clock_final5_reg_lag{threshold}"].astype(bool)
        strict_gm = game_summaries(strict.to_dict("records"),
                                   {"retrospective": "retrospective", "clock_final5_reg": "clock_strict"})
        clock_lag_sensitivity[str(threshold)] = boot_mean(strict_gm.paired_effect_clock_minus_retro,
                                                          SEED + threshold)
    # Show overtime sensitivity: the retrospective window is still defined from
    # each game's final timestamped play, while the clock window remains 3rd period.
    reg = gm.loc[gm.regulation_end.fillna(False)]
    ot = gm.loc[gm.went_overtime.fillna(False)]
    summary = {
        "scope": f"2025-26 NHL regular season, ESPN dates {START.isoformat()} through {END.isoformat()}; all matched settled two-team markets",
        "estimand": "equal-game mean of realized longshot payoff minus trade price; paired effect is clock-window mean minus retrospective-window mean within each game",
        "windows": {"retrospective": "trades in final 10 wall-clock minutes before last timestamped ESPN play, excluding that play and later trades",
                    "clock_final5_reg": "trades assigned to final 5:00 of 3rd period from latest timestamped ESPN play at/before trade; trades after last timestamped play excluded"},
        "eligibility": "5-20c inclusive cheaper-side team contract, folded YES/NO trade prices to cheaper side, non-block trades",
        "nhl": nhl_all,
        "nba_same_dates_price_only": nba_all,
        "league_difference_nba_minus_nhl_window_effect": league_diff,
        "league_difference_regulation_end_games_only": league_diff_regulation_only,
        "marginal_window_differences_separate_game_samples": {"nhl": marginal_nhl, "nba": marginal_nba},
        "league_difference_marginal_window_effect": marginal_league_diff,
        "league_difference_marginal_regulation_end_games_only": marginal_regulation_diff,
        "nhl_clock_lag_sensitivity_seconds": clock_lag_sensitivity,
        "sample": {"espn_final_regular_games": len(espn), "matched_settled_two_market_games": len(games),
                   "games_with_eligible_trades": int(frame.game_id.nunique()), "paired_window_games": len(paired_nhl),
                   "eligible_trade_rows": len(frame), "retrospective_trade_rows": int(frame.retrospective.sum()),
                   "clock_trade_rows": int(frame.clock_final5_reg.sum()),
                   "settlement_matches_espn": int(covdf.settlement_matches_espn.fillna(False).sum()),
                   "settlement_mismatches": int((~covdf.settlement_matches_espn.fillna(False)).sum()),
                   "complementary_market_pairs": int(covdf.markets_complementary.fillna(False).sum()),
                   "regulation_ending_paired_games": len(reg.dropna(subset=["paired_effect_clock_minus_retro"])),
                   "overtime_ending_paired_games": len(ot.dropna(subset=["paired_effect_clock_minus_retro"]))},
        "overtime_sensitivity": {"regulation_only_paired_effect": boot_mean(reg.paired_effect_clock_minus_retro, SEED+10),
                                 "overtime_ending_paired_effect": boot_mean(ot.paired_effect_clock_minus_retro, SEED+11)},
        "clock_mapping_audit": {"median_lag_trade_to_prior_play_seconds": float(frame.loc[frame.valid_pre_final_play, "lag_from_play_s"].median()),
                                "p90_lag_seconds": float(frame.loc[frame.valid_pre_final_play, "lag_from_play_s"].quantile(.9)),
                                "share_over_60s": float((frame.loc[frame.valid_pre_final_play, "lag_from_play_s"] > 60).mean()),
                                "share_over_180s": float((frame.loc[frame.valid_pre_final_play, "lag_from_play_s"] > 180).mean()),
                                "games_using_explicit_game_end_marker": int(covdf.explicit_game_end_marker.fillna(False).sum()),
                                "plays_after_game_end_dropped": int(covdf.plays_after_game_end_dropped.fillna(0).sum()),
                                "limitation": "Trade period and clock are proxied by latest timestamped play; elapsed running clock between plays may make assignment stale."},
        "bootstrap": f"independent game-level percentile bootstrap, {DRAWS} draws; fixed seed {SEED}",
        "interpretation_limit": "Descriptive windows contain different trade moments/game states. The league contrast is not causal. Regulation clock window and overtime final-event window are substantively different; report regulation-only estimate and audit data coverage before treating as transportability evidence."
    }
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(OUT / "trade_windows.parquet", index=False)
    gm.to_csv(OUT / "game_window_estimates.csv", index=False)
    covdf.to_csv(OUT / "game_coverage.csv", index=False)
    nba_gm.to_csv(OUT / "nba_same_dates_game_estimates.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
