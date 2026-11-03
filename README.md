# Late-game NBA prediction markets

Working thesis and analysis package. [Current draft (PDF)](Current_Thesis_Draft.pdf) · [Word](Current_Thesis_Draft.docx) · [Markdown](Current_Thesis_Draft.md)

## Main final-five results

| Price band / estimator | Price − payoff (pp; nominal 95% CI) | Band cohort rows · games |
|---|---:|---:|
| 5–20¢, game-equal | **+3.44** (+1.74 to +5.03) | 1,681,533 · 684 |
| 5–20¢, pooled trade rows | +1.28 (−2.32 to +4.43) | 1,681,533 · 684 |
| 5–20¢, earliest-timestamp tie-group mean | −0.62 (−3.25 to +1.90) | 1,681,533 · 684 |
| 10–40¢, game-equal | **+7.62** (+5.68 to +9.52) | 2,455,553 · 579 |
| 10–40¢, pooled trade rows | +0.76 (−2.71 to +4.25) | 2,455,553 · 579 |
| 10–40¢, earliest-timestamp tie-group mean | +0.46 (−2.82 to +3.80) | 2,455,553 · 579 |

The earliest-timestamp mean averages 1,918 rows (5–20¢) and 1,230 rows (10–40¢); the other estimators use all band cohort rows.

![Final-five game-equal and pooled estimates across price bands](figures/phase5/final5_estimand_comparison.png)

| Paired contrast | Difference (pp; nominal 95% CI) |
|---|---:|
| 5–20¢: game-equal − pooled | +2.16 (−0.15 to +4.87) |
| 10–40¢: game-equal − pooled | +6.86 (+4.78 to +9.17) |

The 5–20¢ paired contrast includes zero. The 10–40¢ contrast is an unadjusted sensitivity result; the bands overlap and estimator chronology is not fully verified. Price bands cover 684/1,211 (56.5%) and 579/1,211 (47.8%) games with any final-five trade, respectively. Timestamps tie in 322/684 and 200/579 games at the earliest eligible row; see the draft for the tie audit. These are descriptive price-outcome summaries, not evidence of live mispricing or profitability.

At Q4 0:00, 10 focal-band rows and 17,866 rows in the 10–40¢ band occur after the last ESPN Q4 play. Trimming them barely changes the focal result; the broader-band paired contrast remains positive (+6.71 pp, nominal 95% CI +4.57 to +9.04). Because timestamps do not establish whether play had ended, this is a sensitivity check rather than a correction.

## Retrospective selection check

| Venue, final 10 minutes before last play | Observed win rate − price | Model prediction |
|---|---:|---:|
| Kalshi | −6.24 pp | −6.24 pp |
| Polymarket | −6.41 pp | −6.39 pp |

This post-hoc pooled fit is less decisive under equal-game and later-game checks. It is predictive accounting, not causal evidence.

## Other useful materials

- [Analysis and reproduction guide](ANALYSIS_README.md) · [Detailed results](RESULTS.md) · [Polymarket results](RESULTS_POLYMARKET.md)
- [Paired estimator contrasts](data/interim/phase5/phase5_final5_estimand_contrasts.csv) · [Clock-zero sensitivity](data/interim/phase5/phase5_clock_zero_edge_sensitivity.csv) · [Game diagnostics](data/interim/phase5/phase5_final5_game_diagnostics.csv) · [Trade-count deciles](data/interim/phase5/phase5_final5_trade_row_deciles.csv)
- [Weighting-audit code](src/phase5_weighting_audit.py) · [Clock-zero audit code](src/phase5_clock_zero_edge_audit.py) · [Specification status](SPECIFICATION_STATUS.md) · [Corrections and deviations](DEVIATIONS.md)
- [Earlier draft v1](archive/v1_2026-11-03/Current_Thesis_Draft_v1.md) · [Prior draft v2](archive/v2_2026-11-03/Current_Thesis_Draft_v2.md)

The repository contains code and selected summaries but omits approximately 38 GB of raw/intermediate caches. Full reproduction requires the original project workspace inputs.
