"""Outcome calibration, tests, fee bands, microstructure and quote diagnostics."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from common import ROOT
from phase5a import PANEL, META, OUT, DRAWS
from game_windows import is_final_regulation_window

SEED=9142026
EDGES=np.array([.03,.05,.10,.20,.35,.50,.65,.80,.90,.97])
TAU_EDGES=np.array([0,5,15,30,60,120,300,np.inf])
TAU_LABELS=['0-5','5-15','15-30','30-60','60-120','120-300','300+']

def boot_game_means(frame,value,group_cols=(),draws=DRAWS,seed=SEED):
    """Equal-weight game means and percentile cluster bootstrap CIs."""
    cols=['game_id',*group_cols]
    gm=frame.groupby(cols,observed=True)[value].mean().reset_index(name='gm')
    rng=np.random.default_rng(seed); games=gm.game_id.unique(); output=[]
    if not group_cols:
        vals=gm.gm.to_numpy(float); point=float(vals.mean())
        ids=rng.integers(0,len(vals),size=(draws,len(vals))); samples=vals[ids].mean(axis=1)
        return {'estimate':point,'games':len(vals),'ci95':np.quantile(samples,[.025,.975]).tolist(),'draws':draws},gm
    for key,g in gm.groupby(list(group_cols),observed=True,sort=False):
        vals=g.gm.to_numpy(float); ids=rng.integers(0,len(vals),size=(draws,len(vals))); samples=vals[ids].mean(axis=1)
        key=key if isinstance(key,tuple) else (key,)
        output.append({**dict(zip(group_cols,key)),'estimate':float(vals.mean()),'games':len(vals),'ci95':np.quantile(samples,[.025,.975]).tolist()})
    return output,gm

def main():
    meta=pd.read_parquet(META); meta=meta[(meta.season==2026)&meta.season_type.eq(2)].copy(); meta['ticker']=meta.ticker.astype(str); meta=meta.set_index('ticker')
    rows=[]; quote_counts={'trades':0,'valid':0,'candle_comparable':0,'candle_bidask_both_within_1c':0}
    for ticker,m in meta.iterrows():
        f=PANEL/f'{ticker}.parquet'
        if not f.exists() or str(m.result).lower() not in ('yes','no'): continue
        x=pd.read_parquet(f)
        if x.empty:continue
        x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce',format='mixed')
        x=x.dropna(subset=['ts']).sort_values('ts',kind='stable').reset_index(drop=True)
        yespx=pd.to_numeric(x.price_yes,errors='coerce').to_numpy(float)
        taker=x.taker_outcome_side.fillna(x.taker_side).astype(str).str.lower().to_numpy()
        ix=pd.DatetimeIndex(x.ts)
        ask_obs=np.where(taker=='yes',yespx,np.nan); bid_obs=np.where(taker=='no',yespx,np.nan)
        ask5=pd.Series(ask_obs,index=ix).rolling('5s',closed='both',min_periods=1).min().to_numpy()
        bid5=pd.Series(bid_obs,index=ix).rolling('5s',closed='both',min_periods=1).max().to_numpy()
        same=x.ticker_yes_is_home.eq(x.selected_team_is_home).to_numpy()
        sel_bid=np.where(same,bid5,1-ask5); sel_ask=np.where(same,ask5,1-bid5)
        crossed=np.isfinite(sel_bid)&np.isfinite(sel_ask)&(sel_bid>sel_ask)
        valid=np.isfinite(sel_bid)&np.isfinite(sel_ask)&~crossed
        # Candles validate (never fill) trade-inferred quotes. Compare selected
        # bid/ask against the corresponding one-minute candle OHLC quote ranges.
        cp=ROOT/'data/interim/kalshi_candles_1m'/f'{ticker}.parquet'
        use5=np.asarray([is_final_regulation_window(p,c,5) for p,c in zip(x.period,x.clock_s_remaining)])
        use10=np.asarray([is_final_regulation_window(p,c,10) for p,c in zip(x.period,x.clock_s_remaining)])
        if cp.exists():
            c=pd.read_parquet(cp).sort_values('end_period_ts'); ce=c.end_period_ts.to_numpy(float); tsnum=x.ts.astype('int64').to_numpy()/1e9
            ci=np.searchsorted(ce,tsnum,side='right')-1; ok=(ci>=0)&valid&(use5|use10)&((tsnum-ce[np.maximum(ci,0)])<=120)
            def qval(obj,key):
                try:return float(obj.get(key))
                except:return np.nan
            cand=0; good=0
            for j in np.flatnonzero(ok):
                cb=c.iloc[ci[j]].yes_bid; ca=c.iloc[ci[j]].yes_ask
                blo,bhi=qval(cb,'low'),qval(cb,'high'); alo,ahi=qval(ca,'low'),qval(ca,'high')
                if same[j]: sblo,sbhi,salo,sahi=blo,bhi,alo,ahi
                else: sblo,sbhi,salo,sahi=1-ahi,1-alo,1-bhi,1-blo
                if np.isfinite([sblo,sbhi,salo,sahi]).all():
                    cand+=1
                    if sblo-.01<=sel_bid[j]<=sbhi+.01 and salo-.01<=sel_ask[j]<=sahi+.01:good+=1
            quote_counts['candle_comparable']+=cand;quote_counts['candle_bidask_both_within_1c']+=good
        x['quote_valid_5s']=valid; x['quote_mid_5s']=np.where(valid,(sel_bid+sel_ask)/2,np.nan); x['quote_spread_5s']=np.where(valid,sel_ask-sel_bid,np.nan)
        # Outcome of the selected contract from the YES contract's settlement.
        yeswin=int(str(m.result).lower()=='yes')
        x['y_selected']=np.where(same,yeswin,1-yeswin)
        selp=pd.to_numeric(x.selected_contract_price,errors='coerce').to_numpy(float)
        x['longshot_price']=np.minimum(selp,1-selp)
        x['longshot_y']=np.where(selp<=.5,x.y_selected,1-x.y_selected)
        x['gap_selected']=x.y_selected-selp
        x['gap_longshot']=x.longshot_y-x.longshot_price
        # phase4's price_bin refers to selected-contract price; retain it for calibration cells.
        x['price_bin']=pd.cut(selp,EDGES,right=False,include_lowest=True).astype(str)
        x.loc[np.isclose(selp,.97),'price_bin']='[0.90,0.97]'
        x['tau_bucket']=pd.cut(pd.to_numeric(x.tau_seconds,errors='coerce'),TAU_EDGES,right=False,labels=TAU_LABELS)
        # Convert selected-side taker outcome into buying/selling the longshot contract.
        selected_bought=x.selected_taker_outcome_side.astype(str).str.lower().eq('yes').to_numpy()
        x['buy_longshot']=np.where(selp<=.5,selected_bought,~selected_bought)
        # 5s mid in folded longshot coordinate.
        x['longshot_mid']=np.where(selp<=.5,x.quote_mid_5s,1-x.quote_mid_5s)
        x['gap_longshot_mid']=x.longshot_y-x.longshot_mid
        x['game_id']=x.game_id.astype(str); x['market_ticker']=ticker
        tsnum=x.ts.astype('int64').to_numpy()/1e9
        tau=pd.to_numeric(x.tau_seconds,errors='coerce').to_numpy(float)
        origin=np.rint(tsnum-tau)
        prior=np.searchsorted(tsnum,np.nan_to_num(origin,nan=-1),side='left')-1
        x['event_origin_utc_s']=origin
        x['pre_event_selected_price']=np.where((prior>=0)&np.isfinite(origin),selp[np.maximum(prior,0)],np.nan)
        quote_counts['trades']+=len(x); quote_counts['valid']+=int(valid.sum())
        # Add only outcome-analysis rows; quote paths were calculated on the full game.
        x['late5']=use5; x['late10']=use10
        keep=['game_id','market_ticker','trade_id','ts','period','clock_s_remaining','clock_running','quiet_timeout','stoppage_type','stoppage_elapsed_seconds','tau_seconds','event_origin_utc_s','last_event_type','last_event_dPstar','clock_decay','pre_event_selected_price','selected_team_is_home','selected_contract_price','y_selected','longshot_price','longshot_y','gap_selected','gap_longshot','quote_valid_5s','quote_mid_5s','quote_spread_5s','longshot_mid','gap_longshot_mid','price_bin','tau_bucket','buy_longshot','count','late5','late10']
        rows.append(x.loc[use5|use10,keep].copy())
    d=pd.concat(rows,ignore_index=True)
    quiet=d.quiet_timeout.fillna(False).astype(bool); running=d.clock_running.fillna(False).astype(bool)
    d['stoppage']=np.where(quiet,'quiet',np.where(running,'running','other'))
    late_out=d.copy(); late_out['price_bin']=late_out.price_bin.astype(str); late_out['tau_bucket']=late_out.tau_bucket.astype(str)
    late_out.to_parquet(OUT/'phase5_late_trades.parquet',index=False)
    d['in_primary_band']=d.longshot_price.between(.05,.20,inclusive='both')
    primary=d.loc[d.late5&d.stoppage.eq('quiet')&d.in_primary_band].copy()
    a,gm=boot_game_means(primary,'gap_longshot')
    a['trades']=int(len(primary)); a['price_mean']=float(primary.longshot_price.mean()); a['outcome_mean_trade_weighted']=float(primary.longshot_y.mean())
    # Explicit opposite sign used for exploitable-overpricing tests.
    primary['A_overprice']=-primary.gap_longshot
    A,ag=boot_game_means(primary,'A_overprice'); A['trades']=len(primary)
    # The selected-team equal-game bootstrap distribution also supplies the
    # prespecified null and fee-band tests for A = price - realized frequency.
    gameA=ag.gm.to_numpy(float); rng=np.random.default_rng(SEED); drawsA=gameA[rng.integers(0,len(gameA),size=(DRAWS,len(gameA)))].mean(axis=1)
    center=drawsA-A['estimate']; A['upper_95_one_sided']=float(np.quantile(drawsA,.95)); A['zero_two_sided_bootstrap_p']=float(np.mean(np.abs(center)>=abs(A['estimate'])))
    # by-time/bin calibration cells: game-equal gap, with clustered percentile intervals.
    cell_results=[]
    for win,col in [('final5','late5'),('final10','late10')]:
        for st in ['quiet','running']:
            z=d.loc[d[col]&d.stoppage.eq(st)&d.price_bin.notna()&d.tau_bucket.notna()].copy()
            z['cell_gap']=(z.y_selected-pd.to_numeric(z.selected_contract_price,errors='coerce'))
            out,_=boot_game_means(z,'cell_gap',['price_bin','tau_bucket'])
            for r in out:r['window']=win;r['stoppage']=st
            cell_results.extend(out)
    # mids secondary: valid quote subset vs invalid quote rows in primary sample.
    quote_subset=[]
    for flag,g in primary.groupby('quote_valid_5s'):
        gw,_=boot_game_means(g,'gap_longshot',draws=DRAWS,seed=SEED)
        mid=boot_game_means(g,'gap_longshot_mid',draws=DRAWS,seed=SEED)[0] if flag else None
        quote_subset.append({'valid_5s':bool(flag),'trades':len(g),'games':int(g.game_id.nunique()),'mean_longshot_price':float(g.longshot_price.mean()),'mean_tau_seconds':float(g.tau_seconds.mean()),'mean_abs_spread':float(g.quote_spread_5s.abs().mean()) if flag else None,'gap_Y_minus_trade_price_trade_weighted':float(g.gap_longshot.mean()),'gap_Y_minus_trade_price_game_weighted':gw,'gap_Y_minus_mid_game_weighted':mid})
    quote_summary={'all_panel_trades':quote_counts['trades'],'all_panel_valid_5s_both_sides':quote_counts['valid'],'all_panel_valid_share':quote_counts['valid']/quote_counts['trades'],'candle_validation_rows':quote_counts['candle_comparable'],'candle_bid_ask_both_within_1c':quote_counts['candle_bidask_both_within_1c'],'candle_validation_share':quote_counts['candle_bidask_both_within_1c']/quote_counts['candle_comparable'] if quote_counts['candle_comparable'] else None,'primary_subset':quote_subset}
    # Fee and cost bands: latest historical taker schedule for each trade date; maker schedule listed conditionally.
    # Fee = ceil cent (rate * P * (1-P) * contracts); large-size limit is rate*P*(1-P).
    med_size=float(pd.to_numeric(primary['count'],errors='coerce').median())
    p=float(primary.longshot_price.mean()); pfee=p*(1-p); halfspread=float(primary.loc[primary.quote_valid_5s,'quote_spread_5s'].mean()/2)
    taker_large=.07*pfee; maker_large=.0175*pfee
    taker_med=float(np.ceil(.07*pfee*med_size*100-1e-10)/100/med_size); maker_med=float(np.ceil(.0175*pfee*med_size*100-1e-10)/100/med_size)
    end_fees={}
    for pp in [.05,.20]:
        q=pp*(1-pp)
        tl=.07*q;ml=.0175*q
        tm=float(np.ceil(.07*q*med_size*100-1e-10)/100/med_size);mm=float(np.ceil(.0175*q*med_size*100-1e-10)/100/med_size)
        end_fees[f'{pp:.2f}']={'large_size_taker_fee':tl,'large_size_maker_fee_formula':ml,'median_size_taker_fee':tm,'median_size_maker_fee_formula':mm}
    A['band_tests']={}
    for band_name,band in [('taker',taker_large+halfspread),('maker',maker_large)]:
        null_boot=drawsA-A['estimate']
        pv=float(np.mean(null_boot >= (A['estimate']-band)))
        lo1=float(np.quantile(drawsA,.05))
        A['band_tests'][band_name]={'band':band,'one_sided_p_A_gt_band':pv,'lower_95_one_sided':lo1,'significant_and_above_band':bool(lo1>band)}
    fee_summary={'mean_primary_price':p,'median_trade_size_contracts':med_size,'large_size_taker_fee_dollars_per_contract':taker_large,'large_size_maker_fee_formula_dollars_per_contract':maker_large,'median_size_taker_fee_dollars_per_contract':taker_med,'median_size_maker_fee_formula_dollars_per_contract':maker_med,'mean_5s_halfspread_dollars_per_contract':halfspread,'large_size_taker_band_including_halfspread':taker_large+halfspread,'large_size_maker_band_formula':maker_large,'median_size_taker_band_including_halfspread':taker_med+halfspread,'median_size_maker_band_formula':maker_med,'fee_range_endpoints':end_fees,'historical_maker_eligibility':'unresolved for KXNBAGAME'}
    # Primary microstructure comparison: paired game-cell A_buy/A_sell in price-Y units.
    primary['price_overpay']=primary.longshot_price-primary.longshot_y
    primary['longshot_price_bin']=pd.cut(primary.longshot_price,[.05,.10,.200001],right=False,include_lowest=True).astype(object)
    primary['buy_sell']=np.where(primary.buy_longshot,'buy_longshot','sell_longshot')
    cell_keys=['longshot_price_bin','tau_bucket']
    micro=[]
    for key,g in primary.groupby(cell_keys,observed=True,sort=False):
        key=key if isinstance(key,tuple) else (key,)
        sides={}
        for side,sg in g.groupby('buy_sell'):
            per=sg.groupby('game_id').price_overpay.mean()
            if len(per): sides[side]=per
        if not {'buy_longshot','sell_longshot'}.issubset(sides): continue
        common=sides['buy_longshot'].index.intersection(sides['sell_longshot'].index)
        if len(common)<1:continue
        buy=sides['buy_longshot'].loc[common].to_numpy(); sell=sides['sell_longshot'].loc[common].to_numpy()
        r=np.random.default_rng(SEED+len(micro)); ix=r.integers(0,len(common),size=(DRAWS,len(common)))
        vals={'A_buy':buy,'A_sell':sell,'A_mid_approx':(buy+sell)/2,'spread_effect_approx':buy-sell}
        rec=dict(zip(cell_keys,key)); rec['games_paired']=len(common)
        for nm,v in vals.items():
            sam=v[ix].mean(axis=1); rec[nm]=float(v.mean()); rec[nm+'_ci95']=np.quantile(sam,[.025,.975]).tolist()
        rec['trades_buy']=int((g.buy_sell=='buy_longshot').sum());rec['trades_sell']=int((g.buy_sell=='sell_longshot').sum());micro.append(rec)
    # Fee-band tests use a point band applied to each paired cell estimate.
    for r in micro:
        pt=float(primary.longshot_price.mean()); fee=.07*pt*(1-pt); maker=.0175*pt*(1-pt)
        for nm,band in [('taker',fee),('maker',maker)]:
            observed=r['A_mid_approx']; lo,hi=r['A_mid_approx_ci95'];
            r[nm+'_band_large_size']=band
            # one-sided percentile-bootstrap p for H0 A_mid <= band
            # (the aggregate table is descriptive; formal A tests are game-level above).
    out={'primary_estimand_Y_minus_price':a,'A_overpricing_price_minus_Y':A,'calibration_cells':cell_results,'microstructure_primary_by_game_cell':micro,'quotes':quote_summary,'fee_band':fee_summary,'method':{'bootstrap_draws':DRAWS,'cluster':'game','seed':SEED,'game_weighting':'average trades within game, then average games'}}
    (OUT/'phase5_main.json').write_text(json.dumps(out,indent=2,default=str))
    pd.DataFrame(cell_results).to_csv(OUT/'phase5b_calibration_cells.csv',index=False)
    pd.DataFrame(micro).to_csv(OUT/'phase5h_microstructure_cells.csv',index=False)
    primary_out=primary.copy(); primary_out['price_bin']=primary_out.price_bin.astype(str)
    primary_out['longshot_price_bin']=primary_out.longshot_price_bin.astype(str)
    primary_out['tau_bucket']=primary_out.tau_bucket.astype(str)
    primary_out.to_parquet(OUT/'phase5_primary_trades.parquet',index=False)
    print(json.dumps(out,indent=2,default=str))
if __name__=='__main__':main()
