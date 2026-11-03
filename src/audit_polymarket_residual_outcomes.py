"""Audit longshot-side Polymarket/Kalshi outcomes on matched game-minutes."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/interim/phase5'
KEYS = ['window', 'band', 'game_id', 'period', 'minute_bin']
BANDS = [('0.05–0.20', .05, .20), ('0.10–0.40', .10, .40)]


def main():
    sys.path.insert(0, str(ROOT / 'src'))
    import phase5_residual_mechanisms as base

    matched = pd.read_parquet(OUT / 'phase5_residual_minute_venue_cells.parquet')
    matched = matched.loc[matched['sample'].eq('matched'), KEYS].drop_duplicates()
    kal = pd.read_parquet(OUT / 'phase5_residual_mechanisms_kalshi_cache.parquet')
    kal['minute_bin'] = (pd.to_numeric(kal.clock_s_remaining, errors='coerce') / 60).apply(
        lambda x: int(-(-x // 1)) if pd.notna(x) else pd.NA).astype('Int64')
    # Reverse the already-folded Kalshi outcome to the selected-team coordinate.
    assign = pd.read_csv(ROOT / 'data/interim/phase4/selected_team_by_game.csv',
                         dtype={'game_id': str}).set_index('game_id')
    games = pd.read_parquet(ROOT / 'data/interim/espn_games.parquet')
    games['game_id'] = games.espn_game_id.astype(str)
    teams = games.set_index('game_id')[['home_abbreviation', 'away_abbreviation']]
    kal['game_id'] = kal.game_id.astype(str)
    kal['selected_team'] = [str(assign.loc[g].selected_team_abbreviation) for g in kal.game_id]
    kal['other_team'] = [str(teams.loc[g].away_abbreviation if bool(assign.loc[g].selected_team_is_home)
                             else teams.loc[g].home_abbreviation) for g in kal.game_id]
    kal['y_selected'] = [int(y) if float(p) <= .5 else 1-int(y) for y, p in zip(
        kal.y, pd.to_numeric(kal.p_selected, errors='coerce'))]
    kal['venue'] = 'Kalshi'

    pbp, starts, _ = base.load_pbp()
    poly, _, _ = base.load_polymarket(pbp, starts)
    poly['minute_bin'] = (pd.to_numeric(poly.game_clock_remaining, errors='coerce') / 60).apply(
        lambda x: int(-(-x // 1)) if pd.notna(x) else pd.NA).astype('Int64')
    poly['selected_team'] = [str(assign.loc[str(g)].selected_team_abbreviation)
                             for g in poly.game_id]
    poly['other_team'] = [str(teams.loc[str(g)].away_abbreviation
                             if bool(assign.loc[str(g)].selected_team_is_home)
                             else teams.loc[str(g)].home_abbreviation) for g in poly.game_id]
    poly['venue'] = 'Polymarket'
    poly['ts'] = pd.to_datetime(poly.timestamp, unit='s', utc=True)
    poly['clock_s_remaining'] = pd.to_numeric(poly.game_clock_remaining, errors='coerce')
    poly[['game_id','window','period','clock_s_remaining','ts','price','p_selected',
          'y_selected','y','y_minus_price','maker_side_folded']].to_parquet(
              OUT / 'phase5_residual_polymarket_audited_cache.parquet', index=False)

    out = []
    for window in ('Knowable', 'Final 5'):
        for label, lo, hi in BANDS:
            keys = matched.loc[matched.window.eq(window) & matched.band.eq(label)]
            venue_rows = []
            for source, frame, price_col in (
                ('Kalshi', kal, 'price'), ('Polymarket', poly, 'price')):
                z = frame.loc[frame.window.eq(window) &
                              pd.to_numeric(frame[price_col], errors='coerce').between(lo, hi, inclusive='both')]
                z = z.copy()
                z['band'] = label
                z = z.merge(keys, on=KEYS, how='inner', validate='many_to_one')
                z['row_longshot_is_selected'] = pd.to_numeric(z.p_selected, errors='coerce').le(.5)
                z['row_longshot_team'] = [str(s) if bool(q) else str(o) for s, o, q in zip(
                    z.game_id.map(assign.selected_team_abbreviation.astype(str)),
                    z.game_id.map({g: str(teams.loc[g].away_abbreviation)
                                   if bool(assign.loc[g].selected_team_is_home)
                                   else str(teams.loc[g].home_abbreviation) for g in z.game_id.astype(str).unique()}),
                    z.row_longshot_is_selected)]
                # Establish which team is the longshot from the median selected-
                # team coordinate in that venue/game-minute, then fold Y to that
                # same side. This avoids assigning one team per individual fill
                # when the market crosses 0.50 within the minute.
                agg = (z.groupby(KEYS, sort=False)
                       .agg(p_selected=('p_selected', 'median'),
                            y_selected=('y_selected', 'first'),
                            unique_selected_y=('y_selected', 'nunique'),
                            intraminute_longshot_teams=('row_longshot_team', 'nunique')).reset_index())
                if agg.unique_selected_y.gt(1).any():
                    raise AssertionError(f'{source} selected-team outcome varies within a game')
                agg['longshot_is_selected'] = agg.p_selected.le(.5)
                agg['other_team'] = [str(teams.loc[str(g)].away_abbreviation
                                         if bool(assign.loc[str(g)].selected_team_is_home)
                                         else teams.loc[str(g)].home_abbreviation)
                                     for g in agg.game_id]
                agg['longshot_team'] = [str(s) if bool(q) else str(o) for s,o,q in zip(
                    agg.game_id.map(assign.selected_team_abbreviation.astype(str)),
                    agg.other_team, agg.longshot_is_selected)]
                agg['y'] = [int(y) if bool(q) else 1-int(y) for y,q in zip(
                    agg.y_selected, agg.longshot_is_selected)]
                agg = agg.rename(columns={'longshot_team': f'{source}_longshot_team',
                                          'y': f'{source}_Y'})
                agg = agg.rename(columns={'intraminute_longshot_teams':
                                          f'{source}_intraminute_longshot_teams'})
                venue_rows.append(agg[KEYS + [f'{source}_longshot_team', f'{source}_Y',
                                              f'{source}_intraminute_longshot_teams']])
            pair = venue_rows[0].merge(venue_rows[1], on=KEYS, how='inner', validate='one_to_one')
            pair['selected_team'] = pair.game_id.map(assign.selected_team_abbreviation.astype(str))
            pair['Y_mismatch'] = pair.Kalshi_Y.astype(int).ne(pair.Polymarket_Y.astype(int))
            pair['longshot_team_mismatch'] = pair.Kalshi_longshot_team.ne(pair.Polymarket_longshot_team)
            out.append(pair)
    audit = pd.concat(out, ignore_index=True)
    cols = ['window', 'band', 'game_id', 'selected_team', 'Kalshi_longshot_team',
            'Polymarket_longshot_team', 'Kalshi_Y', 'Polymarket_Y',
            'Y_mismatch', 'longshot_team_mismatch', 'Kalshi_intraminute_longshot_teams',
            'Polymarket_intraminute_longshot_teams', 'period', 'minute_bin']
    audit = audit[cols]
    audit.to_csv(OUT / 'phase5_residual_outcome_mismatch_audit.csv', index=False)
    summary = {
        'matched_window_band_game_minutes': int(len(audit)),
        'distinct_games': int(audit.game_id.nunique()),
        'Y_mismatches': int(audit.Y_mismatch.sum()),
        'different_longshot_team_rows': int(audit.longshot_team_mismatch.sum()),
        'same_longshot_team_Y_mismatches': int((audit.Y_mismatch & ~audit.longshot_team_mismatch).sum()),
        'mismatch_games': int(audit.loc[audit.Y_mismatch, 'game_id'].nunique()),
        'Kalshi_minutes_with_intraminute_longshot_side_switch': int(audit.Kalshi_intraminute_longshot_teams.gt(1).sum()),
        'Polymarket_minutes_with_intraminute_longshot_side_switch': int(audit.Polymarket_intraminute_longshot_teams.gt(1).sum()),
        'mismatch_rows': audit.loc[audit.Y_mismatch].to_dict('records'),
        'outcome_source': 'resolved Gamma outcome label -> CLOB token id -> fill asset; TEAM_ALIASES canonical team mapping',
        'longshot_fold': 'within each matched venue/game-minute, use median selected-team price; complement selected-team outcome iff that median price > 0.5',
    }
    (OUT / 'phase5_residual_outcome_mismatch_audit.json').write_text(
        __import__('json').dumps(summary, indent=2, default=str))
    print(__import__('json').dumps({k: v for k, v in summary.items() if k != 'mismatch_rows'}, indent=2))
    print(audit.loc[audit.Y_mismatch].to_string(index=False))


if __name__ == '__main__':
    main()
