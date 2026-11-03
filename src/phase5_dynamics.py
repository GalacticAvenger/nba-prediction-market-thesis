"""Phase 5c, 5e, and 5g: price-path decay, drift, and Prelec curves."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from scipy.optimize import least_squares, curve_fit
from sklearn.isotonic import IsotonicRegression
from common import ROOT
from phase5a import PANEL, META, OUT, DRAWS, prelec
from phase5_main import boot_game_means
from game_windows import is_final_regulation_window

TAU_EDGES=np.array([0,5,15,30,60,120,300,np.inf]); TAU_NAMES=['0-5','5-15','15-30','30-60','60-120','120-300','300+']; TAU_CENTERS=np.array([2.5,10,22.5,45,90,210,360.])
PRICE_EDGES=[.03,.05,.10,.20,.35,.50,.65,.80,.90,.97]
SEED=9142026

def calibration_fit(df,label):
    # One equal-weight observation per game and price cent; then average games.
    z=df.loc[df.selected_contract_price.between(.03,.97,inclusive='both')].copy();z['cent']=np.rint(z.selected_contract_price*100).astype(int)
    g=z.groupby(['game_id','cent']).agg(p=('selected_contract_price','mean'),y=('y_selected','mean')).reset_index()
    b=g.groupby('cent').agg(p=('p','mean'),rate=('y','mean'),games=('game_id','nunique')).reset_index()
    iso=IsotonicRegression(increasing=True,out_of_bounds='clip').fit_transform(b.p,b.rate,sample_weight=b.games);b['iso_rate']=iso
    res={}
    def prelec_est(b,target):
        w=np.sqrt(b.games.to_numpy(float));p=b.p.to_numpy();y=b[target].to_numpy()
        fit=least_squares(lambda q:w*(prelec(p,*np.exp(q))-y),np.log([1.2,1]),bounds=(np.log([1e-4,1e-4]),np.log([1e4,1e4])),max_nfev=1000)
        return np.exp(fit.x),float(np.sum(fit.fun**2))
    rng=np.random.default_rng(20261021); games=pd.Index(g.game_id.unique()); centers=np.arange(1,100); gi=games.get_indexer(g.game_id);ci=g.cent.to_numpy()-1
    nn=np.zeros((len(games),99)); ps=np.zeros_like(nn); ys=np.zeros_like(nn)
    nn[gi,ci]=1; ps[gi,ci]=g.p.to_numpy(); ys[gi,ci]=g.y.to_numpy()
    draws=rng.multinomial(len(games),np.full(len(games),1/len(games)),size=DRAWS); boot={'rate':[],'iso_rate':[]}
    for mult in draws:
        n=mult@nn; p_sum=mult@ps; y_sum=mult@ys; keep=n>0
        bb=pd.DataFrame({'cent':centers[keep],'p':p_sum[keep]/n[keep],'rate':y_sum[keep]/n[keep],'games':n[keep]})
        bb['iso_rate']=IsotonicRegression(increasing=True,out_of_bounds='clip').fit_transform(bb.p,bb.rate,sample_weight=bb.games)
        for target in ['rate','iso_rate']:
            ab,_=prelec_est(bb,target);boot[target].append(ab)
    for target in ['rate','iso_rate']:
        ab,sse=prelec_est(b,target);arr=np.asarray(boot[target]);aa,be=ab
        res[target]={'alpha':float(aa),'beta':float(be),'reduced_form_weighting_curvature_1_over_alpha':float(1/aa),'sse':sse,'bootstrap_2000_game_cluster':{'alpha_ci95':np.quantile(arr[:,0],[.025,.975]).tolist(),'beta_ci95':np.quantile(arr[:,1],[.025,.975]).tolist(),'draws':int(len(arr))}}
    b['version']=label
    return res,b

def cpt_fit(df):
    # Fit observed market price as the CPT binary indifference price at empirical P.
    z=df.loc[df.selected_contract_price.between(.03,.97,inclusive='both')].copy();z['cent']=np.rint(z.selected_contract_price*100).astype(int)
    g=z.groupby(['game_id','cent']).agg(p=('selected_contract_price','mean'),y=('y_selected','mean')).reset_index()
    b=g.groupby('cent').agg(market_price=('p','mean'),P=('y','mean'),games=('game_id','nunique')).reset_index(); b=b[b.P.between(.001,.999)]
    def w(P,a,d):return np.exp(-d*np.power(-np.log(np.clip(P,1e-8,1-1e-8)),a))
    def pred(P,a,d):
        wp=w(P,a,d);wq=w(1-P,a,d);return wp/(wp+wq)
    fit=least_squares(lambda q:np.sqrt(b.games.to_numpy())*(pred(b.P.to_numpy(),*np.exp(q))-b.market_price.to_numpy()),np.log([1,1]),bounds=(np.log([1e-4,1e-4]),np.log([1e4,1e4])),max_nfev=3000)
    games=pd.Index(g.game_id.unique());centers=np.arange(1,100);gi=games.get_indexer(g.game_id);ci=g.cent.to_numpy()-1
    nmat=np.zeros((len(games),99));pmat=np.zeros_like(nmat);ymat=np.zeros_like(nmat);nmat[gi,ci]=1;pmat[gi,ci]=g.p.to_numpy();ymat[gi,ci]=g.y.to_numpy()
    rng=np.random.default_rng(20261022);draws=rng.multinomial(len(games),np.full(len(games),1/len(games)),size=DRAWS);vals=[]
    for mult in draws:
        n=mult@nmat;ps=mult@pmat;ys=mult@ymat;ok=n>0
        pp=ps[ok]/n[ok];yy=ys[ok]/n[ok];ww=np.sqrt(n[ok]);keep=(yy>.001)&(yy<.999)
        if keep.sum()<3:continue
        cf=least_squares(lambda q:ww[keep]*(pred(yy[keep],*np.exp(q))-pp[keep]),fit.x,bounds=(np.log([1e-4,1e-4]),np.log([1e4,1e4])),max_nfev=100)
        vals.append(np.exp(cf.x))
    a,d=np.exp(fit.x);arr=np.asarray(vals);return {'alpha':float(a),'delta':float(d),'alpha_ci95':np.quantile(arr[:,0],[.025,.975]).tolist(),'delta_ci95':np.quantile(arr[:,1],[.025,.975]).tolist(),'bootstrap_draws':len(arr),'assumptions':'linear value, no loss aversion; loss aversion/no-trade region not identified from prices','sse':float(np.sum(fit.fun**2))},b

def main():
    meta=pd.read_parquet(META);meta=meta[(meta.season==2026)&meta.season_type.eq(2)].copy();meta['ticker']=meta.ticker.astype(str);meta=meta.set_index('ticker')
    parts=[]
    need=['game_id','ts_utc','period','clock_s_remaining','clock_running','tau_seconds','last_event_type','last_event_dPstar','clock_decay','quiet_timeout','stoppage_type','stoppage_elapsed_seconds','selected_team_is_home','ticker_yes_is_home','selected_contract_price','trade_id']
    for ticker,m in meta.iterrows():
        f=PANEL/f'{ticker}.parquet'
        if not f.exists() or str(m.result).lower() not in ('yes','no'):continue
        x=pd.read_parquet(f,columns=need);x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce');x=x.dropna(subset=['ts']).sort_values('ts',kind='stable').reset_index(drop=True)
        x['game_id']=x.game_id.astype(str);x['market_ticker']=ticker
        x['late5']=[is_final_regulation_window(p,c,5) for p,c in zip(x.period,x.clock_s_remaining)]
        x['late10']=[is_final_regulation_window(p,c,10) for p,c in zip(x.period,x.clock_s_remaining)]
        if not x.late10.any():continue
        same=x.ticker_yes_is_home.eq(x.selected_team_is_home).to_numpy(); yyes=int(str(m.result).lower()=='yes')
        x['y_selected']=np.where(same,yyes,1-yyes)
        x['origin_s']=np.rint(x.ts.astype('int64').to_numpy()/1e9-pd.to_numeric(x.tau_seconds,errors='coerce').fillna(np.nan).to_numpy(float))
        tsnum=pd.to_datetime(x.ts,utc=True).astype('int64').to_numpy()/1e9
        ix=np.searchsorted(tsnum,np.nan_to_num(x.origin_s.to_numpy(),nan=-1),side='left')-1
        x['pre_event_price']=np.where((ix>=0)&np.isfinite(x.origin_s),x.selected_contract_price.to_numpy()[np.maximum(ix,0)],np.nan)
        dp=pd.to_numeric(x.last_event_dPstar,errors='coerce').to_numpy(float)
        x['event_direction_selected']=np.sign(np.where(x.selected_team_is_home.to_numpy(),dp,-dp))
        x['tau']=pd.to_numeric(x.tau_seconds,errors='coerce')
        x['event_key']=x.game_id+'|'+ticker+'|'+pd.Series(x.origin_s,index=x.index).fillna(-1).astype(np.int64).astype(str)
        x['timeout_onset_s']=np.where(x.stoppage_type.astype(str).eq('timeout'),tsnum-pd.to_numeric(x.stoppage_elapsed_seconds,errors='coerce').to_numpy(float),np.nan)
        parts.append(x.loc[x.late10].copy())
    d=pd.concat(parts,ignore_index=True)
    d['price_bin_pre']=pd.cut(d.pre_event_price,PRICE_EDGES,right=False,include_lowest=True).astype(object)
    d.loc[np.isclose(d.pre_event_price,.97),'price_bin_pre']='[0.90,0.97]'
    d['tau_bin']=pd.cut(d.tau,TAU_EDGES,right=False,labels=TAU_NAMES)
    # Distinct event metadata and long-horizon reference, 120-300 seconds.
    em=d.groupby('event_key',sort=False).agg(game_id=('game_id','first'),event_origin=('origin_s','first'),direction=('event_direction_selected','first'),event_type=('last_event_type','first'),preprice=('pre_event_price','first'),price_bin=('price_bin_pre','first'),clock_running=('clock_running','first'),horizon_price=('selected_contract_price',lambda s:np.nan)).reset_index()
    refs=d.loc[d.tau.between(120,300,inclusive='both')].groupby('event_key').selected_contract_price.mean()
    em['horizon_price']=em.event_key.map(refs)
    # Flag an event followed by a timeout onset within the next 120 seconds.
    onsets=d.dropna(subset=['timeout_onset_s']).groupby('game_id').timeout_onset_s.apply(lambda s:np.sort(s.unique())).to_dict()
    def follow(row):
        a=onsets.get(row.game_id,np.array([]));j=np.searchsorted(a,row.event_origin,side='left');return bool(j<len(a) and 0<=a[j]-row.event_origin<=120)
    em['followed_timeout']=em.apply(follow,axis=1)
    em=em.loc[em.direction.ne(0)&em.preprice.between(.03,.97)&em.horizon_price.notna()].copy()
    obs=d.loc[d.event_key.isin(em.event_key)&d.tau.lt(120)].copy()
    obs['tau_bin']=pd.cut(obs.tau,TAU_EDGES,labels=TAU_NAMES,right=False)
    obs=obs.merge(em[['event_key','direction','horizon_price','followed_timeout','price_bin']],on='event_key',how='inner',suffixes=('','_event'))
    obs['response_gap']=obs.direction*(obs.horizon_price-obs.selected_contract_price)
    # Event-equal curve by response direction, with game bootstrap for B,kappa.
    decay={};decay_curves=[]
    def decay_fit(v,with_boot=True):
        centers=dict(zip(TAU_NAMES[:5],TAU_CENTERS[:5]))
        c=v.groupby('tau_bin',observed=True).response_gap.mean().reindex(TAU_NAMES[:5]).dropna()
        if len(c)<3:return None
        tt=np.array([centers[i] for i in c.index]); yy=c.to_numpy()
        f=least_squares(lambda q:np.exp(q[0])*np.exp(-np.exp(q[1])*tt)-yy,np.log([max(np.nanmax(yy),.005),.01]),bounds=(np.log([1e-5,1e-5]),np.log([10,10])))
        ab=np.exp(f.x);result={'B':float(ab[0]),'kappa_per_second':float(ab[1]),'n_events':int(v.event_key.nunique()),'n_games':int(v.game_id.nunique())}
        if with_boot:
            games=pd.Index(v.game_id.unique());v=v.copy();v['tcode']=pd.Categorical(v.tau_bin,categories=TAU_NAMES[:5]).codes
            gi=games.get_indexer(v.game_id);tc=v.tcode.to_numpy();valid=tc>=0
            nmat=np.zeros((len(games),5));smat=np.zeros_like(nmat);np.add.at(nmat,(gi[valid],tc[valid]),1);np.add.at(smat,(gi[valid],tc[valid]),v.response_gap.to_numpy()[valid])
            rng=np.random.default_rng(20261023);draws=rng.multinomial(len(games),np.full(len(games),1/len(games)),size=DRAWS);arr=[]
            for mult in draws:
                nn=mult@nmat;ss=mult@smat;ok=nn>0
                if ok.sum()<3:continue
                t=np.array(TAU_CENTERS[:5])[ok];y=ss[ok]/nn[ok]
                fit=least_squares(lambda q:np.exp(q[0])*np.exp(-np.exp(q[1])*t)-y,f.x,bounds=(np.log([1e-5,1e-5]),np.log([10,10])),max_nfev=100)
                arr.append(np.exp(fit.x))
            ar=np.asarray(arr);result['bootstrap_2000_game_cluster']={'B_ci95':np.quantile(ar[:,0],[.025,.975]).tolist(),'kappa_ci95':np.quantile(ar[:,1],[.025,.975]).tolist(),'draws':len(ar)}
        return result
    for label,sel in [('running_events',obs.clock_running.fillna(False).astype(bool)),('events_followed_by_timeout',obs.followed_timeout.astype(bool))]:
        z=obs.loc[sel&obs.tau_bin.isin(TAU_NAMES[:5])].copy()
        # Average within event/tau first so high-volume events do not dominate.
        e=z.groupby(['event_key','game_id','direction','price_bin','tau_bin'],observed=True).response_gap.mean().reset_index()
        curve=e.groupby(['direction','price_bin','tau_bin'],observed=True).response_gap.agg(['mean','count']).reset_index()
        fits={}
        for direction in [-1,1]:
            v=e.loc[e.direction.eq(direction)]
            if v.empty:continue
            for pbin,vb in v.groupby('price_bin',observed=True,sort=False):
                f=decay_fit(vb)
                if f:fits.setdefault(str(direction),{})[str(pbin)]=f
        decay[label]={'fits':fits,'curve':curve.to_dict(orient='records'),'tau_bins':TAU_NAMES[:5]}
        decay_curves.extend([dict(version=label,**r) for r in curve.to_dict(orient='records')])
    # Benchmark-free short-horizon drift from current trade to first trade at tau+h.
    drift=[]
    for h in [5,15,30,60]:
        pairs=[]
        for _,g in d.loc[d.tau.between(0,120)].groupby('event_key',sort=False):
            g=g.sort_values('tau');tt=g.tau.to_numpy(float);pp=g.selected_contract_price.to_numpy(float)
            if len(g)<2:continue
            idx=np.searchsorted(tt,tt+h,side='left'); ok=idx<len(g)
            cur=np.flatnonzero(ok)
            if not len(cur):continue
            z=g.iloc[cur][['game_id','event_direction_selected','last_event_type']].copy();z['tau_bucket']=pd.cut(tt[cur],TAU_EDGES,labels=TAU_NAMES);z['delta_price']=pp[idx[cur]]-pp[cur];z['horizon_seconds']=h;pairs.append(z)
        if pairs:
            q=pd.concat(pairs,ignore_index=True);q=q.loc[q.event_direction_selected.ne(0)&q.tau_bucket.notna()]
            for (dire,etype,tb),gg in q.groupby(['event_direction_selected','last_event_type','tau_bucket'],observed=True):
                out,_=boot_game_means(gg.rename(columns={'delta_price':'v'}),'v',draws=DRAWS,seed=SEED+h)
                drift.append({'horizon_seconds':h,'direction_selected':int(dire),'event_type':str(etype),'tau_bucket':str(tb),**out})
    # 5g reduced-form and CPT fits, all final-five trades and quiet-stoppage plateau.
    final5=d.loc[d.late5].copy();quiet=final5.loc[final5.quiet_timeout.fillna(False).astype(bool)].copy()
    reduced={};bins=[]
    for label,frame in [('final5_raw_curve',final5),('final5_quiet_plateau',quiet)]:
        f,b=calibration_fit(frame,label);cpt,cb=cpt_fit(frame);reduced[label]={'prelec':f,'cpt_binary':cpt,'games':int(frame.game_id.nunique()),'trades':int(len(frame))};bins.append(b)
    (OUT/'phase5_dynamics.json').write_text(json.dumps({'decay_shape_B_kappa':decay,'decay_curves':decay_curves,'drift':drift,'prelec_and_cpt':reduced},indent=2,default=str))
    pd.concat(bins,ignore_index=True).to_csv(OUT/'phase5g_calibration_bins.csv',index=False)
    print(json.dumps({'decay':decay,'drift_rows':len(drift),'prelec_cpt':reduced},indent=2,default=str))
if __name__=='__main__':main()
