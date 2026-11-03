"""Audit the Moshrefi comparison under one-team-market vs both-team-market counts.

The preprint's near-expiry reference count is close to half the current
regular-season market-YES sample. This sensitivity splits the same paper-date,
last-play-anchored, final-ten-wall-minute sample by whether the market's YES
team is home or away. It is diagnostic only; it does not assume which unit
the preprint used.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from phase5a import META, PANEL, OUT, PAPER_START, PAPER_END, pbp_last, summarize

SEED = 5132026


def main() -> None:
    meta = pd.read_parquet(META)
    meta = meta.loc[(meta.season == 2026) & (meta.season_type == 2)].copy()
    meta["result"] = meta.result.astype(str).str.lower()
    meta = meta.loc[meta.result.isin({"yes", "no"})].set_index("ticker", drop=False)
    last = pbp_last()
    chunks = []
    for ticker, market in meta.iterrows():
        path = PANEL / f"{ticker}.parquet"
        if not path.exists():
            continue
        frame = pd.read_parquet(path, columns=[
            "game_id", "ts_utc", "ticker_yes_is_home",
            "selected_team_is_home", "selected_contract_price",
        ])
        frame["game_id"] = frame.game_id.astype(str)
        frame["timestamp"] = pd.to_datetime(frame.ts_utc, utc=True, errors="coerce")
        frame["last_play"] = frame.game_id.map(last)
        frame["ticker_yes_is_home"] = frame.ticker_yes_is_home.fillna(False).astype(bool)
        frame["selected_team_is_home"] = frame.selected_team_is_home.fillna(False).astype(bool)
        frame["selected_price"] = pd.to_numeric(frame.selected_contract_price, errors="coerce")
        keep = (
            frame.last_play.notna() & frame.timestamp.notna()
            & frame.timestamp.lt(frame.last_play)
            & frame.timestamp.ge(frame.last_play - pd.Timedelta(minutes=10))
            & frame.timestamp.ge(PAPER_START) & frame.timestamp.lt(PAPER_END)
            & frame.selected_price.gt(0) & frame.selected_price.lt(1)
        )
        frame = frame.loc[keep].copy()
        if frame.empty:
            continue
        same_team = frame.ticker_yes_is_home.eq(frame.selected_team_is_home)
        frame["price"] = np.where(same_team, frame.selected_price, 1 - frame.selected_price)
        frame["y"] = int(market.result == "yes")
        chunks.append(frame[["game_id", "price", "y", "ticker_yes_is_home"]])

    sample = pd.concat(chunks, ignore_index=True)
    result = {
        "window": "regular season; Mar 1 through May 15, 2026; final 10 wall-clock minutes before last ESPN play",
        "price_coordinate": "market YES price and market YES settlement outcome",
        "counting_note": "Home-YES and away-YES partitions are diagnostic sensitivities. The reference row definition is not verified, and no side is selected as the primary reproduction.",
        "bootstrap_draws": 2000,
        "bootstrap_cluster": "game",
        "seed": SEED,
        "partitions": {},
    }
    for name, mask in (
        ("combined", np.ones(len(sample), dtype=bool)),
        ("home_yes", sample.ticker_yes_is_home.to_numpy(dtype=bool)),
        ("away_yes", ~sample.ticker_yes_is_home.to_numpy(dtype=bool)),
    ):
        part = sample.loc[mask, ["game_id", "price", "y"]]
        summary, _ = summarize(
            part, name, draws=2000,
            rng=np.random.default_rng(SEED),
        )
        iso = summary.get("isotonic", {})
        result["partitions"][name] = {
            "trades": summary.get("trades"),
            "games": summary.get("games"),
            "alpha": iso.get("alpha"),
            "alpha_ci95": iso.get("bootstrap", {}).get("alpha_ci95"),
            "beta": iso.get("beta"),
            "beta_ci95": iso.get("bootstrap", {}).get("beta_ci95"),
        }

    output = OUT / "phase5a_market_side_sensitivity.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
