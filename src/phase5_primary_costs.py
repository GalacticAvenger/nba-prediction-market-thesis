"""Same-observation game-weighted cost comparison for the Phase 5 primary.

Reads the cached Phase 5 primary trade panel only. No network access.
Costs are per longshot contract; half-spread is available only where both
five-second trade-inferred quote sides were observed.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'data/interim/phase5/phase5_primary_trades.parquet'
OUT = ROOT / 'data/interim/phase5'
DRAWS = 2000
SEED = 9142026


def summarize(frame: pd.DataFrame, label: str, include_spread: bool) -> dict:
    cols = ['game_id', 'A', 'taker_fee_large', 'maker_fee_large',
            'taker_fee_observed_size', 'maker_fee_observed_size',
            'net_taker_fee_only_large', 'net_maker_large',
            'net_taker_fee_only_observed_size', 'net_maker_observed_size']
    if include_spread:
        cols += ['half_spread', 'taker_band_large', 'maker_band_large',
                 'taker_band_observed_size', 'maker_band_observed_size',
                 'net_taker_large', 'net_taker_observed_size']
    z = frame[cols].dropna(subset=['game_id']).copy()
    # Match phase5_main.boot_game_means: sorted game IDs and integer-resampled
    # game means, using the same seed, to make the primary A interval identical.
    game = z.groupby('game_id', sort=True)[cols[1:]].mean()
    if game.empty:
        return {'sample': label, 'trades': 0, 'games': 0, 'estimates': {}}
    values = game.to_numpy(float)
    rng = np.random.default_rng(SEED + (0 if label == 'full_sample' else 1))
    draws = rng.integers(0, len(game), size=(DRAWS, len(game)))
    boot = values[draws].mean(axis=1)
    names = list(game.columns)
    point = values.mean(axis=0)
    estimates = {}
    for i, name in enumerate(names):
        entry = {
            'estimate': float(point[i]),
            'ci95': [float(v) for v in np.quantile(boot[:, i], [.025, .975])],
        }
        if name == 'A':
            entry['upper95_one_sided'] = float(np.quantile(boot[:, i], .95))
            centered = boot[:, i] - point[i]
            entry['zero_two_sided_bootstrap_p'] = float(
                np.mean(np.abs(centered) >= abs(point[i])))
        elif name.startswith('net_'):
            centered = boot[:, i] - point[i]
            entry['one_sided_p_net_gt_zero'] = float(
                np.mean(centered >= point[i]))
        estimates[name] = entry
    return {
        'sample': label,
        'trades': int(len(z)),
        'games': int(len(game)),
        'estimates': estimates,
    }


def main() -> None:
    if not INPUT.exists():
        raise FileNotFoundError(f'Missing cached primary sample: {INPUT}')
    d = pd.read_parquet(INPUT)
    if not (d.late5.fillna(False).all()
            and d.quiet_timeout.fillna(False).all()
            and d.in_primary_band.fillna(False).all()):
        raise ValueError('Input contains rows outside the registered final-five quiet 0.05–0.20 primary sample')
    price = pd.to_numeric(d.longshot_price, errors='coerce').to_numpy(float)
    y = pd.to_numeric(d.longshot_y, errors='coerce').to_numpy(float)
    size = pd.to_numeric(d['count'], errors='coerce').to_numpy(float)
    spread = pd.to_numeric(d.quote_spread_5s, errors='coerce').to_numpy(float)
    valid = (d.quote_valid_5s.fillna(False).astype(bool).to_numpy()
             & np.isfinite(spread) & (spread >= 0))

    # Published formulas use a cent ceiling on total order fees. Large-size
    # figures are the no-rounding per-contract limit; observed-size figures
    # apply the ceiling to each source trade's reported contract count.
    pterm = price * (1 - price)
    taker_large = .07 * pterm
    maker_large = .0175 * pterm
    safe_size = np.where(np.isfinite(size) & (size > 0), size, np.nan)
    taker_obs = np.ceil(.07 * pterm * safe_size * 100 - 1e-10) / 100 / safe_size
    maker_obs = np.ceil(.0175 * pterm * safe_size * 100 - 1e-10) / 100 / safe_size
    half = spread / 2

    d = d.copy()
    d['A'] = price - y
    d['taker_fee_large'] = taker_large
    d['maker_fee_large'] = maker_large
    d['taker_fee_observed_size'] = taker_obs
    d['maker_fee_observed_size'] = maker_obs
    d['half_spread'] = np.where(valid, half, np.nan)
    # Net is the observed overpricing A less the cost to execute by selling
    # the longshot at its bid (equivalent side-cost convention to the plan).
    d['net_taker_fee_only_large'] = d.A - d.taker_fee_large
    d['net_maker_large'] = d.A - d.maker_fee_large
    d['net_taker_fee_only_observed_size'] = d.A - d.taker_fee_observed_size
    d['net_maker_observed_size'] = d.A - d.maker_fee_observed_size
    for suffix, tf, mf in [
        ('large', 'taker_fee_large', 'maker_fee_large'),
        ('observed_size', 'taker_fee_observed_size', 'maker_fee_observed_size'),
    ]:
        d[f'taker_band_{suffix}'] = d[tf] + d.half_spread
        d[f'maker_band_{suffix}'] = d[mf]
        d[f'net_taker_{suffix}'] = d.A - d[f'taker_band_{suffix}']
        d[f'net_maker_{suffix}'] = d.A - d[f'maker_band_{suffix}']

    full = summarize(d, 'full_sample', include_spread=False)
    valid_rows = d.loc[valid].copy()
    valid_summary = summarize(valid_rows, 'quote_valid_subset', include_spread=True)
    result = {
        'estimand': 'A = longshot price - realized longshot outcome; game-weighted mean of within-game means',
        'scope': 'final five regulation minutes, quiet stoppage, folded longshot price 0.05-0.20; cached Phase 5 primary rows',
        'units': 'dollars per contract; multiply by 100 for price points per $1 contract',
        'fees': {'taker_rate': .07, 'maker_rate': .0175,
        'rounding': 'large-size is the unrounded formula limit; observed-size row rounding is a conservative per-trade approximation, not an observed fee, because a source row is not proven to equal one fee-assessed order and an order may have multiple fills',
                 'maker_eligibility': 'historical KXNBAGAME eligibility unresolved; maker figures conditional'},
        'quote_rule': 'five-second quote valid only when both inferred sides are observed, uncrossed, and spread is finite/nonnegative',
        'bootstrap': {'cluster': 'game', 'draws': DRAWS, 'seed': SEED, 'interval': 'percentile 95% CI'},
        'primary_full_sample': full,
        'quote_valid_subset': valid_summary,
        'coverage': {
            'trades_total': int(len(d)),
            'trades_quote_valid': int(valid.sum()),
            'trade_share_quote_valid': float(valid.mean()) if len(valid) else None,
            'games_total': int(d.game_id.nunique()),
            'games_quote_valid': int(d.loc[valid, 'game_id'].nunique()),
            'game_share_with_quote_valid_trade': float(
                d.loc[valid, 'game_id'].nunique() / d.game_id.nunique()),
            'median_trade_size_contracts': float(np.nanmedian(size)),
            'trade_rows_missing_positive_size': int((~(np.isfinite(size) & (size > 0))).sum()),
        },
        'interpretation_rule': 'Counterfactual per-contract cost comparison, not realized strategy P&L. Full sample reports A and fee-only components because half-spread is missing on invalid-quote trades; total taker-cost/net estimates are restricted to the same quote-valid observations as A. Net A-cost and its CI resample paired per-game means of A and that same row-level cost.',
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'phase5_primary_costs.json').write_text(json.dumps(result, indent=2))
    rows = []
    for block in ('primary_full_sample', 'quote_valid_subset'):
        s = result[block]
        for measure, v in s['estimates'].items():
            rows.append({'sample': s['sample'], 'measure': measure,
                         'estimate': v['estimate'], 'ci95_low': v['ci95'][0],
                         'ci95_high': v['ci95'][1], 'trades': s['trades'],
                         'games': s['games'],
                         'upper95_one_sided': v.get('upper95_one_sided'),
                         'zero_two_sided_bootstrap_p': v.get('zero_two_sided_bootstrap_p'),
                         'one_sided_p_net_gt_zero': v.get('one_sided_p_net_gt_zero')})
    pd.DataFrame(rows).to_csv(OUT / 'phase5_primary_costs.csv', index=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
