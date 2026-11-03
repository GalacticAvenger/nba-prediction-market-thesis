"""Read-only Polymarket fill CI and common-coordinate calibration overlays."""
from __future__ import annotations
import json,sys
from pathlib import Path
import numpy as np,pandas as pd,matplotlib.pyplot as plt
from matplotlib.lines import Line2D
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from game_windows import is_final_regulation_window
from ingest_polymarket_onchain import TEAM_ALIASES
from phase5_publication import EDGES,LABELS,ROOT as ROOT2

PH2=ROOT/'data/interim/phase2';POLY_FILE=PH2/'polymarket_maker_fills_season_raw.parquet'
MAP_FILE=PH2/'polymarket_nba_2025_26_market_map.json';ASSIGN_FILE=ROOT/'data/interim/phase4/selected_team_by_game.csv'
PSTAR_FILE=ROOT/'data/interim/phase3/pstar_2025_26_every_second.parquet';PBP_DIR=ROOT/'data/interim/espn_pbp/season=2026/season_type=2'
OUT=ROOT/'data/interim/phase5';FIG=ROOT/'figures/phase5';SEED=5132026;DRAWS=2000

def norm(v):
 import re
 return re.sub(r'[^a-z0-9]','',str(v).lower())
def canonical(v):return TEAM_ALIASES.get(str(v),str(v).lower())
def token_map(market):
 gm=next(x for x in market['gamma_event']['markets'] if str(x.get('conditionId','')).lower()==str(market['condition_id']).lower())
 outcomes=json.loads(gm['outcomes']);tokens=list(map(str,json.loads(gm['clobTokenIds'])));aliases={}
 for team in market['gamma_event'].get('teams',[]):
  ab=canonical(str(team.get('abbreviation','')).upper())
  for label in (team.get('name',''),team.get('alias',''),team.get('abbreviation','')):
   if label:aliases[norm(label)]=ab
 return {aliases[norm(o)]:t for o,t in zip(outcomes,tokens) if norm(o) in aliases}
def make_pstar_grids():
 p=pd.read_parquet(PSTAR_FILE,columns=['game_id','period','clock_s_remaining','pstar']);p.game_id=p.game_id.astype(str);p.period=pd.to_numeric(p.period,errors='coerce').astype('Int8');p.clock_s_remaining=pd.to_numeric(p.clock_s_remaining,errors='coerce').astype(int);grids={}
 for (g,per),z in p.groupby(['game_id','period'],sort=False):
  z=z.sort_values('clock_s_remaining',ascending=False);grids[(g,int(per))]=(z.clock_s_remaining.to_numpy(int),z.pstar.to_numpy(float))
 return grids
def pstar_at(grids,g,per,clock):
 a=grids.get((g,int(per)))
 if a is None or not np.isfinite(clock):return np.nan
 grid,vals=a;ix=np.searchsorted(-grid,-round(float(clock)),side='left');ix=min(max(ix,0),len(vals)-1);return float(vals[ix])
def summarize_bins(df,pcol,ycol,window,venue,coord):
 q=df.loc[df[pcol].ge(.03)&df[pcol].lt(.97),['game_id',pcol,ycol]].copy()
 q['bin']=pd.cut(q[pcol],EDGES,right=False,labels=LABELS,include_lowest=True,ordered=True);q=q.dropna(subset=['bin'])
 games=pd.Index(q.game_id.unique());rows=[];rng=np.random.default_rng(SEED)
 for label in LABELS:
  z=q.loc[q.bin.eq(label)]
  if z.empty:continue
  g=z.groupby('game_id',sort=False).agg(n=(pcol,'size'),sp=(pcol,'sum'),sy=(ycol,'sum'))
  n=np.zeros(len(games));sp=np.zeros(len(games));sy=np.zeros(len(games));ix=games.get_indexer(g.index);n[ix]=g.n;sp[ix]=g.sp;sy[ix]=g.sy
  ids=rng.integers(0,len(games),size=(DRAWS,len(games)));bn=n[ids].sum(1);bp=sp[ids].sum(1);by=sy[ids].sum(1);ok=bn>0
  rows.append({'window':window,'venue':venue,'source':coord,'bin':label,'trades':int(n.sum()),'games':int((n>0).sum()),'mean_p':float(sp.sum()/n.sum()),'mean_p_ci95':[float(x) for x in np.quantile(bp[ok]/bn[ok],[.025,.975])],'observed_y':float(sy.sum()/n.sum()),'observed_y_ci95':[float(x) for x in np.quantile(by[ok]/bn[ok],[.025,.975])]})
 return rows
