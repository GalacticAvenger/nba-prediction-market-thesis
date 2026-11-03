"""Diagnostic only: Kalshi scoring-team price movement before ESPN made-field-goal timestamps."""
import glob,json,re
from pathlib import Path
import numpy as np,pandas as pd
from common import ROOT
I=ROOT/'data/interim'; O=I/'phase2'

def main():
    games=pd.read_parquet(I/'espn_games.parquet'); games=games[(games.season==2026)&(games.season_type==2)]
    team_map={}
    for r in games.itertuples(): team_map[str(r.espn_game_id)]={str(r.home_team_id):str(r.home_abbreviation),str(r.away_team_id):str(r.away_abbreviation)}
    f=glob.glob(str(I/'espn_pbp/season=2026/season_type=2/*.parquet')); p=pd.concat([pd.read_parquet(x) for x in f],ignore_index=True)
    p=p[(p.ts_wall_utc.notna())&(p.game_id.astype(str)!='401809839')].copy()
    txt=p.text.fillna('').str.lower(); typ=p.action_type.fillna('').str.lower()
    p=p[txt.str.contains(r'\bmakes\b',regex=True)&~typ.str.contains('free throw')&~txt.str.contains('free throw')]
    p['team']=p.team.astype(str); p['t_ns']=pd.to_datetime(p.ts_wall_utc,utc=True).astype('int64')
    p['abbr']=[team_map.get(str(g),{}).get(str(t)) for g,t in zip(p.game_id,p.team)]
    events=p.dropna(subset=['abbr']).copy()
    event_groups={str(g):d for g,d in events.groupby('game_id')}
    obs=[]
    for fn in glob.glob(str(I/'kalshi_trades/*.parquet')):
        try: d=pd.read_parquet(fn,columns=['game_id','market_ticker','ts_utc','price','is_block_trade'])
        except: continue
        if d.empty: continue
        gid=str(d.game_id.iloc[0]); ev=event_groups.get(gid)
        if ev is None: continue
        d=d[~d.is_block_trade.fillna(False)]
        if d.empty: continue
        tick=str(d.market_ticker.iloc[0]); abbr=tick.rsplit('-',1)[-1]
        ev=ev[ev.abbr==abbr]
        if len(ev)==0: continue
        d=d.sort_values('ts_utc').copy(); tns=pd.to_datetime(d.ts_utc,utc=True,format='mixed').astype('int64').to_numpy(); prices=d.price.astype(float).to_numpy()
        for e in ev.itertuples():
            t=int(e.t_ns); before=np.searchsorted(tns,t,side='left'); baseix=np.searchsorted(tns,t-10_000_000_000,side='right')-1
            if before==0 or baseix<0: continue
            start=baseix+1; stop=before
            if stop<=start: continue
            changed=np.flatnonzero(np.abs(prices[start:stop]-prices[baseix])>=0.005)
            if not len(changed):
                obs.append({'game_id':gid,'lead_seconds':0,'abs_move':abs(prices[stop-1]-prices[baseix]),'move_before':False})
            else:
                first=start+int(changed[0]); obs.append({'game_id':gid,'lead_seconds':(t-tns[first])/1e9,'abs_move':abs(prices[stop-1]-prices[baseix]),'move_before':True})
    out=pd.DataFrame(obs)
    if len(out):
        moved=out[out.move_before]
        result={'definition':'Scoring-team YES price. Compare latest trade in [ESPN wallclock-10s, ESPN wallclock) to prior trade at/before -10s; a movement is >=0.5 cent at any time in the pre-event interval. Diagnostic only; no alignment offset is estimated or applied.',
           'matched_made_field_goals':int(len(out)),'with_pre_timestamp_price_movement':int(len(moved)),'share_with_pre_timestamp_movement':float(len(moved)/len(out)),
           'lead_seconds_median_among_movers':float(moved.lead_seconds.median()) if len(moved) else None,'lead_seconds_p90':float(moved.lead_seconds.quantile(.9)) if len(moved) else None,
           'abs_price_move_median_all':float(out.abs_move.median()),'abs_price_move_median_movers':float(moved.abs_move.median()) if len(moved) else None,
           'abs_price_move_mean_movers':float(moved.abs_move.mean()) if len(moved) else None}
    else: result={'matched_made_field_goals':0}
    (O/'kalshi_made_shot_lead.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
if __name__=='__main__': main()
