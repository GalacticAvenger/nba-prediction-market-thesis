# Late-game NBA prediction markets

Working thesis and analysis package. [Current draft (PDF)](Current_Thesis_Draft.pdf) · [Word](Current_Thesis_Draft.docx) · [Markdown](Current_Thesis_Draft.md)

## Main result: retrospective window vs. game-state test

| Analysis | Estimate (pp; nominal 95% CI) | Sample |
|---|---:|---:|
| Kalshi: observed gap, 10 minutes before last play (`Y − price`) | −6.24 (−8.32 to −3.64) | 532,303 rows · 561 games |
| Cross-fitted prediction of same pooled gap | −6.24 (−8.33 to −3.71) | Held-out games |
| Model-refit pooled remainder | −0.003 (−0.14 to +0.17) | Same target sample |
| Equal-game remainder | −0.98 (−2.17 to +0.35) | Same 561 games |
| Chronological holdout remainder | +1.89 (−3.68 to +9.41) | 161,087 rows · 137 games |
| Planned final-five quiet estimate (`price − payoff`) | +2.33 (−0.53 to +4.94) | 309,318 rows · 390 games |
| Quiet estimate after estimated taker costs and half-spread | +1.15 (−1.62 to +3.82) | 251,686 quote-valid rows · 376 games |

The cross-fitted model reproduces the pooled retrospective gap, but equal-game aggregation, a wider fixed-prediction bootstrap, and a later-game holdout make that fit less decisive. The quiet-stoppage estimate is positive but inconclusive; it does not establish a persistent real-time gap or profitable strategy. Quiet-window cleaning uses some later play-by-play information, and the exact primary estimator/filter chronology is not verified.

![Observed and cross-fitted retrospective-window gaps and sensitivity of the model remainder to weighting and time](figures/phase5/crossfit_selection_validation.png)

## Supporting result: estimates depend on weighting

![Final-five game-equal and pooled estimates across price bands](figures/phase5/final5_estimand_comparison.png)

In the 5–20¢ final-five band, game-equal is +3.44 pp and pooled-trade is +1.28; their paired contrast is +2.16 (−0.15 to +4.87), which includes zero. The separately listed 10–40¢ band overlaps it and is unadjusted sensitivity evidence. Earliest-timestamp summaries average tied rows rather than picking an arbitrary row; see the draft and linked diagnostics for counts.

At Q4 0:00, 10 focal-band rows and 17,866 rows in the 10–40¢ band occur after the last ESPN Q4 play. Trimming them barely changes the focal result; the broader-band paired contrast remains positive (+6.71 pp, nominal 95% CI +4.57 to +9.04). Because timestamps do not establish whether play had ended, this is a sensitivity check rather than a correction.

Polymarket shows a similar pooled observed/predicted gap (−6.41/−6.39 pp), while its equal-game remainder is +2.89 pp (−0.13 to +6.19). This supports a similar pooled accounting pattern, not an independent replication or a causal explanation.

## Other useful materials

- [Analysis and reproduction guide](ANALYSIS_README.md) · [Detailed results](RESULTS.md) · [Polymarket results](RESULTS_POLYMARKET.md)
- [Cross-fit diagnostic](data/interim/phase5/phase5_crossfit_selection_diagnostic.json) · [Inference and weighting audit](data/interim/phase5/phase5_selection_inference_audit.json) · [Chronological validation](data/interim/phase5/phase5_temporal_selection_validation.json)
- [Planned-primary cost results](data/interim/phase5/phase5_primary_costs.json) · [Weighting contrasts](data/interim/phase5/phase5_final5_estimand_contrasts.csv) · [Clock-zero sensitivity](data/interim/phase5/phase5_clock_zero_edge_sensitivity.csv)
- [Cross-fit code](src/phase5_crossfit_selection_diagnostic.py) · [Weighting-audit code](src/phase5_weighting_audit.py) · [Specification status](SPECIFICATION_STATUS.md) · [Corrections and deviations](DEVIATIONS.md)
- [Earlier draft v1](archive/v1_2026-11-03/Current_Thesis_Draft_v1.md) · [Draft v2](archive/v2_2026-11-03/Current_Thesis_Draft_v2.md) · [Draft v3](archive/v3_2026-11-03/Current_Thesis_Draft_v3.md)

The repository contains code and selected summaries but omits approximately 38 GB of raw/intermediate caches. Full reproduction requires the original project workspace inputs.
