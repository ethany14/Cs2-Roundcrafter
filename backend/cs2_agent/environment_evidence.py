"""Causal evidence vector: explicit masks, coarse sounds, spotted history, static cover."""
import json,math,sqlite3,base64,zlib
from pathlib import Path
import numpy as np
from .casebook import ROOT
from .geometry import Mesh,eye
from .acoustics import sound_support
from .smoke import cylinder_interval
from .smoke_voxels import raycast
from .ballistics_experiment import estimate_direct_hit
NAMES=['geometry_available','dynamic_geometry_unknown','forward_cover','left_cover','back_cover','right_cover','footstep_candidates','gunshot_candidates','other_sound_candidates','sound_geometry_blocked_fraction','sound_mapping_missing','sound_listener_position_age']+[f'sound_sector_{i}' for i in range(8)]+['self_spotted_history_count','last_seen_age','last_seen_forward','last_seen_right','last_seen_height','last_seen_valid','current_known_target_static_clear','current_known_target_smoke_possible','smoke_in_view','fire_in_view','self_flash_duration','self_flash_alpha','smoke_voxel_known','smoke_voxel_occupied','known_target_material_crossings','known_target_glass_or_chainlink','known_target_convex_thickness','known_target_thickness_valid','conditional_unarmored_chest_damage','direct_damage_valid','wall_damage','wall_damage_valid']

def load_map(name):
 if name=='de_dust2':
  from .map_assets import load_scene
  return load_scene()
 p=ROOT/'data/maps/all'/name;d=np.load(p/'scene.npz');m=Mesh(d['triangles']);m.surface_ids=d['groups'];m.surfaces=json.loads((p/'scene.json').read_text())['groups'];return m

def position(p):return np.array([p['X'],p['Y'],p['Z']],float)
def endpoint(p):return position(p)+[0,0,64-18*float(p.get('duck_amount') or 0)]
def intersections(mesh,start,end,limit=32):
 hits=mesh.intersections(start,end,limit=limit)
 # Dust2's named door assets are fixed cover, not dynamic doors.
 if hasattr(mesh,'doors'):hits+=mesh.doors.intersections(start,end,limit=limit)
 return sorted(hits,key=lambda h:h['fraction'])[:limit]
def blocked(mesh,start,end):return bool(intersections(mesh,start,end,1))
def active(events,start_name,end_name,tick,round_start):
 starts=[e for e in events if e['event_name']==start_name and round_start<=e['tick']<=tick]
 return [e for e in starts if not any(x['event_name']==end_name and x.get('entityid')==e.get('entityid') and e['tick']<x['tick']<=tick for x in events)]
def has_view(mesh,actor,point):
 o=endpoint(actor);d=point-o;length=np.linalg.norm(d)
 if length<1e-5:return True
 yaw,pitch=np.deg2rad([actor['yaw'],actor['pitch']]);f=np.array([np.cos(pitch)*np.cos(yaw),np.cos(pitch)*np.sin(yaw),-np.sin(pitch)])
 return f@d/length>=math.cos(math.pi/4) and not blocked(mesh,o,point)
