"""Build Phase 4 aligned trade panel and outcome-free power counts."""
from __future__ import annotations
import json, os, re
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from common import ROOT
from game_windows import is_final_regulation_window
warnings.filterwarnings('ignore', category=FutureWarning, message='Downcasting object dtype arrays on .fillna')

I=ROOT/'data/interim'
# Optional isolated output and constant ESPN wall-clock shift for the
# registered-offset robustness. Defaults preserve the canonical Phase 4 run.
O=Path(os.environ.get('PHASE4_OUTPUT_DIR', str(I/'phase4')))
SHIFT_SECONDS=float(os.environ.get('PHASE4_SHIFT_SECONDS','0'))
PANEL=O/'trade_panel'; PANEL.mkdir(parents=True,exist_ok=True)
P3=I/'phase3'; P2=I/'phase2'
PRICE_EDGES=[.03,.05,.10,.20,.35,.50,.65,.80,.90,.97]
PRICE_LABELS=[f'[{a:.2f},{b:.2f}{"]" if i==len(PRICE_EDGES)-2 else ")"}' for i,(a,b) in enumerate(zip(PRICE_EDGES[:-1],PRICE_EDGES[1:]))]
TAU_EDGES=[0,5,15,30,60,120,300,float('inf')]
TAU_LABELS=['[0,5)','[5,15)','[15,30)','[30,60)','[60,120)','[120,300)','[300,∞)']
PROMPT={'shot','rebound','turnover'}
ESPN_TO_KALSHI={'GS':'GSW','NO':'NOP','NY':'NYK','SA':'SAS','UTAH':'UTA','WSH':'WAS'}

def epoch(x):
    # Phase 2 restart estimates can mix whole seconds, microseconds and nanoseconds.
    return pd.to_datetime(x,utc=True,errors='coerce',format='mixed').astype('int64').to_numpy()/1e9

