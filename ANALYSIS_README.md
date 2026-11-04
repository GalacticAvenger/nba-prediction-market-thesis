# Senior thesis analysis package

Prepared November 3, 2026. This repository contains analysis code, selected result summaries, and figures for late-game NBA prediction-market research.

## Findings

In the 5–20¢ Kalshi cohort, the ten wall-clock minutes before the final ESPN play contain 532,303 trade rows in 561 games. The pooled `Y − price` gap is −6.24 percentage points. Five-fold game-held-out cross-fitting predicts −6.24, but the estimated remainder depends on the aggregation and validation method: equal-game remainder −0.98 (fixed-prediction 95% CI −2.17 to +0.35), fixed-prediction pooled remainder −0.003 (−2.20 to +2.67), and chronological later-game remainder +1.89 (−3.68 to +9.41). The model-refit bootstrap interval for the pooled remainder is much narrower (−0.14 to +0.17); it is a separate inference sensitivity, not a replacement for the fixed-prediction interval.

A matched-game calculation compares the retrospective window with the final five regulation minutes. It uses the same 5–20¢ price band, market/`P*` support, and only games with trades in both samples. In 557 games, the game-equal mean of `Y − price` is −6.68 in the retrospective window and −2.79 in the regulation-clock window; the paired difference is +3.89 points (95% CI +2.16 to +5.67). The median within-game difference is −0.09, and 29% of games have a positive difference. A five-minute realized-end window gives a +7.03-point mean difference, with a −1.10-point median. These means compare different trade rows and game states; they do not identify a causal window effect.

The ten-minute matched difference falls to +0.56 points (−0.16 to +1.30) after excluding games that reached overtime. This is a diagnostic only because overtime status depends on the realized game path. It cannot be used as a confirmatory estimate or preferred correction.

The separate project-designated final-five quiet-stoppage game-equal estimate is `price − payoff` +2.33 points (95% CI −0.53 to +4.94; 390 games; bootstrap p=.0965). On the same quote-valid observations, estimated taker fees and half-spread leave +1.15 points (−1.62 to +3.82; 376 games). These estimates do not establish a persistent or profitable live gap. The quiet interval screen uses later play-by-play, clock alignment has an unknown common lag, and no dated protocol verifies the exact outcome estimator and timeout/restart filters.

Weighting contrasts are secondary. In the full final-five 5–20¢ cohort, the game-equal estimate is +3.44 points and the pooled estimate is +1.28; their paired contrast is +2.16 (−0.15 to +4.87), which includes zero. This cohort does not apply the `P*` common-support filter used in the matched-window analysis. The 10–40¢ band overlaps the focal band and is an unadjusted sensitivity. The earliest-timestamp estimate averages all tied rows (1,918 rows in 5–20¢; 1,230 in 10–40¢), rather than selecting one row by input order.

## Files

- `RESULTS.md`, `RESULTS_POLYMARKET.md`, `DEVIATIONS.md`: detailed results, venue checks, and corrections.
- `WALLET_STUDY.md`, `RECON.md`, `PREDICTIONS.md`, `PROSPECTIVE_POLYMARKET_PROTOCOL.md`, `SPECIFICATION_STATUS.md`: project design and source documentation.
- `src/*.py`, `config.yaml`, `requirements.txt`, and `Makefile`: analysis code and settings.
- `data/interim/phase5/phase5_crossfit_selection_diagnostic.json`, `phase5_selection_inference_audit.json`, `phase5_temporal_selection_validation.json`, `phase5_paired_window_contrast.json`, and `phase5_primary_costs.json`: main result summaries.
- `phase5_paired_window_game_differences.csv`: one row per game and window pair, used for the empirical distribution figure.

## Reproduction

The repository omits approximately 38 GB of raw and intermediate source data. The included summaries and figures can be reviewed from a clone, but complete reproduction requires the original project workspace and its `data/raw/` and `data/interim/` inputs. From that workspace, rerun the paired comparison and save its compact outputs into this repository with:

```sh
python github_release/src/phase5_paired_window_contrast.py \
  --project-root . \
  --output-dir github_release/data/interim/phase5
```

The paired window bootstrap resamples the common games jointly for each pair of window estimates (20,000 draws; fixed seeds recorded in the JSON). The source script records per-game differences, the mean and median paired difference, and an overtime-excluded diagnostic. The latter is labeled as post-outcome-selected and is not used for confirmatory inference. The ECDF figure displays the full per-game distribution without smoothing or trimming.

The retrospective cross-fit, inference audit, and chronological validation can be rerun with `make phase5-crossfit-selection-diagnostic`, `make phase5-selection-inference-audit`, and `make phase5-temporal-selection-validation` in the full source workspace. The weighting audit uses 10,000 paired game-bootstrap draws (seeds 6102126 and 6102127). Its intervals are nominal and are not adjusted across price bands or estimands.

No result should be read without its sample, outcome, weighting rule, and status. Market-price-minus-`P*` estimates within market-price-selected bands are not used as findings; the Moshrefi comparison is not an exact replication; Polymarket account labels are observable proxies; and wallet analyses remain exploratory.
