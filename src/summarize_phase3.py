"""Create final-five-minute reliability tables/figure and concise model metrics."""
import json
from pathlib import Path
import pandas as pd
import numpy as np
from common import ROOT
from game_windows import final_regulation_mask

I=ROOT/'data/interim'; O=I/'phase3'; F=ROOT/'figures'; F.mkdir(exist_ok=True)

def make_rel(d,sample):
    mask=np.asarray(final_regulation_mask(d.period,d.clock_s_remaining,5),dtype=bool)
    z=d[mask].copy() if sample=='final5_regulation' else d.copy()
    if z.empty:return pd.DataFrame()
    z['bin']=pd.cut(z.pstar,bins=np.linspace(0,1,11),include_lowest=True,labels=False)
    a=z.groupby('bin',observed=True).agg(states=('y','size'),games=('game_id','nunique'),mean_p=('pstar','mean'),win_rate=('y','mean')).reset_index()
    a['calibration_error']=a.win_rate-a.mean_p; a['sample']=sample
    return a

def main():
    summary=json.loads((O/'phase3_summary.json').read_text()); p=pd.read_parquet(O/'pstar_2025_26_every_second.parquet')
    outputs=[]
    for s in ['all_states','final5_regulation']:
        r=make_rel(p,s); outputs.append(r); r.to_csv(O/f'reliability_2025_26_{s}.csv',index=False)
    both=pd.concat(outputs,ignore_index=True); both.to_csv(O/'reliability_2025_26_all_and_final5.csv',index=False)
    try:
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(1,2,figsize=(11,4.5),sharex=True,sharey=True)
        for ax,s,title in zip(axes,['all_states','final5_regulation'],['All game states','Final five minutes of regulation']):
            d=both[both['sample']==s]
            ax.plot([0,1],[0,1],color='0.6',linestyle='--',linewidth=1)
            ax.plot(d.mean_p,d.win_rate,marker='o',color='#1f77b4')
            for r in d.itertuples():
                if r.states>=50: ax.annotate(str(r.states), (r.mean_p,r.win_rate), xytext=(3,3),textcoords='offset points',fontsize=7)
            ax.set_title(title); ax.set_xlabel('Mean predicted home-team win probability'); ax.grid(alpha=.2)
        axes[0].set_ylabel('Observed home-team win frequency')
        fig.suptitle('P* calibration on the 2025–26 market sample')
        fig.tight_layout(); fig.savefig(F/'pstar_reliability_2025_26.png',dpi=180); plt.close(fig)
    except Exception as e:
        summary['reliability_plot_error']=str(e)
        (O/'phase3_summary.json').write_text(json.dumps(summary,indent=2,default=str))
    m=np.asarray(final_regulation_mask(p.period,p.clock_s_remaining,5),dtype=bool)
    summary['market_sample_final5_reliability']={'n_states':int(m.sum()),'n_games':int(p.loc[m,'game_id'].nunique()),'brier':float(np.mean((p.loc[m,'y']-p.loc[m,'pstar'])**2))}
    for col in ['pstar','pstar_with_possession','pstar_spline_logistic']:
        if col in p:
            summary.setdefault('market_sample_final5_brier_by_model',{})[col]=float(np.mean((p.loc[m,'y']-p.loc[m,col])**2))
    summary['possession_final5_brier_increment']=(summary['market_sample_final5_brier_by_model'].get('pstar_with_possession')-
        summary['market_sample_final5_brier_by_model'].get('pstar'))
    # Phase 5 calibration bins, including both longshot and favorite wings.
    edges=[0.03,0.05,0.10,0.20,0.35,0.50,0.65,0.80,0.90,0.97]
    labels=[f'[{a:.2f},{b:.2f}{"]" if i==len(edges)-2 else ")"}' for i,(a,b) in enumerate(zip(edges[:-1],edges[1:]))]
    z=p.loc[m].copy(); z['price_bin']=pd.cut(z.pstar,edges,right=False,labels=labels,include_lowest=True)
    bins=z.groupby('price_bin',observed=True).agg(states=('y','size'),games=('game_id','nunique'),mean_pstar=('pstar','mean'),observed_frequency=('y','mean')).reset_index()
    bins['calibration_gap']=bins.observed_frequency-bins.mean_pstar
    bins.to_csv(O/'reliability_2025_26_final5_main_price_bins.csv',index=False)
    (O/'phase3_summary.json').write_text(json.dumps(summary,indent=2,default=str))
    print(json.dumps({'selected_model':summary['selected_model'],'selection':summary['selected_model_holdout_metrics'],'market_sample':summary['final_refit_market_sample_metrics'],'final5':summary['market_sample_final5_reliability']},indent=2))
if __name__=='__main__':main()
