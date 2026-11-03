"""Selection-formula calibration and paired/robustness Prelec checks."""
from __future__ import annotations

import json
import ast
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import ROOT
from phase5a import META, PANEL, OUT, DRAWS, calibration, fit_bins, prelec, pbp_last
from game_windows import is_final_regulation_window

SEED = 7252026
MIN_GAMES_1C = 30
FIG = ROOT / 'figures' / 'phase5'
FIG.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)


def matrices(frame: pd.DataFrame, prob: str = 'price', bins: int = 100):
    """Game x one-cent sufficient statistics for a trade-weighted calibration."""
    d = frame.loc[frame[prob].gt(0) & frame[prob].lt(1), ['game_id', prob, 'y']].copy()
    d['cent'] = np.floor(d[prob].to_numpy(float) * 100 - 1e-10).astype(int)
    d = d.loc[d.cent.between(0, bins - 1)]
    g = d.groupby(['game_id', 'cent'], sort=False).agg(
        n=('y', 'size'), wins=('y', 'sum'), psum=(prob, 'sum')).reset_index()
    games = pd.Index(g.game_id.unique())
    gi = games.get_indexer(g.game_id)
    ci = g.cent.to_numpy(int)
    n = np.zeros((len(games), bins), dtype=float)
    wins = np.zeros_like(n)
    psum = np.zeros_like(n)
    n[gi, ci] = g.n.to_numpy(float)
    wins[gi, ci] = g.wins.to_numpy(float)
    psum[gi, ci] = g.psum.to_numpy(float)
    return games, n, wins, psum


def matrix_fit(n, wins, psum, target='iso', draw_weights=None):
    if draw_weights is not None:
        n = draw_weights @ n
        wins = draw_weights @ wins
        psum = draw_weights @ psum
    keep = n > 0
    b = pd.DataFrame({'cent': np.flatnonzero(keep), 'n': n[keep],
                      'p': psum[keep] / n[keep],
                      'raw_rate': wins[keep] / n[keep]})
    if b.empty:
        return None
    if target == 'iso':
        from sklearn.isotonic import IsotonicRegression
        b['iso_rate'] = IsotonicRegression(increasing=True, out_of_bounds='clip').fit_transform(
            b.p, b.raw_rate, sample_weight=b.n)
        result = fit_bins(b, 'iso_rate')
    else:
        result = fit_bins(b, 'raw_rate')
    return result


def alpha_summary(frame, pcol='price', draws=DRAWS, seed=SEED):
    d = frame[['game_id', pcol, 'y']].rename(columns={pcol: 'price'}).copy()
    # Match phase5a.summarize(): retain every non-boundary contract price.
    d = d.loc[d.price.gt(0) & d.price.lt(1)]
    if d.empty:
        return {'trades': 0, 'games': 0}
    games, n, wins, psum = matrices(d)
    base = matrix_fit(n, wins, psum, 'iso')
    rng = np.random.default_rng(seed)
    boot = []
    for start in range(0, draws, 100):
        size = min(100, draws - start)
        ws = rng.multinomial(len(games), np.full(len(games), 1 / len(games)), size=size)
        for w in ws:
            fit = matrix_fit(n, wins, psum, 'iso', w)
            if fit and fit.get('alpha') and np.isfinite(fit['alpha']):
                boot.append(fit['alpha'])
    return {'trades': int(len(d)), 'games': int(d.game_id.nunique()),
            'price_bins': int(np.sum(n.sum(axis=0) > 0)),
            'alpha': base['alpha'], 'beta': base['beta'],
            'alpha_ci95': np.quantile(boot, [.025, .975]).tolist() if boot else None,
            'successful_draws': len(boot), 'draws': draws, 'cluster': 'game',
            'fit': 'isotonic calibration; trade-count weighted Prelec-II'}


