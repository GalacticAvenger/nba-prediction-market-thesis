"""Plot cross-venue, game-held-out selection predictions and remainders."""
from __future__ import annotations
import json
import matplotlib.pyplot as plt
import numpy as np

from common import ROOT

FILES = {
    'Kalshi': ROOT/'data/interim/phase5/phase5_crossfit_selection_diagnostic.json',
    'Polymarket': ROOT/'data/interim/phase2/polymarket_crossfit_selection_diagnostic.json',
}
AUDIT = ROOT/'data/interim/phase5/phase5_selection_inference_audit.json'
TEMPORAL = ROOT/'data/interim/phase5/phase5_temporal_selection_validation.json'
OUT = ROOT/'figures/phase5'


def main() -> None:
    data={venue:json.loads(path.read_text()) for venue,path in FILES.items()}
    audit=json.loads(AUDIT.read_text())
    temporal=json.loads(TEMPORAL.read_text())
    def result(venue, band, coord):
        key=f'{band}_10m_{coord}_0.050'
        root='coordinates' if venue=='Kalshi' else 'estimates'
        return data[venue][root][key]
    groups=[('Kalshi','05_20','5–20¢'),('Polymarket','05_20','5–20¢'),
            ('Kalshi','10_40','10–40¢'),('Polymarket','10_40','10–40¢')]
    fig,axes=plt.subplots(1,3,figsize=(17,7),gridspec_kw={'width_ratios':[1,1,1.55]})
    colors={'observed':'#232b35','predicted':'#2675b8'}
    for ax,coord,title in zip(axes[:2],('price','pstar'),
                              ('Market price: observed vs predicted','P*: observed vs predicted')):
        for i,(venue,band,label) in enumerate(groups):
            v=result(venue,band,coord)
            for j,(kind,est,ci) in enumerate([
                ('observed',v['observed_gap'],v['observed_gap_ci95']),
                ('predicted',v['selection_predicted_gap'],v['selection_predicted_gap_ci95'])]):
                x=i+(-.13 if j==0 else .13)
                ax.errorbar(x,est*100,yerr=[[ (est-ci[0])*100 ],[ (ci[1]-est)*100 ]],
                    fmt='o',color=colors[kind],capsize=3,markersize=6,
                    label={'observed':'Observed','predicted':'Cross-fit prediction'}[kind]
                    if i==0 else None)
        ax.axhline(0,color='#777777',linewidth=.8)
        ax.set_title(title,fontsize=11)
        ax.set_xticks(range(len(groups)),[f'{v}\n{band}' for v,_,band in groups])
        ax.set_ylabel('Outcome minus probability (percentage points)')
        ax.grid(axis='y',alpha=.2)
        ax.legend(frameon=False,loc='lower left',fontsize=8)

    ax=axes[2]
    rows=[]
    for venue, name in [('kalshi','Kalshi'),('polymarket','Polymarket')]:
        a=audit[venue]
        rows.append((f'{name}: random-fold, trade-weighted',
                     a['remainder']['trade_weighted']['estimate']*100,
                     a['remainder']['trade_weighted']['ci95_fixed_prediction_game_bootstrap'],
                     data[name]['coordinates' if name=='Kalshi' else 'estimates'][
                         f'05_20_10m_price_0.050']['remainder_ci95']))
        rows.append((f'{name}: random-fold, equal-game',
                     a['remainder']['equal_game']['estimate']*100,
                     a['remainder']['equal_game']['ci95_fixed_prediction_game_bootstrap'], None))
    tv=temporal['coordinates']['05_20_price_0.05']
    rows.append(('Kalshi: chronological holdout', tv['remainder']*100,
                 tv['ci95']['remainder'], None))
    ys=np.arange(len(rows))
    for y,(label,e,ci_fixed,ci_refit) in enumerate(rows):
        ax.errorbar(e,y,xerr=[[e-ci_fixed[0]*100],[ci_fixed[1]*100-e]],
                    fmt='o',color='#2f7d52',capsize=3,markersize=5,
                    label='Fixed-prediction / temporal bootstrap' if y==0 else None)
        if ci_refit is not None:
            ax.errorbar(e,y,xerr=[[(e/100-ci_refit[0])*100],[(ci_refit[1]-e/100)*100]],
                        fmt='none',ecolor='#d17a22',elinewidth=2,capsize=4,
                        label='Original refit bootstrap' if y==0 else None)
    ax.set_yticks(ys,[r[0] for r in rows],fontsize=7)
    ax.axvline(0,color='#777777',linewidth=.8)
    ax.set_xlabel('Observed minus selection prediction (pp)')
    ax.set_title('Remainder across weights and time')
    ax.grid(axis='x',alpha=.2)
    ax.invert_yaxis()
    ax.legend(frameon=False,loc='upper center',bbox_to_anchor=(.5,-.12),ncol=2,fontsize=7)
    fig.suptitle('Outcome-dependent selection: pooled fit and validation sensitivities',
                 fontsize=14,y=1.02)
    fig.text(.5,-.07,'Left panels show pooled random-fold results. Right panel compares game weighting and a later-season holdout; intervals use different bootstrap treatments.',
             ha='center',fontsize=9)
    fig.tight_layout()
    OUT.mkdir(parents=True,exist_ok=True)
    fig.savefig(OUT/'crossfit_selection_validation.png',dpi=300,bbox_inches='tight')
    fig.savefig(OUT/'crossfit_selection_validation.pdf',bbox_inches='tight')


if __name__=='__main__':
    main()
