"""Evaluate the site's movement-prediction path (backend/cs2_agent/movement_model.py) end to end.

Rebuilds inputs from .dem files with the same code the website uses, on a 2 s grid of every round,
and compares with the real future track. Writes outputs/movement/web/evaluation.json (new folder;
earlier experiment outputs are not touched).

  python experiments/movement/evaluate_web.py            # test-split demos + demos shown on the site
"""
import json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from cs2_agent import movement_model as mm
OUT=ROOT/'outputs/movement/web'

def windows(path):
    """All eligible windows of one demo: features (history only) and the real future, kept apart."""
    meta=mm._node('rounds',path)
    if meta['map'] not in mm.MAPS or abs((meta['rate'] or 0)-64)>.1:return meta,[]
    plan=[]
    for i,s in enumerate(meta['rounds']):
        t=s['start']+128
        while t+128<s['end']:plan.append((i,t));t+=128
    need=sorted({t+k*32 for _,t in plan for k in range(-4,5)})
    rows={}
    for j in range(0,len(need),4000):rows.update(mm._node('ticks',path,','.join(map(str,need[j:j+4000])))['rows'])
    out=[];rejected={}
    for i,t in plan:
        s=meta['rounds'][i];now=rows.get(str(t),[])
        for r in now:
            if not r.get('is_alive') or r.get('team_num') not in (2,3):continue
            find=lambda tt:next((x for x in rows.get(str(tt),[]) if x['steamid']==r['steamid']),None)
            try:h,c=mm.features([find(t+(k-4)*32) for k in range(5)],now,s['start'],t,s['plants'])
            except mm.MovementInputError as e:rejected[e.code]=rejected.get(e.code,0)+1;continue
            fut=[find(t+k*32) for k in (1,2,3,4)]
            ok=all(x and x.get('is_alive') and x.get('team_num')==r['team_num'] for x in fut) and all(math.hypot(b['X']-a['X'],b['Y']-a['Y'])<=200 for a,b in zip([r]+fut,fut))
            if not ok:rejected['future_incomplete']=rejected.get('future_incomplete',0)+1;continue
            out.append({'round':i+1,'tick':t,'seconds':(t-s['start'])/64,'steamid':r['steamid'],'h':h,'c':c,'start':[r['X'],r['Y'],r['Z']],'yaw':r['yaw'],
                        'future':[[fut[k-1]['X'],fut[k-1]['Y'],fut[k-1]['Z']] for k in mm.FUTURE]})
    meta['rejected']=rejected;return meta,out

def score(ws,split_z=None):
    if not ws:return None,[]
    loc=mm.predict_local([w['h'] for w in ws],[w['c'] for w in ws]).reshape(-1,3,2);k=mm.info()['velocity_factor'];res=[]
    for w,p in zip(ws,loc):
        pred=mm.to_world(p.tolist(),w['start'],w['yaw']);vel=-np.array(w['h'][-2][:2])
        velp=mm.to_world((vel*np.array(mm.FUTURE)[:,None]*k).tolist(),w['start'],w['yaw'])
        e=lambda q:[math.hypot(a[0]-b[0],a[1]-b[1]) for a,b in zip(q,w['future'])]
        moved=math.hypot(w['future'][-1][0]-w['start'][0],w['future'][-1][1]-w['start'][1])
        floor=None if split_z is None else (w['start'][2]<split_z)!=(w['future'][-1][2]<split_z)
        res.append({**{x:w[x] for x in ('round','seconds','steamid','start','future')},'pred':pred,'err':e(pred),'vel_err':e(velp),'still_err':e([w['start']]*3),'moved_2s':moved,'floor_change':floor})
    agg=lambda key,sel=lambda r:True:round(float(np.mean([np.mean(r[key]) for r in res if sel(r)])),2) if any(sel(r) for r in res) else None
    summary={'n':len(res),'ADE':agg('err'),'velocity_ADE':agg('vel_err'),'stationary_ADE':agg('still_err'),
             'FDE_2s':round(float(np.mean([r['err'][2] for r in res])),2),'velocity_FDE_2s':round(float(np.mean([r['vel_err'][2] for r in res])),2),
             'moving_n':sum(r['moved_2s']>100 for r in res),'moving_ADE':agg('err',lambda r:r['moved_2s']>100),'moving_velocity_ADE':agg('vel_err',lambda r:r['moved_2s']>100),
             'model_beats_velocity_share':round(float(np.mean([np.mean(r['err'])<np.mean(r['vel_err']) for r in res])),3)}
    if split_z is not None:summary['floor_change_n']=sum(bool(r['floor_change']) for r in res);summary['floor_change_ADE']=agg('err',lambda r:r['floor_change'])
    return summary,res

def main():
    from cs2_agent import radar_maps,demo_workbench as wb,demo_review as dr
    OUT.mkdir(parents=True,exist_ok=True)
    ds=json.loads(mm.DATASET.read_text());split=json.loads((mm.MODEL_DIR/'protocol.json').read_text())['split']
    jobs=[(d['path'],d['map'],split[d['group']],'test-split demo',None) for d in ds if split[d['group']]=='test']
    for m in wb.catalog():
        try:p=str(wb.demo_path(m['id']))
        except Exception:continue
        jobs.append((p,m['map'],mm.training_split(m['id']),'site match',m['id']))
    report={'model':mm.info(),'demos':[]};cases=[]
    for path,mp,sp,kind,mid in jobs:
        if kind=='site match' and any(Path(j['path'])==Path(path) for j in report['demos']):continue
        meta,ws=windows(path)
        try:z=radar_maps.metadata(meta['map']).get('floor_split_z')
        except Exception:z=None
        summary,res=score(ws,z)
        report['demos'].append({'path':path,'name':Path(path).name,'map':meta['map'],'split':sp,'kind':kind,'match_id':mid,'rejected':meta.get('rejected'),'summary':summary})
        print(kind,sp,Path(path).name,summary and {k:summary[k] for k in ('n','ADE','velocity_ADE','moving_ADE')},flush=True)
        if mid:cases+=[{**r,'match_id':mid,'map':meta['map'],'split':sp} for r in res]
    tests=[d for d in report['demos'] if d['kind']=='test-split demo' and d['summary']]
    by_map={}
    for d in tests:by_map.setdefault(d['map'],[]).append(d['summary'])
    w=lambda xs,k:round(sum(x[k]*x['n'] for x in xs)/sum(x['n'] for x in xs),2)
    report['test_split_by_map']={m:{'n':sum(x['n'] for x in xs),'ADE':w(xs,'ADE'),'velocity_ADE':w(xs,'velocity_ADE'),'stationary_ADE':w(xs,'stationary_ADE')} for m,xs in sorted(by_map.items())}
    report['test_split_overall']={'n':sum(d['summary']['n'] for d in tests),'ADE':w([d['summary'] for d in tests],'ADE'),'velocity_ADE':w([d['summary'] for d in tests],'velocity_ADE'),'stationary_ADE':w([d['summary'] for d in tests],'stationary_ADE')}
    (OUT/'evaluation.json').write_text(json.dumps(report,indent=1,ensure_ascii=False),encoding='utf-8')
    (OUT/'site-cases.json').write_text(json.dumps(cases),encoding='utf-8')
    print('overall test-split',report['test_split_overall'])

if __name__=='__main__':main()