def paired_alpha(market, pstar, label, draws=DRAWS):
    """Paired game-cluster bootstrap; both fits use the same sampled games."""
    m = market[['game_id', 'price', 'y']].copy()
    s = pstar[['game_id', 'pstar', 'y']].rename(columns={'pstar': 'price'}).copy()
    m = m.loc[m.price.gt(0) & m.price.lt(1)]
    s = s.loc[s.price.gt(0) & s.price.lt(1)]
    common = np.intersect1d(m.game_id.unique(), s.game_id.unique())
    m = m.loc[m.game_id.isin(common)]; s = s.loc[s.game_id.isin(common)]
    gm, *mm = matrices(m); gs, *ss = matrices(s)
    games = pd.Index(common)
    # Reindex game x bins to the common game order so each draw is paired.
    def reorder(frame):
        g, n, w, p = matrices(frame)
        ix = g.get_indexer(games)
        return n[ix], w[ix], p[ix]
    mn, mw, mp = reorder(m); sn, sw, sp = reorder(s)
    point_m = matrix_fit(mn, mw, mp, 'iso')['alpha']
    point_s = matrix_fit(sn, sw, sp, 'iso')['alpha']
    rng = np.random.default_rng(SEED + sum(label.encode()))
    diffs = []
    for start in range(0, draws, 100):
        ws = rng.multinomial(len(games), np.full(len(games), 1 / len(games)),
                             size=min(100, draws - start))
        for w in ws:
            fm = matrix_fit(mn, mw, mp, 'iso', w)
            fs = matrix_fit(sn, sw, sp, 'iso', w)
            if fm and fs and fm.get('alpha') and fs.get('alpha'):
                diffs.append(fm['alpha'] - fs['alpha'])
    return {'window': label, 'market_alpha': point_m, 'pstar_alpha': point_s,
            'difference_market_minus_pstar': point_m - point_s,
            'ci95_difference': np.quantile(diffs, [.025, .975]).tolist(),
            'games': int(len(games)), 'draws': draws,
            'successful_draws': len(diffs), 'cluster': 'paired game bootstrap'}


