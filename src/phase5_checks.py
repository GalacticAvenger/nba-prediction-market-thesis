"""Coordinate, regulation-window, and clock-span checks for Phase 5a."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from common import ROOT
from phase5a import PANEL, META, OUT, PAPER_START, PAPER_END, DRAWS, summarize
from game_windows import is_final_regulation_window

def main():
    meta=pd.read_parquet(META); meta=meta[(meta.season==2026)&meta.season_type.eq(2)].copy()
    meta['ticker']=meta.ticker.astype(str); meta['result']=meta.result.astype(str).str.lower()
    meta=meta.set_index('ticker',drop=False)
    # PBP is batched; collect final wall stamp by game.
    pb=[]
    for f in (ROOT/'data/interim/espn_pbp/season=2026/season_type=2').glob('*.parquet'):
        x=pd.read_parquet(f,columns=['game_id','ts_wall_utc'])
        x['ts']=pd.to_datetime(x.ts_wall_utc,utc=True,errors='coerce'); pb.append(x.dropna(subset=['ts']))
    pb=pd.concat(pb,ignore_index=True); pb['game_id']=pb.game_id.astype(str)
    last=pb.groupby('game_id').ts.max().to_dict()
    panels=[]
    for ticker,m in meta.iterrows():
        f=PANEL/f'{ticker}.parquet'
        if not f.exists() or m.result not in ('yes','no'): continue
        x=pd.read_parquet(f,columns=['game_id','ts_utc','period','clock_s_remaining','selected_team_is_home','ticker_yes_is_home','selected_contract_price','trade_id'])
        x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce'); x['game_id']=x.game_id.astype(str)
        x=x.loc[x.ts.ge(PAPER_START)&x.ts.lt(PAPER_END)].copy()
        if x.empty: continue
        same=x.ticker_yes_is_home.eq(x.selected_team_is_home)
        x['price_selected']=pd.to_numeric(x.selected_contract_price,errors='coerce')
        x['price_yes']=np.where(same,x.price_selected,1-x.price_selected)
        x['y_yes']=int(m.result=='yes'); x['y_selected']=np.where(same,x.y_yes,1-x.y_yes)
        x['last_play']=x.game_id.map(last)
        x['market_ticker']=ticker
        panels.append(x[['game_id','market_ticker','trade_id','ts','period','clock_s_remaining','price_selected','price_yes','y_selected','y_yes','last_play']])
    d=pd.concat(panels,ignore_index=True)
    dwin=d.loc[d.last_play.notna()&(d.ts<d.last_play)&(d.ts>=d.last_play-pd.Timedelta(minutes=10))].copy()
    q10=np.asarray([is_final_regulation_window(p,c,10) for p,c in zip(d.period,d.clock_s_remaining)],dtype=bool)
    results={}; fits={}
    def run(name,frame):
        z=frame[['game_id','price','y']].copy(); s,b=summarize(z,name,draws=DRAWS,bin_width=1)
        fits[name]=s
        return s
    # Coordinate cross: same paper dates, regular-season games and identical trade rows.
    cross=[('b_gameclock10_market_yes',d.loc[q10].assign(price=d.loc[q10].price_yes,y=d.loc[q10].y_yes)),
           ('b_gameclock10_selected',d.loc[q10].assign(price=d.loc[q10].price_selected,y=d.loc[q10].y_selected)),
           ('d_wallclock10_market_yes',dwin.assign(price=dwin.price_yes,y=dwin.y_yes)),
           ('d_wallclock10_selected',dwin.assign(price=dwin.price_selected,y=dwin.y_selected))]
    for name,frame in cross: run(name,frame)
    # Location of distortion across Q4 regulation clock windows, both coordinates.
    for mins in [2,3,5,10]:
        mask=np.asarray([is_final_regulation_window(p,c,mins) for p,c in zip(d.period,d.clock_s_remaining)],dtype=bool)
        sub=d.loc[mask]
        run(f'q4_final{mins}_market_yes',sub.assign(price=sub.price_yes,y=sub.y_yes))
        run(f'q4_final{mins}_selected',sub.assign(price=sub.price_selected,y=sub.y_selected))
    # Clock span for the common (d) paper-date regular-season sample. Last PBP
    # state at or before each trade supplies the remaining regulation game clock.
    # Read PBP clock states.
    pbs=[]
    for f in (ROOT/'data/interim/espn_pbp/season=2026/season_type=2').glob('*.parquet'):
        z=pd.read_parquet(f,columns=['game_id','ts_wall_utc','period','clock_s_remaining'])
        z['game_id']=z.game_id.astype(str); z['ts']=pd.to_datetime(z.ts_wall_utc,utc=True,errors='coerce'); pbs.append(z.dropna(subset=['ts']))
    pbs=pd.concat(pbs,ignore_index=True)
    clock=[]; wall=[]
    for gid,g in dwin.groupby('game_id',sort=False):
        q=pbs.loc[pbs.game_id.eq(gid)].sort_values('ts')
        if q.empty: continue
        idx=np.searchsorted(q.ts.astype('int64').to_numpy(),g.ts.astype('int64').to_numpy(),side='right')-1
        valid=idx>=0; rem=np.full(len(g),np.nan)
        per=q.period.to_numpy()[np.maximum(idx,0)]; sec=q.clock_s_remaining.to_numpy()[np.maximum(idx,0)].astype(float)
        ok=valid&(per>=1)&(per<=4)&np.isfinite(sec)
        rem[ok]=(4-per[ok])*12+sec[ok]/60
        clock.extend(rem[ok].tolist()); wall.extend(((g.last_play-g.ts).dt.total_seconds().to_numpy()[ok]/60).tolist())
    results['d_clock_span_regular_paper_dates']={'trades_in_d_window':int(len(dwin)),'trades_with_clock_state':int(len(clock)),'mean_wall_minutes_remaining':float(np.mean(wall)),'mean_game_clock_minutes_remaining':float(np.mean(clock)),'median_game_clock_minutes_remaining':float(np.median(clock)),'game_clock_minutes_remaining_p10_p90':[float(x) for x in np.quantile(clock,[.1,.9])]}
    results['coordinate_cross_scope']='2026-03-01 through 2026-05-15 inclusive; regular season only; same seed-17 matched games and trade rows for all four fits'
    results['clock_window_scope']='2026-03-01 through 2026-05-15 inclusive; regular-season Phase 4 panel; Q4 final 2/3/5/10 game-clock minutes'
    results['bootstrap']={'draws':DRAWS,'cluster':'game','seed':5132026,'fits':fits}
    (OUT/'phase5_quick_checks.json').write_text(json.dumps(results,indent=2,default=str))
    print(json.dumps(results,indent=2,default=str))
if __name__=='__main__': main()
