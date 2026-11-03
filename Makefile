PYTHON ?= python3

.PHONY: all phase1-summary rebuild-pbp-cache phase2 phase3 phase4 phase5 phase5-preflight phase5-clock-shift phase5a-market-side-sensitivity phase5-primary-estimate-figure phase5-primary-influence-diagnostic phase5-crossfit-selection-diagnostic phase5-crossfit-benchmark-sensitivity phase5-polymarket-selection-crossfit phase5-selection-crossfit-figure phase5-temporal-selection-validation phase5-selection-inference-audit phase5-postponed-game-sensitivity phase6-wallet-profiles phase6-wallet-outcomes phase6-wallet-common-support phase6-wallet-profile-sensitivity phase6-wallet-history-sample phase6-wallet-position-sample phase6-wallet-receipt-validation phase6-wallet-balance-validation phase6-wallet-exact-fill-balance-sample phase6-wallet-inventory-extension-history phase6-wallet-inventory-extension-position phase6-wallet-inventory-extension-balance phase6-wallet-inventory-extension-fill phase6-wallet-inventory-extension-summary phase6-wallet-inventory-extension-redemption phase6-wallet-inventory-opportunity phase6-wallet-prior-game-profiles phase6-wallet-prior-profile-sensitivity phase6-wallet-gap-decomposition phase6-taker-flow-impact phase6-wallet-execution-style phase6-wallet-execution-style-analysis phase6-wallet-execution-style-decomposition phase6-prospective-collect phase6-prospective-materialize phase6-prospective-audit

all: phase1-summary rebuild-pbp-cache phase2 phase3 phase4

phase1-summary:
	$(PYTHON) src/summarize_phase1.py

rebuild-pbp-cache:
	$(PYTHON) src/rebuild_pbp_cache.py

phase2:
	$(PYTHON) src/phase2.py
	$(PYTHON) src/phase2_fixes.py
	$(PYTHON) src/phase2_price_lead.py
	$(PYTHON) src/validate_phase2_candles.py
	$(PYTHON) src/summarize_phase2_polymarket.py

phase3:
	$(PYTHON) src/phase3.py
	$(PYTHON) src/summarize_phase3.py

phase4:
	$(PYTHON) src/phase4.py

# Phase 5 consumes cached Phase 1–4 inputs plus the read-only Polymarket
# season fill file/summary. These recipes do not fetch data from the network.
phase5-preflight:
	test -d data/interim/phase4/trade_panel
	test -f data/interim/phase4/selected_team_by_game.csv
	test -f data/interim/phase3/pstar_2025_26_every_second.parquet
	test -d data/interim/espn_pbp/season=2026/season_type=2
	test -f data/interim/phase2/polymarket_maker_fills_season_raw.parquet
	test -f data/interim/phase2/polymarket_nba_2025_26_market_map.json
	test -f data/interim/phase6/polymarket_selection_summary.json

phase5: phase5-preflight
	$(PYTHON) src/phase5a.py
	$(PYTHON) src/phase5_checks.py
	$(PYTHON) src/phase5_main.py
	$(PYTHON) src/phase5_dynamics.py
	$(PYTHON) src/phase5_outcome_selection.py
	$(PYTHON) src/phase5_selection_formula.py
	$(PYTHON) src/phase5_selection_decomposition.py
	$(PYTHON) src/phase5_primary_costs.py
	$(PYTHON) src/phase5_publication.py
	$(PYTHON) src/phase5_weighting_resolution.py
	$(PYTHON) src/phase5_residual_mechanisms.py
	$(PYTHON) src/phase5_residual_outcome_weighting.py
	$(PYTHON) src/phase5_residual_polymarket_matched_estimators.py
	$(PYTHON) src/phase5_calibration_common_coordinates.py
	$(PYTHON) src/phase5_polymarket_overlay.py

