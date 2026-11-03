# Senior thesis analysis package

Prepared November 3, 2026. This repository accompanies `Current_Thesis_Draft.docx` and preserves the earlier manuscript snapshots. Earlier drafts are preserved in `archive/` (v1, v2, and v3).

## Key result and limits

The thesis asks whether a large longshot outcome gap in a window ending at the final ESPN play persists under the project-designated game-clock quiet-stoppage estimate. In the retrospective Kalshi 5–20¢ cohort (532,303 trade rows; 561 games), the observed `Y − price` gap is −6.24 percentage points. Five-fold game-held-out cross-fitting predicts −6.24, but that near-zero pooled remainder is not stable across inference targets: the equal-game remainder is −0.98 (fixed-prediction 95% CI −2.17 to +0.35), and the chronological later-game remainder is +1.89 (−3.68 to +9.41). A parallel Polymarket pooled estimate is similar, but has fewer games and shares ESPN timing/model construction.

The planned final-five quiet-stoppage game-equal estimate is `price − payoff` +2.33 pp (95% CI −0.53 to +4.94; 390 games; p=.0965). After estimated taker fees and half-spread, the same-observation estimate is +1.15 pp (−1.62 to +3.82). These results do not establish a persistent real-time gap or an exploitable strategy. Quiet interval filtering uses some later play-by-play information, and the exact estimator/filter chronology is not independently verified from a dated protocol. The cross-fit is predictive accounting, not causal identification; its strongest result is specific to pooled trades.

Weighting contrasts are secondary: in the full final-five 5–20¢ cohort, the game-equal estimate is +3.44 pp, pooled is +1.28, and their paired contrast is +2.16 (−0.15 to +4.87). The 10–40¢ band overlaps and is unadjusted sensitivity evidence. The earlier first-row-per-game statistic depended on input order when timestamps tied; the replacement averages all rows at each game’s earliest timestamp (1,918 rows in 5–20¢; 1,230 in 10–40¢).

A separate alignment check flags Q4 0:00 rows timestamped after the last ESPN Q4 play: 10 in the focal band and 17,866 in 10–40¢. Trimming them barely changes the focal estimate and moves the broad-band paired contrast to +6.71 pp (95% CI +4.57 to +9.04). This is diagnostic, not a preferred correction, because timestamps alone do not establish when play ended.

## Contents

- `Current_Thesis_Draft.md`, `.docx`, `.pdf`: current working manuscript.
- `archive/`: preserved prior manuscripts.
- `RESULTS.md`, `RESULTS_POLYMARKET.md`, `DEVIATIONS.md`: analysis record, platform results, and corrections.
- `THESIS_STRATEGY.md`, `WALLET_STUDY.md`, `RECON.md`, `PREDICTIONS.md`, `PROSPECTIVE_POLYMARKET_PROTOCOL.md`, `SPECIFICATION_STATUS.md`: research design and data/source documentation.
- `src/*.py`, `config.yaml`, `requirements.txt`, and `Makefile`: analysis source and settings.
- `data/interim/phase5/phase5_crossfit_selection_diagnostic.json`, `phase5_selection_inference_audit.json`, `phase5_temporal_selection_validation.json`, and `phase5_primary_costs.json`: headline retrospective-window, inference, chronological, and planned-primary cost results.
- `data/interim/phase5/phase5_final5_estimand_contrasts.csv`: secondary weighting estimates and paired game-bootstrap contrasts.
- `data/interim/phase5/phase5_final5_estimand_diagnostics.json`: coverage, tie, leave-one-game-out, and trade-count diagnostics.
- `data/interim/phase5/phase5_final5_game_diagnostics.csv`: game-level inputs underlying the weighting summaries.
- `data/interim/phase5/phase5_final5_trade_row_deciles.csv`: exploratory trade-count deciles.
- `data/interim/phase5/phase5_clock_zero_edge_sensitivity.csv`: paired estimates with and without Q4 0:00 rows timestamped after the last ESPN Q4 play.

## Reproduction

The source workspace contains approximately 38 GB of raw/intermediate data, which are not included here. Full reproduction requires those cached inputs. The complete project workspace is required. Reproduce the main Phase 5 analyses with `make phase5`; rerun the focused audits with `make phase5-crossfit-selection-diagnostic`, `make phase5-selection-inference-audit`, and `make phase5-temporal-selection-validation`. With the late-trade panel available, the secondary weighting audit is:

```sh
python src/phase5_weighting_audit.py \
  --input /path/to/phase5_late_trades.parquet \
  --output-dir data/interim/phase5
```

The weighting analysis uses 10,000 paired game-cluster bootstrap draws for each band (seeds 6102126 and 6102127). The optional clock-zero alignment check can be regenerated with `src/phase5_clock_zero_edge_audit.py`, supplying both the late-trade cache and `pbp_derived_regular.parquet`; it uses the same draws and seeds for paired contrasts. Its intervals are nominal and unadjusted. The main repository omits approximately 38 GB of source/intermediate caches, so it does not independently regenerate the complete pipeline.

No result should be interpreted without its sample, outcome, weighting rule, and correction status. In particular, market-price-minus-`P*` estimates within market-price-selected bands are not used as claims; the Moshrefi comparison is not an exact replication; Polymarket account labels are observable proxies; and wallet analyses remain exploratory.
