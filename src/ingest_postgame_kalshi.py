"""Cache Kalshi main-sample trades after the final ESPN play through close/settlement."""
from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests
from common import ROOT, RAW, get_json, make_session, safe_name
from ingest_kalshi import BASE

OUT=ROOT/'data/interim/phase5/post_game_trades'

def iso_epoch(v):
    t=pd.to_datetime(v,utc=True,errors='coerce',format='mixed')
    return None if pd.isna(t) else float(t.timestamp())

def fetch_one(m,last_play):
    ticker=m.ticker; start=iso_epoch(last_play)
    close=iso_epoch(m.close_time); settle=iso_epoch(m.settlement_ts)
    ends=[v for v in (close,settle) if v is not None]
    if start is None or not ends or max(ends)<=start: return ticker,[]
    end=max(ends); lo=int(start); hi=int(end)
    rows=[]; cursor=''; page=0; session=make_session()
    while True:
        params={'ticker':ticker,'min_ts':lo,'max_ts':hi,'is_block_trade':'false','limit':1000}
        if cursor: params['cursor']=cursor
        url=requests.Request('GET',f'{BASE}/historical/trades',params=params).prepare().url
        cache=RAW/'kalshi'/'trades_postgame'/safe_name(ticker)/f'{lo}_{hi}'/f'page_{page:05d}.json'
        payload=get_json(session,url,cache,min_interval=.12)
        trades=payload.get('trades',[])
        for tr in trades:
            created=tr.get('created_time')
            rows.append({'game_id':str(m.game_id),'market_ticker':ticker,'trade_id':tr.get('trade_id'),
                         'ts_utc':created,'price':float(tr['yes_price_dollars']),'count':float(tr.get('count_fp',0)),
                         'taker_side':tr.get('taker_side'),'taker_outcome_side':tr.get('taker_outcome_side'),
                         'taker_book_side':tr.get('taker_book_side'),'is_block_trade':bool(tr.get('is_block_trade',False)),
                         'settlement_result':m.result,'season':int(m.season),'season_type':int(m.season_type),
                         'post_game':True,'last_espn_play_utc':str(last_play),'market_close_time':m.close_time,
                         'settlement_ts':m.settlement_ts})
        cursor=payload.get('cursor',''); page+=1
        if not cursor: break
    return ticker,rows

def main():
    games=ROOT/'data/interim/espn_pbp/season=2026/season_type=2'
    pbp=pd.concat([pd.read_parquet(p,columns=['game_id','ts_wall_utc']) for p in games.glob('*.parquet')],ignore_index=True)
    pbp['wall']=pd.to_datetime(pbp.ts_wall_utc,utc=True,errors='coerce',format='mixed')
    last=pbp.dropna(subset=['wall']).groupby(pbp.game_id.astype(str)).wall.max().to_dict()
    meta=pd.read_parquet(ROOT/'data/interim/kalshi_market_metadata.parquet')
    meta=meta[(meta.season==2026)&(meta.season_type==2)&meta.game_id.astype(str).isin(last)].copy()
    work=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut={ex.submit(fetch_one,m,last[str(m.game_id)]):m.ticker for m in meta.itertuples(index=False)}
        done=0; total=0; markets=0
        for f in as_completed(fut):
            ticker,rows=f.result(); markets+=1; total+=len(rows); work.extend(rows); done+=1
            if done%100==0: print(f'{done}/{len(fut)} markets, {total:,} raw post-game rows',flush=True)
    out=pd.DataFrame(work)
    if len(out):
        out['ts_utc']=pd.to_datetime(out.ts_utc,utc=True,errors='coerce',format='mixed').dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        out=out.drop_duplicates(['market_ticker','trade_id']).sort_values(['game_id','ts_utc','market_ticker'])
    OUT.mkdir(parents=True,exist_ok=True)
    out.to_parquet(OUT/'post_game_trades.parquet',index=False,compression='zstd')
    out.groupby('market_ticker',as_index=False).size().to_csv(OUT/'post_game_counts_by_market.csv',index=False)
    manifest={'markets_checked':markets,'raw_postgame_rows':total,'deduplicated_rows':len(out),'games':int(out.game_id.nunique()) if len(out) else 0,'post_game_flag':True,'range':'last ESPN play through max(market close, settlement timestamp)','block_trades_requested':False,'raw_cache':'data/raw/kalshi/trades_postgame/'}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)); print(json.dumps(manifest,indent=2))
if __name__=='__main__': main()