def build_phase5_frames():
    meta = pd.read_parquet(META)
    meta = meta.loc[(meta.season == 2026) & meta.season_type.eq(2)].copy()
    meta['ticker'] = meta.ticker.astype(str)
    meta['result'] = meta.result.astype(str).str.lower()
    meta = meta.loc[meta.result.isin(['yes', 'no'])].set_index('ticker', drop=False)
    last = pbp_last()
    pbp_parts = []
    for f in (ROOT / 'data/interim/espn_pbp/season=2026/season_type=2').glob('*.parquet'):
        z = pd.read_parquet(f, columns=['game_id', 'period', 'clock_s_remaining', 'ts_wall_utc'])
        z['game_id'] = z.game_id.astype(str)
        z['ts'] = pd.to_datetime(z.ts_wall_utc, utc=True, errors='coerce')
        pbp_parts.append(z.dropna(subset=['ts']))
    pbp = pd.concat(pbp_parts, ignore_index=True)
    ot_games = set(pbp.loc[pbp.period.gt(4), 'game_id'])
    q4 = pbp.loc[pbp.period.eq(4) & pbp.clock_s_remaining.le(180)].sort_values('ts')
    know_start = q4.groupby('game_id', sort=False).first().ts.to_dict()
    assign = pd.read_csv(ROOT / 'data/interim/phase4/selected_team_by_game.csv',
                         dtype={'game_id': str}).set_index('game_id').selected_team_is_home.to_dict()
    weak = pd.read_csv(ROOT / 'data/interim/phase2/alignment_game_flags.csv', dtype={'game_id': str})
    weak_games = set(weak.loc[weak.weak_alignment_gt5_backward_steps.astype(bool), 'game_id'])
    frames = {w: [] for w in ['d_market', 'd_pstar', 'd_home_market', 'd_home_pstar',
                              'know_market', 'know_pstar', 'know_home_market', 'know_home_pstar',
                              'f5_market', 'f5_pstar', 'f5_home_market', 'f5_home_pstar']}
    base_chunks = []
    for ticker, m in meta.iterrows():
        f = PANEL / f'{ticker}.parquet'
        if not f.exists():
            continue
        cols = ['game_id', 'ts_utc', 'period', 'clock_s_remaining',
                'selected_contract_price', 'selected_contract_pstar',
                'pstar_with_possession', 'pstar_spline_logistic',
                'selected_team_is_home', 'ticker_yes_is_home']
        x = pd.read_parquet(f, columns=cols)
        if x.empty:
            continue
        x['game_id'] = x.game_id.astype(str)
        x['ts'] = pd.to_datetime(x.ts_utc, utc=True, errors='coerce')
        x = x.dropna(subset=['ts']).copy()
        x['period'] = pd.to_numeric(x.period, errors='coerce')
        x['clock_s_remaining'] = pd.to_numeric(x.clock_s_remaining, errors='coerce')
        x['last'] = x.game_id.map(last)
        x = x.loc[x['last'].notna() & x.ts.lt(x['last']) & x.period.ge(4)].copy()
        if x.empty:
            continue
        selected_home = x.selected_team_is_home.fillna(False).astype(bool).to_numpy()
        yes_home = x.ticker_yes_is_home.fillna(False).astype(bool).to_numpy()
        psel = pd.to_numeric(x.selected_contract_price, errors='coerce').to_numpy(float)
        sstar = pd.to_numeric(x.selected_contract_pstar, errors='coerce').to_numpy(float)
        sstar_pos = pd.to_numeric(x.pstar_with_possession, errors='coerce').to_numpy(float)
        sstar_spline = pd.to_numeric(x.pstar_spline_logistic, errors='coerce').to_numpy(float)
        p_yes = np.where(selected_home == yes_home, psel, 1 - psel)
        ps_yes = np.where(selected_home == yes_home, sstar, 1 - sstar)
        ps_pos_yes = np.where(selected_home == yes_home, sstar_pos, 1 - sstar_pos)
        ps_spline_yes = np.where(selected_home == yes_home, sstar_spline, 1 - sstar_spline)
        y_yes = np.full(len(x), int(m.result == 'yes'), dtype=np.int8)
        p_home = np.where(yes_home, p_yes, 1 - p_yes)
        ps_home = np.where(yes_home, ps_yes, 1 - ps_yes)
        y_home = np.where(yes_home, y_yes, 1 - y_yes).astype(np.int8)
        gid_num = pd.to_numeric(x.game_id, errors='coerce').fillna(-1).astype('int64').to_numpy()
        last_arr = x['last']
        dmask = x.ts.ge(last_arr - pd.Timedelta(minutes=10)).to_numpy()
        starts = x.game_id.map(know_start)
        kmask = starts.notna().to_numpy() & x.ts.ge(starts).to_numpy() & x.ts.lt(starts + pd.Timedelta(minutes=10)).to_numpy()
        f5mask = np.array([is_final_regulation_window(p, c, 5)
                           for p, c in zip(x.period, x.clock_s_remaining)])
        for key, mask, pr, yy in [
            ('d', dmask, p_yes, y_yes), ('know', kmask, p_yes, y_yes), ('f5', f5mask, p_yes, y_yes)]:
            if not mask.any():
                continue
            frames[key + '_market'].append(pd.DataFrame({'game_id': gid_num[mask], 'price': pr[mask], 'y': yy[mask]}))
            pstar_key = 'pstar' if key.endswith('_market') else 'pstar'
            frames[key + '_pstar'].append(pd.DataFrame({'game_id': gid_num[mask], 'pstar': ps_yes[mask], 'y': yy[mask]}))
            frames[key + '_home_market'].append(pd.DataFrame({'game_id': gid_num[mask], 'price': p_home[mask], 'y': y_home[mask]}))
            frames[key + '_home_pstar'].append(pd.DataFrame({'game_id': gid_num[mask], 'pstar': ps_home[mask], 'y': y_home[mask]}))
        # Selection-formula base: all regulation and OT trades strictly in-game.
        base_chunks.append(pd.DataFrame({'game_id': gid_num, 'ts': x.ts.to_numpy(),
            'end_ts': last_arr.to_numpy(), 'period': x.period.to_numpy(),
            'clock_s_remaining': x.clock_s_remaining.to_numpy(),
            'price': p_yes, 'pstar': ps_yes,
            'pstar_with_possession': ps_pos_yes,
            'pstar_spline_logistic': ps_spline_yes,
            'y': y_yes, 'is_d': dmask, 'is_know': kmask,
            'is_ot_game': x.game_id.isin(ot_games).to_numpy()}))
    result = {k: pd.concat(v, ignore_index=True) if v else pd.DataFrame() for k, v in frames.items()}
    base = pd.concat(base_chunks, ignore_index=True)
    base['weak_alignment'] = base.game_id.astype(str).isin(weak_games)
    return result, base, weak_games


