"""Decompose selected-window price gaps into selection-predicted and residual parts."""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from common import ROOT
from phase5_selection_formula import build_phase5_frames, DRAWS, SEED
from phase5a import OUT

BANDS = [('0.05-0.20', .05, .20), ('0.10-0.40', .10, .40)]
COORDS = [('Market', 'price'), ('P*', 'pstar')]


def make_bin_map(table):
    keys = set(table.bin.astype(str))
    def mapper(p):
        c = int(np.floor(float(p) * 100 - 1e-10))
        one = f'1c:{c:02d}'
        five = f'5c:{(c // 5) * 5:02d}'
        if one in keys:
            return one
        if five in keys:
            return five
        return None
    return mapper


def sufficient(frame, prob, mapper):
    d = frame.loc[frame[prob].between(.03, .97, inclusive='both'),
                  ['game_id', prob, 'y', 'is_d']].copy()
    d['bin'] = d[prob].map(mapper)
    d = d.dropna(subset=['bin'])
    games = pd.Index(d.game_id.unique())
    bins = pd.Index(sorted(d.bin.unique(), key=lambda x: int(x.split(':')[1])))
    gi = games.get_indexer(d.game_id); bi = bins.get_indexer(d.bin)
    arrays = {k: np.zeros((len(games), len(bins)), dtype=float)
              for k in ['base0','base1','in0','in1']}
    y = d.y.to_numpy(int); ins = d.is_d.to_numpy(bool)
    for cls in (0, 1):
        m = y == cls
        arrays[f'base{cls}'][gi[m], bi[m]] += 1
        mi = m & ins
        arrays[f'in{cls}'][gi[mi], bi[mi]] += 1
    return games, bins, arrays


def target_groups(target, prob, mapper, lo, hi):
    z = target.loc[target.price.between(lo, hi, inclusive='both') &
                    target.price.between(.03, .97, inclusive='both') &
                    target.pstar.between(.03, .97, inclusive='both')].copy()
    z['prob'] = pd.to_numeric(z[prob], errors='coerce')
    z['bin'] = z.prob.map(mapper)
    z = z.dropna(subset=['bin','prob'])
    # P* is continuous within cent bins; retain 4 decimals to average C(p)-p
    # over the same trade-price distribution without a per-draw row scan.
    z['pkey'] = z.prob.round(4)
    g = z.groupby(['game_id','bin','pkey'], sort=False).agg(
        n=('y','size'), wins=('y','sum'), psum=('prob','sum')).reset_index()
    return z, g


def decompose(base, target, prob, mapper, lo, hi, draws=DRAWS, seed=SEED):
    sample, grouped = target_groups(target, prob, mapper, lo, hi)
    if sample.empty:
        return {'trades': 0, 'games': 0, 'observed': None, 'predicted': None, 'remainder': None}
    games, bins, arr = sufficient(base, prob, mapper)
    bin_index = bins.get_indexer(grouped.bin)
    game_index = games.get_indexer(grouped.game_id)
    n = grouped.n.to_numpy(float)
    wins = grouped.wins.to_numpy(float)
    psum = grouped.psum.to_numpy(float)
    p = np.divide(psum, n, out=np.zeros_like(psum), where=n > 0)
    rng = np.random.default_rng(seed)
    W = rng.multinomial(len(games), np.full(len(games), 1 / len(games)), size=draws)
    draws_out = np.empty((draws, 3), dtype=float)
    for i, w in enumerate(W):
        b0 = w @ arr['base0']; b1 = w @ arr['base1']
        i0 = w @ arr['in0']; i1 = w @ arr['in1']
        pi0 = np.divide(i0, b0, out=np.zeros_like(i0), where=b0 > 0)
        pi1 = np.divide(i1, b1, out=np.zeros_like(i1), where=b1 > 0)
        den = p * pi1[bin_index] + (1-p) * pi0[bin_index]
        c = np.divide(p * pi1[bin_index], den, out=np.zeros_like(p), where=den > 0)
        wg = w[game_index]
        total = np.sum(wg * n)
        observed = np.sum(wg * (wins - psum)) / total
        predicted = np.sum(wg * n * (c - p)) / total
        remainder = np.sum(wg * (wins - n*c)) / total
        draws_out[i] = [observed, predicted, remainder]
    # Point estimates use the unweighted sufficient statistics.
    b0 = arr['base0'].sum(axis=0); b1 = arr['base1'].sum(axis=0)
    i0 = arr['in0'].sum(axis=0); i1 = arr['in1'].sum(axis=0)
    pi0 = np.divide(i0, b0, out=np.zeros_like(i0), where=b0 > 0)
    pi1 = np.divide(i1, b1, out=np.zeros_like(i1), where=b1 > 0)
    den = p * pi1[bin_index] + (1-p) * pi0[bin_index]
    c = np.divide(p * pi1[bin_index], den, out=np.zeros_like(p), where=den > 0)
    observed = float(np.sum(wins - psum) / np.sum(n))
    predicted = float(np.sum(n * (c-p)) / np.sum(n))
    remainder = float(np.sum(wins - n*c) / np.sum(n))
    out = {'trades': int(len(sample)), 'games': int(sample.game_id.nunique()),
           'observed': observed, 'observed_ci95': np.quantile(draws_out[:,0],[.025,.975]).tolist(),
           'predicted': predicted, 'predicted_ci95': np.quantile(draws_out[:,1],[.025,.975]).tolist(),
           'remainder': remainder, 'remainder_ci95': np.quantile(draws_out[:,2],[.025,.975]).tolist(),
           'draws': draws, 'successful_draws': draws, 'cluster': 'game',
           'band_defined_by': 'market YES price; same trades used for Market and P*',
           'probability_common_support': 'both market and P* in [0.03, 0.97]'}
    return out


