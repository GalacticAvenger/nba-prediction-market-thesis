"""Rebuild the registered Phase 5 primary under constant ESPN wall-time shifts.

Offsets move all ESPN wall timestamps later relative to unchanged Kalshi trade
timestamps. Each Phase 4 rebuild writes to an isolated output directory. The
registered game-weighted primary and same-quote cost comparison are then
recomputed from that panel. This is a researcher-chosen sensitivity grid, not
an estimate of ESPN's absolute lag.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / 'data/interim'
OUT = INTERIM / 'phase5'
SENS_DIR = INTERIM / 'phase4_clock_sensitivity'
OFFSETS = (-10, -5, 0, 5, 10)
DRAWS = 2000
SEED = 9142026


def clustered_summary(frame: pd.DataFrame, offset: int, quote_valid: bool) -> dict:
    z = frame
    if quote_valid:
        z = z.loc[z.quote_valid_5s].copy()
    if z.empty:
        return {'trades': 0, 'games': 0}
    game = z.groupby('game_id', sort=True)[['A', 'cost']].mean()
    vals = game.to_numpy(float)
    rng = np.random.default_rng(SEED + (1 if quote_valid else 0))
    ids = rng.integers(0, len(game), size=(DRAWS, len(game)))
    boot = vals[ids].mean(axis=1)
    point = vals.mean(axis=0)
    net = vals[:, 0] - vals[:, 1]
    net_draw = boot[:, 0] - boot[:, 1]
    centered = net_draw - net.mean()
    result = {
        'trades': int(len(z)), 'games': int(len(game)),
        'A': {'estimate': float(point[0]), 'ci95': np.quantile(boot[:, 0], [.025, .975]).tolist()},
    }
    if quote_valid:
        result.update({
            'taker_cost_including_half_spread': {
                'estimate': float(point[1]), 'ci95': np.quantile(boot[:, 1], [.025, .975]).tolist()},
            'A_minus_cost': {
                'estimate': float(net.mean()), 'ci95': np.quantile(net_draw, [.025, .975]).tolist(),
                'one_sided_p_net_gt_zero': float(np.mean(centered >= net.mean())),
            },
        })
    else:
        result['A_upper95_one_sided'] = float(np.quantile(boot[:, 0], .95))
    return result


def build_primary(panel_dir: Path, offset: int) -> tuple[pd.DataFrame, dict]:
    meta = pd.read_parquet(INTERIM / 'kalshi_market_metadata.parquet')
    meta = meta[(meta.season == 2026) & (meta.season_type == 2)].copy()
    meta['ticker'] = meta.ticker.astype(str)
    meta['result'] = meta.result.astype(str).str.lower()
    result_by_ticker = dict(zip(meta.ticker, meta.result))

    pieces = []
    files = sorted(panel_dir.glob('*.parquet'))
    for i, path in enumerate(files, 1):
        d = pd.read_parquet(path, columns=[
            'game_id', 'market_ticker', 'trade_id', 'ts_utc', 'selected_team_is_home',
            'ticker_yes_is_home', 'selected_contract_price', 'longshot_price',
            'quiet_timeout', 'is_final5', 'count'])
        if d.empty:
            continue
        d = d.loc[d.is_final5.fillna(False) & d.quiet_timeout.fillna(False)].copy()
        d = d.loc[d.longshot_price.between(.05, .20, inclusive='both')].copy()
        if d.empty:
            continue
        y_yes = d.market_ticker.astype(str).map(result_by_ticker).eq('yes').to_numpy(dtype=np.int8)
        same = (d.selected_team_is_home.fillna(False).to_numpy(bool)
                == d.ticker_yes_is_home.fillna(False).to_numpy(bool))
        y_selected = np.where(same, y_yes, 1 - y_yes)
        price = pd.to_numeric(d.selected_contract_price, errors='coerce').to_numpy(float)
        y_longshot = np.where(price <= .5, y_selected, 1 - y_selected)
        d['A'] = d.longshot_price.to_numpy(float) - y_longshot
        pieces.append(d[['game_id', 'market_ticker', 'trade_id', 'A', 'longshot_price']])
        if i % 500 == 0:
            print(f'offset {offset:+d}: scanned {i}/{len(files)} markets', flush=True)
    if not pieces:
        raise RuntimeError(f'No primary observations for offset {offset:+d}')
    primary = pd.concat(pieces, ignore_index=True)
    quotes = pd.read_parquet(OUT / 'phase5_late_trades.parquet', columns=[
        'market_ticker', 'trade_id', 'quote_valid_5s', 'quote_spread_5s'])
    quotes = quotes.drop_duplicates(['market_ticker', 'trade_id'])
    primary = primary.merge(quotes, on=['market_ticker', 'trade_id'], how='left', validate='one_to_one')
    primary['quote_valid_5s'] = primary.quote_valid_5s.fillna(False).astype(bool)
    price = primary.longshot_price.to_numpy(float)
    fee = .07 * price * (1 - price)
    half_spread = pd.to_numeric(primary.quote_spread_5s, errors='coerce').to_numpy(float) / 2
    valid = primary.quote_valid_5s.to_numpy(bool) & np.isfinite(half_spread) & (half_spread >= 0)
    primary['quote_valid_5s'] = valid
    primary['cost'] = fee + np.where(valid, half_spread, 0)
    summary = {
        'offset_seconds': offset,
        'definition': 'ESPN wall timestamps plus offset; Kalshi trade timestamps unchanged',
        'primary_full_sample': clustered_summary(primary, offset, False),
        'quote_valid_coverage': {
            'trades': int(valid.sum()), 'games': int(primary.loc[valid, 'game_id'].nunique()),
            'share_trades': float(valid.mean()),
        },
        'primary_quote_valid_same_observation': clustered_summary(primary, offset, True),
    }
    return primary, summary


def main() -> None:
    if not (OUT / 'phase5_late_trades.parquet').exists():
        raise FileNotFoundError('Run `make phase5` first to create the cached five-second quote panel.')
    SENS_DIR.mkdir(parents=True, exist_ok=True)
    summaries = []
    for offset in OFFSETS:
        label = f'{offset:+d}s'.replace('+', 'plus').replace('-', 'minus')
        out_dir = SENS_DIR / label
        env = os.environ.copy()
        env['PHASE4_OUTPUT_DIR'] = str(out_dir)
        env['PHASE4_SHIFT_SECONDS'] = str(offset)
        print(f'Building isolated Phase 4 panel for ESPN shift {offset:+d}s at {out_dir}', flush=True)
        subprocess.run([sys.executable, str(ROOT / 'src/phase4.py')], cwd=ROOT, env=env, check=True)
        primary, summary = build_primary(out_dir / 'trade_panel', offset)
        if offset == 0:
            canonical = pd.read_parquet(OUT / 'phase5_primary_trades.parquet', columns=[
                'market_ticker', 'trade_id', 'A_overprice', 'quote_valid_5s'])
            key = ['market_ticker', 'trade_id']
            left = primary.sort_values(key).reset_index(drop=True)
            right = canonical.sort_values(key).reset_index(drop=True)
            if not left[key].equals(right[key]):
                raise AssertionError('Zero-shift primary keys differ from canonical Phase 5 rows')
            if not np.allclose(left.A, right.A_overprice, atol=1e-12, rtol=0):
                raise AssertionError('Zero-shift outcomes differ from canonical Phase 5 rows')
            if not np.array_equal(left.quote_valid_5s.to_numpy(bool), right.quote_valid_5s.to_numpy(bool)):
                raise AssertionError('Zero-shift quote coverage differs from canonical Phase 5 rows')
            print('Zero-shift panel exactly matches the canonical primary sample, outcomes, and quote-valid flags.', flush=True)
        summaries.append(summary)
        (SENS_DIR / 'phase5_clock_shift_sensitivity.json').write_text(json.dumps({
            'method': 'researcher-chosen constant shift sensitivity; not a lag estimate',
            'offsets_seconds': list(OFFSETS), 'bootstrap': {'cluster': 'game', 'draws': DRAWS, 'seed': SEED},
            'results': summaries,
        }, indent=2))
        print(json.dumps(summary, indent=2), flush=True)
    pd.json_normalize(summaries, sep='.').to_csv(SENS_DIR / 'phase5_clock_shift_sensitivity.csv', index=False)


if __name__ == '__main__':
    main()
