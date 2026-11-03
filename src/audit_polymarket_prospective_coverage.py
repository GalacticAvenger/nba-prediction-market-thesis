"""Audit completed prospective games against the frozen quote-coverage rule."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from common import RAW, ROOT, get_json
from game_windows import is_final_regulation_window
from ingest_pbp import play_records

OUT = ROOT / "data/interim/phase6/prospective"
CATALOG = OUT / "market_catalog.json"
STATUS = OUT / "collector_status.jsonl"
QUOTE_DIR = OUT / "quote_events"
FRESH_SECONDS = 5.0


def read_status() -> list[dict]:
    return [json.loads(line) for line in STATUS.read_text().splitlines() if line]


def valid_quote(row: dict) -> bool:
    try:
        bid, ask = float(row["best_bid"]), float(row["best_ask"])
        return 0 < bid < ask < 1
    except (KeyError, TypeError, ValueError):
        return False


def quiet_windows(game: dict, rows: list[dict]) -> list[tuple[float, float]]:
    pbp = pd.DataFrame(rows)
    if pbp.empty:
        return []
    pbp["_ord"] = np.arange(len(pbp))
    windows = []
    for _, group in pbp.groupby("game_id", sort=False):
        group = group.sort_values("_ord", kind="stable").reset_index(drop=True)
        records = list(group.itertuples(index=False))
        for i, event in enumerate(records):
            event_type = str(event.action_type or "").lower()
            if "timeout" not in event_type or not is_final_regulation_window(
                    event.period, event.clock_s_remaining, 5):
                continue
            next_live, next_index = None, None
            for j in range(i + 1, len(records)):
                candidate = records[j]
                if int(candidate.period or 0) != int(event.period or 0):
                    break
                candidate_type = str(candidate.action_type or "").lower()
                if any(x in candidate_type for x in ("shot", "rebound", "turnover")) and pd.notna(
                        candidate.ts_wall_utc) and pd.notna(candidate.clock_s_remaining):
                    next_live, next_index = candidate, j
                    break
            if next_live is None or pd.isna(event.ts_wall_utc) or pd.isna(event.clock_s_remaining):
                continue
            restart = pd.Timestamp(next_live.ts_wall_utc) - pd.Timedelta(
                seconds=float(event.clock_s_remaining) - float(next_live.clock_s_remaining))
            onset = pd.Timestamp(event.ts_wall_utc)
            stop = restart - pd.Timedelta(seconds=5)
            if stop < onset:
                continue
            segment = records[i + 1:next_index]
            segment_text = " ".join((str(x.action_type or "") + " " + str(x.text or "")).lower()
                                    for x in segment)
            changed_score = any(str(x.score_home) != str(event.score_home)
                                or str(x.score_away) != str(event.score_away) for x in segment)
            if changed_score or any(term in segment_text for term in ("review", "challenge")):
                continue
            # Phase 4 additionally rejects any foul/free-throw record before the
            # five-second trimmed restart, even if the timeout interval survives.
            event_times = pd.to_datetime(pbp.ts_wall_utc, utc=True, errors="coerce")
            in_window = (event_times >= onset) & (event_times <= stop)
            event_types = pbp.action_type.fillna("").str.lower()
            if event_types[in_window].str.contains(r"foul|free throw", regex=True).any():
                continue
            windows.append((onset.timestamp(), stop.timestamp()))
    # Collapse duplicate/overlapping timeout records before counting time-grid
    # observations; ESPN sometimes emits more than one timeout record for one
    # stoppage. Phase 4 quarter breaks cannot intersect its final-five rule.
    merged: list[list[float]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def load_quotes(slugs: set[str]) -> dict[str, dict[str, list[tuple[float, dict]]]]:
    out: dict[str, dict[str, list[tuple[float, dict]]]] = {slug: {} for slug in slugs}
    for path in sorted(QUOTE_DIR.glob("events_*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                slug = row.get("slug")
                if slug not in out or row.get("event_type") not in {"book", "price_change", "best_bid_ask"}:
                    continue
                asset = str(row.get("asset_id", ""))
                recv = pd.Timestamp(row["received_at_utc"]).timestamp()
                out[slug].setdefault(asset, []).append((recv, row))
    for assets in out.values():
        for asset in assets:
            assets[asset].sort(key=lambda pair: pair[0])
    return out


def quote_at(events: list[tuple[float, dict]], times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    event_times = np.asarray([x[0] for x in events], dtype=float)
    idx = np.searchsorted(event_times, times, side="right") - 1
    ages = np.full(len(times), np.inf)
    ok = idx >= 0
    ages[ok] = times[ok] - event_times[idx[ok]]
    fresh = ok & (ages >= 0) & (ages <= FRESH_SECONDS)
    valid = np.zeros(len(times), dtype=bool)
    for i in np.flatnonzero(ok):
        valid[i] = valid_quote(events[idx[i]][1])
    return fresh & valid, ages


def main() -> None:
    catalog = json.loads(CATALOG.read_text())["markets"]
    now = datetime.now(timezone.utc).timestamp()
    statuses = read_status()
    session = requests.Session()
    summaries = {}
    for slug, market in catalog.items():
        if pd.Timestamp(market["scheduled_start_utc"]).timestamp() >= now - 3 * 3600:
            continue
        gid = market["espn_game_id"]
        checked = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        cache = RAW / "polymarket" / "prospective" / "espn_summaries" / f"{gid}_{checked}.json"
        payload = get_json(session, f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={gid}", cache)
        competition = (payload.get("header", {}).get("competitions") or [{}])[0]
        if competition.get("status", {}).get("type", {}).get("completed"):
            summaries[slug] = payload
    completed = {s: catalog[s] for s in summaries}
    quotes = load_quotes(set(completed))
    result_rows = []
    for slug, market in sorted(completed.items()):
        start_ts = pd.Timestamp(market["scheduled_start_utc"]).timestamp()
        token_ids = {v["token_id"] for v in market["outcome_tokens"].values()}
        pretip_assets = {asset for asset, events in quotes[slug].items()
                         if asset in token_ids and events and events[0][0] < start_ts}
        prior_connects = [x for x in statuses if x.get("kind") == "websocket_connected"
                          and pd.Timestamp(x["recorded_utc"]).timestamp() < start_ts]
        connected_before_tip = bool(prior_connects)
        if len(pretip_assets) != 2 or not connected_before_tip:
            result_rows.append({"slug": slug, "espn_game_id": market["espn_game_id"],
                                "scheduled_start_utc": market["scheduled_start_utc"],
                                "pre_tip_capture": False, "eligible_quiet_seconds": 0,
                                "covered_seconds": 0, "coverage": None,
                                "qualifies_95pct": False,
                                "reason": "both outcome tokens not observed pre-tip" if len(pretip_assets) != 2 else "no prior WebSocket connection"})
            continue
        gid = market["espn_game_id"]
        payload = summaries[slug]
        plays = payload.get("plays", [])
        game = {"espn_game_id": gid, "season": 2026, "season_type": 2}
        pbp_rows = play_records(game, payload, any(p.get("wallclock") for p in plays))
        windows = quiet_windows(market, pbp_rows)
        if not windows:
            result_rows.append({"slug": slug, "espn_game_id": gid,
                                "scheduled_start_utc": market["scheduled_start_utc"],
                                "pre_tip_capture": True, "eligible_quiet_seconds": 0,
                                "covered_seconds": 0, "coverage": None,
                                "qualifies_95pct": False, "reason": "no Phase 4-compatible final-five quiet windows"})
            continue
        grid = np.concatenate([np.arange(np.ceil(a), np.floor(b) + 1, 1.0) for a, b in windows])
        asset_ids = [market["outcome_tokens"][side]["token_id"] for side in ("home", "away")]
        asset_events = [quotes[slug].get(asset, []) for asset in asset_ids]
        fresh = []
        for events in asset_events:
            states, _ = quote_at(events, grid)
            fresh.append(states)
        both = fresh[0] & fresh[1]
        coverage = float(both.mean()) if len(grid) else float("nan")
        result_rows.append({"slug": slug, "espn_game_id": gid,
                            "scheduled_start_utc": market["scheduled_start_utc"],
                            "pre_tip_capture": True, "eligible_quiet_seconds": int(len(grid)),
                            "home_covered_seconds": int(fresh[0].sum()),
                            "away_covered_seconds": int(fresh[1].sum()),
                            "home_quote_updates": len(asset_events[0]), "away_quote_updates": len(asset_events[1]),
                            "home_valid_updates": sum(valid_quote(x[1]) for x in asset_events[0]),
                            "away_valid_updates": sum(valid_quote(x[1]) for x in asset_events[1]),
                            "covered_seconds": int(both.sum()), "coverage": coverage,
                            "qualifies_95pct": bool(coverage >= 0.95),
                            "reason": ""})
    frame = pd.DataFrame(result_rows)
    frame.to_csv(OUT / "coverage_audit.csv", index=False)
    summary = {"checked_utc": datetime.now(timezone.utc).isoformat(),
               "completed_games": len(frame),
               "pre_tip_games": int(frame.pre_tip_capture.sum()) if len(frame) else 0,
               "games_with_eligible_quiet_seconds": int(frame.eligible_quiet_seconds.gt(0).sum()) if len(frame) else 0,
               "games_passing_95pct": int(frame.qualifies_95pct.sum()) if len(frame) else 0,
               "rule": "one-second grid over Phase 4-compatible final-five clean timeouts; both home and away tokens must have uncrossed two-sided quotes, each event received within prior 5 seconds"}
    (OUT / "coverage_audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    if len(frame):
        print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
