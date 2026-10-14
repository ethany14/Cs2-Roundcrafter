import copy
import pytest
from cs2_agent.tactical_solver import intent,assess,command

def candidate():
 s=intent();return {**{k:s[k] for k in ['map','side','role','origin_area','target_area','next_area']},'position':[1.,2.,3.],'pitch':-30.,'yaw':90.,'mode':'stand_left','standable':True,'bounces':1,'reached_target':True}

def test_source_constraints_have_evidence():
 s=intent();assert s['release_clock']==106 and s['origin_area']=='Roof' and s['next_area']=='Ramp';assert '1:46' in s['source_steps'][0]
@pytest.mark.parametrize('field,value',[('origin_area','Heaven'),('role','bomb'),('side','CT'),('map','de_dust2'),('next_area','Secret'),('pitch',-89),('standable',False),('bounces',4),('reached_target',False),('mode','runjump')])
def test_unreasonable_candidates_rejected(field,value):
 c=candidate();c[field]=value;assert assess(intent(),c)['status']=='rejected'
def test_countdown_and_travel():
 c=candidate();s=intent();assert assess(s,c,{'clock':100})['blocked'];assert assess(s,c,{'clock':110,'travel_seconds':8})['blocked'];assert not assess(s,c,{'clock':110,'travel_seconds':2})['blocked']
def test_unknowns_never_certify():
 r=assess(intent(),candidate(),{'clock':110});assert r['status']=='practice_candidate' and not r['recommended'];assert any('耗时' in x for x in r['unknown'])
@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,True])
def test_invalid_context(value):
 with pytest.raises(ValueError):assess(intent(),candidate(),{'clock':value})
def test_command_rejects_injection():
 c=candidate();assert command(c)=='setpos 1.000000 2.000000 3.000000; setang -30.000000 90.000000 0.000000';c['position'][0]='1; quit'
 with pytest.raises(ValueError):command(c)
def test_flat_ground_simulator():
 from cs2_agent.geometry import Mesh
 from cs2_agent.grenade_search import simulate,standable
 m=Mesh([[[-10000,-10000,0],[10000,-10000,0],[10000,10000,0]],[[-10000,-10000,0],[10000,10000,0],[-10000,10000,0]]]);assert standable(m,[10,20,0]);assert not standable(m,[10,20,20]);r=simulate(m,[10,20,0],-20,0);assert r and r['settled'] and r['end'][0]>10 and abs(r['end'][2]-2)<.1
def test_unstable_is_rejected():
 c=candidate();c['robustness']={'passed':1,'tested':5};assert assess(intent(),c)['blocked']
def test_corridor_is_not_smoke_certification():
 from cs2_agent.grenade_search import corridor_screen
 r=corridor_screen([0,0,0],[{'from':[-500,0,50],'to':[500,0,50]}]);assert r['passed'];assert not corridor_screen([0,1000,0],[{'from':[-500,0,50],'to':[500,0,50]}])['passed'];assert not corridor_screen([0,0,0],[])['passed']
def test_wrong_corridor_rejected_even_stable():
 c=candidate();c['robustness']={'passed':5,'tested':5};c['target_corridor']={'tested':8,'intersections':1,'passed':False};assert any('枪线' in x for x in assess(intent(),c)['blocked'])
