"""Phase 2 diagnostics built from the cached Phase 1 inputs.

This script does not estimate outcome calibration. It derives PBP state and
reports source timing/coverage diagnostics before any event-price alignment.
"""
from __future__ import annotations

import glob
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from common import ROOT
from game_windows import final_regulation_mask

INTERIM = ROOT / "data" / "interim"
OUT = INTERIM / "phase2"


def load_pbp(season_type=2):
    files = glob.glob(str(INTERIM / "espn_pbp" / "season=2026" / f"season_type={season_type}" / "*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True) if files else pd.DataFrame()


def is_made(row):
    text = str(row.get("text") or "").lower()
    return bool(re.search(r"\b(makes|made)\b", text)) and "free throw" not in text


def is_turnover(row):
    return "turnover" in str(row.get("action_type") or "").lower()


def is_made_ft(row):
    typ = str(row.get("action_type") or "").lower()
    return "free throw" in typ and is_made(row)


def is_last_ft(row):
    typ = str(row.get("action_type") or "")
    m = re.search(r"(\d+) of (\d+)", typ)
    return bool(m and int(m.group(1)) == int(m.group(2))) or "1 of 1" in typ


def derive_game(g):
    g = g.sort_values("_ord", kind="stable").copy().reset_index(drop=True)
    # Possession owner is inferred from the event sequence. For a closeout event,
    # use the offense already in possession; a made shot/turnover ends it, while
    # a defensive rebound transfers it. Missing initiations remain explicitly null.
    owner = None
    last_offense = None
    poss_counts = Counter()
    poss_by_row = []
    running_by_row = []
    prior_by_row = []
    previous = None
    stop_words = ("foul", "free throw", "timeout", "substitution", "review", "challenge",
                  "end period", "end game", "jumpball", "violation", "out of bounds")
    for i, r in g.iterrows():
        typ = str(r.action_type or "").lower()
        txt = str(r.text or "")
        team = str(r.team) if pd.notna(r.team) else None
        if "jumpball" in typ:
            # Possession is unknown on the jump itself; the first subsequent
            # offensive action identifies the winner.
            owner = None
        elif "defensive rebound" in typ:
            if owner and team and owner != team:
                poss_counts[owner] += 1
            owner = team
            last_offense = team
        elif "offensive rebound" in typ:
            if owner is None:
                owner = team
        elif is_made(r):
            owner = team or owner
            if owner:
                poss_counts[owner] += 1
                last_offense = owner
            owner = None
        elif is_turnover(r):
            owner = team or owner
            if owner:
                poss_counts[owner] += 1
                last_offense = owner
            owner = None
        elif is_last_ft(r):
            # A missed final FT can continue via offensive rebound. Delay terminal
            # classification until the next action if ESPN provides the rebound.
            owner = team or owner
            if is_made_ft(r) and owner:
                poss_counts[owner] += 1
                last_offense = owner
                owner = None
        elif team and ("shot" in typ or "foul" in typ or "free throw" in typ):
            owner = team
        if owner is None and team and ("shot" in typ or "foul" in typ or "free throw" in typ):
            owner = team
        poss_by_row.append(owner)
        if previous is None:
            running_by_row.append(None)
        else:
            same_period = int(previous.period or 0) == int(r.period or 0)
            dclock = float(previous.clock_s_remaining) - float(r.clock_s_remaining) if pd.notna(previous.clock_s_remaining) and pd.notna(r.clock_s_remaining) else 0
            walldt = (pd.Timestamp(r.ts_wall_utc) - pd.Timestamp(previous.ts_wall_utc)).total_seconds() if pd.notna(r.ts_wall_utc) and pd.notna(previous.ts_wall_utc) else None
            # State at the current event is inferred from the preceding clock
            # decrement, with explicit stoppage actions marked stopped at the event.
            live = same_period and dclock > 0 and not any(w in typ for w in stop_words)
            running_by_row.append(bool(live))
        prior_by_row.append(previous)
        previous = r
    g["possession"] = poss_by_row
    g["clock_running"] = running_by_row
    g["possessions_ending"] = 0
    # Attach inferred terminal possession counts to the game summary; the per-row
    # owner remains the state after each event, not a retroactive owner guess.
    g.attrs["poss_counts"] = dict(poss_counts)
    return g


def clock_quality(pbp):
    p = pbp.dropna(subset=["ts_wall_utc", "clock_s_remaining", "period"]).copy()
    p["wall"] = pd.to_datetime(p.ts_wall_utc, utc=True)
    p = p.sort_values(["game_id", "_ord"], kind="stable")
    p["wall_dt"] = p.groupby("game_id").wall.diff().dt.total_seconds()
    p["prev_clock"] = p.groupby("game_id").clock_s_remaining.shift()
    p["prev_period"] = p.groupby("game_id").period.shift()
    p["game_dt"] = p.prev_clock - p.clock_s_remaining
    p["prev_type"] = p.groupby("game_id").action_type.shift().fillna("").str.lower()
    p["running_pair"] = ((p.period == p.prev_period) & (p.game_dt > 0) & (p.game_dt <= 15) &
                          (p.wall_dt >= 0) & (p.wall_dt <= 25) &
                          ~p.prev_type.str.contains(r"foul|free throw|timeout|review|challenge|substitution|end period|end game|turnover|rebound|violation|jumpball", regex=True))
    batches = p.groupby(["game_id", "wall"]).size()
    ordered = p.groupby("game_id").wall_dt
    # Monotonicity is assessed over every timestamped play, even if the record's
    # game clock is absent. Timing-error summaries below require a valid clock.
    all_wall = pbp.dropna(subset=["ts_wall_utc"]).copy()
    all_wall["wall"] = pd.to_datetime(all_wall.ts_wall_utc, utc=True)
    all_wall = all_wall.sort_values(["game_id", "_ord"], kind="stable")
    all_wall["wall_dt"] = all_wall.groupby("game_id").wall.diff().dt.total_seconds()
    violations = int((all_wall.wall_dt < 0).sum())
    games_any_backwards = int((all_wall[all_wall.wall_dt < 0].groupby("game_id").size() > 0).sum())
    per_game_backwards = all_wall[all_wall.wall_dt < 0].groupby("game_id").size()
    action = p[p.running_pair].copy()
    action["abs_err"] = (action.wall_dt - action.game_dt).abs()
    by_type = action.groupby("action_type").agg(n=("wall_dt", "size"), median_wall_seconds=("wall_dt", "median"), median_game_seconds=("game_dt", "median"), median_abs_difference=("abs_err", "median"), within_2s=("abs_err", lambda s: float((s <= 2).mean()))).sort_values("n", ascending=False)
    summary = {
        "plays_with_wallclock": int(len(p)), "resolution": "1-second (all source strings have no fractional-second field)",
        "monotonicity_violations": violations,
        "games_with_any_monotonicity_violation": games_any_backwards,
        "games_with_more_than_5_violations": int((per_game_backwards > 5).sum()),
        "consecutive_wall_pairs": int(p.wall_dt.notna().sum()),
        "multi_play_timestamps": int((batches > 1).sum()),
        "plays_in_batched_timestamps": int(batches[batches > 1].sum()),
        "batch_fraction_of_timestamp_groups": float((batches > 1).mean()),
        "running_pairs": int(action.shape[0]),
        "running_pairs_abs_error_le_2s": float((action.abs_err <= 2).mean()) if len(action) else None,
        "running_pairs_abs_error_le_5s": float((action.abs_err <= 5).mean()) if len(action) else None,
    }
    return summary, by_type.reset_index()


def timeout_rows(pbp):
    rows = []
    live_words = ("shot", "free throw", "rebound", "turnover", "foul", "jumpball")
    for gid, gg in pbp.groupby("game_id", sort=False):
        gg = gg.sort_values("_ord", kind="stable").reset_index(drop=True)
        records = list(gg.itertuples(index=False))
        for i, r in enumerate(records):
            typ = str(r.action_type or "").lower()
            if "timeout" not in typ:
                continue
            nxt = None
            for j in range(i + 1, len(records)):
                n = records[j]
                ntyp = str(n.action_type or "").lower()
                if int(n.period or 0) != int(r.period or 0):
                    break
                if any(w in ntyp for w in live_words) and pd.notna(n.ts_wall_utc) and pd.notna(n.clock_s_remaining):
                    nxt = n
                    break
            if nxt is None or pd.isna(r.ts_wall_utc) or pd.isna(r.clock_s_remaining):
                continue
            restart = pd.Timestamp(nxt.ts_wall_utc) - pd.Timedelta(seconds=float(r.clock_s_remaining) - float(nxt.clock_s_remaining))
            onset = pd.Timestamp(r.ts_wall_utc)
            segment = records[i + 1:j]
            signal_text = " ".join((str(x.action_type or "") + " " + str(x.text or "")).lower() for x in segment)
            score_changes = any(str(x.score_home) != str(r.score_home) or str(x.score_away) != str(r.score_away) for x in segment)
            flagged = score_changes or any(x in signal_text for x in ("review", "challenge"))
            rows.append({"game_id": str(gid), "period": int(r.period), "clock_s_remaining": float(r.clock_s_remaining), "onset_wall": str(r.ts_wall_utc), "next_live_action": str(nxt.action_type), "next_live_clock": float(nxt.clock_s_remaining), "restart_wall_est": restart.isoformat(), "quiet_seconds_est": (restart - onset).total_seconds(), "excluded_score_review_challenge": bool(flagged), "survives_quiet_rule": bool(not flagged and restart >= onset)})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pbp = load_pbp(2)
    pbp = pbp[pbp.season == 2026].copy()
    # Filter the non-standings NBA Cup final before main-sample state/timeout
    # diagnostics. The four zero-play placeholder fixtures have no rows to keep.
    cup_final_id = "401809839"
    pbp = pbp[pbp.game_id.astype(str) != cup_final_id].copy()
    # The source array is already ordered. Event IDs append a variable-width play
    # sequence to the game ID, so numeric ID sorting is not a safe substitute.
    pbp["_ord"] = pbp.groupby("game_id", sort=False).cumcount()
    # Work game-by-game for state inference, preserving original action records.
    derived_games = []
    poss = []
    for gid, game in pbp.groupby("game_id", sort=False):
        dg = derive_game(game)
        counts = dg.attrs.get("poss_counts", {})
        poss.append({"game_id": gid, "team_a_possessions": sorted(counts.values())[0] if len(counts) >= 2 else None,
                     "team_b_possessions": sorted(counts.values())[-1] if len(counts) >= 2 else None,
                     "total_possessions": sum(counts.values()), "counts_by_team": json.dumps(counts)})
        derived_games.append(dg)
    derived = pd.concat(derived_games, ignore_index=True)
    derived.drop(columns=["_ord"], errors="ignore").to_parquet(OUT / "pbp_derived_regular.parquet", index=False)
    summary, by_type = clock_quality(pbp)
    (OUT / "espn_clock_quality.json").write_text(json.dumps(summary, indent=2))
    by_type.to_csv(OUT / "running_clock_by_action.csv", index=False)
    wall = pbp.dropna(subset=["ts_wall_utc"]).copy()
    wall["wall"] = pd.to_datetime(wall.ts_wall_utc, utc=True)
    wall = wall.sort_values(["game_id", "_ord"], kind="stable")
    wall["wall_dt"] = wall.groupby("game_id").wall.diff().dt.total_seconds()
    backwards = wall[wall.wall_dt < 0].groupby("game_id").size()
    flags = pd.DataFrame({"game_id": wall.game_id.astype(str).unique()}).set_index("game_id")
    flags["backward_steps"] = backwards
    flags["backward_steps"] = flags.backward_steps.fillna(0).astype(int)
    flags["weak_alignment_gt5_backward_steps"] = flags.backward_steps > 5
    flags.reset_index().to_csv(OUT / "alignment_game_flags.csv", index=False)
    summary["global_offset_seconds"] = 0
    summary["global_offset_basis"] = "ESPN and Kalshi timestamps are UTC; no event-response price fit was used."
    summary["weak_alignment_games_gt5_backward_steps"] = int((flags.backward_steps > 5).sum())
    (OUT / "alignment_diagnostics.json").write_text(json.dumps(summary, indent=2))
    tout = timeout_rows(pbp)
    tout.to_csv(OUT / "timeout_intervals.csv", index=False)
    survives = tout[tout.survives_quiet_rule]
    final5 = survives[pd.Series(final_regulation_mask(survives.period, survives.clock_s_remaining, 5), index=survives.index)]
    print(json.dumps({"clock": summary, "timeouts_total": len(tout), "timeouts_survive": len(survives), "timeouts_survive_final_5_regulation": len(final5), "games": pbp.game_id.nunique()}, indent=2))
    pd.DataFrame(poss).to_csv(OUT / "possessions_by_game.csv", index=False)
    # Determine non-standings/phantom fixtures from the 82-game constraint.
    games = pd.read_parquet(INTERIM / "espn_games.parquet")
    season = games[(games.season == 2026) & (games.season_type == 2)].copy()
    season["event_date"] = season.event_date_utc.str[:10]
    cup = season[(season.event_date == "2025-12-17") & (season.home_abbreviation == "NY") & (season.away_abbreviation == "SA")]
    no_clock_regular = {"401810384", "401810499", "401810506", "401810507"}
    drop_ids = no_clock_regular | set(cup.espn_game_id.astype(str))
    kept = season[~season.espn_game_id.astype(str).isin(drop_ids)]
    team_counts = pd.concat([kept.home_abbreviation, kept.away_abbreviation]).value_counts()
    fixture_diag = {"schedule_type2_rows": len(season), "drop_ids": sorted(drop_ids), "cup_final_id": cup.espn_game_id.astype(str).tolist(),
                    "remaining_games": len(kept), "team_game_counts": team_counts.sort_index().to_dict(),
                    "all_teams_exactly_82": bool(len(kept) == 1230 and len(team_counts) == 30 and (team_counts == 82).all())}
    (OUT / "sample_fixtures.json").write_text(json.dumps(fixture_diag, indent=2))
    # Sharper Kalshi semantics: non-overlapping UTC 5s buckets by market, only
    # buckets with both YES- and NO-outcome takers. Compare bucket mean yes_price.
    trade_files = glob.glob(str(INTERIM / "kalshi_trades" / "*.parquet"))
    pair_counts = Counter()
    pair_values = []
    for path in trade_files:
        t = pd.read_parquet(path, columns=["ts_utc", "price", "taker_outcome_side", "is_block_trade"])
        t = t[~t.is_block_trade.fillna(False)].copy()
        if t.empty:
            continue
        t["sec"] = pd.to_datetime(t.ts_utc, utc=True, format="mixed").astype("int64") // 1_000_000_000
        t["window"] = t.sec // 5
        ag = t.groupby(["window", "taker_outcome_side"]).price.agg(["mean", "size"]).unstack("taker_outcome_side")
        if not {"yes", "no"}.issubset(set(ag["mean"].columns)):
            continue
        both = ag["mean"].dropna(subset=["yes", "no"])
        if len(both):
            pair_values.extend(zip(both["yes"].astype(float).tolist(), both["no"].astype(float).tolist()))
    if pair_values:
        arr = np.asarray(pair_values)
        pair_diag = {"method": "non-overlapping 5-second UTC buckets within market; compare mean yes_price for YES taker rows vs NO taker rows; exclude block trades", "windows_with_both_sides": int(len(arr)),
                     "yes_mean_price_greater_share": float((arr[:, 0] > arr[:, 1]).mean()),
                     "equal_share": float((arr[:, 0] == arr[:, 1]).mean()), "yes_mean_price_lower_share": float((arr[:, 0] < arr[:, 1]).mean())}
    else:
        pair_diag = {"windows_with_both_sides": 0}
    (OUT / "kalshi_5s_pairwise.json").write_text(json.dumps(pair_diag, indent=2))
    print(json.dumps({"fixtures": fixture_diag, "kalshi_5s": pair_diag}, indent=2))


if __name__ == "__main__":
    main()
