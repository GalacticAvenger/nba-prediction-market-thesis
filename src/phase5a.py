"""Moshrefi replication variants with game-cluster bootstrap uncertainty."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from sklearn.isotonic import IsotonicRegression
from common import ROOT
from game_windows import is_final_regulation_window

META=ROOT/'data/interim/kalshi_market_metadata.parquet'
PANEL=ROOT/'data/interim/phase4/trade_panel'
TRADES=ROOT/'data/interim/kalshi_trades'
PBP=ROOT/'data/interim/espn_pbp/season=2026'
ASSIGN=ROOT/'data/interim/phase4/selected_team_by_game.csv'
POST=ROOT/'data/interim/phase5/post_game_trades/post_game_trades.parquet'
OUT=ROOT/'data/interim/phase5'; OUT.mkdir(parents=True,exist_ok=True)
PAPER_START=pd.Timestamp('2026-03-01T00:00:00Z'); PAPER_END=pd.Timestamp('2026-05-16T00:00:00Z')
BOUNDS=(1e-4,1e4); DRAWS=2000; RNG_SEED=5132026

def prelec(p,a,b):
    p=np.clip(np.asarray(p,float),1e-12,1-1e-12)
    return np.exp(-np.minimum(b*np.exp(np.clip(a*np.log(-np.log(p)),-700,700)),700))

def calibration(frame,bin_width=1):
    d=frame.loc[frame.price.gt(0)&frame.price.lt(1)&frame.y.notna(),['game_id','price','y']].copy()
    if d.empty: return pd.DataFrame(columns=['cent','n','p','raw_rate','iso_rate'])
    d['cent']=np.floor((d.price*100-1e-10)/bin_width).astype('int16')
    b=d.groupby('cent',as_index=False).agg(n=('y','size'),p=('price','mean'),raw_rate=('y','mean'))
    b['iso_rate']=IsotonicRegression(increasing=True,out_of_bounds='clip').fit_transform(b.p,b.raw_rate,sample_weight=b.n)
    return b

def fit_bins(b, target):
    if len(b)<3:return {'alpha':None,'beta':None,'boundary':False,'sse':None}
    p=b.p.to_numpy(float); y=b[target].to_numpy(float); w=np.sqrt(b.n.to_numpy(float))
    def resid(z): return w*(prelec(p,*np.exp(z))-y)
    f=least_squares(resid,np.log([1.5,1.2]),bounds=(np.log([BOUNDS[0]]*2),np.log([BOUNDS[1]]*2)),max_nfev=300)
    ab=np.exp(f.x)
    return {'alpha':float(ab[0]),'beta':float(ab[1]),'boundary':bool(np.any(np.isclose(np.abs(f.x),np.abs(np.log(BOUNDS[0])),atol=1e-5)) or np.any(np.isclose(f.x,np.log(BOUNDS[1]),atol=1e-5))),'sse':float(np.sum(resid(f.x)**2))}

def summarize(frame,label,draws=DRAWS,rng=None,bin_width=1):
    b=calibration(frame,bin_width); out={'trades':int(len(frame)),'games':int(frame.game_id.nunique()),'price_bins':int(len(b)),'bin_width_cents':bin_width}
    if not len(b): return out,pd.DataFrame()
    for target,name in [('raw_rate','raw'),('iso_rate','isotonic')]:
        base=fit_bins(b,target); out[name]=base
        # Cluster bootstrap by game, using game x price-cent sufficient statistics.
        stats=frame.loc[frame.price.gt(0)&frame.price.lt(1),['game_id','price','y']].copy()
        stats['cent']=np.floor((stats.price*100-1e-10)/bin_width).astype('int16')
        g=stats.groupby(['game_id','cent']).agg(n=('y','size'),wins=('y','sum'),psum=('price','sum')).reset_index()
        games=pd.Index(g.game_id.unique()); n_bins=int(100/bin_width); gi=games.get_indexer(g.game_id); ci=g.cent.to_numpy()
        counts=np.zeros((len(games),n_bins),dtype=np.float64); wins=np.zeros_like(counts); psums=np.zeros_like(counts)
        counts[gi,ci]=g.n.to_numpy(); wins[gi,ci]=g.wins.to_numpy(); psums[gi,ci]=g.psum.to_numpy()
        vals=[]; rng=rng or np.random.default_rng(RNG_SEED)
        multin=rng.multinomial(len(games),np.full(len(games),1/len(games)),size=draws)
        for mult in multin:
            nn=mult@counts; ww=mult@wins; pp=mult@psums; keep=nn>0
            zz=pd.DataFrame({'cent':np.flatnonzero(keep),'n':nn[keep],'p':pp[keep]/nn[keep],'raw_rate':ww[keep]/nn[keep]})
            zz['iso_rate']=IsotonicRegression(increasing=True,out_of_bounds='clip').fit_transform(zz.p,zz.raw_rate,sample_weight=zz.n)
            f=fit_bins(zz,target)
            if f['alpha'] is not None and np.isfinite(f['alpha']+f['beta']): vals.append([f['alpha'],f['beta']])
        arr=np.asarray(vals)
        out[name]['bootstrap']={'requested_draws':draws,'successful_draws':int(len(arr)),'cluster':'game','seed':RNG_SEED,'alpha_ci95':np.quantile(arr[:,0],[.025,.975]).tolist() if len(arr) else None,'beta_ci95':np.quantile(arr[:,1],[.025,.975]).tolist() if len(arr) else None}
    b['fit_raw']=prelec(b.p,out['raw']['alpha'],out['raw']['beta']) if out['raw']['alpha'] else np.nan
    b['fit_isotonic']=prelec(b.p,out['isotonic']['alpha'],out['isotonic']['beta']) if out['isotonic']['alpha'] else np.nan
    b['version']=label
    return out,b

def pbp_last():
    parts=[]
    for f in PBP.glob('season_type=*/*.parquet'):
        x=pd.read_parquet(f,columns=['game_id','ts_wall_utc'])
        x['ts']=pd.to_datetime(x.ts_wall_utc,utc=True,errors='coerce')
        parts.append(x.dropna(subset=['ts']))
    allp=pd.concat(parts,ignore_index=True)
    return allp.groupby(allp.game_id.astype(str)).ts.max().to_dict()

def main():
    rng=np.random.default_rng(RNG_SEED)
    meta=pd.read_parquet(META); meta=meta[(meta.season==2026)&meta.season_type.isin([2,3])].copy(); meta['game_id']=meta.game_id.astype(str)
    meta['close']=pd.to_datetime(meta.close_time,utc=True,errors='coerce',format='mixed')
    meta['result']=meta.result.astype(str).str.lower(); meta=meta.drop_duplicates('ticker').set_index('ticker',drop=False)
    last=pbp_last(); assign=pd.read_csv(ASSIGN,dtype={'game_id':str}).set_index('game_id').selected_team_is_home.to_dict()
    # Raw in-game market-coordinate trades, all season types, excluding unresolved outcomes and blocks.
    chunks=[]
    for ticker,m in meta.iterrows():
        f=TRADES/f'{ticker}.parquet'
        if not f.exists() or m.result not in ('yes','no'): continue
        x=pd.read_parquet(f)
        if x.empty: continue
        x=x.loc[~x.is_block_trade.fillna(False)].copy(); x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce',format='mixed')
        x['game_id']=x.game_id.astype(str); x['price']=pd.to_numeric(x.price,errors='coerce'); x['y']=(x.settlement_result.astype(str).str.lower()=='yes').astype('int8')
        x['market_ticker']=ticker; x['season_type']=int(m.season_type); x['result']=m.result
        chunks.append(x[['game_id','market_ticker','ts','price','y','season_type','result']])
    raw=pd.concat(chunks,ignore_index=True) if chunks else pd.DataFrame()
    # Market YES price and market YES outcome, filtered to strictly before the last ESPN play.
    raw['last_play']=raw.game_id.map(last)
    d=raw.dropna(subset=['last_play','ts']).loc[lambda x:(x.ts<x.last_play)&(x.ts>=x.last_play-pd.Timedelta(minutes=10))&x.price.gt(0)&x.price.lt(1)].copy()
    paper=d.ts.ge(PAPER_START)&d.ts.lt(PAPER_END)
    datasets={'d_paper_dates_including_playoffs':d.loc[paper].copy(),'d_full_season_including_playoffs':d.copy(),'d_full_regular_season':d.loc[d.season_type.eq(2)].copy()}
    # Version b: shared final-regulation predicate and selected-team outcome coordinate.
    bp=[]
    for ticker,m in meta.loc[meta.season_type.eq(2)].iterrows():
        f=PANEL/f'{ticker}.parquet'
        if not f.exists() or m.result not in ('yes','no'): continue
        x=pd.read_parquet(f,columns=['game_id','ts_utc','selected_contract_price','selected_team_is_home','ticker_yes_is_home','period','clock_s_remaining'])
        mask=[is_final_regulation_window(p,c,10) for p,c in zip(x.period,x.clock_s_remaining)]
        x=x.loc[mask].copy(); x['game_id']=x.game_id.astype(str); x['price']=x.selected_contract_price
        x['y']=np.where(x.ticker_yes_is_home.eq(x.selected_team_is_home),int(m.result=='yes'),int(m.result=='no')); x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce')
        bp.append(x[['game_id','ts','price','y']])
    b=pd.concat(bp,ignore_index=True); bpaper=b.ts.ge(PAPER_START)&b.ts.lt(PAPER_END)
    datasets['b_paper_dates_final10_regulation']=b.loc[bpaper].copy(); datasets['b_full_regular_season_final10_regulation']=b
    # Version a: close-time window in the saved selected-team coordinate, including post-game archive rows.
    ap=[]
    for ticker,m in meta.loc[meta.season_type.eq(2)].iterrows():
        f=PANEL/f'{ticker}.parquet'
        if not f.exists() or pd.isna(m.close) or m.result not in ('yes','no'): continue
        x=pd.read_parquet(f,columns=['game_id','ts_utc','trade_id','selected_contract_price','selected_team_is_home','ticker_yes_is_home'])
        x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce',format='mixed'); x=x.loc[(x.ts<=m.close)&(x.ts>m.close-pd.Timedelta(minutes=10))].copy()
        if len(x)==0:continue
        x['game_id']=x.game_id.astype(str); x['price']=x.selected_contract_price; x['y']=np.where(x.ticker_yes_is_home.eq(x.selected_team_is_home),int(m.result=='yes'),int(m.result=='no')); x['market_ticker']=ticker
        ap.append(x[['game_id','market_ticker','trade_id','ts','price','y']])
    a=pd.concat(ap,ignore_index=True) if ap else pd.DataFrame(columns=['game_id','ts','price','y'])
    if POST.exists():
        post=pd.read_parquet(POST); post['game_id']=post.game_id.astype(str); post['ts']=pd.to_datetime(post.ts_utc,utc=True,errors='coerce'); post['price']=pd.to_numeric(post.price,errors='coerce')
        # Saved archive is market-coordinate; transform to seed-17 coordinate from team assignment and metadata.
        mm=meta.reset_index(drop=True).set_index('ticker'); yes_team=post.market_ticker.map(mm.yes_sub_title); eg=pd.read_parquet(ROOT/'data/interim/espn_games.parquet'); eg['espn_game_id']=eg.espn_game_id.astype(str); home_abbr=post.game_id.map(eg.set_index('espn_game_id').home_abbreviation.to_dict())
        yes_home=yes_team.eq(home_abbr); selhome=post.game_id.map(assign).astype('boolean')
        post['price']=np.where(yes_home.eq(selhome),post.price,1-post.price); outcome=post.settlement_result.astype(str).str.lower()
        post['y']=np.where(yes_home.eq(selhome),outcome.eq('yes'),outcome.eq('no')).astype(int)
        post['market_ticker']=post.market_ticker.astype(str)
        a=pd.concat([a,post[['game_id','market_ticker','trade_id','ts','price','y']]],ignore_index=True).drop_duplicates(['market_ticker','trade_id'],keep='last')
    close_map=meta.close.to_dict(); a['close']=a.market_ticker.map(close_map)
    a=a.dropna(subset=['close']); a=a.loc[(a.ts.le(a.close))&(a.ts>a.close-pd.Timedelta(minutes=10))].copy()
    aok=a.dropna(subset=['ts']).copy()
    datasets['a_paper_dates_close_window_existing_basis']=aok.loc[aok.ts.ge(PAPER_START)&aok.ts.lt(PAPER_END)].copy()
    datasets['a_full_season_close_window_existing_basis']=aok.copy()
    for key in list(datasets):
        if key.startswith('a_') or key.startswith('b_'):
            datasets[key+'_5c']=datasets[key]
    summaries={}; tables={}
    for name,frame in datasets.items():
        if 'last_play' in frame: frame=frame.drop(columns='last_play')
        width=5 if name.endswith('_5c') else 1
        s,t=summarize(frame,name,rng=rng,bin_width=width); summaries[name]=s; tables[name]=t
        print(name, s.get('trades'), s.get('games'), flush=True)
    (OUT/'phase5a_bootstrap.json').write_text(json.dumps({'bootstrap_draws':DRAWS,'seed':RNG_SEED,'reference_trades':327473,'versions':summaries},indent=2))
    pd.concat(list(tables.values()),ignore_index=True).to_csv(OUT/'phase5a_bootstrap_bins.csv',index=False)
    print(json.dumps(summaries,indent=2))
if __name__=='__main__':main()
