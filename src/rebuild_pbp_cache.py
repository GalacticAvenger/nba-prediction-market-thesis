"""Rebuild interim ESPN PBP parquet from cached summary JSON (no network requests)."""
import json
from pathlib import Path
import pandas as pd
import pyarrow as pa, pyarrow.parquet as pq
from ingest_pbp import play_records
from common import ROOT
I=ROOT/'data/interim'; RAW=ROOT/'data/raw/espn/summaries'

def main():
    games=pd.read_parquet(I/'espn_games.parquet').copy(); games['espn_game_id']=games.espn_game_id.astype(str)
    gmap={r.espn_game_id:r._asdict() for r in games.itertuples(index=False)}
    updated=0; missing=[]
    for path in sorted((I/'espn_pbp').glob('season=*/season_type=*/*.parquet')):
        old=pd.read_parquet(path); ids=list(old.game_id.astype(str).drop_duplicates()); rows=[]
        for gid in ids:
            payload_path=RAW/f'{gid}.json'
            if not payload_path.exists(): missing.append(gid); continue
            payload=json.loads(payload_path.read_text())
            game=gmap.get(gid)
            if not game: continue
            # Convert namedtuple dict's fields back to the keys play_records expects.
            game={'espn_game_id':gid,'season':int(game['season']),'season_type':int(game['season_type'])}
            has_wall=any(play.get('wallclock') for play in payload.get('plays',[]))
            rows.extend(play_records(game,payload,include_wallclock=(game['season']==2026 and has_wall)))
        if rows:
            pq.write_table(pa.Table.from_pylist(rows),path,compression='zstd'); updated+=len(rows)
    print(json.dumps({'parquet_files_rebuilt':len(list((I/'espn_pbp').glob('season=*/season_type=*/*.parquet'))),'action_rows':updated,'missing_cached_summaries':sorted(set(missing))},indent=2))
if __name__=='__main__': main()
