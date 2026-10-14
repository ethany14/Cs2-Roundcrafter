import copy,json,math
import pytest
from cs2_agent.nuke_teaching import check,teaching,ROLES,ACTIONS
def sample():
 invs=[dict(smoke=1,flash=1,fire=1,he=1),dict(smoke=1,flash=2,fire=1,he=0),dict(smoke=1,flash=0,fire=0,he=0),dict(smoke=0,flash=0,fire=0,he=0),dict(smoke=1,flash=0,fire=1,he=0)]
 return dict(map='de_nuke',side='T',phase='opening',clock=115,players=[dict(id=f'P{i+1}',alive=True,cooperates=True,position_ready=True,has_c4=i==4,utility=inv) for i,inv in enumerate(invs)])
def test_complete_assigns_unique_roles_without_requiring_awp():
 r=check(sample());assert not r['blocked'];assert len({a['player'] for a in r['assignment']})==5;assert not r['ready_for_recommendation']
def test_team_totals_do_not_replace_individual_inventory():
 s=sample();s['players'][1]['utility']['flash']=1;s['players'][3]['utility']['flash']=1
 assert sum(p['utility']['flash'] for p in s['players'])==3
 assert check(s)['blocked']
def test_duplicate_flash_occurrences_count_twice():
 s=sample();s['players'][1]['utility']['flash']=1;assert check(s)['blocked']
def test_swap_people_can_match():
 s=sample();s['players'][0],s['players'][1]=s['players'][1],s['players'][0];assert not check(s)['blocked']
@pytest.mark.parametrize('field',['alive','cooperates'])
def test_missing_participant(field):
 s=sample();s['players'][3][field]=False;assert check(s)['blocked']
def test_unknown_inventory_not_satisfied():
 s=sample();s['players'][1]['utility']=None;r=check(s);assert any('未知' in u for u in r['unknown']);assert not r['ready_for_recommendation']
def test_countdown_and_missed_window():
 s=sample();s['clock']=90;assert any('错过' in b for b in check(s)['blocked'])
def test_history_requires_fixed_assignment_and_dependencies():
 s=sample();s['clock']=100;s['completed']=[dict(id='nades',clock=100)]
 with pytest.raises(ValueError):check(s)
 s['assignment']=dict(zip(ROLES,[f'P{i+1}' for i in range(5)]));assert any('顺序' in b for b in check(s)['blocked'])
def test_completed_consumption_and_future_event_validation():
 s=sample();s['assignment']=dict(zip(ROLES,[f'P{i+1}' for i in range(5)]));s['clock']=105;s['completed']=[dict(id='outside_smoke',clock=113),dict(id='vent_smoke',clock=112),dict(id='heaven_smoke',clock=106),dict(id='hut_fire',clock=106)]
 for i,k in [(4,'smoke'),(2,'smoke'),(1,'smoke'),(4,'fire')]:s['players'][i]['utility'][k]-=1
 assert not check(s)['blocked'];s['completed'][0]['clock']=90
 with pytest.raises(ValueError):check(s)
@pytest.mark.parametrize('value',[-1,True,3])
def test_invalid_inventory(value):
 s=sample();s['players'][0]['utility']['smoke']=value
 with pytest.raises(ValueError):check(s)
def test_actual_teaching_provenance_and_unverified_status():
 d=teaching();assert d['demo_count']==10 and d['observed_throw_count']>1000
 assert next(x for x in d['lessons'] if x['id']=='6518')['candidates']==[]
 assert any(t['candidates'] for t in d['lessons'])
 for t in d['lessons']:
  for m in t['candidates']:
   assert m['status']=='spatial_candidate_needs_review';c=d['cases'][m['case_id']]
   assert c['team']==2 and c['type']==t['kind'] and c['release']['area'] in t['origin']
   assert c['throw_tick']<=c['effect_tick'] and c['path'][-1][0]<=c['effect_tick'];assert len(c['demo_sha256'])==64
   assert all(math.isfinite(v) for p in c['path'] for v in p)

def test_observed_methods_do_not_invent_keys_or_certify_lineup():
 d=teaching();assert len(d['cases'])==15
 for c in d['cases'].values():
  m=c['method'];assert m['status']=='observed_active_grenade_fields';assert c['throw_tick']-16<=m['sample_tick']<=c['throw_tick'];assert m['physical_key_sequence'] is None
  assert 0<=m['strength']<=1;assert not c['anchors']['practice_verified']
  a=c['anchors']['stable_before_throw']
  if a:assert c['throw_tick']-128<=a['tick']<=c['throw_tick']

def test_geometry_ray_and_stability():
 import importlib.util
 import numpy as np
 from cs2_agent.casebook import ROOT
 spec=importlib.util.spec_from_file_location('anchors',ROOT/'experiments/knowledge/compute_throw_anchors.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 tri=np.array([[[10,-10,-10],[10,10,-10],[10,0,10]]],dtype=float)
 assert np.allclose(mod.ray_hit(tri,np.zeros(3),np.array([1,0,0])),[10,0,0]);assert mod.ray_hit(tri,np.zeros(3),np.array([-1,0,0])) is None
 assert mod.anchor([dict(tick=i,position=[0,0,0]) for i in range(20)],19)['tick']==19
 assert mod.anchor([dict(tick=i,position=[i,0,0]) for i in range(20)],19) is None
