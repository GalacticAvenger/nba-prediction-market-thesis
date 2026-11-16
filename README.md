# Late Game Windows and Longshot Prices in NBA Prediction Markets

This repository contains the analysis code, compact saved outputs, derived game-level files, and figures for a thesis on how NBA late-game price-minus-payoff estimates change with the definition of the game window and the weighting of trades. The main data are 2025–26 Kalshi NBA trades joined to ESPN play-by-play; NHL and Polymarket analyses and a stylized fair-pricing simulation are extensions. The repo does not contain the raw source data or the large intermediate trade panels.

## Sign convention

Throughout the thesis, the reported gap is **A = price − payoff (p − Y)**, in percentage points unless stated otherwise. Positive values mean the trade price exceeded the realized payoff; negative values mean the realized payoff exceeded price. Tables and figures use this convention.

Some retained diagnostic outputs predate the final convention and store **payoff − price (Y − p)**. In particular, this applies to `data/interim/phase5/phase5_main.json` (the `primary_estimand_Y_minus_price` field; the same file also has a separate A field), `phase5a_revised.json`, `phase5_residual_outcome_estimators.csv`, `phase5_weighting/phase5_weighting_estimators.csv` (rows where `metric` is `Y_minus_p`), `phase5_crossfit_selection_diagnostic.json`, `phase5_crossfit_selection_diagnostic_games.csv`, `phase5_selection_inference_audit.json`, and `phase5_paired_window_contrast.json`, `phase5_paired_window_contrast.csv`, and `phase5_paired_window_game_differences.csv`. The paired-window fields explicitly contain `y_minus_p` in their names; the cross-fit files store outcomes-minus-price in `observed_gap`. To express these fields as A, multiply them by −1. Their calibration rates and win/loss selection shares do not use this gap sign convention.

## Thesis table and figure provenance

Each row maps the thesis item to the script and saved output containing its values. Commands assume the repository root as the working directory and the complete local data cache described below. Table 1 is a compiled sample inventory, so its values come from multiple analysis outputs rather than one table-generation script.