def observed_only(target, lo, hi, draws=DRAWS, seed=SEED):
    z = target.loc[target.price.between(lo,hi,inclusive='both') &
                   target.price.between(.03,.97,inclusive='both') &
                   target.pstar.between(.03,.97,inclusive='both')].copy()
    if z.empty:
        return {'trades':0,'games':0,'observed':None,'observed_ci95':None}
    games=pd.Index(z.game_id.unique()); gi=games.get_indexer(z.game_id)
    n=np.bincount(gi,minlength=len(games)).astype(float)
    vals={}
    for name,pcol in [('Market','price'),('P*','pstar')]:
        # game-level trade totals preserve the trade-weighted point estimator
        # under each game-cluster bootstrap draw.
        sums=np.zeros(len(games)); np.add.at(sums,gi,z.y.to_numpy(float)-z[pcol].to_numpy(float))
        rng=np.random.default_rng(seed+(0 if name=='Market' else 1))
        W=rng.multinomial(len(games),np.full(len(games),1/len(games)),size=draws)
        bd=(W@sums)/(W@n)
        vals[name]={'estimate':float(sums.sum()/n.sum()),
                    'ci95':np.quantile(bd,[.025,.975]).tolist()}
    return {'trades':int(len(z)),'games':int(z.game_id.nunique()),'observed':vals,
            'draws':draws,'cluster':'game'}


def main():
    frames, base, _weak = build_phase5_frames()
    # Formula base and d samples are restricted to the d definition; no-OT
    # estimands additionally remove every game that entered overtime.
    formula_bins=pd.read_csv(OUT/'phase5_selection_formula_bins.csv')
    out=[]
    for window, no_ot in [('(d)',False),('(d) excl. OT',True)]:
        b=base.loc[base.period.ge(4)].copy()
        if no_ot:
            b=b.loc[~b.is_ot_game]
        target=b.loc[b.is_d].copy()
        for band,lo,hi in BANDS:
            for source,prob in COORDS:
                tabkey='(d) excluding OT' if no_ot else '(d)'
                tab=formula_bins.loc[formula_bins.window.eq(tabkey) & formula_bins.coordinate.eq(prob)]
                mapper=make_bin_map(tab)
                res=decompose(b,target,prob,mapper,lo,hi,seed=SEED+(10 if no_ot else 0)+(1 if prob=='pstar' else 0))
                out.append({'window':window,'band':band,'source':source,**res})
    # Knowable window observed gaps only; price defines the band and both
    # probability series use that exact shared set of trades.
    know=base.loc[base.is_know].copy()
    know_pairs=[]
    for band,lo,hi in BANDS:
        r=observed_only(know,lo,hi,seed=SEED+77)
        know_pairs.append({'window':'Knowable','band':band,**r})
    pd.DataFrame(out).to_csv(OUT/'phase5_selection_decomposition.csv',index=False)
    pd.DataFrame(know_pairs).to_json(OUT/'phase5_selection_decomposition_knowable.json',orient='records',indent=2)
    summary={'d_decompositions':out,'knowable_observed_gaps':know_pairs,
             'method':{'selection_formula':'pi1=P(trade in d|Y=1,p), pi0=P(trade in d|Y=0,p); estimated from all final-regulation and overtime trades in the same price bin','prediction':'C(p)=p*pi1/(p*pi1+(1-p)*pi0); predicted gap is the trade-weighted mean C(p)-p on the exact target trades','remainder':'trade-weighted observed Y-p minus predicted C(p)-p','bootstrap':'2,000 game-cluster resamples; re-estimate pi in every draw and use the same resampled games for all three components','bands':'market YES price defines each interval; Market and P* use identical trades; both coordinates are restricted to common 0.03-0.97 support','bins':'reuse approved selection-formula bins: one cent unless fewer than 30 selected games for an outcome, then five-cent pooled'}}
    (OUT/'phase5_selection_decomposition.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
