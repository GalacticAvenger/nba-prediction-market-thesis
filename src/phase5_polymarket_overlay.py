"""Add read-only Polymarket summary estimates to Phase 5 figures and tables."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from common import ROOT

KALSHI=ROOT/'data/interim/phase5/phase5_publication_summary.json'
POLY=ROOT/'data/interim/phase6/polymarket_selection_summary.json'  # read only
FIG=ROOT/'figures/phase5'; TAB=ROOT/'tables/phase5'; OUT=ROOT/'data/interim/phase5'
EDGES=np.array([.03,.05,.10,.20,.35,.50,.65,.80,.90,.97])

def tex_table(path,caption,label,headers,rows,align):
    lines=[r'\begin{table}[!htbp]',r'\centering',r'\small',rf'\caption{{{caption}}}',rf'\label{{{label}}}',rf'\resizebox{{\textwidth}}{{!}}{{%',rf'\begin{{tabular}}{{{align}}}',r'\toprule',' & '.join(headers)+r' \\',r'\midrule']
    lines += [' & '.join(map(str,row))+r' \\' for row in rows]
    lines += [r'\bottomrule',r'\end{tabular}',r'}',r'\end{table}']
    (TAB/path).write_text('\n'.join(lines)+'\n')

def main():
    k=json.load(open(KALSHI)); p=json.load(open(POLY))
    # Extend the two-panel calibration figure with the available Polymarket
    # trade-weighted calibration points. The supplied summary has no clustered
    # bin intervals, so retain Kalshi bands and plot Poly points without bands.
    polybins=pd.DataFrame(p['calibration_bins'])
    kalrows=[]
    for window,coords in k['calibration_figure_bins'].items():
        for coord,values in coords.items():
            for value in values:kalrows.append({'window':window,'coordinate':coord,**value})
    kalbins=pd.DataFrame(kalrows)
    styles={('Kalshi','Market'):{'color':'#245a8d','ls':'-','marker':'o'},
            ('Kalshi','P*'):{'color':'#d47a20','ls':'-','marker':'s'},
            ('Polymarket','Market'):{'color':'#6a3d9a','ls':'--','marker':'D'},
            ('Polymarket','P*'):{'color':'#16806a','ls':'--','marker':'^'}}
    fig,axs=plt.subplots(1,2,figsize=(8.2,3.7),sharex=True,sharey=True)
    for ax,window,title in zip(axs,['d','final5'],['(d) Last 10 wall minutes','Final 5 regulation minutes']):
        for coord in ['Market','P*']:
            kcoord='market' if coord=='Market' else 'Pstar'
            kb=kalbins[(kalbins.window==window)&(kalbins.coordinate==kcoord)].sort_values('mean_p')
            st=styles[('Kalshi',coord)]
            ax.plot(kb.mean_p,kb.observed_y,marker=st['marker'],ls=st['ls'],color=st['color'],lw=1.5,ms=3,label=f"Kalshi {coord}")
            ax.fill_between(kb.mean_p.to_numpy(),kb.observed_y_ci95.apply(lambda z:z[0]).to_numpy(float),kb.observed_y_ci95.apply(lambda z:z[1]).to_numpy(float),color=st['color'],alpha=.12,lw=0)
        specs=[('d_wall10_own_token','market','d_market','Market'),('d_wall10_own_token','pstar','d_pstar','P*')] if window=='d' else [('gameclock_final5_selected','market','gameclock_5_market','Market'),('gameclock_final5_selected','pstar','gameclock_5_pstar','P*')]
        for version,source,polywindow,coord in specs:
            z=polybins[(polybins.version==version)&(polybins.source==source)&(polybins.window==polywindow)].copy()
            z['bin_lo']=z.cent.astype(float)/100
            z=z[(z.bin_lo>=.03)&(z.bin_lo<.97)].copy()
            z['main_bin']=pd.cut(z.bin_lo,EDGES,right=False,include_lowest=True)
            g=z.groupby('main_bin',observed=True).apply(lambda a:pd.Series({'n':a.n.sum(),'mean_p':np.average(a.p,weights=a.n),'observed_y':np.average(a.raw_rate,weights=a.n)}),include_groups=False).reset_index(drop=True)
            st=styles[('Polymarket',coord)]
            ax.plot(g.mean_p,g.observed_y,marker=st['marker'],ls=st['ls'],color=st['color'],lw=1.25,ms=3.5,label=f"Polymarket {coord}")
        ax.plot([.03,.97],[.03,.97],color='#555555',ls=':',lw=1,label='45°')
        ax.set(title=title,xlim=(.03,.97),ylim=(.03,.97),xlabel='Mean predicted probability')
        ax.set_xticks([.05,.2,.35,.5,.65,.8,.9,.97]);ax.set_yticks([.05,.2,.35,.5,.65,.8,.9,.97]);ax.tick_params(labelsize=7)
    axs[0].set_ylabel('Observed win frequency')
    handles,labels=axs[1].get_legend_handles_labels();fig.legend(handles,labels,frameon=False,loc='lower center',ncol=5,bbox_to_anchor=(.5,-.05),fontsize=7)
    fig.tight_layout(rect=[0,.08,1,1])
    for ext in ('pdf','png'):fig.savefig(FIG/f'calibration_market_vs_pstar.{ext}',bbox_inches='tight')
    plt.close(fig)
    # Alpha figure with Kalshi and Polymarket estimates in separate columns.
    fitrows=[('d','d_market','d_pstar','d_market','d_pstar'),
      ('Knowable','knowable_market','knowable_pstar','knowable_market','knowable_pstar'),
      ('Final 2','gameclock_2_market','gameclock_2_pstar','gameclock_2_market','gameclock_2_pstar'),
      ('Final 3','gameclock_3_market','gameclock_3_pstar','gameclock_3_market','gameclock_3_pstar'),
      ('Final 5','gameclock_5_market','gameclock_5_pstar','gameclock_5_market','gameclock_5_pstar'),
      ('Final 10','gameclock_10_market','gameclock_10_pstar','gameclock_10_market','gameclock_10_pstar')]
    marks=[('Kalshi','Market','#245a8d','o'),('Kalshi','P*','#d47a20','s'),('Polymarket','Market','#6a3d9a','D'),('Polymarket','P*','#16806a','^')]
    fig,ax=plt.subplots(figsize=(8.1,4.3)); ybase=np.arange(len(fitrows))[::-1]; offsets=[-.24,-.08,.08,.24]
    for i,(window,km,kp,pm,pp) in enumerate(fitrows):
        for off,(venue,coord,color,mark),key in zip(offsets,marks,[km,kp,pm,pp]):
            f=(k if venue=='Kalshi' else p)['fits'][key]['isotonic']; b=f['bootstrap'];ci=b['alpha_ci95']; y=ybase[i]+off
            ax.errorbar(f['alpha'],y,xerr=[[f['alpha']-ci[0]],[ci[1]-f['alpha']]],fmt=mark,color=color,capsize=2,ms=3.7,lw=1.1)
    ax.axvline(1,color='#555',ls='--',lw=1);ax.set_yticks(ybase,[r[0] for r in fitrows]);ax.set_xlabel('Prelec-II α (isotonic calibration)');ax.set_title('Late-window curvature by platform and probability source')
    ax.legend(handles=[Line2D([],[],color=c,marker=m,ls='',label=f'{v} {s}') for v,s,c,m in marks],frameon=False,loc='lower right',ncol=2,fontsize=8)
    fig.tight_layout()
    for ext in ('pdf','png'):fig.savefig(FIG/f'prelec_alpha_by_window.{ext}',bbox_inches='tight')
    plt.close(fig)
    # P* placebo table: direct platform columns, using available full-season windows.
    lookup=[('d','d_market','d_pstar'),('Knowable','knowable_market','knowable_pstar'),('Final 2','gameclock_2_market','gameclock_2_pstar'),('Final 3','gameclock_3_market','gameclock_3_pstar'),('Final 5','gameclock_5_market','gameclock_5_pstar'),('Final 10','gameclock_10_market','gameclock_10_pstar')]
    rows=[]
    for win,km,kp in lookup:
        pk=km.replace('_market','_market'); pp=kp
        for src,kk,pkkey in [('Market',km,pk),('P*',kp,pp)]:
            ka=k['fits'][kk]['isotonic'];kb=ka['bootstrap']['alpha_ci95'];pa=p['fits'][pkkey]['isotonic'];pb=pa['bootstrap']['alpha_ci95']
            kc=k['fits'][kk];pc=p['fits'][pkkey]
            rows.append([win,src,f"{kc['trades']:,} / {kc['games']:,}",f"{ka['alpha']:.3f} [{kb[0]:.3f}, {kb[1]:.3f}]",f"{ka['beta']:.3f}",f"{pc['trades']:,} / {pc['games']:,}",f"{pa['alpha']:.3f} [{pb[0]:.3f}, {pb[1]:.3f}]",f"{pa['beta']:.3f}"])
    tex_table('pstar_placebo.tex','Kalshi and Polymarket trade-weighted Prelec-II fits; game-cluster bootstrap CIs. Paper-date P* coverage is unavailable for playoffs.','tab:pstar-placebo',['Window','Source','Kalshi N / G','Kalshi α [95% CI]','Kalshi β','Polymarket N / G','Polymarket α [95% CI]','Polymarket β'],rows,'llrlrlrl')
    # Mechanism comparison supported by both platform summaries. The wall-time
    # and OT-by-outcome table remains Kalshi-only because the Poly summary does
    # not report those grouped statistics.
    kr=k['final3_pstar_inside_outside_d'];pr=p['final3_longshot_inside_outside_d'];rows=[]
    for win in ['inside_d','outside_d']:
        for coord,kname,pname in [('Market','Y_minus_market','price'),('P*','Y_minus_Pstar','Pstar')]:
            a=kr[win];b=next(x for x in pr if x['window']==win and x['coordinate'].lower()==pname.lower())
            v=a[kname];ci=v['ci95'];pc=b['game_weighted_gap_ci95']
            rows.append([win.replace('_',' '),coord,f"{a['trades']:,} / {a['games']}",f"{v['estimate']:.4f} [{ci[0]:.4f}, {ci[1]:.4f}]",f"{b['maker_fills']:,} / {b['games']}",f"{b['game_weighted_Y_minus_probability']:.4f} [{pc[0]:.4f}, {pc[1]:.4f}]"])
    tex_table('mechanism_platform_comparison.tex','Final-three-minute 0.05–0.20 longshot gaps inside/outside (d), Kalshi versus Polymarket.','tab:mechanism-platform',['Window','Probability','Kalshi N / G','Kalshi Y−p [95% CI]','Polymarket N / G','Polymarket Y−p [95% CI]'],rows,'llrlrl')
    # Save an explicit derived binned-data artifact; source summary remains untouched.
    out=[]
    for window,version in [('d','d_wall10_own_token'),('final5','gameclock_final5_selected')]:
        for source in ('market','pstar'):
            polywindow=('d_market' if source=='market' else 'd_pstar') if window=='d' else (f'gameclock_5_{source}')
            z=polybins[(polybins.version==version)&(polybins.source==source)&(polybins.window==polywindow)].copy();z['bin_lo']=z.cent.astype(float)/100;z=z[(z.bin_lo>=.03)&(z.bin_lo<.97)];z['analysis_bin']=pd.cut(z.bin_lo,EDGES,right=False,include_lowest=True)
            for label,g in z.groupby('analysis_bin',observed=True):out.append({'window':window,'source':source,'bin':str(label),'trades':int(g.n.sum()),'mean_probability':np.average(g.p,weights=g.n),'observed_frequency':np.average(g.raw_rate,weights=g.n),'confidence_interval':'not available in supplied summary'})
    pd.DataFrame(out).to_csv(OUT/'polymarket_calibration_main_bins.csv',index=False)

if __name__=='__main__':main()
