"""Offline evidence from local sound assets. Radius/curve support is NOT hearing proof."""
import hashlib,json,re
from pathlib import Path
import numpy as np
from .casebook import ROOT

def blocks(text):return {m[1]:m[2] for m in re.finditer(r'^\t([^\s=]+) =\s*\n\t\{\n(.*?)^\t\}',text,re.M|re.S)}
def build_profiles():
 directory=ROOT/'data/sounds/soundevents';nodes={};sources={}
 for name in ['game_sounds_footsteps.vsndevts','game_sounds_weapons.vsndevts']:
  path=directory/name;sources[name]=hashlib.sha256(path.read_bytes()).hexdigest()
  for key,b in blocks(path.read_text(encoding='utf-8')).items():
   curve=re.search(r'\t\tdistance_volume_mapping_curve =\s*\n\t\t\[(.*?)\n\t\t\]',b,re.S)
   points=[]
   if curve:
    for row in re.findall(r'\[([^\[\]]+)\]',curve[1]):
     nums=[float(n) for n in re.findall(r'-?\d+(?:\.\d+)?',row)];points.append(nums)
   child=re.search(r'\t\tsoundevent_01 =\s*\n\t\t\[(.*?)\n\t\t\]',b,re.S)
   nodes[key]={'points':points,'children':re.findall(r'"([^"]+)"',child[1]) if child and 'enable_child_events = true' in b else [],'file':name,'baked_occlusion':'use_baked_occlusion = true' in b}
 weapons={};path=ROOT/'data/maps/weapons.vdata';sources[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
 for _,b in blocks(path.read_text(encoding='utf-8')).items():
  key=re.search(r'm_szName = "(weapon_[^"]+)"',b)
  single=re.search(r'WEAPON_SOUND_SINGLE = soundevent:"([^"]+)"',b);silenced=re.search(r'WEAPON_SOUND_SPECIAL1 = soundevent:"([^"]+)"',b)
  if key and single:weapons[key[1]]={'normal':single[1],'silenced':silenced[1] if silenced else None}
 result={'nodes':nodes,'weapons':weapons,'source_sha256':sources,'limits':'Piecewise-linear curve proxy; engine tangents/mixing/baked acoustics not reproduced; support radius is not guaranteed audibility.'}
 (ROOT/'data/sounds/profiles.json').write_text(json.dumps(result,indent=2));return result

def curve_components(profiles,key,seen=()):
 if key in seen or key not in profiles['nodes']:return []
 node=profiles['nodes'][key];return ([node['points']] if node['points'] else [])+sum([curve_components(profiles,k,seen+(key,)) for k in node['children']],[])
def sound_support(profiles,event,distance):
 if event.get('event_name')=='player_sound':
  radius=event.get('radius');return {'known':isinstance(radius,(int,float)) and radius>0,'in_support':isinstance(radius,(int,float)) and 0<=distance<radius,'radius':radius,'basis':'demo player_sound radius','confirmed_heard':False}
 weapon=event.get('weapon','');weapon=weapon if weapon.startswith('weapon_') else 'weapon_'+weapon
 mapping=profiles['weapons'].get(weapon,{});key=mapping.get('silenced' if event.get('silenced') else 'normal');curves=curve_components(profiles,key)
 if not curves:return {'known':False,'in_support':False,'confirmed_heard':False,'basis':'missing sound asset mapping'}
 radius=max(max(p[0] for p in curve) for curve in curves);amplitude=max(float(np.interp(distance,[p[0] for p in curve],[p[1] for p in curve],left=curve[0][1],right=0)) for curve in curves)
 return {'known':True,'in_support':0<=distance<radius and amplitude>0,'radius':radius,'unoccluded_curve_proxy':amplitude,'event':key,'basis':'local sound curve plus enabled child events','confirmed_heard':False}
if __name__=='__main__':
 p=build_profiles();print(json.dumps({'nodes':len(p['nodes']),'weapons':len(p['weapons']),'footstep_curve':p['nodes']['Base.Footstep']['points']}))
