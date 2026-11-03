"""Selection-free localization of the late-game longshot price–P* residual."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from common import ROOT
from game_windows import is_final_regulation_window

OUT = ROOT / 'data/interim/phase5'
PANEL = ROOT / 'data/interim/phase4/trade_panel'
META = ROOT / 'data/interim/kalshi_market_metadata.parquet'
PBP = ROOT / 'data/interim/phase2/pbp_derived_regular.parquet'
PSTAR = ROOT / 'data/interim/phase3/pstar_2025_26_every_second.parquet'
POLY = ROOT / 'data/interim/phase2/polymarket_maker_fills_season_raw.parquet'
POLY_MAP = ROOT / 'data/interim/phase2/polymarket_nba_2025_26_market_map.json'
ASSIGN = ROOT / 'data/interim/phase4/selected_team_by_game.csv'
DRAWS = 2000
SEED = 20261022
BANDS = [('0.05–0.20', .05, .20), ('0.10–0.40', .10, .40)]


def bootstrap_mean(frame, value, weight='game', draws=DRAWS, seed=SEED):
    """Mean and game-clustered percentile CI, game-equal or pooled trade-equal."""
    z = frame[['game_id', value]].dropna().copy()
    if z.empty:
        return {'estimate': None, 'ci95': [None, None], 'trades': 0, 'games': 0}
    g = z.groupby('game_id', sort=False)[value].agg(['sum', 'count', 'mean'])
    rng = np.random.default_rng(seed)
    w = rng.multinomial(len(g), np.full(len(g), 1 / len(g)), size=draws)
    if weight == 'game':
        vals = g['mean'].to_numpy(float)
        boot = (w @ vals) / w.sum(axis=1)
        point = float(vals.mean())
    elif weight == 'trade':
        sums, counts = g['sum'].to_numpy(float), g['count'].to_numpy(float)
        den = w @ counts
        boot = (w @ sums) / np.where(den > 0, den, np.nan)
        point = float(sums.sum() / counts.sum())
    else:
        raise ValueError(weight)
    return {'estimate': point,
            'ci95': [float(x) for x in np.nanquantile(boot, [.025, .975])],
            'trades': int(len(z)), 'games': int(len(g)),
            'weighting': weight, 'cluster': 'game', 'draws': draws}


def grouped_summary(frame, key, metrics, seed=SEED):
    out = []
    for label, z in frame.groupby(key, dropna=False, observed=True, sort=True):
        row = {key: 'unknown' if pd.isna(label) else str(label),
               'trades': int(len(z)), 'games': int(z.game_id.nunique())}
        for i, metric in enumerate(metrics):
            row[metric] = bootstrap_mean(z, metric, seed=seed + i)
        out.append(row)
    return out


def cluster_regression(frame, y, x, controls=(), continuous=(), cluster='game_id'):
    """Equal-game-weight WLS with game-clustered sandwich SEs."""
    import statsmodels.api as sm
    cols = [cluster, y, x, *controls, *continuous]
    d = frame[cols].dropna().copy()
    if d.empty or d[cluster].nunique() < 2:
        return {'n': int(len(d)), 'games': int(d[cluster].nunique()), 'coefficients': {}}
    # Equal total mass per game, retaining within-game observation variation.
    d['_w'] = 1 / d.groupby(cluster)[cluster].transform('size')
    pieces = [pd.Series(1.0, index=d.index, name='const'), d[[x]].astype(float)]
    for c in continuous:
        pieces.append(d[[c]].astype(float))
    for c in controls:
        dm = pd.get_dummies(d[c].astype(str), prefix=c, drop_first=True, dtype=float)
        pieces.append(dm)
    X = pd.concat(pieces, axis=1).astype(float)
    fit = sm.WLS(d[y].astype(float), X, weights=d._w).fit(
        cov_type='cluster', cov_kwds={'groups': d[cluster], 'use_correction': True})
    coefs = {}
    for name in X.columns:
        se = float(fit.bse[name]); estimate = float(fit.params[name])
        coefs[name] = {'estimate': estimate,
                       'ci95': [estimate - 1.96 * se, estimate + 1.96 * se],
                       'se_cluster': se, 'pvalue': float(fit.pvalues[name])}
    return {'n': int(len(d)), 'games': int(d[cluster].nunique()),
            'weighting': 'equal total trade weight per game',
            'cluster': 'game', 'coefficients': coefs}


def load_pbp():
    pbp = pd.read_parquet(PBP)
    pbp['game_id'] = pbp.game_id.astype(str)
    pbp['wall'] = pd.to_datetime(pbp.ts_wall_utc, utc=True, errors='coerce')
    pbp = pbp.dropna(subset=['wall']).sort_values(['game_id', 'wall'], kind='stable')
    starts = (pbp.loc[pbp.period.eq(4) & pbp.clock_s_remaining.le(180)]
              .groupby('game_id', sort=False).wall.first().to_dict())
    lasts = pbp.groupby('game_id', sort=False).wall.max().to_dict()
    return pbp, starts, lasts


def state_at(pbp, gid, ts):
    z = pbp.get(gid)
    n = len(ts)
    out = {'score_home': np.full(n, np.nan), 'score_away': np.full(n, np.nan),
           'possession': np.full(n, '', dtype=object)}
    if z is None or z.empty:
        return out
    walls = z.wall.astype('int64').to_numpy()
    target = pd.DatetimeIndex(ts).astype('int64').to_numpy()
    ix = np.searchsorted(walls, target, side='right') - 1
    ok = ix >= 0
    for col in ('score_home', 'score_away', 'possession'):
        vals = z[col].to_numpy()
        out[col][ok] = vals[ix[ok]]
    return out


def load_kalshi():
    pbp, starts, lasts = load_pbp()
    pbp_by_game = {g: z.reset_index(drop=True) for g, z in pbp.groupby('game_id', sort=False)}
    games = pd.read_parquet(ROOT / 'data/interim/espn_games.parquet')
    games['game_id'] = games.espn_game_id.astype(str)
    team_ids = games.set_index('game_id')[['home_team_id', 'away_team_id']].to_dict('index')
    meta = pd.read_parquet(META)
    meta = meta.loc[(meta.season == 2026) & meta.season_type.eq(2)].copy()
    meta['game_id'] = meta.game_id.astype(str)
    meta['ticker'] = meta.ticker.astype(str)
    meta['result'] = meta.result.astype(str).str.lower()
    keep = ['game_id', 'trade_id', 'ts_utc', 'period', 'clock_s_remaining',
            'clock_running', 'tau_seconds', 'clock_decay',
            'selected_team_is_home', 'ticker_yes_is_home', 'selected_contract_price',
            'selected_contract_pstar', 'selected_taker_outcome_side', 'count']
    chunks = []
    for m in meta.itertuples(index=False):
        f = PANEL / f'{m.ticker}.parquet'
        if not f.exists() or m.result not in ('yes', 'no'):
            continue
        x = pd.read_parquet(f, columns=keep)
        if x.empty:
            continue
        x['game_id'] = str(m.game_id)
        x['market_ticker'] = str(m.ticker)
        x['ts'] = pd.to_datetime(x.ts_utc, utc=True, errors='coerce')
        x = x.dropna(subset=['ts', 'selected_contract_price', 'selected_contract_pstar'])
        if x.empty:
            continue
        x = x.sort_values('ts', kind='stable').reset_index(drop=True)
        x['event_origin_utc_s'] = np.rint(
            x.ts.astype('int64').to_numpy()/1e9 -
            pd.to_numeric(x.tau_seconds,errors='coerce').to_numpy(float))
        # Keep live-market observations only; this does not exclude games by OT
        # status and does not define either window relative to game end.
        last = lasts.get(str(m.game_id))
        if last is not None:
            x = x.loc[x.ts.le(last)].copy()
        start = starts.get(str(m.game_id))
        if start is None:
            x['knowable'] = False
        else:
            x['knowable'] = x.ts.ge(start) & x.ts.lt(start + pd.Timedelta(minutes=10))
        x['final5'] = [is_final_regulation_window(p, c, 5)
                       for p, c in zip(x.period, x.clock_s_remaining)]
        # Keep the two windows separately: their rows overlap by design.
        selected_home = x.selected_team_is_home.fillna(False).astype(bool).to_numpy()
        yes_home = x.ticker_yes_is_home.fillna(False).astype(bool).to_numpy()
        same = selected_home == yes_home
        y_yes = int(m.result == 'yes')
        x['y_selected'] = np.where(same, y_yes, 1-y_yes).astype('int8')
        x['p_selected'] = pd.to_numeric(x.selected_contract_price, errors='coerce')
        x['ps_selected'] = pd.to_numeric(x.selected_contract_pstar, errors='coerce')
        long_is_selected = x.p_selected.le(.5).to_numpy()
        x['price'] = np.minimum(x.p_selected, 1-x.p_selected)
        x['pstar'] = np.where(long_is_selected, x.ps_selected, 1-x.ps_selected)
        x['y'] = np.where(long_is_selected, x.y_selected, 1-x.y_selected).astype('int8')
        x['price_minus_pstar'] = x.price - x.pstar
        x['y_minus_price'] = x.y - x.price
        side = x.selected_taker_outcome_side.astype(str).str.lower()
        buy_long = np.where(long_is_selected, side.eq('yes'), side.eq('no'))
        x['taker_side'] = np.where(side.isin(['yes','no']),
                                   np.where(buy_long,'buy longshot','sell longshot'),
                                   'unknown')
        # Rebuild five-second trade-inferred selected-contract quotes from both
        # taker sides, then fold the valid mid to the same longshot contract.
        ask_obs = np.where(side.eq('yes'), x.p_selected.to_numpy(float), np.nan)
        bid_obs = np.where(side.eq('no'), x.p_selected.to_numpy(float), np.nan)
        dt = pd.DatetimeIndex(x.ts)
        ask = pd.Series(ask_obs, index=dt).rolling('5s', closed='both', min_periods=1).min().to_numpy()
        bid = pd.Series(bid_obs, index=dt).rolling('5s', closed='both', min_periods=1).max().to_numpy()
        valid = np.isfinite(ask) & np.isfinite(bid) & (bid <= ask)
        mid_sel = np.where(valid, (ask+bid)/2, np.nan)
        halfspread = np.where(valid, (ask-bid)/2, np.nan)
        x['valid_mid'] = valid
        x['mid'] = np.where(long_is_selected, mid_sel, 1-mid_sel)
        x['mid_minus_pstar'] = x.mid - x.pstar
        x['y_minus_mid'] = x.y - x.mid
        x['halfspread'] = halfspread
        x['clock_decay_longshot'] = np.where(long_is_selected,
                                              pd.to_numeric(x.clock_decay, errors='coerce'),
                                              -pd.to_numeric(x.clock_decay, errors='coerce'))
        x['price_cent'] = np.floor(x.price.to_numpy(float)*100 + 1e-8).astype(int)
        # Time remaining cells are restricted to regulation Q4 by construction.
        clk = pd.to_numeric(x.clock_s_remaining, errors='coerce')
        x['time_cell'] = pd.cut(clk, [-1e-8,60,120,180,300.0001],
                                labels=['0–1 min','1–2 min','2–3 min','3–5 min'],
                                right=True, include_lowest=True).astype(object)
        st = state_at(pbp_by_game, str(m.game_id), x.ts)
        x['score_home'] = st['score_home']; x['score_away'] = st['score_away']
        margin = x.score_home - x.score_away
        abs_margin = margin.abs()
        x['margin_cell'] = pd.cut(abs_margin, [0,3,6,np.inf],
                                  labels=['1–3','4–6','7+'], right=True).astype(object)
        ids = team_ids.get(str(m.game_id), {})
        trailing_id = np.where(margin > 0, str(ids.get('away_team_id')),
                               np.where(margin < 0, str(ids.get('home_team_id')), ''))
        poss = pd.Series(st['possession']).fillna('').astype(str).to_numpy()
        x['trailing_possession'] = np.where(pd.isna(margin) | (margin == 0) | (poss == ''),
                                            'unknown',
                                            np.where(poss == trailing_id, 'yes', 'no'))
        x['state_cell'] = x.margin_cell.astype(str) + ' × ' + x.trailing_possession.astype(str)
        x['ot_observed'] = x.period.gt(4)
        want = ['game_id','market_ticker','trade_id','ts','window','period',
                         'clock_s_remaining','clock_running','event_origin_utc_s',
                         'clock_decay_longshot','price','pstar','y','price_minus_pstar',
                         'y_minus_price','mid','mid_minus_pstar','y_minus_mid',
                         'valid_mid','halfspread','taker_side','price_cent','time_cell',
                         'margin_cell','trailing_possession','state_cell','count',
                         'ot_observed','p_selected','ps_selected','selected_team_is_home']
        chunks.append(pd.concat([
            x.loc[x.knowable].assign(window='Knowable'),
            x.loc[x.final5].assign(window='Final 5')
        ], ignore_index=True)[want].copy())
    if not chunks:
        raise RuntimeError('No eligible Kalshi panel rows')
    return pd.concat(chunks, ignore_index=True), pbp, starts


def map_poly():
    sys.path.insert(0, str(ROOT/'src'))
    from ingest_polymarket_onchain import TEAM_ALIASES
    mapping = json.loads(POLY_MAP.read_text())
    assign = pd.read_csv(ASSIGN, dtype={'game_id': str})
    selected_home = dict(zip(assign.game_id.astype(str),
                              assign.selected_team_is_home.astype(bool)))
    # Keep this join identical to the audited Polymarket selection analysis:
    # TEAM_ALIASES keys are uppercase abbreviations (e.g. NY -> NYK), so look
    # up the original abbreviation before lower-casing the fallback.
    def canon(v):
        q = str(v)
        return TEAM_ALIASES.get(q, q.lower())
    def norm(v):
        import re
        return re.sub(r'[^a-z0-9]', '', str(v).lower())
    def token_map(m):
        gm = next(x for x in m['gamma_event']['markets']
                  if str(x.get('conditionId', '')).lower() ==
                     str(m['condition_id']).lower())
        outcomes = json.loads(gm['outcomes'])
        tokens = list(map(str, json.loads(gm['clobTokenIds'])))
        team_by_alias = {}
        for team in m['gamma_event'].get('teams', []):
            abbr = canon(str(team.get('abbreviation', '')).upper())
            for label in (team.get('name', ''), team.get('alias', ''),
                          team.get('abbreviation', '')):
                if label:
                    team_by_alias[norm(label)] = abbr
        return {team_by_alias[norm(outcome)]: token
                for outcome, token in zip(outcomes, tokens)
                if norm(outcome) in team_by_alias}
    by_slug = {}
    for m in mapping['markets']:
        gid = str(m['espn_game_id'])
        by_team = token_map(m)
        home_token = by_team.get(canon(m['home_team']))
        away_token = by_team.get(canon(m['away_team']))
        winner_token = by_team.get(canon(m['resolved_winner_abbreviation']))
        if not all((home_token, away_token, winner_token)):
            continue
        resolved = canon(m.get('resolved_winner_abbreviation'))
        home_abbr = canon(m['home_team'])
        # The winner is joined through the official outcome-to-token mapping,
        # not by comparing abbreviations reconstructed from fill labels.
        home_win = winner_token == home_token
        by_slug[m['slug']] = {'game_id':gid, 'home_token':home_token,
                              'away_token':away_token, 'winner_token':winner_token,
                              'home_win':home_win, 'selected_home':selected_home.get(gid)}
    return by_slug


def load_polymarket(pbp, starts):
    mkt = map_poly()
    games = set(v['game_id'] for v in mkt.values())
    f = pd.read_parquet(POLY, columns=['espn_game_id','slug','asset','side','price','timestamp',
                                       'outcome','period','clock_s_remaining'])
    f['espn_game_id'] = f.espn_game_id.astype(str)
    f = f.loc[f.slug.isin(mkt)].copy()
    f['ts'] = pd.to_datetime(f.timestamp, unit='s', utc=True, errors='coerce')
    f['game_id'] = f.slug.map({s:v['game_id'] for s,v in mkt.items()})
    f = f.loc[f.game_id.isin(games) & f.ts.notna()].copy()
    f['knowable_start'] = f.game_id.map(starts)
    f['knowable'] = f.knowable_start.notna() & f.ts.ge(f.knowable_start) & \
                    f.ts.lt(f.knowable_start + pd.Timedelta(minutes=10))
    f['final5'] = [is_final_regulation_window(p,c,5)
                   for p,c in zip(f.period,f.clock_s_remaining)]
    f['window'] = np.select([f.knowable, f.final5], ['Knowable','Final 5'], default='')
    f = f.loc[f.window.ne('')].copy()
    if f.empty:
        raise RuntimeError('No eligible Polymarket rows')
    # Resolve each maker fill by its audited CLOB token id.  This is the same
    # outcome join used by run_polymarket_selection_analysis.py.
    f['outcome_home'] = pd.array([
        (str(asset) == mkt[slug]['home_token']) if str(asset) in
        (mkt[slug]['home_token'], mkt[slug]['away_token']) else None
        for slug, asset in zip(f.slug, f.asset)
    ], dtype='boolean')
    f = f.loc[f.outcome_home.notna()].copy()
    f['selected_home'] = f.slug.map({s:v['selected_home'] for s,v in mkt.items()})
    f = f.loc[f.selected_home.notna()].copy()
    same_selected = f.outcome_home.astype(bool).to_numpy() == f.selected_home.astype(bool).to_numpy()
    f['p_selected'] = np.where(same_selected, f.price, 1-f.price)
    f['y_selected'] = np.where(f.selected_home,
                               f.slug.map({s:int(v['home_win']) for s,v in mkt.items()}),
                               f.slug.map({s:1-int(v['home_win']) for s,v in mkt.items()}))
    f['game_clock_remaining'] = pd.to_numeric(f.clock_s_remaining, errors='coerce')
    f['pstar_clock'] = np.rint(pd.to_numeric(f.clock_s_remaining, errors='coerce')).astype('Int64')
    # Join the price-independent Phase 3 home probability at each aligned state.
    ps = pd.read_parquet(PSTAR, columns=['game_id','period','clock_s_remaining','pstar'])
    ps['game_id'] = ps.game_id.astype(str)
    f = f.merge(ps, left_on=['game_id','period','pstar_clock'],
                right_on=['game_id','period','clock_s_remaining'], how='left',
                validate='many_to_one')
    f['ps_selected'] = np.where(f.selected_home, f.pstar, 1-f.pstar)
    long_sel = f.p_selected.le(.5)
    f['longshot_is_selected'] = long_sel
    row_token_is_longshot = same_selected == long_sel.to_numpy()
    maker_buys_token = f.side.astype(str).str.upper().eq('BUY').to_numpy()
    f['maker_side_folded'] = np.where(maker_buys_token == row_token_is_longshot,
                                      'buy longshot','sell longshot')
    f['price'] = np.minimum(f.p_selected,1-f.p_selected)
    f['pstar'] = np.where(long_sel, f.ps_selected,1-f.ps_selected)
    f['y'] = np.where(long_sel, f.y_selected,1-f.y_selected)
    f['price_minus_pstar'] = f.price-f.pstar
    f['y_minus_price'] = f.y-f.price
    f['venue'] = 'Polymarket'
    return f[['game_id','window','period','game_clock_remaining','price','p_selected','y_selected',
              'pstar','y','price_minus_pstar',
              'y_minus_price','slug','asset','timestamp','maker_side_folded',
              'selected_home','longshot_is_selected']].copy(), int(f.pstar.notna().sum()), int(len(f))


def main():
    cache = OUT/'phase5_residual_mechanisms_kalshi_cache.parquet'
    if cache.exists():
        k = pd.read_parquet(cache)
        pbp, starts, _last_unused = load_pbp()
    else:
        k, pbp, starts = load_kalshi()
        k.to_parquet(cache,index=False)
    print(f'loaded Kalshi: {len(k):,} rows / {k.game_id.nunique():,} games', flush=True)
    # Requested localization: game-weighted point estimates and game-clustered CIs.
    loc = []
    for win in ('Knowable','Final 5'):
        for band, lo, hi in BANDS:
            z = k.loc[k.window.eq(win) & k.price.between(lo,hi,inclusive='both')].copy()
            if z.empty: continue
            for metric in ('price_minus_pstar','y_minus_price'):
                loc.append({'window':win,'band':band,'dimension':'overall','split':'all',
                            metric:bootstrap_mean(z,metric,seed=SEED+len(loc))})
            dims = [('clock state','clock_running',
                     lambda q: np.where(q.clock_running.eq(True),'running','stopped')),
                    ('taker side','taker_side',lambda q:q.taker_side)]
            for label, _, fn in dims:
                g=z.copy()
                if label=='clock state': g=g.loc[g.clock_running.notna()].copy()
                g['split']=fn(g)
                for row in grouped_summary(g,'split',['price_minus_pstar','y_minus_price']):
                    loc.append({'window':win,'band':band,'dimension':label,**row})
            if win=='Final 5':
                for row in grouped_summary(z.dropna(subset=['time_cell']),'time_cell',
                                           ['price_minus_pstar','y_minus_price']):
                    loc.append({'window':win,'band':band,'dimension':'game-clock remaining',**row})
            state=z.loc[z.margin_cell.notna()].copy()
            for row in grouped_summary(state,'state_cell',['price_minus_pstar','y_minus_price']):
                loc.append({'window':win,'band':band,'dimension':'score margin × trailing possession',**row})
            # Trade price and valid mid are paired on exactly the valid-quote rows.
            valid=z.loc[z.valid_mid].copy()
            for row in grouped_summary(valid,'taker_side',
                                       ['price_minus_pstar','y_minus_price',
                                        'mid_minus_pstar','y_minus_mid']):
                loc.append({'window':win,'band':band,
                            'dimension':'taker side × valid quote measure',**row})
            for name, metric in [('trade price (valid-mid subset)','price_minus_pstar'),
                                 ('valid mid','mid_minus_pstar'),
                                 ('trade-price outcome check (valid-mid subset)','y_minus_price'),
                                 ('mid outcome check','y_minus_mid')]:
                r=bootstrap_mean(valid,metric,seed=SEED+len(loc))
                loc.append({'window':win,'band':band,'dimension':name,'split':'all',**r})
            # Trade and quote coverage diagnostics for the requested microstructure comparison.
            loc.append({'window':win,'band':band,'dimension':'valid-mid quote coverage',
                        'split':'valid','trades':int(len(valid)),
                        'games':int(valid.game_id.nunique()),'share':float(len(valid)/len(z))})
    print(f'localization done: {len(loc)} cells', flush=True)

    # Slow-tracking regression in running-clock trades, separately by requested band/window.
    slow=[]
    for win in ('Knowable','Final 5'):
        for band,lo,hi in BANDS:
            z=k.loc[k.window.eq(win)&k.clock_running.fillna(False)&
                    k.price.between(lo,hi,inclusive='both')&
                    k.clock_decay_longshot.notna()].copy()
            if z.empty: continue
            z['clock_decay_cent']=z.clock_decay_longshot*100
            model=cluster_regression(z,'price_minus_pstar','clock_decay_cent',
                                     controls=('price_cent',))
            slow.append({'window':win,'band':band,'test':'price-minus-Pstar on clock-decay, price-cent FE',
                         **model})
    print(f'slow regressions done: {len(slow)}', flush=True)

    # Event-free running-clock price paths. Keep the contract side fixed at entry;
    # use the last trade before t+h and the Phase 3 P* at clock(t)-h.
    drift=[]
    pbp_by={g:d.reset_index(drop=True) for g,d in pbp.groupby('game_id',sort=False)}
    pstar_grid=pd.read_parquet(PSTAR,columns=['game_id','period','clock_s_remaining','pstar'])
    pstar_grid['game_id']=pstar_grid.game_id.astype(str)
    pstar_map={(str(g),int(p),int(c)):float(v) for g,p,c,v in
               pstar_grid[['game_id','period','clock_s_remaining','pstar']].itertuples(index=False,name=None)}
    drift_pair_frames={}
    for win in ('Knowable','Final 5'):
        for band,lo,hi in BANDS:
            eligible=k.loc[k.window.eq(win)&k.clock_running.fillna(False)&
                           k.price.between(lo,hi,inclusive='both')].copy()
            for ticker, startsample in eligible.groupby('market_ticker',sort=False):
                gid=str(startsample.game_id.iloc[0])
                full=pd.read_parquet(PANEL/f'{ticker}.parquet',columns=[
                    'ts_utc','period','clock_s_remaining','clock_running','tau_seconds',
                    'selected_contract_price'])
                full['ts']=pd.to_datetime(full.ts_utc,utc=True,errors='coerce')
                full=full.dropna(subset=['ts','selected_contract_price'])
                last=pbp_by[gid].wall.max()
                full=full.loc[full.ts.le(last)].sort_values('ts',kind='stable').reset_index(drop=True)
                tns=full.ts.astype('int64').to_numpy()
                pvals=pd.to_numeric(full.selected_contract_price,errors='coerce').to_numpy(float)
                origin=np.rint(tns/1e9-pd.to_numeric(full.tau_seconds,errors='coerce').to_numpy(float))
                per=pd.to_numeric(full.period,errors='coerce').fillna(-1).to_numpy(int)
                stopped=pbp_by[gid].loc[pbp_by[gid].clock_running.eq(False),'wall'].astype('int64').to_numpy()
                for h in (5,15,30):
                    r=startsample
                    t0=pd.DatetimeIndex(r.ts).astype('int64').to_numpy()
                    target=t0+int(h*1e9)
                    j0=np.searchsorted(tns,t0,side='right')-1
                    jh=np.searchsorted(tns,target,side='right')-1
                    ok=(j0>=0)&(jh>=j0)
                    safe=np.flatnonzero(ok)
                    if not len(safe): continue
                    ok[safe]&=(origin[jh[safe]]==origin[j0[safe]])
                    ok[safe]&=full.clock_running.fillna(False).to_numpy()[j0[safe]]
                    ok[safe]&=full.clock_running.fillna(False).to_numpy()[jh[safe]]
                    ok[safe]&=(per[jh[safe]]==pd.to_numeric(r.period,errors='coerce').to_numpy(int)[safe])
                    # Require no known stopped-clock PBP state between endpoints.
                    left=np.searchsorted(stopped,t0,side='right')
                    right=np.searchsorted(stopped,target,side='right')
                    ok &= (right-left)==0
                    if win=='Knowable':
                        st=starts.get(gid)
                        if st is None: continue
                        ok &= target < int((st+pd.Timedelta(minutes=10)).value)
                    else:
                        ok &= (pd.to_numeric(r.clock_s_remaining,errors='coerce').to_numpy(float)>h)
                    ii=np.flatnonzero(ok)
                    if not len(ii): continue
                    side_sign=np.where(r.p_selected.to_numpy(float)[ii]<=.5,1.0,-1.0)
                    p0=np.where(side_sign>0,r.p_selected.to_numpy(float)[ii],1-r.p_selected.to_numpy(float)[ii])
                    ps0=np.where(side_sign>0,r.ps_selected.to_numpy(float)[ii],1-r.ps_selected.to_numpy(float)[ii])
                    ph=np.where(side_sign>0,pvals[jh[ii]],1-pvals[jh[ii]])
                    target_clock=np.rint(r.clock_s_remaining.to_numpy(float)[ii]-h).astype(int)
                    selected_home=r.selected_team_is_home.fillna(False).astype(bool).to_numpy()[ii]
                    home_ps=np.array([pstar_map.get((gid,int(r.period.iloc[j]),int(c)),np.nan)
                                       for j,c in zip(ii,target_clock)],float)
                    ps_selected=np.where(selected_home,home_ps,1-home_ps)
                    psh=np.where(side_sign>0,ps_selected,1-ps_selected)
                    gap0=p0-ps0; gaph=ph-psh
                    q=pd.DataFrame({'game_id':gid,'convergence':np.abs(gap0)-np.abs(gaph),
                                    'initial_abs_gap':np.abs(gap0)})
                    q=q.dropna()
                    if q.empty: continue
                    drift_pair_frames.setdefault((win,band,h),[]).append(q)
    for (win,band,h),parts in drift_pair_frames.items():
        q=pd.concat(parts,ignore_index=True)
        mean=bootstrap_mean(q,'convergence',seed=SEED+h)
        reg=cluster_regression(q,'convergence','initial_abs_gap')
        drift.append({'window':win,'band':band,'horizon_seconds':h,
                      'event_free_pairs':int(len(q)),
                      'mean_signed_convergence':mean,'size_response':reg})
    print(f'drift done: {len(drift)} cells', flush=True)

    # Simple always-enter strategy at qualifying knowable-window trade prices.
    exploit=[]
    z=k.loc[k.window.eq('Knowable')&k.price.between(.05,.20,inclusive='both')].copy()
    z['fee_taker_large']=.07*z.price*(1-z.price)
    z['fee_maker_large']=.0175*z.price*(1-z.price)
    z['profit_maker']=z.price-z.y-z.fee_maker_large
    first_all=z.sort_values('ts',kind='stable').drop_duplicates('game_id',keep='first')
    for weighting in ('trade','first-entry'):
        for label, frame, field in [
            ('maker fee only', z, 'profit_maker'),
            ('taker fee + half-spread (valid 5s quote)', z.loc[z.valid_mid].copy(), 'profit_taker')]:
            frame=frame.copy()
            if label.startswith('taker'):
                if weighting=='first-entry':
                    frame=first_all.loc[first_all.valid_mid].copy()
                frame['profit_taker']=frame.price-frame.y-frame.fee_taker_large-frame.halfspread
            if weighting=='first-entry' and not label.startswith('taker'):
                frame=first_all.copy()
            res=bootstrap_mean(frame,field,weight='trade',seed=SEED+len(exploit))
            exploit.append({'estimator':weighting,'cost':label,**res,
                            'mean_gross_profit':float((frame.price-frame.y).mean()) if len(frame) else None,
                            'mean_fee':float(frame.fee_taker_large.mean() if label.startswith('taker') else frame.fee_maker_large.mean()) if len(frame) else None,
                            'mean_halfspread':float(frame.halfspread.mean()) if label.startswith('taker') and len(frame) else (0.0 if len(frame) else None),
                            'quote_valid_share_in_base':float(z.valid_mid.mean()) if len(z) else None,
                            'first_entry_quote_valid_games':int(first_all.valid_mid.sum()) if weighting=='first-entry' else None,
                            'first_entry_eligible_games':int(len(first_all)) if weighting=='first-entry' else None})

    # Read-only Polymarket maker-fill comparison using the saved full-season parquet.
    poly, poly_joined, poly_rows = load_polymarket(pbp, starts)
    print(f'Polymarket joined: {poly_joined:,}/{poly_rows:,}', flush=True)
    poly_results=[]
    for win in ('Knowable','Final 5'):
        for band,lo,hi in BANDS:
            q=poly.loc[poly.window.eq(win)&poly.price.between(lo,hi,inclusive='both')]
            if q.empty: continue
            a=bootstrap_mean(q,'price_minus_pstar',seed=SEED+3)
            b=bootstrap_mean(q,'y_minus_price',seed=SEED+4)
            poly_results.append({'window':win,'band':band,'venue':'Polymarket maker fills',
                                 'price_minus_pstar':a,'y_minus_price':b})

    uninterpretable_gap_note = ('UNINTERPRETABLE: cells are selected by market price, so price-minus-P* is conditioned on market value; the initial-gap convergence regression is mechanically positive under measurement noise.')
    for row in loc:
        row['price_minus_pstar_status'] = uninterpretable_gap_note
    for row in slow:
        row['interpretation_status'] = uninterpretable_gap_note
    for row in drift:
        row['mean_signed_convergence_status'] = uninterpretable_gap_note
        row['initial_gap_size_response_status'] = uninterpretable_gap_note
    for row in poly_results:
        row['price_minus_pstar_status'] = uninterpretable_gap_note
    result={'scope':{'season':'2025-26 regular season','windows':'Knowable: first Q4 state <=3:00, following 10 wall minutes; final 5 regulation game-clock minutes','no_overtime_exclusion':True,'in_game_rows_only':True,'postgame_or_game-end windows used':False,'bootstrap_draws':DRAWS,'cluster':'game'},
            'kalshi':{'rows':int(len(k)),'games':int(k.game_id.nunique()),
                      'overtime_trades_in_knowable_window':int(k.loc[k.window.eq('Knowable')&k.ot_observed].shape[0]),
                      'localization':loc,'slow_tracking_regressions':slow,
                      'event_free_running_drift':drift,'exploitability':exploit},
            'polymarket':{'source_file':str(POLY.relative_to(ROOT)),'maker_fill_rows_after_window_filter':int(poly_rows),'pstar_matched_rows':int(poly_joined),'results':poly_results},
            'interpretation_status':uninterpretable_gap_note,
            'methods':{'primary_gap':'longshot trade price minus P* for the same contract, folded at the selected-team market price; game-equal means with game-clustered percentile bootstrap','outcome_check':'folded longshot settlement Y minus folded trade price','mid':'5-second rolling trade-inferred bid and ask in the selected-team coordinate; both sides required, crossed quotes excluded','taker_buy_sell':'selected_taker_outcome_side transformed into the folded longshot contract direction','clock_decay':'Phase 4 selected-team clock_decay sign-transformed to the folded longshot side','slow_regression':'equal-game-weight WLS, one-cent market-price fixed effects, game-clustered sandwich SE','drift':'last trade at or before 5/15/30s in the same event-origin episode, endpoints and intervening observed PBP states running; contract side fixed at entry; convergence is |gap0|-|gaph| and its size response is continuous','profit':'per contract: longshot price minus realized longshot payout Y, less large-size historical-formula fee; taker version also subtracts valid 5s half-spread; trade-weighted and first qualifying row per game, game-cluster bootstrap','polymarket':'read-only maker-fill parquet; contract price/outcome and P* transformed to seed-17 selected-team, then folded to the longshot side'} }
    (OUT/'phase5_residual_mechanisms.json').write_text(json.dumps(result,indent=2,default=str))
    # Expanded machine-readable outputs make each requested cell auditable.
    flat=[]
    for x in loc:
        row={'window':x['window'],'band':x['band'],'dimension':x['dimension'],
             'split':x.get('split'),'trades':x.get('trades'),'games':x.get('games'),
             'price_minus_pstar_status':x.get('price_minus_pstar_status')}
        for c in ('time_cell','state_cell'):
            if c in x: row['split']=x[c]
        for m in ('price_minus_pstar','y_minus_price','mid_minus_pstar','y_minus_mid'):
            q=x.get(m,{})
            if isinstance(q,dict):
                row[m+'_estimate']=q.get('estimate')
                row[m+'_ci_low']=q.get('ci95',[None,None])[0]
                row[m+'_ci_high']=q.get('ci95',[None,None])[1]
        flat.append(row)
    pd.DataFrame(flat).to_csv(OUT/'phase5_residual_localization.csv',index=False)
    pd.DataFrame(poly_results).to_json(OUT/'phase5_residual_polymarket.json',orient='records',indent=2)
    print(json.dumps({'kalshi_rows':len(k),'kalshi_games':k.game_id.nunique(),
                      'polymarket_rows':poly_rows,'polymarket_pstar_matched':poly_joined,
                      'localization_cells':len(loc),'slow_regressions':len(slow),
                      'drift_results':len(drift),'exploitability_results':len(exploit)},indent=2))


if __name__ == '__main__':
    main()
