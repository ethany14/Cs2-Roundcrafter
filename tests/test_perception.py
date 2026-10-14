import copy
import numpy as np
from cs2_agent.geometry import Mesh,smoke_intersects,sight
from cs2_agent.perception import reconstruct


def wall():
    mesh=Mesh([[[5,-10,-10],[5,10,-10],[5,10,100]],[[5,-10,-10],[5,10,100],[5,-10,100]]]);mesh.sha256='fixture'
    return mesh


def player(identifier,side,x,spotted=None):
    return {'player':identifier,'side':side,'alive':True,'position':[x,0,0],'yaw':0,'pitch':0,
            'duck_amount':0,'flash_duration':0,'hp':83,'equipment':1234,'approximate_spotted_by':spotted or []}


def test_segment_wall_endpoints_and_reverse():
    m=wall()
    assert m.blocked([0,0,64],[10,0,64])
    assert m.blocked([10,0,64],[0,0,64])
    assert not m.blocked([0,0,64],[4,0,64])
    assert not m.blocked([0,20,64],[10,20,64])


def test_smoke_respects_time_and_expiry():
    s=[{'start_tick':10,'expired_tick':20,'position':[5,0,0]}]
    assert not smoke_intersects([0,0,64],[10,0,64],s,9)
    assert smoke_intersects([0,0,64],[10,0,64],s,15)
    assert not smoke_intersects([0,0,64],[10,0,64],s,20)


def test_view_cone_is_not_visibility():
    a,b=player('a','CT',0),player('b','T',10)
    r=sight(wall(),a,b,[],10)
    assert r['within_approximate_view_cone'] and not r['static_ray_clear']
    a['yaw']=180
    assert not sight(wall(),a,b,[],10)['within_approximate_view_cone']


def test_future_spots_and_enemy_health_never_enter_player_information():
    a,b=player('a','CT',0,['b']),player('b','T',10,['a'])
    c={'id':'fixture','tick':100,'actor':'a','side':'CT','tick_rate':64,'features':{'own_alive':1},
       'evidence':{'snapshot':[a,b],'history':[{'tick':90,'players':[a,b]},{'tick':101,'players':[a,b]}],'smokes':[]}}
    info=reconstruct(c,wall())['player_information']
    assert len(info['recent_spotting_evidence'])==1
    assert info['last_reported_enemies'][0]['tick']==90
    assert 'hp' not in info['last_reported_enemies'][0]
    assert 'equipment' not in info['last_reported_enemies'][0]
    assert 'approximate_spotted_by' not in info['self']


def test_clear_geometry_never_creates_known_enemy():
    a,b=player('a','CT',0),player('b','T',2)
    c={'id':'fixture','tick':100,'actor':'a','side':'CT','tick_rate':64,'features':{'own_alive':1},
       'evidence':{'snapshot':[a,b],'history':[{'tick':100,'players':[a,b]}],'smokes':[]}}
    result=reconstruct(c,wall())
    assert result['spectator_geometry']['actor_to_enemies'][0]['static_ray_clear']
    assert result['player_information']['last_reported_enemies']==[]
    assert not result['decision_gate']['can_score_decision']


def test_geometry_unknown_flash_is_not_unflashed():
    a,b=player('a','CT',0),player('b','T',2);a['flash_duration']=None
    assert sight(wall(),a,b,[],10)['flash_state']=='unknown'


def test_obj_coordinate_conversion(tmp_path):
    path=tmp_path/'wall.obj'
    path.write_text('v -0.254 -0.254 0.127\nv 0.254 -0.254 0.127\nv 0.254 2.54 0.127\nv -0.254 2.54 0.127\nf 1 2 3\nf 1 3 4\n')
    assert Mesh.from_obj(path).blocked([0,0,64],[10,0,64])


def test_offline_report_is_markdown(tmp_path):
    from cs2_agent.review import write_packet_report
    dest=tmp_path/'report.md'
    write_packet_report({'candidate':{'match_id':'m','map':'de_dust2','round':1,'tick':100,'source_url':'https://example.com'},
                         'retrieval':{'matches':[]},'player_information':{'status':'not_enriched'}},dest)
    content=dest.read_text(encoding='utf-8')
    assert content.startswith('# 局势证据报告') and 'not_enriched' in content