def main():
    sched=pd.read_parquet(I/'espn_games.parquet'); sched=sched[(sched.season==2026)&(sched.season_type==2)].copy()
    sched['game_id']=sched.espn_game_id.astype(str)
    pbp=pd.read_parquet(P2/'pbp_derived_regular.parquet'); pbp=pbp[pbp.game_id.astype(str).isin(sched.game_id)].copy()
    if SHIFT_SECONDS:
        pbp['ts_wall_utc']=pd.to_datetime(pbp.ts_wall_utc,utc=True,errors='coerce')+pd.to_timedelta(SHIFT_SECONDS,unit='s')
    pstar=pd.read_parquet(P3/'pstar_2025_26_every_second.parquet',columns=['game_id','period','clock_s_remaining','pstar','pstar_with_possession','pstar_spline_logistic'])
    meta_path=Path(os.environ.get('PHASE4_METADATA_PATH', str(I/'kalshi_market_metadata.parquet')))
    meta=pd.read_parquet(meta_path); meta=meta[(meta.season==2026)&(meta.season_type==2)].copy()
    # Optional isolated market-to-game linkage sensitivity. These environment
    # variables are used only for an explicitly requested sidecar rebuild.
    ticker_filter=os.environ.get('PHASE4_TICKER_FILTER')
    if ticker_filter:
        wanted=set(t.strip() for t in ticker_filter.split(',') if t.strip())
        meta=meta.loc[meta.ticker.astype(str).isin(wanted)].copy()
    overrides=json.loads(os.environ.get('PHASE4_GAME_ID_OVERRIDES_JSON','{}'))
    if overrides:
        meta['game_id']=meta.game_id.astype(str).map(lambda g:str(overrides.get(g,g)))
    meta=meta.merge(sched[['game_id','home_team','away_team','home_team_id','away_team_id','home_abbreviation','away_abbreviation']],on='game_id',how='inner')
    # One contract per game, assigned from sorted standings IDs before examining outcomes.
    gids=sorted(meta.game_id.astype(str).unique()); chosen=dict(zip(gids,np.random.default_rng(17).integers(0,2,len(gids))))
    assign=[]
    for g in gids:
        r=sched.loc[sched.game_id.eq(g)].iloc[0]; ishome=chosen[g]==0
        assign.append({'game_id':g,'selected_team_is_home':ishome,'selected_team_id':r.home_team_id if ishome else r.away_team_id,
                       'selected_team':r.home_team if ishome else r.away_team,
                       'selected_team_abbreviation':r.home_abbreviation if ishome else r.away_abbreviation,'seed':17})
    pd.DataFrame(assign).to_csv(O/'selected_team_by_game.csv',index=False)
    timeout=pd.read_csv(P2/'timeout_intervals.csv'); timeout=timeout[timeout.game_id.astype(str).isin(gids)].copy()
    timeout=timeout[timeout.survives_selected_buffer.fillna(False).astype(bool)].copy()
    timeout['start']=epoch(timeout.onset_wall)+SHIFT_SECONDS; timeout['end']=epoch(timeout.restart_wall_est)+SHIFT_SECONDS-timeout.quiet_window_end_buffer_selected.fillna(5).to_numpy()
    # Quarter breaks are clock-stopped, event-free intervals from the final PBP
    # record at 0:00 to the first next-period live record, trimmed by the same 5s.
    break_rows=[]
    for gid,d in pbp.groupby(pbp.game_id.astype(str),sort=False):
        x=d.dropna(subset=['ts_wall_utc','period']).copy(); x['wall']=pd.to_datetime(x.ts_wall_utc,utc=True,errors='coerce'); x=x.dropna(subset=['wall'])
        if x.empty: continue
        bounds=x.groupby('period').wall.agg(['min','max'])
        for per in (1,2,3):
            if per in bounds.index and per+1 in bounds.index:
                st=bounds.loc[per,'max'].timestamp(); en=bounds.loc[per+1,'min'].timestamp()-5
                if en>st: break_rows.append({'game_id':gid,'start':st,'end':en})
    breaks=pd.DataFrame(break_rows)
    break_by_game={g:d for g,d in breaks.groupby('game_id',sort=False)} if len(breaks) else {}
    flags=pd.read_csv(P2/'alignment_game_flags.csv'); weak=dict(zip(flags.game_id.astype(str),flags.weak_alignment_gt5_backward_steps.fillna(False)))
    # P* second lookup keyed by game, period, clock second.
    pstar['game_id']=pstar.game_id.astype(str); pmap={}
    for (g,per),d in pstar.groupby(['game_id','period'],sort=False):
        pmap[(g,int(per))]=(d.clock_s_remaining.to_numpy(dtype=int),d.pstar.to_numpy(float),
                            d.pstar_with_possession.to_numpy(float),d.pstar_spline_logistic.to_numpy(float))
    pstar_games=set(pstar.game_id.unique())
    def lookup_pstar(gid,periods,clocks,variant=0):
        out=np.full(len(periods),np.nan)
        for per in np.unique(periods):
            loc=np.flatnonzero(periods==per); pm=pmap.get((gid,int(per)))
            if pm is None: continue
            grid,base,pos,spline=pm; vals=(base,pos,spline)[variant]
            idx=np.searchsorted(-grid,-np.rint(clocks[loc]).astype(int),side='left')
            out[loc]=vals[np.clip(idx,0,len(grid)-1)]
        return out
    pbpmap={g:d for g,d in pbp.groupby(pbp.game_id.astype(str),sort=False)}
    timeouts={g:d for g,d in timeout.groupby(timeout.game_id.astype(str),sort=False)}
    timeout['phase4_clear_of_foul_ft']=True
    for ix,tr in timeout.iterrows():
        src=pbpmap.get(str(tr.game_id))
        if src is None: continue
        ats=epoch(src.ts_wall_utc); kinds=src.action_type.fillna('').str.lower().to_numpy()
        in_window=(ats>=tr.start)&(ats<=tr.end)
        has_foul_ft=any(('foul' in k) or ('free throw' in k) for k in kinds[in_window])
        timeout.loc[ix,'phase4_clear_of_foul_ft']=not has_foul_ft
    timeout_final5=np.asarray([is_final_regulation_window(p,c,5) for p,c in zip(timeout.period,timeout.clock_s_remaining)],dtype=bool)
    phase4_timeout_counts={'phase2_selected':int(len(timeout)),
        'phase2_selected_final5':int(timeout_final5.sum()),
        'excluded_foul_or_free_throw':int((~timeout.phase4_clear_of_foul_ft).sum()),
        'phase4_quiet_eligible':int(timeout.phase4_clear_of_foul_ft.sum()),
        'phase4_quiet_eligible_final5':int((timeout_final5&timeout.phase4_clear_of_foul_ft).sum()),
        'phase4_final5_games':int(timeout.loc[timeout_final5&timeout.phase4_clear_of_foul_ft,'game_id'].nunique())}
    timeouts={g:d for g,d in timeout.groupby(timeout.game_id.astype(str),sort=False)}
    meta_by_ticker={r.ticker:r for r in meta.itertuples(index=False)}
    gamesets={}; counts={}; quote_counts={'trade_rows':0,'bid_fresh':0,'ask_fresh':0,'both_quotes':0,'crossed':0,'candle_matched':0}
    aligned_rows=0; missing_clock=0; weak_rows=0; written=0
    trade_dir=Path(os.environ.get('PHASE4_TRADE_INPUT_DIR', str(I/'kalshi_trades')))
    candle_dir=Path(os.environ.get('PHASE4_CANDLE_INPUT_DIR', str(I/'kalshi_candles_1m')))
    for n,path in enumerate(sorted(trade_dir.glob('*.parquet')),1):
        ticker=path.stem; m=meta_by_ticker.get(ticker)
        if m is None: continue
        gid=str(m.game_id)
        if gid not in pbpmap or gid not in pstar_games: continue
        d=pd.read_parquet(path)
        d=d[(d.season_type==2)&(~d.is_block_trade.fillna(False))].copy()
        if d.empty: continue
        d['game_id']=gid; d['market_ticker']=ticker; d['ts']=pd.to_datetime(d.ts_utc,utc=True,errors='coerce',format='mixed')
        d=d.dropna(subset=['ts','price']).sort_values('ts',kind='stable').reset_index(drop=True)
        if d.empty: continue
        # Identify the random contract before converting quote coordinates.
        yescode=ticker.rsplit('-',1)[-1]
        homecode=ESPN_TO_KALSHI.get(str(m.home_abbreviation),str(m.home_abbreviation))
        awaycode=ESPN_TO_KALSHI.get(str(m.away_abbreviation),str(m.away_abbreviation))
        if yescode not in (homecode,awaycode):
            raise ValueError(f'Cannot identify YES team for {ticker}: schedule codes {homecode}/{awaycode}')
        home=(yescode==homecode)
        chosen_home=bool(chosen[gid]==0) # deterministic assignment: 0=home, 1=away
        selected_market=(home==chosen_home)
        ts=d.ts.astype('int64').to_numpy()/1e9; px=d.price.to_numpy(float)
        # Trade-inferred YES bid/ask: a NO taker prints at YES bid; a YES taker at YES ask.
        yes=d.taker_outcome_side.fillna(d.taker_side).str.lower().eq('yes').to_numpy()
        ask_obs=np.where(yes,px,np.nan); bid_obs=np.where(~yes,px,np.nan)
        ix=pd.DatetimeIndex(d.ts)
        r_ask=pd.Series(ask_obs,index=ix).rolling('60s',min_periods=1).min().to_numpy()
        r_bid=pd.Series(bid_obs,index=ix).rolling('60s',min_periods=1).max().to_numpy()
        cp=candle_dir/f'{ticker}.parquet'; cb=np.full(len(d),np.nan); ca=np.full(len(d),np.nan); candle_age=np.full(len(d),np.inf)
        if cp.exists():
            c=pd.read_parquet(cp); c=c.sort_values('end_period_ts')
            ce=c.end_period_ts.to_numpy(float); ci=np.searchsorted(ce,ts,side='right')-1; ok=ci>=0
            if ok.any():
                ca[ok]=pd.to_numeric(c.iloc[ci[ok]].yes_ask.map(lambda x:x.get('close') if isinstance(x,dict) else np.nan),errors='coerce')
                cb[ok]=pd.to_numeric(c.iloc[ci[ok]].yes_bid.map(lambda x:x.get('close') if isinstance(x,dict) else np.nan),errors='coerce')
                candle_age[ok]=ts[ok]-ce[ci[ok]]
        ca=np.where(candle_age<=120,ca,np.nan); cb=np.where(candle_age<=120,cb,np.nan)
        ask=np.fmin(r_ask,ca); bid=np.fmax(r_bid,cb)
        selected_bid=np.where(selected_market, bid, 1-ask)
        selected_ask=np.where(selected_market, ask, 1-bid)
        selected_taker=np.where(selected_market,d.taker_outcome_side.fillna(d.taker_side).str.lower().to_numpy(),
                                np.where(d.taker_outcome_side.fillna(d.taker_side).str.lower().to_numpy()=='yes','no','yes'))
        ask_stale=~np.isfinite(ask); bid_stale=~np.isfinite(bid)
        crossed=np.isfinite(ask)&np.isfinite(bid)&(bid>ask)
        # A pair of side observations that crosses is not a usable contemporaneous quote.
        bid_stale|=crossed; ask_stale|=crossed
        quote_valid=~(bid_stale|ask_stale)
        quote_mid=np.where(quote_valid,(bid+ask)/2,np.nan)
        quote_half_spread=np.where(quote_valid,(ask-bid)/2,np.nan)
        # PBP mapping uses the latest timestamped record at or before each trade.
        a=pbpmap[gid].copy(); a['wall']=pd.to_datetime(a.ts_wall_utc,utc=True,errors='coerce'); a=a.dropna(subset=['wall']).sort_values(['wall','period','clock_s_remaining'],kind='stable').reset_index(drop=True)
        if a.empty: continue
        at=a.wall.astype('int64').to_numpy()/1e9; ai=np.searchsorted(at,ts,side='right')-1; ai=np.clip(ai,0,len(a)-1)
        period=a.period.to_numpy()[ai].astype(int); clock=a.clock_s_remaining.to_numpy(dtype=float)[ai]
        running=a.clock_running.to_numpy()[ai]; action=a.action_type.fillna('').to_numpy()[ai]
        # Home P* at the matched event clock and its possession/spline robustness counterparts.
        ph=lookup_pstar(gid,period,clock,0); php=lookup_pstar(gid,period,clock,1); psp=lookup_pstar(gid,period,clock,2)
        pteam=ph if home else 1-ph; pteam_pos=php if home else 1-php; pteam_spline=psp if home else 1-psp
        p_selected=px if selected_market else 1-px
        ps_selected=pteam if selected_market else 1-pteam
        ps_pos_selected=pteam_pos if selected_market else 1-pteam_pos
        ps_spline_selected=pteam_spline if selected_market else 1-pteam_spline
        long_price=np.minimum(p_selected,1-p_selected); long_pstar=np.minimum(ps_selected,1-ps_selected)
        # Latest material event (score or possession change) drives tau and event descriptors.
        scoreh=a.score_home.to_numpy(float); scorea=a.score_away.to_numpy(float)
        poss=a.possession.fillna('').astype(str).to_numpy()
        score_delta=np.r_[0,np.diff(scoreh-scorea)]
        poss_change=np.r_[False,poss[1:]!=poss[:-1]]
        types=a.action_type.fillna('').str.lower().to_numpy()
        is_event=(score_delta!=0)|poss_change|np.array([('turnover' in t) or ('defensive rebound' in t) for t in types])
        ei=np.where(is_event)[0]
        ev_at=at[ei]
        ev_ix=np.searchsorted(ev_at,ts,side='right')-1
        tau=np.where(ev_ix>=0,ts-ev_at[np.maximum(ev_ix,0)],np.nan)
        evrow=ei[np.maximum(ev_ix,0)] if len(ei) else np.zeros(len(d),dtype=int)
        evt_type=a.action_type.to_numpy()[evrow] if len(ei) else np.full(len(d),'')
        ev_dir=score_delta[evrow] if len(ei) else np.zeros(len(d))
        ev_pstar_home=np.full(len(ei),np.nan); ev_dp_home=np.full(len(ei),np.nan)
        if len(ei):
            ev_pstar_home=lookup_pstar(gid,a.period.to_numpy()[ei].astype(int),a.clock_s_remaining.to_numpy(float)[ei],0)
            prev=np.maximum(ei-1,0)
            before=lookup_pstar(gid,a.period.to_numpy()[prev].astype(int),a.clock_s_remaining.to_numpy(float)[prev],0)
            ev_dp_home=ev_pstar_home-before; ev_dp_home[ei==0]=np.nan
        last_event_phome=np.full(len(d),np.nan); last_dp_home=np.full(len(d),np.nan)
        if len(ei):
            has_event=ev_ix>=0; last_event_phome[has_event]=ev_pstar_home[ev_ix[has_event]]; last_dp_home[has_event]=ev_dp_home[ev_ix[has_event]]
        # Timeout window and progress since onset. Only reviewed-clean intervals survive.
        q=np.zeros(len(d),bool); q_elapsed=np.full(len(d),np.nan); q_type=np.full(len(d),'',object)
        td=timeouts.get(gid)
        if td is not None:
            for tr in td.itertuples(index=False):
                if not tr.phase4_clear_of_foul_ft: continue
                hit=(ts>=tr.start)&(ts<=tr.end)
                q|=hit; q_elapsed[hit]=ts[hit]-tr.start; q_type[hit]='timeout'
        bd=break_by_game.get(gid)
        if bd is not None:
            for br in bd.itertuples(index=False):
                hit=(ts>=br.start)&(ts<=br.end)
                q|=hit; q_elapsed[hit]=ts[hit]-br.start; q_type[hit]='period_break'
        # One-contract selected coordinates for all market states; price bins use 0.03-0.97 floor.
        one_p=pd.Series(p_selected).where((p_selected>=.03)&(p_selected<=.97))
        pbin=pd.cut(one_p,PRICE_EDGES,right=False,labels=PRICE_LABELS)
        pbin.loc[one_p.eq(.97)]=PRICE_LABELS[-1]
        taubin=pd.cut(tau,TAU_EDGES,right=False,labels=TAU_LABELS)
        unique_state,state_inverse=np.unique(np.column_stack((period,clock)),axis=0,return_inverse=True)
        late10=np.array([is_final_regulation_window(p,c,10) for p,c in unique_state],dtype=bool)
        late5=np.array([is_final_regulation_window(p,c,5) for p,c in unique_state],dtype=bool)
        ten=late10[state_inverse]; five=late5[state_inverse]
        running_bool=pd.array(running,dtype='boolean').fillna(False).to_numpy(dtype=bool)
        quiet=q & ~running_bool
        last_event_pselected=last_event_phome if chosen_home else 1-last_event_phome
        event_dp_selected=last_dp_home if chosen_home else -last_dp_home
        clock_decay=np.where(running_bool,ps_selected-last_event_pselected,np.nan)
        status=np.where(quiet,'quiet_timeout',np.where(running_bool,'running_clock','other_stoppage_or_unknown'))
        for winname,win in [('final5',five),('final10',ten)]:
            for st in ('quiet_timeout','running_clock'):
                use=win&(status==st)&pd.notna(pbin)&pd.notna(taubin)
                for b,t in zip(np.asarray(pbin)[use],np.asarray(taubin)[use]):
                    counts.setdefault((winname,st,str(b),str(t)),set()).add(gid)
        # Primary power sample uses one contract/game, folded longshot price and only surviving quiet timeouts.
        primary=five&quiet&(long_price>=.05)&(long_price<=.20)
        if primary.any():
            gs=gamesets.setdefault(gid,[])
            # one outcome/game; keep trade-weighted P* only as a variance forecast, not as an outcome.
            gs.extend(long_pstar[primary][np.isfinite(long_pstar[primary])].tolist())
        out=pd.DataFrame({'game_id':gid,'market_ticker':ticker,'trade_id':d.trade_id,'ts_utc':d.ts_utc,'period':period,'clock_s_remaining':clock,
            'clock_running':running_bool,'alignment_weak':bool(weak.get(gid,False)),'action_type':action,'tau_seconds':tau,'last_event_type':evt_type,'last_event_direction_home_score':ev_dir,
            'last_event_pstar':last_event_pselected,'last_event_dPstar':event_dp_selected,'clock_decay':clock_decay,
            'selected_team_is_home':chosen_home,'ticker_yes_is_home':home,'selected_contract_price':p_selected,'selected_contract_pstar':ps_selected,
            'pstar_with_possession':ps_pos_selected,'pstar_spline_logistic':ps_spline_selected,'longshot_price':long_price,'longshot_pstar':long_pstar,
            'price_bin':pbin.astype(object),'tau_bucket':taubin.astype(object),'quiet_timeout':quiet,'stoppage_elapsed_seconds':q_elapsed,'stoppage_type':q_type,
            'best_contract_bid_rolling_candle':selected_bid,'best_contract_ask_rolling_candle':selected_ask,'quote_mid':quote_mid,'quote_half_spread':quote_half_spread,
            'bid_undetermined':bid_stale,'ask_undetermined':ask_stale,'quote_pair_crossed':crossed,'candle_quote_age_seconds':candle_age,
            'is_final5':five,'is_final10':ten,'taker_outcome_side':d.taker_outcome_side,'selected_taker_outcome_side':selected_taker,'taker_side':d.taker_side,'count':d['count'],'price_yes':px})
        out.to_parquet(PANEL/f'{ticker}.parquet',index=False,compression='zstd'); written+=len(out)
        aligned_rows+=len(out); missing_clock+=int(np.isnan(clock).sum()); weak_rows+=int(bool(weak.get(gid,False)))*len(out)
        quote_counts['trade_rows']+=len(out); quote_counts['bid_fresh']+=int((~bid_stale).sum()); quote_counts['ask_fresh']+=int((~ask_stale).sum()); quote_counts['both_quotes']+=int(quote_valid.sum()); quote_counts['crossed']+=int(crossed.sum()); quote_counts['candle_matched']+=int((candle_age<=120).sum())
        if n%100==0: print(f'{n} market files; panel rows {written:,}',flush=True)
    power=[]
    for winname in ('final5','final10'):
      for st in ('quiet_timeout','running_clock'):
       for b in PRICE_LABELS:
        for tau_bucket in TAU_LABELS:
         key=(winname,st,b,tau_bucket); n_games=len(counts.get(key,set()))
         power.append({'window':winname,'clock_state':st,'price_bin':b,'tau_bucket':tau_bucket,'games':n_games,'under_150_games':n_games<150})
    pd.DataFrame(power).to_csv(O/'power_cells.csv',index=False)
    primary_n=len(gamesets); pergame=np.array([np.mean(v) for v in gamesets.values() if v])
    # Expected Bernoulli sampling variance under the independent, market-free P* forecasts.
    se=float(np.sqrt(np.mean(pergame*(1-pergame))/primary_n)) if primary_n else None
    ci=1.96*se if se is not None else None
    mde=(1.96+.8416)*se if se is not None else None
    primary_summary={'games':primary_n,'trade_rows':int(sum(len(x) for x in gamesets.values())),'mean_forecast_longshot_probability':float(pergame.mean()) if len(pergame) else None,
        'expected_95pct_ci_half_width':ci,'m0_proposal':ci,'mde_80pct_two_sided':mde,'flag_under_150_games':primary_n<150,
        'calculation':'independent game-level Bernoulli variance using each contributing game’s average market-free P* for the selected longshot; no Y or Y-price values used'}
    (O/'power_summary.json').write_text(json.dumps({'primary':primary_summary,'power_cells':len(power),'panel_rows':written,'aligned_games':len(gamesets),'quotes':quote_counts,'timeout_intervals':phase4_timeout_counts,
        'missing_clock_rows':missing_clock,'weak_alignment_rows':weak_rows,'config_proposal':{'price_bin_edges':PRICE_EDGES,'tau_bucket_edges_seconds':[0,5,15,30,60,120,300,'inf'],'window_minutes':[5,10],
        'quiet_stoppage':'clean timeout interval (Phase 2 exclusions plus no foul/free throw before estimated restart) and event-free quarter breaks; five-second end buffer','quote_trade_lookback_seconds':60,'quote_candle_max_age_seconds':120,'random_contract_seed':17}},indent=2))
    print(json.dumps(primary_summary,indent=2)); print('panel_rows',written,'quotes',quote_counts)

if __name__=='__main__': main()
