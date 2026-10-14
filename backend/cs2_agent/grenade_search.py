"""Independent conservative point-projectile prototype, not calibrated CS2 physics."""
import json, math, hashlib
from pathlib import Path
import numpy as np
from .casebook import ROOT
from .geometry import Mesh
from .tactical_solver import intent, assess, command
from .smoke import cylinder_interval

PARAMS={'gravity':320.,'speed':675.,'elasticity':.45,'dt':1/64,'max_seconds':8,'eye_height':64.,'release_offset':16.,'status':'gravity_checked_on_demo_holdout_launch_and_bounce_uncalibrated','collision':'continuous_sphere_faces_edges_vertices','radius':2.,'radius_status':'experimental_shape_not_engine_verified'}

def scene():
 path=ROOT/'data/maps/all/de_nuke/scene.npz';meta=json.loads(path.with_suffix('.json').read_text());d=np.load(path)
 allowed=[i for i,g in enumerate(meta['groups']) if g.get('SurfaceProperty')!='audioblocker']
 m=Mesh(d['triangles'][np.isin(d['groups'],allowed)].reshape(-1,3,3));m.sha256=hashlib.sha256(path.read_bytes()).hexdigest();return m

def first_hit(m,a,b):
 hits=m.intersections(a,b,limit=1)
 if not hits:return None
 h=hits[0];tri=m.tri[h['triangle']];n=np.cross(tri[1]-tri[0],tri[2]-tri[0]);n/=max(np.linalg.norm(n),1e-12)
 if np.dot(n,np.asarray(b)-a)>0:n=-n
 return h['fraction'],n

def standable(m,pos):
 p=np.asarray(pos,float)
 # Ground support at feet and four corners; reject unsupported height and slopes.
 for dx,dy in [(0,0),(-14,-14),(-14,14),(14,-14),(14,14)]:
  q=p+[dx,dy,0];h=first_hit(m,q+[0,0,4],q-[0,0,5])
  if h is None or h[1][2]<.7:return False
 # Conservative sparse clearance probes. This is not an engine player-hull trace.
 for dx,dy in [(-16,-16),(-16,16),(16,-16),(16,16),(0,0)]:
  if first_hit(m,p+[dx,dy,5],p+[dx,dy,72]):return False
 for z in [10,36,64]:
  for dx,dy in [(16,0),(-16,0),(0,16),(0,-16)]:
   if first_hit(m,p+[0,0,z],p+[dx,dy,z]):return False
 return True

def simulate_point_legacy(m,pos,pitch,yaw):
 effective=pitch-(90-abs(pitch))/9;p,y=map(math.radians,[effective,yaw]);direction=np.array([math.cos(p)*math.cos(y),math.cos(p)*math.sin(y),-math.sin(p)])
 eye=np.asarray(pos,float)+[0,0,PARAMS['eye_height']];x=eye+direction*PARAMS['release_offset']
 if first_hit(m,eye,x):return None
 v=direction*PARAMS['speed'];path=[x.tolist()];bounces=0;contacts=0;dt=PARAMS['dt']
 for step in range(round(PARAMS['max_seconds']/dt)):
  new_v=v+[0,0,-PARAMS['gravity']*dt];end=x+(v+new_v)*dt/2;hit=first_hit(m,x,end)
  if hit:
   frac,n=hit;x=x+(end-x)*frac+n*.08;impact=abs(float(np.dot(new_v,n)));v=(new_v-2*np.dot(new_v,n)*n)*PARAMS['elasticity'];contacts+=1
   if impact>80:bounces+=1
   if n[2]>.7 and np.linalg.norm(v)<35:return {'end':x.tolist(),'path':path+[x.tolist()],'bounces':bounces,'flight_seconds':(step+1)*dt,'settled':True}
   if contacts>16:return None
  else:x=end;v=new_v
  if step%2==0:path.append(x.tolist())
 return None

# Published first-party measurements by Memorin; not validated on this installation.
JUMP_PROFILE={'source':'https://memorin.app/mechanics/jump-throw',
 'source_build':'1.41.6.8/10847','latched_player_vz':218.86838,
 'inheritance':1.25,'latch_seconds':.1,'takeoff_vz':298.86838,
 'player_gravity':800.,'status':'external_measurement_local_calibration_pending'}

