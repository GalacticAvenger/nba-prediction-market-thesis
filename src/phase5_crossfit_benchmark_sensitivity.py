"""Alternative-P* sensitivity for the cross-fitted retrospective selection test."""
from __future__ import annotations

import json
import pandas as pd

from common import ROOT
from phase5_selection_formula import build_phase5_frames
from phase5_crossfit_selection_diagnostic import _oof_selected, _estimate

OUT = ROOT / "data/interim/phase5"
VARIANTS = ("pstar", "pstar_with_possession", "pstar_spline_logistic")
BAND = (.05, .20)
MINUTES = 10
WIDTH = .05
DRAWS = 2000


def main() -> None:
    _frames, original, _weak = build_phase5_frames()
    base = original.loc[original.period.ge(4)].copy()
    base["is_d"] = base.ts.ge(base.end_ts - pd.Timedelta(minutes=MINUTES))
    rows = []
    for variant in VARIANTS:
        d = base.copy()
        d["pstar"] = pd.to_numeric(d[variant], errors="coerce")
        for coord in ("price", "pstar"):
            oof = _oof_selected(d, coord, WIDTH, BAND)
            result = _estimate(oof, d, coord, WIDTH, BAND, draws=DRAWS)
            rows.append({"benchmark": variant, "coordinate": coord,
                         "window_minutes": MINUTES, "market_price_band": list(BAND),
                         "bin_width": WIDTH, **result})
    (OUT / "phase5_crossfit_benchmark_sensitivity.json").write_text(
        json.dumps({"purpose": "Sensitivity of the cross-fitted 10-minute selection diagnostic to alternative P* models.",
                    "method": "Same market-price cohort, window, game folds, bin width, and game-cluster bootstrap; P* benchmark and common-support screen vary together.",
                    "benchmarks": list(VARIANTS), "draws": DRAWS, "results": rows}, indent=2) + "\n")
    pd.DataFrame(rows).to_csv(OUT / "phase5_crossfit_benchmark_sensitivity.csv", index=False)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
