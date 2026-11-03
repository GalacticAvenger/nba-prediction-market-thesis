"""Phase 3: score-only win probability benchmark, with held-out model selection."""
from __future__ import annotations
import glob,json,re,warnings
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.preprocessing import SplineTransformer,StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss,log_loss
from lightgbm import LGBMClassifier
from common import ROOT
from game_windows import final_regulation_mask

I=ROOT/'data/interim'; OUT=I/'phase3'; OUT.mkdir(parents=True,exist_ok=True)
FEATURES=['score_diff','log_seconds_remaining','period','is_home','has_possession','free_throw_state','score_x_time']
NON_STANDINGS_CUP_FINALS={'401607495','401734908','401809839'}

def made(txt): return bool(re.search(r'\b(makes|made)\b',txt,re.I))
def turnover(t): return 'turnover' in t.lower()
def rebound(t): return 'rebound' in t.lower()
def derive_pos(g):
    owner=None; vals=[]
    for r in g.itertuples(index=False):
        t=str(r.action_type or '').lower(); team=str(r.team) if pd.notna(r.team) else None
        # ESPN sometimes omits an explicit defensive-rebound record after a miss.
        # The next opponent live action reveals that possession changed.
        if owner and team and team!=owner and any(w in t for w in ('shot','turnover','rebound')):
            owner=team
        if 'offensive rebound' in t: owner=team or owner
        elif 'defensive rebound' in t: owner=team
        elif turnover(t): owner=None
        elif 'free throw' in t:
            owner=team or owner
            m=re.search(r'(\d+) of (\d+)',t)
            if m and m.group(1)==m.group(2) and made(str(r.text or '')): owner=None
        elif 'shot' in t or re.search(r'\b(makes|misses)\b',str(r.text or ''),re.I):
            owner=team or owner
            if made(str(r.text or '')) and 'free throw' not in t: owner=None
        vals.append(owner)
    return vals

def feature_rows_for_game(g, sample_step=10, output_every_second=False):
    g=g.sort_values('_ord',kind='stable').reset_index(drop=True)
    g['possession_derived']=g['possession'].astype('string') if 'possession' in g.columns and g['possession'].notna().any() else derive_pos(g)
    # Need home/away team IDs, infer from score labels kept in the schedule map.
    home_id=str(g.attrs.get('home_id','')); away_id=str(g.attrs.get('away_id',''))
    if not home_id or not away_id:
        teams=[str(x) for x in g.team.dropna().unique()]
        if len(teams)!=2: return [],None
        home_id,away_id=teams[0],teams[1]
    valid=g.dropna(subset=['period','clock_s_remaining']).copy()
    if valid.empty:return [],None
    valid['period']=valid.period.astype(int); valid['clock_s_remaining']=valid.clock_s_remaining.astype(float)
    # Labels from final recorded score; game outcome is shared by both perspectives.
    fin=valid.sort_values('_ord').iloc[-1]
    sh,sa=fin.score_home,fin.score_away
    if pd.isna(sh) or pd.isna(sa): return [],None
    yhome=int(float(sh)>float(sa))
    frames=[]
    for per,pg in valid.groupby('period',sort=True):
        pg=pg.sort_values('_ord',kind='stable').reset_index(drop=True)
        # Emit the complete game-clock grid, not just clocks represented by plays.
        # The source begins with an opening jump/clock state; periods without an
        # observed clock are excluded by PBP coverage checks upstream.
        lo=0; hi=720 if per<=4 else 300
        # Use a fixed 10-second game-clock grid for balanced training and a 1-second
        # grid for 2025-26 output. State is the latest completed ESPN action at that clock.
        step=1 if output_every_second else sample_step
        targets=np.arange(hi,lo-1,-step,dtype=int)
        clocks=pg.clock_s_remaining.to_numpy(dtype=float)
        # ESPN clocks are descending within each period. A binary search selects the
        # latest action at/above each target clock in vectorized form.
        idx=np.searchsorted(-clocks,-targets,side='right')-1
        # Above the earliest observed action, carry the first observed state back
        # to the period start; below it, carry forward the most recent action.
        idx=np.clip(idx,0,len(clocks)-1)
        if not len(targets):
            continue
        scores_h=pg.score_home.to_numpy(dtype=float); scores_a=pg.score_away.to_numpy(dtype=float)
        poss_arr=pg.possession_derived.fillna('').astype(str).to_numpy(); types=pg.action_type.fillna('').to_numpy()
        total=(4-int(per))*720+targets if per<=4 else (int(per)-4)*300+targets
        total=np.maximum(0,total)
        sd=scores_h[idx]-scores_a[idx]
        own_home=(poss_arr[idx]==home_id).astype('int8')
        common=pd.DataFrame({'game_id':str(g.game_id.iloc[0]),'season':int(g.season.iloc[0]),'period':int(per),
            'clock_s_remaining':targets,'seconds_remaining':total,'log_seconds_remaining':np.log1p(total),
            'free_throw_state':pd.Series(types[idx]).str.lower().str.contains('free throw').astype('int8').to_numpy(),
            'timestamp_source':str(g.timestamp_source.iloc[0] or '') if 'timestamp_source' in g else ''})
        home=common.copy(); home['score_diff']=sd; home['score_x_time']=sd*np.log1p(total)
        home['is_home']=1; home['has_possession']=own_home; home['y']=yhome; home['team_perspective']=1
        if output_every_second:
            frames.append(home)
        else:
            away=common.copy(); away['score_diff']=-sd; away['score_x_time']=-sd*np.log1p(total)
            away['is_home']=0; away['has_possession']=1-own_home; away['y']=1-yhome; away['team_perspective']=-1
            frames.extend([home,away])
    return (pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()),(yhome,float(sh),float(sa),home_id,away_id)

