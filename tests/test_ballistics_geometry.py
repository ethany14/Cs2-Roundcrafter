import numpy as np
import pytest
from cs2_agent.solid_geometry import clip_planes
from cs2_agent.ballistics_experiment import direct_damage,candidate_wall_damage


def cube():
    return np.array([[1,0,0,10],[-1,0,0,0],[0,1,0,10],[0,-1,0,0],[0,0,1,10],[0,0,-1,0]],float)


def test_closed_solid_thickness_and_inside_segment():
    assert clip_planes(cube(),[-5,5,5],[15,5,5])==(.25,.75)
    assert clip_planes(cube(),[5,5,5],[15,5,5])==(0.,.5)
    assert clip_planes(cube(),[-5,15,5],[15,15,5]) is None
    assert clip_planes(cube(),[-5,5,5],[-1,5,5]) is None


def test_armor_hitgroup_range_and_no_wall_claim():
    weapon={'m_nDamage':36,'m_flRangeModifier':.98,'m_flHeadshotMultiplier':4,'m_flArmorRatio':1.55,'m_flRange':8192,'m_flPenetration':2}
    assert direct_damage(weapon,0,'head',100,False)==144
    assert direct_damage(weapon,0,'head',100,True)==111
    assert direct_damage(weapon,0,'left_leg',100,True)==27
    assert direct_damage(weapon,0,'chest',1,True)==34
    with pytest.raises(ValueError):direct_damage(weapon,float('nan'),'head',0,False)
    with pytest.raises(ValueError):direct_damage(weapon,0,'generic',0,False)
    layer={'entry_fraction':.1,'exit_fraction':.2,'thickness_units':10,'material':'wood','collision_tags':['passbullets'],'segment_starts_inside':False,'segment_ends_inside':False}
    with pytest.raises(ValueError,match='Conditional'):candidate_wall_damage(weapon,100,'head',100,True,[layer],{})


def test_damage_tool_rejects_unknown_or_invalid_inputs():
    from cs2_agent.ballistics_experiment import estimate_direct_hit
    with pytest.raises(ValueError):estimate_direct_hit({'weapon':'ak47','distance_units':100,'hitgroup':'head','armor':-1,'helmet':True})
    with pytest.raises(ValueError):estimate_direct_hit({'weapon':'ak47','distance_units':True,'hitgroup':'head','armor':100,'helmet':True})
    with pytest.raises(ValueError):estimate_direct_hit({'weapon':'hegrenade','distance_units':100,'hitgroup':'head','armor':100,'helmet':True})


def test_registered_damage_tool_keeps_wall_and_knowledge_boundaries(tmp_path,monkeypatch):
    import json
    from cs2_agent import ballistics_experiment
    from cs2_agent.casebook_tools import casebook_tools
    assets=tmp_path/'data/maps';assets.mkdir(parents=True)
    weapon={'m_nDamage':36,'m_flRangeModifier':.98,'m_flHeadshotMultiplier':4,'m_flArmorRatio':1.55,'m_flRange':8192,'m_flPenetration':2}
    (assets/'weapon-ballistics.json').write_text(json.dumps({'weapons':{'weapon_ak47':weapon}}))
    monkeypatch.setattr(ballistics_experiment,'ROOT',tmp_path)
    tool=next(t for t in casebook_tools() if t.name=='estimate_direct_hit_damage')
    result=tool.execute({'weapon':'ak47','distance_units':500,'hitgroup':'head','armor':100,'helmet':True})
    assert result['damage']==109
    assert not result['wall_damage_supported']
    assert 'hypothetical' in result['knowledge_boundary']
