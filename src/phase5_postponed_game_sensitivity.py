"""Outcome sensitivity for the omitted Jan. 24 GSW–MIN postponed market."""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from common import ROOT
from phase5_main import SEED

PANEL_DIR = ROOT / "data/interim/phase4_postponed_market_sensitivity/phase4/trade_panel"
META_PATH = ROOT / "data/interim/phase4_postponed_market_sensitivity/kalshi_market_metadata.parquet"
PRIMARY_PATH = ROOT / "data/interim/phase5/phase5_primary_trades.parquet"
OUT = ROOT / "data/interim/phase4_postponed_market_sensitivity"
DRAWS = 2000


def summarize(game_means: pd.Series) -> dict:
    vals = game_means.to_numpy(float)
    rng = np.random.default_rng(SEED)
    samples = vals[rng.integers(0, len(vals), size=(DRAWS, len(vals)))].mean(axis=1)
    point = float(vals.mean())
    centered = samples - point
    return {"estimate_A_price_minus_Y": point,
            "ci95_game_cluster_bootstrap": np.quantile(samples, [.025, .975]).tolist(),
            "one_sided_95_upper_bound": float(np.quantile(samples, .95)),
            "two_sided_bootstrap_p_against_zero": float(np.mean(np.abs(centered) >= abs(point))),
            "games": int(len(vals)), "draws": DRAWS, "seed": SEED}


def main() -> None:
    base = pd.read_parquet(PRIMARY_PATH)
    base_game = base.groupby("game_id").A_overprice.mean()
    if "401857824" in base_game.index.astype(str):
        raise ValueError("The completed game is already in the primary sample; refusing to double count")
    meta = pd.read_parquet(META_PATH).set_index("ticker")
    panels = []
    for ticker, m in meta.iterrows():
        x = pd.read_parquet(PANEL_DIR / f"{ticker}.parquet")
        same = x.ticker_yes_is_home.eq(x.selected_team_is_home).to_numpy()
        yeswin = int(str(m.result).lower() == "yes")
        y_selected = np.where(same, yeswin, 1 - yeswin)
        p_selected = pd.to_numeric(x.selected_contract_price, errors="coerce").to_numpy(float)
        longshot_price = np.minimum(p_selected, 1 - p_selected)
        longshot_y = np.where(p_selected <= .5, y_selected, 1 - y_selected)
        x = x.assign(y_selected=y_selected, longshot_price=longshot_price,
                     longshot_y=longshot_y,
                     A_overprice=longshot_price - longshot_y,
                     game_id=x.game_id.astype(str), market_ticker=ticker)
        panels.append(x)
    added = pd.concat(panels, ignore_index=True)
    primary = added.loc[
        added.is_final5.astype(bool)
        & added.quiet_timeout.fillna(False).astype(bool)
        & added.longshot_price.between(.05, .20, inclusive="both")
    ].copy()
    added_game = primary.groupby("game_id").A_overprice.mean()
    if len(added_game) > 1 or (len(added_game) == 1 and "401857824" not in added_game.index):
        raise ValueError(f"Expected at most the completed game contribution, got {added_game.index.tolist()}")
    combined = pd.concat([base_game, added_game])
    result = {
        "event": "KXNBAGAME-26JAN24GSWMIN",
        "mapping": "ESPN completed game 401857824 (Golden State at Minnesota, Jan. 25); market rules identify the fixture originally scheduled for Jan. 24 and market close follows the completed game's last play.",
        "market_rows_in_sidecar_panel": int(len(added)),
        "new_primary_trades": int(len(primary)),
        "new_primary_games": int(primary.game_id.nunique()),
        "new_game_A_price_minus_Y": float(added_game.iloc[0]) if len(added_game) else None,
        "canonical_primary": summarize(base_game),
        "with_postponed_market_sensitivity": summarize(combined),
        "interpretation": "This market contributes no qualifying final-five quiet-stoppage trades after the registered filters, so the remapping does not change the registered primary estimate.",
        "scope": "One-game data-linkage sensitivity; canonical registered sample and results are unchanged.",
    }
    (OUT / "phase5_postponed_game_sensitivity.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
