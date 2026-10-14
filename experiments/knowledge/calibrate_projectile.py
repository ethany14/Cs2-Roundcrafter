"""Fit free-flight gravity on disjoint demo files; do not select existing lineups."""
import json
from pathlib import Path
import numpy as np
from cs2_agent.casebook import ROOT
files=sorted((ROOT/'data/knowledge/metastack/extracted').glob('*.json'));rows=[]
for fi,f in enumerate(files):
 d=json.loads(f.read_text());count=0
 for c in d.get('cases',[]):
  if c['type']!='smoke':continue
  p=np.asarray(c['path'],float)
  for i in range(0,len(p)-6,7):
   seg=p[i:i+7];t=(seg[:,0]-seg[0,0])/64
   if not np.allclose(np.diff(t),.0625):continue
   A=np.column_stack([np.ones(7),t,t*t]);coef=np.linalg.lstsq(A,seg[:,1:4],rcond=None)[0];res=float(np.max(np.linalg.norm(A@coef-seg[:,1:4],axis=1)));acc=2*coef[2];speed=float(np.linalg.norm(coef[1]));g=-acc[2]
   if res>.15 or np.linalg.norm(acc[:2])>5 or speed<50 or not 20<g<1000:continue
   rows.append({'split':'train' if fi<len(files)-3 else 'holdout','demo':f.stem,'case_id':c['id'],'start_tick':int(seg[0,0]),'gravity':float(g),'fit_max_residual':res,'t':t.tolist(),'positions':seg[:,1:4].tolist()});count+=1
train=[x for x in rows if x['split']=='train'];hold=[x for x in rows if x['split']=='holdout'];g=float(np.median([x['gravity'] for x in train]));errors=[]
for r in hold:
 t=np.array(r['t']);p=np.array(r['positions']);dt=t[1];v=(p[1]-p[0])/dt+[0,0,g*dt/2];pred=p[0]+t[:,None]*v+np.column_stack([t*0,t*0,-g*t*t/2]);errors.extend(np.linalg.norm(pred[2:]-p[2:],axis=1).tolist())
report={'train_demos':[p.stem for p in files[:-3]],'holdout_demos':[p.stem for p in files[-3:]],'train_windows':len(train),'holdout_windows':len(hold),'fitted_gravity':g,'reference_gravity':320,'holdout_gravity_median':float(np.median([x['gravity'] for x in hold])),'holdout_position_error_units':{'median':float(np.median(errors)),'p95':float(np.percentile(errors,95)),'max':max(errors)},'selection':'7 consecutive 4-tick samples; low quadratic residual and low horizontal acceleration; moving smoke projectile; selection conditions exclude collisions and network jumps','limits':['64 Hz sampling assumption','Filtered free-flight windows only; not launch, bounce or smoke coverage validation','Position-derived velocity; not independent server velocity telemetry','No demo throw angle or ready-made lineup used by solver']}
(ROOT/'outputs/tactics/free-flight-calibration.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
