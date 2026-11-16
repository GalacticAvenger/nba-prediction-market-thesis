"""Reproduce fresh NBA results reported on 2026-11-10; reads thesis data only.

Outputs a JSON record with sample counts, point estimates, bootstrap intervals,
source descriptions, and settings. No thesis document is edited.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from phase5_selection_formula import build_phase5_frames
from phase5a import META, PANEL, OUT
from game_windows import is_final_regulation_window

DRAWS = 2000
BOOT_SEED = 6102126
FIXED_DRAW = 20000
FIXED_SEED = 334455
OUTFILE = ROOT / 'data/interim/phase5/fresh_results_audit_2026_11_10.json'

def boot_mean(vals, draws=DRAWS, seed=BOOT_SEED):
    a = np.asarray(vals, dtype=float)
    a = a[np.isfinite(a)]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(draws, len(a)))
    boot = a[idx].mean(axis=1)
    return {'estimate': float(a.mean()), 'ci95': np.quantile(boot, [.025, .975]).tolist(),
            'draws': draws, 'seed': seed}

def first_entry(z):
    q = z.sort_values(['game_id', 'ts'], kind='stable').drop_duplicates('game_id')
    r = boot_mean(q.A.to_numpy())
    return {'eligible_trades': int(len(z)), 'games': int(len(q)), 'first_entry_trades': int(len(q)),
            'A_pp': 100*r['estimate'], 'CI95_pp': [100*x for x in r['ci95']],
            'draws': DRAWS, 'seed': BOOT_SEED}

def main():
    out = {'bootstrap_draws_saved_table_convention': DRAWS,
           'bootstrap_seed_fresh_first_entry_and_game_summaries': BOOT_SEED,
           'A_convention': 'A = p - Y', 'units': 'A in percentage points; price in cents'}
    out['sample_definitions_verified_from_source'] = {
        'Moshrefi_comparison_2524781_trades_1202_games': {
            'source': 'src/phase5a.py, version d_full_regular_season',
            'population':'2025-26 Kalshi NBA regular-season trade records with settled YES/NO outcomes',
            'price':'each traded contract market-YES price; all interior prices 0 < p < 1; not a folded longshot band',
            'window':'[last timestamped ESPN play - 10 minutes, last timestamped ESPN play); excludes final play and later trades',
            'filters':'block trades excluded; valid trade timestamps and ESPN last-play timestamp required; no P* support screen',
            'trades':2524781,'games':1202},
        'same_date_NBA_retrospective_933979_trades_581_games': {
            'source':'src/nhl_window_analysis.py, load_nba_dates',
            'population':'2025-26 NBA regular-season games on New York local dates 2025-10-07 through 2026-04-16 inclusive, matched to settled Kalshi team markets and ESPN summaries',
            'price':'cheaper-side team contract (longshot_price), folded to its own YES/NO outcome; 5 to 20 cents inclusive',
            'window':'[ESPN explicit Game End timestamp - 10 minutes, Game End timestamp); if no explicit marker, use maximum timestamped ESPN play; excludes endpoint and later trades',
            'filters':'Phase 4 panel rows (block trades excluded upstream); settled YES/NO outcomes; no P* support screen',
            'trades':933979,'games':581}}

    # Full-game first entry: earliest trade in the folded cheaper-side 5-20c band.
    meta = pd.read_parquet(META)
    meta = meta.loc[(meta.season == 2026) & meta.season_type.eq(2)].copy()
    meta['ticker'] = meta.ticker.astype(str)
    meta['result'] = meta.result.astype(str).str.lower()
    meta = meta.loc[meta.result.isin(['yes', 'no'])]
    full_parts = []
    for m in meta.itertuples(index=False):
        path = PANEL / f'{m.ticker}.parquet'
        if not path.exists():
            continue
        x = pd.read_parquet(path, columns=['game_id','ts_utc','selected_contract_price',
                                          'selected_team_is_home','ticker_yes_is_home'])
        if x.empty:
            continue
        x['game_id'] = x.game_id.astype(str)
        x['ts'] = pd.to_datetime(x.ts_utc, utc=True, errors='coerce')
        ps = pd.to_numeric(x.selected_contract_price, errors='coerce').to_numpy(float)
        same = (x.selected_team_is_home.fillna(False).astype(bool).to_numpy() ==
                x.ticker_yes_is_home.fillna(False).astype(bool).to_numpy())
        y_yes = np.full(len(x), int(m.result == 'yes'), dtype=int)
        y_selected = np.where(same, y_yes, 1-y_yes)
        lp = np.minimum(ps, 1-ps)
        ly = np.where(ps <= .5, y_selected, 1-y_selected)
        take = np.isfinite(lp) & (lp >= .05) & (lp <= .20)
        if take.any():
            full_parts.append(pd.DataFrame({'game_id':x.game_id.to_numpy()[take],
                'ts':x.ts.to_numpy()[take], 'A':lp[take]-ly[take]}))
    full_all = pd.concat(full_parts, ignore_index=True)
    full = full_all.dropna(subset=['ts']).sort_values(['game_id','ts'], kind='stable').drop_duplicates('game_id')
    r = boot_mean(full.A.to_numpy())
    out['G1_full_game_first_entry'] = {'trades': int(len(full)), 'games': int(len(full)),
        'eligible_trade_rows_in_full_game_population':int(len(full_all)),
        'A_pp': 100*r['estimate'], 'CI95_pp':[100*x for x in r['ci95']],
        'definition':'earliest in-game trade, cheaper-side (longshot) contract price 5-20 cents inclusive'}
    fg = full_all.groupby('game_id', sort=True)
    fn = fg.size().to_numpy(float); fs = fg.A.sum().to_numpy(float); fm = fg.A.mean().to_numpy(float)
    fi = np.random.default_rng(9142026).integers(0,len(fn),size=(DRAWS,len(fn)))
    out['N2_full_game_baseline'] = {
        'trades':int(len(full_all)), 'games':int(full_all.game_id.nunique()),
        'trade_weighted_A_pp':100*float(fs.sum()/fn.sum()),
        'trade_weighted_CI95_pp':[100*float(v) for v in np.quantile(fs[fi].sum(axis=1)/fn[fi].sum(axis=1),[.025,.975])],
        'equal_game_A_pp':100*float(fm.mean()),
        'equal_game_CI95_pp':[100*float(v) for v in np.quantile(fm[fi].mean(axis=1),[.025,.975])],
        'draws':DRAWS,'seed':9142026}

    # Reconstruct P*-supported final-five and retrospective selections.
    print('Building phase-5 frame…', flush=True)
    _, base, _ = build_phase5_frames()
    b = base.loc[base.price.between(.05,.20,inclusive='both')].copy()
    b['A'] = b.price - b.y
    b['supported'] = b.price.between(.03,.97,inclusive='both') & b.pstar.between(.03,.97,inclusive='both')
    b['f5'] = np.array([is_final_regulation_window(p,c,5) for p,c in zip(b.period,b.clock_s_remaining)])
    f5p = b.loc[b.f5 & b.supported].copy()
    out['G1_final5_Pstar_first_entry'] = first_entry(f5p)
    out['G1_final5_Pstar_first_entry']['definition'] = 'earliest timestamped eligible trade per game; market YES price 5-20 cents inclusive; market price and P* each in [3,97] cents; Q4/OT in-game rows before last ESPN play; final five regulation minutes'
    ref_band = b.loc[b.supported].copy()
    n1 = {}
    for yval, label in [(1,'winning_contracts'),(0,'losing_contracts')]:
        q = ref_band.loc[ref_band.y.eq(yval)]
        n1[label] = {'reference_trades':int(len(q)), 'window_trades':int(q.is_d.sum()),
                     'share_entering_retrospective_10m':float(q.is_d.mean()), 'games':int(q.game_id.nunique())}
    out['N1_outcome_specific_window_entry_rates'] = {
        'reference_population':{'trades':int(len(ref_band)),'games':int(ref_band.game_id.nunique()),
          'price_band':'market YES 5-20 cents inclusive; market and P* support [3,97] cents'},
        'by_outcome':n1}

    # Exact 684-game no-P* sensitivity is based on saved final-five longshot rows.
    late = pd.read_parquet(OUT/'phase5_late_trades.parquet',
        columns=['game_id','ts','late5','longshot_price','longshot_y'])
    late = late.loc[late.late5 & late.longshot_price.between(.05,.20,inclusive='both')].copy()
    late['A'] = late.longshot_price-late.longshot_y
    out['G1_final5_no_Pstar_first_entry'] = first_entry(late)
    out['G1_final5_no_Pstar_first_entry']['definition'] = 'earliest timestamped eligible trade per game in saved final-five sample; cheaper-side longshot price 5-20 cents inclusive; no P* support restriction'
    out['N3_window_sample_counts'] = {
        'retrospective_10m_common_support':{'trades':int(ref_band.is_d.sum()),'games':int(ref_band.loc[ref_band.is_d,'game_id'].nunique())},
        'final5_Pstar_support':{'trades':int(len(f5p)),'games':int(f5p.game_id.nunique())},
        'final5_no_Pstar_support':{'trades':int(len(late)),'games':int(late.game_id.nunique())}}

    # Per-game trade frequency among supported final-five 5-20c rows.
    counts = f5p.groupby('game_id').agg(n=('A','size'), has_win=('y','max'))
    out['G2_trade_counts_per_game_final5_Pstar'] = {
        ('contains_winning_eligible_contract' if int(k) else 'no_winning_eligible_contract'):
        {'games':int(len(v)), 'mean_eligible_trades':float(v.n.mean()),
         'median_eligible_trades':float(v.n.median())} for k,v in counts.groupby('has_win')}
    out['G2_trade_counts_per_game_final5_Pstar']['sample'] = {'trades':int(len(f5p)), 'games':int(f5p.game_id.nunique())}

    # Selection reference population: both price and P* common support.
    ref = b.loc[b.supported].copy()
    grp = ref.groupby('game_id', sort=True)
    n = grp.size().to_numpy(float)
    p_sum = grp.price.sum().to_numpy(float); a_sum = grp.A.sum().to_numpy(float)
    p_mean = grp.price.mean().to_numpy(float); a_mean = grp.A.mean().to_numpy(float)
    ids = np.random.default_rng(BOOT_SEED).integers(0,len(n),size=(DRAWS,len(n)))
    g3 = {}
    for name, means, sums in [('mean_price',p_mean,p_sum),('A',a_mean,a_sum)]:
        pooled = sums.sum()/n.sum()
        pooled_boot = sums[ids].sum(axis=1)/n[ids].sum(axis=1)
        equal = means.mean(); equal_boot = means[ids].mean(axis=1)
        g3[name] = {'pooled':{'estimate':float(pooled*100), 'CI95':[float(x*100) for x in np.quantile(pooled_boot,[.025,.975])]},
                    'equal_game':{'estimate':float(equal*100), 'CI95':[float(x*100) for x in np.quantile(equal_boot,[.025,.975])]}}
    out['G3_selection_reference_baseline'] = {'trades':int(len(ref)), 'games':int(ref.game_id.nunique()),
       'mean_price_cents_and_A_percentage_points':g3}

    def weighted_summaries(z, seed=9142026):
        gg=z.groupby('game_id',sort=True);nn=gg.size().to_numpy(float)
        sums=gg.A.sum().to_numpy(float); means=gg.A.mean().to_numpy(float)
        ix=np.random.default_rng(seed).integers(0,len(nn),size=(DRAWS,len(nn)))
        return {'trades':int(len(z)),'games':int(z.game_id.nunique()),
          'trade_weighted_A_pp':100*float(sums.sum()/nn.sum()),
          'trade_weighted_CI95_pp':[100*float(v) for v in np.quantile(sums[ix].sum(1)/nn[ix].sum(1),[.025,.975])],
          'equal_game_A_pp':100*float(means.mean()),
          'equal_game_CI95_pp':[100*float(v) for v in np.quantile(means[ix].mean(1),[.025,.975])],
          'draws':DRAWS,'seed':seed}
    out['N6_final5_weighting_sensitivity'] = {
        'Pstar_common_support_market_yes':weighted_summaries(f5p),
        'no_Pstar_folded_longshot':weighted_summaries(late)}

    quiet = pd.read_parquet(OUT/'phase5_primary_trades.parquet',
        columns=['game_id','longshot_price','longshot_y','quote_valid_5s'])
    quiet['A']=quiet.longshot_price-quiet.longshot_y
    def sd_game_means(z):
        means=z.groupby('game_id').A.mean()
        return {'games':int(len(means)),'trades':int(len(z)),
                'SD_game_mean_A_pp':float(means.std(ddof=1)*100)}
    out['N7_across_game_dispersion'] = {
        'quiet_primary_all_rows':sd_game_means(quiet),
        'quiet_primary_quote_valid_rows':sd_game_means(quiet.loc[quiet.quote_valid_5s.fillna(False)])}

    # Separate equal-game levels within the paired windows and OT-status strata.
    f5 = f5p.groupby('game_id').agg(f5A=('A','mean'), ot=('is_ot_game','max'))
    retro = ref.loc[ref.is_d.astype(bool)].groupby('game_id').agg(retrospectiveA=('A','mean'),ot=('is_ot_game','max'))
    pair = f5.join(retro,lsuffix='_f5',rsuffix='_retro',how='inner')
    g4 = {'paired_games':int(len(pair)), 'overtime_games':int(pair.ot_f5.sum()),
          'non_overtime_games':int((~pair.ot_f5).sum()), 'levels':{}}
    for label, sub in [('non_overtime',pair.loc[~pair.ot_f5]),('overtime',pair.loc[pair.ot_f5])]:
        g4['levels'][label] = {}
        for col in ('retrospectiveA','f5A'):
            r = boot_mean(sub[col].to_numpy())
            g4['levels'][label][col] = {'games':int(len(sub)), 'A_pp':100*r['estimate'],
                                         'CI95_pp':[100*x for x in r['ci95']]}
    out['G4_overtime_stratified_paired_window_levels'] = g4
    contrasts = {'all_paired_games':pair, 'non_overtime':pair.loc[~pair.ot_f5],
                 'overtime':pair.loc[pair.ot_f5]}
    out['N4_N5_paired_window_contrasts_A_final5_minus_retrospective'] = {
        label:{'games':int(len(sub)), 'estimate_pp':100*float((sub.f5A-sub.retrospectiveA).mean()),
               'CI95_pp':[100*x for x in boot_mean((sub.f5A-sub.retrospectiveA).to_numpy(),seed=9142026)['ci95']]}
        for label,sub in contrasts.items()}

    # Fixed-prediction 10-cent-bin market-price remainder, equal-game.
    games_path = OUT/'phase5_crossfit_selection_diagnostic_games.csv'
    games = pd.read_csv(games_path)
    z = games.loc[(games.window_minutes == 10) & games.price_band.eq('05_20') &
                  games.coordinate.eq('price') & np.isclose(games.bin_width,.1)].copy()
    vals = z.remainder.to_numpy(float) # stored as Y - predicted selected probability
    weights = z.trades.to_numpy(float)
    ri = np.random.default_rng(FIXED_SEED).integers(0,len(vals),size=(FIXED_DRAW,len(vals)))
    fixed_equal_y_minus_q = vals[ri].mean(axis=1)
    fixed_trade_y_minus_q = ((vals*weights)[ri].sum(axis=1)/weights[ri].sum(axis=1))
    fixed_point_y_minus_q = float(np.average(vals, weights=weights))
    # Convert to A residual, predicted probability - outcome.
    out['10c_bin_market_remainder_fixed_prediction_bootstrap'] = {
        'games':int(len(z)), 'trades':int(z.trades.sum()), 'stored_coordinate':'Y - predicted selected probability',
        'reported_coordinate':'A residual = predicted selected probability - Y (sign reversed)',
        'A_trade_weighted_pp':-100*fixed_point_y_minus_q,
        'CI95_A_trade_weighted_pp':[-100*float(np.quantile(fixed_trade_y_minus_q,.975)),
                                     -100*float(np.quantile(fixed_trade_y_minus_q,.025))],
        'A_equal_game_pp':-100*float(vals.mean()),
        'CI95_A_equal_game_pp':[-100*float(np.quantile(fixed_equal_y_minus_q,.975)),
                                -100*float(np.quantile(fixed_equal_y_minus_q,.025))],
        'draws':FIXED_DRAW,'seed':FIXED_SEED,
        'note':'Fixed-prediction bootstrap resamples game-level OOF residuals and conditions on fitted predictions; trade-weighted CI is the matching counterpart to the pooled-trade refit remainder.'}

    # The saved refit estimate and both fixed-prediction Polymarket intervals.
    saved_crossfit = json.loads((ROOT/'data/interim/phase5/phase5_crossfit_selection_diagnostic.json').read_text())
    refit = saved_crossfit['coordinates']['05_20_10m_price_0.100']
    out['10c_bin_market_remainder_refit_bootstrap_saved_output'] = {
        'trades':refit['trades'],'games':refit['games'],
        'A_percentage_points':-100*refit['unexplained_remainder'],
        'CI95_A_percentage_points':[-100*refit['remainder_ci95'][1],-100*refit['remainder_ci95'][0]],
        'draws':refit['game_cluster_bootstrap_draws'],'source':'data/interim/phase5/phase5_crossfit_selection_diagnostic.json; sign reversed from stored Y - predicted probability'}
    out['N8_selection_model_10c_bin_remainder'] = {
        'trades':refit['trades'],'games':refit['games'],
        'A_percentage_points':-100*refit['unexplained_remainder'],
        'CI95_A_percentage_points':[-100*refit['remainder_ci95'][1],-100*refit['remainder_ci95'][0]],
        'draws':refit['game_cluster_bootstrap_draws'],
        'source':'saved model-refit game-cluster bootstrap output; sign reversed from stored Y - predicted probability'}
    poly_path = ROOT/'data/interim/phase2/polymarket_crossfit_selection_diagnostic_games.csv'
    poly = pd.read_csv(poly_path)
    poly = poly.loc[(poly.window_minutes == 10) & poly.price_band.eq('05_20') &
                    poly.coordinate.eq('price') & np.isclose(poly.bin_width,.05)].copy()
    pv = poly.remainder.to_numpy(float) # stored Y - predicted probability
    # Earlier fresh 2,000-draw result used the same games and fixed predictions.
    pi2 = np.random.default_rng(9142026).integers(0,len(pv),size=(2000,len(pv)))
    p2 = pv[pi2].mean(axis=1)
    paudit = json.loads((ROOT/'data/interim/phase5/phase5_selection_inference_audit.json').read_text())['polymarket']['remainder']['equal_game']['ci95_fixed_prediction_game_bootstrap']
    out['polymarket_equal_game_remainder_fixed_prediction'] = {
        'trades':int(poly.trades.sum()),'games':int(len(poly)),
        'A_percentage_points':-100*float(pv.mean()),
        'fresh_2000_draw_CI95_A_percentage_points':[-100*float(np.quantile(p2,.975)),-100*float(np.quantile(p2,.025))],
        'fresh_draws':2000,'fresh_seed':9142026,
        'saved_20000_draw_CI95_A_percentage_points':[-100*float(paudit[1]),-100*float(paudit[0])],
        'saved_draws':20000,'saved_seed':334455,
        'saved_source':'data/interim/phase5/phase5_selection_inference_audit.json; its stored Y - predicted probability interval is sign reversed to A.'}

    n9 = {}
    for stored, label in [('observed_gap','observed_A'),('predicted_gap','predicted_A'),('remainder','remainder_A')]:
        vv = -poly[stored].to_numpy(float)
        ii = np.random.default_rng(9142026).integers(0,len(vv),size=(DRAWS,len(vv)))
        n9[label] = {'estimate_pp':100*float(vv.mean()),
                     'CI95_pp':[100*float(x) for x in np.quantile(vv[ii].mean(1),[.025,.975])]}
    n9['trades']=int(poly.trades.sum());n9['games']=int(len(poly));n9['draws']=DRAWS;n9['seed']=9142026
    out['N9_polymarket_equal_game_fixed_OOF_decomposition'] = n9

    prelec = json.loads((ROOT/'data/interim/phase5/phase5a_bootstrap.json').read_text())
    fit = prelec['versions']['d_full_regular_season']
    out['Prelec_beta_saved_fit'] = {'trades':fit['trades'],'games':fit['games'],
        'raw':{'beta':fit['raw']['beta'],'CI95':fit['raw']['bootstrap']['beta_ci95']},
        'isotonic':{'beta':fit['isotonic']['beta'],'CI95':fit['isotonic']['bootstrap']['beta_ci95']},
        'draws':prelec['bootstrap_draws'],'seed':prelec['seed'],
        'source':'data/interim/phase5/phase5a_bootstrap.json; saved fits, not freshly refit in this audit'}

    OUTFILE.parent.mkdir(parents=True,exist_ok=True)
    OUTFILE.write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps(out,indent=2),flush=True)
    print(f'OUTPUT={OUTFILE}',flush=True)

if __name__ == '__main__':
    main()