def reliability(df, pred_col, name):
    d=df.copy(); d['bin']=pd.cut(d[pred_col],bins=np.linspace(0,1,11),include_lowest=True,labels=False)
    out=d.groupby('bin',observed=True).agg(n=('y','size'),games=('game_id','nunique'),mean_pred=(pred_col,'mean'),win_rate=('y','mean')).reset_index()
    out['gap']=out.win_rate-out.mean_pred; out['sample']=name
    return out

def fit_spline(train, use_pos):
    cols=['score_diff','log_seconds_remaining','period','is_home','free_throw_state','score_x_time']+(['has_possession'] if use_pos else [])
    # Spline basis on state variables; score/time interaction preserves requested nonlinear response.
    model=make_pipeline(SplineTransformer(n_knots=5,degree=3,include_bias=False),StandardScaler(),LogisticRegression(C=0.5,max_iter=500))
    model.fit(train[cols],train.y)
    return model,cols

def fit_lgbm(train,use_pos):
    cols=FEATURES if use_pos else [x for x in FEATURES if x!='has_possession']
    mono=[1,0,0,0,0,0,1] if use_pos else [1,0,0,0,0,1]
    m=LGBMClassifier(n_estimators=550,learning_rate=.035,num_leaves=23,max_depth=-1,min_child_samples=120,
       subsample=.85,colsample_bytree=.9,reg_lambda=2,verbosity=-1,n_jobs=-1,random_state=17,monotone_constraints=mono)
    m.fit(train[cols],train.y)
    return m,cols

def metrics(df,pred):
    late5=np.asarray(final_regulation_mask(df.period,df.clock_s_remaining,5),dtype=bool)
    return {'n_state_rows':len(df),'n_games':int(df.game_id.nunique()),'brier':float(brier_score_loss(df.y,pred)),
            'log_loss':float(log_loss(df.y,np.clip(pred,1e-6,1-1e-6))),
            'final5_n':int(late5.sum()),
            'final5_games':int(df.loc[late5,'game_id'].nunique()),
            'final5_brier':float(brier_score_loss(df.loc[late5,'y'],pred[late5]))}