| Thesis item | Producing script(s) | Saved values | Rerun command(s) |
|---|---|---|---|
| Table 1 — NBA analysis sample counts | `src/phase5_main.py`; `src/phase5_primary_costs.py` | `data/interim/phase5/phase5_main.json`; `data/interim/phase5/phase5_primary_costs.json` | `python src/phase5_main.py`; `python src/phase5_primary_costs.py` |
| Table 2 — fair-price simulation gaps | `analysis/null_simulation_fair_pricing_2026_11_10.py` | `data/interim/phase5/fair_pricing_null_simulation_2026_11_10.json` | `python analysis/null_simulation_fair_pricing_2026_11_10.py` |
| Table 3 — winner/loser trade shares by price bin | `src/phase5_selection_formula.py` | `data/interim/phase5/phase5_selection_formula.json`; `data/interim/phase5/phase5_selection_formula_bins.csv` | `python src/phase5_selection_formula.py` |
| Table 4 — observed, predicted, and remainder gaps | `src/phase5_crossfit_selection_diagnostic.py`; `src/phase5_selection_inference_audit.py` | `data/interim/phase5/phase5_crossfit_selection_diagnostic.json`; `data/interim/phase5/phase5_selection_inference_audit.json` | `python src/phase5_crossfit_selection_diagnostic.py`; `python src/phase5_selection_inference_audit.py` |
| Table 5 — paired windows and overtime split | `src/phase5_paired_window_contrast.py`; `analysis/additional_estimands_2026_11_10.py` | `data/interim/phase5/phase5_paired_window_contrast.json`; `data/interim/phase5/phase5_paired_window_game_differences.csv`; `data/interim/phase5/additional_estimands_2026_11_10.json` | `python src/phase5_paired_window_contrast.py --project-root . --output-dir data/interim/phase5`; `python analysis/additional_estimands_2026_11_10.py` |
| Table 6 — estimator and weighting comparisons | `src/phase5_weighting_resolution.py`; `analysis/fresh_results_audit_2026_11_10.py` | `data/interim/phase5/phase5_weighting/phase5_weighting_summary.json`; `data/interim/phase5/phase5_weighting/phase5_weighting_estimators.csv`; `data/interim/phase5/fresh_results_audit_2026_11_10.json` | `python src/phase5_weighting_resolution.py`; `python analysis/fresh_results_audit_2026_11_10.py` |
| Table 7 — fixed-clock estimates by mark | `analysis/additional_estimands_2026_11_10.py` | `data/interim/phase5/additional_estimands_2026_11_10.json` (`3_fixed_game_clock_sampling`) | `python analysis/additional_estimands_2026_11_10.py` |
| Table 8 — quiet-stoppage weighting | `src/phase5_weighting_resolution.py`; `src/phase5_primary_costs.py` | `data/interim/phase5/phase5_weighting/phase5_weighting_estimators.csv`; `data/interim/phase5/phase5_primary_costs.json` | `python src/phase5_weighting_resolution.py`; `python src/phase5_primary_costs.py` |
| Table 9 — timestamp shifts and costs | `src/phase5_clock_shift_sensitivity.py`; `src/phase5_primary_costs.py` | `data/interim/phase4_clock_sensitivity/phase5_clock_shift_sensitivity.json`; `data/interim/phase4_clock_sensitivity/phase5_clock_shift_sensitivity.csv`; `data/interim/phase5/phase5_primary_costs.json` | `make phase5-clock-shift`; `python src/phase5_primary_costs.py` |
| Table 10 — NHL windows and weighting | `src/nhl_window_analysis.py` | `data/interim/nhl_2025_26_window_analysis/summary.json`; `game_window_estimates.csv`; `nba_same_dates_game_estimates.csv` in the same directory | `python src/nhl_window_analysis.py` |
| Table B1 — simulation parameters | `analysis/null_simulation_fair_pricing_2026_11_10.py` | `data/interim/phase5/fair_pricing_null_simulation_2026_11_10.json` | `python analysis/null_simulation_fair_pricing_2026_11_10.py` |
| Table B2 — six basketball sensitivity settings | `analysis/null_simulation_sensitivity_sweep_2026_11_10.py` | `data/interim/phase5/fair_pricing_nba_sensitivity_sweep_2026_11_10.json` | `python analysis/null_simulation_sensitivity_sweep_2026_11_10.py` |
| Figure 1 — retrospective-window calibration | `analysis/build_thesis_figures_2026_11_16.py` | `figures/thesis/figure1_retrospective_window_calibration.png` and `.pdf`; plotted values in `figure1_calibration_bins.csv` and `figure1_calibration_curves.csv` | `python analysis/build_thesis_figures_2026_11_16.py` |
| Figure 2 — paired game gaps | `analysis/build_thesis_figures_2026_11_16.py` | `figures/thesis/figure2_paired_games_window_gaps.png` and `.pdf`; plotted game values in `figure2_paired_game_points.csv` | `python analysis/build_thesis_figures_2026_11_16.py` |
| Figure 3 — NBA estimates and simulation means | `analysis/build_thesis_figures_2026_11_16.py` | `figures/thesis/figure3_nba_estimates_and_simulation.png` and `.pdf`; plotted estimates in `figure3_estimates_and_intervals.csv` | `python analysis/build_thesis_figures_2026_11_16.py --figure3-only` |

All three figures, their value CSVs, `figures/thesis/figure_values_manifest.json`, and the Figure 3 retrospective equal-game interval at `data/interim/phase5/retrospective_equal_game_ci_for_figures.json` are included. Figure 1 also depends on `phase5a_bootstrap_bins.csv`; Figure 3 additionally uses the saved cross-fit, inference-audit, weighting, and simulation outputs listed above. NHL game-level estimate and coverage CSVs are included so the NHL sample can be inspected without the trade-level panel.

