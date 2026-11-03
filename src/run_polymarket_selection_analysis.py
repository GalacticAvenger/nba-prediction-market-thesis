"""Replicate the Kalshi Phase 5 selection analysis on Polymarket maker fills.

All shared phase files are inputs only. Outputs are written under phase2/Polymarket.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from common import write_json  # noqa: E402
from game_windows import is_final_regulation_window, is_overtime  # noqa: E402
from ingest_polymarket_onchain import TEAM_ALIASES  # noqa: E402
from phase5a import summarize  # noqa: E402

P2 = ROOT / 'data/interim/phase2'
FILL_FILE = P2 / 'polymarket_maker_fills_season_raw.parquet'
MAP_FILE = P2 / 'polymarket_nba_2025_26_market_map.json'
ASSIGN_FILE = ROOT / 'data/interim/phase4/selected_team_by_game.csv'
PSTAR_FILE = ROOT / 'data/interim/phase3/pstar_2025_26_every_second.parquet'
PBP_DIR = ROOT / 'data/interim/espn_pbp/season=2026/season_type=2'
OUT = P2
SEED = 5132026
DRAWS = 2000


def norm(value):
    import re
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


def canonical(abbr):
    abbr = str(abbr)
    return TEAM_ALIASES.get(abbr, abbr.lower())


def token_map(market):
    """Return token ids by canonical team abbreviation for the moneyline market."""
    gm = next(x for x in market['gamma_event']['markets']
              if str(x.get('conditionId', '')).lower() == str(market['condition_id']).lower())
    outcomes = json.loads(gm['outcomes'])
    tokens = list(map(str, json.loads(gm['clobTokenIds'])))
    team_by_alias = {}
    for team in market['gamma_event'].get('teams', []):
        abbr = canonical(str(team.get('abbreviation', '')).upper())
        for label in (team.get('name', ''), team.get('alias', ''), team.get('abbreviation', '')):
            if label:
                team_by_alias[norm(label)] = abbr
    result = {}
    for outcome, token in zip(outcomes, tokens):
        abbr = team_by_alias.get(norm(outcome))
        if abbr:
            result[abbr] = token
    return result


def attach_pstar(fills):
    """Map home-side P* at nearest rounded ESPN period/clock second."""
    p = pd.read_parquet(PSTAR_FILE, columns=['game_id', 'period', 'clock_s_remaining', 'pstar'])
    p['game_id'] = p.game_id.astype(str)
    p['period'] = pd.to_numeric(p.period, errors='coerce').astype('Int8')
    p['clock_s_remaining'] = pd.to_numeric(p.clock_s_remaining, errors='coerce').astype(int)
    grids = {}
    for (gid, period), q in p.groupby(['game_id', 'period'], sort=False):
        q = q.sort_values('clock_s_remaining', ascending=False)
        grids[(gid, int(period))] = (q.clock_s_remaining.to_numpy(dtype=int),
                                     q.pstar.to_numpy(dtype=float))
    fills['pstar_home'] = np.nan
    fills['period_key'] = pd.to_numeric(fills.period, errors='coerce')
    fills['clock_key'] = np.rint(pd.to_numeric(fills.clock_s_remaining, errors='coerce'))
    for (gid, period), indexes in fills.groupby(['game_id', 'period_key'], sort=False).groups.items():
        if pd.isna(period):
            continue
        lookup = grids.get((gid, int(period)))
        if lookup is None:
            continue
        grid, vals = lookup
        ix = np.searchsorted(-grid, -fills.loc[indexes, 'clock_key'].to_numpy(dtype=float), side='left')
        ix = np.clip(ix, 0, len(vals) - 1)
        fills.loc[indexes, 'pstar_home'] = vals[ix]
    fills.drop(columns=['period_key', 'clock_key'], inplace=True)
    return fills


def summarize_fit(frame, price_col, y_col='y', label=''):
    q = frame[['game_id', price_col, y_col]].rename(columns={price_col: 'price', y_col: 'y'}).copy()
    # Same fit/calibration implementation as the main session's Phase 5 outputs.
    fit, bins = summarize(q, label, draws=DRAWS, rng=np.random.default_rng(SEED), bin_width=1)
    return fit, bins


def game_cluster_gap(frame, value_col):
    g = frame.groupby('game_id', sort=False)[value_col].mean().to_numpy(dtype=float)
    if len(g) == 0:
        return {'games': 0, 'estimate': None, 'ci95': [None, None]}
    rng = np.random.default_rng(9142026)
    boot = g[rng.integers(0, len(g), size=(DRAWS, len(g)))].mean(axis=1)
    return {'games': int(len(g)), 'estimate': float(g.mean()),
            'ci95': [float(x) for x in np.quantile(boot, [.025, .975])]}


def add_fit(name, frame, price_col, y_col='y'):
    fit, bins = summarize_fit(frame, price_col, y_col, name)
    return fit, bins


def main():
    market_doc = json.loads(MAP_FILE.read_text())
    markets = {str(m['espn_game_id']): m for m in market_doc['markets']}
    assignments = pd.read_csv(ASSIGN_FILE, dtype={'game_id': str}).set_index('game_id')
    schedule = pd.read_parquet(ROOT/'data/interim/espn_games.parquet')
    schedule['game_id'] = schedule.espn_game_id.astype(str)
    home_abbr = schedule.set_index('game_id').home_abbreviation.astype(str).to_dict()

    pbp_parts = []
    for path in PBP_DIR.glob('*.parquet'):
        part = pd.read_parquet(path, columns=['game_id', 'period', 'clock_s_remaining', 'ts_wall_utc'])
        pbp_parts.append(part)
    pbp = pd.concat(pbp_parts, ignore_index=True)
    pbp['game_id'] = pbp.game_id.astype(str)
    pbp['period'] = pd.to_numeric(pbp.period, errors='coerce')
    pbp['clock_s_remaining'] = pd.to_numeric(pbp.clock_s_remaining, errors='coerce')
    pbp['ts'] = pd.to_datetime(pbp.ts_wall_utc, utc=True, errors='coerce')
    pbp = pbp.dropna(subset=['ts'])
    last_play = pbp.groupby('game_id').ts.max().to_dict()
    overtime_games = set(pbp.loc[pbp.period.gt(4), 'game_id'].unique())
    q4 = pbp.loc[pbp.period.eq(4) & pbp.clock_s_remaining.le(180)].sort_values('ts')
    knowable_start = q4.groupby('game_id', sort=False).ts.first().to_dict()

    # Keep only needed maker fields. No taker rows are added to the calibration unit.
    fills = pd.read_parquet(FILL_FILE, columns=[
        'game_id', 'espn_game_id', 'slug', 'timestamp', 'asset', 'outcome',
        'price', 'size', 'period', 'clock_s_remaining', 'side'])
    fills['game_id'] = fills.espn_game_id.astype(str)
    fills['timestamp'] = pd.to_numeric(fills.timestamp, errors='coerce')
    fills['ts'] = pd.to_datetime(fills.timestamp, unit='s', utc=True, errors='coerce')
    fills['period'] = pd.to_numeric(fills.period, errors='coerce')
    fills['clock_s_remaining'] = pd.to_numeric(fills.clock_s_remaining, errors='coerce')
    fills['price'] = pd.to_numeric(fills.price, errors='coerce')
    fills['asset'] = fills.asset.astype(str)
    fills = fills.loc[fills.ts.notna() & fills.period.notna() & fills.price.gt(0) & fills.price.lt(1)].copy()

    fills['selected_home'] = False
    fills['selected_token'] = ''
    fills['home_token'] = ''
    fills['away_token'] = ''
    fills['winner_token'] = ''
    fills['market_resolved'] = False
    mapping_errors = []
    for gid, ix in fills.groupby('game_id', sort=False).groups.items():
        market = markets.get(gid)
        assignment = assignments.loc[gid] if gid in assignments.index else None
        if market is None or assignment is None:
            mapping_errors.append({'game_id': gid, 'reason': 'market or shared assignment missing'})
            continue
        by_team = token_map(market)
        hteam = canonical(market['home_team'])
        ateam = canonical(market['away_team'])
        winner = canonical(market['resolved_winner_abbreviation'])
        ht, at, wt = by_team.get(hteam), by_team.get(ateam), by_team.get(winner)
        if not all((ht, at, wt)):
            mapping_errors.append({'game_id': gid, 'slug': market['slug'], 'reason': 'could not map moneyline token',
                                   'tokens_by_team': by_team, 'home': hteam, 'away': ateam, 'winner': winner})
            continue
        is_home = bool(assignment.selected_team_is_home)
        fills.loc[ix, 'selected_home'] = is_home
        fills.loc[ix, 'home_token'] = ht
        fills.loc[ix, 'away_token'] = at
        fills.loc[ix, 'selected_token'] = ht if is_home else at
        fills.loc[ix, 'winner_token'] = wt
        fills.loc[ix, 'market_resolved'] = True
    fills = fills.loc[fills.market_resolved].copy()
    fills['asset_is_home'] = fills.asset.eq(fills.home_token)
    fills['asset_is_selected'] = fills.asset.eq(fills.selected_token)
    fills['asset_is_winner'] = fills.asset.eq(fills.winner_token)
    token_ok = fills.asset_is_home | fills.asset.eq(fills.away_token)
    unknown_assets = int((~token_ok).sum())
    fills = fills.loc[token_ok].copy()
    fills['y_own'] = fills.asset_is_winner.astype('int8')
    fills['y_selected'] = np.where(fills.asset_is_selected, fills.y_own, 1-fills.y_own).astype('int8')
    fills['price_selected'] = np.where(fills.asset_is_selected, fills.price, 1-fills.price)
    fills['last_play'] = fills.game_id.map(last_play)
    fills['know_start'] = fills.game_id.map(knowable_start)
    fills['ot_game'] = fills.game_id.isin(overtime_games)
    fills = attach_pstar(fills)
    fills['pstar_selected'] = np.where(fills.selected_home, fills.pstar_home, 1-fills.pstar_home)
    fills['pstar_own'] = np.where(fills.asset_is_home, fills.pstar_home, 1-fills.pstar_home)

    # Actual window masks. D is strictly before the last ESPN play.
    in_d = fills.last_play.notna() & fills.ts.lt(fills.last_play) & fills.ts.ge(fills.last_play-pd.Timedelta(minutes=10))
    d = fills.loc[in_d].copy()
    d_no_ot = d.loc[~d.ot_game].copy()
    # First Q4 state <= 3:00 through +10 wall minutes or the last play, in-game only.
    know_end = pd.concat([fills.know_start + pd.Timedelta(minutes=10), fills.last_play], axis=1).min(axis=1)
    in_know = fills.know_start.notna() & fills.last_play.notna() & fills.ts.ge(fills.know_start) & fills.ts.lt(know_end)
    know = fills.loc[in_know].copy()
    # Full 2025-26 regular season; regulation window predicate excludes OT periods.
    gameclock = {}
    for minutes in (2, 3, 5, 10):
        mask = np.fromiter((is_final_regulation_window(p, c, minutes)
                            for p, c in zip(fills.period, fills.clock_s_remaining)),
                           dtype=bool, count=len(fills))
        gameclock[f'final{minutes}'] = fills.loc[mask].copy()

    datasets = {
        'd_wall10_own_token': (d, 'price', 'y_own'),
        'd_wall10_excluding_ot_own_token': (d_no_ot, 'price', 'y_own'),
        'knowable_wall10_selected': (know, 'price_selected', 'y_selected'),
        **{f'gameclock_final{m}_selected': (gameclock[f'final{m}'], 'price_selected', 'y_selected')
           for m in (2, 3, 5, 10)},
    }
    fits, bin_frames, samples = {}, [], {}
    for name, (frame, price_col, y_col) in datasets.items():
        fit, bins = add_fit(name, frame, price_col, y_col)
        fits[name] = fit
        samples[name] = {'maker_fills': int(len(frame)), 'games': int(frame.game_id.nunique()),
                         'outcome_coordinate': 'own token' if y_col == 'y_own' else 'seed-17 selected team',
                         'price_coordinate': price_col}
        if len(bins):
            bins['analysis'] = name
            bins['fit_target'] = 'price'
            bin_frames.append(bins)
        print(f'fit {name}: {len(frame):,} rows / {frame.game_id.nunique()} games', flush=True)

    # P* substitutes for the price coordinate on the same rows and with the same outcome.
    placebo_fits = {}
    for name, (frame, price_col, y_col) in datasets.items():
        pcol = 'pstar_own' if y_col == 'y_own' else 'pstar_selected'
        valid = frame.loc[frame[pcol].notna()].copy()
        fit, bins = add_fit(name, valid, pcol, y_col)
        placebo_fits[name] = fit
        samples[name]['pstar_maker_fills'] = int(len(valid))
        samples[name]['pstar_games'] = int(valid.game_id.nunique())
        if len(bins):
            bins['analysis'] = name
            bins['fit_target'] = 'pstar'
            bin_frames.append(bins)
        print(f'P* {name}: {len(valid):,} rows / {valid.game_id.nunique()} games', flush=True)

    # Final three game-clock minutes; define the longshot contract from traded price,
    # then use P* for that same contract in the placebo outcome gap.
    m3 = np.fromiter((is_final_regulation_window(p, c, 3)
                      for p, c in zip(fills.period, fills.clock_s_remaining)), dtype=bool, count=len(fills))
    in_game = fills.last_play.notna() & fills.ts.lt(fills.last_play)
    longshot = fills.loc[m3 & in_game].copy()
    longshot['longshot_price'] = np.minimum(longshot.price_selected, 1-longshot.price_selected)
    longshot['longshot_y'] = np.where(longshot.price_selected <= .5,
                                       longshot.y_selected, 1-longshot.y_selected)
    longshot['longshot_pstar'] = np.where(longshot.price_selected <= .5,
                                          longshot.pstar_selected, 1-longshot.pstar_selected)
    longshot = longshot.loc[longshot.longshot_price.ge(.05) & longshot.longshot_price.lt(.20)].copy()
    longshot['inside_d'] = longshot.last_play.notna() & longshot.ts.lt(longshot.last_play) & longshot.ts.ge(longshot.last_play-pd.Timedelta(minutes=10))
    longshot_rows = []
    for window, mask in [('inside_d', longshot.inside_d), ('outside_d', ~longshot.inside_d)]:
        for coord, value in [('price', 'longshot_price'), ('Pstar', 'longshot_pstar')]:
            q = longshot.loc[mask & longshot[value].notna()].copy()
            q['gap'] = q.longshot_y - q[value]
            stat = game_cluster_gap(q, 'gap')
            longshot_rows.append({'window': window, 'coordinate': coord, 'maker_fills': int(len(q)),
                                  'games': int(q.game_id.nunique()), 'mean_longshot_probability': float(q[value].mean()) if len(q) else None,
                                  'trade_weighted_win_rate': float(q.longshot_y.mean()) if len(q) else None,
                                  'trade_weighted_Y_minus_probability': float(q.gap.mean()) if len(q) else None,
                                  'game_weighted_Y_minus_probability': stat['estimate'],
                                  'game_weighted_gap_ci95': stat['ci95']})
    longshot_df = pd.DataFrame(longshot_rows)

    # 0.10-0.40 contracts, grouped in the requested five windows; the interval is inclusive.
    contract_windows = {
        'd_wall10': (d, 'price', 'y_own', 'pstar_own'),
        'd_wall10_excluding_ot': (d_no_ot, 'price', 'y_own', 'pstar_own'),
        'knowable_wall10': (know, 'price_selected', 'y_selected', 'pstar_selected'),
        'gameclock_final2_selected': (gameclock['final2'], 'price_selected', 'y_selected', 'pstar_selected'),
        'gameclock_final5_selected': (gameclock['final5'], 'price_selected', 'y_selected', 'pstar_selected'),
    }
    contract_rows = []
    for window, (frame, pcol, ycol, pstarcol) in contract_windows.items():
        for coord, value in [('price', pcol), ('Pstar', pstarcol)]:
            q = frame.loc[frame[value].between(.10, .40, inclusive='both') & frame[value].notna()].copy()
            q['gap'] = q[ycol] - q[value]
            stat = game_cluster_gap(q, 'gap')
            contract_rows.append({'window': window, 'coordinate': coord, 'maker_fills': int(len(q)),
                                  'games': int(q.game_id.nunique()),
                                  'trade_weighted_win_rate': float(q[ycol].mean()) if len(q) else None,
                                  'trade_weighted_Y_minus_probability': float(q.gap.mean()) if len(q) else None,
                                  'game_weighted_Y_minus_probability': stat['estimate'],
                                  'game_weighted_gap_ci95': stat['ci95']})
    contracts = pd.DataFrame(contract_rows)

    output = {
        'method': {
            'maker_rows_only': True, 'prelec': 'Phase 5 main session phase5a.summarize; Prelec-II; one-cent bins; trade-weighted bin fits',
            'bootstrap': {'draws': DRAWS, 'cluster': 'game', 'seed': SEED},
            'extreme_price_filter': 'same main-session selection fitter: 0 < observed coordinate < 1; P* placebo substitutes P* at fill time and uses 0 < P* < 1',
            'assignment_file': str(ASSIGN_FILE), 'assignment_seed': 17,
            'pstar_model': 'home-coordinate pstar from pstar_2025_26_every_second.parquet, nearest rounded ESPN period/clock second; converted to outcome coordinate',
            'gameclock_comparison_scope': 'full 2025-26 NBA regular-season rows; regulation Q4 game-clock predicate, all other periods excluded',
            'knowable_window': 'first ESPN Q4 state at <=180 seconds through min(+10 wall minutes, last ESPN play), in-game only',
        },
        'mapping': {'maker_rows_after_market_assignment': int(len(fills)), 'unknown_outcome_token_rows_removed': unknown_assets,
                    'market_mapping_errors': mapping_errors},
        'samples': samples, 'price_fits': fits, 'pstar_placebo_fits': placebo_fits,
        'final3_longshot_inside_outside_d': longshot_rows,
        'contracts_010_040': contract_rows,
    }
    write_json(OUT/'polymarket_selection_analysis.json', output)
    if bin_frames:
        pd.concat(bin_frames, ignore_index=True).to_csv(OUT/'polymarket_selection_analysis_bins.csv', index=False)
    longshot_df.to_csv(OUT/'polymarket_selection_longshot_d.csv', index=False)
    contracts.to_csv(OUT/'polymarket_selection_contracts_010_040.csv', index=False)
    print(json.dumps({'mapping': output['mapping'], 'samples': samples}, indent=2, default=str), flush=True)

if __name__ == '__main__':
    main()