def selection_formula(base, prob, no_ot=False, draws=DRAWS):
    d = base.copy()
    if no_ot:
        d = d.loc[~d.is_ot_game]
    d = d.loc[d[prob].between(.03, .97, inclusive='both')].copy()
    d['cent'] = np.floor(d[prob].to_numpy(float) * 100 - 1e-10).astype(int)
    selected = d.is_d.to_numpy(bool)
    # Sparse one-cent bins are pooled to their containing five-cent bin.
    support = d.loc[selected].groupby(['cent', 'y']).game_id.nunique().unstack(fill_value=0)
    for y in (0, 1):
        if y not in support:
            support[y] = 0
    sparse_cent = set(support.index[(support[0] < MIN_GAMES_1C) | (support[1] < MIN_GAMES_1C)])
    d['bin_key'] = [f'5c:{(c // 5) * 5:02d}' if c in sparse_cent else f'1c:{c:02d}' for c in d.cent]
    bin_keys = sorted(d.bin_key.unique(), key=lambda k: int(k.split(':')[1]))
    games = pd.Index(d.game_id.unique())
    cols = ['base0', 'base1', 'in0', 'in1', 'ps0', 'ps1', 'ips0', 'ips1']
    arr = {k: np.zeros((len(games), len(bin_keys)), dtype=float) for k in cols}
    gidx = games.get_indexer(d.game_id)
    bidx = pd.Categorical(d.bin_key, categories=bin_keys, ordered=True).codes
    yy = d.y.to_numpy(int); pp = d[prob].to_numpy(float); ins = d.is_d.to_numpy(bool)
    for y in (0, 1):
        mask = yy == y
        arr[f'base{y}'][gidx[mask], bidx[mask]] += 1
        arr[f'ps{y}'][gidx[mask], bidx[mask]] += pp[mask]
        im = mask & ins
        arr[f'in{y}'][gidx[im], bidx[im]] += 1
        arr[f'ips{y}'][gidx[im], bidx[im]] += pp[im]
    rng = np.random.default_rng(SEED + (17 if no_ot else 0) + (1 if prob == 'pstar' else 0))
    ws = rng.multinomial(len(games), np.full(len(games), 1 / len(games)), size=draws)
    records = []
    pred_alpha = []
    pred_beta = []
    for draw_i in range(draws + 1):
        w = None if draw_i == 0 else ws[draw_i - 1]
        vals = {k: (v.sum(axis=0) if w is None else w @ v) for k, v in arr.items()}
        b0, b1, i0, i1 = (vals[x] for x in ('base0', 'base1', 'in0', 'in1'))
        ps0, ps1, ips0, ips1 = (vals[x] for x in ('ps0', 'ps1', 'ips0', 'ips1'))
        p_sum = ips0 + ips1
        pbar = np.divide(p_sum, i0 + i1, out=np.zeros_like(p_sum), where=(i0 + i1) > 0)
        pi0 = np.divide(i0, b0, out=np.zeros_like(i0), where=b0 > 0)
        pi1 = np.divide(i1, b1, out=np.zeros_like(i1), where=b1 > 0)
        c = np.divide(pbar * pi1, pbar * pi1 + (1 - pbar) * pi0,
                      out=np.full_like(pbar, np.nan), where=(pbar * pi1 + (1 - pbar) * pi0) > 0)
        obs = np.divide(i1, i0 + i1, out=np.full_like(i1, np.nan), where=(i0 + i1) > 0)
        fit_frame = pd.DataFrame({'cent': np.arange(len(bin_keys)), 'p': pbar,
                                  'n': i0 + i1, 'pred': c})
        fit_frame = fit_frame.loc[fit_frame.n.gt(0) & fit_frame.p.gt(0) & fit_frame.p.lt(1)]
        fit = fit_bins(fit_frame, 'pred') if len(fit_frame) >= 3 else {}
        if draw_i == 0:
            for j, key in enumerate(bin_keys):
                if i0[j] + i1[j] == 0:
                    continue
                records.append({'bin': key, 'mean_price': pbar[j], 'pi0': pi0[j], 'pi1': pi1[j],
                    'predicted_calibration': c[j], 'observed_calibration': obs[j],
                    'base_trades_y0': b0[j], 'base_trades_y1': b1[j],
                    'window_trades_y0': i0[j], 'window_trades_y1': i1[j],
                    'base_games': int(np.sum((arr['base0'][:, j] + arr['base1'][:, j]) > 0)),
                    'window_games_y0': int(np.sum(arr['in0'][:, j] > 0)),
                    'window_games_y1': int(np.sum(arr['in1'][:, j] > 0)), '_bin_index': j})
            base_fit = fit
        else:
            for j, key in enumerate(bin_keys):
                rec = next((r for r in records if r['_bin_index'] == j), None)
                if rec is not None:
                    # Store aligned bands by bin position.
                    if np.isfinite(c[j]) and np.isfinite(obs[j]):
                        rec['_pred_boot'] = rec.get('_pred_boot', []) + [float(c[j])]
                        rec['_obs_boot'] = rec.get('_obs_boot', []) + [float(obs[j])]
            if fit.get('alpha') is not None:
                pred_alpha.append(fit['alpha']); pred_beta.append(fit['beta'])
    for row in records:
        pb = row.pop('_pred_boot', []); ob = row.pop('_obs_boot', [])
        row.pop('_bin_index', None)
        row['predicted_ci95'] = np.nanquantile(pb, [.025, .975]).tolist() if pb else None
        row['observed_ci95'] = np.nanquantile(ob, [.025, .975]).tolist() if ob else None
    return records, {'alpha': base_fit.get('alpha'), 'beta': base_fit.get('beta'),
        'alpha_ci95': np.quantile(pred_alpha, [.025, .975]).tolist() if pred_alpha else None,
        'beta_ci95': np.quantile(pred_beta, [.025, .975]).tolist() if pred_beta else None,
        'trades_base': int(len(d)), 'trades_window': int(d.is_d.sum()),
        'games_base': int(d.game_id.nunique()), 'games_window': int(d.loc[d.is_d, 'game_id'].nunique()),
        'draws': draws, 'successful_fit_draws': len(pred_alpha), 'minimum_games_1c': MIN_GAMES_1C,
        'cluster': 'game', 'fit_target': 'predicted selection-formula calibration curve'}