def jump_release(m,pos):
 # Height is an explicit continuous-motion approximation, not a measured pose.
 t=JUMP_PROFILE['latch_seconds']
 dz=JUMP_PROFILE['takeoff_vz']*t-.5*JUMP_PROFILE['player_gravity']*t*t
 p=np.asarray(pos,float)
 for dx,dy in [(0,0),(-16,-16),(-16,16),(16,-16),(16,16)]:
  if first_hit(m,p+[dx,dy,72],p+[dx,dy,72+dz]):return None
 return {'height_offset':dz,'added_vz':JUMP_PROFILE['latched_player_vz']*JUMP_PROFILE['inheritance'],
         'height_evidence':'continuous_motion_inference','profile':JUMP_PROFILE}

def simulate(m,pos,pitch,yaw,checkpoint=None,mode='stand_left',launch_override=None):
 from .projectile_collision import sweep,advance
 effective=pitch-(90-abs(pitch))/9;p,y=map(math.radians,[effective,yaw]);direction=np.array([math.cos(p)*math.cos(y),math.cos(p)*math.sin(y),-math.sin(p)])
 launch=launch_override if launch_override is not None else jump_release(m,pos) if mode=='jump_left' else {'height_offset':0.,'added_vz':0.}
 if launch is None:return None
 eye=np.asarray(launch.get('release_feet',pos),float)+[0,0,launch.get('eye_height',PARAMS['eye_height'])+launch['height_offset']];x=eye+direction*PARAMS['release_offset']
 if sweep(m,eye,x,PARAMS['radius']):return None
 velocity=direction*PARAMS['speed']+np.asarray(launch.get('added_velocity',[0,0,launch['added_vz']]));path=[x.tolist()];bounces=0;contacts=0;dt=PARAMS['dt']
 for step in range(round(PARAMS['max_seconds']/dt)):
  if checkpoint is not None:checkpoint()
  x,velocity,events,settled,limited=advance(m,x,velocity,dt,PARAMS['gravity'],PARAMS['radius'],PARAMS['elasticity'])
  bounces+=sum(e['impact']>80 for e in events);contacts+=len(events)
  if limited:return None
  if settled:return {'end':x.tolist(),'path':path+[x.tolist()],'bounces':bounces,'contacts':contacts,'flight_seconds':(step+1)*dt,'settled':True}
  if contacts>32:return None
  if step%2==0:path.append(x.tolist())
 return None

def area_samples():
 # Only geographic name/position observations; no recorded throw angles or paths.
 out={}
 for f in sorted((ROOT/'data/knowledge/metastack/extracted').glob('*.json')):
  for a in json.loads(f.read_text()).get('anchors',[]):
   p=a['position'];key=tuple(round(v/48) for v in p);out.setdefault(a['name'],{})[key]=p
 return {name:list(rows.values()) for name,rows in out.items()}

def corridor_screen(end,rays):
 hits=sum(cylinder_interval(ray['from'],ray['to'],np.asarray(end)) is not None for ray in rays)
 return {'intersections':hits,'tested':len(rays),'passed':bool(rays) and hits==len(rays),'model':'provisional_cylinder_200_radius_not_true_smoke','evidence':'sampled_static_clear_sightlines_not_actual_enemy_positions'}

