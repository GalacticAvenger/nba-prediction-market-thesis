"""Side and timing diagnostics on the first jointly matched game-minute."""
from pathlib import Path
import sys, json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/interim/phase5'
DRAWS=2000
SEED=20261025
BANDS=[('0.05–0.20',.05,.20),('0.10–0.40',.10,.40)]
KEYS=['game_id','period','minute_bin']
PANEL=ROOT/'data/interim/phase4/trade_panel'

def boot(frame,value,seed):
    z=frame[['game_id',value]].dropna()
    g=z.groupby('game_id',sort=False)[value].mean().to_numpy(float)
    n=len(g)
    if not n:return {'estimate':None,'ci95':[None,None],'games':0}
    rng=np.random.default_rng(seed)
    ix=rng.integers(0,n,size=(DRAWS,n))
    return {'estimate':float(g.mean()),'ci95':[float(x) for x in np.quantile(g[ix].mean(axis=1),[.025,.975])],
            'games':int(n),'bootstrap_draws':DRAWS,'cluster':'game'}

def prep_minute(df):
    z=df.copy()
    z['minute_bin']=np.ceil(pd.to_numeric(z.clock_s_remaining,errors='coerce')/60).astype('Int64')
    z['seconds_into_minute']=(z.minute_bin.astype(float)*60-pd.to_numeric(z.clock_s_remaining,errors='coerce')).clip(0,60)
    return z

def main():
    selected=pd.read_parquet(OUT/'phase5_residual_minute_venue_cells.parquet')
    selected=selected.loc[selected['sample'].eq('matched')]
    selected=selected[['window','band',*KEYS]].drop_duplicates()
    kal=prep_minute(pd.read_parquet(OUT/'phase5_residual_mechanisms_kalshi_cache.parquet'))
    sys.path.insert(0,str(ROOT/'src'))
    import phase5_residual_mechanisms as base
    pbp,starts,_=base.load_pbp()
    poly,_,_=base.load_polymarket(pbp,starts)
    poly=poly.rename(columns={'game_clock_remaining':'clock_s_remaining'})
    poly=prep_minute(poly)
    rows=[]
    def add(window,band,label,metric,frame,scale=1):
        res=boot(frame,metric,SEED+len(rows)*53)
        if res['estimate'] is not None:
            res['estimate']*=scale; res['ci95']=[x*scale for x in res['ci95']]
        rows.append({'window':window,'band':band,'measure':label,**res})
    for window in ('Knowable','Final 5'):
      for band,lo,hi in BANDS:
        sel=selected.loc[selected.window.eq(window)&selected.band.eq(band),KEYS]
        kk=kal.loc[kal.window.eq(window)&kal.price.between(lo,hi,inclusive='both')].merge(sel,on=KEYS,how='inner')
        pp=poly.loc[poly.window.eq(window)&poly.price.between(lo,hi,inclusive='both')].merge(sel,on=KEYS,how='inner')
        # Direct paired difference, one observation per matched game-minute.
        km=kk.groupby(KEYS,sort=False).agg(k_price=('price','median')).reset_index()
        pm=pp.groupby(KEYS,sort=False).agg(p_price=('price','median')).reset_index()
        pair=km.merge(pm,on=KEYS,how='inner',validate='one_to_one')
        pair['price_difference']=pair.k_price-pair.p_price
        add(window,band,'Kalshi minus Polymarket minute-median price','price_difference',pair,100)
        # Maker-side median price and mean trade-level Y-price in each matched minute.
        for side in ('buy longshot','sell longshot'):
            q=pp.loc[pp.maker_side_folded.eq(side)]
            g=q.groupby(KEYS,sort=False).agg(median_price=('price','median'),
                                            y_minus_price=('y_minus_price','mean')).reset_index()
            add(window,band,f'Polymarket maker {side}: minute-median price','median_price',g,100)
            add(window,band,f'Polymarket maker {side}: mean Y-price','y_minus_price',g,100)
        # Recover the raw YES/NO side from cached Phase 4 market rows for the
        # ticker whose YES outcome is the longshot; this yields true ask/bid sides.
        side_parts=[]
        for ticker in kk.market_ticker.drop_duplicates():
            f=PANEL/f'{ticker}.parquet'
            if not f.exists(): continue
            ids=set(kk.loc[kk.market_ticker.eq(ticker),'trade_id'])
            x=pd.read_parquet(f,columns=['trade_id','taker_outcome_side','price_yes'])
            x=x.loc[x.trade_id.isin(ids)].copy(); x['market_ticker']=ticker
            side_parts.append(x)
        if side_parts:
            raw_side=pd.concat(side_parts,ignore_index=True)
            q=kk.merge(raw_side,on=['market_ticker','trade_id'],how='inner',validate='one_to_one')
            q=q.loc[pd.to_numeric(q.price_yes,errors='coerce').le(.5)]
            for side,label in [('yes','YES-taker at ask'),('no','NO-taker at bid')]:
                g=(q.loc[q.taker_outcome_side.astype(str).str.lower().eq(side)]
                   .groupby(KEYS,sort=False).agg(median_price=('price','median')).reset_index())
                add(window,band,f'Kalshi {label}: minute-median longshot price','median_price',g,100)
        # Mean seconds into the period-specific 60-second game-clock bin per venue/minute.
        by_venue=[]
        for venue,q in [('Kalshi',kk),('Polymarket',pp)]:
            g=q.groupby(KEYS,sort=False).agg(mean_seconds=('seconds_into_minute','mean')).reset_index()
            add(window,band,f'{venue}: mean seconds into minute','mean_seconds',g,1)
            by_venue.append(g.rename(columns={'mean_seconds':f'{venue}_seconds'}))
        timing=by_venue[0].merge(by_venue[1],on=KEYS,how='inner',validate='one_to_one')
        timing['difference']=timing['Polymarket_seconds']-timing['Kalshi_seconds']
        add(window,band,'Polymarket minus Kalshi mean seconds into minute','difference',timing,1)
    res=pd.DataFrame(rows)
    res.to_csv(OUT/'phase5_residual_minute_side_diagnostic.csv',index=False)
    print(res.to_string(index=False))
if __name__=='__main__': main()