def main():
    frames, base, weak = build_phase5_frames()
    # Paired alpha differences on identical approved trade samples and resamples.
    pairs = []
    for label, mk, pk in [('(d)', 'd_m', 'd_s'), ('(d) excl. OT', 'd_noot_m', 'd_noot_s'),
                          ('Knowable', 'know_m', 'know_s'), ('Final 5', 'f5cal', 'f5cal')]:
        if label == '(d) excl. OT':
            m = frames['d_market'].copy(); p = frames['d_pstar'].copy()
            # OT game exclusion uses game ids present in overtime in the base panel.
            ot_ids = set(base.loc[base.is_ot_game, 'game_id'].unique())
            m = m.loc[~m.game_id.isin(ot_ids)]; p = p.loc[~p.game_id.isin(ot_ids)]
        elif label == 'Final 5':
            m = frames['f5_market'].rename(columns={'price':'price'})
            p = frames['f5_pstar'].rename(columns={'pstar':'price'})
        else:
            m = frames['d_market' if label == '(d)' else 'know_market']
            p = frames['d_pstar' if label == '(d)' else 'know_pstar']
        # paired_alpha expects a market price and a pstar column.
        p = p.rename(columns={'price':'pstar'}) if 'price' in p.columns else p
        pairs.append(paired_alpha(m, p, label))
    # Headline fit robustness: remove weak-alignment games; transform to home-team contract.
    robust = []
    for label, mkey, pkey in [('(d)', 'd_market', 'd_pstar'), ('Knowable', 'know_market', 'know_pstar'),
                              ('Final 5', 'f5_market', 'f5_pstar')]:
        for sample_label, exclude_weak, home in [('Main convention', False, False),
                                                  ('Excluding weak alignment', True, False),
                                                  ('Home-team convention', False, True)]:
            for src, key in [('Market', mkey), ('P*', pkey)]:
                name = key.replace('market','home_market').replace('pstar','home_pstar') if home else key
                df = frames[name].copy()
                if exclude_weak:
                    df = df.loc[~df.game_id.astype(str).isin(weak)]
                pcol = 'price' if src == 'Market' else 'pstar'
                fit = alpha_summary(df, pcol=pcol, seed=SEED + len(robust))
                robust.append({'window': label, 'source': src, 'specification': sample_label, **fit})
    # Selection formula (regular season final regulation + OT base population).
    selection = {}; selection_rows = []
    for spec, no_ot in [('(d)', False), ('(d) excluding OT', True)]:
        for coord in ('price', 'pstar'):
            rows, fit = selection_formula(base, coord, no_ot=no_ot)
            selection[f'{spec}_{coord}'] = fit
            for row in rows:
                selection_rows.append({'window': spec, 'coordinate': coord, **row})
    pd.DataFrame(selection_rows).to_csv(OUT / 'phase5_selection_formula_bins.csv', index=False)
    (OUT / 'phase5_selection_formula.json').write_text(json.dumps(selection, indent=2))
    pd.DataFrame(pairs).to_csv(OUT / 'phase5_paired_alpha_differences.csv', index=False)
    (OUT / 'phase5_paired_alpha_differences.json').write_text(json.dumps(pairs, indent=2))
    pd.DataFrame(robust).to_csv(OUT / 'phase5_alpha_robustness.csv', index=False)
    (OUT / 'phase5_alpha_robustness.json').write_text(json.dumps(robust, indent=2))
    plot_selection(pd.DataFrame(selection_rows))
    print(json.dumps({'selection_formula': selection, 'paired_differences': pairs,
                      'alpha_robustness': robust}, indent=2))


