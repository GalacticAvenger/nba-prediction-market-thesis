"""Recompute the main realized-end selection diagnostic with the remapped game."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from common import ROOT
from phase5_selection_formula import build_phase5_frames
from phase5_crossfit_selection_diagnostic import _oof_selected, _estimate

OUT = ROOT / "data/interim/phase4_postponed_market_sensitivity"
BAND = (.05, .20)


def main() -> None:
    _frames, base, _weak = build_phase5_frames()
    base = base.loc[base.period.ge(4)].copy()
    base["game_id"] = pd.to_numeric(base.game_id).astype("int64")
    base["ts"] = pd.to_datetime(base.ts, utc=True)
    base["end_ts"] = pd.to_datetime(base.end_ts, utc=True)
    panel_dir = OUT / "phase4/trade_panel"
    meta = pd.read_parquet(OUT / "kalshi_market_metadata.parquet").set_index("ticker")
    summary = json.loads((ROOT / "data/raw/espn/summaries/401857824.json").read_text())
    last_play = max(pd.Timestamp(p["wallclock"]) for p in summary["plays"] if p.get("wallclock"))
    pbs = []
    for ticker, market in meta.iterrows():
        x = pd.read_parquet(panel_dir / f"{ticker}.parquet")
        same = x.ticker_yes_is_home.eq(x.selected_team_is_home).to_numpy()
        yeswin = int(str(market.result).lower() == "yes")
        y = np.where(same, yeswin, 1 - yeswin).astype(np.int8)
        pbs.append(pd.DataFrame({
            "game_id": pd.to_numeric(x.game_id).astype("int64"),
            "ts": pd.to_datetime(x.ts_utc, utc=True),
            "end_ts": last_play,
            "period": pd.to_numeric(x.period),
            "price": pd.to_numeric(x.selected_contract_price),
            "pstar": pd.to_numeric(x.selected_contract_pstar),
            "longshot_price": pd.to_numeric(x.longshot_price),
            "y": y,
            "is_d": pd.to_datetime(x.ts_utc, utc=True).ge(last_play - pd.Timedelta(minutes=10)),
        }))
    add = pd.concat(pbs, ignore_index=True)
    add = add.loc[add.period.ge(4)].copy()
    extended = pd.concat([base, add], ignore_index=True)
    specs = {}
    for label, dataset in (("canonical_rebuilt", base), ("with_postponed_market", extended)):
        for width in (.05, .10):
            key = f"price_{width:.2f}"
            oof = _oof_selected(dataset, "price", width, BAND)
            specs[f"{label}_{key}"] = _estimate(oof, dataset, "price", width, BAND)
    result = {
        "event_ticker": "KXNBAGAME-26JAN24GSWMIN",
        "mapping": "originally scheduled Jan. 24 fixture, completed Jan. 25 as ESPN game 401857824",
        "selection_window": "ten wall minutes before the completed game's last ESPN play",
        "last_play_utc": last_play.isoformat(),
        "band": list(BAND), "sidecar_in_game_rows": int(len(add)),
        "sidecar_window_selected_team_band_trades": int(add.loc[add.is_d & add.price.between(*BAND)].shape[0]),
        "sidecar_window_longshot_band_trades": int(add.loc[add.is_d & add.longshot_price.between(*BAND)].shape[0]),
        "specifications": specs,
        "scope": "One-game linkage sensitivity; canonical inputs and registered results are unchanged.",
    }
    (OUT / "phase5_postponed_selection_sensitivity.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
