"""Outcome-only estimators for the selection-free Phase 5 residual investigation."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/interim/phase5'
CACHE=OUT/'phase5_residual_mechanisms_kalshi_cache.parquet'
DRAWS=2000
SEED=20261023
BANDS=[('0.05–0.20',.05,.20),('0.10–0.40',.10,.40)]


def estimate(frame, metric, estimator, seed):
    z=frame[['game_id','ts',metric]].dropna().copy()
    if z.empty:
        return {'trades':0,'games':0,'estimate':None,'ci95':[None,None]}
    if estimator=='first-entry':
        z=z.sort_values(['game_id','ts'],kind='stable').drop_duplicates('game_id',keep='first')
    g=z.groupby('game_id',sort=False)[metric].agg(['sum','count','mean'])
    ng=len(g); rng=np.random.default_rng(seed)
    draws=rng.multinomial(ng,np.full(ng,1/ng),size=DRAWS)
    if estimator=='trade-weighted':
        s=g['sum'].to_numpy(float); n=g['count'].to_numpy(float)
        vals=(draws@s)/np.maximum(draws@n,1)
        point=float(s.sum()/n.sum())
    elif estimator in ('first-entry','game-weighted'):
        v=g['mean'].to_numpy(float)
        vals=(draws@v)/ng
        point=float(v.mean())
    else: raise ValueError(estimator)
    return {'trades':int(len(z)),'games':int(ng),'estimate':point,
            'ci95':[float(x) for x in np.quantile(vals,[.025,.975])],
            'cluster':'game','bootstrap_draws':DRAWS}


def rows_for_sample(frame, venue, window, band):
    rows=[]
    def emit(cell_family, cell, subset, metrics):
        for metric_name,metric in metrics:
            for est in ('trade-weighted','first-entry','game-weighted'):
                a=estimate(subset,metric,est,SEED+len(rows)*17)
                rows.append({'venue':venue,'window':window,'band':band,
                             'cell_family':cell_family,'cell':cell,
                             'measure':metric_name,'estimator':est,**a})
    emit('overall','all',frame,[('Y − price','y_minus_price')])
    if venue=='Kalshi':
        for val,label in [(True,'running'),(False,'stopped')]:
            emit('clock state',label,frame.loc[frame.clock_running.eq(val)],
                 [('Y − price','y_minus_price')])
        for side in ('buy longshot','sell longshot'):
            emit('taker side',side,frame.loc[frame.taker_side.eq(side)],
                 [('Y − price','y_minus_price')])
        valid=frame.loc[frame.valid_mid & frame.mid.notna()]
        emit('valid-mid subset','trade price',valid,[('Y − price','y_minus_price')])
        emit('valid-mid subset','mid',valid,[('Y − mid','y_minus_mid')])
        if window=='Final 5':
            for time_cell in ('0–1 min','1–2 min','2–3 min','3–5 min'):
                emit('game-clock remaining',time_cell,
                     frame.loc[frame.time_cell.eq(time_cell)],[('Y − price','y_minus_price')])
        for margin in ('1–3','4–6','7+'):
            for poss in ('yes','no','unknown'):
                cell=f'{margin} × {poss}'
                emit('score × trailing possession (descriptive)',cell,
                     frame.loc[frame.state_cell.eq(cell)],[('Y − price','y_minus_price')])
    elif venue=='Polymarket':
        for side in ('buy longshot','sell longshot'):
            emit('maker side',side,frame.loc[frame.maker_side_folded.eq(side)],
                 [('Y − price','y_minus_price')])
    return rows


def main():
    k=pd.read_parquet(CACHE)
    out=[]
    for window in ('Knowable','Final 5'):
        for band,lo,hi in BANDS:
            z=k.loc[k.window.eq(window)&k.price.between(lo,hi,inclusive='both')].copy()
            out.extend(rows_for_sample(z,'Kalshi',window,band))
    # Use the already-defined Phase 2/3 cache loaders and shared window predicate.
    sys.path.insert(0,str(ROOT/'src'))
    import phase5_residual_mechanisms as base
    poly_cache=OUT/'phase5_residual_polymarket_audited_cache.parquet'
    if poly_cache.exists():
        poly=pd.read_parquet(poly_cache)
    else:
        pbp,starts,_=base.load_pbp()
        poly,_,_=base.load_polymarket(pbp,starts)
    for window in ('Knowable','Final 5'):
        for band,lo,hi in BANDS:
            z=poly.loc[poly.window.eq(window)&poly.price.between(lo,hi,inclusive='both')].copy()
            if 'ts' not in z:
                z['ts']=pd.to_datetime(z.timestamp,unit='s',utc=True)
            out.extend(rows_for_sample(z,'Polymarket',window,band))
    df=pd.DataFrame(out)
    csv=OUT/'phase5_residual_outcome_estimators.csv'
    df.to_csv(csv,index=False)
    meta={'scope':'selection-free windows only; no game-end or OT conditioning',
          'windows':'Knowable and final 5 regulation game-clock minutes',
          'bands':['0.05–0.20','0.10–0.40'],
          'estimators':['trade-weighted','first-entry (first eligible row per game per cell)','game-weighted (sensitivity)'],
          'ci':'95% game-cluster bootstrap percentile interval; 2000 resamples',
          'kalshi_games':int(k.game_id.nunique()),
          'polymarket_rows':int(len(poly)),
          'polymarket_games':int(poly.game_id.nunique()),
          'output':str(csv.relative_to(ROOT))}
    (OUT/'phase5_residual_outcome_estimators.json').write_text(json.dumps(meta,indent=2))
    print(json.dumps(meta,indent=2))
    print('rows',len(df),'null/empty cells',int((df.trades==0).sum()))

if __name__=='__main__': main()