def plot_selection(df):
    # Overtime-excluded estimates condition on an outcome-dependent event and
    # are retained only in the archived diagnostic data, not thesis figures.
    df = df.loc[df.window.eq('(d)')]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.8), sharex=False, sharey=False)
    styles = {'predicted_calibration': ('#2369a1', 'Selection-formula prediction'),
              'observed_calibration': ('#c44e52', 'Observed in-window calibration')}
    for i, (window, coord) in enumerate([('(d)', 'price'), ('(d)', 'pstar')]):
        ax = axes[i]
        sub = df.loc[df.window.eq(window) & df.coordinate.eq(coord)].copy()
        sub['x'] = sub.mean_price
        for col, (color, label) in styles.items():
            sub = sub.sort_values('x')
            y = sub[col].to_numpy(float)
            ci_col = f'{col.replace("calibration", "ci95")}'
            ci_values = [ast.literal_eval(v) if isinstance(v, str) else v
                         for v in sub[ci_col].tolist()]
            ci = np.array(ci_values, dtype=float)
            ax.plot(sub.x, y, marker='o', ms=3, lw=1.5, color=color, label=label)
            if ci.size and ci.ndim == 2:
                ax.fill_between(sub.x, ci[:, 0], ci[:, 1], color=color, alpha=.15, linewidth=0)
        lo = max(.03, float(sub.x.min()) if len(sub) else .03); hi = min(.97, float(sub.x.max()) if len(sub) else .97)
        ax.plot([lo, hi], [lo, hi], color='.35', ls='--', lw=1, label='45°')
        ax.set_title(f'{window} · {"market price" if coord == "price" else "P*"}')
        ax.set_xlabel('Mean probability in bin'); ax.set_ylabel('Win frequency')
        ax.set_xlim(lo, hi); ax.set_ylim(0, 1)
        if i == 0: ax.legend(frameon=False, loc='best')
    fig.suptitle('Selection-formula prediction and observed calibration', y=.99, fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / 'selection_formula_calibration.png', bbox_inches='tight')
    fig.savefig(FIG / 'selection_formula_calibration.pdf', bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    main()
