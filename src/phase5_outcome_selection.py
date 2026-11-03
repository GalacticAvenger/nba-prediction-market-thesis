"""Phase 5 outcome-selection diagnostics requested before Phase 6."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from common import ROOT
from phase5a import META, PANEL, OUT, summarize, DRAWS, pbp_last
from phase5_main import boot_game_means
from game_windows import is_final_regulation_window

SEED=5132026

def main():
    meta=pd.read_parquet(META)
    meta=meta[(meta.season==2026)&meta.season_type.eq(2)].copy()
    meta['ticker']=meta.ticker.astype(str); meta['result']=meta.result.astype(str).str.lower()
    meta=meta.set_index('ticker',drop=False)
    last=pbp_last()
    pbps=[]
    for f in (ROOT/'data/interim/espn_pbp/season=2026/season_type=2').glob('*.parquet'):
        p=pd.read_parquet(f,columns=['game_id','period','clock_s_remaining','ts_wall_utc'])
        p['game_id']=p.game_id.astype(str);p['ts']=pd.to_datetime(p.ts_wall_utc,utc=True,errors='coerce')
        pbps.append(p.dropna(subset=['ts']))
    pbp=pd.concat(pbps,ignore_index=True).sort_values('ts')
    ot=set(pbp.loc[pbp.period.gt(4),'game_id'].unique())
    # Market panels, with the main P* model and both outcome coordinates.
    panels=[]
    for ticker,m in meta.iterrows():
        f=PANEL/f'{ticker}.parquet'
        if not f.exists() or m.result not in ('yes','no'): continue
        x=pd.read_parquet(f,columns=['game_id','market_ticker','trade_id','ts_utc','period','clock_s_remaining','selected_contract_price','selected_contract_pstar','selected_team_is_home','ticker_yes_is_home','count','quiet_timeout'])
        x['game_id']=x.game_id.astype(str);x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce');x['market_ticker']=ticker
        x['selected_price']=pd.to_numeric(x.selected_contract_price,errors='coerce');x['selected_pstar']=pd.to_numeric(x.selected_contract_pstar,errors='coerce')
        same=x.ticker_yes_is_home.eq(x.selected_team_is_home)
        x['y_selected']=np.where(same,int(m.result=='yes'),int(m.result=='no')).astype('int8')
        x['price_yes']=np.where(same,x.selected_price,1-x.selected_price)
        x['pstar_yes']=np.where(same,x.selected_pstar,1-x.selected_pstar)
        x['y_yes']=int(m.result=='yes');x['last_play']=x.game_id.map(last);x['ot']=x.game_id.isin(ot)
        panels.append(x)
    d=pd.concat(panels,ignore_index=True)
    d=d.loc[d.ts.notna()&d.last_play.notna()&(d.ts<d.last_play)].copy()
    d['d_window']=(d.ts>=d.last_play-pd.Timedelta(minutes=10))
    # 1. P* placebo, game-clock windows and d. YES-coordinate in d, selected-team in regulation windows.
    placebo=[]
    z=d.loc[d.d_window].assign(price=lambda q:q.pstar_yes,y=lambda q:q.y_yes)
    placebo.append(('d_wall10_market_yes_Pstar',z))
    for mins in (2,3,5,10):
        mask=[is_final_regulation_window(p,c,mins) for p,c in zip(d.period,d.clock_s_remaining)]
        z=d.loc[mask].assign(price=lambda q:q.selected_pstar,y=lambda q:q.y_selected)
        placebo.append((f'gameclock_final{mins}_selected_Pstar',z))
    pfits={}
    for name,z in placebo:
        s,_=summarize(z[['game_id','price','y']],name,draws=DRAWS,rng=np.random.default_rng(SEED))
        pfits[name]=s
        print('placebo',name,s.get('trades'),s.get('games'),s.get('isotonic'),flush=True)
    # 2/3. Final 3 regulation minutes, longshot price .05-.20.
    late=pd.read_parquet(OUT/'phase5_late_trades.parquet')
    late['game_id']=late.game_id.astype(str);late['ts']=pd.to_datetime(late.ts,utc=True,errors='coerce')
    # This file is already restricted to Q4 final ten by game clock.
    f3=late.loc[late.period.eq(4)&late.clock_s_remaining.between(0,180,inclusive='both')&late.longshot_price.between(.05,.20,inclusive='left')].copy()
    f3['last_play']=f3.game_id.map(last);f3['wall_to_end_min']=(f3.last_play-f3.ts).dt.total_seconds()/60
    f3['inside_d']=f3.ts.ge(f3.last_play-pd.Timedelta(minutes=10))&f3.ts.lt(f3.last_play)
    mech={}
    for y in (1,0):
        q=f3.loc[f3.longshot_y.eq(y)]
        games=q.drop_duplicates('game_id').game_id
        mech[str(y)]={'trades':int(len(q)),'games':int(q.game_id.nunique()),'wall_minutes_to_end_trade_weighted_mean':float(q.wall_to_end_min.mean()),'wall_minutes_to_end_trade_weighted_median':float(q.wall_to_end_min.median()),'games_with_overtime':int(sum(g in ot for g in games)),'share_games_overtime':float(np.mean([g in ot for g in games])) if len(games) else None}
    splits={}
    for label,flag in [('inside_d',True),('outside_d',False)]:
        q=f3.loc[f3.inside_d.eq(flag)].copy();q['gap']=q.longshot_y-pd.to_numeric(q.longshot_price,errors='coerce')
        s,_=boot_game_means(q,'gap',draws=DRAWS,seed=SEED)
        splits[label]={'trades':int(len(q)),'games':int(q.game_id.nunique()),'estimate_Y_minus_price':s.get('estimate'),'ci95':s.get('ci95'),'draws':DRAWS,'cluster':'game'}
    # 4. d actual YES-coordinate excluding OT games.
    q=d.loc[d.d_window&~d.ot].copy().rename(columns={'price_yes':'price','y_yes':'y'})
    d_no_ot,_=summarize(q[['game_id','price','y']],'d_no_overtime',draws=DRAWS,rng=np.random.default_rng(SEED))
    # 5. Knowable wall-clock window: first Q4 ESPN state at <=3:00, next 10 wall minutes.
    q4=pbp.loc[pbp.period.eq(4)&pbp.clock_s_remaining.le(180)].sort_values('ts')
    starts=q4.groupby('game_id',as_index=False).first().set_index('game_id').ts.to_dict()
    d['know_start']=d.game_id.map(starts)
    kw=d.loc[d.know_start.notna()&d.ts.ge(d.know_start)&d.ts.lt(d.know_start+pd.Timedelta(minutes=10))].copy()
    # selected-team market coordinate, matching the main Phase 5 estimand.
    know_fit,_=summarize(kw[['game_id','selected_price','y_selected']].rename(columns={'selected_price':'price','y_selected':'y'}),'knowable_wall10',draws=DRAWS,rng=np.random.default_rng(SEED))
    # 6. Metadata close_time vs last ESPN play.
    meta2=meta.reset_index(drop=True).copy();meta2['last_play']=meta2.game_id.astype(str).map(last)
    meta2['close']=pd.to_datetime(meta2.close_time,utc=True,errors='coerce',format='mixed')
    meta2['close_minus_last_min']=(meta2.close-meta2.last_play).dt.total_seconds()/60
    cm=meta2.dropna(subset=['close_minus_last_min'])
    close_stats={'markets':int(len(cm)),'close_before_last_play':int(cm.close_minus_last_min.lt(0).sum()),'close_equal_last_play':int(cm.close_minus_last_min.eq(0).sum()),'close_after_last_play':int(cm.close_minus_last_min.gt(0).sum()),'minutes_close_minus_last_play_median_p10_p90':[float(v) for v in np.quantile(cm.close_minus_last_min,[.1,.5,.9])], 'created_time_fields':int(meta2.created_time.notna().sum()),'open_time_fields':int(meta2.open_time.notna().sum()),'close_time_fields':int(meta2.close_time.notna().sum()),'metadata_has_close_time_history':False}
    # 7. Final-ten quiet secondary A-band tests, seed 17 selected-team longshot.
    quiet=late.loc[late.late10&late.quiet_timeout.fillna(False)&late.longshot_price.between(.05,.20,inclusive='left')].copy()
    quiet['A']=quiet.longshot_price-quiet.longshot_y
    a,ag=boot_game_means(quiet,'A',draws=DRAWS,seed=9142026)
    gamevals=ag.gm.to_numpy(float);rng=np.random.default_rng(9142026);bd=gamevals[rng.integers(0,len(gamevals),size=(DRAWS,len(gamevals)))].mean(axis=1)
    pmean=float(quiet.longshot_price.mean()); med=float(pd.to_numeric(quiet['count'],errors='coerce').median())
    half=float(quiet.loc[quiet.quote_valid_5s,'quote_spread_5s'].mean()/2)
    bands={'taker':.07*pmean*(1-pmean)+half,'maker':.0175*pmean*(1-pmean)}
    band_tests={k:{'band':v,'one_sided_p_A_gt_band':float(np.mean((bd-a['estimate'])>=a['estimate']-v)),'lower_95_one_sided':float(np.quantile(bd,.05))} for k,v in bands.items()}
    out={'placebo_Pstar':{'fits':pfits,'method':'Trade-time P* substituted for price; identical one-cent calibration bins, raw and isotonic Prelec-II fits; 2,000 game-cluster bootstrap draws. d uses market-YES P* and outcome; game-clock uses selected-team P* and outcome.'},'final3_longshot_wall_and_overtime':mech,'final3_split_by_d_window_game_weighted_Y_minus_price':splits,'d_excluding_overtime':d_no_ot,'knowable_wall10_after_first_Q4_3min':{'trades':int(len(kw)),'games':int(kw.game_id.nunique()),'fit':know_fit,'window':'[first ESPN Q4 state at clock <=3:00, +10 wall minutes); cached in-game market panel rows only'},'close_time_metadata':close_stats,'final10_quiet_secondary_A_band_tests':{'trades':int(len(quiet)),'games':int(quiet.game_id.nunique()),'A_estimate':a,'mean_price':pmean,'median_trade_size':med,'mean_halfspread':half,'band_tests':band_tests,'method':'game-equal mean of game-level trade-average price minus outcome; 2,000 game-cluster bootstrap; cost formula as Phase 5d.'}}
    (OUT/'phase5_outcome_selection.json').write_text(json.dumps(out,indent=2,default=str))
    print(json.dumps(out,indent=2,default=str))
if __name__=='__main__':main()
