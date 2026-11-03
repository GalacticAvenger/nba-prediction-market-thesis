# Senior thesis analysis package

Prepared on November 3, 2026. This repository accompanies `Current_Thesis_Draft.docx` and is intended to make the completed analysis legible and reproducible. The thesis is a working draft; it is not a final submission. Version 1 is preserved in `archive/v1_2026-11-03/`.

## Main finding

For 5–20¢ Kalshi longshot trades in the final five regulation minutes, the equal-game price-minus-payoff estimate is +3.44 percentage points (nominal 95% game-bootstrap CI +1.76 to +5.01; 1,681,533 trades; 684 games). The pooled-trade estimator on those rows is +1.28 (−2.39 to +4.41); the first-entry estimator, using one trade per game, is −0.60 (−3.26 to +1.89). Only the unadjusted equal-game interval excludes zero. Leave-one-game-out game-weighted estimates range from +3.41 to +3.57 points. Because the estimator chronology is not fully documented, treat these intervals as descriptive rather than confirmatory.

The narrower quiet-stoppage estimate is +2.33 points (−0.53 to +4.94; 309,318 trades; 390 games). It is inconclusive, and timeout/restart filters use later event information. Its contrast with the full final-five estimate is descriptive, not a causal stoppage effect. The same-observation gap after estimated taker fees and half-spread is +1.15 points (−1.62 to +3.82; 251,686 quote-valid trades / 376 games); this is counterfactual cost accounting, not realized profit.

A separate post-hoc model predicts the pooled trade-weighted gap in the ten minutes before the final ESPN play on Kalshi and Polymarket. Equal-game and chronological holdout results are less decisive. This is predictive accounting, not causal identification or evidence prices were correct during play.

## Included

- `Current_Thesis_Draft.md` and `.docx`: revised working manuscript. `archive/v1_2026-11-03/` preserves the previous version.
- `RESULTS.md`, `RESULTS_POLYMARKET.md`, `DEVIATIONS.md`: detailed research record, platform results, and corrections. Read the correction notes and supersession labels before using old values.
- `THESIS_STRATEGY.md`, `WALLET_STUDY.md`, `RECON.md`, `PREDICTIONS.md`, `PROSPECTIVE_POLYMARKET_PROTOCOL.md`, `SPECIFICATION_STATUS.md`: design, claim, source, and exploratory-analysis documentation.
- `src/*.py`, including `phase5_final5_longshot_weighting.py`, `phase5_dynamic_timeout_sensitivity.py`, `config.yaml`, `requirements.txt`, and `Makefile`: analysis source and settings. Generated Python bytecode is omitted.
- Final Phase 5 tables and figures, selected machine-readable CSV/JSON summaries for Phase 5 and the later wallet analyses, and `TIMING_SENSITIVITY.json`, the post-hoc dynamic timeout sensitivity output.
- Original proposal PDF for context.

The earlier two-page update and AI-generated research summary are not included as canonical analysis: they are short summaries and the AI summary is not a substitute for the current working draft. Project notes describe the quiet-stoppage estimate as planned, but I have not verified a dated protocol fixing the exact estimator and timeout/restart filters before results. The manuscript discloses this and does not describe the result as independently verified confirmatory evidence.

## Data and reproduction

The source workspace contains approximately 38 GB of raw and intermediate data across roughly 100,000 files. Those caches are not included in this repository. Main market and Polymarket inputs cover the 2025–26 season; ESPN play-by-play training data cover earlier seasons. Reproduction requires the cached files noted in `RESULTS.md` and `RESULTS_POLYMARKET.md`.

With the project’s existing cache in place, run `make phase5` from the project root to regenerate the core Phase 5 analyses, figures, and tables. This cached-data workflow does not fetch source data. Recompute the matched-band final-five weighting comparison with `python src/phase5_final5_longshot_weighting.py --input <path-to-phase5_late_trades.parquet> --output data/interim/phase5/phase5_final5_longshot_weighting.csv` from the release folder. The post-hoc timing sensitivity can be regenerated with `python src/phase5_dynamic_timeout_sensitivity.py --output timing_sensitivity.json`. The wallet-profile analysis can be reproduced from its cached inputs with `make phase6-wallet-execution-style-analysis`, `make phase6-wallet-execution-style-decomposition`, `make phase6-taker-flow-impact`, and `make phase6-wallet-inventory-opportunity`. Targets that retrieve wallet histories or call the Polygon RPC require network access and are not needed to reproduce the main Phase 5 estimates.

No result in this package should be read without its sample definition, weighting, and correction status. In particular:

1. Equal-game, pooled-trade, and first-entry final-five estimates differ materially; the thesis reports them side by side and does not treat them as interchangeable.
2. The Moshrefi comparison is qualified; the observation-count convention is unresolved.
3. Overtime-excluded estimates are invalid for inference because overtime status depends on the realized path.
4. A historical Polymarket winner-mapping error affected earlier residual estimates; only corrected token-based results are current.
5. Market-price-minus-P* results within market-price-selected bands are marked uninterpretable and are excluded from claims.
6. Polymarket account labels are observable proxies; wallet analyses are exploratory, selected, and not causal.

## Quick file map

- `tables/phase5/`: primary estimand, cost, calibration, selection, and sensitivity tables.
- `figures/phase5/`: calibration, primary-estimate, event-response, and selection figures.
- `data/interim/phase5/`: selected CSV/JSON result summaries and analysis caches in the original project; the large Parquet caches are not in this package.
- `data/interim/phase6/`: selected wallet-analysis summaries; complete original cached inputs remain in the project workspace.

## Curvature sample labels

The full-season final-ten-minute Kalshi fit is α=1.526 (95% CI 1.311–1.856; 2,524,781 trades / 1,202 games). The paper-date comparison window (March 1–May 15, 2026) is α=1.674 (95% CI 1.125–2.499; 659,214 trades / 334 games). The paper’s reported 327,473-observation convention remains unreconciled. These are distinct samples; see the corrected opening summary and detailed tables in `RESULTS.md`.
