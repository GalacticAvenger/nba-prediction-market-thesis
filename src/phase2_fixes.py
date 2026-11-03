"""Approved Phase 2 corrections: prompt-action timeout anchors, buffers, and possessions."""
from __future__ import annotations
import glob, json, re
from pathlib import Path
from collections import Counter
import pandas as pd
import numpy as np
from common import ROOT
from game_windows import final_regulation_mask

I=ROOT/'data/interim'; O=I/'phase2'; O.mkdir(parents=True,exist_ok=True)
CONFIG=ROOT/'config.yaml'

def prompt(r):
    t=str(r.action_type or '').lower()
    return any(x in t for x in ('shot','rebound','turnover'))

def timeout_diagnostics(pbp):
    cfg=CONFIG.read_text() if CONFIG.exists() else ''
    m=re.search(r'quiet_window_end_buffer_seconds:\s*(\d+)',cfg)
    selected=int(m.group(1)) if m else 5
    out=[]
    for gid,g in pbp.groupby('game_id',sort=False):
        g=g.sort_values('_ord').reset_index(drop=True); rr=list(g.itertuples(index=False))
        for i,r in enumerate(rr):
            if 'timeout' not in str(r.action_type or '').lower(): continue
            nxt=None; j=None
            for k in range(i+1,len(rr)):
                n=rr[k]
                if int(n.period or 0)!=int(r.period or 0): break
                if prompt(n) and pd.notna(n.ts_wall_utc) and pd.notna(n.clock_s_remaining): nxt=n;j=k;break
            if nxt is None or pd.isna(r.ts_wall_utc) or pd.isna(r.clock_s_remaining): continue
            restart=pd.Timestamp(nxt.ts_wall_utc)-pd.Timedelta(seconds=float(r.clock_s_remaining)-float(nxt.clock_s_remaining))
            onset=pd.Timestamp(r.ts_wall_utc)
            seg=rr[i+1:j]
            texts=' '.join((str(x.action_type or '')+' '+str(x.text or '')).lower() for x in seg)
            score=any(str(x.score_home)!=str(r.score_home) or str(x.score_away)!=str(r.score_away) for x in seg)
            flag=score or any(z in texts for z in ('review','challenge'))
            base={'game_id':str(gid),'period':int(r.period),'clock_s_remaining':float(r.clock_s_remaining),'onset_wall':onset.isoformat(),
                  'anchor_action_type':str(nxt.action_type),'anchor_clock':float(nxt.clock_s_remaining),'restart_wall_est':restart.isoformat(),
                  'quiet_seconds_raw':(restart-onset).total_seconds(),'excluded_score_review_challenge':bool(flag)}
            for b in (0,5,10):
                stop=restart-pd.Timedelta(seconds=b)
                base[f'quiet_seconds_buffer_{b}']=max(0,(stop-onset).total_seconds())
                base[f'survives_buffer_{b}']=bool(not flag and stop>=onset)
            out.append(base)
    d=pd.DataFrame(out); d['quiet_window_end_buffer_selected']=selected
    d['quiet_seconds_selected']=d.get(f'quiet_seconds_buffer_{selected}')
    d['survives_selected_buffer']=d.get(f'survives_buffer_{selected}')
    d.to_csv(O/'timeout_intervals.csv',index=False)
    surv={}
    if len(d):
        for b in (0,5,10):
            ss=d[d[f'survives_buffer_{b}']]
            late=pd.Series(final_regulation_mask(ss.period,ss.clock_s_remaining,5),index=ss.index)
            surv[str(b)]={'all':len(ss),'final5_regulation':int(late.sum()),
                          'final5_games':int(ss.loc[late,'game_id'].nunique())}
    (O/'timeout_buffer_summary.json').write_text(json.dumps({'anchor_rule':'first subsequent shot, rebound, or turnover within the period; excludes free throws, fouls, substitutions and other delayed actions','buffers_seconds':[0,5,10],'selected_buffer_seconds':selected,'counts':surv},indent=2))
    return surv

def boxscore_stats(gid):
    p=ROOT/'data/raw/espn/summaries'/f'{gid}.json'
    if not p.exists(): return []
    try: x=json.loads(p.read_text())
    except: return []
    res=[]
    for t in x.get('boxscore',{}).get('teams',[]):
        vals={z.get('name'):z.get('displayValue','') for z in t.get('statistics',[])}
        fg=vals.get('fieldGoalsMade-fieldGoalsAttempted',''); ft=vals.get('freeThrowsMade-freeThrowsAttempted','')
        try: fga=float(fg.split('-')[1]); fta=float(ft.split('-')[1]); orb=float(vals.get('offensiveRebounds',0)); tov=float(vals.get('turnovers',0))
        except: continue
        res.append({'team':str(t.get('team',{}).get('id')),'fga':fga,'orb':orb,'tov':tov,'fta':fta,'box_poss':fga-orb+tov+0.44*fta})
    return res

