"""Run season-wide game-weighted Polymarket 6a-lite calibration."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from common import ROOT, write_json
from game_windows import final_regulation_mask, is_overtime
from ingest_polymarket_onchain import TEAM_ALIASES

MAP = ROOT / "data/interim/phase2/polymarket_nba_2025_26_market_map.json"
FILLS = ROOT / "data/interim/phase2/polymarket_maker_fills_season_raw.parquet"
ASSIGN = ROOT / "data/interim/phase4/selected_team_by_game.csv"
OUT = ROOT / "data/interim/phase2"
EDGES = np.array([.03, .05, .10, .20, .35, .50, .65, .80, .90, .97])


def norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def bootstrap_mean(values, rng, draws=2000):
    a = np.asarray(values, dtype=float)
    if not len(a):
        return [None, None]
    samples = rng.choice(a, size=(draws, len(a)), replace=True).mean(axis=1)
    return [float(np.quantile(samples, .025)), float(np.quantile(samples, .975))]


def main():
    mapping = json.loads(MAP.read_text())
    assignments = pd.read_csv(ASSIGN, dtype={"game_id": str})
    assignments["game_id"] = assignments.game_id.astype(str)
    selected = dict(zip(assignments.game_id,
                        assignments.selected_team_is_home.astype(bool)))
    market_by_slug = {m["slug"]: m for m in mapping["markets"]}
    fills = pd.read_parquet(FILLS)
    fills["espn_game_id"] = fills.espn_game_id.astype(str)
    fills["asset"] = fills.asset.astype(str)
    fills["period"] = pd.to_numeric(fills.period, errors="coerce")
    fills["clock_s_remaining"] = pd.to_numeric(fills.clock_s_remaining, errors="coerce")
    fills["price"] = pd.to_numeric(fills.price, errors="coerce")
    fills["size"] = pd.to_numeric(fills["size"], errors="coerce")
    # Delegate classification to the shared Kalshi/Polymarket window helper.
    fills["is_final_regulation_10m"] = final_regulation_mask(
        fills.period.to_numpy(), fills.clock_s_remaining.to_numpy(), 10)
    rows = []
    missing_assignment = set()
    mapping_errors = []
    for slug, part in fills.groupby("slug", sort=False):
        market = market_by_slug[slug]
        gid = str(market["espn_game_id"])
        if gid not in selected:
            missing_assignment.add(gid)
            continue
        home_selected = selected[gid]
        selected_abbr = market["home_team"] if home_selected else market["away_team"]
        event = market["gamma_event"]
        gamma_market = next(x for x in event["markets"]
                            if str(x.get("conditionId", "")).lower() ==
                            str(market["condition_id"]).lower())
        outcomes = json.loads(gamma_market["outcomes"])
        tokens = json.loads(gamma_market["clobTokenIds"])
        outcome_by_token = dict(zip(map(str, tokens), outcomes))
        canonical_abbr = TEAM_ALIASES.get(selected_abbr, selected_abbr.lower())
        team_aliases = {norm(selected_abbr), norm(canonical_abbr)}
        for team in event.get("teams", []):
            if norm(team.get("abbreviation", "")) == norm(canonical_abbr):
                team_aliases.update(norm(team.get(k, "")) for k in ("name", "alias", "abbreviation"))
        chosen_token = next((t for t, outcome in outcome_by_token.items()
                             if norm(outcome) in team_aliases), None)
        if chosen_token is None:
            mapping_errors.append({"slug": slug, "selected_team": selected_abbr,
                                   "outcomes": outcomes})
            continue
        # ESPN uses historical abbreviations for several franchises (GS, NO,
        # NY, SA, UTAH, WSH), while Gamma's resolved winner uses current
        # abbreviations (GSW, NOP, NYK, SAS, UTA, WAS). Compare canonical IDs.
        resolved_abbr = market["resolved_winner_abbreviation"]
        selected_canonical = TEAM_ALIASES.get(selected_abbr, selected_abbr.lower())
        resolved_canonical = TEAM_ALIASES.get(resolved_abbr, resolved_abbr.lower())
        result = int(resolved_canonical == selected_canonical)
        q4 = part[part.is_final_regulation_10m].copy()
        q4["selected_price"] = np.where(q4.asset == chosen_token,
                                        q4.price, 1 - q4.price)
        q4 = q4[(q4.selected_price >= .03) & (q4.selected_price <= .97)].copy()
        if q4.empty:
            continue
        q4["y"] = result
        q4["selected_team"] = selected_abbr
        q4["price_bin"] = pd.cut(q4.selected_price,
                                 EDGES, right=False, include_lowest=True,
                                 labels=False)
        q4.loc[q4.selected_price == .97, "price_bin"] = len(EDGES) - 2
        q4 = q4.dropna(subset=["price_bin"])
        rows.extend(q4[["espn_game_id", "slug", "selected_team", "timestamp",
                        "proxyWallet", "asset", "side", "selected_price", "size",
                        "y", "price_bin"]].to_dict("records"))
    late = pd.DataFrame(rows)
    late.to_parquet(OUT / "polymarket_6a_lite_season_maker_fills.parquet", index=False)
    rng = np.random.default_rng(17)
    per_game = (late.assign(gap=late.y - late.selected_price)
                .groupby("espn_game_id", as_index=False)
                .agg(fills=("selected_price", "size"), mean_price=("selected_price", "mean"),
                     mean_y=("y", "mean"), mean_gap=("gap", "mean"))) if len(late) else pd.DataFrame()
    overall = {
        "games": int(len(per_game)), "maker_fills": int(len(late)),
        "mean_price_game_weighted": float(per_game.mean_price.mean()) if len(per_game) else None,
        "realized_win_rate_game_weighted": float(per_game.mean_y.mean()) if len(per_game) else None,
        "mean_y_minus_price_game_weighted": float(per_game.mean_gap.mean()) if len(per_game) else None,
        "ci95_y_minus_price_game_cluster_bootstrap": bootstrap_mean(per_game.mean_gap, rng) if len(per_game) else [None, None],
    }
    game_bins = (late.assign(gap=late.y - late.selected_price)
                 .groupby(["espn_game_id", "price_bin"], as_index=False)
                 .agg(fills=("selected_price", "size"), mean_price=("selected_price", "mean"),
                      mean_y=("y", "mean"), mean_gap=("gap", "mean")))
    summaries = []
    for b in range(len(EDGES) - 1):
        g = game_bins[game_bins.price_bin == b]
        summaries.append({"price_bin": f"[{EDGES[b]:.2f},{EDGES[b+1]:.2f}{']' if b == len(EDGES)-2 else ')'}",
                          "games": int(g.espn_game_id.nunique()),
                          "maker_fills": int(g.fills.sum()) if len(g) else 0,
                          "game_weighted_mean_price": float(g.mean_price.mean()) if len(g) else None,
                          "game_weighted_win_rate": float(g.mean_y.mean()) if len(g) else None,
                          "game_weighted_gap_y_minus_price": float(g.mean_gap.mean()) if len(g) else None,
                          "gap_ci95_game_cluster_bootstrap": bootstrap_mean(g.mean_gap, rng) if len(g) else [None, None]})
    result = {"definition": "maker fills only; ESPN period 4 with game clock <= 600s; overtime excluded; price in [0.03,0.97]",
              "assignment_file": str(ASSIGN), "assignment_seed": 17,
              "assignment_games": int(assignments.game_id.nunique()),
              "mapped_games_with_rows": int(late.espn_game_id.nunique()) if len(late) else 0,
              "overtime_maker_fills_separate": int(sum(
                  int(count) for period, count in fills.period.value_counts().items()
                  if is_overtime(period))),
              "all_season_maker_rows": int(len(fills)), "late_sample": overall,
              "bins": summaries, "missing_assignment_game_ids": sorted(missing_assignment),
              "outcome_mapping_errors": mapping_errors,
              "bootstrap_draws": 2000, "bootstrap_seed": 17}
    write_json(OUT / "polymarket_6a_lite_season.json", result)
    pd.DataFrame(summaries).to_csv(OUT / "polymarket_6a_lite_season_bins.csv", index=False)
    print(json.dumps({k: v for k, v in result.items() if k != "bins"}, indent=2))


if __name__ == "__main__":
    main()
