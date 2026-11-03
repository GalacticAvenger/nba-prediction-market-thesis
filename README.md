# NBA prediction-market thesis: analysis and working draft

This private repository contains the current working thesis draft, selected paper tables and figures, analysis source code, and compact result summaries for a senior thesis on late-game NBA prediction-market calibration. Raw and intermediate source data are excluded.

## Current status

The manuscript is a working draft for advising discussion, not a final thesis. The main result is a pre-specified, equal-game-weighted Kalshi estimate of price minus realized payoff for 5–20¢ longshots during eligible quiet stoppages in the final five regulation minutes: **+2.33 percentage points** (95% game-bootstrap CI: **−0.53 to +4.94**; 390 games; 309,318 trades; two-sided bootstrap p = 0.0965). The estimate is inconclusive. Its timeout-screening and estimated-restart rules use later event information, so the implemented sample is not fully trade-time-identifiable.

A separate, post-hoc timing sensitivity gives +2.04 points (95% CI: −0.77 to +4.59; 411 games; 343,823 trades). It retains other retrospective filters and is not a replacement for the primary estimate. The realized-end selection analysis is predictive accounting, not causal identification. See the manuscript and `ANALYSIS_README.md` for definitions, caveats, and superseded results.

## Start here

- [Working thesis draft (Markdown)](Current_Thesis_Draft.md)
- [Working thesis draft (Word)](Current_Thesis_Draft.docx)
- [Analysis guide and reproduction limits](ANALYSIS_README.md)
- [Detailed Kalshi results and corrections](RESULTS.md)
- [Polymarket results](RESULTS_POLYMARKET.md)
- [Analysis deviations and superseded estimates](DEVIATIONS.md)

## Tables and figures

Tables are provided as LaTeX source so they can be used in the manuscript. Figures are supplied as PDF for publication workflows, with PNG previews where available.

- Tables: [primary estimate and cost checks](tables/phase5/primary_estimand_band_tests.tex), [paired residuals](tables/phase5/paired_residuals.tex), [weighting sensitivity](tables/phase5/weighting_sensitivity.tex), and [qualified Moshrefi comparison](tables/phase5/replication_5a_d.tex).
- Figures: [primary estimate](figures/phase5/prespecified_primary_estimate.pdf), [calibration](figures/phase5/calibration_market_vs_pstar.pdf), [selection validation](figures/phase5/crossfit_selection_validation.pdf), [curvature by window](figures/phase5/prelec_alpha_by_window.pdf), and [event response and drift](figures/phase5/event_response_and_drift.pdf).

## Reproduction

The repository includes analysis scripts, configuration, compact CSV/JSON summaries, and a Makefile. It does **not** include raw market trades, play-by-play source files, or the full analysis cache (about 38 GB in the working copy). Consequently, most end-to-end targets require the corresponding local cache and cannot be reproduced from a fresh clone alone. See `ANALYSIS_README.md` and the detailed results notes for required inputs. The post-hoc timing sensitivity script is `src/phase5_dynamic_timeout_sensitivity.py`.

No license is included because no distribution license has been selected. The repository is private.
