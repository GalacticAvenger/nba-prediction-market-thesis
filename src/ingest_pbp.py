"""Fetch ESPN schedules and per-play NBA data; includes a local NBA-CDN retry."""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

from common import RAW, ROOT, get_json, make_session, safe_name

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
NBA_CDN = "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
NBA_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"),
    "Referer": "https://www.nba.com/", "Origin": "https://www.nba.com",
    "Accept": "application/json, text/plain, */*",
}


def get_teams(session: requests.Session) -> list[dict[str, str]]:
    payload = get_json(session, f"{ESPN}/teams?limit=50", RAW / "espn" / "teams.json", min_interval=0.1)
    return [{"team_id": str(x["team"]["id"]), "abbreviation": x["team"]["abbreviation"],
             "display_name": x["team"]["displayName"]}
            for x in payload["sports"][0]["leagues"][0]["teams"]]


def get_schedule(session: requests.Session, season: int, season_type: int,
                 teams: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    games: dict[str, dict[str, Any]] = {}
    for team in teams:
        tid = team["team_id"]
        url = f"{ESPN}/teams/{tid}/schedule?season={season}&seasontype={season_type}"
        cache = RAW / "espn" / "schedules" / str(season) / f"type_{season_type}" / f"team_{tid}.json"
        payload = get_json(session, url, cache, min_interval=0.08)
        for event in payload.get("events", []):
            competitors = event.get("competitions", [{}])[0].get("competitors", [])
            home = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away = next((c for c in competitors if c.get("homeAway") == "away"), {})
            games[str(event["id"])] = {
                "espn_game_id": str(event["id"]), "event_date_utc": event.get("date"),
                "event_name": event.get("name"), "season": season, "season_type": season_type,
                "home_team_id": str(home.get("team", {}).get("id", "")),
                "home_abbreviation": home.get("team", {}).get("abbreviation", ""),
                "home_team": home.get("team", {}).get("displayName", ""),
                "away_team_id": str(away.get("team", {}).get("id", "")),
                "away_abbreviation": away.get("team", {}).get("abbreviation", ""),
                "away_team": away.get("team", {}).get("displayName", ""),
                "status": event.get("status", {}).get("type", {}).get("name", ""),
            }
    return games


def parse_clock(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("displayValue")
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+):(\d{2}(?:\.\d+)?)\s*", value)
    if match:
        return int(match.group(1)) * 60 + float(match.group(2))
    # ESPN switches to a bare decimal seconds display in the final minute.
    if re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", value):
        seconds = float(value)
        return seconds if 0 <= seconds < 60 else None
    return None


def parse_wallclock(value: Any) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_summary(session: requests.Session, game: dict[str, Any]) -> dict[str, Any]:
    gid = game["espn_game_id"]
    return get_json(session, f"{ESPN}/summary?event={gid}", RAW / "espn" / "summaries" / f"{gid}.json", min_interval=0.03)


def _thread_session() -> requests.Session:
    from threading import local
    if not hasattr(_thread_session, "state"):
        _thread_session.state = local()
    if not hasattr(_thread_session.state, "session"):
        _thread_session.state.session = make_session()
    return _thread_session.state.session


def fetch_one_game(game: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    payload = fetch_summary(_thread_session(), game)
    # The summary-level wallclockAvailable flag is imperfect: one 2025-26
    # regular-season summary has per-play wall clocks despite a false flag.
    has_play_wallclock = any(play.get("wallclock") for play in payload.get("plays", []))
    include_wallclock = game["season"] == 2026 and has_play_wallclock
    return game, play_records(game, payload, include_wallclock), include_wallclock


def play_records(game: dict[str, Any], payload: dict[str, Any], include_wallclock: bool) -> list[dict[str, Any]]:
    rows = []
    for play in payload.get("plays", []):
        period = play.get("period", {})
        team = play.get("team", {})
        # ESPN's summary does not expose possession or clock_running as explicit PBP fields.
        play_wallclock = parse_wallclock(play.get("wallclock")) if include_wallclock else None
        rows.append({
            "game_id": game["espn_game_id"],
            "period": period.get("number") if isinstance(period, dict) else None,
            "clock_s_remaining": parse_clock(play.get("clock")),
            "ts_wall_utc": play_wallclock,
            "action_type": play.get("type", {}).get("text") if isinstance(play.get("type"), dict) else None,
            "team": str(team.get("id")) if team.get("id") is not None else None,
            "score_home": play.get("homeScore"), "score_away": play.get("awayScore"),
            "possession": None, "clock_running": None,
            "event_id": play.get("id"), "text": play.get("text"),
            "season": game["season"], "season_type": game["season_type"],
            "timestamp_source": "ESPN summary plays[].wallclock" if play_wallclock else None,
        })
    return rows


def fetch_cdn_probe(game_id: str) -> str:
    response = requests.get(NBA_CDN.format(game_id=game_id), headers=NBA_HEADERS, timeout=30)
    response.raise_for_status()
    path = RAW / "nba_cdn" / f"playbyplay_{safe_name(game_id)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return str(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2016, 2027)),
                        help="ESPN season IDs; 2016 corresponds to 2015-16")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--schedule-only", action="store_true")
    parser.add_argument("--cdn-probe-game-id")
    args = parser.parse_args()
    if args.cdn_probe_game_id:
        print(fetch_cdn_probe(args.cdn_probe_game_id))
        return
    session = make_session()
    teams = get_teams(session)
    games: dict[str, dict[str, Any]] = {}
    for season in args.seasons:
        games.update(get_schedule(session, season, 2, teams))
    if 2026 in args.seasons:
        games.update(get_schedule(session, 2026, 3, teams))
    schedule_rows = sorted(games.values(), key=lambda g: (g["event_date_utc"] or "", g["espn_game_id"]))
    out = ROOT / "data" / "interim"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(schedule_rows).to_parquet(out / "espn_games.parquet", index=False)
    (out / "espn_games.json").write_text(json.dumps(schedule_rows, indent=2), encoding="utf-8")
    print(f"Cached schedules: {len(schedule_rows)} unique games")
    if args.schedule_only:
        return
    failures = []
    wallclock_available = {"regular": 0, "playoffs": 0}
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for game in schedule_rows:
        grouped.setdefault((game["season"], game["season_type"]), []).append(game)
    for (season, season_type), season_games in sorted(grouped.items()):
        season_dir = out / "espn_pbp" / f"season={season}" / f"season_type={season_type}"
        season_dir.mkdir(parents=True, exist_ok=True)
        for batch_num, start in enumerate(range(0, len(season_games), 50)):
            batch = season_games[start:start + 50]
            rows = []
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(fetch_one_game, game): game for game in batch}
                for future in as_completed(futures):
                    game = futures[future]
                    try:
                        result_game, game_rows, wall_ok = future.result()
                        rows.extend(game_rows)
                        if season == 2026 and wall_ok:
                            key = "playoffs" if season_type == 3 else "regular"
                            wallclock_available[key] += 1
                    except Exception as exc:
                        failures.append({"espn_game_id": game["espn_game_id"], "error": repr(exc)})
            if rows:
                table = pa.Table.from_pylist(rows)
                pq.write_table(table, season_dir / f"batch_{batch_num:04d}.parquet", compression="zstd")
            completed = min(start + len(batch), len(season_games))
            print(f"season={season} type={season_type}: summaries {completed}/{len(season_games)}; actions_written={len(rows)}; failures={len(failures)}", flush=True)
    (out / "espn_pbp_failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    (out / "espn_wallclock_availability.json").write_text(json.dumps(wallclock_available, indent=2), encoding="utf-8")
    print(f"Failed games={len(failures)}; wallclock_available={wallclock_available}")


if __name__ == "__main__":
    main()
