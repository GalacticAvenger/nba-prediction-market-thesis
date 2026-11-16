"""Additional thesis estimands requested 2026-11-10.

Uses A = p - Y and 2,000 game-cluster bootstrap draws throughout. Reads source
data and prior audit output; does not modify any draft. Item 6 is deliberately
not simulated: this file records results for items 1-5 only.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from phase5_selection_formula import build_phase5_frames
from phase5a import META, PANEL

DRAWS = 2000
SEED = 20261110
OUT = ROOT / 'data/interim/phase5/additional_estimands_2026_11_10.json'

def _arr_summary(z: pd.DataFrame, seed: int, *, estimate_equal: bool = True):
    """Pooled/equal A and cluster bootstrap percentile CIs, all in pp."""
    g = z.groupby('game_id', sort=True).A.agg(['size','sum','mean'])
    n = g['size'].to_numpy(float); sums = g['sum'].to_numpy(float); means = g['mean'].to_numpy(float)
    if not len(g): return {'trades': int(len(z)), 'games': 0}
    ix = np.random.default_rng(seed).integers(0, len(g), size=(DRAWS, len(g)))
    pooled_draws = sums[ix].sum(1) / n[ix].sum(1)
    equal_draws = means[ix].mean(1)
    out = {'trades': int(len(z)), 'games': int(len(g)),
           'pooled_A_pp': float(100*sums.sum()/n.sum()),
           'pooled_CI95_pp': [float(x) for x in 100*np.quantile(pooled_draws,[.025,.975])],
           'equal_game_A_pp': float(100*means.mean()),
           'equal_game_CI95_pp': [float(x) for x in 100*np.quantile(equal_draws,[.025,.975])],
           'draws': DRAWS, 'seed': seed, 'bootstrap_unit': 'game'}
    return out

def _equal_pooled_diff(z: pd.DataFrame, seed: int):
    g=z.groupby('game_id',sort=True).A.agg(['size','sum','mean'])
    n=g['size'].to_numpy(float); sm=g['sum'].to_numpy(float); mn=g['mean'].to_numpy(float)
    ix=np.random.default_rng(seed).integers(0,len(g),size=(DRAWS,len(g)))
    d=mn[ix].mean(1)-sm[ix].sum(1)/n[ix].sum(1)
    return {'trades':int(len(z)), 'games':int(len(g)),
            'equal_game_minus_pooled_A_pp':float(100*(mn.mean()-sm.sum()/n.sum())),
            'CI95_pp':[float(x) for x in 100*np.quantile(d,[.025,.975])],
            'draws':DRAWS,'seed':seed,'bootstrap_unit':'game; both estimates recomputed per draw'}

def _paired_window_pooled(a: pd.DataFrame, b: pd.DataFrame, seed: int):
    """Paired-game resampling, pooled estimates for each window and their B-A contrast."""
    ga=a.groupby('game_id').A.agg(['size','sum'])
    gb=b.groupby('game_id').A.agg(['size','sum'])
    ids=ga.index.intersection(gb.index).sort_values()
    ga=ga.loc[ids]; gb=gb.loc[ids]
    na=ga['size'].to_numpy(float); sa=ga['sum'].to_numpy(float)
    nb=gb['size'].to_numpy(float); sb=gb['sum'].to_numpy(float)
    ix=np.random.default_rng(seed).integers(0,len(ids),size=(DRAWS,len(ids)))
    aa=sa.sum()/na.sum(); bb=sb.sum()/nb.sum()
    ad=sa[ix].sum(1)/na[ix].sum(1); bd=sb[ix].sum(1)/nb[ix].sum(1)
    dd=bd-ad
    return {'games':int(len(ids)), 'window_A':{'trades':int(na.sum()),'pooled_A_pp':float(100*aa),'CI95_pp':[float(x) for x in 100*np.quantile(ad,[.025,.975])]},
            'window_B':{'trades':int(nb.sum()),'pooled_A_pp':float(100*bb),'CI95_pp':[float(x) for x in 100*np.quantile(bd,[.025,.975])]},
            'B_minus_A_pp':float(100*(bb-aa)),'difference_CI95_pp':[float(x) for x in 100*np.quantile(dd,[.025,.975])],
            'draws':DRAWS,'seed':seed,'bootstrap_unit':'paired game; pooled means recomputed per draw'}

def load_full_game():
    """All settled regular-season NBA team-market trade rows, folded to cheaper side."""
    meta=pd.read_parquet(META)
    meta=meta.loc[(meta.season==2026)&meta.season_type.eq(2)].copy()
    meta['ticker']=meta.ticker.astype(str); meta['result']=meta.result.astype(str).str.lower()
    meta=meta.loc[meta.result.isin(['yes','no'])]
    parts=[]
    for m in meta.itertuples(index=False):
        f=PANEL/f'{m.ticker}.parquet'
        if not f.exists(): continue
        x=pd.read_parquet(f,columns=['game_id','ts_utc','selected_contract_price','selected_team_is_home','ticker_yes_is_home'])
        if x.empty: continue
        x['game_id']=x.game_id.astype(str); x['ts']=pd.to_datetime(x.ts_utc,utc=True,errors='coerce')
        px=pd.to_numeric(x.selected_contract_price,errors='coerce').to_numpy(float)
        same=x.selected_team_is_home.fillna(False).astype(bool).to_numpy()==x.ticker_yes_is_home.fillna(False).astype(bool).to_numpy()
        yyes=int(m.result=='yes'); ys=np.where(same,yyes,1-yyes)
        lp=np.minimum(px,1-px); ly=np.where(px<=.5,ys,1-ys)
        ok=np.isfinite(lp)&(lp>=.05)&(lp<=.20)
        if ok.any(): parts.append(pd.DataFrame({'game_id':x.game_id.to_numpy()[ok],'A':lp[ok]-ly[ok]}))
    return pd.concat(parts,ignore_index=True)

def main():
    out={'convention':'A = p - Y','units':'percentage points unless stated','bootstrap':{'draws':DRAWS,'unit':'game','interval':'percentile 95%','seed':SEED},'draft_modified':False}
    # NBA core samples.
    print('Building NBA P* frame…',flush=True)
    _,base,_=build_phase5_frames()
    base=base.loc[base.price.between(.05,.20,inclusive='both')].copy()
    base['A']=base.price-base.y
    base['support']=base.price.between(.03,.97,inclusive='both')&base.pstar.between(.03,.97,inclusive='both')
    f5p=base.loc[base.support & base.period.eq(4) & base.clock_s_remaining.le(300)].copy()
    # Include the source's authoritative final-five predicate for any game-clock edge cases.
    f5p=base.loc[base.support & np.array([int(p)==4 and float(c)<=300 for p,c in zip(base.period,base.clock_s_remaining)])].copy()
    retro=base.loc[base.support & base.is_d.astype(bool)].copy()
    late=pd.read_parquet(ROOT/'data/interim/phase5/phase5_late_trades.parquet')
    late=late.loc[late.late5 & late.longshot_price.between(.05,.20,inclusive='both')].copy()
    late['A']=late.longshot_price-late.longshot_y
    quiet=pd.read_parquet(ROOT/'data/interim/phase5/phase5_primary_trades.parquet')
    quiet['A']=quiet.longshot_price-quiet.longshot_y
    quiet=quiet.loc[quiet.in_primary_band.fillna(False)].copy()

    # 1. Paired pooled-window contrast, including OT strata.
    out['1_paired_pooled_window_contrast']={}
    for label, mask in [('all_557_paired_games',None),('506_non_overtime',False),('51_overtime',True)]:
        if mask is None:
            ids=set(retro.game_id.unique()) & set(f5p.game_id.unique())
        else:
            ot_map=base.groupby('game_id').is_ot_game.max()
            allowed=set(ot_map.index[ot_map.eq(mask)])
            ids=(set(retro.game_id.unique()) & set(f5p.game_id.unique())) & allowed
        out['1_paired_pooled_window_contrast'][label]=_paired_window_pooled(
            retro.loc[retro.game_id.isin(ids)],f5p.loc[f5p.game_id.isin(ids)],SEED+1+(0 if mask is None else int(mask)))

    # 2. Equal-game estimate minus pooled estimate under joint game resampling.
    full=load_full_game()
    out['2_equal_game_minus_pooled']={
        'full_game_5_20c':_equal_pooled_diff(full,SEED+20),
        'final5_Pstar_support_market_yes_5_20c':_equal_pooled_diff(f5p,SEED+21),
        'final5_no_Pstar_folded_longshot_5_20c':_equal_pooled_diff(late,SEED+22),
        'quiet_stoppage_primary_5_20c':_equal_pooled_diff(quiet,SEED+23)}

    # 3. Fixed regulation-clock minute marks. Locate each mark's first ESPN
    # play-by-play timestamp at/after the clock reaches it, then choose the first
    # eligible trade in the next 60 wall-clock seconds, also requiring the trade
    # record itself to show that the mark has been reached.
    pbp_parts=[]
    for f in (ROOT/'data/interim/espn_pbp/season=2026/season_type=2').glob('*.parquet'):
        q=pd.read_parquet(f,columns=['game_id','period','clock_s_remaining','ts_wall_utc'])
        q['game_id']=q.game_id.astype(str); q['ts']=pd.to_datetime(q.ts_wall_utc,utc=True,errors='coerce')
        q['clock_s_remaining']=pd.to_numeric(q.clock_s_remaining,errors='coerce')
        pbp_parts.append(q.dropna(subset=['ts','clock_s_remaining']))
    pbp=pd.concat(pbp_parts,ignore_index=True)
    out['3_fixed_game_clock_sampling']={}
    for label,z,pricecol,ycol,requires_support in [
        ('with_Pstar',base,'price','y',True),('without_Pstar',late,'longshot_price','longshot_y',False)]:
        d=z.copy(); d['game_id']=d.game_id.astype(str); d['A']=d[pricecol]-d[ycol]
        if requires_support: d=d.loc[d.support]
        d=d.loc[d.period.eq(4)]
        marks=[]
        for mark in [300,240,180,120,60]:
            crossings=(pbp.loc[pbp.period.eq(4)&pbp.clock_s_remaining.le(mark)]
                       .sort_values(['game_id','ts'],kind='stable').drop_duplicates('game_id'))
            start=crossings.set_index('game_id').ts
            q=d.loc[d.game_id.isin(start.index)&d.clock_s_remaining.le(mark)].copy()
            q['mark_ts']=q.game_id.map(start)
            q=q.loc[q.ts.ge(q.mark_ts)&q.ts.lt(q.mark_ts+pd.Timedelta(seconds=60))]
            q=q.sort_values(['game_id','ts'],kind='stable').drop_duplicates('game_id')
            marks.append({'mark_remaining_seconds':mark,'sample':q})
        combined=pd.concat([m['sample'].assign(mark=m['mark_remaining_seconds']) for m in marks],ignore_index=True)
        out['3_fixed_game_clock_sampling'][label]={
            'overall_all_sampled_trades':_arr_summary(combined,SEED+(30 if requires_support else 31)),
            'overall_estimator':'pooled A over selected trade-mark observations, each counted once; game-cluster bootstrap resamples games and retains all selected marks within each sampled game',
            'sampling_rule':'for each mark, use the first ESPN play-by-play timestamp at/after regulation clock reaches the mark; select the first eligible trade at/after that timestamp and within the following 60 wall-clock seconds, requiring its ESPN-assigned game clock to be at or below the mark; each game can contribute once per mark',
            'per_mark':{str(m['mark_remaining_seconds']):_arr_summary(m['sample'],SEED+40+m['mark_remaining_seconds']+(0 if requires_support else 1000)) for m in marks}}

    # 4. NHL windows.
    nhl=pd.read_parquet(ROOT/'data/interim/nhl_2025_26_window_analysis/trade_windows.parquet')
    nhl['game_id']=nhl.game_id.astype(str); nhl['A']=-pd.to_numeric(nhl.gap_y_minus_p,errors='coerce')
    nhl['ts_sort']=pd.to_numeric(nhl.ts,errors='coerce')
    n5=nhl.loc[nhl.clock_final5_reg.astype(bool)&nhl.longshot_price.between(.05,.20,inclusive='both')].copy()
    nr=nhl.loc[nhl.retrospective.astype(bool)&nhl.longshot_price.between(.05,.20,inclusive='both')].copy()
    counts=n5.groupby('game_id').agg(n=('A','size'),has_winning_eligible_contract=('longshot_y','max'))
    out['4a_NHL_final5_trade_counts_by_game_outcome']={
        ('contains_winning_eligible_contract' if bool(k) else 'no_winning_eligible_contract'):{'games':int(len(v)),'eligible_trades':int(v.n.sum()),'mean_trades_per_game':float(v.n.mean()),'median_trades_per_game':float(v.n.median())}
        for k,v in counts.groupby('has_winning_eligible_contract')}
    out['4a_NHL_final5_trade_counts_by_game_outcome']['overall']={'trades':int(len(n5)),'games':int(len(counts))}
    paired=set(n5.game_id.unique())&set(nr.game_id.unique())
    out['4b_NHL_461_paired_games_levels']={'paired_games':len(paired),'retrospective':_arr_summary(nr.loc[nr.game_id.isin(paired)],SEED+50),'final5_regulation':_arr_summary(n5.loc[n5.game_id.isin(paired)],SEED+51)}
    def first_by_game(z,seed):
        q=z.sort_values(['game_id','ts_sort'],kind='stable').drop_duplicates('game_id').copy()
        return {'eligible_trades':int(len(z)),'first_trade_per_game':_arr_summary(q,seed)}
    out['4c_NHL_first_trade_per_game']={'retrospective':first_by_game(nr,SEED+52),'final5_regulation':first_by_game(n5,SEED+53)}

    # 5. NBA taker side; source has taker outcome side folded into longshot buy/sell.
    def by_taker(z,seed):
        sides={}
        for buy,label in [(True,'bought_longshot'),(False,'sold_longshot')]:
            q=z.loc[z.buy_longshot.astype(bool).eq(buy)].copy()
            sides[label]=_arr_summary(q,seed+(0 if buy else 1))
        return {'source_field':'buy_longshot; derived from taker outcome side in Kalshi trade records','sides':sides}
    late_full=pd.read_parquet(ROOT/'data/interim/phase5/phase5_late_trades.parquet')
    late5=late_full.loc[late_full.late5 & late_full.longshot_price.between(.05,.20,inclusive='both')].copy(); late5['A']=late5.longshot_price-late5.longshot_y
    quiet0=pd.read_parquet(ROOT/'data/interim/phase5/phase5_primary_trades.parquet')
    quiet0=quiet0.loc[quiet0.in_primary_band.fillna(False)].copy(); quiet0['A']=quiet0.longshot_price-quiet0.longshot_y
    out['5_taker_side_split']={'Kalshi_NBA_taker_side_available':True,'final5_pooled_by_taker_side':by_taker(late5,SEED+60),'quiet_stoppage_pooled_by_taker_side':by_taker(quiet0,SEED+62),
       'NHL_raw_Kalshi_trade_records_contain_taker_outcome_side':True,
       'NHL_window_parquet_does_not_retain_taker_side':True}

    prior=ROOT/'data/interim/phase5/fresh_results_audit_2026_11_10.json'
    if prior.exists():
        old=json.loads(prior.read_text())
        has_n = {f'N{i}': any(k.startswith(f'N{i}_') for k in old) or (i == 5 and any(k.startswith('N4_N5') for k in old)) for i in range(1,10)}
        has_prelec=any('prelec' in k.lower() for k in old)
        out['prior_fresh_audit_reference']={'path':str(prior.relative_to(ROOT)),'included_keys':sorted(old.keys()),'N1_to_N9_present':has_n,'Prelec_present':has_prelec}
        out['prior_fresh_audit_results']=old
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print(f'Wrote {OUT}',flush=True)

if __name__=='__main__': main()