def main():
    schedules=pd.read_parquet(I/'espn_games.parquet')
    sched=schedules[(schedules.season_type==2)].copy(); sched['espn_game_id']=sched.espn_game_id.astype(str)
    sched=sched[~sched.espn_game_id.isin(NON_STANDINGS_CUP_FINALS)]
    sm={r.espn_game_id:(str(r.home_team_id),str(r.away_team_id)) for r in sched.itertuples()}
    season_dfs={}; outcome_rows=[]; market_rows=[]
    for season in range(2016,2027):
        print('load season',season,flush=True)
        if season==2026:
            raw=pd.read_parquet(I/'phase2/pbp_derived_regular.parquet')
        else:
            files=glob.glob(str(I/f'espn_pbp/season={season}/season_type=2/*.parquet'))
            if not files: continue
            raw=pd.concat([pd.read_parquet(f) for f in files],ignore_index=True)
        raw=raw[~raw.game_id.astype(str).isin(NON_STANDINGS_CUP_FINALS)].copy()
        raw['_ord']=raw.groupby('game_id',sort=False).cumcount()
        frames=[]
        for gid,g in raw.groupby('game_id',sort=False):
            if str(gid) not in sm: continue
            g.attrs['home_id'],g.attrs['away_id']=sm[str(gid)]
            out,final=feature_rows_for_game(g,10,output_every_second=(season==2026))
            if final is None: continue
            if len(out): frames.append(out)
            outcome_rows.append({'game_id':str(gid),'season':season,'home_win':final[0],'home_score':final[1],'away_score':final[2]})
        d=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
        if len(d):
            season_dfs[season]=d
            if season==2026: d.to_parquet(OUT/'pstar_2025_26_every_second.parquet',index=False)
            print(' season rows',len(d),'games',d.game_id.nunique(),flush=True)
    if not season_dfs: raise RuntimeError('No training PBP state rows were built')
    # Hold out 2024-25 season for model selection only.
    train=pd.concat([v for k,v in season_dfs.items() if 2016<=k<=2024],ignore_index=True)
    valid=season_dfs.get(2025)
    if valid is None: raise RuntimeError('2024-25 holdout season missing (season=2025)')
    rows=[]; fitted={}
    for family,fit in [('spline_logistic',fit_spline),('lightgbm_monotone',fit_lgbm)]:
      for pos in [False,True]:
        mod,cols=fit(train,pos); pr=mod.predict_proba(valid[cols])[:,1]
        m=metrics(valid,pr); m.update({'model':family,'possession_feature':pos,'selection_season':'2024-25'})
        rows.append(m); fitted[(family,pos)]=(mod,cols)
        print('model',m,flush=True)
        rel=reliability(valid.assign(pred=pr),'pred',family+('_pos' if pos else '_nopos'))
        rel.to_csv(OUT/f'reliability_2024_25_{family}_pos{int(pos)}.csv',index=False)
    comp=pd.DataFrame(rows).sort_values('final5_brier'); comp.to_csv(OUT/'model_selection.csv',index=False)
    # Possession changes final-five holdout Brier by only a few ten-thousandths;
    # treat this reconstructed feature as unreliable and select the best no-pos model.
    nopos=comp[~comp.possession_feature].sort_values('final5_brier')
    bestrow=nopos.iloc[0]; bestkey=(bestrow.model,False)
    # Final P*: refit selected learner on all 2015-16 through 2024-25 and evaluate the
    # separate 2025-26 market sample (no market prices/odds are used in fitting).
    fulltrain=pd.concat([v for k,v in season_dfs.items() if 2016<=k<=2025],ignore_index=True)
    finalmod,cols=(fit_spline if bestkey[0]=='spline_logistic' else fit_lgbm)(fulltrain,bestkey[1])
    test=season_dfs.get(2026)
    test['pstar']=finalmod.predict_proba(test[cols])[:,1]
    # Prespecified robustness predictions: possession and spline alternatives.
    posmod,poscols=(fit_spline if bestkey[0]=='spline_logistic' else fit_lgbm)(fulltrain,True)
    test['pstar_with_possession']=posmod.predict_proba(test[poscols])[:,1]
    splinemod,splinecols=fit_spline(fulltrain,False)
    test['pstar_spline_logistic']=splinemod.predict_proba(test[splinecols])[:,1]
    test.to_parquet(OUT/'pstar_2025_26_every_second.parquet',index=False)
    test_metrics=metrics(test,test.pstar.to_numpy())
    test_rel=reliability(test,'pstar','2025-26 market sample'); test_rel.to_csv(OUT/'reliability_2025_26.csv',index=False)
    holdrow=next(r for r in rows if r['model']==bestkey[0] and r['possession_feature']==bestkey[1])
    holdmodel,holdcols=fitted[bestkey]; holdpred=holdmodel.predict_proba(valid[holdcols])[:,1]
    holdmetrics=metrics(valid,holdpred)
    # Frequency resolution and counts per one-second output game.
    sec=test.groupby('game_id').agg(seconds=('clock_s_remaining','count'),periods=('period','nunique'))
    summary={'training_seasons':'2015-16 through 2023-24 for selection fit; final refit includes 2024-25',
      'holdout_model_selection_season':'2024-25','selection_candidates':rows,
      'selection_rule':'lowest 2024-25 holdout final-five-minute Brier among no-possession models; possession retained for robustness because its late-game increment is negligible',
      'selected_model':bestkey[0],'selected_possession_feature':bestkey[1],
      'selected_model_holdout_metrics':holdmetrics,'final_refit_market_sample_metrics':test_metrics,
      'market_sample_games':int(test.game_id.nunique()),'output_state_rows':int(len(test)),
      'per_game_seconds_min':int(sec.seconds.min()),'per_game_seconds_median':float(sec.seconds.median()),'per_game_seconds_max':int(sec.seconds.max()),
      'timestamp_sources':test.timestamp_source.value_counts().to_dict(),
      'features':['team-perspective score differential','log seconds remaining','period','team is home','free-throw play state','score differential x log time remaining']+(['team-perspective possession'] if bestkey[1] else []),
      'market_data_excluded_from_all_fits':True,'non_standings_cup_finals_excluded':sorted(NON_STANDINGS_CUP_FINALS),
      'robustness_models':['selected learner with possession','spline logistic without possession']}
    (OUT/'phase3_summary.json').write_text(json.dumps(summary,indent=2,default=str))
    print(json.dumps(summary,indent=2,default=str))
if __name__=='__main__': main()
