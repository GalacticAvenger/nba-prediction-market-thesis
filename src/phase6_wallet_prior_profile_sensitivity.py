"""One-at-a-time threshold sensitivity for prior-game wallet profiles."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from phase6_wallet_prior_game_profiles import OUT as PROFILE_OUT, estimate_contrast

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROFILE_OUT / "prior_behavior_profile_threshold_sensitivity.csv"
SUMMARY = PROFILE_OUT / "prior_behavior_profile_threshold_sensitivity.json"


def classify(frame: pd.DataFrame, min_records: int, activity_cut: float,
             dominance_cut: float) -> pd.Series:
    n = frame.prior_activity_records
    games = frame.prior_games
    rate = frame.prior_records_per_active_day
    maker = frame.prior_maker_record_share
    labels = pd.Series("established_mixed", index=frame.index, dtype="string")
    limited = n.lt(min_records) | games.lt(3)
    labels.loc[limited] = "limited_prior_history"
    high = ~limited & rate.ge(activity_cut)
    labels.loc[high] = "high_prior_activity"
    maker_dom = ~limited & ~high & maker.ge(dominance_cut)
    taker_dom = ~limited & ~high & maker.le(1 - dominance_cut)
    labels.loc[maker_dom] = "maker_record_dominant"
    labels.loc[taker_dom] = "taker_record_dominant"
    return labels


def main() -> None:
    frame = pd.read_parquet(PROFILE_OUT / "target_buys_with_prior_game_profiles.parquet")
    specs = [("base", 20, 20, .75),
             ("min_history_10", 10, 20, .75),
             ("min_history_50", 50, 20, .75),
             ("activity_10", 20, 10, .75),
             ("activity_50", 20, 50, .75),
             ("dominance_70pct", 20, 20, .70),
             ("dominance_90pct", 20, 20, .90)]
    rows = []
    for label, min_records, activity_cut, dominance_cut in specs:
        profile = classify(frame, min_records, activity_cut, dominance_cut)
        contrasts = [
            ("limited_vs_established", profile.eq("limited_prior_history"),
             ~profile.eq("limited_prior_history")),
            ("high_activity_vs_other_established", profile.eq("high_prior_activity"),
             ~profile.isin(["limited_prior_history", "high_prior_activity"])),
            ("maker_vs_taker_dominant_established", profile.eq("maker_record_dominant"),
             profile.eq("taker_record_dominant")),
        ]
        for comparison, treated, control in contrasts:
            estimates = estimate_contrast(
                frame, label, treated, control, comparison)
            for result in estimates:
                rows.append({"specification": label,
                             "min_prior_records": min_records,
                             "high_activity_records_per_day": activity_cut,
                             "maker_or_taker_dominance_cutoff": dominance_cut,
                             **result})
    result = pd.DataFrame(rows)
    result.to_csv(OUTPUT, index=False)
    summary = {
        "design": "One-at-a-time changes to the researcher-defined prior-history, activity-intensity, and maker/taker dominance thresholds. Same game × minute × P* band × participant-role common-support estimator and game/wallet clustered uncertainty as main analysis.",
        "specifications": [{"name": n, "min_prior_records": m,
                            "high_activity_records_per_day": a,
                            "dominance_cutoff": d} for n, m, a, d in specs],
        "n_estimates": int(len(result)),
        "limits": [
            "This is exploratory threshold sensitivity, not a multiplicity-adjusted confirmatory test.",
            "All profile labels remain based on the assembled NBA-market history and do not identify bots, retail, professionals, or causal price impact.",
        ],
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