# Slow robustness: five isolated Phase 4 rebuilds at -10, -5, 0, +5, +10 sec.
# The canonical Phase 4 panel is not overwritten.
phase5-clock-shift:
	test -f data/interim/phase5/phase5_late_trades.parquet
	$(PYTHON) src/phase5_clock_shift_sensitivity.py

# Diagnostic split of the paper-date, last-play-anchored market YES sample.
phase5a-market-side-sensitivity: phase5-preflight
	$(PYTHON) src/phase5a_market_side_sensitivity.py

phase5-primary-estimate-figure:
	$(PYTHON) src/phase5_primary_figure.py

phase5-primary-influence-diagnostic: phase5-preflight
	$(PYTHON) src/phase5_primary_influence_diagnostic.py

# Out-of-game validation of selection-only calibration adjustment.
phase5-crossfit-selection-diagnostic: phase5-preflight
	$(PYTHON) src/phase5_crossfit_selection_diagnostic.py

phase5-crossfit-benchmark-sensitivity: phase5-preflight
	$(PYTHON) src/phase5_crossfit_benchmark_sensitivity.py

phase5-polymarket-selection-crossfit: phase5-preflight
	$(PYTHON) src/phase5_polymarket_selection_crossfit.py

phase5-selection-crossfit-figure: phase5-crossfit-selection-diagnostic phase5-polymarket-selection-crossfit
	$(PYTHON) src/phase5_plot_selection_crossfit.py

# Post-hoc transportability check: train on early season games, evaluate on late games.
phase5-temporal-selection-validation: phase5-preflight
	$(PYTHON) src/phase5_temporal_selection_validation.py

# Game-weighting and fixed-prediction bootstrap audit of the random-fold OOF result.
phase5-selection-inference-audit:
	$(PYTHON) src/phase5_selection_inference_audit.py

# Isolated in-game data and registered-primary sensitivity for the postponed GSW–MIN fixture.
phase5-postponed-game-sensitivity:
	PYTHONPATH=src $(PYTHON) src/ingest_postponed_market_sensitivity.py
	PHASE4_METADATA_PATH=data/interim/phase4_postponed_market_sensitivity/kalshi_market_metadata.parquet PHASE4_TRADE_INPUT_DIR=data/interim/phase4_postponed_market_sensitivity/kalshi_trades PHASE4_CANDLE_INPUT_DIR=data/interim/phase4_postponed_market_sensitivity/kalshi_candles_1m PHASE4_OUTPUT_DIR=data/interim/phase4_postponed_market_sensitivity/phase4 PHASE4_TICKER_FILTER='KXNBAGAME-26JAN24GSWMIN-MIN,KXNBAGAME-26JAN24GSWMIN-GSW' $(PYTHON) src/phase4.py
	PYTHONPATH=src $(PYTHON) src/phase5_postponed_game_sensitivity.py
	PYTHONPATH=src $(PYTHON) src/phase5_postponed_selection_sensitivity.py

# Outcome-free Polymarket participant profiles and identity/role audit.
phase6-wallet-profiles:
	$(PYTHON) src/phase6_wallet_profiles.py

phase6-wallet-outcomes: phase6-wallet-profiles
	$(PYTHON) src/phase6_wallet_outcomes.py

phase6-wallet-common-support: phase6-wallet-outcomes
	$(PYTHON) src/phase6_wallet_common_support.py

phase6-wallet-profile-sensitivity: phase6-wallet-common-support
	$(PYTHON) src/phase6_wallet_profile_sensitivity.py

# Downloads and caches a fixed stratified sample of full wallet-market histories.
phase6-wallet-history-sample: phase6-wallet-outcomes
	$(PYTHON) src/phase6_wallet_history_sample.py

phase6-wallet-position-sample: phase6-wallet-history-sample
	$(PYTHON) src/phase6_wallet_position_sample.py

phase6-wallet-receipt-validation: phase6-wallet-history-sample
	$(PYTHON) src/phase6_validate_redemption_receipts.py

