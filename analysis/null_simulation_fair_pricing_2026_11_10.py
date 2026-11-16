"""Fair-pricing null simulation, 1,000 seasons x 1,230 games; no draft edits.
Prices are exact probabilities under each simulated random-walk game, computed
by backward induction. Only estimator sufficient statistics are retained."""
from __future__ import annotations
import json, math, sys, glob
from pathlib import Path
import numpy as np
from numba import njit

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/interim/phase5/fair_pricing_null_simulation_2026_11_10.json"
R=1000
G=1230
SEED=20261110
NAMES=["full_pooled","full_equal_game","full_first_trade","full_fixed_clock",
       "final5_pooled","final5_equal_game","final5_first_trade","final5_fixed_clock",
       "retro10m_pooled","retro10m_equal_game"]
COUNTS=["full_trade_rows","full_games_with_trades","full_first_entries","full_fixed_observations",
        "final5_trade_rows","final5_games_with_trades","final5_first_entries","final5_fixed_observations",
        "retro10m_trade_rows","retro10m_games_with_trades"]

@njit
def dp_make(n, bound, vals, probs):
    dp=np.empty((n+1,2*bound+1))
    for j in range(2*bound+1):
        d=j-bound
        dp[0,j]=1. if d>0 else (0. if d<0 else .5)
    for r in range(1,n+1):
        for j in range(2*bound+1):
            s=0.
            for k in range(len(vals)):
                jj=j+vals[k]
                v=0. if jj<0 else (1. if jj>=2*bound+1 else dp[r-1,jj])
                s+=probs[k]*v
            dp[r,j]=s
    return dp

@njit
def draw_step(cdf, vals):
    u=np.random.random()
    for k in range(len(cdf)):
        if u<cdf[k]: return vals[k]
    return vals[-1]

