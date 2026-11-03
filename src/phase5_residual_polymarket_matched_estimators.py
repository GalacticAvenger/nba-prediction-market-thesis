"""Audited Polymarket residuals on matched Kalshi/Polymarket game-minutes."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/interim/phase5'
DRAWS=2000
SEED=20261027

def clustered(frame, value, weighting, seed):
    z=frame[['game_id',value]].dropna().copy()
    if not len(z): return {'estimate':None,'ci95':[None,None],'trades':0,'games':0}
    if weighting=='first-entry':
        z=frame.sort_values('ts',kind='stable').drop_duplicates('game_id').loc[:,['game_id',value]].dropna()
    g=z.groupby('game_id',sort=False)[value].agg(['sum','count','mean'])
    n=len(g); rng=np.random.default_rng(seed)
    mult=rng.multinomial(n,np.full(n,1/n),size=DRAWS)
    if weighting=='trade-weighted':
        s=g['sum'].to_numpy(float); c=g['count'].to_numpy(float)
        boot=(mult@s)/np.maximum(mult@c,1)
        point=float(s.sum()/c.sum())
    else:
        v=g['mean'].to_numpy(float); boot=(mult@v)/n; point=float(v.mean())
    return {'estimate':point,'ci95':[float(x) for x in np.quantile(boot,[.025,.975])],
            'trades':int(len(z)),'games':int(n),'cluster':'game','draws':DRAWS}

def main():
    cells=pd.read_parquet(OUT/'phase5_residual_minute_venue_cells.parquet')
    keys=cells.loc[cells['sample'].eq('matched'),
                   ['window','band','game_id','period','minute_bin']].drop_duplicates()
    sys.path.insert(0,str(ROOT/'src'))
    import phase5_residual_mechanisms as base
    poly_cache=OUT/'phase5_residual_polymarket_audited_cache.parquet'
    if poly_cache.exists():
        poly=pd.read_parquet(poly_cache)
    else:
        pbp,starts,_=base.load_pbp()
        poly,_,_=base.load_polymarket(pbp,starts)
    poly['ts']=pd.to_datetime(poly.ts,utc=True,errors='coerce')
    poly['period']=pd.to_numeric(poly.period,errors='coerce').astype('Int64')
    clock_col='game_clock_remaining' if 'game_clock_remaining' in poly else 'clock_s_remaining'
    poly['clock_s_remaining']=pd.to_numeric(poly[clock_col],errors='coerce')
    poly['minute_bin']=np.ceil(poly.clock_s_remaining/60).astype('Int64')
    poly['y_minus_median_price']=np.nan
    rows=[]; audit=[]
    for window in ('Knowable','Final 5'):
      for band,lo,hi in [('0.05–0.20',.05,.20),('0.10–0.40',.10,.40)]:
        sample=keys.loc[keys.window.eq(window)&keys.band.eq(band)]
        chosen=poly.merge(sample,on=['window','game_id','period','minute_bin'],how='inner',validate='many_to_many')
        chosen=chosen.loc[chosen.price.between(lo,hi,inclusive='both')].copy()
        # Each game contributes the jointly observed first eligible minute selected
        # by phase5_residual_minute_venue_check.py.
        mins=(chosen.groupby(['game_id','period','minute_bin'],sort=False)
              .agg(y_selected=('y_selected','first'),
                   median_selected_price=('p_selected','median'),
                   median_price=('price','median'),
                   first_ts=('ts','min'),n_trades=('price','size')).reset_index())
        mins['y']=np.where(mins.median_selected_price.le(.5),mins.y_selected,
                           1-mins.y_selected).astype('int8')
        mins['y_minus_median_price']=mins.y-mins.median_price
        for weighting in ('trade-weighted','first-entry'):
            z=chosen.copy()
            if weighting=='first-entry':
                z=z.sort_values('ts',kind='stable').drop_duplicates('game_id')
            r=clustered(z,'y_minus_price',weighting,SEED+len(rows))
            rows.append({'window':window,'band':band,'measure':'Y − trade price',
                         'estimator':weighting,**r})
        # Minute-median estimate is a separate paired diagnostic (one minute/game).
        r=clustered(mins.rename(columns={'first_ts':'ts'}),'y_minus_median_price',
                    'first-entry',SEED+len(rows))
        rows.append({'window':window,'band':band,'measure':'Y − minute-median price',
                     'estimator':'first-entry game-minute',**r})
        audit.append({'window':window,'band':band,'matched_game_minutes':int(len(mins)),
                      'matched_games':int(mins.game_id.nunique()),'maker_rows':int(len(chosen))})
    out=pd.DataFrame(rows)
    out.to_csv(OUT/'phase5_residual_polymarket_matched_estimators.csv',index=False)
    pd.DataFrame(audit).to_csv(OUT/'phase5_residual_polymarket_matched_sample.csv',index=False)
    print(out.to_string(index=False));print(pd.DataFrame(audit).to_string(index=False))

if __name__=='__main__': main()