phase6-wallet-balance-validation: phase6-wallet-position-sample
	$(PYTHON) src/phase6_validate_position_balances.py

phase6-wallet-exact-fill-balance-sample: phase6-wallet-balance-validation
	$(PYTHON) src/phase6_exact_fill_balance_sample.py

# Independent follow-on validation sample. Hash ranks 0–2 formed the original
# sample; ranks 3–7 add up to five new pairs per month/profile/role cell.
phase6-wallet-inventory-extension-history:
	$(PYTHON) src/phase6_wallet_history_sample.py --p6-dir data/interim/phase6/inventory_extension --raw-dir data/raw/polymarket/activity_wallet_market_extension --start-rank 3 --per-cell 5

phase6-wallet-inventory-extension-position: phase6-wallet-inventory-extension-history
	$(PYTHON) src/phase6_wallet_position_sample.py --p6-dir data/interim/phase6/inventory_extension

phase6-wallet-inventory-extension-balance: phase6-wallet-inventory-extension-position
	$(PYTHON) src/phase6_validate_position_balances.py --p6-dir data/interim/phase6/inventory_extension --raw-dir data/raw/polymarket/wallet_preblock_balance_extension

phase6-wallet-inventory-extension-fill: phase6-wallet-inventory-extension-balance
	$(PYTHON) src/phase6_exact_fill_balance_sample.py --p6-dir data/interim/phase6/inventory_extension --raw-dir data/raw/polymarket/wallet_preblock_balance_extension

phase6-wallet-inventory-extension-redemption: phase6-wallet-inventory-extension-history
	$(PYTHON) src/phase6_validate_redemption_receipts.py --p6-dir data/interim/phase6/inventory_extension --raw-dir data/raw/polymarket/wallet_position_receipts_extension

phase6-wallet-inventory-extension-summary: phase6-wallet-inventory-extension-fill phase6-wallet-inventory-extension-redemption
	$(PYTHON) src/phase6_inventory_extension_summary.py

# Strict prior-block inventory versus strictly earlier same-token purchase history.
phase6-wallet-inventory-opportunity:
	$(PYTHON) src/phase6_wallet_inventory_opportunity.py

# Outcome-free wallet behavior measured before each target game starts.
phase6-wallet-prior-game-profiles: phase6-wallet-outcomes
	$(PYTHON) src/phase6_wallet_prior_game_profiles.py

phase6-wallet-prior-profile-sensitivity: phase6-wallet-prior-game-profiles
	$(PYTHON) src/phase6_wallet_prior_profile_sensitivity.py

# Additive profile accounting of selected prior-season Polymarket price gaps.
phase6-wallet-gap-decomposition: phase6-wallet-prior-game-profiles
	$(PYTHON) src/phase6_wallet_gap_decomposition.py

# Whether account-profile taker order flow predicts later benchmark-adjusted price moves.
phase6-taker-flow-impact: phase6-wallet-prior-game-profiles
	$(PYTHON) src/phase6_taker_flow_impact.py

# Transaction-level cadence and ticket-size profiles, outcome-free.
phase6-wallet-execution-style: phase6-wallet-prior-game-profiles
	$(PYTHON) src/phase6_wallet_execution_style.py

phase6-wallet-execution-style-analysis: phase6-wallet-execution-style
	$(PYTHON) src/phase6_wallet_execution_style_analysis.py

phase6-wallet-execution-style-decomposition: phase6-wallet-execution-style
	$(PYTHON) src/phase6_execution_style_gap_decomposition.py

# Prospective public capture of NBA moneyline order books and wallet-linked fills.
phase6-prospective-collect:
	$(PYTHON) src/collect_polymarket_prospective.py

phase6-prospective-materialize:
	$(PYTHON) src/materialize_polymarket_prospective_trades.py

phase6-prospective-audit:
	$(PYTHON) src/audit_polymarket_prospective_coverage.py
