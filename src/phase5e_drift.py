"""Benchmark-free trade-price drift during quiet stoppages, clustered by game."""
import json
import numpy as np
import pandas as pd
from common import ROOT
from phase5a import OUT, DRAWS
from phase5_main import boot_game_means

def main():
    p=OUT/'phase5_late_trades.parquet'
    d=pd.read_parquet(p,columns=['game_id','market_ticker','ts','late5','late10','quiet_timeout','tau_seconds','event_origin_utc_s','last_event_type','last_event_dPstar','selected_team_is_home','selected_contract_price'])
    d=d.loc[d.quiet_timeout.fillna(False).astype(bool)&pd.to_numeric(d.tau_seconds,errors='coerce').between(0,120)].copy()
    d['game_id']=d.game_id.astype(str);d['tau']=pd.to_numeric(d.tau_seconds,errors='coerce')
    dp=pd.to_numeric(d.last_event_dPstar,errors='coerce');d['direction_selected']=np.sign(np.where(d.selected_team_is_home,dp,-dp))
    d['event_key']=d.game_id+'|'+d.market_ticker+'|'+pd.to_numeric(d.event_origin_utc_s,errors='coerce').fillna(-1).astype('int64').astype(str)
    d['tau_bucket']=pd.cut(d.tau,[0,5,15,30,60,120],right=False,labels=['0-5','5-15','15-30','30-60','60-120'])
    out=[]
    for win,wcol in [('final5','late5'),('final10','late10')]:
        z=d.loc[d[wcol]].copy(); pairs=[]
        for _,g in z.groupby('event_key',sort=False):
            g=g.sort_values('tau');tt=g.tau.to_numpy(float);pp=pd.to_numeric(g.selected_contract_price,errors='coerce').to_numpy(float)
            if len(g)<2:continue
            for h in [5,15,30,60]:
                idx=np.searchsorted(tt,tt+h,side='left');cur=np.flatnonzero(idx<len(g))
                if not len(cur):continue
                q=g.iloc[cur][['game_id','direction_selected','last_event_type','tau_bucket']].copy()
                q['horizon_seconds']=h;q['delta_price']=pp[idx[cur]]-pp[cur];pairs.append(q)
        if not pairs:continue
        q=pd.concat(pairs,ignore_index=True).dropna(subset=['tau_bucket','direction_selected'])
        q=q.loc[q.direction_selected.ne(0)]
        for (h,dire,etype,tb),g in q.groupby(['horizon_seconds','direction_selected','last_event_type','tau_bucket'],observed=True,sort=False):
            s,_=boot_game_means(g.rename(columns={'delta_price':'change'}),'change',draws=DRAWS,seed=20261030+int(h))
            out.append({'window':win,'horizon_seconds':int(h),'event_direction_selected':int(dire),'event_type':str(etype),'tau_bucket':str(tb),'trades':len(g),**s})
    result={'source_rows_quiet_stoppage_tau_le_120':int(len(d)),'rows_by_window':{'final5':int(d.late5.sum()),'final10':int(d.late10.sum())},'grouped_game_cluster_results':out,'method':'Within each game-event episode, pair the current quiet-stoppage trade with the first trade at tau+h; estimate delta selected-contract price, then game-equal mean and game-cluster bootstrap CI. No P* or outcome is used.'}
    (OUT/'phase5e_drift.json').write_text(json.dumps(result,indent=2,default=str));pd.DataFrame(out).to_csv(OUT/'phase5e_drift.csv',index=False)
    print(json.dumps({'rows':len(d),'groups':len(out)},indent=2))
if __name__=='__main__':main()
