"""Build a read-only cross-venue alpha table for Polymarket selection fits."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from common import write_json
from phase5a import summarize
from game_windows import is_final_regulation_window
P2=ROOT/'data/interim/phase2';P5=ROOT/'data/interim/phase5'
SEED=5132026;DRAWS=2000
SPRING_START=pd.Timestamp('2026-03-01T00:00:00Z');SPRING_END=pd.Timestamp('2026-05-16T00:00:00Z')

def fit(frame,pc,yc,name):
    z=frame[['game_id',pc,yc]].rename(columns={pc:'price',yc:'y'})
    return summarize(z,name,draws=DRAWS,rng=np.random.default_rng(SEED),bin_width=1)[0]

def pbp_clock():
    parts=[]
    for f in (ROOT/'data/interim/espn_pbp/season=2026/season_type=2').glob('*.parquet'):
        parts.append(pd.read_parquet(f,columns=['game_id','period','clock_s_remaining','ts_wall_utc']))
    p=pd.concat(parts,ignore_index=True)
    p['game_id']=p.game_id.astype(str);p['period']=pd.to_numeric(p.period,errors='coerce');p['clock_s_remaining']=pd.to_numeric(p.clock_s_remaining,errors='coerce');p['ts']=pd.to_datetime(p.ts_wall_utc,utc=True,errors='coerce')
    p=p.dropna(subset=['ts']);last=p.groupby('game_id').ts.max().to_dict();ot=set(p.loc[p.period.gt(4),'game_id'].unique())
    q=p[(p.period==4)&(p.clock_s_remaining<=180)].sort_values('ts');starts=q.groupby('game_id',sort=False).ts.first().to_dict()
    return last,ot,starts

def main():
    last,ot,starts=pbp_clock()
    meta=pd.read_parquet(ROOT/'data/interim/kalshi_market_metadata.parquet')
    meta=meta[(meta.season==2026)&(meta.season_type==2)].copy();meta['ticker']=meta.ticker.astype(str);meta['game_id']=meta.game_id.astype(str);meta['result']=meta.result.astype(str).str.lower();meta=meta.set_index('ticker')
    panels=[]
    for ticker,m in meta.iterrows():
        f=ROOT/'data/interim/phase4/trade_panel'/f'{ticker}.parquet'
        if not f.exists() or m.result not in ('yes','no'):continue
        x=pd.read_parquet(f,columns=['game_id','ts_utc','ticker_yes_is_home','selected_team_is_home','selected_contract_price','selected_contract_pstar','period','clock_s_remaining'])
        if x.empty:continue
        x['game_id']=x.game_id.astype(str);x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce');x=x.dropna(subset=['ts'])
        x['yes_y']=int(m.result=='yes');same=x.ticker_yes_is_home.eq(x.selected_team_is_home)
        x['selected_y']=np.where(same,x.yes_y,1-x.yes_y)
        x['selected_price']=pd.to_numeric(x.selected_contract_price,errors='coerce')
        x['selected_pstar']=pd.to_numeric(x.selected_contract_pstar,errors='coerce')
        x['yes_pstar']=np.where(same,x.selected_pstar,1-x.selected_pstar)
        x['last_play']=x.game_id.map(last);x['know_start']=x.game_id.map(starts);x['ot']=x.game_id.isin(ot)
        x['ticker']=ticker
        panels.append(x[['game_id','ts','period','clock_s_remaining','yes_y','selected_y','selected_price','selected_pstar','yes_pstar','last_play','know_start','ot','ticker']])
    d=pd.concat(panels,ignore_index=True)
    in_d=d.last_play.notna()&d.ts.lt(d.last_play)&d.ts.ge(d.last_play-pd.Timedelta(minutes=10))
    d_no_ot=d.loc[in_d&~d.ot].copy()
    know_end=pd.concat([d.know_start+pd.Timedelta(minutes=10),d.last_play],axis=1).min(axis=1)
    in_know=d.know_start.notna()&d.last_play.notna()&d.ts.ge(d.know_start)&d.ts.lt(know_end)
    know=d.loc[in_know].copy()
    spring=d.ts.ge(SPRING_START)&d.ts.lt(SPRING_END)
    kalshi={}
    kalshi['d_wall10_own_token_price']=json.load(open(P5/'phase5a_bootstrap.json'))['versions']['d_full_regular_season']
    # Existing output has P* for all regular-season (d) fills in market-YES coordinate.
    kalshi['d_wall10_own_token_Pstar']=json.load(open(P5/'phase5_outcome_selection.json'))['placebo_Pstar']['fits']['d_wall10_market_yes_Pstar']
    kalshi['d_wall10_excluding_ot_own_token_price']=json.load(open(P5/'phase5_outcome_selection.json'))['d_excluding_overtime']
    kalshi['knowable_wall10_selected_price']=json.load(open(P5/'phase5_outcome_selection.json'))['knowable_wall10_after_first_Q4_3min']['fit']
    # Matching P* estimates absent from saved output: calculate from read-only panels.
    pstar_sets={
        'd_wall10_excluding_ot_own_token_Pstar':(d_no_ot,'yes_pstar','yes_y'),
        'knowable_wall10_selected_Pstar':(know,'selected_pstar','selected_y'),
    }
    for minutes in (2,3,5,10):
        mask=np.fromiter((is_final_regulation_window(p,c,minutes) for p,c in zip(d.period,d.clock_s_remaining)),dtype=bool,count=len(d))
        frame=d.loc[mask&spring].copy()
        key=f'gameclock_final{minutes}_selected'
        kalshi[key+'_price']=json.load(open(P5/'phase5_quick_checks.json'))['bootstrap']['fits'][f'q4_final{minutes}_selected']
        pstar_sets[key+'_Pstar']=(frame,'selected_pstar','selected_y')
    pstar_generated={}
    for name,(frame,pc,yc) in pstar_sets.items():
        print(f'Kalshi P* fit {name}: {len(frame):,} / {frame.game_id.nunique()} games',flush=True)
        pstar_generated[name]=fit(frame,pc,yc,name)
        kalshi[name]=pstar_generated[name]
    poly=json.load(open(P2/'polymarket_selection_analysis.json'))
    table=[]
    matches={
        'd_wall10_own_token_price':('d_wall10_own_token','price','all regular season'),
        'd_wall10_own_token_Pstar':('d_wall10_own_token','Pstar','all regular season'),
        'd_wall10_excluding_ot_own_token_price':('d_wall10_excluding_ot_own_token','price','all regular season; OT games removed'),
        'd_wall10_excluding_ot_own_token_Pstar':('d_wall10_excluding_ot_own_token','Pstar','all regular season; OT games removed'),
        'knowable_wall10_selected_price':('knowable_wall10_selected','price','all regular season'),
        'knowable_wall10_selected_Pstar':('knowable_wall10_selected','Pstar','all regular season'),
    }
    for minutes in (2,3,5,10):
        polykey=f'gameclock_final{minutes}_selected_spring_match'
        kk=f'gameclock_final{minutes}_selected'
        matches[kk+'_price']=(polykey,'price','2026-03-01 through 2026-05-15 regular season')
        matches[kk+'_Pstar']=(polykey,'Pstar','2026-03-01 through 2026-05-15 regular season')
    for k,(pk,coord,scope) in matches.items():
        pf=poly['price_fits'][pk] if coord=='price' else poly['pstar_placebo_fits'][pk]
        kf=kalshi[k]
        for curve in ('raw','isotonic'):
            pfit=pf[curve];kfit=kf[curve]
            pboot=pfit.get('bootstrap') or {};kboot=kfit.get('bootstrap') or {}
            table.append({'analysis':k,'window_scope':scope,'coordinate':coord,'curve':curve,
                          'polymarket_trades':pf['trades'],'polymarket_games':pf['games'],
                          'polymarket_alpha':pfit['alpha'],'polymarket_alpha_ci95':pboot.get('alpha_ci95'),
                          'kalshi_trades':kf.get('trades'),'kalshi_games':kf.get('games'),
                          'kalshi_alpha':kfit['alpha'],'kalshi_alpha_ci95':kboot.get('alpha_ci95'),
                          'kalshi_source':'saved main-session output' if k not in pstar_generated else 'read-only Phase 4 panels, same fitter'} )
    table_df=pd.DataFrame(table)
    table_df.to_csv(P2/'polymarket_kalshi_alpha_comparison.csv',index=False)
    out={'kalshi_pstar_fits_derived_read_only':pstar_generated,'alpha_comparison':table}
    write_json(P2/'polymarket_kalshi_alpha_comparison.json',out)
    print(table_df.to_string(index=False),flush=True)
if __name__=='__main__':main()
