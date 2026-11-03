"""Cross-venue validation of realized-end window selection on Polymarket."""
from __future__ import annotations
import json
import sys

import numpy as np
import pandas as pd

from common import ROOT
from phase5_crossfit_selection_diagnostic import (
    PRICE_BANDS, BIN_WIDTHS, DURATIONS_MINUTES, _estimate, _oof_selected,
)
from run_polymarket_selection_analysis import (
    FILL_FILE, MAP_FILE, ASSIGN_FILE, PSTAR_FILE, PBP_DIR,
    attach_pstar, token_map,
)

OUT = ROOT / 'data/interim/phase2'


def main() -> None:
    map_doc = json.loads(MAP_FILE.read_text())
    markets = {str(m['espn_game_id']): m for m in map_doc['markets']}
    assignment = pd.read_csv(ASSIGN_FILE, dtype={'game_id':str}).set_index('game_id')
    pbp_parts=[]
    for path in PBP_DIR.glob('*.parquet'):
        z=pd.read_parquet(path, columns=['game_id','period','ts_wall_utc'])
        z['game_id']=z.game_id.astype(str)
        z['ts']=pd.to_datetime(z.ts_wall_utc,utc=True,errors='coerce')
        pbp_parts.append(z.dropna(subset=['ts']))
    pbp=pd.concat(pbp_parts,ignore_index=True)
    last=pbp.groupby('game_id').ts.max().to_dict()

    fills=pd.read_parquet(FILL_FILE,columns=[
        'espn_game_id','timestamp','asset','price','period','clock_s_remaining'])
    fills['game_id']=fills.espn_game_id.astype(str)
    fills['ts']=pd.to_datetime(pd.to_numeric(fills.timestamp,errors='coerce'),
                               unit='s',utc=True,errors='coerce')
    fills['asset']=fills.asset.astype(str)
    fills['price']=pd.to_numeric(fills.price,errors='coerce')
    fills['period']=pd.to_numeric(fills.period,errors='coerce')
    fills['clock_s_remaining']=pd.to_numeric(fills.clock_s_remaining,errors='coerce')
    fills=fills.loc[fills.ts.notna() & fills.price.between(0,1,inclusive='neither')].copy()
    fills['selected_home']=False
    fills['selected_token']=''
    fills['winner_token']=''
    fills['home_token']=''
    fills['away_token']=''
    for gid,ix in fills.groupby('game_id',sort=False).groups.items():
        market=markets.get(gid)
        if market is None or gid not in assignment.index:
            continue
        by_team=token_map(market)
        home=str(market['home_team'])
        away=str(market['away_team'])
        # token_map keys are canonical abbreviations; resolve using the same
        # canonicalizer used by the audited published Polymarket pipeline.
        from run_polymarket_selection_analysis import canonical
        h=canonical(home); a=canonical(away)
        w=canonical(market['resolved_winner_abbreviation'])
        ht,at,wt=by_team.get(h),by_team.get(a),by_team.get(w)
        if not all((ht,at,wt)):
            continue
        sh=bool(assignment.loc[gid].selected_team_is_home)
        fills.loc[ix,'selected_home']=sh
        fills.loc[ix,'selected_token']=ht if sh else at
        fills.loc[ix,'winner_token']=wt
        fills.loc[ix,'home_token']=ht
        fills.loc[ix,'away_token']=at
    valid_token=fills.asset.eq(fills.home_token) | fills.asset.eq(fills.away_token)
    fills=fills.loc[fills.selected_token.ne('') & valid_token].copy()
    fills['asset_is_selected']=fills.asset.eq(fills.selected_token)
    fills['y_own']=fills.asset.eq(fills.winner_token).astype('int8')
    fills['price']=np.where(fills.asset_is_selected,fills.price,1-fills.price)
    fills['y']=np.where(fills.asset_is_selected,fills.y_own,1-fills.y_own).astype('int8')
    fills['last_play']=fills.game_id.map(last)
    fills=fills.loc[fills.last_play.notna() & fills.ts.lt(fills.last_play) &
                    fills.period.ge(4)].copy()
    fills=attach_pstar(fills)
    fills['pstar']=np.where(fills.selected_home,fills.pstar_home,1-fills.pstar_home)
    fills['is_d']=fills.ts.ge(fills.last_play-pd.Timedelta(minutes=10))
    base=fills[['game_id','price','pstar','y','is_d','ts','last_play']].copy()
    base=base.rename(columns={'last_play':'end_ts'})

    summary={}
    game_frames=[]
    for band_name, band in PRICE_BANDS.items():
      for minutes in DURATIONS_MINUTES:
        window_base=base.copy()
        window_base['is_d']=window_base.ts.ge(
            window_base.end_ts-pd.Timedelta(minutes=minutes))
        for coord in ('price','pstar'):
            for width in BIN_WIDTHS:
                oof=_oof_selected(window_base,coord,width,band)
                summary[f'{band_name}_{minutes}m_{coord}_{width:.3f}']=_estimate(
                    oof,window_base,coord,width,band)
                t=oof.loc[oof.price.between(*band) & oof.price.between(.03,.97) &
                          oof.pstar.between(.03,.97) & oof[coord].between(.03,.97)].dropna(
                              subset=['q_base_oof','q_selected_oof'])
                t=t.assign(observed_gap=t.y-t[coord],base_gap=t.q_base_oof-t[coord],
                           predicted_gap=t.q_selected_oof-t[coord],remainder=t.y-t.q_selected_oof)
                g=t.groupby('game_id',sort=False).agg(trades=('y','size'),
                    observed_gap=('observed_gap','mean'),base_gap=('base_gap','mean'),
                    predicted_gap=('predicted_gap','mean'),remainder=('remainder','mean')).reset_index()
                g.insert(1,'window_minutes',minutes)
                g.insert(2,'price_band',band_name)
                g.insert(3,'coordinate',coord); g.insert(4,'bin_width',width)
                game_frames.append(g)
    result={'venue':'Polymarket maker fills; audited token winner mapping',
        'target_window':'5/10/15 wall minutes before last ESPN play, strictly in-game',
        'base':'all mapped Polymarket fills before last ESPN play in Q4/OT, restricted separately to each target market-price band and common market/P* support',
        'method':'Same five-fold game-held-out selection model and full game-cluster bootstrap as the Kalshi diagnostic.',
        'unique_games_in_base':int(base.game_id.nunique()),
        'mapped_base_rows':int(len(base)), 'estimates':summary}
    (OUT/'polymarket_crossfit_selection_diagnostic.json').write_text(json.dumps(result,indent=2))
    pd.concat(game_frames,ignore_index=True).to_csv(
        OUT/'polymarket_crossfit_selection_diagnostic_games.csv',index=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