def main():
 assignments=pd.read_csv(ASSIGN_FILE,dtype={'game_id':str}).set_index('game_id');sched=pd.read_parquet(ROOT/'data/interim/espn_games.parquet');sched['game_id']=sched.espn_game_id.astype(str);home_abbr=sched.set_index('game_id').home_abbreviation.astype(str).to_dict()
 md=json.loads(MAP_FILE.read_text());markets={str(m['espn_game_id']):m for m in md['markets']};tokens={};winners={};home_token={};selected_token={}
 for gid,m in markets.items():
  bm=token_map(m);ht=bm.get(canonical(m['home_team']));at=bm.get(canonical(m['away_team']));wt=bm.get(canonical(m['resolved_winner_abbreviation']))
  if not all((ht,at,wt)):continue
  a=assignments.loc[gid] if gid in assignments.index else None
  if a is None:continue
  tokens[gid]=(ht,at,wt);winners[gid]=wt;home_token[gid]=ht;selected_token[gid]=ht if bool(a.selected_team_is_home) else at
 pbp=[]
 for f in PBP_DIR.glob('*.parquet'):
  z=pd.read_parquet(f,columns=['game_id','period','clock_s_remaining','ts_wall_utc']);z['game_id']=z.game_id.astype(str);z['ts']=pd.to_datetime(z.ts_wall_utc,utc=True,errors='coerce');pbp.append(z.dropna(subset=['ts']))
 pbp=pd.concat(pbp,ignore_index=True);last=pbp.groupby('game_id').ts.max().to_dict();grids=make_pstar_grids()
 cols=['espn_game_id','timestamp','asset','price','period','clock_s_remaining']
 fills=pd.read_parquet(POLY_FILE,columns=cols);fills['game_id']=fills.espn_game_id.astype(str);fills['ts']=pd.to_datetime(pd.to_numeric(fills.timestamp,errors='coerce'),unit='s',utc=True,errors='coerce');fills['asset']=fills.asset.astype(str);fills['price']=pd.to_numeric(fills.price,errors='coerce');fills['period']=pd.to_numeric(fills.period,errors='coerce');fills['clock_s_remaining']=pd.to_numeric(fills.clock_s_remaining,errors='coerce');fills=fills.dropna(subset=['ts','price','period','clock_s_remaining']);parts=[]
 for gid,ix in fills.groupby('game_id',sort=False).groups.items():
  if gid not in tokens or gid not in last:continue
  ht,at,wt=tokens[gid];z=fills.loc[ix];home=z.asset.eq(ht).to_numpy();selected=z.asset.eq(selected_token[gid]).to_numpy();valid=home|z.asset.eq(at).to_numpy();
  if not valid.any():continue
  z=z.loc[valid].copy();home=home[valid];selected=selected[valid];own_y=z.asset.eq(wt).to_numpy().astype('int8');y_sel=np.where(selected,own_y,1-own_y).astype('int8')
  ph=np.array([pstar_at(grids,gid,p,c) for p,c in zip(z.period,z.clock_s_remaining)]);pown=np.where(home,ph,1-ph);selhome=selected_token[gid]==ht;psel=ph if selhome else 1-ph
  z['p_own']=z.price.to_numpy();z['y_own']=own_y;z['ps_own']=pown;z['p_selected']=np.where(selected,z.price.to_numpy(),1-z.price.to_numpy());z['y_selected']=y_sel;z['ps_selected']=psel
  z['last']=last[gid];d=z.ts.lt(z['last'])&z.ts.ge(z['last']-pd.Timedelta(minutes=10));w5=np.array([is_final_regulation_window(p,c,5) for p,c in zip(z.period,z.clock_s_remaining)])
  if d.any():parts.append(z.loc[d,['game_id','p_own','y_own','ps_own']].rename(columns={'p_own':'p','y_own':'y','ps_own':'pstar'}).assign(window='d'))
  if w5.any():parts.append(z.loc[w5,['game_id','p_selected','y_selected','ps_selected']].rename(columns={'p_selected':'p','y_selected':'y','ps_selected':'pstar'}).assign(window='final5'))
  if len(parts)%100==0:print(f'processed {len(parts)} Polymarket partitions',flush=True)
 data=pd.concat(parts,ignore_index=True);print('usable calibration rows',len(data),'games',data.groupby('window').game_id.nunique().to_dict(),flush=True)
 # Verify the read-only fill panel reproduces documented sample counts.
 pm_summary=json.load(open(ROOT/'data/interim/phase6/polymarket_selection_summary.json'));checks={}
 for w,key in [('d','d_wall10_own_token'),('final5','gameclock_final5_selected')]:
  v=data.loc[data.window.eq(w)];checks[w]={'fills':int(len(v)),'games':int(v.game_id.nunique()),'summary_fills':pm_summary['samples'][key]['maker_fills'],'summary_games':pm_summary['samples'][key]['games']}
  if len(v)!=checks[w]['summary_fills']:raise ValueError(f'Polymarket sample mismatch {w}: {checks[w]}')
 bins=[]
 for w in ('d','final5'):
  z=data.loc[data.window.eq(w)]
  for src,pcol in [('Market','p'),('P*','pstar')]:bins.extend(summarize_bins(z,pcol,'y',w,'Polymarket',src))
 # Kalshi d rows from current publication JSON, matching market-YES.
 k=json.load(open(OUT/'phase5_publication_summary.json'));kb=[]
 for w,kw in [('d','d'),('final5','final5')]:
  for src,kcoord in [('Market','market'),('P*','Pstar')]:
   for r in k['calibration_figure_bins'][kw][kcoord]:kb.append({'window':w,'venue':'Kalshi','source':src,'bin':r['bin'],'trades':r['trades'],'games':r['games'],'mean_p':r['mean_p'],'mean_p_ci95':r['mean_p_ci95'],'observed_y':r['observed_y'],'observed_y_ci95':r['observed_y_ci95']})
 # Rebuild Kalshi final-five in the selected-team coordinate.
 meta=pd.read_parquet(ROOT/'data/interim/kalshi_market_metadata.parquet');meta=meta[(meta.season==2026)&(meta.season_type==2)&meta.result.astype(str).str.lower().isin(['yes','no'])].copy();meta['ticker']=meta.ticker.astype(str)
 krows=[]
 for m in meta.itertuples():
  f=ROOT/'data/interim/phase4/trade_panel'/f'{m.ticker}.parquet'
  if not f.exists():continue
  x=pd.read_parquet(f,columns=['game_id','period','clock_s_remaining','selected_contract_price','selected_contract_pstar','selected_team_is_home','ticker_yes_is_home'])
  mask=np.array([is_final_regulation_window(p,c,5) for p,c in zip(x.period,x.clock_s_remaining)])
  if not mask.any():continue
  same=x.selected_team_is_home.fillna(False).astype(bool).to_numpy()==x.ticker_yes_is_home.fillna(False).astype(bool).to_numpy();yyes=np.full(len(x),int(str(m.result).lower()=='yes'),dtype=int);ys=np.where(same,yyes,1-yyes)
  q=pd.DataFrame({'game_id':x.loc[mask,'game_id'].astype(str).to_numpy(),'market_p':x.loc[mask,'selected_contract_price'].to_numpy(float),'pstar_p':x.loc[mask,'selected_contract_pstar'].to_numpy(float),'y':ys[mask]})
  krows.append(q)
 kz=pd.concat(krows,ignore_index=True)
 for src,pcol in [('Market','market_p'),('P*','pstar_p')]:kb.extend(summarize_bins(kz,pcol,'y','final5','Kalshi',src))
 allrows=kb+bins
 pd.DataFrame([{'window':r['window'],'venue':r['venue'],'source':r['source'],'bin':r['bin'],'trades':r['trades'],'games':r['games'],'mean_p':r['mean_p'],'mean_p_ci95_low':r['mean_p_ci95'][0],'mean_p_ci95_high':r['mean_p_ci95'][1],'observed_y':r['observed_y'],'observed_y_ci95_low':r['observed_y_ci95'][0],'observed_y_ci95_high':r['observed_y_ci95'][1]} for r in allrows]).to_csv(OUT/'phase5_calibration_common_coordinates.csv',index=False)
 # Render with game-clustered bands for all four series in each panel.
 colors={('Kalshi','Market'):'#245a8d',('Kalshi','P*'):'#d47a20',('Polymarket','Market'):'#6a3d9a',('Polymarket','P*'):'#16806a'};markers={'Kalshi':'o','Polymarket':'D'}
 fig,axs=plt.subplots(1,2,figsize=(8.2,3.7),sharex=True,sharey=True)
 for ax,w,title in zip(axs,['d','final5'],['(d) Last 10 wall minutes','Final 5 regulation minutes']):
  for v in ('Kalshi','Polymarket'):
   for s in ('Market','P*'):
    rr=[r for r in allrows if r['window']==w and r['venue']==v and r['source']==s]
    rr=sorted(rr,key=lambda r:r['mean_p']);c=colors[(v,s)];x=np.array([r['mean_p'] for r in rr]);y=np.array([r['observed_y'] for r in rr]);lo=np.array([r['observed_y_ci95'][0] for r in rr]);hi=np.array([r['observed_y_ci95'][1] for r in rr]);ls='-' if v=='Kalshi' else '--'
    ax.plot(x,y,color=c,marker=markers[v],ls=ls,lw=1.3,ms=3.5,label=f'{v} {s}');ax.fill_between(x,lo,hi,color=c,alpha=.12,lw=0)
  ax.plot([.03,.97],[.03,.97],color='#555',ls=':',lw=1,label='45°');ax.set(title=title,xlim=(.03,.97),ylim=(.03,.97),xlabel='Mean predicted probability');ax.set_xticks([.05,.2,.35,.5,.65,.8,.9,.97]);ax.set_yticks([.05,.2,.35,.5,.65,.8,.9,.97])
 axs[0].set_ylabel('Observed win frequency');h,l=axs[1].get_legend_handles_labels();fig.legend(h,l,frameon=False,loc='lower center',ncol=5,bbox_to_anchor=(.5,-.05),fontsize=7);fig.tight_layout(rect=[0,.08,1,1])
 for ext in ('pdf','png'):fig.savefig(FIG/f'calibration_market_vs_pstar.{ext}',bbox_inches='tight')
 plt.close(fig)
 (OUT/'phase5_calibration_common_coordinates_validation.json').write_text(json.dumps({'polymarket_source_file':str(POLY_FILE.relative_to(ROOT)),'source_summary_read_only':True,'sample_count_checks':checks,'bin_cluster':'game','draws':DRAWS,'seed':SEED,'coordinates':{'d':'Polymarket own token/outcome; Kalshi market YES/outcome','final5':'seed-17 selected-team coordinate for both venues'},'polymarket_bin_ci_available':True},indent=2))
 print(json.dumps(checks,indent=2))
if __name__=='__main__':main()
