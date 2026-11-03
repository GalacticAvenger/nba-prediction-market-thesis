# Senior thesis analysis package

Prepared November 3, 2026. This repository accompanies `Current_Thesis_Draft.docx` and preserves the earlier manuscript snapshots. Version 1 is in `archive/v1_2026-11-03/`; the draft immediately before the current weighting/tie revision is in `archive/v2_2026-11-03/`.

## Key result and limits

The final-five 5–20¢ sample has a +3.44 pp game-equal estimate (nominal 95% game-bootstrap CI +1.74 to +5.03; 1,681,533 rows; 684 games) and +1.28 pp pooled-trade estimate (−2.32 to +4.43). Their paired contrast is +2.16 pp (−0.15 to +4.87), which includes zero. In the separately listed 10–40¢ band, the estimates are +7.62 game-equal and +0.76 pooled; the paired contrast is +6.86 (+4.78 to +9.17). This latter interval is an unadjusted sensitivity result, not independent confirmation. The bands overlap. Both estimands condition on a game having at least one eligible final-five trade.

The earlier first-row-per-game estimate depended on input row order when multiple trades shared the earliest timestamp. The revised tie-group mean averages all rows at that timestamp before averaging across games: 1,918 earliest-timestamp rows in the 5–20¢ cohort and 1,230 in 10–40¢. Timestamp precision does not identify within-timestamp order. The full cohort counts (1,681,533 and 2,455,553) apply to the game-equal and pooled estimators.

A separate alignment sensitivity check finds 10 Q4 0:00 rows in the focal band and 17,866 in 10–40¢ after the last ESPN Q4 play. Trimming those rows leaves the focal contrast unchanged; the 10–40¢ contrast moves from +6.86 to +6.71 pp (nominal 95% CI +4.57 to +9.04). The trim is diagnostic because these timestamps alone do not establish when play ended.

The separate quiet-stoppage estimate is +2.33 pp (−0.53 to +4.94; 309,318 trade rows; 390 games); its timeout/restart filters use some later event information. The retrospective-end cross-fit is post hoc. None of these establishes live mispricing, causal effects, or realized profitability.

## Contents

- `Current_Thesis_Draft.md`, `.docx`, `.pdf`: current working manuscript.
- `archive/`: preserved prior manuscripts.
- `RESULTS.md`, `RESULTS_POLYMARKET.md`, `DEVIATIONS.md`: analysis record, platform results, and corrections.
- `THESIS_STRATEGY.md`, `WALLET_STUDY.md`, `RECON.md`, `PREDICTIONS.md`, `PROSPECTIVE_POLYMARKET_PROTOCOL.md`, `SPECIFICATION_STATUS.md`: research design and data/source documentation.
- `src/*.py`, `config.yaml`, `requirements.txt`, and `Makefile`: analysis source and settings.
- `data/interim/phase5/phase5_final5_estimand_contrasts.csv`: both bands’ estimates and paired game-bootstrap contrasts.
- `data/interim/phase5/phase5_final5_estimand_diagnostics.json`: coverage, tie, leave-one-game-out, and trade-count diagnostics.
- `data/interim/phase5/phase5_final5_game_diagnostics.csv`: game-level inputs underlying the weighting summaries.
- `data/interim/phase5/phase5_final5_trade_row_deciles.csv`: exploratory trade-count deciles.
- `data/interim/phase5/phase5_clock_zero_edge_sensitivity.csv`: paired estimates with and without Q4 0:00 rows timestamped after the last ESPN Q4 play.

## Reproduction

The source workspace contains approximately 38 GB of raw/intermediate data, which are not included here. Full reproduction requires those cached inputs. With the Phase 5 late-trade panel available, run:

```sh
python src/phase5_weighting_audit.py \
  --input /path/to/phase5_late_trades.parquet \
  --output-dir data/interim/phase5
```

The weighting analysis uses 10,000 paired game-cluster bootstrap draws for each band (seeds 6102126 and 6102127). The optional clock-zero alignment check can be regenerated with `src/phase5_clock_zero_edge_audit.py`, supplying both the late-trade cache and `pbp_derived_regular.parquet`; it uses the same draws and seeds for paired contrasts. Its percentile intervals are nominal and not adjusted for multiple comparisons. The weighting identity is descriptive, not causal. Other core Phase 5 analyses can be regenerated with `make phase5` from the complete project workspace; this release copy alone does not contain all inputs needed by that target.

No result should be interpreted without its sample, outcome, weighting rule, and correction status. In particular, market-price-minus-`P*` estimates within market-price-selected bands are not used as claims; the Moshrefi comparison is not an exact replication; Polymarket account labels are observable proxies; and wallet analyses remain exploratory.