def possessions(pbp):
    rows=[]; state_rows=[]
    for gid,g in pbp.groupby('game_id',sort=False):
        g=g.sort_values('_ord').reset_index(drop=True); rr=list(g.itertuples(index=False))
        counts=Counter(); owner=None; poss_state=[]; last_period=None; last_action_owner=None
        for i,r in enumerate(rr):
            typ=str(r.action_type or '').lower(); team=str(r.team) if pd.notna(r.team) else None
            # Starting period's opening jumpball identifies the eventual offense in its description.
            if 'jump' in typ and ('ball' in typ or 'jumpball' in typ):
                m=re.search(r'gains possession',str(r.text or ''),re.I)
                if m:
                    pname=str(r.text).split('(')[-1].split(' gains')[0]
                    # Explicit team is unavailable; next team-tagged live action below identifies owner.
                    owner=None
            elif 'offensive rebound' in typ:
                if team: owner=team
            elif 'defensive rebound' in typ:
                if owner and team and owner!=team: counts[owner]+=1
                owner=team
            elif is_turnover(typ):
                who=team or owner
                if who: counts[who]+=1
                owner=None
            elif is_attempt(typ,str(r.text or '')):
                owner=team or owner
                if is_made_text(str(r.text or '')) and 'free throw' not in (typ+' '+str(r.text).lower()):
                    if owner: counts[owner]+=1
                    owner=None
                else:
                    # A missed field goal with no rebound record is terminal if the next
                    # offensive action is by the opponent, or when the period ends.
                    for n in rr[i+1:]:
                        nt=str(n.action_type or '').lower(); nteam=str(n.team) if pd.notna(n.team) else None
                        if 'offensive rebound' in nt and nteam==owner: break
                        if 'defensive rebound' in nt:
                            if owner and nteam and nteam!=owner: counts[owner]+=1
                            owner=nteam; break
                        if 'end period' in nt:
                            if owner: counts[owner]+=1
                            owner=None; break
                        if nteam and nteam!=owner and (is_attempt(nt,str(n.text or '')) or is_turnover(nt) or 'foul' in nt):
                            if owner: counts[owner]+=1
                            owner=nteam; break
                    # loop above only handles missed-shot gap; keep same owner after miss
            elif 'free throw' in typ:
                owner=team or owner
                if is_last_ft(typ) and is_made_text(str(r.text or '')):
                    if owner: counts[owner]+=1
                    owner=None
            elif 'end period' in typ:
                if owner: counts[owner]+=1
                owner=None
            elif team and owner is None and (is_attempt(typ,str(r.text or '')) or 'foul' in typ or 'free throw' in typ):
                owner=team
            poss_state.append(owner)
        # Correct missing-period-boundary terminal if still held after final play.
        if owner: counts[owner]+=1
        state_rows.extend({'game_id':str(gid),'_ord':i,'possession':v} for i,v in enumerate(poss_state))
        official=boxscore_stats(gid)
        for s in official:
            rows.append({'game_id':str(gid),'team':s['team'],'box_possessions':s['box_poss'],'fga':s['fga'],'orb':s['orb'],'tov':s['tov'],'fta':s['fta'],
                         'action_possessions':counts.get(s['team'],0),'difference':counts.get(s['team'],0)-s['box_poss']})
    d=pd.DataFrame(rows); d.to_csv(O/'possessions_by_game.csv',index=False)
    if len(d):
        summ={'team_game_rows':len(d),'mean_box_possessions':float(d.box_possessions.mean()),'mean_action_possessions':float(d.action_possessions.mean()),
              'median_abs_difference':float(d.difference.abs().median()),'within_3_share':float((d.difference.abs()<=3).mean()),'within_3_count':int((d.difference.abs()<=3).sum()),
              'undercount_share':float((d.difference< -3).mean()),'overcount_share':float((d.difference>3).mean()),
              'games_both_teams_within_3':int((d.assign(ok=d.difference.abs()<=3).groupby('game_id').ok.sum()==2).sum()),
              'games_at_least_one_team_within_3':int((d.assign(ok=d.difference.abs()<=3).groupby('game_id').ok.sum()>=1).sum())}
    else: summ={'team_game_rows':0}
    (O/'possession_validation.json').write_text(json.dumps(summ,indent=2))
    return summ,pd.DataFrame(state_rows)

def is_turnover(typ): return 'turnover' in typ
def is_attempt(typ,txt): return ('shot' in typ) or bool(re.search(r'\b(makes|misses)\b',txt,re.I) and 'free throw' not in txt.lower())
def is_made_text(txt): return bool(re.search(r'\b(makes|made)\b',txt,re.I))
def is_last_ft(typ):
    m=re.search(r'(\d+) of (\d+)',typ); return bool(m and int(m.group(1))==int(m.group(2))) or '1 of 1' in typ

def main():
    files=glob.glob(str(I/'espn_pbp/season=2026/season_type=2/*.parquet')); pbp=pd.concat([pd.read_parquet(f) for f in files],ignore_index=True)
    pbp=pbp[(pbp.season==2026)&(pbp.game_id.astype(str)!='401809839')].copy(); pbp['_ord']=pbp.groupby('game_id',sort=False).cumcount()
    timeouts=timeout_diagnostics(pbp); pos,state=possessions(pbp)
    phase2=O/'pbp_derived_regular.parquet'; old=pd.read_parquet(phase2); old['_ord']=old.groupby('game_id',sort=False).cumcount(); old=old.drop(columns=['possession'],errors='ignore')
    # patch only possession states when row counts/order correspond to original 2026 regular sample
    merged=old.merge(state,on=['game_id','_ord'],how='left')
    if 'possession_y' in merged: merged=merged.rename(columns={'possession_y':'possession'}).drop(columns=['possession_x'],errors='ignore')
    merged.drop(columns=['_ord'],errors='ignore').to_parquet(phase2,index=False)
    print(json.dumps({'timeout_counts':timeouts,'possession_validation':json.loads((O/'possession_validation.json').read_text())},indent=2))
if __name__=='__main__': main()
