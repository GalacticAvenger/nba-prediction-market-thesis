"""Rematch Gamma NBA events to ESPN games and validate settled winners."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from common import ROOT, write_json
from ingest_polymarket_onchain import INTERIM, RAW, TEAM_ALIASES, gamma_events, make_session, season_games

SLUG_RE = re.compile(r"^nba-([a-z]+)-([a-z]+)-(\d{4}-\d{2}-\d{2})$")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def resolved_team(event):
    markets = event.get("markets") or []
    market = next((m for m in markets if m.get("clobTokenIds")), None)
    if not market:
        return None, "no binary token market"
    try:
        outcomes = json.loads(market["outcomes"])
        prices = [float(x) for x in json.loads(market["outcomePrices"])]
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "unreadable outcomes or resolution prices"
    if len(outcomes) != 2 or len(prices) != 2:
        return None, "not a resolved binary market"
    if not market.get("closed") or market.get("umaResolutionStatus") != "resolved":
        return None, "market not marked resolved"
    if prices.count(max(prices)) != 1 or max(prices) < 0.999:
        return None, "winner is not uniquely resolved to 1"
    winner_label = outcomes[prices.index(max(prices))]
    for team in event.get("teams") or []:
        aliases = {team.get(k) for k in ("name", "alias", "abbreviation")}
        if norm(winner_label) in {norm(a) for a in aliases if a}:
            return str(team.get("abbreviation", "")).upper(), None
    return None, f"resolved outcome {winner_label!r} did not match Gamma team labels"


def espn_final(game_id):
    path = ROOT / "data/raw/espn/summaries" / f"{game_id}.json"
    if not path.exists():
        return None, "missing cached ESPN final summary"
    obj = json.loads(path.read_text())
    plays = obj.get("plays") or []
    end = next((p for p in reversed(plays) if p.get("type", {}).get("text") == "End Game"), None)
    comp = (obj.get("header", {}).get("competitions") or [{}])[0]
    teams = comp.get("competitors") or []
    away = next((t for t in teams if t.get("homeAway") == "away"), None)
    home = next((t for t in teams if t.get("homeAway") == "home"), None)
    if not end or not away or not home:
        return None, "missing ESPN End Game scores or team assignment"
    try:
        away_score, home_score = int(end["awayScore"]), int(end["homeScore"])
    except (TypeError, ValueError, KeyError):
        return None, "invalid ESPN final score"
    winner = away if away_score > home_score else home if home_score > away_score else None
    if winner is None:
        return None, "ESPN final score tied"
    espn_abbr = winner["team"]["abbreviation"].upper()
    canonical = TEAM_ALIASES.get(espn_abbr, espn_abbr.lower()).upper()
    return {"winner_abbreviation": canonical, "espn_winner_abbreviation": espn_abbr,
            "away_score": away_score, "home_score": home_score}, None


def main():
    session = make_session()
    events = gamma_events(session)
    games = season_games()
    event_rows = []
    for event in events:
        m = SLUG_RE.match(event.get("slug", ""))
        if m:
            event_rows.append({"event": event, "teams": frozenset(m.group(1, 2)),
                               "slug_date": pd.Timestamp(m.group(3))})
    markets, unmatched, resolution_failures = [], [], []
    for game in games.itertuples(index=False):
        gid = str(game.espn_game_id)
        away = TEAM_ALIASES.get(game.away_abbreviation, game.away_abbreviation.lower())
        home = TEAM_ALIASES.get(game.home_abbreviation, game.home_abbreviation.lower())
        teamset = frozenset((away, home))
        exact_slug = f"nba-{away}-{home}-{pd.Timestamp(game.event_date_utc).tz_convert('America/New_York').strftime('%Y-%m-%d')}"
        utc_day = pd.Timestamp(game.event_date_utc).tz_convert("UTC").normalize().tz_localize(None)
        et_day = pd.Timestamp(game.event_date_utc).tz_convert("America/New_York").normalize().tz_localize(None)
        candidates = [r for r in event_rows if r["teams"] == teamset
                      and (abs((r["slug_date"] - utc_day).days) <= 1
                           or abs((r["slug_date"] - et_day).days) <= 1)]
        if not candidates:
            unmatched.append({"espn_game_id": gid, "event_name": game.event_name,
                              "reason": "no Gamma event with both teams within +/-1 day in UTC or Eastern"})
            continue
        final, error = espn_final(gid)
        if error:
            unmatched.append({"espn_game_id": gid, "event_name": game.event_name,
                              "reason": error, "candidate_slugs": [x["event"]["slug"] for x in candidates]})
            continue
        qualified = []
        candidate_results = []
        for candidate in candidates:
            win, why = resolved_team(candidate["event"])
            candidate_results.append({"slug": candidate["event"]["slug"], "resolved_winner": win,
                                      "reason": why})
            if win == final["winner_abbreviation"]:
                qualified.append(candidate)
        exact_qualified = [c for c in qualified if c["event"]["slug"] == exact_slug]
        if len(exact_qualified) == 1:
            selected = exact_qualified[0]
        elif qualified:
            scheduled_ts = pd.Timestamp(game.event_date_utc).timestamp()
            def kickoff_distance(candidate):
                value = candidate["event"].get("startTime") or candidate["event"].get("eventDate")
                try:
                    return abs(pd.Timestamp(value).timestamp() - scheduled_ts)
                except (TypeError, ValueError):
                    return float("inf")
            distances = [(kickoff_distance(c), c) for c in qualified]
            best = min(x[0] for x in distances)
            closest = [c for d, c in distances if d == best]
            selected = closest[0] if len(closest) == 1 else None
        else:
            selected = None
        if selected is None:
            unmatched.append({"espn_game_id": gid, "event_name": game.event_name,
                              "reason": "no unique Gamma resolved winner agrees with ESPN final score",
                              "espn_final": final, "candidates": candidate_results})
            continue
        event = selected["event"]
        market = next((m for m in event.get("markets", []) if m.get("clobTokenIds")), None)
        if not market:
            unmatched.append({"espn_game_id": gid, "event_name": game.event_name,
                              "reason": "winner-matched Gamma event has no token market"})
            continue
        tokens = json.loads(market["clobTokenIds"])
        markets.append({"slug": event["slug"], "espn_game_id": gid,
                        "away_team": game.away_abbreviation, "home_team": game.home_abbreviation,
                        "condition_id": market.get("conditionId"), "token_ids": tokens,
                        "market_id": str(market.get("id", "")),
                        "gamma_date": event.get("eventDate"), "exact_slug_match": event["slug"] == exact_slug,
                        "resolved_winner_abbreviation": final["winner_abbreviation"],
                        "espn_final_score": {"away": final["away_score"], "home": final["home_score"]},
                        "resolution_confirmed": True, "gamma_event": event})
        if len(candidates) > 1:
            resolution_failures.append({"espn_game_id": gid, "candidate_count": len(candidates),
                                        "selected": event["slug"], "espn_winner": final["winner_abbreviation"]})
    result = {"gamma_events_seen": len(events), "espn_regular_season_games": len(games),
              "mapped_markets": len(markets), "unmatched_count": len(unmatched),
              "unmatched_games": unmatched, "markets": markets}
    write_json(INTERIM / "polymarket_nba_2025_26_market_map.json", result)
    rematches = [m for m in markets if not m["exact_slug_match"]]
    report = {"exact_slug_matches": sum(m["exact_slug_match"] for m in markets),
              "date_team_rematches": len(rematches), "mapped_and_resolution_confirmed": len(markets),
              "still_unmatched": unmatched}
    write_json(INTERIM / "polymarket_market_rematch_audit.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "still_unmatched"}, indent=2))
    print("unmatched:", json.dumps(unmatched, separators=(",", ":")))


if __name__ == "__main__":
    main()
