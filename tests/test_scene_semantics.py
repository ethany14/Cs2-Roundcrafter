import numpy as np
from cs2_agent.geometry import Mesh,sight
from cs2_agent.smoke import cylinder_interval,assess


def test_vertical_smoke_segment_crosses_even_if_start_above_cloud():
    assert cylinder_interval([0,0,300],[0,0,-100],np.array([0,0,0]))==(.3,.85)
    assert cylinder_interval([201,0,300],[201,0,-100],np.array([0,0,0])) is None


def test_smoke_disturbance_is_uncertain_not_clear_and_has_no_future_leak():
    smoke=[{'entity_id':1,'start_tick':1,'expired_tick':None,'position':[0,0,0],
            'voxel_updates':[{'tick':20,'revision':1},{'tick':101,'revision':2}]}]
    disturbances={'he':[{'tick':90,'position':[0,0,0]},{'tick':101,'position':[0,0,0]}]}
    result=assess([-300,0,64],[300,0,64],smoke,100,64,disturbances)
    assert result['status']=='disturbed_opacity_unknown'
    assert result['overlaps'][0]['latest_voxel_update']['revision']==1
    assert len(result['overlaps'][0]['disturbances'])==1
    smoke[0]['expired_tick']=100
    assert not assess([-300,0,64],[300,0,64],smoke,100)['overlaps']


def test_only_forward_shot_ray_is_disturbance_candidate():
    smoke=[{'start_tick':1,'expired_tick':None,'position':[0,0,0]}]
    event={'tick':99,'origin':[-500,0,64],'angles':[0,180]}
    result=assess([-300,0,64],[300,0,64],smoke,100,64,{'shots':[event]})
    assert not result['overlaps'][0]['disturbances']
    event['angles']=[0,0]
    assert assess([-300,0,64],[300,0,64],smoke,100,64,{'shots':[event]})['overlaps'][0]['disturbances']


def test_material_collision_never_becomes_bulletproof_or_opaque():
    mesh=Mesh([[[5,-10,-10],[5,10,-10],[5,10,100]],[[5,-10,-10],[5,10,100],[5,-10,100]]])
    mesh.surface_ids=np.array([0,0]);mesh.surfaces=[{'SurfaceProperty':'chainlink','InteractAs':['passbullets']}]
    actor={'position':[0,0,0],'yaw':0,'pitch':0,'flash_duration':0,'duck_amount':0}
    target={**actor,'position':[10,0,0]}
    result=sight(mesh,actor,target,[],100)
    assert not result['static_ray_clear']
    assert result['line_of_fire']['can_penetrate'] is None
    assert result['line_of_fire']['head_ray_crossings'][0]['bullet_evidence']=='explicit_passbullets_tag'
    assert result['line_of_fire']['head_ray_crossings'][0]['visual_evidence']=='possibly_transparent_or_perforated'


def test_ray_hits_are_sorted_not_bvh_visit_order():
    mesh=Mesh([[[8,-10,-10],[8,10,-10],[8,10,100]],[[2,-10,-10],[2,10,-10],[2,10,100]]])
    hits=mesh.intersections([0,0,10],[10,0,10])
    assert [round(h['distance_units']) for h in hits]==[2,8]


def test_ladder_surface_index_alone_does_not_imply_climbing():
    from cs2_agent.perception import reconstruct
    from test_perception import wall,player
    actor=player('a','CT',0);enemy=player('b','T',10)
    actor.update(move_type=2,ladder_surface_index=10)
    c={'id':'fixture','tick':100,'actor':'a','side':'CT','tick_rate':64,'features':{'own_alive':1},
       'evidence':{'snapshot':[actor,enemy],'history':[{'tick':100,'players':[actor,enemy]}],'smokes':[]}}
    assert reconstruct(c,wall())['player_information']['movement_context']['on_ladder'] is False
    actor['move_type']=9
    assert reconstruct(c,wall())['player_information']['movement_context']['on_ladder'] is True