def build(raw,sample,mesh,profiles,demo_hash,map_name,voxel_db=None):
 t=sample['tick'];frames={tick:[] for tick in sample['ticks'] if sample['start']<=tick<=t}
 for p in raw['frames']:
  if p['tick'] in frames:frames[p['tick']].append(p)
 actor=next(p for p in frames[t] if str(p['steamid'])==sample['actor']);o=endpoint(actor);yaw=math.radians(actor['yaw']);forward=np.array([math.cos(yaw),math.sin(yaw),0]);right=np.array([-math.sin(yaw),math.cos(yaw),0]);v=dict.fromkeys(NAMES,0.);v['geometry_available']=1;v['dynamic_geometry_unknown']=1 # static world does not reconstruct dynamic props on any map
 for key,angle in zip(['forward_cover','left_cover','back_cover','right_cover'],[0,-math.pi/2,math.pi,math.pi/2]):
  end=o+256*np.array([math.cos(yaw+angle),math.sin(yaw+angle),0]);hit=intersections(mesh,o,end,limit=1);v[key]=hit[0]['fraction'] if hit else 1.
 sounds=[];counts={};blocked=0;missing=0;age=[]
 for e in sorted(raw['events'],key=lambda x:x['tick'],reverse=True):
  if not max(sample['start'],t-128)<e['tick']<=t or e['event_name'] not in ['player_sound','weapon_fire'] or str(e.get('user_steamid'))==sample['actor']:continue
  if e['event_name']=='weapon_fire' and any(k in e.get('weapon','') for k in ['knife','bayonet','grenade','flashbang','molotov','decoy','c4']):continue
  typ='footstep' if e.get('step') else ('gunshot' if e['event_name']=='weapon_fire' else 'other_sound')
  if counts.get(typ,0)>=4:continue
  before=[k for k in frames if k<=e['tick']]
  if not before:continue
  ft=max(before);listener=next((p for p in frames[ft] if str(p['steamid'])==sample['actor']),None)
  if listener is None or any(e.get('user_'+a) is None for a in ['X','Y','Z']):continue
  src=np.array([e['user_'+a] for a in ['X','Y','Z']],float)+[0,0,20 if typ=='footstep' else 60];ear=endpoint(listener);dist=float(np.linalg.norm(src-ear));support=sound_support(profiles,e,dist)
  if not support['known']:missing+=1;continue
  if not support['in_support']:continue
  counts[typ]=counts.get(typ,0)+1;isblocked=bool(intersections(mesh,ear,src,1));blocked+=isblocked;angle=math.atan2(src[1]-ear[1],src[0]-ear[0])-yaw;sector=int(((angle+math.pi)%(2*math.pi))/(math.pi/4));v[f'sound_sector_{sector}']=1;age.append((e['tick']-ft)/64)
  sounds.append({'type':typ,'tick':e['tick'],'bearing_sector':sector,'static_obstacle':bool(isblocked),'basis':support['basis'],'confirmed_heard':False})
 for typ in ['footstep','gunshot','other_sound']:v[typ+'_candidates']=counts.get(typ,0)/4
 v['sound_geometry_blocked_fraction']=blocked/max(1,len(sounds));v['sound_mapping_missing']=0 # Unmapped global events must not reveal hidden activity.
 v['sound_listener_position_age']=max(age,default=0)
 # Only self spotting evidence supplies enemy coordinates; no live hidden-coordinate refresh.
 seen={}
 for tick in sorted(frames):
  for p in frames[tick]:
   if p.get('is_alive') and p['team_num']!=actor['team_num'] and sample['actor'] in [str(x) for x in (p.get('approximate_spotted_by') or [])]:seen[str(p['steamid'])]=(tick,p)
 v['self_spotted_history_count']=len(seen)/5;last=max(seen.values(),key=lambda x:x[0],default=None);target=None
 if last:
  tick,target=last;d=position(target)-position(actor);v.update(last_seen_age=(t-tick)/128,last_seen_forward=float(d@forward)/2000,last_seen_right=float(d@right)/2000,last_seen_height=float(d[2])/1000,last_seen_valid=1)
 smokes=[s for s in active(raw['events'],'smokegrenade_detonate','smokegrenade_expired',t,sample['start']) if has_view(mesh,actor,np.array([s['x'],s['y'],s['z']])+[0,0,40])];fires=active(raw['events'],'inferno_startburn','inferno_expire',t,sample['start']);view_end=o+forward*1000;hit=intersections(mesh,o,view_end,limit=1)
 if hit:view_end=o+(view_end-o)*hit[0]['fraction']
 v['smoke_in_view']=min(4,sum(cylinder_interval(o,view_end,np.array([s['x'],s['y'],s['z']])) is not None for s in smokes))/4
 v['fire_in_view']=min(4,sum(has_view(mesh,actor,np.array([s['x'],s['y'],s['z']])+[0,0,20]) for s in fires))/4
 v['self_flash_duration']=min(5,float(actor.get('flash_duration') or 0))/5;v['self_flash_alpha']=float(actor.get('flash_max_alpha') or 0)/255 if v['self_flash_duration']>0 else 0
 details={'sounds':sounds,'last_seen_tick':last[0] if last else None,'sound_note':'radius candidate plus static obstruction, not rendered sound or confirmed hearing','wall_damage':{'value':None,'reason':'penetration hypothesis failed prior validation'},'smoke_voxel_frames':[]}
 if target is not None:
  end=endpoint(target);hits=intersections(mesh,o,end);v['current_known_target_static_clear']=float(not hits);v['known_target_material_crossings']=min(8,len(hits))/8;v['known_target_glass_or_chainlink']=float(any(h['surface'].get('SurfaceProperty') in ['glass','chainlink'] for h in hits))
  overlap=[s for s in smokes if cylinder_interval(o,end,np.array([s['x'],s['y'],s['z']])) is not None];v['current_known_target_smoke_possible']=float(bool(overlap))
  if hasattr(mesh,'solids'):
   layers=mesh.solids.intervals(o,end);details['solid_intervals']=layers
   complete=[x for x in layers if not x.get('segment_starts_inside') and not x.get('segment_ends_inside')]
   if complete:v['known_target_convex_thickness']=sum(x.get('thickness_units',0) for x in complete)/100;v['known_target_thickness_valid']=1
  for s in overlap:
   if voxel_db:
    row=voxel_db.execute('SELECT tick,position,payload FROM frames WHERE demo_hash=? AND entity_index=? AND tick BETWEEN ? AND ? ORDER BY tick DESC LIMIT 1',(demo_hash,s['entityid'],s['tick'],t)).fetchone()
    if row:
     result=raycast({'tick':row[0],'position':json.loads(row[1]),'data_base64':base64.b64encode(zlib.decompress(row[2])).decode()},o,end);details['smoke_voxel_frames'].append(result)
     if result['status']=='network_occupancy_decoded':v['smoke_voxel_known']=1;v['smoke_voxel_occupied']=max(v['smoke_voxel_occupied'],float(result['intersects']))
  # Conditional damage uses an explicit hypothetical unarmored chest, never hidden enemy armor.
  aliases={'AK-47':'ak47','M4A4':'m4a1','M4A1-S':'m4a1_silencer','AWP':'awp','SSG 08':'ssg08','Desert Eagle':'deagle','Glock-18':'glock','USP-S':'usp_silencer','MP9':'mp9','MAC-10':'mac10','Galil AR':'galilar','FAMAS':'famas'};weapon=aliases.get(actor.get('active_weapon_name'))
  if weapon and not hits and np.linalg.norm(end-o)>0:
   try:v['conditional_unarmored_chest_damage']=estimate_direct_hit({'weapon':weapon,'distance_units':float(np.linalg.norm(end-o)),'hitgroup':'chest','armor':0,'helmet':False})['damage']/100;v['direct_damage_valid']=1
   except ValueError:pass
 return [float(v[k]) for k in NAMES],details