def search(action_id='heaven_smoke',max_origins=4):
 spec=intent(action_id);m=scene();areas=area_samples();
 audit_path=ROOT/'outputs/tactics/solver-collision-audit.json'
 rays=json.loads(audit_path.read_text())['target_rays'] if action_id=='heaven_smoke' and audit_path.exists() else []
 raw=areas.get(spec['origin_area'],[]);targets=np.array(areas.get(spec['target_area'],[]),float)
 if len(targets)==0:raise ValueError('Target geography unavailable')
 # A regional search target, explicitly not a verified smoke seal.
 center=np.median(targets,axis=0);valid=[]
 raw=sorted(raw,key=lambda p:float(np.linalg.norm(np.asarray(p)-center)))
 rejected=0
 for pos in raw:
  if any(math.dist(pos,q)<96 for q in valid):continue
  if not standable(m,pos):rejected+=1;continue
  valid.append(pos)
  if len(valid)>=max_origins:break
 candidates=[];tried=0;nearest=None
 for pos in valid:
  yaw=math.degrees(math.atan2(center[1]-pos[1],center[0]-pos[0]))
  for dy in [-12,0,12]:
   for pitch in [-65,-50,-35,-20,-5,10]:
    tried+=1;r=simulate(m,pos,pitch,yaw+dy)
    if not r:continue
    distance=float(np.linalg.norm(np.asarray(r['end'])-center))
    nearest=distance if nearest is None else min(nearest,distance)
    if distance>160 or abs(r['end'][2]-center[2])>64 or r['bounces']>spec['max_bounces']:continue
    c={'map':spec['map'],'side':spec['side'],'role':spec['role'],'origin_area':spec['origin_area'],'target_area':spec['target_area'],'next_area':spec['next_area'],'position':pos,'pitch':pitch,'yaw':yaw+dy,'mode':'stand_left','standable':True,'reached_target':True,'bounces':r['bounces'],'distance':distance,'trajectory':r['path'],'flight_seconds':r['flight_seconds'],'coverage_verified':False,'game_validated':False,'exposure_checked':False}
    checks=[]
    for dp,dyaw in [(0,0),(-.5,0),(.5,0),(0,-.5),(0,.5)]:
     j=simulate(m,pos,pitch+dp,yaw+dy+dyaw);checks.append(bool(j and j['bounces']<=spec['max_bounces'] and np.linalg.norm(np.asarray(j['end'])-center)<=160 and abs(j['end'][2]-center[2])<=64))
    c['robustness']={'passed':sum(checks),'tested':len(checks),'perturbation_degrees':.5,'meaning':'coarse_region_sensitivity_not_success_probability'}
    c['target_corridor']=corridor_screen(r['end'],rays);c['assessment']=assess(spec,c);c['practice_command']=command(c);candidates.append(c)
 # Refine around coarse hits; never borrow demo throw angles.
 seeds=list(candidates)
 for seed in seeds[:2]:
  for dp in [-2,-1,0,1,2]:
   for dy in [-2,-1,0,1,2]:
    pitch=seed['pitch']+dp;yaw=seed['yaw']+dy;tried+=1
    r=simulate(m,seed['position'],pitch,yaw)
    if not r:continue
    distance=float(np.linalg.norm(np.asarray(r['end'])-center))
    if distance>160 or abs(r['end'][2]-center[2])>64 or r['bounces']>spec['max_bounces']:continue
    c={**seed,'pitch':pitch,'yaw':yaw,'distance':distance,'trajectory':r['path'],'flight_seconds':r['flight_seconds'],'bounces':r['bounces']}
    checks=[]
    for dp2,dy2 in [(0,0),(-.5,0),(.5,0),(0,-.5),(0,.5)]:
     j=simulate(m,c['position'],pitch+dp2,yaw+dy2);checks.append(bool(j and j['bounces']<=spec['max_bounces'] and np.linalg.norm(np.asarray(j['end'])-center)<=160 and abs(j['end'][2]-center[2])<=64))
    c['robustness']={'passed':sum(checks),'tested':5,'perturbation_degrees':.5,'meaning':'coarse_region_sensitivity_not_success_probability'}
    c['target_corridor']=corridor_screen(r['end'],rays);c['assessment']=assess(spec,c);c['practice_command']=command(c);candidates.append(c)
 rejected_unstable=sum(c['robustness']['passed']<4 for c in candidates)
 diagnostics=[{k:v for k,v in c.items() if k!='practice_command'} for c in candidates if c['assessment']['blocked']][:3]
 candidates=[c for c in candidates if not c['assessment']['blocked']]
 candidates.sort(key=lambda c:(-c['robustness']['passed'],c['bounces'],c['distance']))
 return {'schema':1,'intent':spec,'physics':PARAMS,'map_sha256':m.sha256,'target_center':center.tolist(),'target_radius':160,'height_tolerance':64,'origins':valid,'counts':{'sampled_origins':len(raw),'rejected_footing':rejected,'simulated':tried,'candidates':len(candidates),'rejected_unstable':rejected_unstable,'rejected_corridor_coarse':sum(not c['target_corridor']['passed'] for c in seeds)},'nearest_settled_distance':nearest,'candidates':candidates[:5],'diagnostics':diagnostics,'target_rays':rays,'status':'experimental_candidates' if candidates else 'no_solution_in_bounded_search','limits':['有限粗搜索，无解不代表不存在投法','增加代表性枪线的粗包络筛选；仍不代表真实体素烟雾封锁','球形扫掠半径为实验设定；未验证游戏实际碰撞形状，未处理动态门和破碎玻璃','已计算碰撞后剩余 tick；滚动、引爆和摩擦仍未精确校准','站位仅通过稀疏落脚和空间探针，不代表完整导航可达','未调用大模型；战术约束来自已审核的来源描述映射']}

if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--action',default='heaven_smoke');ap.add_argument('--origins',type=int,default=4);a=ap.parse_args();r=search(a.action,max(1,min(12,a.origins)));p=ROOT/'outputs/tactics/tactical-solver.json';p.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':r['status'],'counts':r['counts'],'nearest':r['nearest_settled_distance']}))
