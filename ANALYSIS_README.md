# Senior thesis analysis package

Prepared on November 3, 2026. This repository accompanies `Current_Thesis_Draft.docx` and is intended to make the completed analysis legible and reproducible. The thesis is a working draft; it is not a final submission.

## Main conclusion

The pre-specified Kalshi estimate for 5–20¢ longshots traded during quiet stoppages in the final five regulation minutes is +2.33 percentage points for price minus realized payoff (95% game-bootstrap CI −0.53 to +4.94; p=.0965; 309,318 trades; 390 games). The estimate is inconclusive. The 80%-power MDE is 4.61 points. The secondary same-observation gap after estimated taker fee and half-spread is +1.15 points (95% CI −1.62 to +3.82; quote-valid subset: 251,686 rows / 376 games); this is not realized trading profit. The primary sample is clock-based but not fully trade-time-identifiable because whole-timeout exclusions and the restart buffer use later information. A post-hoc timing sensitivity adds 34,505 pre-event trades in 46 games and estimates +2.04 points (10,000-draw game-bootstrap 95% CI −0.77 to +4.59; 343,823 trades; 411 games). It retains other retrospective filters.

A five-fold game-held-out model predicts the pooled trade-weighted gap in the retrospective ten minutes before the last ESPN play: Kalshi observed/predicted Y−price = −6.24/−6.24 points; Polymarket = −6.41/−6.39. The Kalshi equal-game remainder is −0.98 points (95% CI −2.17 to +0.35) and a later 137-game holdout remainder is +1.89 (−3.68 to +9.41). Treat this as a post-hoc predictive accounting result, not causal identification or evidence prices were correct live.

## Included

- `Current_Thesis_Draft.md` and `.docx`: full working manuscript, with methods, results, limitations, and appendices.
- `RESULTS.md`, `RESULTS_POLYMARKET.md`, `DEVIATIONS.md`: detailed research record, platform results, and corrections. Read the correction notes and supersession labels before using old values.
- `THESIS_STRATEGY.md`, `WALLET_STUDY.md`, `RECON.md`, `PREDICTIONS.md`, `PROSPECTIVE_POLYMARKET_PROTOCOL.md`: design, claim, source, and exploratory-analysis documentation.
- `src/*.py`, including `phase5_dynamic_timeout_sensitivity.py`, `config.yaml`, `requirements.txt`, and `Makefile`: analysis source and settings. Generated Python bytecode is omitted.
- Final Phase 5 tables and figures, selected machine-readable CSV/JSON summaries for Phase 5 and the later wallet analyses, and `TIMING_SENSITIVITY.json`, the post-hoc dynamic timeout sensitivity output.
- Original proposal PDF for context.

The earlier two-page update and AI-generated research summary are not included as canonical analysis: they are short summaries and the AI summary is not a substitute for the current working draft. The project files establish an internal pre-specification; an external preregistration record has not been verified. Older research notes use “registered” to refer to the internal locked primary specification.

## Data and reproduction

The source workspace contains approximately 38 GB of raw and intermediate data across roughly 100,000 files. Those caches are not included in this repository. Main market and Polymarket inputs cover the 2025–26 season; ESPN play-by-play training data cover earlier seasons. Reproduction requires the cached files noted in `RESULTS.md` and `RESULTS_POLYMARKET.md`.

With the project’s existing cache in place, run `make phase5` from the project root to regenerate the core Phase 5 analyses, figures, and tables. This cached-data workflow does not fetch source data. The post-hoc timing sensitivity can be regenerated with `python src/phase5_dynamic_timeout_sensitivity.py --output timing_sensitivity.json`. The wallet-profile analysis can be reproduced from its cached inputs with `make phase6-wallet-execution-style-analysis`, `make phase6-wallet-execution-style-decomposition`, `make phase6-taker-flow-impact`, and `make phase6-wallet-inventory-opportunity`. Targets that retrieve wallet histories or call the Polygon RPC require network access and are not needed to reproduce the main pre-specified estimate.

No result in this package should be read without its sample definition, weighting, and correction status. In particular:

1. The pre-specified primary is equal-game weighted and uses price minus realized payoff.
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
