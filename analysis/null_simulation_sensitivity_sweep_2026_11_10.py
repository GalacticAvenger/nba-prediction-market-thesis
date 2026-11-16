"""Prespecified 3x2 NBA null-simulation sensitivity sweep.
Each cell uses the same 1,000 seasons, 1,230 games/season, and seed.
Only the arrival closeness coefficient and added late-close wall delay vary.
No draft is edited; no parameter is tuned to match observed results."""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import null_simulation_fair_pricing_2026_11_10 as base

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/interim/phase5/fair_pricing_nba_sensitivity_sweep_2026_11_10.json"
R=1000
G=1230
SEED=20261110
NAMES=base.NAMES
COUNTS=base.COUNTS

def run_cell(boost, late_delay):
    vals=np.asarray([-3,-2,-1,0,1,2,3],dtype=np.int64)
    probs=np.asarray([.04,.12,.22,.24,.22,.12,.04],dtype=np.float64)
    cdf=np.cumsum(probs); cdf[-1]=1.
    reg_minutes=48; nreg=96; otsteps=10; bound=6*nreg+3*otsteps+20
    dpreg=base.dp_make(nreg,bound,vals,probs)
    dpot=base.dp_make(otsteps,bound,vals,probs)
    em=np.empty((R,10)); om=np.empty((R,10)); cm=np.empty((R,4))
    for r in range(R):
        e,o,c=base.season(SEED+r,nreg,reg_minutes,otsteps,bound,vals,probs,cdf,dpreg,dpot,
            4.,float(late_delay),6,7.5,float(boost),.15,.5,120)
        em[r]=e; om[r]=o; cm[r]=c
        if (r+1)%200==0:
            print(f"boost={boost}, late_delay={late_delay}: {r+1}/{R}",flush=True)
    def mcmean(col):
        x=cm[:,col]; x=x[np.isfinite(x)]
        return {'mean':float(x.mean()),'MCSE':float(x.std(ddof=1)/math.sqrt(len(x)))}
    ratios=cm[:,1]; ratios=ratios[np.isfinite(ratios)]
    return {
      'estimators':base.bootless_summary(em,NAMES),
      'mean_sample_sizes':base.count_summary(om),
      'overtime_share':mcmean(0),
      'final5_trade_count_ratio_winning_vs_no_winning_longshot':{
        'mean':float(ratios.mean()),'MCSE':float(ratios.std(ddof=1)/math.sqrt(len(ratios))),
        'mean_trades_per_game_with_winning_longshot':float(cm[:,2].mean()),
        'mean_trades_per_game_without_winning_longshot':float(cm[:,3].mean())},
      'fixed_time_fairness_check':{
        'final5_fixed_clock_A_pp_mean':float(em[:,7].mean()*100),
        'MCSE_pp':float(em[:,7].std(ddof=1)/math.sqrt(R)*100),
        'z_from_zero':float(em[:,7].mean()/(em[:,7].std(ddof=1)/math.sqrt(R)))},
      'seed':SEED,'synthetic_seasons':R,'games_per_season':G
    }

def main():
    # Predeclared Cartesian grid: no data-dependent parameter changes.
    cells={}
    for boost in [1.,3.,6.]:
        for delay in [25.,50.]:
            key=f"closeness_coefficient_{int(boost)}__late_delay_{int(delay)}s"
            print("Running",key,flush=True)
            cells[key]=run_cell(boost,delay)
    out={
      'purpose':'Sensitivity of the fair-pricing NBA null simulation to the two prespecified parameters.',
      'grid':{'closeness_term_coefficient':[1,3,6],'late_close_extra_wall_delay_mean_seconds':[25,50]},
      'fixed_settings':{
        'seed_each_cell':SEED,'synthetic_seasons_each_cell':R,'games_per_season':G,
        'other_parameters':'Identical to analysis/null_simulation_fair_pricing_2026_11_10.py NBA baseline.',
        'estimator_units':'A in percentage points; Monte Carlo standard errors across seasons; no bootstrap inside seasons.',
        'unmodified_parameters':{
          'regulation_possessions':96,'game_clock_seconds_per_possession':30,
          'score_difference_increment_probabilities':{'-3':.04,'-2':.12,'-1':.22,'0':.24,'+1':.22,'+2':.12,'+3':.04},
          'overtime_possessions':10,'overtime_break_wall_seconds':120,'base_stoppage_exponential_mean_seconds':4,
          'late_close_margin_threshold_abs_points':6,'trade_base_rate_per_second':7.5,
          'closeness_price_scale':.15,'late_clock_rate_multiplier_minus_one':.5,
          'longshot_probability_band':[.05,.20],'price':'exact dynamic-programming win probability'}
      },
      'runs':cells
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print("Wrote",OUT,flush=True)

if __name__=="__main__": main()
