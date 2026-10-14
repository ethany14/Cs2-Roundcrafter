import copy
import numpy as np
from cs2_agent.acoustics import sound_support
from cs2_agent.environment_evidence import build,NAMES,active,intersections

class Clear:
 def intersections(self,*args,**kwargs):return []

def fixture():
 actor={'steamid':'1','team_num':2,'X':0,'Y':0,'Z':0,'yaw':0,'pitch':0,'is_alive':True,'flash_duration':0,'flash_max_alpha':255}
 enemy={**actor,'steamid':'2','team_num':3,'X':100,'approximate_spotted_by':[]}
 frames=[{**p,'tick':t} for t in [64,96,128] for p in [actor,enemy]]
 return {'frames':frames,'events':[]},{'actor':'1','tick':128,'start':0,'ticks':[64,96,128]},{'weapons':{},'nodes':{}}

def vector(raw,sample,profiles):return build(raw,sample,Clear(),profiles,'hash','test')[0]

def test_sound_radius_boundary_and_children():
 assert sound_support({}, {'event_name':'player_sound','radius':1100},1099)['in_support']
 assert not sound_support({}, {'event_name':'player_sound','radius':1100},1100)['in_support']
 p={'weapons':{'weapon_test':{'normal':'base','silenced':None}},'nodes':{'base':{'points':[[0,1],[100,0]],'children':['far']},'far':{'points':[[100,.5],[1000,0]],'children':[]}}}
 assert sound_support(p,{'weapon':'test'},500)['in_support']
 assert not sound_support(p,{'weapon':'test','silenced':True},50)['known']

def test_future_and_hidden_coordinates_do_not_change_features():
 raw,sample,p=fixture();before=vector(raw,sample,p)
 for frame in raw['frames']:
  if frame['steamid']=='2':frame['X']=9000
 raw['frames'].append({**raw['frames'][0],'steamid':'2','team_num':3,'tick':160,'approximate_spotted_by':['1']});sample['ticks'].append(160)
 raw['events'].append({'event_name':'player_sound','tick':129,'user_steamid':'2','radius':1100,'step':True,'user_X':50,'user_Y':0,'user_Z':0})
 np.testing.assert_array_equal(before,vector(raw,sample,p))

def test_last_seen_stale_and_flash_inactive():
 raw,sample,p=fixture();raw['frames'][1]['approximate_spotted_by']=['1'];first=vector(raw,sample,p)
 raw['frames'][-1]['X']=8000
 np.testing.assert_array_equal(first,vector(raw,sample,p))
 v=dict(zip(NAMES,first));assert v['last_seen_valid']==1 and v['last_seen_forward']==.05
 assert v['last_seen_age']==.5 and v['self_flash_alpha']==0 and v['wall_damage_valid']==0

def test_unknown_sound_is_not_global_activity_signal():
 raw,sample,p=fixture();a=vector(raw,sample,p);raw['events']=[{'event_name':'weapon_fire','tick':100,'user_steamid':'2','weapon':'unknown','user_X':100,'user_Y':0,'user_Z':0}]
 np.testing.assert_array_equal(a,vector(raw,sample,p))

def test_effect_expiry_and_entity_reuse_are_causal():
 events=[{'event_name':'start','entityid':1,'tick':1},{'event_name':'end','entityid':1,'tick':4},{'event_name':'start','entityid':1,'tick':8},{'event_name':'end','entityid':1,'tick':12}]
 assert len(active(events,'start','end',3,0))==1
 assert len(active(events,'start','end',5,0))==0
 assert active(events,'start','end',10,0)[0]['tick']==8

def test_fixed_dust2_cover_included():
 class Wall(Clear):
  def intersections(self,*args,**kwargs):return [{'fraction':.4}]
 mesh=Clear();mesh.doors=Wall();assert intersections(mesh,[0,0,0],[1,0,0],1)==[{'fraction':.4}]

def test_agent_reads_filtered_evidence(tmp_path,monkeypatch):
 import json
 import cs2_agent.environment_tools as tool_module
 monkeypatch.setattr(tool_module,'ROOT',tmp_path)
 env=tmp_path/'outputs/movement/environment';env.mkdir(parents=True);comp=tmp_path/'outputs/movement/comparison';comp.mkdir()
 (comp/'rows.json').write_text(json.dumps([{'demo':'abc','index':4,'map':'test','tick':128}]))
 (env/'feature-schema.json').write_text(json.dumps({'names':['wall_damage_valid']}))
 (env/'abc.json').write_text(json.dumps([{'index':4,'features':[0],'details':{'sounds':[]}}]))
 tool=tool_module.environment_tools()[0];assert 'error' in tool.execute({'sample_index':-1})
 answer=tool.execute({'sample_index':0});assert answer['features']['wall_damage_valid']==0 and not answer['ready_for_tactical_advice']
