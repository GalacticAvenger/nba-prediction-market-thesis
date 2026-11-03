"""Game-weighting, trade-weighting, first-entry, and knowable-bin checks."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from phase5a import META,PANEL,OUT,pbp_last
from game_windows import is_final_regulation_window
SEED=6102126;DRAWS=2000
EDGES=np.array([.03,.05,.10,.20,.35,.50,.65,.80,.90,.97])
LABELS=['.03-.05','.05-.10','.10-.20','.20-.35','.35-.50','.50-.65','.65-.80','.80-.90','.90-.97']

def boot_estimators(z, metrics, weighted_col=None, seed=SEED):
    z=z.dropna(subset=['game_id']+metrics).copy();g=z.groupby('game_id',sort=True)
    count=g.size().to_numpy(dtype=float)
    sums=np.column_stack([g[m].sum().to_numpy(dtype=float) for m in metrics])
    means=sums/count[:,None]
    rng=np.random.default_rng(seed);ids=rng.integers(0,len(count),size=(DRAWS,len(count)))
    # Equal game means; trade-weighted ratio of cluster totals.
    gm_draw=means[ids].mean(axis=1)
    tw_draw=sums[ids].sum(axis=1)/count[ids].sum(axis=1)[:,None]
    out={}
    for i,m in enumerate(metrics):
        out[m]={'game_weighted':{'estimate':float(means[:,i].mean()),'ci95':[float(x) for x in np.quantile(gm_draw[:,i],[.025,.975])]},
                'trade_weighted':{'estimate':float(sums[:,i].sum()/count.sum()),'ci95':[float(x) for x in np.quantile(tw_draw[:,i],[.025,.975])]},'games':int(len(count)),'trades':int(count.sum())}
    # First entry by timestamp in this cell, one row per game.
    first=z.sort_values(['game_id','ts'],kind='stable').drop_duplicates('game_id')
    nfirst=len(first);vals=first[metrics].to_numpy(float)
    if nfirst:
        fid=rng.integers(0,nfirst,size=(DRAWS,nfirst));fd=vals[fid].mean(axis=1)
        for i,m in enumerate(metrics):out[m]['first_entry']={'estimate':float(vals[:,i].mean()),'ci95':[float(x) for x in np.quantile(fd[:,i],[.025,.975])],'games':nfirst,'trades':nfirst}
    return out

def interval_est(values, seed=SEED):
    vals=np.asarray(values,float);vals=vals[np.isfinite(vals)]
    if not len(vals):return {'estimate':None,'ci95':[None,None]}
    rng=np.random.default_rng(seed);draw=vals[rng.integers(0,len(vals),size=(DRAWS,len(vals)))].mean(axis=1)
    return {'estimate':float(vals.mean()),'ci95':[float(v) for v in np.quantile(draw,[.025,.975])]}

def bin_estimators(z,pcol,first=False):
    q=z.loc[z[pcol].ge(.03)&z[pcol].lt(.97),['game_id','ts',pcol,'y']].copy()
    q['bin']=pd.cut(q[pcol],EDGES,right=False,labels=LABELS,include_lowest=True,ordered=True)
    q=q.dropna(subset=['bin'])
    out=[]
    for b,v in q.groupby('bin',observed=True,sort=False):
        if first:v=v.sort_values(['game_id','ts'],kind='stable').drop_duplicates('game_id')
        v=v.copy();v['obs']=1;res=boot_estimators(v.rename(columns={pcol:'p'}),['p','y'])
        out.append({'bin':str(b),'source':pcol,'estimator':'first-entry' if first else 'trade-weighted',
          'trades':len(v),'games':int(v.game_id.nunique()),'mean_p':res['p']['trade_weighted']['estimate'] if not first else res['p']['game_weighted']['estimate'],
          'mean_p_ci95':res['p']['trade_weighted']['ci95'] if not first else res['p']['game_weighted']['ci95'],
          'observed_y':res['y']['trade_weighted']['estimate'] if not first else res['y']['game_weighted']['estimate'],
          'observed_y_ci95':res['y']['trade_weighted']['ci95'] if not first else res['y']['game_weighted']['ci95']})
    return out

def main():
    # (d) is the full regular-season plus playoffs replication window; all
    # standings-season estimands below remain regular-season only.
    meta=pd.read_parquet(META);meta=meta[(meta.season==2026)&meta.season_type.isin([2,3])].copy();meta['ticker']=meta.ticker.astype(str);meta['result']=meta.result.astype(str).str.lower()
    last=pbp_last();parts=[];knowable_all=[]
    pbps=[]
    for f in (ROOT/'data/interim/espn_pbp/season=2026/season_type=2').glob('*.parquet'):
        p=pd.read_parquet(f,columns=['game_id','period','clock_s_remaining','ts_wall_utc']);p['game_id']=p.game_id.astype(str);p['ts']=pd.to_datetime(p.ts_wall_utc,utc=True,errors='coerce');pbps.append(p.dropna(subset=['ts']))
    pbp=pd.concat(pbps,ignore_index=True);pbp=pbp.sort_values('ts');q4=pbp.loc[pbp.period.eq(4)&pbp.clock_s_remaining.le(180)].groupby('game_id',sort=False).first();starts=q4.ts.to_dict();ot=set(pbp.loc[pbp.period.gt(4),'game_id'])
    for j,(_,m) in enumerate(meta.iterrows()):
        reg_market=int(m.season_type)==2
        f=PANEL/f'{m.ticker}.parquet'
        if not f.exists() or m.result not in ('yes','no'):continue
        cols=['game_id','market_ticker','trade_id','ts_utc','period','clock_s_remaining','selected_contract_price','selected_contract_pstar','selected_team_is_home','ticker_yes_is_home','quiet_timeout']
        x=pd.read_parquet(f,columns=cols)
        if x.empty:continue
        x['game_id']=x.game_id.astype(str);x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce');x=x.dropna(subset=['ts']).copy()
        sh=x.selected_team_is_home.fillna(False).astype(bool).to_numpy();yh=x.ticker_yes_is_home.fillna(False).astype(bool).to_numpy();same=sh==yh
        yyes=int(m.result=='yes');yy=np.full(len(x),yyes,dtype=np.int8)
        ps=pd.to_numeric(x.selected_contract_pstar,errors='coerce').to_numpy(float);pr=pd.to_numeric(x.selected_contract_price,errors='coerce').to_numpy(float)
        price_yes=np.where(same,pr,1-pr);pstar_yes=np.where(same,ps,1-ps)
        x['market_p']=price_yes;x['pstar_p']=pstar_yes;x['y']=yy;x['last']=x.game_id.map(last);x['start']=x.game_id.map(starts);x['ot']=x.game_id.isin(ot)
        end=pd.Series(np.minimum((x.start+pd.Timedelta(minutes=10)).astype('int64'),x['last'].astype('int64')),index=x.index)
        wins2=np.array([is_final_regulation_window(p,c,2) for p,c in zip(x.period,x.clock_s_remaining)])
        wins5=np.array([is_final_regulation_window(p,c,5) for p,c in zip(x.period,x.clock_s_remaining)])
        masks={'(d)':x['last'].notna().to_numpy()&x.ts.lt(x['last']-pd.Timedelta(minutes=0)).to_numpy()&x.ts.ge(x['last']-pd.Timedelta(minutes=10)).to_numpy(),
          '(d) excl. OT':reg_market & x['last'].notna().to_numpy()&x.ts.lt(x['last']).to_numpy()&x.ts.ge(x['last']-pd.Timedelta(minutes=10)).to_numpy()&~x.ot.to_numpy(),
          'Knowable':reg_market & x.start.notna().to_numpy()&x['last'].notna().to_numpy()&x.ts.ge(x.start).to_numpy()&x.ts.le(pd.to_datetime(end,utc=True)).to_numpy(),
          'Final 2':reg_market & wins2,'Final 5':reg_market & wins5}
        # corrected (d) strict in-game condition
        masks['(d)']=x['last'].notna().to_numpy()&x.ts.lt(x['last']).to_numpy()&x.ts.ge(x['last']-pd.Timedelta(minutes=10)).to_numpy()
        if reg_market and masks['Knowable'].any():
            km=masks['Knowable']
            knowable_all.append(pd.DataFrame({'game_id':x.loc[km,'game_id'].to_numpy(),'ts':x.loc[km,'ts'].to_numpy(),'market_p':price_yes[km],'pstar_p':pstar_yes[km],'y':yy[km]}))
        for win,mask in masks.items():
            band=mask & (price_yes>=.10)&(price_yes<=.40)
            if band.any():parts.append(pd.DataFrame({'window':win,'game_id':x.loc[band,'game_id'].to_numpy(),'ts':x.loc[band,'ts'].to_numpy(),'market_p':price_yes[band],'pstar_p':pstar_yes[band],'y':yy[band]}))
        # quiet windows: a fixed market longshot contract cell, P* folded to that same contract
        ysel=np.where(same,yy,1-yy)
        lp=np.minimum(pr,1-pr);lps=np.where(pr<=.5,ps,1-ps);ly=np.where(pr<=.5,ysel,1-ysel)
        quiet=x.quiet_timeout.fillna(False).astype(bool).to_numpy()&(lp>=.05)&(lp<=.20)
        for win,mask in [('Primary final 5 quiet',wins5),('Final 10 quiet',np.array([is_final_regulation_window(p,c,10) for p,c in zip(x.period,x.clock_s_remaining)]))]:
            # The main and secondary quiet estimates are regular-season
            # estimands and use the assigned selected-team contract.
            take=quiet&mask&reg_market
            if win=='Final 10 quiet':take &= x.quiet_timeout.fillna(False).astype(bool).to_numpy()
            if take.any():parts.append(pd.DataFrame({'window':win,'game_id':x.loc[take,'game_id'].to_numpy(),'ts':x.loc[take,'ts'].to_numpy(),'market_ticker':x.loc[take,'market_ticker'].astype(str).to_numpy(),'trade_id':x.loc[take,'trade_id'].astype(str).to_numpy(),'market_p':lp[take],'pstar_p':lps[take],'y':ly[take]}))
        if j%250==0:print(f'loaded {j+1}/{len(meta)} markets',flush=True)
    data=pd.concat(parts,ignore_index=True)
    # Replace legacy Phase 4 quote fields with the approved five-second quote
    # reconstruction for first-entry fee bands; candles are not used here.
    quote_file=OUT/'phase5_late_trades.parquet'
    quotes=pd.read_parquet(quote_file,columns=['market_ticker','trade_id','quote_valid_5s','quote_spread_5s'])
    quotes['market_ticker']=quotes.market_ticker.astype(str);quotes['trade_id']=quotes.trade_id.astype(str)
    quotes=quotes.drop_duplicates(['market_ticker','trade_id']).set_index(['market_ticker','trade_id'])
    quietrows=data.window.astype(str).str.contains('quiet')
    qkeys=pd.MultiIndex.from_arrays([data.loc[quietrows,'market_ticker'].astype(str),data.loc[quietrows,'trade_id'].astype(str)])
    valid=quotes.quote_valid_5s.reindex(qkeys).fillna(False).to_numpy(bool)
    spread=quotes.quote_spread_5s.reindex(qkeys).to_numpy(float)/2
    data.loc[quietrows,'halfspread']=np.where(valid,spread,np.nan)
    results={}; rows=[]
    for win,z0 in data.groupby('window',sort=False):
        z=z0.copy()
        quiet='quiet' in win.lower()
        for src,pcol in [('Market','market_p'),('P*','pstar_p')]:
            q=z[['game_id','ts',pcol,'y']].rename(columns={pcol:'p'}).copy()
            q['win_rate']=q.y
            q['gap']=q.y-q.p if not quiet else q.p-q.y # A = p-Y for quiet estimands
            metrics=['win_rate','gap']
            # Match phase5_main.boot_game_means exactly for the registered
            # Market final-five quiet primary: same rows/sign, sorted game
            # order, integer cluster resampling, and RNG seed.
            boot_seed=9142026 if win=='Primary final 5 quiet' and src=='Market' else SEED
            out=boot_estimators(q,metrics,seed=boot_seed)
            results.setdefault(win,{})[src]={'metric':'A=price-Y' if quiet else 'Y-p','trade_count':int(out['gap']['trades']),'results':out}
            for estimator in ['game_weighted','trade_weighted','first_entry']:
                for metric in metrics:
                    v=out[metric][estimator]
                    metric_label='win_rate' if metric=='win_rate' else ('A' if quiet else 'Y_minus_p')
                    rows.append({'window':win,'source':src,'estimator':estimator,'metric':metric_label,'estimate':v['estimate'],'ci95_low':v['ci95'][0],'ci95_high':v['ci95'][1],'trades':out[metric]['trades'],'games':out[metric]['games'] if estimator!='first_entry' else v['games']})
    # First-entry quiet estimates: one observation per game with a one-sided
    # percentile upper bound. Cost inference is handled by phase5_primary_costs,
    # which uses the same quote-valid observations for A and spread; do not
    # combine all first-entry outcomes with a spread computed on only a subset.
    quiet_first_tests={}
    for win in ('Primary final 5 quiet','Final 10 quiet'):
        z=data.loc[data.window.eq(win)].copy();quiet_first_tests[win]={}
        for src,pcol in [('Market','market_p'),('P*','pstar_p')]:
            qcols=['game_id','ts','market_p','halfspread','y']+([] if pcol=='market_p' else [pcol])
            q=z[qcols].copy()
            if pcol!='market_p':q=q.rename(columns={pcol:'p'})
            else:q=q.rename(columns={'market_p':'p'})
            q=q.sort_values(['game_id','ts'],kind='stable').drop_duplicates('game_id')
            vals=(q.p-q.y).to_numpy(float);point=float(vals.mean());rng=np.random.default_rng(SEED);draw=vals[rng.integers(0,len(vals),size=(DRAWS,len(vals)))].mean(axis=1)
            market_prices=q.market_p.to_numpy(float) if 'market_p' in q.columns else q.p.to_numpy(float)
            quiet_first_tests[win][src]={'estimate':point,'upper_95_one_sided':float(np.quantile(draw,.95)),'games':int(len(vals)),'bootstrap_draws':DRAWS,'seed':SEED}
    # Knowable calibration, probability bins by source. b = trade weighted; c = first trade per game within each bin.
    know=pd.concat(knowable_all,ignore_index=True);bins=[]
    for src,pcol in [('Market','market_p'),('P*','pstar_p')]:
        for isfirst in (False,True):
            r=bin_estimators(know.rename(columns={pcol:pcol}),pcol,first=isfirst)
            for v in r:v['source']=src;bins.append(v)
    outpath=OUT/'phase5_weighting';outpath.mkdir(exist_ok=True)
    (outpath/'phase5_weighting_summary.json').write_text(json.dumps({'estimators':results,'quiet_first_entry_tests':quiet_first_tests,'knowable_bins':bins,'knowable_calibration_sample':{'trades':int(len(know)),'games':int(know.game_id.nunique())},'methods':{'game_weighted':'mean of within-game means','trade_weighted':'pooled trade mean; game-cluster bootstrap resamples game clusters and preserves cluster sizes','first_entry':'earliest timestamped eligible trade per game within the market-price cell; one row per game','quiet_estimand':'A=p-Y, using market longshot side; P* folded to that exact contract','first_entry_inference':'2,000 game-resampled percentile draws; fee-band p uses centered bootstrap errors','draws':DRAWS,'seed':SEED}},indent=2))
    pd.DataFrame(rows).to_csv(outpath/'phase5_weighting_estimators.csv',index=False);pd.DataFrame(bins).to_csv(outpath/'phase5_knowable_weighting_bins.csv',index=False)
    tab=ROOT/'tables/phase5/weighting_sensitivity.tex';tab.parent.mkdir(parents=True,exist_ok=True)
    lines=[r'\begin{table}[!htbp]',r'\centering',r'\scriptsize',r'\caption{Estimator sensitivity. The pre-registered game-weighted final-five quiet estimate is primary; first-entry and trade-weighted estimates are sensitivities. Game-clustered 95\% CIs.}',r'\label{tab:phase5-weighting}',r'\begin{tabular}{llrrlll}',r'\toprule',r'Window & Source & Trades & Games & Game-weighted & First-entry & Trade-weighted \\',r'\midrule']
    for win,z in results.items():
        for src,v in z.items():
            metrics=['gap'] if 'quiet' in win.lower() else ['win_rate','gap']
            for metric in metrics:
                estimates=[v['results'][metric][e] for e in ('game_weighted','first_entry','trade_weighted')]
                games=v['results'][metric]['games'];trades=v['trade_count']
                label=('A' if 'quiet' in win.lower() else 'Y-p') if metric=='gap' else 'Win rate'
                cell=lambda a:f"{a['estimate']:.4f} [{a['ci95'][0]:.4f},{a['ci95'][1]:.4f}]"
                lines.append(f"{win} {label} & {src} & {trades:,} & {games:,} & {cell(estimates[0])} & {cell(estimates[1])} & {cell(estimates[2])} "+r"\\")
    for win,by_source in quiet_first_tests.items():
        shortwin='F5 quiet' if win.startswith('Primary') else 'F10 quiet'
        for src,v in by_source.items():
            lines.append(f"{shortwin} U95 one-sided & {src} & -- & {v['games']:,} & -- & {v['upper_95_one_sided']:.4f} & -- "+r"\\")
    lines += [r'\bottomrule',r'\end{tabular}',r'\end{table}']
    tab.write_text('\n'.join(lines)+'\n')
    claim=ROOT/'tables/phase5/moshrefi_10_40_claim.tex'
    claim_lines=[r'\begin{table}[!htbp]',r'\centering',r'\scriptsize',r'\caption{First-entry headline estimates; game- and trade-weighted sensitivity estimates for the 10--40 cent band.}',r'\label{tab:moshrefi-10-40}',r'\begin{tabular}{llrrlll}',r'\toprule',r'Window & Source & Trades & Games & First-entry & Game-weighted & Trade-weighted \\',r'\midrule']
    for win in ('(d)','(d) excl. OT','Knowable','Final 2','Final 5'):
        for src,v in results[win].items():
            for metric,label in (('win_rate','Win rate'),('gap','Y-p')):
                est=[v['results'][metric][e] for e in ('first_entry','game_weighted','trade_weighted')]
                games=v['results'][metric]['games'];trades=v['trade_count']
                cell=lambda a:f"{a['estimate']:.4f} [{a['ci95'][0]:.4f},{a['ci95'][1]:.4f}]"
                claim_lines.append(f"{win} {label} & {src} & {trades:,} & {games:,} & {cell(est[0])} & {cell(est[1])} & {cell(est[2])} "+r"\\")
    claim_lines += [r'\bottomrule',r'\end{tabular}',r'\end{table}'];claim.write_text('\n'.join(claim_lines)+'\n')
    summary_path=OUT/'phase5_publication_summary.json'
    if summary_path.exists():
        summary=json.loads(summary_path.read_text());updated=[]
        name_map={'(d)':'(d)','(d) excl. OT':'(d) excl. OT','Knowable':'Knowable','Final 2':'Final 2','Final 5':'Final 5'}
        for win in ('(d)','(d) excl. OT','Knowable','Final 2','Final 5'):
            for src,v in results[win].items():
                gap=v['results']['gap'];wr=v['results']['win_rate'];
                updated.append({'window':name_map[win],'source':src,'probability_range':[.10,.40],'band_defined_by':'market contract price','trades':v['trade_count'],'games':gap['games'],'win_rate':{'estimate':wr['game_weighted']['estimate'],'ci95':wr['game_weighted']['ci95']},'Y_minus_probability':{'estimate':gap['game_weighted']['estimate'],'ci95':gap['game_weighted']['ci95']},'estimators':{k:{'win_rate':wr[k],'Y_minus_probability':gap[k]} for k in ('game_weighted','trade_weighted','first_entry')}})
        summary['moshrefi_10_40_claim']=updated;summary_path.write_text(json.dumps(summary,indent=2))
    print(json.dumps({'datasets':{k:{s:v['trade_count'] for s,v in z.items()} for k,z in results.items()},'knowable_bins':len(bins),'out':str(outpath)},indent=2))
if __name__=='__main__':main()
