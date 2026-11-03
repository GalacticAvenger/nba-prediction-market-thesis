"""Out-of-game validation of a selection-only calibration adjustment.

The original formula substitutes the quoted probability p for the base-rate
P(Y=1|p). This diagnostic instead estimates the base conditional win rate and
window-selection rates on other games, then predicts the selected-window rate
for held-out games using Bayes' rule.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from common import ROOT
from phase5_selection_formula import build_phase5_frames

OUT = ROOT / 'data/interim/phase5'
SEED = 20261022
FOLDS = 5
DRAWS = 2000
PRICE_BANDS = {'05_20': (.05, .20), '10_40': (.10, .40)}
BIN_WIDTHS = (.05, .10)
DURATIONS_MINUTES = (5, 10, 15)


def _bin_id(values: np.ndarray, width: float) -> np.ndarray:
    # Fixed bins avoid selecting the binning rule using held-out outcomes.
    n_bins = int(round(1 / width))
    return np.floor(np.asarray(values, dtype=float) / width).astype(int).clip(0, n_bins - 1)


def _fold_map(game_ids: np.ndarray) -> dict[object, int]:
    unique = np.unique(game_ids)
    rng = np.random.default_rng(SEED)
    shuffled = rng.permutation(unique)
    return {g: int(i % FOLDS) for i, g in enumerate(shuffled)}


def _refit_bootstrap(base: pd.DataFrame, coord: str, bin_width: float,
                    band: tuple[float, float],
                    draws: int = DRAWS) -> dict[str, np.ndarray]:
    """Game bootstrap that re-estimates q and both selection rates per draw."""
    n_bins = int(round(1 / bin_width))
    cols = ['game_id', 'price', 'pstar', 'y', 'is_d']
    if coord not in ('price', 'pstar'):
        cols.append(coord)
    keep = (base.price.between(*band) & base.price.between(.03,.97) &
            base.pstar.between(.03,.97) & base[coord].between(.03,.97))
    d = base.loc[keep, cols].copy()
    d['bin'] = _bin_id(d[coord].to_numpy(), bin_width)
    games = np.sort(d.game_id.unique())
    gi = pd.Index(games).get_indexer(d.game_id)
    fmap = _fold_map(d.game_id.to_numpy())
    fold = np.array([fmap[g] for g in games], dtype=np.int8)
    yy = d.y.to_numpy(int)
    dd = d.is_d.to_numpy(int)
    feature = d.bin.to_numpy(int)*4 + yy*2 + dd
    base_counts = np.zeros((len(games), n_bins*4), dtype=float)
    np.add.at(base_counts, (gi, feature), 1)

    # The base already has the target market-price band and common support;
    # D selects the realized-last-play window within that base.
    m = d.is_d.to_numpy(bool)
    tg = gi[m]
    tb = d.loc[m, 'bin'].to_numpy(int)
    tn = np.zeros((len(games), n_bins), dtype=float)
    ty = np.zeros_like(tn)
    tp = np.zeros_like(tn)
    np.add.at(tn, (tg, tb), 1)
    np.add.at(ty, (tg, tb), d.loc[m, 'y'].to_numpy(float))
    np.add.at(tp, (tg, tb), d.loc[m, coord].to_numpy(float))

    rng = np.random.default_rng(SEED + 991 + (0 if coord == 'price' else 1) + int(bin_width*1000))
    W = rng.multinomial(len(games), np.full(len(games), 1/len(games)), size=draws)
    numer = {k: np.zeros(draws, dtype=float) for k in
             ['observed', 'base', 'predicted', 'remainder']}
    denominator = np.zeros(draws, dtype=float)
    for f in range(FOLDS):
        tr = fold != f
        te = fold == f
        c = (W[:, tr] @ base_counts[tr]).reshape(draws, n_bins, 2, 2)
        b0 = c[:, :, 0, :].sum(axis=2)
        b1 = c[:, :, 1, :].sum(axis=2)
        i0, i1 = c[:, :, 0, 1], c[:, :, 1, 1]
        # Jeffreys smoothing keeps sparse tail-bin bootstrap cells defined.
        q = (b1 + .5) / (b0 + b1 + 1)
        pi0 = (i0 + .5) / (b0 + 1)
        pi1 = (i1 + .5) / (b1 + 1)
        den = q*pi1+(1-q)*pi0
        qd = np.divide(q*pi1, den, out=np.full_like(q, np.nan), where=den>0)
        wt = W[:, te]
        n_te, y_te, p_te = tn[te], ty[te], tp[te]
        denominator += np.einsum('dg,gb->d', wt, n_te)
        numer['observed'] += np.einsum('dg,gb->d', wt, y_te-p_te)
        numer['base'] += np.einsum('dg,gb,db->d', wt, n_te, q) - np.einsum('dg,gb->d', wt,p_te)
        numer['predicted'] += np.einsum('dg,gb,db->d', wt, n_te, qd) - np.einsum('dg,gb->d', wt,p_te)
        numer['remainder'] += np.einsum('dg,gb->d', wt,y_te) - np.einsum('dg,gb,db->d', wt,n_te,qd)
    return {k: v/denominator for k,v in numer.items()}


def _oof_selected(base: pd.DataFrame, coord: str, bin_width: float,
                  band: tuple[float,float]) -> pd.DataFrame:
    cols = ['game_id', coord, 'y', 'is_d']
    if coord != 'price':
        cols.insert(1, 'price')
    else:
        cols.insert(1, 'pstar')
    keep = (base.price.between(*band) & base.price.between(.03,.97) &
            base.pstar.between(.03,.97) & base[coord].between(.03,.97))
    d = base.loc[keep, cols].copy()
    n_bins = int(round(1 / bin_width))
    d['bin'] = _bin_id(d[coord].to_numpy(), bin_width)
    fmap = _fold_map(d.game_id.to_numpy())
    d['fold'] = d.game_id.map(fmap).astype('int8')
    selected = []
    for fold in range(FOLDS):
        train = d.loc[d.fold.ne(fold)]
        test = d.loc[d.fold.eq(fold) & d.is_d]
        # Estimate q=P(Y=1|bin), pi1=P(D|Y=1,bin), and
        # pi0=P(D|Y=0,bin), using training games only.
        stats = train.groupby(['bin', 'y', 'is_d'], observed=True).size().unstack(
            ['y', 'is_d'], fill_value=0)
        def count(y: int, in_d: bool) -> np.ndarray:
            col = (y, in_d)
            if col not in stats.columns:
                return np.zeros(n_bins, dtype=float)
            return stats[col].reindex(range(n_bins), fill_value=0).to_numpy(float)
        b1 = count(1, False) + count(1, True)
        b0 = count(0, False) + count(0, True)
        i1, i0 = count(1, True), count(0, True)
        q = (b1 + .5) / (b1 + b0 + 1)
        pi1 = (i1 + .5) / (b1 + 1)
        pi0 = (i0 + .5) / (b0 + 1)
        den = q*pi1 + (1-q)*pi0
        q_d = np.divide(q*pi1, den, out=np.full(n_bins, np.nan), where=den>0)
        z = test.copy()
        z['q_base_oof'] = q[z.bin.to_numpy()]
        z['q_selected_oof'] = q_d[z.bin.to_numpy()]
        z['pi1_oof'] = pi1[z.bin.to_numpy()]
        z['pi0_oof'] = pi0[z.bin.to_numpy()]
        selected.append(z)
    return pd.concat(selected, ignore_index=True)


def _estimate(z: pd.DataFrame, base: pd.DataFrame, coord: str,
              bin_width: float, band: tuple[float,float], draws: int = DRAWS) -> dict:
    # Identical selected trades for the base-rate and selection-adjusted
    # predictions. The market-price band defines the target cohort.
    t = z.loc[z.price.between(*band) & z.price.between(.03,.97) &
              z.pstar.between(.03,.97) & z[coord].between(.03, .97)].copy()
    t = t.dropna(subset=['q_base_oof', 'q_selected_oof', 'pi1_oof', 'pi0_oof'])
    if t.empty:
        return {'trades': 0, 'games': 0}
    t['observed_gap'] = t.y - t[coord]
    t['base_gap'] = t.q_base_oof - t[coord]
    t['selection_predicted_gap'] = t.q_selected_oof - t[coord]
    t['remainder'] = t.y - t.q_selected_oof
    g = t.groupby('game_id', sort=False).agg(
        n=('y', 'size'), observed=('observed_gap', 'sum'),
        base=('base_gap', 'sum'), predicted=('selection_predicted_gap', 'sum'),
        remainder=('remainder', 'sum')).reset_index()
    point = {k: float(g[k].sum()/g.n.sum()) for k in
             ['observed', 'base', 'predicted', 'remainder']}
    boot = _refit_bootstrap(base, coord, bin_width, band, draws)
    cis = {k: np.nanquantile(v, [.025, .975]).tolist() for k, v in boot.items()}
    return {'trades': int(len(t)), 'games': int(t.game_id.nunique()),
            'bin_width': bin_width,
            'market_price_band': list(band),
            'observed_gap': point['observed'], 'observed_gap_ci95': cis['observed'],
            'baseline_gap_on_target_mix': point['base'], 'baseline_gap_ci95': cis['base'],
            'selection_predicted_gap': point['predicted'],
            'selection_predicted_gap_ci95': cis['predicted'],
            'unexplained_remainder': point['remainder'],
            'remainder_ci95': cis['remainder'],
            'selection_shift_from_base': point['predicted']-point['base'],
            'selection_shift_ci95': np.nanquantile(boot['predicted']-boot['base'], [.025,.975]).tolist(),
            'game_cluster_bootstrap_draws': draws,
            'successful_bootstrap_draws': min(int(np.isfinite(v).sum()) for v in boot.values()),
            'interval_note': 'game-cluster bootstrap refits conditional win rates and selection probabilities in every draw'}


def main() -> None:
    _frames, base, _weak = build_phase5_frames()
    # Vary the retrospective window length while holding the market-price
    # cohort and common support constant.
    base = base.loc[base.period.ge(4)].copy()
    outputs = {}
    aggregate = []
    for band_name, band in PRICE_BANDS.items():
      for minutes in DURATIONS_MINUTES:
        window_base = base.copy()
        window_base['is_d'] = window_base.ts.ge(
            window_base.end_ts - pd.Timedelta(minutes=minutes))
        for coord in ('price', 'pstar'):
            for width in BIN_WIDTHS:
                oof = _oof_selected(window_base, coord, width, band)
                outputs[f'{band_name}_{minutes}m_{coord}_{width:.3f}'] = _estimate(
                    oof, window_base, coord, width, band)
                t = oof.loc[oof.price.between(*band) & oof.price.between(.03,.97) &
                            oof.pstar.between(.03,.97) & oof[coord].between(.03,.97)].dropna(
                    subset=['q_base_oof','q_selected_oof'])
                t = t.assign(observed_gap=t.y-t[coord], base_gap=t.q_base_oof-t[coord],
                             predicted_gap=t.q_selected_oof-t[coord],
                             remainder=t.y-t.q_selected_oof)
                g = t.groupby('game_id', sort=False).agg(
                    trades=('y','size'), observed_gap=('observed_gap','mean'),
                    base_gap=('base_gap','mean'), predicted_gap=('predicted_gap','mean'),
                    remainder=('remainder','mean')).reset_index()
                g.insert(1, 'window_minutes', minutes)
                g.insert(2, 'price_band', band_name)
                g.insert(3, 'coordinate', coord)
                g.insert(4, 'bin_width', width)
                aggregate.append(g)
    summary = {'estimand': 'five-fold cross-fitted selection adjustment in realized-last-play windows across market-price bands',
        'market_price_bands': {k:list(v) for k,v in PRICE_BANDS.items()},
        'window_minutes_sensitivity': list(DURATIONS_MINUTES),
        'base': 'all in-game Q4/OT trades before each game last ESPN play, restricted separately to each target market-price band and common market/P* support',
        'method': 'Within fixed probability bins, estimate q=P(Y=1|p), pi1=P(D|Y=1,p), pi0=P(D|Y=0,p) on four folds of games, using Jeffreys Beta(0.5,0.5) smoothing to stabilize sparse outcome/bin cells. Predict held-out selected-window calibration as q*pi1/[q*pi1+(1-q)*pi0].',
        'why': 'The original formula substitutes p for q and therefore assumes the full base sample is calibrated. This version estimates q out of game and tests that assumption separately.',
        'folds': FOLDS, 'bin_width_sensitivity': list(BIN_WIDTHS), 'coordinates': outputs}
    (OUT/'phase5_crossfit_selection_diagnostic.json').write_text(json.dumps(summary, indent=2))
    pd.concat(aggregate, ignore_index=True).to_csv(OUT/'phase5_crossfit_selection_diagnostic_games.csv', index=False)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
