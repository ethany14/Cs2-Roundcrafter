import threading
import numpy as np
import pytest
from cs2_agent.free_lab import validate, solve
from cs2_agent.geometry import Mesh

def request(**kw):
    return {'map':'de_nuke','origin':[0,0,.5],'target':[500,0,2],'radius':64,'seconds':10,'max_simulations':120,**kw}

@pytest.mark.parametrize('change',[{'origin':[0,0,float('nan')]},{'seconds':10000},{'max_simulations':10000},{'mode':'jump'},{'map':'../../bad'},{'target':[0,0]},{'radius':True}])
def test_invalid_requests(change):
    with pytest.raises(ValueError):validate(request(**change))

def floor():
    return Mesh(np.array([[[-10000,-10000,0],[10000,-10000,0],[10000,10000,0]],[[-10000,-10000,0],[10000,10000,0],[-10000,10000,0]]]))

def test_real_physics_search_on_synthetic_floor():
    # Actual numerical/collision model, synthetic geometry; not a game validation.
    r=solve(request(),mesh=floor())
    assert r['simulations']<=120
    assert r['candidates'] and r['status']=='experimental_candidates'
    for c in r['candidates']:
        assert c['distance']<=64 and not c['game_validated']
        assert c['practice_command'].startswith('setpos')

def test_cancellation_and_invalid_footing():
    e=threading.Event();e.set()
    assert solve(request(),e,mesh=floor())['status']=='cancelled'
    assert solve(request(origin=[0,0,100]),mesh=floor())['status']=='invalid_origin'

def test_no_fabricated_candidate_out_of_range():
    r=solve(request(target=[15000,0,0],max_simulations=10),mesh=floor())
    assert r['simulations']==10 and not r['candidates']
    assert r['status']=='budget_exhausted'


def test_result_is_json_serializable():
    import json
    json.dumps(solve(request(max_simulations=10),mesh=floor()))

@pytest.mark.parametrize('name',['de_nuke','de_mirage','de_inferno','de_dust2','de_ancient','de_anubis','de_cache'])
def test_official_radar_roundtrip(name):
    from cs2_agent.radar_maps import metadata,world_to_uv,uv_to_world,image_path
    m=metadata(name)
    assert m['width']==1024 and m['height']==1024 and image_path(name).exists()
    for uv in [[0,0],[1,1],*[v for v in m['landmarks'].values()]]:
        assert world_to_uv(m,uv_to_world(m,uv))==pytest.approx(uv)
    if name=='de_nuke':assert m['floor_split_z']==-495 and image_path(name+'_lower').exists()


def test_auto_compares_jump_after_standing_failure():
    r=solve(request(mode='auto',target=[2300,0,2],max_simulations=180),mesh=floor())
    assert r['mode_decision']['code']=='jump_recommended'
    assert [x['mode'] for x in r['mode_checks']]==['stand_left','jump_left']
    assert r['simulations']<=180
    assert all(c['mode']=='jump_left' and c['launch_assumptions']['added_vz']>0 for c in r['candidates'])
    assert '必须' in r['mode_decision']['message']  # explicitly says this is NOT a necessity proof


def test_auto_prefers_standing_when_sufficient():
    r=solve(request(mode='auto'),mesh=floor())
    assert r['mode_decision']['code']=='standing_sufficient'
    assert len(r['mode_checks'])==1


def test_low_ceiling_blocks_jump_but_not_standing():
    from cs2_agent.grenade_search import jump_release,standable
    triangles=list(floor().tri.reshape(-1,3,3))
    triangles.extend([[[-100,-100,85],[100,100,85],[100,-100,85]],
                      [[-100,-100,85],[-100,100,85],[100,100,85]]])
    m=Mesh(np.array(triangles))
    assert standable(m,[0,0,.5])
    assert jump_release(m,[0,0,.5]) is None
    r=solve(request(mode='jump_left'),mesh=m)
    assert r['status']=='jump_blocked' and not r['candidates']
    assert r['mode_decision']['code']=='unknown'


def test_auto_cancellation_does_not_recommend_jump():
    e=threading.Event()
    def progress(d):e.set()
    r=solve(request(mode='auto',target=[2300,0,2]),e,progress,mesh=floor())
    assert r['status']=='cancelled' and not r['candidates']
    assert r['mode_decision']['code']=='unknown'


@pytest.mark.parametrize('mode',['w_jump_left','crouch_jump_left','run_jump_left'])
def test_new_movement_profiles_reach_independent_target(mode):
    from cs2_agent.throw_movement import movement_release
    m=floor();launch=movement_release(m,[0,0,.5],0,mode,128)
    assert launch is not None
    if mode=='w_jump_left':assert launch['player_horizontal_speed']==30 and launch['run_distance']==0
    if mode=='crouch_jump_left':assert launch['eye_height']==46 and launch['added_vz']>218.86838*1.25
    if mode=='run_jump_left':
        assert launch['jump_point']==pytest.approx([128,0,.5])
        assert launch['player_horizontal_speed']>200 and len(launch['ground_path'])>2
    r=solve(request(mode=mode,target=[1500,0,2],max_simulations=180),mesh=m)
    assert r['candidates']
    assert all(c['mode']==mode and c['execution_steps'] for c in r['candidates'])


def test_runup_rejects_wall_and_unsupported_floor():
    from cs2_agent.throw_movement import movement_release
    wall=[[[60,-100,0],[60,100,150],[60,100,0]],[[60,-100,0],[60,-100,150],[60,100,150]]]
    m=Mesh(np.concatenate([floor().tri.reshape(-1,3,3),np.array(wall)]))
    assert movement_release(m,[0,0,.5],0,'run_jump_left',128) is None
    assert movement_release(floor(),[9990,0,.5],0,'run_jump_left',128) is None


def test_all_modes_budget_and_unknown_result():
    r=solve(request(mode='auto_all',target=[15000,0,2],max_simulations=25),mesh=floor())
    assert len(r['mode_checks'])==5 and r['simulations']<=25
    assert not r['candidates'] and r['mode_decision']['code']=='unknown'

@pytest.mark.parametrize('distance',[-1,0,300,float('nan'),True])
def test_invalid_run_distance(distance):
    with pytest.raises(ValueError):validate(request(mode='run_jump_left',run_distance=distance))


def test_all_modes_continue_after_first_hit_and_sort():
    r=solve(request(mode='auto_all',target=[500,0,2],max_simulations=400,seconds=20),mesh=floor())
    assert len(r['mode_checks'])==5
    assert all(c['status']!='not_started' for c in r['mode_checks'])
    assert len({c['mode'] for c in r['candidates']})>=3
    assert any(c['mode']=='stand_left' for c in r['candidates'])
    keys=[(c['difficulty_rank'],c['distance']) for c in r['candidates']]
    assert keys==sorted(keys)
    assert r['simulations']<=400 and r['mode_decision']['code']=='choose_candidate'


def test_cancel_all_marks_unattempted_and_clears_candidates():
    e=threading.Event()
    def progress(d):e.set()
    r=solve(request(mode='auto_all'),e,progress,mesh=floor())
    assert r['status']=='cancelled' and not r['candidates']
    assert len(r['mode_checks'])==5
    assert all(x['status']=='not_started' for x in r['mode_checks'][1:])
