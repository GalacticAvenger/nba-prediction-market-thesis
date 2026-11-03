"""Compare realized-end and clock-based late-game samples within the same games.

This is a post-hoc descriptive analysis. It holds the 5-20 cent market-price
band, market/P* support, and game set fixed, then compares game-level Y-price
means in (a) the final five regulation minutes and (b) the final five or ten
wall-clock minutes before the last ESPN play. It does not identify a causal
window effect: the windows contain different trades and game states.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

PRICE_LOW, PRICE_HIGH = 0.05, 0.20
PSTAR_LOW, PSTAR_HIGH = 0.03, 0.97
BOOTSTRAP_DRAWS = 20_000
SEED = 20261103


def contrast(base: pd.DataFrame, retrospective_mask: pd.Series,
             clock_mask: pd.Series, label: str, no_overtime: bool,
             game_detail_rows: list[dict]) -> dict:
    d = base.loc[retrospective_mask].copy()
    f = base.loc[clock_mask].copy()
    gd = d.groupby('game_id', sort=True).agg(
        mean_y_minus_p=('y_minus_p', 'mean'), rows=('y_minus_p', 'size'))
    gf = f.groupby('game_id', sort=True).agg(
        mean_y_minus_p=('y_minus_p', 'mean'), rows=('y_minus_p', 'size'))
    common = gd.index.intersection(gf.index)
    gd, gf = gd.loc[common], gf.loc[common]
    delta = gf.mean_y_minus_p.to_numpy() - gd.mean_y_minus_p.to_numpy()
    if len(common) < 2:
        raise ValueError(f'Fewer than two paired games for {label}')
    game_detail_rows.extend({
        'comparison': label,
        'overtime_games_excluded': no_overtime,
        'game_id': game_id,
        'retrospective_y_minus_p_pp': float(ret * 100),
        'clock_window_y_minus_p_pp': float(clock * 100),
        'clock_minus_retrospective_pp': float(diff * 100),
    } for game_id, ret, clock, diff in zip(
        common, gd.mean_y_minus_p.to_numpy(), gf.mean_y_minus_p.to_numpy(), delta))

    rng = np.random.default_rng(SEED + (1 if no_overtime else 0) +
                                (5 if '5-minute' in label else 10))
    idx = rng.integers(0, len(common), size=(BOOTSTRAP_DRAWS, len(common)))
    draw_d = gd.mean_y_minus_p.to_numpy()[idx].mean(axis=1)
    draw_f = gf.mean_y_minus_p.to_numpy()[idx].mean(axis=1)
    draw_delta = delta[idx].mean(axis=1)
    draw_median_delta = np.median(delta[idx], axis=1)

    # Pooled rows are included to show how much the result changes when games
    # with more eligible rows receive more weight. This is descriptive only.
    common_set = set(common)
    dc = d.loc[d.game_id.isin(common_set)]
    fc = f.loc[f.game_id.isin(common_set)]
    loo = (delta.sum() - delta) / (len(delta) - 1)
    return {
        'comparison': label,
        'overtime_games_excluded': no_overtime,
        'paired_games': int(len(common)),
        'retrospective_rows': int(len(dc)),
        'clock_window_rows': int(len(fc)),
        'retrospective_game_equal_y_minus_p_pp': float(gd.mean_y_minus_p.mean() * 100),
        'retrospective_game_equal_ci95_pp': (np.quantile(draw_d, [.025, .975]) * 100).tolist(),
        'clock_window_game_equal_y_minus_p_pp': float(gf.mean_y_minus_p.mean() * 100),
        'clock_window_game_equal_ci95_pp': (np.quantile(draw_f, [.025, .975]) * 100).tolist(),
        'paired_clock_minus_retrospective_pp': float(delta.mean() * 100),
        'paired_clock_minus_retrospective_ci95_pp': (np.quantile(draw_delta, [.025, .975]) * 100).tolist(),
        'paired_difference_median_pp': float(np.median(delta) * 100),
        'paired_difference_median_ci95_pp': (np.quantile(draw_median_delta, [.025, .975]) * 100).tolist(),
        'share_games_clock_minus_retrospective_positive': float(np.mean(delta > 0)),
        'leave_one_game_out_mean_difference_range_pp': [float(loo.min() * 100), float(loo.max() * 100)],
        'retrospective_trade_weighted_y_minus_p_pp': float(dc.y_minus_p.mean() * 100),
        'clock_window_trade_weighted_y_minus_p_pp': float(fc.y_minus_p.mean() * 100),
        'bootstrap': {'cluster': 'game', 'draws': BOOTSTRAP_DRAWS,
                      'seed': SEED + (1 if no_overtime else 0) + (5 if '5-minute' in label else 10)},
        'interpretation': 'Post-hoc paired descriptive contrast; the windows contain different trades and game states, so the difference is not a causal effect of window definition.'
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', default='.',
                        help='Full thesis workspace containing src/ and cached data/')
    parser.add_argument('--output-dir', default='data/interim/phase5',
                        help='Directory for compact JSON and CSV outputs')
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    import sys
    sys.path.insert(0, str(project_root / 'src'))
    from phase5_selection_formula import build_phase5_frames
    from game_windows import is_final_regulation_window

    _, base, _ = build_phase5_frames()
    base = base.copy()
    base['ts'] = pd.to_datetime(base.ts, utc=True, errors='coerce')
    base['end_ts'] = pd.to_datetime(base.end_ts, utc=True, errors='coerce')
    base = base.loc[
        base.price.between(PRICE_LOW, PRICE_HIGH, inclusive='both') &
        base.pstar.between(PSTAR_LOW, PSTAR_HIGH, inclusive='both') &
        base.price.between(PSTAR_LOW, PSTAR_HIGH, inclusive='both')
    ].copy()
    base['y_minus_p'] = base.y - base.price
    base['clock_final5'] = [
        is_final_regulation_window(p, c, 5)
        for p, c in zip(base.period, base.clock_s_remaining)
    ]
    base['retrospective_5m'] = base.ts.ge(base.end_ts - pd.Timedelta(minutes=5))
    base['retrospective_10m'] = base.is_d.astype(bool)

    results = []
    game_detail_rows: list[dict] = []
    for excluded in (False, True):
        z = base.loc[~base.is_ot_game.astype(bool)].copy() if excluded else base
        for window, mask in [('5-minute realized-end', z.retrospective_5m),
                             ('10-minute realized-end', z.retrospective_10m)]:
            results.append(contrast(
                z, mask, z.clock_final5,
                f'{window} vs final-five regulation clock', excluded,
                game_detail_rows
            ))

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    summary = {
        'estimand': 'same-game equal-weighted difference in mean longshot Y-price across retrospective and game-clock windows',
        'price_band': [PRICE_LOW, PRICE_HIGH],
        'market_and_pstar_common_support': [PSTAR_LOW, PSTAR_HIGH],
        'windows': {
            '5-minute realized-end': 'Five wall-clock minutes before each game’s last ESPN play.',
            '10-minute realized-end': 'Ten wall-clock minutes before each game’s last ESPN play.',
            'final-five regulation clock': 'Q4 game clock from 5:00 through 0:00; overtime excluded.'
        },
        'status': 'Post-hoc descriptive paired comparison. It holds the market-price band, common-support rule, and game identity fixed, but compares different trade rows and game states. It cannot isolate a causal effect of window construction.',
        'results': results
    }
    (outdir / 'phase5_paired_window_contrast.json').write_text(
        json.dumps(summary, indent=2), encoding='utf-8')
    rows = []
    for item in results:
        rows.append({k: v for k, v in item.items() if k not in ('bootstrap', 'interpretation')})
    pd.DataFrame(rows).to_csv(outdir / 'phase5_paired_window_contrast.csv', index=False)
    details = pd.DataFrame(game_detail_rows)
    details.to_csv(outdir / 'phase5_paired_window_game_differences.csv', index=False)
    import matplotlib.pyplot as plt
    figure_dir = Path(__file__).resolve().parents[1] / 'figures' / 'phase5'
    figure_dir.mkdir(parents=True, exist_ok=True)
    plotted = [r for r in results if not r['overtime_games_excluded']]
    plotted.sort(key=lambda r: 0 if r['comparison'].startswith('5-minute') else 1)
    labels = ['Five-minute realized-end window', 'Ten-minute realized-end window']
    estimates = np.array([r['paired_clock_minus_retrospective_pp'] for r in plotted])
    intervals = np.array([r['paired_clock_minus_retrospective_ci95_pp'] for r in plotted])
    y = np.array([0.0, 0.55])
    fig, ax = plt.subplots(figsize=(7.4, 2.45))
    ax.axvline(0, color='#6B7280', linewidth=1, linestyle='--', zorder=0)
    ax.errorbar(estimates, y,
                xerr=np.vstack([estimates - intervals[:, 0], intervals[:, 1] - estimates]),
                fmt='o', color='#1F5A85', ecolor='#1F5A85', capsize=4,
                markersize=6, linewidth=1.6)
    ax.set_yticks(y, labels)
    ax.set_ylim(-0.25, 0.80)
    ax.set_xlabel('Final-five regulation mean minus realized-end mean of Y − price (pp)')
    ax.set_title('Same-game comparison of late-game windows')
    ax.grid(axis='x', color='#D9E0E8', linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.tick_params(axis='y', length=0, pad=8)
    fig.text(.5, .015,
             'Points are game-equal paired means; bars show nominal 95% game-bootstrap intervals.',
             ha='center', fontsize=8, color='#4B5563')
    fig.tight_layout(rect=(0, .07, 1, 1))
    fig.savefig(figure_dir / 'paired_window_contrast.png', dpi=200, bbox_inches='tight')
    plt.close(fig)

    # Show why the paired mean and median differ: one observation per game,
    # with the full empirical distribution and no smoothing or tail trimming.
    focal_label = '10-minute realized-end vs final-five regulation clock'
    focal = details.loc[
        details.comparison.eq(focal_label) &
        ~details.overtime_games_excluded.astype(bool),
        'clock_minus_retrospective_pp'
    ].to_numpy()
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    ax.ecdf(focal, color='#1F5A85', linewidth=2.0,
            label='One paired difference per game')
    median = float(np.median(focal))
    mean = float(np.mean(focal))
    zero_share = float(np.mean(focal <= 0))
    ax.axvline(0, color='#6B7280', linewidth=1.2, linestyle='--', label='No difference')
    ax.axvline(median, color='#3CAEA3', linewidth=1.5, linestyle=':',
               label=f'Median: {median:+.2f} pp')
    ax.axvline(mean, color='#ED553B', linewidth=1.5, linestyle='-.',
               label=f'Mean: {mean:+.2f} pp')
    ax.set_xlabel('Final-five regulation mean minus realized-end mean of Y − price (pp)')
    ax.set_ylabel('Cumulative share of matched games')
    ax.set_title('Game-level paired differences: mean versus median', loc='left')
    ax.set_ylim(0, 1)
    ax.grid(axis='both', color='#D9E0E8', linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.legend(frameon=False, loc='lower right', fontsize=8)
    ax.text(.01, .98,
            f'{len(focal)} matched games; {(1-zero_share)*100:.1f}% have a positive difference; full range shown',
            transform=ax.transAxes, va='top', ha='left', fontsize=8,
            color='#4B5563')
    fig.tight_layout()
    fig.savefig(figure_dir / 'paired_window_difference_ecdf.png', dpi=200,
                bbox_inches='tight')
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
