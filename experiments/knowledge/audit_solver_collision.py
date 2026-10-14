import json,time
import numpy as np
from cs2_agent.grenade_search import scene,simulate,area_samples
from cs2_agent.smoke import cylinder_interval
from cs2_agent.casebook import ROOT
m=scene();old=json.loads((ROOT/'outputs/tactics/tactical-solver-v1.json').read_text());rows=[];started=time.time()
for c in old.get('diagnostics',[]):
 result=simulate(m,c['position'],c['pitch'],c['yaw']);rows.append({'position':c['position'],'pitch':c['pitch'],'yaw':c['yaw'],'old_end':c['trajectory'][-1],'new':result,'endpoint_change':None if not result else float(np.linalg.norm(np.array(result['end'])-c['trajectory'][-1]))})
areas=area_samples()
def diverse(name,count):
 result=[]
 for p in sorted(areas[name]):
  if not any(np.linalg.norm(np.array(p)-q)<100 for q in result):result.append(p)
  if len(result)>=count:break
 return result
rays=[]
for h in diverse('Heaven',16):
 for a in diverse('BombsiteA',24):
  origin=np.array(h)+[0,0,64];target=np.array(a)+[0,0,64]
  if not m.blocked(origin,target):rays.append({'from':origin.tolist(),'to':target.tolist()})
selected=rays[::max(1,len(rays)//8)][:8]
for r in rows:
 if r['new']:r['provisional_envelope_intersections']=sum(cylinder_interval(ray['from'],ray['to'],np.array(r['new']['end'])) is not None for ray in selected)
report={'physics':{'shape':'radius-2 sphere; assumed, not CS2 engine validated','remaining_tick':True},'comparisons':rows,'target_rays':selected,'clear_ray_count':len(rays),'target_evidence':'hypothetical sightlines between observed callout positions under standing eye-height assumption; static line of sight only','elapsed_seconds':time.time()-started,'limits':['These rays are not actual enemy positions','Cylinder overlap is not smoke opacity or sealed Heaven validation','Callout samples can include transitional/in-air points; not authoritative navmesh']}
(ROOT/'outputs/tactics/solver-collision-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k not in ['comparisons','target_rays']}));print(json.dumps([{k:v for k,v in r.items() if k!='new'} for r in rows]))