@njit
def season(seed,nreg,mins,otsteps,bound,vals,probs,cdf,dpreg,dpot,
           baseextra,closeextra,closediff,rate0,boost,pscale,clockboost,otbreak):
    np.random.seed(seed)
    # estimators, sample counts, OT and final-five trade-count checks
    e=np.full(10,np.nan); obs=np.zeros(10); otc=0
    maxn=nreg+otsteps*1000
    qv=np.empty(maxn); cntv=np.empty(maxn,dtype=np.int64); waitv=np.empty(maxn)
    durv=np.empty(maxn); startv=np.empty(maxn); side1=np.empty(maxn,dtype=np.bool_)
    isreg=np.empty(maxn,dtype=np.bool_)
    fN=fS=fEq=fGames=fFirst=fFirstN=fFixS=fFixN=0.
    aN=aS=aEq=aGames=aFirst=aFirstN=aFixS=aFixN=0.
    rN=rS=rEq=rGames=0.
    nwin=nnowin=wintrades=nowintrades=0.
    for game in range(G):
        d=0; ns=0; wall=0.
        for t in range(nreg):
            rem=nreg-t; p1=dpreg[rem,d+bound]; q=p1 if p1<=.5 else 1.-p1
            lateclose=(rem<=10 and abs(d)<=closediff)
            dur=30.+np.random.exponential(baseextra+(closeextra if lateclose else 0.))
            prog=1.-rem/nreg
            lam=rate0*(1.+boost*math.exp(-abs(p1-.5)/pscale))*(1.+clockboost*prog)
            wait=dur+1.; count=0
            if .05<=q<=.20:
                wait=np.random.exponential(1./lam)
                if wait<dur: count=1+np.random.poisson(lam*(dur-wait))
            qv[ns]=q; cntv[ns]=count; waitv[ns]=wait; durv[ns]=dur; startv[ns]=wall
            side1[ns]=(p1<=.5); isreg[ns]=True
            ns+=1; wall+=dur; d+=draw_step(cdf,vals)
        if d==0:
            otc+=1
            while d==0:
                wall+=otbreak
                for t in range(otsteps):
                    rem=otsteps-t; p1=dpot[rem,d+bound]; q=p1 if p1<=.5 else 1.-p1
                    lateclose=(rem<=max(1,otsteps//3) and abs(d)<=closediff)
                    dur=30.+np.random.exponential(baseextra+(closeextra if lateclose else 0.))
                    lam=rate0*(1.+boost*math.exp(-abs(p1-.5)/pscale))*(1.+clockboost*(1.-rem/otsteps))
                    wait=dur+1.; count=0
                    if .05<=q<=.20:
                        wait=np.random.exponential(1./lam)
                        if wait<dur: count=1+np.random.poisson(lam*(dur-wait))
                    qv[ns]=q; cntv[ns]=count; waitv[ns]=wait; durv[ns]=dur; startv[ns]=wall
                    side1[ns]=(p1<=.5); isreg[ns]=False
                    ns+=1; wall+=dur; d+=draw_step(cdf,vals)
        end=wall
        fn=fs=an=ass=rn=rs=0.; fi=ai=-1; fwin=False
        for j in range(ns):
            n=cntv[j]
            if n>0:
                y=1 if ((side1[j] and d>0) or ((not side1[j]) and d<0)) else 0
                a=qv[j]-y; an+=n; ass+=n*a
                if ai<0: ai=j
                if isreg[j] and j>=nreg-10:
                    fn+=n; fs+=n*a
                    if fi<0: fi=j
                    if y==1: fwin=True
        # Accumulate full and final-five estimates.
        aN+=an; aS+=ass
        if an>0.: aEq+=ass/an; aGames+=1.
        if ai>=0:
            y=1 if ((side1[ai] and d>0) or ((not side1[ai]) and d<0)) else 0
            aFirst+=qv[ai]-y; aFirstN+=1.
        fN+=fn; fS+=fs
        if fn>0.:
            fEq+=fs/fn; fGames+=1.
            if fwin: wintrades+=fn; nwin+=1.
            else: nowintrades+=fn; nnowin+=1.
        if fi>=0:
            y=1 if ((side1[fi] and d>0) or ((not side1[fi]) and d<0)) else 0
            fFirst+=qv[fi]-y; fFirstN+=1.
        # Recompute retrospective row counts per state, conditionally thinning once.
        for j in range(ns):
            n=cntv[j]
            if n<=0: continue
            overlap=max(0.,min(startv[j]+durv[j],end)-max(startv[j],end-600.))
            if overlap<=0.: continue
            y=1 if ((side1[j] and d>0) or ((not side1[j]) and d<0)) else 0
            a=qv[j]-y; prob=overlap/durv[j]
            picked=n if prob>.999999999 else np.random.binomial(n,prob)
            rn+=picked; rs+=picked*a
        rN+=rn; rS+=rs
        if rn>0.: rEq+=rs/rn; rGames+=1.
        # Fixed sampling at every whole clock minute, first eligible arrival
        # within 60 wall-clock seconds. Marks align with 30-second steps.
        for mark in range(mins,0,-1):
            first=(mins-mark)*2
            deadline=startv[first]+60.
            for j in range(first,ns):
                if startv[j]>=deadline: break
                if qv[j]<.05 or qv[j]>.20: continue
                if startv[j]+waitv[j] < min(startv[j]+durv[j],deadline):
                    y=1 if ((side1[j] and d>0) or ((not side1[j]) and d<0)) else 0
                    a=qv[j]-y; aFixS+=a; aFixN+=1.
                    if mark<=5 and j<nreg: fFixS+=a; fFixN+=1.
                    break
                if startv[j]+durv[j]>=deadline: break
    e[0]=aS/aN if aN else np.nan; e[1]=aEq/aGames if aGames else np.nan
    e[2]=aFirst/aFirstN if aFirstN else np.nan; e[3]=aFixS/aFixN if aFixN else np.nan
    e[4]=fS/fN if fN else np.nan; e[5]=fEq/fGames if fGames else np.nan
    e[6]=fFirst/fFirstN if fFirstN else np.nan; e[7]=fFixS/fFixN if fFixN else np.nan
    e[8]=rS/rN if rN else np.nan; e[9]=rEq/rGames if rGames else np.nan
    obs[:]=np.array([aN,aGames,aFirstN,aFixN,fN,fGames,fFirstN,fFixN,rN,rGames])
    ratio=(wintrades/nwin)/(nowintrades/nnowin) if nwin and nnowin else np.nan
    check=np.array([otc/G,ratio,wintrades/nwin if nwin else np.nan,nowintrades/nnowin if nnowin else np.nan])
    return e,obs,check

def bootless_summary(mat,names):
    out={}
    for j,name in enumerate(names):
        x=mat[:,j]; x=x[np.isfinite(x)]
        out[name]={'mean_A_pp':float(x.mean()*100),'MCSE_pp':float(x.std(ddof=1)/math.sqrt(len(x))*100),'valid_seasons':int(len(x))}
    return out

def count_summary(mat):
    return {n:{'mean_per_season':float(mat[:,i].mean()),'MCSE':float(mat[:,i].std(ddof=1)/math.sqrt(len(mat)))} for i,n in enumerate(COUNTS)}

def run(label,regmins,increment_values,increment_probs,extras,close_diff,otbreak,seed,base_trade_rate):
    vals=np.asarray(increment_values,np.int64); probs=np.asarray(increment_probs,np.float64)
    cdf=np.cumsum(probs); cdf[-1]=1.
    nreg=regmins*2; otsteps=10; bound=6*nreg+3*otsteps+20
    dpreg=dp_make(nreg,bound,vals,probs); dpot=dp_make(otsteps,bound,vals,probs)
    em=np.empty((R,10)); om=np.empty((R,10)); cm=np.empty((R,4))
    for r in range(R):
        e,o,c=season(seed+r,nreg,regmins,otsteps,bound,vals,probs,cdf,dpreg,dpot,
            extras[0],extras[1],close_diff,base_trade_rate,3.,.15,.5,otbreak)
        em[r]=e; om[r]=o; cm[r]=c
        if (r+1)%100==0: print(f"{label}: {r+1}/{R} seasons",flush=True)
    def check(col):
        x=cm[:,col]; x=x[np.isfinite(x)]
        return {'mean':float(x.mean()),'MCSE':float(x.std(ddof=1)/math.sqrt(len(x)))}
    ratio=cm[:,1]; ratio=ratio[np.isfinite(ratio)]
    result={'estimators':bootless_summary(em,NAMES),'mean_sample_sizes':count_summary(om),
      'checks':{'overtime_share':check(0),'final5_trade_count_ratio_winning_vs_no_winning_longshot':
        {'mean':float(ratio.mean()),'MCSE':float(ratio.std(ddof=1)/math.sqrt(len(ratio))),
         'mean_trades_per_game_with_winning_longshot':float(cm[:,2].mean()),
         'mean_trades_per_game_without_winning_longshot':float(cm[:,3].mean())},
        'fixed_time_fairness_z':None if em[:,7].std(ddof=1)==0 else float(em[:,7].mean()/(em[:,7].std(ddof=1)/math.sqrt(R)))},
      'synthetic_seasons':R,'games_per_season':G,'seed':seed}
    return result

def real_comparators():
    sys.path.insert(0,str(ROOT/"src"))
    import pandas as pd
    from phase5a import META
    meta=pd.read_parquet(META)
    meta=meta.loc[(meta.season==2026)&meta.season_type.eq(2)&meta.result.astype(str).str.lower().isin(["yes","no"])]
    ids=set(meta.game_id.astype(str)); parts=[]
    for f in (ROOT/"data/interim/espn_pbp/season=2026/season_type=2").glob("*.parquet"):
        parts.append(pd.read_parquet(f,columns=["game_id","period"]))
    p=pd.concat(parts).groupby("game_id").period.max(); p=p[p.index.astype(str).isin(ids)]
    nba_ot=int(p.gt(4).sum()); nba_n=int(len(p))
    x=pd.read_parquet(ROOT/"data/interim/phase5/phase5_late_trades.parquet",columns=["game_id","late5","longshot_price","longshot_y"])
    x=x.loc[x.late5&x.longshot_price.between(.05,.20,inclusive="both")]
    g=x.groupby("game_id").agg(n=("longshot_y","size"),win=("longshot_y","max"))
    aw=g.loc[g.win.eq(1),"n"]; an=g.loc[g.win.eq(0),"n"]
    nhl=pd.read_parquet(ROOT/"data/interim/nhl_2025_26_window_analysis/trade_windows.parquet",columns=["game_id","clock_final5_reg","longshot_price","longshot_y"])
    nx=nhl.loc[nhl.clock_final5_reg&nhl.longshot_price.between(.05,.20,inclusive="both")]
    ng=nx.groupby("game_id").agg(n=("longshot_y","size"),win=("longshot_y","max"))
    nw=ng.loc[ng.win.eq(1),"n"]; nn=ng.loc[ng.win.eq(0),"n"]
    rows=[]
    for f in glob.glob(str(ROOT/"data/raw/nhl_2025_26/espn/summary_*.json")):
        try:
            z=json.loads(Path(f).read_text()); gid=str(z.get("header",{}).get("id",""))
            periods=[int((v.get("period") or {}).get("number",0)) for v in z.get("plays",[]) if isinstance(v.get("period"),dict)]
            if gid and periods: rows.append((gid,max(periods)))
        except Exception: pass
    s=pd.DataFrame(rows,columns=["game_id","max_period"]).drop_duplicates("game_id")
    s=s[s.game_id.isin(set(nhl.game_id.astype(str)))]
    return {'NBA':{'overtime_games':nba_ot,'games':nba_n,'overtime_share':nba_ot/nba_n,
        'final5_mean_trades_with_winning_longshot':float(aw.mean()),'final5_mean_trades_without_winning_longshot':float(an.mean()),
        'final5_trade_count_ratio':float(aw.mean()/an.mean()),'games_with_winning':int(len(aw)),'games_without_winning':int(len(an))},
      'NHL_variant':{'overtime_games':int(s.max_period.gt(3).sum()),'games_with_ESPN_summary':int(len(s)),
        'overtime_share':float(s.max_period.gt(3).mean()),
        'final5_mean_trades_with_winning_longshot':float(nw.mean()),'final5_mean_trades_without_winning_longshot':float(nn.mean()),
        'final5_trade_count_ratio':float(nw.mean()/nn.mean()),'games_with_winning':int(len(nw)),'games_without_winning':int(len(nn))}}

def main():
    out={'design':{'A':'p-Y','seasons':R,'games_per_season':G,'seed':SEED,
      'uncertainty':'Monte Carlo SE across synthetic-season estimates; no within-season bootstrap',
      'windows':{'final5':'last 10 possession steps of regulation (5 game-clock minutes)','retro10m':'last 600 simulated wall-clock seconds before game end',
        'fixed_clock':'one sample at each whole remaining game-clock minute; first eligible trade in next 60 wall-clock seconds; full game samples all regulation marks, final5 samples 5:00 through 1:00; pooled over sampled trades'},
      'longshot':'q=min(P,1-P), inclusive 0.05 to 0.20; no P* support restriction',
      'price_fairness':'P is exact dynamic-programming conditional win probability under the simulator; no fitted prices or P*',
      'arrival':'Poisson; sport-specific base rate * [1+3 exp(-abs(P-0.5)/0.15)] * [1+0.5*elapsed_fraction]; depends only on current probability and clock, highest near a 50-50 state',
      'OT':'tie at regulation enters 10-possession (5 game-clock-minute) period; repeat if tied; tie boundary has continuation value 0.5 under symmetric increments',
      'within_season_bootstrap':False},
      'parameters':{'NBA':{'regulation_minutes':48,'possessions':96,'game_clock_seconds_per_possession':30,
        'score_difference_increment_probabilities':{'-3':.04,'-2':.12,'-1':.22,'0':.24,'+1':.22,'+2':.12,'+3':.04},
        'regulation_increment_SD_points':math.sqrt(2.12*96),'overtime_possessions':10,'OT_break_wall_seconds':120,
        'base_stoppage_exponential_mean_seconds':4,'extra_mean_seconds_when_final5_and_margin_abs_le_6':25,
        'trade_rate_base_per_second':7.5,'close_trade_multiplier_at_even_price':4},
        'hockey_rare_scoring_variant':{'regulation_minutes':60,'possessions':120,'game_clock_seconds_per_possession':30,
        'score_difference_increment_probabilities':{'-1':.025,'0':.95,'+1':.025},
        'expected_goals_total_per_regulation_game':6,'overtime_possessions':10,'OT_break_wall_seconds':60,
        'base_stoppage_exponential_mean_seconds':5,'extra_mean_seconds_when_final5_and_margin_abs_le_1':35,
        'trade_rate_base_per_second':.25,'close_trade_multiplier_at_even_price':4}},
      'parameter_rationales':{'NBA_score_walk':'96 steps at 30 game-clock seconds represent a 48-minute regulation game; the symmetric -3 to +3 increment mix has per-step variance 2.12 and an end-of-regulation score-difference SD of about 14.27 points, a compact basketball-like margin scale without fitting play-by-play transitions.',
        'hockey_score_walk':'A 5% scoring-event probability per 30-second step (±1 with equal probability) yields 6 expected total goals over 60 minutes; one goal changes the margin by one and can move late win probabilities sharply.',
        'overtime':'Ten 30-second steps make each overtime a shorter five-minute period; the periods repeat until a winner. The 120-second NBA and 60-second hockey wall-clock breaks are explicit stylized inter-period pauses.',
        'wall_clock':'Each possession lasts 30 game-clock seconds plus an exponential stoppage delay. Base mean delays are 4 seconds (NBA) and 5 seconds (hockey); in a close final five minutes, add 25 seconds (NBA, absolute margin at most 6) or 35 seconds (hockey, absolute margin at most 1). These are transparent stylized assumptions, not fitted estimates.',
        'trade_arrivals':'The close-state multiplier peaks at 4x for a 50-50 win probability; 0.15 is the probability-distance scale and 0.5 adds up to 50% for late clock. Sport-specific base rates 7.5/sec (NBA) and 0.25/sec (hockey) scale the eligible final-five row counts toward the observed league-specific sample levels; the rate shape is not fitted.',
        'symmetric_start':'Every game starts tied with equal team strength; there is no home advantage, team heterogeneity, or point drift. This isolates estimator behavior under an intentionally minimal fair-pricing null.'},
      'real_comparators':real_comparators()}
    print('Running NBA baseline',flush=True)
    out['NBA']=run('NBA',48,[-3,-2,-1,0,1,2,3],[.04,.12,.22,.24,.22,.12,.04],[4.,25.],6,120,SEED,7.5)
    print('Running hockey rare-scoring variant',flush=True)
    out['hockey_rare_scoring']=run('Hockey',60,[-1,0,1],[.025,.95,.025],[5.,35.],1,60,SEED+1000000,.25)
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print('Wrote',OUT,flush=True)

if __name__=="__main__": main()
