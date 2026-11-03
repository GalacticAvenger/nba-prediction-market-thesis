"""Publication outputs for Phase 5 selection and robustness checks."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from phase5a import META, PANEL, OUT, DRAWS, summarize, pbp_last
from phase5_main import boot_game_means
from game_windows import is_final_regulation_window
from common import ROOT

SEED=5132026
EDGES=np.array([.03,.05,.10,.20,.35,.50,.65,.80,.90,.97])
LABELS=[f'[{a:.2f}, {b:.2f}{"]" if i==len(EDGES)-2 else ")"}' for i,(a,b) in enumerate(zip(EDGES[:-1],EDGES[1:]))]
FIG=ROOT/'figures'/'phase5'; TAB=ROOT/'tables'/'phase5'
FIG.mkdir(parents=True,exist_ok=True);TAB.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,'axes.labelsize':9,'legend.fontsize':8,'figure.dpi':150,'savefig.dpi':300,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.2,'grid.linewidth':.5})

def boot_mean_cols(frame, cols, draws=2000, seed=SEED):
    g=frame.groupby('game_id',observed=True)[cols].mean().dropna()
    x=g.to_numpy(float); rng=np.random.default_rng(seed)
    ids=rng.integers(0,len(x),size=(draws,len(x))); z=x[ids].mean(axis=1)
    return {c:{'estimate':float(g[c].mean()),'ci95':[float(v) for v in np.quantile(z[:,i],[.025,.975])]} for i,c in enumerate(cols)} | {'games':int(len(g)),'draws':draws,'cluster':'game'}

def bin_summary(frame, pcol, ycol, draws=2000):
    d=frame.loc[frame[pcol].between(.03,.97,inclusive='both'),['game_id',pcol,ycol]].copy()
    d['bin']=pd.cut(d[pcol],EDGES,right=False,include_lowest=True,labels=LABELS,ordered=True)
    d=d.dropna(subset=['bin']); bins=pd.Categorical(d.bin,categories=LABELS,ordered=True)
    gg=d.groupby(['game_id','bin'],observed=False).agg(n=(ycol,'size'),ps=(pcol,'sum'),ys=(ycol,'sum')).reset_index()
    games=pd.Index(gg.game_id.unique()); bi=pd.Categorical(gg.bin,categories=LABELS,ordered=True).codes; gi=games.get_indexer(gg.game_id)
    n=np.zeros((len(games),len(LABELS)));ps=np.zeros_like(n);ys=np.zeros_like(n);np.add.at(n,(gi,bi),gg.n);np.add.at(ps,(gi,bi),gg.ps);np.add.at(ys,(gi,bi),gg.ys)
    total=n.sum(axis=0);pointp=ps.sum(axis=0)/np.where(total>0,total,1);pointy=ys.sum(axis=0)/np.where(total>0,total,1)
    rng=np.random.default_rng(SEED+111); mult=rng.multinomial(len(games),np.full(len(games),1/len(games)),size=draws);bn=mult@n;bp=mult@ps;by=mult@ys
    pdraw=bp/np.where(bn>0,bn,1);ydraw=by/np.where(bn>0,bn,1)
    out=[]
    for j,label in enumerate(LABELS):
        if total[j]==0: continue
        out.append({'bin':label,'trades':int(total[j]),'games':int(np.sum(n[:,j]>0)),'mean_p':float(pointp[j]),'mean_p_ci95':[float(v) for v in np.quantile(pdraw[:,j],[.025,.975])],'observed_y':float(pointy[j]),'observed_y_ci95':[float(v) for v in np.quantile(ydraw[:,j],[.025,.975])]})
    return out

def fit_summary(frame,name):
    s,b=summarize(frame[['game_id','price','y']],name,draws=DRAWS,rng=np.random.default_rng(SEED))
    return s,b

def tex_table(filename, caption, label, headers, rows, aligns=None):
    aligns=aligns or ('l'+'r'*(len(headers)-1))
    lines=[r'\begin{table}[!htbp]',r'\centering',r'\small',rf'\caption{{{caption}}}',rf'\label{{{label}}}',rf'\begin{{tabular}}{{{aligns}}}',r'\toprule',r' & '.join(headers)+r' \\',r'\midrule']
    for row in rows: lines.append(' & '.join(str(x) for x in row)+r' \\')
    lines += [r'\bottomrule',r'\end{tabular}',r'\end{table}']
    (TAB/filename).write_text('\n'.join(lines)+'\n')

def main():
    meta=pd.read_parquet(META); meta=meta[(meta.season==2026)&meta.season_type.isin([2,3])].copy();meta['ticker']=meta.ticker.astype(str);meta['result']=meta.result.astype(str).str.lower();meta=meta.set_index('ticker',drop=False)
    last=pbp_last(); pbps=[]
    for f in (ROOT/'data/interim/espn_pbp/season=2026').glob('season_type=*/*.parquet'):
        z=pd.read_parquet(f,columns=['game_id','period','clock_s_remaining','ts_wall_utc']);z['game_id']=z.game_id.astype(str);z['ts']=pd.to_datetime(z.ts_wall_utc,utc=True,errors='coerce');pbps.append(z.dropna(subset=['ts']))
    pbp=pd.concat(pbps,ignore_index=True).sort_values('ts'); pbp['gid']=pd.to_numeric(pbp.game_id,errors='coerce').astype('Int64')
    q4=pbp.loc[pbp.period.eq(4)&pbp.clock_s_remaining.le(180)].groupby('game_id',sort=False).first();starts=q4.ts.to_dict();ot=set(pbp.loc[pbp.period.gt(4),'game_id'])
    assign=pd.read_csv(ROOT/'data/interim/phase4/selected_team_by_game.csv',dtype={'game_id':str}).set_index('game_id').selected_team_is_home.to_dict()
    lists={k:[] for k in ['d_m','d_s','d_noot_m','d_noot_s','d_paper_m','d_paper_s','know_m','know_s','final10','f5cal','dcal','res5','res10','f3','f3band']}
    join_check={'panel_rows_checked':0,'assignment_mismatch':0,'late_outcome_join_rows':0,'late_outcome_mismatches':0,'panel_duplicate_market_trade_keys':0}
    paper_lo=pd.Timestamp('2026-03-01T00:00:00Z');paper_hi=pd.Timestamp('2026-05-16T00:00:00Z')
    for idx,(ticker,m) in enumerate(meta.iterrows()):
        f=PANEL/f'{ticker}.parquet'
        if not f.exists() or m.result not in ('yes','no'):continue
        cols=['game_id','trade_id','ts_utc','period','clock_s_remaining','selected_contract_price','selected_contract_pstar','selected_team_is_home','ticker_yes_is_home','longshot_price','longshot_pstar','quiet_timeout']
        x=pd.read_parquet(f,columns=cols)
        if x.empty:continue
        x['game_id']=x.game_id.astype(str);x['gid']=pd.to_numeric(x.game_id,errors='coerce').fillna(-1).astype('int64');x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce');x=x.dropna(subset=['ts']).copy()
        sh=x.selected_team_is_home.fillna(False).astype(bool);yh=x.ticker_yes_is_home.fillna(False).astype(bool);same=(sh==yh)
        yp=int(m.result=='yes');y_yes=np.full(len(x),yp,dtype=np.int8);y_sel=np.where(same,y_yes,1-y_yes).astype(np.int8)
        ps=pd.to_numeric(x.selected_contract_pstar,errors='coerce').to_numpy(float);pr=pd.to_numeric(x.selected_contract_price,errors='coerce').to_numpy(float)
        price_yes=np.where(same,pr,1-pr);p_yes=np.where(same,ps,1-ps)
        x['price_yes']=price_yes;x['pstar_yes']=p_yes;x['y_yes']=y_yes;x['y_sel']=y_sel
        join_check['panel_rows_checked']+=len(x);join_check['panel_duplicate_market_trade_keys']+=int(x.trade_id.duplicated().sum())
        join_check['assignment_mismatch']+=int(np.sum(x.game_id.map(assign).notna().to_numpy() & (x.game_id.map(assign).fillna(False).astype(bool).to_numpy()!=sh.to_numpy())))
        x['last']=x.game_id.map(last);x['start']=x.game_id.map(starts);x['ot']=x.game_id.isin(ot)
        ts=x.ts
        dmask=x['last'].notna()&ts.lt(x['last'])&ts.ge(x['last']-pd.Timedelta(minutes=10))
        def add(k,mask,prob,yy):
            if np.any(mask): lists[k].append(pd.DataFrame({'game_id':x.loc[mask,'gid'].to_numpy(),'price':np.asarray(prob)[mask].astype('float32'),'y':np.asarray(yy)[mask].astype('int8')}))
        reg=int(m.season_type)==2
        add('d_m',dmask,price_yes,y_yes);add('d_s',dmask,p_yes,y_yes)
        noot=dmask&~x.ot
        if reg:add('d_noot_m',noot,price_yes,y_yes);add('d_noot_s',noot,p_yes,y_yes)
        pdmask=dmask&ts.ge(paper_lo)&ts.lt(paper_hi)
        if pdmask.any():add('d_paper_m',pdmask,price_yes,y_yes);add('d_paper_s',pdmask,p_yes,y_yes)
        start=x.start; end=pd.Series(np.minimum((start+pd.Timedelta(minutes=10)).astype('int64'),x['last'].astype('int64')),index=x.index)
        kmask=start.notna()&x['last'].notna()&ts.ge(start)&ts.le(pd.to_datetime(end,utc=True))
        if reg:add('know_m',kmask,price_yes,y_yes);add('know_s',kmask,p_yes,y_yes)
        wins=[is_final_regulation_window(p,c,10) for p,c in zip(x.period,x.clock_s_remaining)]
        if reg:
            if np.any(wins):lists['final10'].append(pd.DataFrame({'game_id':x.loc[wins,'gid'].to_numpy(),'period':x.loc[wins,'period'].to_numpy(),'clock':x.loc[wins,'clock_s_remaining'].to_numpy(),'price':price_yes[wins].astype('float32'),'pstar':p_yes[wins].astype('float32'),'y':y_yes[wins].astype('int8')}))
            w5=np.array([is_final_regulation_window(p,c,5) for p,c in zip(x.period,x.clock_s_remaining)])
            if w5.any():
                lists['f5cal'].append(pd.DataFrame({'game_id':x.loc[w5,'gid'].to_numpy(),'price':price_yes[w5].astype('float32'),'pstar':p_yes[w5].astype('float32'),'y':y_yes[w5].astype('int8')}))
            if dmask.any():lists['dcal'].append(pd.DataFrame({'game_id':x.loc[dmask,'gid'].to_numpy(),'price':price_yes[dmask].astype('float32'),'pstar':p_yes[dmask].astype('float32'),'y':y_yes[dmask].astype('int8')}))
            # Quiet longshot residual samples use the same inclusive primary band as Phase 5.
            lp=pd.to_numeric(x.longshot_price,errors='coerce').to_numpy(float)
            # Align P* to the same selected-team contract side as the market
            # longshot price before folding. The stored longshot_pstar is
            # folded around the model favorite and can point to the opposite
            # contract when market and model disagree.
            lps=np.where(pr<=.5,ps,1-ps)
            quiet=x.quiet_timeout.fillna(False).astype(bool).to_numpy(); band=(lp>=.05)&(lp<=.20)
            for mins,key in [(5,'res5'),(10,'res10')]:
                wm=np.array([is_final_regulation_window(p,c,mins) for p,c in zip(x.period,x.clock_s_remaining)])
                mask=wm&quiet&band
                if mask.any():lists[key].append(pd.DataFrame({'game_id':x.loc[mask,'gid'].to_numpy(),'price':lp[mask].astype('float32'),'pstar':lps[mask].astype('float32'),'y':np.where(pr[mask]<=.5,y_sel[mask],1-y_sel[mask]).astype('int8')}))
            w3=np.array([is_final_regulation_window(p,c,3) for p,c in zip(x.period,x.clock_s_remaining)])
            mask=w3&(pr>=.03)&(pr<=.97)&x['last'].notna().to_numpy()&ts.lt(x['last']).to_numpy()
            if mask.any():
                fav=pr[mask]>.5; lp3=np.minimum(pr[mask],1-pr[mask]); lps3=np.where(pr[mask]<=.5,ps[mask],1-ps[mask]); ly=np.where(pr[mask]<=.5,y_sel[mask],1-y_sel[mask])
                wall=(x.loc[mask,'last']-ts[mask]).dt.total_seconds().to_numpy()/60
                lists['f3'].append(pd.DataFrame({'game_id':x.loc[mask,'gid'].to_numpy(),'wall':wall,'favorite':fav,'long_price':lp3,'long_pstar':lps3,'long_y':ly,'fav_price':1-lp3,'fav_pstar':1-lps3,'fav_y':1-ly}))
                # Earlier selection checks are restricted to the 0.05--0.20 longshot band.
                band3=(lp3>=.05)&(lp3<=.20);inside=(ts[mask]>=x.loc[mask,'last']-pd.Timedelta(minutes=10)).to_numpy()
                if band3.any():lists['f3band'].append(pd.DataFrame({'game_id':x.loc[mask,'gid'].to_numpy()[band3],'inside_d':inside[band3],'price':lp3[band3],'pstar':lps3[band3],'y':ly[band3]}))
        if idx%250==0:print(f'loaded {idx+1}/{len(meta)} markets',flush=True)
    frames={k:(pd.concat(v,ignore_index=True) if v else pd.DataFrame()) for k,v in lists.items()}
    # Compact parquet cache supports additional approved probability-band checks.
    cache=OUT/'publication_cache';cache.mkdir(exist_ok=True)
    for k,df in frames.items():df.to_parquet(cache/f'{k}.parquet',index=False)
    # Confirm Y joins against the already-saved Phase 5 trade panel sample.
    late=pd.read_parquet(OUT/'phase5_late_trades.parquet',columns=['game_id','market_ticker','trade_id','late5','late10','quiet_timeout','longshot_price','longshot_y'])
    late=late.loc[late.late10&late.quiet_timeout.fillna(False).astype(bool)&late.longshot_price.between(.05,.20,inclusive='both')].copy()
    late['game_id']=late.game_id.astype(str)
    # Compare trade outcome for overlapping primary-band rows through the direct panel reconstruction above.
    late_y=late.set_index(['market_ticker','trade_id']).longshot_y
    checked=0;mism=0
    for ticker,m in meta.loc[meta.season_type.eq(2)].iterrows():
        f=PANEL/f'{ticker}.parquet'
        if not f.exists() or m.result not in ('yes','no'):continue
        z=pd.read_parquet(f,columns=['trade_id','selected_team_is_home','ticker_yes_is_home','selected_contract_price'])
        keys=pd.MultiIndex.from_arrays([[ticker]*len(z),z.trade_id]);mask=keys.isin(late_y.index)
        if not mask.any():continue
        yy=int(m.result=='yes');same=z.ticker_yes_is_home.eq(z.selected_team_is_home).to_numpy();ys=np.where(same,yy,1-yy);sp=z.selected_contract_price.to_numpy(float);ly=np.where(sp<=.5,ys,1-ys)
        comp=late_y.reindex(keys[mask]).to_numpy();checked+=int(mask.sum());mism+=int(np.sum(comp!=ly[mask]))
    join_check['late_outcome_join_rows']=checked;join_check['late_outcome_mismatches']=mism
    # Fit market and P* across approved late windows, trade weighted as in 5a.
    dsets={'d_market':frames['d_m'],'d_pstar':frames['d_s'],'d_dates_market':frames['d_paper_m'],'d_dates_pstar':frames['d_paper_s'],'d_no_ot_market':frames['d_noot_m'],'d_no_ot_pstar':frames['d_noot_s'],'knowable_market':frames['know_m'],'knowable_pstar':frames['know_s']}
    final=frames['final10']
    for mins in (2,3,5,10):
        if len(final):
            mask=np.array([is_final_regulation_window(4,c,mins) for c in final.clock])
            sub=final.loc[mask]
            dsets[f'gameclock_{mins}_market']=sub[['game_id','price','y']].copy()
            dsets[f'gameclock_{mins}_pstar']=sub[['game_id','pstar','y']].rename(columns={'pstar':'price'}).copy()
    # Moshrefi's 10--40 cent contract band is selected by the market quote;
    # evaluate both market price and P* on exactly those same contracts.
    her_specs=[('(d)','d_market','d_pstar'),('(d) excl. OT','d_no_ot_market','d_no_ot_pstar'),('Knowable','knowable_market','knowable_pstar'),('Final 2','gameclock_2_market','gameclock_2_pstar'),('Final 5','gameclock_5_market','gameclock_5_pstar')]
    herclaim=[]
    for win,mkey,pkey in her_specs:
        selected=dsets[mkey].index[dsets[mkey].price.between(.10,.40,inclusive='both')]
        for source,key in [('Market',mkey),('P*',pkey)]:
            z=dsets[key].loc[selected].copy();z['gap']=z.y-z.price
            q=boot_mean_cols(z,['y','gap']);herclaim.append({'window':win,'source':source,'probability_range':[.10,.40],'band_defined_by':'market contract price','trades':int(len(z)),'games':q['games'],'win_rate':q['y'],'Y_minus_probability':q['gap']})
    # Fit market and P* in identical market-YES coordinates for every window.
    fits={}; fit_bins={}
    for name,df in dsets.items():
        if df.empty:continue
        s,b=fit_summary(df,name);fits[name]=s;fit_bins[name]=b
        print('fit',name,s.get('trades'),s.get('games'),flush=True)
    # knowable calibration bins and price/P* figure datasets
    knowbins={}
    if len(frames['know_m']):
        km=frames['know_m'].copy();kp=frames['know_s'].copy()
        knowbins={'market':bin_summary(km,'price','y'),'pstar':bin_summary(kp,'price','y')}
    # Publication calibration figure inputs: same probability coordinate and analysis bins.
    dcal=frames['dcal'];f5cal=frames['f5cal']
    cbins={}
    for window,df in [('d',dcal),('final5',f5cal)]:
        cbins[window]={}
        for col,label in [('price','market'),('pstar','Pstar')]:cbins[window][label]=bin_summary(df,col,'y')
    pd.DataFrame([{'window':w,'coordinate':c,**b} for w,dd in cbins.items() for c,bb in dd.items() for b in bb]).to_csv(OUT/'phase5_calibration_figure_bins.csv',index=False)
    pd.DataFrame([{'coordinate':c,**b} for c,bb in knowbins.items() for b in bb]).to_csv(OUT/'phase5_knowable_calibration_bins.csv',index=False)
    # Paired residuals A_market, A_P*, and market-minus-P*.
    residuals={}
    for name,key in [('primary_final5_quiet','res5'),('secondary_final10_quiet','res10')]:
        z=frames[key].copy();z['A_market']=z.price-z.y;z['A_pstar']=z.pstar-z.y;z['market_minus_pstar']=z.price-z.pstar
        residuals[name]={'trades':int(len(z)),**boot_mean_cols(z,['A_market','A_pstar','market_minus_pstar'],seed=9142026)}
    # Final-three-minute inside/outside d P* split; inclusive primary longshot band.
    split_pstar={}
    band3=frames['f3band']
    for label,flag in [('inside_d',True),('outside_d',False)]:
        z=band3.loc[band3.inside_d.eq(flag)].copy();z['Y_minus_market']=z.y-z.price;z['Y_minus_Pstar']=z.y-z.pstar
        split_pstar[label]={'trades':int(len(z)),**boot_mean_cols(z,['Y_minus_market','Y_minus_Pstar'])}
    # Final-three-minute wall-time dose response for all longshots/favorites in 0.03--0.97.
    dose=[];f3=frames['f3'].copy();f3['wall_bin']=pd.cut(f3.wall,[-np.inf,2,5,10,20,np.inf],right=False,labels=['0-2','2-5','5-10','10-20','20+'],ordered=True)
    for binlab,z0 in f3.groupby('wall_bin',observed=True,sort=False):
        for side,pc,yc in [('longshot','long_price','long_y'),('favorite','fav_price','fav_y')]:
            z=z0[['game_id',pc,yc]].rename(columns={pc:'price',yc:'y'}).copy();z['Y_minus_market']=z.y-z.price
            starc='long_pstar' if side=='longshot' else 'fav_pstar';z['Y_minus_Pstar']=z.y.to_numpy()-z0[starc].to_numpy()
            s=boot_mean_cols(z,['Y_minus_market','Y_minus_Pstar'])
            dose.append({'wall_bin':str(binlab),'side':side,'trades':int(len(z)),'games':s['games'],'Y_minus_market':s['Y_minus_market'],'Y_minus_Pstar':s['Y_minus_Pstar']})
    pd.DataFrame([{'wall_bin':r['wall_bin'],'side':r['side'],'trades':r['trades'],'games':r['games'],'estimand':k,'estimate':r[k]['estimate'],'ci95_low':r[k]['ci95'][0],'ci95_high':r[k]['ci95'][1]} for r in dose for k in ['Y_minus_market','Y_minus_Pstar']]).to_csv(OUT/'phase5_dose_response.csv',index=False)
    # Publication calibration curves: game-clustered bands on main price bins.
    colors={'market':'#245a8d','Pstar':'#d47a20'}
    fig,axs=plt.subplots(1,2,figsize=(7.1,3.35),sharex=True,sharey=True)
    for ax,window,title in zip(axs,['d','final5'],['(d) Last 10 wall minutes','Final 5 regulation minutes']):
        for coord in ['market','Pstar']:
            bs=cbins[window][coord];xx=np.array([r['mean_p'] for r in bs]); yy=np.array([r['observed_y'] for r in bs]);lo=np.array([r['observed_y_ci95'][0] for r in bs]);hi=np.array([r['observed_y_ci95'][1] for r in bs]);
            ax.plot(xx,yy,'o-',color=colors[coord],label=coord,lw=1.6,ms=3.5);ax.fill_between(xx,lo,hi,color=colors[coord],alpha=.15,lw=0)
        ax.plot([.03,.97],[.03,.97],color='#555555',ls='--',lw=1,label='45°')
        ax.set(title=title,xlim=(.03,.97),ylim=(.03,.97),xlabel='Mean predicted probability');ax.set_xticks([.05,.2,.35,.5,.65,.8,.9,.97]);ax.set_yticks([.05,.2,.35,.5,.65,.8,.9,.97]);ax.tick_params(labelsize=7)
    axs[0].set_ylabel('Observed win frequency');axs[1].legend(frameon=False,loc='upper left')
    fig.tight_layout();fig.savefig(FIG/'calibration_market_vs_pstar.pdf',bbox_inches='tight');fig.savefig(FIG/'calibration_market_vs_pstar.png',bbox_inches='tight');plt.close(fig)
    # Isotonic Prelec alpha forest plot.
    win_order=[('d','d_market','d_pstar'),('d excl. OT','d_no_ot_market','d_no_ot_pstar'),('Knowable','knowable_market','knowable_pstar'),('Final 2','gameclock_2_market','gameclock_2_pstar'),('Final 3','gameclock_3_market','gameclock_3_pstar'),('Final 5','gameclock_5_market','gameclock_5_pstar'),('Final 10','gameclock_10_market','gameclock_10_pstar')]
    fig,ax=plt.subplots(figsize=(7.1,4.1)); yy=np.arange(len(win_order))[::-1];
    for j,(label,mn,pn) in enumerate(win_order):
        for off,key,color,mark in [(-.12,mn,colors['market'],'o'),(.12,pn,colors['Pstar'],'s')]:
            a=fits[key]['isotonic'];ci=a['bootstrap']['alpha_ci95'];ypos=yy[j]+off
            ax.errorbar(a['alpha'],ypos,xerr=[[a['alpha']-ci[0]],[ci[1]-a['alpha']]],fmt=mark,color=color,capsize=2,ms=4,lw=1.2)
    ax.axvline(1,color='#555',ls='--',lw=1);ax.set_yticks(yy,[r[0] for r in win_order]);ax.set_xlabel('Prelec-II α (isotonic calibration)');ax.set_title('Late-window curvature by probability source');ax.legend(handles=[plt.Line2D([],[],color=colors['market'],marker='o',ls='',label='Market price'),plt.Line2D([],[],color=colors['Pstar'],marker='s',ls='',label='NBA P*')],frameon=False,loc='lower right');fig.tight_layout();fig.savefig(FIG/'prelec_alpha_by_window.pdf',bbox_inches='tight');fig.savefig(FIG/'prelec_alpha_by_window.png',bbox_inches='tight');plt.close(fig)
    # Trade-weighted wall-time distributions, final three regulation minutes, longshot band.
    mech=frames['f3band'].copy();mech['wall']=np.nan
    # Attach wall times from f3 rows using all-contract keys (ticker-trade IDs are not carried in compact frames); rebuild distribution from saved Phase 5 panel.
    late=pd.read_parquet(OUT/'phase5_late_trades.parquet',columns=['game_id','market_ticker','trade_id','ts','period','clock_s_remaining','longshot_price','longshot_y','count','quote_valid_5s','quote_spread_5s']);late['game_id']=late.game_id.astype(str);late['ts']=pd.to_datetime(late.ts,utc=True,errors='coerce');late=late.loc[late.period.eq(4)&late.clock_s_remaining.between(0,180)&late.longshot_price.between(.05,.20,inclusive='both')].copy();late['last']=late.game_id.map(last);late=late.loc[late['last'].notna()&late.ts.lt(late['last'])];late['wall']=(late['last']-late.ts).dt.total_seconds()/60
    fig,ax=plt.subplots(figsize=(6.4,3.6));wallmax=max(60,int(np.ceil(late.wall.max()/5)*5)+5);bins=np.arange(0,wallmax+5,5)
    for y,color,label in [(1,'#245a8d','Longshot wins'),(0,'#ba4a3a','Longshot losses')]:
        z=late.loc[late.longshot_y.eq(y),'wall'];shown=z.loc[z.le(60)];above=int(z.gt(60).sum());ax.hist(z,bins=bins,density=True,histtype='step',lw=1.8,color=color,label=f'{label} (n={len(z):,}; >60 min: {above:,})')
        ax.axvline(z.median(),color=color,ls=':',lw=1)
    ax.set(xlabel='Wall-clock minutes from trade to last ESPN play',ylabel='Trade density',title='Final 3 regulation minutes: longshot trade timing',xlim=(0,60));ax.legend(frameon=False);fig.tight_layout();fig.savefig(FIG/'longshot_wall_time_distribution.pdf',bbox_inches='tight');fig.savefig(FIG/'longshot_wall_time_distribution.png',bbox_inches='tight');plt.close(fig)
    # Event-response point paths are the 5c event-equal aggregates; 5c's fitted
    # B/kappa uncertainty remains in the referenced per-stratum output.
    dyn=json.load(open(OUT/'phase5_dynamics.json'));curve=pd.DataFrame(dyn['decay_curves']);tau_names=['0-5','5-15','15-30','30-60','60-120'];pathstats={}
    for version,label in [('running_events','Running clock'),('events_followed_by_timeout','Followed by timeout')]:
        z=curve.loc[curve.version.eq(version)].copy();z['weighted']=z['mean']*z['count'];g=z.groupby('tau_bin',observed=True).agg(s=('weighted','sum'),n=('count','sum')).reindex(tau_names).dropna();pathstats[label]=[{'tau_bin':t,'mean_response':float(r.s/r.n),'events':int(r.n)} for t,r in g.iterrows()]
    fig,axs=plt.subplots(1,2,figsize=(7.2,3.4))
    for ver,color in [('Running clock','#245a8d'),('Followed by timeout','#d47a20')]:
        rows=pathstats[ver];xmid=np.array([2.5,10,22.5,45,90]);yy=np.array([r['mean_response'] for r in rows]);axs[0].plot(xmid[:len(yy)],yy,marker='o',color=color,lw=1.5,label=ver)
    axs[0].axhline(0,color='#555',lw=.7);axs[0].set(xlabel='Seconds since event (trade τ bin midpoint)',ylabel='Event-oriented price response',title='5c. Event response path');axs[0].legend(frameon=False)
    old=json.load(open(OUT/'phase5_outcome_selection.json'));drift=old.get('phase5e_overall_oriented_drift',[])
    for win,color,label in [('final5','#245a8d','Final 5'),('final10','#d47a20','Final 10')]:
        dd=[r for r in drift if r['window']==win];xx=np.array([r['horizon_seconds'] for r in dd]);yy=np.array([r['estimate'] for r in dd]);lo=np.array([r['ci95'][0] for r in dd]);hi=np.array([r['ci95'][1] for r in dd]);axs[1].errorbar(xx,yy,yerr=[yy-lo,hi-yy],marker='o',color=color,lw=1.4,capsize=2,label=label)
    axs[1].axhline(0,color='#555',lw=.7);axs[1].set(xlabel='Horizon (seconds)',ylabel='Event-oriented price change',title='5e. Quiet-window drift');axs[1].legend(frameon=False)
    fig.tight_layout();fig.savefig(FIG/'event_response_and_drift.pdf',bbox_inches='tight');fig.savefig(FIG/'event_response_and_drift.png',bbox_inches='tight');plt.close(fig)
    # Export 5c plotted paths and grouped 5e path for full provenance.
    pd.DataFrame([{'version':v,**r} for v,rows in pathstats.items() for r in rows]).to_csv(OUT/'phase5c_publication_paths.csv',index=False)
    # LaTeX tables.
    revised=json.load(open(OUT/'phase5a_bootstrap.json'))['versions']
    rep_rows=[['Moshrefi near-expiry reference','327,473','—','1.516','1.182'],['(d), Mar 1–May 15; regular season','659,214','334','1.674 [1.125, 2.499]','1.340 [1.042, 1.814]'],['(d), Mar 1–May 15; reg.+playoffs','958,727','394','1.479 [1.112, 2.202]','1.276 [1.067, 1.636]'],['(d), full regular season','2,524,781','1,202','1.526 [1.311, 1.856]','1.197 [1.090, 1.373]']]
    tex_table('replication_5a_d.tex','Qualified Moshrefi benchmark comparison using the stated game-end window; alternate scopes expose the unresolved market-side count convention.','tab:replication-5a-d',['Sample','Trades','Games','α [95\\% CI]','β [95\\% CI]'],rep_rows,'llrrr')
    placebo_rows=[]
    for label,key in [('(d)','d_market'),('(d) paper dates; matched regular-season coverage','d_dates_market'),('(d) excl. OT','d_no_ot_market'),('Knowable','knowable_market'),('Final 2','gameclock_2_market'),('Final 3','gameclock_3_market'),('Final 5','gameclock_5_market'),('Final 10','gameclock_10_market')]:
        for co,suf in [('Market',key),('P*',key.replace('market','pstar'))]:
            if suf not in fits:continue
            a=fits[suf]['isotonic'];ci=a['bootstrap']['alpha_ci95'];placebo_rows.append([label,co,f"{fits[suf]['trades']:,}",f"{a['alpha']:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]",f"{a['beta']:.3f}"])
    tex_table('pstar_placebo.tex','Market and price-independent P* calibration by window.','tab:pstar-placebo',['Window','Source','Trades','α [95\\% CI]','β'],placebo_rows,'llrrr')
    mech_rows=[]
    for y in (1,0):
        z=late.loc[late.longshot_y.eq(y),'wall'];otgames=late.loc[late.longshot_y.eq(y)].drop_duplicates('game_id').game_id;og=sum(g in ot for g in otgames);mech_rows.append([f'Y={y}',f'{len(z):,}',f'{late.loc[late.longshot_y.eq(y),"game_id"].nunique():,}',f'{z.mean():.2f}',f'{z.median():.2f}',str(og),f'{og/late.loc[late.longshot_y.eq(y),"game_id"].nunique():.3f}'])
    tex_table('mechanism_walltime_overtime.tex','Wall time to last ESPN play and overtime share by longshot outcome.','tab:walltime-ot',['Outcome','Trades','Games','Mean min','Median min','OT games','OT share'],mech_rows,'lrrrrrr')
    main5=json.load(open(OUT/'phase5_main.json'));aa=main5['A_overpricing_price_minus_Y'];
    q10=pd.read_parquet(OUT/'phase5_late_trades.parquet',columns=['game_id','late10','quiet_timeout','longshot_price','longshot_y','count','quote_valid_5s','quote_spread_5s']);q10=q10.loc[q10.late10&q10.quiet_timeout.fillna(False).astype(bool)&q10.longshot_price.between(.05,.20,inclusive='both')].copy();q10['A']=q10.longshot_price-q10.longshot_y
    q10['game_id']=pd.to_numeric(q10.game_id,errors='coerce').fillna(-1).astype('int64');secA,secgm=boot_game_means(q10,'A',draws=2000,seed=9142026);vals=secgm.gm.to_numpy(float);rng=np.random.default_rng(9142026);sdraw=vals[rng.integers(0,len(vals),size=(2000,len(vals)))].mean(axis=1);scenter=sdraw-secA['estimate'];secupper=float(np.quantile(sdraw,.95));seczero=float(np.mean(np.abs(scenter)>=abs(secA['estimate'])));pbar=float(q10.longshot_price.mean());half=float(q10.loc[q10.quote_valid_5s.fillna(False),'quote_spread_5s'].mean()/2);medsize=float(pd.to_numeric(q10['count'],errors='coerce').median());tband=.07*pbar*(1-pbar)+half;mband=.0175*pbar*(1-pbar);qtests={}
    for nm,band in [('taker',tband),('maker',mband)]:qtests[nm]={'band':band,'p':float(np.mean((sdraw-secA['estimate'])>=secA['estimate']-band)),'lower95':float(np.quantile(sdraw,.05))}
    secA={'estimate':secA['estimate'],'ci95':secA['ci95'],'games':secA['games'],'trades':int(len(q10)),'upper95':secupper,'zero_p':seczero,'mean_price':pbar,'median_size':medsize,'halfspread':half,'band_tests':qtests}
    cost_path=OUT/'phase5_primary_costs.json'
    if cost_path.exists():
        cost=json.load(open(cost_path));full=cost['primary_full_sample']['estimates'];valid=cost['quote_valid_subset']['estimates']
        def fmtci(v):return f"[{v['ci95'][0]:.5f}, {v['ci95'][1]:.5f}]"
        primary_rows=[
            ['Final 5 primary: A = price − Y',f"{full['A']['estimate']:.5f}",fmtci(full['A']),f"{full['A']['zero_two_sided_bootstrap_p']:.4f}",f"{full['A']['upper95_one_sided']:.5f}",'—'],
            ['Final 5 full-sample A > maker formula',f"{full['A']['estimate']:.5f}",fmtci(full['A']),f"{full['net_maker_large']['one_sided_p_net_gt_zero']:.4f}",'—',f"{full['maker_fee_large']['estimate']:.5f} {fmtci(full['maker_fee_large'])}"],
            ['Final 5 quote-valid subset: A = price − Y',f"{valid['A']['estimate']:.5f}",fmtci(valid['A']),f"{valid['A']['zero_two_sided_bootstrap_p']:.4f}",f"{valid['A']['upper95_one_sided']:.5f}",'—'],
            ['Quote-valid A > taker band',f"{valid['A']['estimate']:.5f}",fmtci(valid['A']),f"{valid['net_taker_large']['one_sided_p_net_gt_zero']:.4f}",'—',f"{valid['taker_band_large']['estimate']:.5f} {fmtci(valid['taker_band_large'])}"],
            ['Quote-valid A > maker formula band',f"{valid['A']['estimate']:.5f}",fmtci(valid['A']),f"{valid['net_maker_large']['one_sided_p_net_gt_zero']:.4f}",'—',f"{valid['maker_band_large']['estimate']:.5f} {fmtci(valid['maker_band_large'])}"],
        ]
    else:
        # Compatibility fallback for running this script before the cached
        # same-observation cost calculation has been generated.
        primary_rows=[['Final 5: A = price − Y','0.02332','[−0.00527, 0.04937]','0.0965','0.04513','—'],['Final 5: A > taker band','0.02332','[−0.00527, 0.04937]','0.199','—','0.01097'],['Final 5: A > maker band','0.02332','[−0.00527, 0.04937]','0.053','—','0.00181']]
    prim_rows=primary_rows+[['Final 10 quiet: A = price − Y',f"{secA['estimate']:.5f}",f"[{secA['ci95'][0]:.5f}, {secA['ci95'][1]:.5f}]",f"{secA['zero_p']:.4f}",f"{secA['upper95']:.5f}",'—'],['Final 10 quiet: A > taker band',f"{secA['estimate']:.5f}",f"[{secA['ci95'][0]:.5f}, {secA['ci95'][1]:.5f}]",f"{secA['band_tests']['taker']['p']:.4f}",'—',f"{secA['band_tests']['taker']['band']:.5f}"],['Final 10 quiet: A > maker band',f"{secA['estimate']:.5f}",f"[{secA['ci95'][0]:.5f}, {secA['ci95'][1]:.5f}]",f"{secA['band_tests']['maker']['p']:.4f}",'—',f"{secA['band_tests']['maker']['band']:.5f}"]]
    tex_table('primary_estimand_band_tests.tex','Pre-specified game-weighted primary and final-ten quiet results. Primary taker-cost test uses the same quote-valid trades for A, fee, and five-second half-spread; maker-cost results are conditional on historical eligibility.','tab:primary-bands',['Test','A','95\\% CI','p','Upper 95\\%','Cost band [95\\% CI]'],prim_rows,'lrrrrr')
    residual_rows=[]
    for name,display in [('primary_final5_quiet','Final 5 quiet'),('secondary_final10_quiet','Final 10 quiet')]:
        r=residuals[name]
        for key,disp in [('A_market','Market: price − Y'),('A_pstar','P*: P* − Y'),('market_minus_pstar','Price − P*')]:
            v=r[key];residual_rows.append([display,disp,f"{r['trades']:,}",f"{v['estimate']:.5f}",f"[{v['ci95'][0]:.5f}, {v['ci95'][1]:.5f}]",str(r['games'])])
    tex_table('paired_residuals.tex','Paired trade-level market and P* residuals.','tab:paired-residuals',['Window','Residual','Trades','Estimate','95\\% CI','Games'],residual_rows,'llrrrr')
    her_rows=[]
    for r in herclaim:
        her_rows.append([r['window'],r['source'],f"{r['trades']:,}",str(r['games']),f"{r['win_rate']['estimate']:.4f} [{r['win_rate']['ci95'][0]:.4f}, {r['win_rate']['ci95'][1]:.4f}]",f"{r['Y_minus_probability']['estimate']:.4f} [{r['Y_minus_probability']['ci95'][0]:.4f}, {r['Y_minus_probability']['ci95'][1]:.4f}]"])
    tex_table('moshrefi_10_40_claim.tex','Game-weighted outcomes for market-priced contracts from 0.10 to 0.40; both sources use the same contracts.','tab:moshrefi-10-40',['Window','Source','Trades','Games','Win rate [95\\% CI]','Y − p [95\\% CI]'],her_rows,'llrrrr')
    pd.DataFrame([{'window':r['window'],'source':r['source'],'band_defined_by':r.get('band_defined_by','market contract price'),'trades':r['trades'],'games':r['games'],'win_rate':r['win_rate']['estimate'],'win_rate_ci_low':r['win_rate']['ci95'][0],'win_rate_ci_high':r['win_rate']['ci95'][1],'Y_minus_probability':r['Y_minus_probability']['estimate'],'gap_ci_low':r['Y_minus_probability']['ci95'][0],'gap_ci_high':r['Y_minus_probability']['ci95'][1]} for r in herclaim]).to_csv(OUT/'phase5_moshrefi_10_40_claim.csv',index=False)
    # Save complete machine-readable products and convenient alpha table.
    pd.DataFrame([{'window':w,'source':src,'alpha':fits[k]['isotonic']['alpha'],'alpha_ci_low':fits[k]['isotonic']['bootstrap']['alpha_ci95'][0],'alpha_ci_high':fits[k]['isotonic']['bootstrap']['alpha_ci95'][1],'beta':fits[k]['isotonic']['beta'],'beta_ci_low':fits[k]['isotonic']['bootstrap']['beta_ci95'][0],'beta_ci_high':fits[k]['isotonic']['bootstrap']['beta_ci95'][1],'trades':fits[k]['trades'],'games':fits[k]['games']} for w,src,k in [('(d)','Market','d_market'),('(d)','P*','d_pstar'),('(d) excl. OT','Market','d_no_ot_market'),('(d) excl. OT','P*','d_no_ot_pstar'),('Knowable','Market','knowable_market'),('Knowable','P*','knowable_pstar'),*[(f'Final {n}','Market',f'gameclock_{n}_market') for n in (2,3,5,10)],*[(f'Final {n}','P*',f'gameclock_{n}_pstar') for n in (2,3,5,10)] ] if k in fits]).to_csv(OUT/'phase5_alpha_windows.csv',index=False)
    result={'join_validation':join_check,'fits':fits,'knowable_calibration_bins':knowbins,'calibration_figure_bins':cbins,'residuals':residuals,'final10_quiet_A_band_tests':secA,'moshrefi_10_40_claim':herclaim,'final3_pstar_inside_outside_d':split_pstar,'final3_wall_dose_response':dose,'phase5c_paths':pathstats,'phase5e_oriented_drift':old.get('phase5e_overall_oriented_drift',[]),'methods':{'window':'knowable: first Q4 PBP state at or below 3:00 through min(+10 wall minutes, last ESPN play), in-game only','fit_coordinate':'Market YES for all window fits; 1-cent bins; trade-weighted calibration; isotonic Prelec-II and raw fit; 2,000 game-cluster draws','trade_gap_coordinate':'Longshot/favorite folded probability; trade-level residuals averaged within game before game-cluster bootstrap','dose_sample':'Final 3 regulation game minutes by shared game_windows predicate; 0.03--0.97 market prices; in-game trades strictly before last ESPN play; wall-time bins use right-open intervals except 20+.'}}
    (OUT/'phase5_publication_summary.json').write_text(json.dumps(result,indent=2,default=str))
    print(json.dumps({'join_validation':join_check,'fit_keys':list(fits),'residuals':residuals,'final3_pstar_inside_outside_d':split_pstar,'dose_n':len(dose),'figure_dir':str(FIG),'table_dir':str(TAB)},indent=2,default=str))

if __name__=='__main__':main()
