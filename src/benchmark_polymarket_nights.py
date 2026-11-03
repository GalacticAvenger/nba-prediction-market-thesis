"""Create union-by-night windows and benchmark resumable Polygon log collection."""
from __future__ import annotations
import json, os, time
from pathlib import Path
import pandas as pd
import requests
from common import ROOT, write_json
from ingest_polymarket_onchain import RPC, V1, V2, TOPICS, rpc

RAW = ROOT / 'data/raw/polymarket'
OUT = ROOT / 'data/interim/phase2'
PBP = ROOT / 'data/interim/espn_pbp/season=2026/season_type=2'

def make_plan():
    mp=json.loads((OUT/'polymarket_nba_2025_26_market_map.json').read_text())
    ids={str(m['espn_game_id']):m for m in mp['markets']}
    paths=list(PBP.glob('*.parquet'))
    pbp=pd.concat([pd.read_parquet(p,columns=['game_id','ts_wall_utc']) for p in paths],ignore_index=True)
    pbp=pbp[pbp.game_id.astype(str).isin(ids)].dropna(subset=['ts_wall_utc']).copy()
    pbp['ts']=pd.to_datetime(pbp.ts_wall_utc,utc=True).astype('int64')//10**9
    games=pbp.groupby(pbp.game_id.astype(str)).ts.agg(['min','max']).reset_index(names='game_id')
    games['night']=pd.to_datetime(games['min'],unit='s',utc=True).dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
    games['start']=games['min']-1800; games['end']=games['max']+1800
    plan=[]
    for night,g in games.groupby('night'):
        plan.append({'night':night,'start_ts':int(g.start.min()),'end_ts':int(g.end.max()),
                     'game_count':len(g),'games':g.game_id.tolist(),
                     'tokens':sorted({str(t) for gid in g.game_id for t in ids[gid]['token_ids']})})
    write_json(OUT/'polymarket_night_window_plan.json',plan)
    return plan

def block_for_ts(s, ts, latest_num, latest_ts):
    # Polygon's block cadence is ~2.1s. Search a narrow bracket then binary-search.
    guess=max(0,int(latest_num-(latest_ts-ts)/2.1))
    radius=400
    lo=max(0,guess-radius); hi=min(latest_num,guess+radius)
    while True:
        lb=rpc(s,'eth_getBlockByNumber',[hex(lo),False]); hb=rpc(s,'eth_getBlockByNumber',[hex(hi),False])
        if int(lb['timestamp'],16) <= ts <= int(hb['timestamp'],16): break
        radius*=2; lo=max(0,guess-radius); hi=min(latest_num,guess+radius)
    while lo<hi:
        mid=(lo+hi)//2
        b=rpc(s,'eth_getBlockByNumber',[hex(mid),False])
        if int(b['timestamp'],16)<ts: lo=mid+1
        else: hi=mid
    return lo

def collect_night(s, night):
    latest=rpc(s,'eth_getBlockByNumber',['latest',False]); n=int(latest['number'],16); ts=int(latest['timestamp'],16)
    a=block_for_ts(s,night['start_ts'],n,ts); b=block_for_ts(s,night['end_ts'],n,ts)
    dest=RAW/'night_logs'/night['night']; dest.mkdir(parents=True,exist_ok=True)
    reqs=0; nlogs=0; bytes_=0; t0=time.monotonic()
    for ex, topics in ((V1,[TOPICS['order_filled_v1'],TOPICS['orders_matched_v1']]),(V2,[TOPICS['order_filled_v2'],TOPICS['orders_matched_v2']])):
        # 1rpc public archive RPC enforces a strict 50-block eth_getLogs window.
        for lo in range(a,b+1,50):
            hi=min(b,lo+49); path=dest/f'{ex}_{lo}_{hi}.json'
            if path.exists():
                nlogs+=len(json.loads(path.read_text())); continue
            ans=rpc(s,'eth_getLogs',[{'address':ex,'fromBlock':hex(lo),'toBlock':hex(hi),'topics':[topics]}])
            write_json(path,ans); reqs+=1; nlogs+=len(ans); bytes_+=path.stat().st_size
    return {'night':night['night'],'games':night['game_count'],'from_block':a,'to_block':b,
            'rpc_requests':reqs,'raw_logs':nlogs,'downloaded_bytes':bytes_,
            'elapsed_seconds':round(time.monotonic()-t0,2)}

def main():
    plan=make_plan(); s=requests.Session()
    # five nights spanning season dates; include validation night and month spread.
    wanted=['2025-10-21','2025-11-15','2025-12-15','2026-01-15','2026-03-15']
    by={p['night']:p for p in plan}; chosen=[by[d] for d in wanted if d in by]
    results=[]
    for p in chosen:
        try:
            r=collect_night(s,p); results.append(r); print(json.dumps(r),flush=True)
        except Exception as e:
            results.append({'night':p['night'],'error':repr(e)}); print(json.dumps(results[-1]),flush=True)
    write_json(OUT/'polymarket_night_benchmark.json',{'selected':wanted,'results':results,'night_count':len(plan),'plan':str(OUT/'polymarket_night_window_plan.json')})

if __name__=='__main__': main()
