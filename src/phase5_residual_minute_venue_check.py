"""Matched/unmatched minute-median outcome diagnostic for Kalshi and Polymarket."""
from pathlib import Path
import sys, json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/interim/phase5'
DRAWS=2000
SEED=20261024
BANDS=[('0.05–0.20',.05,.20),('0.10–0.40',.10,.40)]

def first_entry_minute_rows(frame, venue, window, band):
    z=frame.loc[frame.window.eq(window)&frame.price.between(*band[1:],inclusive='both')].copy()
    z['minute_bin']=np.ceil(pd.to_numeric(z.clock_s_remaining,errors='coerce')/60).astype('Int64')
    z=z.dropna(subset=['minute_bin','ts','y','price'])
    # Period is part of key: each quarter/OT period has its own clock.
    agg=(z.groupby(['game_id','period','minute_bin'],sort=False,observed=True)
         .agg(ts=('ts','min'),y_selected=('y_selected','first'),
              median_selected_price=('p_selected','median'),
              median_price=('price','median'),n_trades=('price','size'))
         .reset_index())
    agg['y']=np.where(agg.median_selected_price.le(.5),agg.y_selected,1-agg.y_selected).astype('int8')
    agg['venue']=venue
    agg['y_minus_median_price']=agg.y-agg.median_price
    return agg

def mean_boot(x,seed):
    # First-entry sample has one minute per game; resample whole games.
    y=x.y_minus_median_price.to_numpy(float)
    n=len(y)
    if not n:return {'estimate':None,'ci95':[None,None],'games':0,'game_minutes':0}
    rng=np.random.default_rng(seed)
    ix=rng.integers(0,n,size=(DRAWS,n))
    boot=y[ix].mean(axis=1)
    return {'estimate':float(y.mean()),'ci95':[float(q) for q in np.quantile(boot,[.025,.975])],
            'games':int(x.game_id.nunique()),'game_minutes':int(len(x)),
            'bootstrap_draws':DRAWS,'cluster':'game'}

def main():
    kal=pd.read_parquet(OUT/'phase5_residual_mechanisms_kalshi_cache.parquet')
    kal=kal.rename(columns={'ts':'ts','y':'y','clock_s_remaining':'clock_s_remaining'})
    kal['y_selected']=np.where(pd.to_numeric(kal.p_selected,errors='coerce').le(.5),
                               kal.y,1-kal.y).astype('int8')
    sys.path.insert(0,str(ROOT/'src'))
    import phase5_residual_mechanisms as base
    poly_cache=OUT/'phase5_residual_polymarket_audited_cache.parquet'
    if poly_cache.exists():
        poly=pd.read_parquet(poly_cache)
    else:
        pbp,starts,_=base.load_pbp()
        poly,_,_=base.load_polymarket(pbp,starts)
    poly['ts']=pd.to_datetime(poly.ts,utc=True,errors='coerce')
    clock_col='game_clock_remaining' if 'game_clock_remaining' in poly else 'clock_s_remaining'
    poly['clock_s_remaining']=pd.to_numeric(poly[clock_col],errors='coerce')
    poly['period']=pd.to_numeric(poly.period,errors='coerce').astype('Int64')
    results=[]; minute_rows=[]
    for window in ('Knowable','Final 5'):
      for band in BANDS:
        a=first_entry_minute_rows(kal,'Kalshi',window,band)
        b=first_entry_minute_rows(poly,'Polymarket',window,band)
        keys=['game_id','period','minute_bin']
        matched_keys=a[keys].merge(b[keys],on=keys,how='inner').drop_duplicates()
        a['matched']=pd.MultiIndex.from_frame(a[keys]).isin(pd.MultiIndex.from_frame(matched_keys[keys]))
        b['matched']=pd.MultiIndex.from_frame(b[keys]).isin(pd.MultiIndex.from_frame(matched_keys[keys]))
        # Matched first-entry is the same earliest jointly observed minute for both venues.
        paired=(a.loc[a.matched].merge(b.loc[b.matched],on=keys,suffixes=('_kalshi','_poly')))
        paired['order_ts']=paired[['ts_kalshi','ts_poly']].min(axis=1)
        first_keys=(paired.sort_values(['order_ts','period','minute_bin'],kind='stable')
                    .drop_duplicates('game_id',keep='first')[keys])
        for venue,x in [('Kalshi',a),('Polymarket',b)]:
          q=x.merge(first_keys,on=keys,how='inner').sort_values(['ts','period','minute_bin'],kind='stable').copy()
          stat=mean_boot(q,SEED+len(results)*31)
          results.append({'window':window,'band':band[0],'sample':'matched','venue':venue,**stat})
          if len(q):
            w=q.copy(); w['window']=window; w['band']=band[0]; w['sample']='matched'
            minute_rows.append(w)
        for venue,x in [('Kalshi',a),('Polymarket',b)]:
          q=x.loc[~x.matched].sort_values(['ts','period','minute_bin'],kind='stable')
          q=q.drop_duplicates('game_id',keep='first').copy()
          stat=mean_boot(q,SEED+len(results)*31)
          results.append({'window':window,'band':band[0],'sample':'unmatched','venue':venue,**stat})
          if len(q):
            w=q.copy(); w['window']=window; w['band']=band[0]; w['sample']='unmatched'
            minute_rows.append(w)
    res=pd.DataFrame(results)
    res.to_csv(OUT/'phase5_residual_minute_venue_check.csv',index=False)
    pd.concat(minute_rows,ignore_index=True).to_parquet(OUT/'phase5_residual_minute_venue_cells.parquet',index=False)
    print(res.to_string(index=False))
if __name__=='__main__': main()