The close-time diagnostic is an additional analysis, not one of Tables 1–10: run `python src/phase5_close_time_moshrefi_window.py`; its saved results are in `data/interim/phase5/close_time_window_march_midmay_2026.json`.
The P* filter comparison quoted in Section 5.2 of the thesis is saved in `data/interim/phase5/pstar_filter_gap_comparison_2026_11_16.json`; regenerate it with `python analysis/pstar_filter_gap_comparison_2026_11_16.py`.

## Data sources and reproduction

The main season covers 2025–26 games. The ingestion code uses:

- **Kalshi:** `https://api.elections.kalshi.com/trade-api/v2/historical/markets` and `/historical/trades`, with game-specific trade windows matched to ESPN. The close-time diagnostic also retrieves eligible postgame rows through the historical trades route.
- **ESPN:** team schedules and each game’s summary endpoint, `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}`. The saved play-by-play records are from the summary `plays` array.
- **Polymarket:** public `GET https://data-api.polymarket.com/trades`, with Gamma event/market metadata used to map games and outcome tokens. The in-game season collection uses timestamp bounds from ESPN play-by-play.

The original workspace’s raw-cache file modification dates indicate the core Kalshi raw downloads were saved **October 21–November 4, 2026**, ESPN schedules/summaries **October 21–November 4, 2026**, and the Polymarket Data API season cache **October 21, 2026**. The close-time postgame cache was extended on **November 16, 2026**. These are local file-system timestamps; the ingestion outputs do not record a per-request download timestamp. The raw sports data themselves cover the 2025–26 season (ESPN also supplies earlier seasons for P* training). About **38 GB** of raw and intermediate data is not included. Scripts require those files under the same `data/raw/` and `data/interim/` paths used by the source code.

With network access and the full local cache available, the collection commands are:

```bash
python src/ingest_pbp.py --seasons 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025 2026
python src/ingest_kalshi.py
python src/ingest_polymarket_onchain.py
python src/ingest_polymarket_data_api.py
```

Install the pinned environment and use **Python 3.13.2**:

```bash
python3 -m pip install -r requirements.txt
```

`requirements.txt` pins: `requests==2.32.5`, `urllib3==2.5.0`, `pandas==2.2.3`, `pyarrow==21.0.0`, `numpy==2.3.5`, `scipy==1.16.1`, `statsmodels==0.14.5`, `scikit-learn==1.7.2`, `lightgbm==4.6.0`, `numba==0.62.0`, `llvmlite==0.45.0`, `matplotlib==3.10.7`, and `websockets==17.3`.

The documented analysis rerun commands above use cached data. They do not all fetch raw inputs themselves. For the complete legacy Phase 1–5 workflow, see `ANALYSIS_README.md` and `Makefile`; `make phase5` runs the cached Phase 5 pipeline after its input preflight. A clone without the omitted data can inspect the compact JSON/CSV outputs and figures but cannot regenerate every estimate from source trades.

## Additional files included for the final thesis

In addition to the requested scripts and outputs, this branch includes the saved inputs required to reproduce the plotted values and key table values: the fresh-results audit script/output; the one-cent Prelec bins and fit/bootstrap output; selection-formula bins/output; the cross-fit game-level diagnostic CSV and inference audit; the weighting summary/estimates; the primary cost output; timestamp-shift summary; and NHL game-level estimates/coverage. `figures/thesis/figure2_paired_game_points.csv` contains 557 game-level observations; the NHL files contain game-level summaries only. No raw trade-level parquet is added by this update. Files are small derived summaries; the repository is kept below 100 MB.

## Scope and limitations

The selection model and simulation are descriptive tools for checking how a chosen window and weighting rule affect measured price-minus-payoff gaps. The simulation is stylized and is not fitted to play-by-play transitions. NHL and Polymarket results are extensions. None of these outputs alone establishes profitable mispricing or a causal effect of changing the window. See `DEVIATIONS.md` for the chronology of analysis decisions, including choices identified after results were inspected.
