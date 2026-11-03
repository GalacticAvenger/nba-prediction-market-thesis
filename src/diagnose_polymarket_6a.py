"""Reproduce Phase 6a outcome, mapping, price, and maker-price diagnostics."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
import run_polymarket_6a_season as cal
from common import ROOT, write_json

OUT = ROOT / 'data/interim/phase2'
MAP = json.loads((OUT/'polymarket_nba_2025_26_market_map.json').read_text())
MARKETS = {str(m['espn_game_id']):m for m in MAP['markets']}
ASSIGN = pd.read_csv(ROOT/'data/interim/phase4/selected_team_by_game.csv', dtype={'game_id':str}).set_index('game_id')

def canon(x):
    x=str(x)
    return cal.TEAM_ALIASES.get(x, x.lower())

def selected_token(m, abbr):
    canonical=canon(abbr); aliases={cal.norm(abbr),cal.norm(canonical)}
    for t in m['gamma_event'].get('teams',[]):
        if cal.norm(t.get('abbreviation','')) == cal.norm(canonical):
            aliases.update(cal.norm(t.get(k,'')) for k in ('name','alias','abbreviation'))
    gm=next(x for x in m['gamma_event']['markets'] if str(x.get('conditionId','')).lower()==str(m['condition_id']).lower())
    outcomes=json.loads(gm['outcomes']); tokens=json.loads(gm['clobTokenIds'])
    hit=next((tok for tok,outcome in zip(tokens,outcomes) if cal.norm(outcome) in aliases),None)
    return hit, outcomes, tokens

# Outcome audit: 903 6a games; compare previous literal-abbreviation result and
# corrected result to Kalshi's same game/team Y in its main late-trade panel.
season=pd.read_parquet(OUT/'polymarket_6a_lite_season_maker_fills.parquet')
gids=season.espn_game_id.astype(str).unique()
kal=pd.read_parquet(ROOT/'data/interim/phase5/phase5_late_trades.parquet',columns=['game_id','y_selected','selected_team_is_home'])
kal.game_id=kal.game_id.astype(str)
ky=kal.groupby('game_id').agg(kalshi_y=('y_selected','first'),kalshi_y_n=('y_selected','nunique'),kalshi_home=('selected_team_is_home','first')).reset_index().set_index('game_id')
outcomes=[]
for gid in gids:
    m=MARKETS[gid]; a=ASSIGN.loc[gid]; selected=str(a.selected_team_abbreviation); resolved=str(m['resolved_winner_abbreviation'])
    old=int(resolved==selected); new=int(canon(resolved)==canon(selected))
    k=ky.loc[gid]
    outcomes.append({'game_id':gid,'slug':m['slug'],'selected_team':selected,'selected_team_id':str(a.selected_team_id),
                     'resolved_abbreviation':resolved,'legacy_y':old,'corrected_y':new,'kalshi_y':int(k.kalshi_y),
                     'legacy_mismatch':old!=int(k.kalshi_y),'corrected_mismatch':new!=int(k.kalshi_y)})
od=pd.DataFrame(outcomes).sort_values(['game_id'])
od.to_csv(OUT/'polymarket_6a_outcome_audit.csv',index=False)
# Selected-team win rates, after alias correction.
winrates=od.groupby(['selected_team','selected_team_id']).corrected_y.agg(games='size',wins='sum',win_rate='mean').reset_index().sort_values('selected_team')
winrates.to_csv(OUT/'polymarket_6a_team_win_rates.csv',index=False)
# Outcome label and every historical/standard abbreviation to ESPN team id.
schedule=pd.read_parquet(ROOT/'data/interim/espn_games.parquet'); schedule['gid']=schedule.espn_game_id.astype(str); sched=schedule.set_index('gid')
teammap={}
for m in MAP['markets']:
    gid=str(m['espn_game_id'])
    if gid not in sched.index: continue
    g=sched.loc[gid]
    for abbr,tid,name in [(g.home_abbreviation,g.home_team_id,g.home_team),(g.away_abbreviation,g.away_team_id,g.away_team)]:
        key=canon(abbr)
        for t in m['gamma_event'].get('teams',[]):
            if cal.norm(t.get('abbreviation',''))==cal.norm(key):
                record={'polymarket_outcome_name':t.get('name'),'polymarket_abbreviation':t.get('abbreviation'),
                        'espn_abbreviation':abbr,'espn_team_id':str(tid),'espn_team_name':name}
                teammap[record['polymarket_abbreviation']]=record
teams=pd.DataFrame(teammap.values()).sort_values('polymarket_abbreviation')
teams.to_csv(OUT/'polymarket_6a_team_mapping.csv',index=False)
# Polymarket selected-token vs Kalshi selected-team price by regulation minute.
pm=pd.read_parquet(OUT/'polymarket_maker_fills_season_raw.parquet')
pm['espn_game_id']=pm.espn_game_id.astype(str); pm['period']=pd.to_numeric(pm.period,errors='coerce'); pm['clock_s_remaining']=pd.to_numeric(pm.clock_s_remaining,errors='coerce'); pm['price']=pd.to_numeric(pm.price,errors='coerce')
pmrows=[]
for slug,part in pm[(pm.period==4)&pm.clock_s_remaining.between(0,600)].groupby('slug',sort=False):
    m=next((x for x in MAP['markets'] if x['slug']==slug),None)
    if m is None: continue
    gid=str(m['espn_game_id'])
    if gid not in ASSIGN.index or gid not in set(gids): continue
    tok,_,_=selected_token(m,str(ASSIGN.loc[gid].selected_team_abbreviation))
    if tok is None: continue
    part=part.copy(); part['selected_price']=np.where(part.asset.astype(str)==str(tok),part.price,1-part.price)
    part=part[part.selected_price.between(0,1)].copy()
    part['clock_minute_remaining']=np.floor(part.clock_s_remaining/60).astype(int)
    pmrows.append(part[['espn_game_id','clock_minute_remaining','selected_price']])
poly=pd.concat(pmrows,ignore_index=True).groupby(['espn_game_id','clock_minute_remaining']).selected_price.median().rename('polymarket_median')
kalrows=[]
alias={'GS':'GSW','NO':'NOP','NY':'NYK','SA':'SAS','UTAH':'UTA','WSH':'WAS'}
for f in (ROOT/'data/interim/phase4/trade_panel').glob('*.parquet'):
    d=pd.read_parquet(f,columns=['game_id','period','clock_s_remaining','selected_contract_price'])
    if d.empty: continue
    gid=str(int(d.game_id.iloc[0]))
    if gid not in ASSIGN.index or gid not in set(gids): continue
    expected=alias.get(str(ASSIGN.loc[gid].selected_team_abbreviation),str(ASSIGN.loc[gid].selected_team_abbreviation))
    # Phase 4 stores a separate contract panel per team; retain only selected team ticker.
    if not f.stem.endswith('-'+expected): continue
    d['period']=pd.to_numeric(d.period,errors='coerce');d['clock_s_remaining']=pd.to_numeric(d.clock_s_remaining,errors='coerce');d['selected_contract_price']=pd.to_numeric(d.selected_contract_price,errors='coerce')
    d=d[(d.period==4)&d.clock_s_remaining.between(0,600)&d.selected_contract_price.between(0,1)].copy()
    d['clock_minute_remaining']=np.floor(d.clock_s_remaining/60).astype(int);d['espn_game_id']=gid
    kalrows.append(d[['espn_game_id','clock_minute_remaining','selected_contract_price']].rename(columns={'selected_contract_price':'kalshi_median'}))
kalp=pd.concat(kalrows,ignore_index=True).groupby(['espn_game_id','clock_minute_remaining']).kalshi_median.median().rename('kalshi_median')
price=pd.concat([poly,kalp],axis=1).dropna().reset_index()
price['difference_polymarket_minus_kalshi']=price.polymarket_median-price.kalshi_median
price=price.merge(od[['game_id','slug','selected_team']].rename(columns={'game_id':'espn_game_id'}),on='espn_game_id',how='left')
price.to_csv(OUT/'polymarket_6a_minute_price_comparison.csv',index=False)
large=price[price.difference_polymarket_minus_kalshi.abs()>(.10+1e-9)].copy()
# Own-asset semantics on Oct. 21 late-window maker rows; receipt prices are
# already decoded as cash/shares for the token in that OrderFilled event.
oct=pm[(pm.slug=='nba-hou-okc-2025-10-21')&(pm.period==4)&pm.clock_s_remaining.between(0,600)].copy(); m=next(x for x in MAP['markets'] if x['slug']=='nba-hou-okc-2025-10-21'); tok,_,_=selected_token(m,str(ASSIGN.loc[str(m['espn_game_id'])].selected_team_abbreviation)); oct['is_selected_asset']=oct.asset.astype(str).eq(str(tok)); oct['selected_price']=np.where(oct.is_selected_asset,oct.price,1-oct.price)
y=int(canon(m['resolved_winner_abbreviation'])==canon(str(ASSIGN.loc[str(m['espn_game_id'])].selected_team_abbreviation))); oct['Y']=y;oct['Y_minus_selected_price']=oct.Y-oct.selected_price
side=oct.groupby(['side','is_selected_asset']).agg(rows=('price','size'),mean_api_own_asset_price=('price','mean'),mean_selected_price=('selected_price','mean'),mean_Y_minus_price=('Y_minus_selected_price','mean'),median_Y_minus_price=('Y_minus_selected_price','median')).reset_index()
side.to_csv(OUT/'polymarket_oct21_price_perspective.csv',index=False)
# Receipt vs API same fill key confirms own-asset price for each maker side.
receipts=pd.read_csv(OUT/'polymarket_oct21_onchain_maker_fills.csv')
api=pm[(pm.slug=='nba-hou-okc-2025-10-21') & pm.period.notna()].copy()
api['transaction_hash']=api.transactionHash.str.lower();api['wallet']=api.proxyWallet.str.lower();api['asset']=api.asset.astype(str)
api['size_key']=pd.to_numeric(api['size']).round(5);api['price_key']=pd.to_numeric(api['price']).round(5)
receipts['size_key']=pd.to_numeric(receipts['size']).round(5);receipts['price_key']=pd.to_numeric(receipts['price']).round(5)
receipts['transaction_hash']=receipts.transaction_hash.str.lower();receipts['wallet']=receipts.maker.str.lower();receipts['asset']=receipts.token.astype(str)
receipt_unique=receipts.drop_duplicates(['transaction_hash','wallet','asset','maker_side','size_key','price_key'])
joined=api.merge(receipt_unique,left_on=['transaction_hash','wallet','asset','side','size_key','price_key'],right_on=['transaction_hash','wallet','asset','maker_side','size_key','price_key'],suffixes=('_api','_receipt'),validate='one_to_one')
joined['price_diff']=pd.to_numeric(joined.price_api)-pd.to_numeric(joined.price_receipt)
receipt_summary=joined.groupby('side').agg(rows=('price_diff','size'),max_abs_price_difference=('price_diff',lambda x:float(x.abs().max())),mean_abs_price_difference=('price_diff',lambda x:float(x.abs().mean()))).reset_index().to_dict('records')
summary={'games_compared':len(od),'legacy_outcome_mismatches_vs_kalshi':int(od.legacy_mismatch.sum()),'corrected_outcome_mismatches_vs_kalshi':int(od.corrected_mismatch.sum()),
         'legacy_mismatch_game_ids':od[od.legacy_mismatch].game_id.tolist(),'team_win_rates':winrates.to_dict('records'),
         'team_names_and_ids':teams.to_dict('records'),'price_minute_pairs':len(price),
         'price_difference_summary':price.difference_polymarket_minus_kalshi.describe(percentiles=[.01,.05,.25,.5,.75,.95,.99]).to_dict(),
         'price_pairs_abs_difference_gt_0_10':len(large),'games_abs_difference_gt_0_10':sorted(large.slug.unique().tolist()),
         'large_price_differences':large[['slug','selected_team','clock_minute_remaining','polymarket_median','kalshi_median','difference_polymarket_minus_kalshi']].to_dict('records'),
         'oct21_selected_team':str(ASSIGN.loc[str(m['espn_game_id'])].selected_team_abbreviation),'oct21_Y':y,
         'oct21_own_asset_vs_receipt_price_by_maker_side':receipt_summary,
         'oct21_Y_minus_price_by_maker_side_and_asset':side.to_dict('records')}
write_json(OUT/'polymarket_6a_bug_diagnostics.json',summary)
print(json.dumps({k:v for k,v in summary.items() if k not in ('team_names_and_ids','team_win_rates','large_price_differences')},indent=2))
print('WIN RATES')
print(winrates.to_string(index=False))
print('TEAM MAPPING')
print(teams.to_string(index=False))
print('LARGE PRICE DIFFERENCES')
print(large[['slug','clock_minute_remaining','polymarket_median','kalshi_median','difference_polymarket_minus_kalshi']].sort_values(['slug','clock_minute_remaining']).to_string(index=False))
print('OCT PERSPECTIVE');print(side.to_string(index=False))
