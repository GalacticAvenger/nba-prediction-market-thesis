"""Sensitivity to outcome-free wallet-profile cutoffs in common support."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from phase6_wallet_common_support import fit_many

ROOT = Path(__file__).resolve().parents[1]
P6 = ROOT / "data/interim/phase6"
INPUT = P6 / "polymarket_wallet_late5_target_trades.parquet"
KEYS = ["game_id", "minute", "pbin", "role"]
OUTCOMES = ("settlement_payoff_minus_cost", "outcome_minus_benchmark")


def common_support(frame: pd.DataFrame, group: str, keys: list[str] = KEYS
                   ) -> tuple[pd.DataFrame, int]:
    support = frame.groupby(keys, observed=True)[group].agg(["min", "max"])
    cells = support.loc[(support["min"] == 0) & (support["max"] == 1)].index
    q = frame.set_index(keys).loc[lambda z: z.index.isin(cells)].reset_index()
    q[group] = q[group].astype(bool)
    return q, len(cells)


def main() -> None:
    df = pd.read_parquet(INPUT)
    df = df.loc[df.high_activity_ge_20_per_active_day.notna()].copy()
    df["minute"] = np.floor((300 - df.clock_s_remaining) / 60).clip(0, 4).astype(int)
    df["pbin"] = pd.cut(df.pstar_own,
                        [0, .05, .10, .15, .20, .25, .30, .40, .50],
                        include_lowest=True, labels=False)
    results = []
    samples = []
    support_definition_sensitivity = []

    for threshold in (20, 100, 500):
        source = f"high_activity_ge_{threshold}_per_active_day"
        q = df.copy()
        q["treated"] = q[source].fillna(False).astype(bool)
        q, cells = common_support(q, "treated")
        fitted, _, _ = fit_many(q, OUTCOMES, "treated",
                                f"high_activity_{threshold}_vs_other", KEYS)
        results.extend(fitted)
        samples.append({"comparison": f"high_activity_{threshold}_vs_other",
                        "eligible_rows": len(df), "support_rows": len(q),
                        "support_cells": cells, "games": q.game_id.nunique(),
                        "wallets": q.wallet.nunique()})

    for threshold in (.50, .75, .90):
        q = df.copy()
        q["treated"] = q.maker_record_share.ge(threshold)
        # Assign the 50% tie to maker-dominant so the groups never overlap.
        taker_cutoff = "lt" if threshold == .50 else "le"
        taker = (q.maker_record_share.lt(1 - threshold) if threshold == .50
                 else q.maker_record_share.le(1 - threshold))
        q = q.loc[q.treated | taker].copy()
        q, cells = common_support(q, "treated")
        comparison = (f"maker_record_share_ge_{threshold:.2f}_vs_maker_record_share_"
                      f"{taker_cutoff}_{1-threshold:.2f}")
        fitted, _, _ = fit_many(q, OUTCOMES, "treated",
                                comparison, KEYS)
        results.extend(fitted)
        samples.append({"comparison": comparison,
                        "eligible_rows": int((df.maker_record_share.ge(threshold)
                                              | taker.reindex(df.index, fill_value=False)).sum()),
                        "support_rows": len(q), "support_cells": cells,
                        "games": q.game_id.nunique(), "wallets": q.wallet.nunique()})

    # Check that profile estimates do not depend on the primary one-minute
    # clock bins and uneven P* bands.
    bin_schemes = {
        "base_5c_then_10c": [0, .05, .10, .15, .20, .25, .30, .40, .50],
        "fine_2_5c": np.round(np.arange(0, .5001, .025), 3).tolist(),
        "coarse_10c": [0, .10, .20, .30, .40, .50],
    }
    for clock_seconds in (60, 30):
        df["timebin"] = np.floor((300 - df.clock_s_remaining) / clock_seconds).clip(
            0, 300 // clock_seconds - 1).astype(int)
        for bin_name, bins in bin_schemes.items():
            df["pbin"] = pd.cut(df.pstar_own, bins, include_lowest=True, labels=False)
            keys = ["game_id", "timebin", "pbin", "role"]
            for comparison in ("high_activity_20_vs_other", "maker_75_vs_taker_75"):
                q = df.copy()
                if comparison.startswith("high_activity"):
                    q["treated"] = q.high_activity_ge_20_per_active_day.fillna(False).astype(bool)
                else:
                    maker = q["maker_record_share_ge_0.75"].fillna(False).astype(bool)
                    taker = q["taker_record_share_ge_0.75"].fillna(False).astype(bool)
                    q = q.loc[maker | taker].copy()
                    q["treated"] = maker.loc[q.index]
                eligible_rows = len(q)
                q, cells = common_support(q, "treated", keys)
                fit, _, _ = fit_many(q, OUTCOMES, "treated", comparison, keys)
                for result in fit:
                    result["clock_bin_seconds"] = clock_seconds
                    result["pstar_bin_scheme"] = bin_name
                results.extend(fit)
                support_definition_sensitivity.append({
                    "comparison": comparison, "clock_bin_seconds": clock_seconds,
                    "pstar_bin_scheme": bin_name, "eligible_rows": eligible_rows,
                    "support_rows": len(q), "support_cells": cells,
                    "games": int(q.game_id.nunique()),
                })

    pd.DataFrame(results).to_csv(P6 / "polymarket_wallet_profile_sensitivity.csv", index=False)
    summary = {
        "design": "Common-support cell fixed-effect contrasts within game, regulation-minute, P* band, and participant role; two-way game/wallet clustered confidence intervals.",
        "outcomes": {"settlement_payoff_minus_cost": "Y-price, purchase outcome minus cost; not wallet P&L",
                     "outcome_minus_benchmark": "Y-P*, calibration residual among selected purchases"},
        "support_by_cutoff": samples,
        "support_definition_sensitivity": support_definition_sensitivity,
        "limits": [
            "These are sensitivity checks for exploratory profile contrasts, not preregistered confirmatory tests.",
            "High-activity groups compare each threshold with all other observed accounts.",
            "Maker/taker profiles are defined from observed in-game NBA participant-record share, not identity or automation.",
            "P* is estimated and the screen is selected on clock, price, side, and P*.",
        ],
    }
    (P6 / "polymarket_wallet_profile_sensitivity.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(pd.DataFrame(results).to_string(index=False))


if __name__ == "__main__":
    main()
