import copy
import json
import pytest
from langchain_core.messages import AIMessage
from cs2_agent.studio import DIRECTORY,visible_players
from cs2_agent.studio_planner import PlanningHost,validate_plans,planning_packet,evidence_hash


def fixture():
    k={'routes':[{'id':'hold'},{'id':'retreat'}], 'other_actor_routes':{'ally':[{'id':'hold'}]}}
    plans=[{'route_id':r['id'],'title':'条件性方案','reason':'测试说明','objective':r['id'],'trigger':'观察条件','abort_condition':'信息改变','risks':['风险'],'assumptions':['假设'],
            'responses':{b:[{'player':'ally','route_id':'hold'}] for b in ('continue','cooperate','counter')},
            'response_notes':{b:'分支假设' for b in ('continue','cooperate','counter')}} for r in k['routes']]
    return k,plans


def test_hidden_enemy_never_enters_known_state():
    rows=[{'player':'self','side':'CT','alive':True,'position':[1,2,3]},
          {'player':'hidden','side':'T','alive':True,'position':[999,999,999],'hp':100},
          {'player':'spotted','side':'T','alive':True,'position':[4,5,6],'hp':100,'approximate_spotted_by':['self']}]
    result=visible_players(rows,'CT','self')
    assert {p['player'] for p in result}=={'self','spotted'}
    assert all('hp' not in p and 'approximate_spotted_by' not in p for p in result)


@pytest.mark.parametrize('invalid',['own_route','hidden_actor','actor_route','duplicate_plan','duplicate_actor'])
def test_rejects_unsupported_simulations(invalid):
    k,p=fixture()
    if invalid=='own_route':p[0]['route_id']='through_wall'
    if invalid=='hidden_actor':p[0]['responses']['counter'][0]['player']='hidden'
    if invalid=='actor_route':p[0]['responses']['counter'][0]['route_id']='through_wall'
    if invalid=='duplicate_plan':p[1]['route_id']='hold'
    if invalid=='duplicate_actor':p[0]['responses']['counter']*=2
    with pytest.raises(ValueError):validate_plans(p,k)


def test_real_agent_loop_reads_both_sources_then_submits(tmp_path):
    knowledge,plans=fixture()
    steps=[('finish_task',{'text':'premature'}),('read_decision_context',{}),('read_professional_references',{}),
           ('submit_decision_plans',{'plans':plans}),('finish_task',{'text':'offline fixture'})]
    class Model:
        def invoke(self,messages,tools):
            name,args=steps.pop(0)
            return AIMessage(content='',tool_calls=[{'id':str(len(steps)),'name':name,'args':args}])
    host=PlanningHost(tmp_path/'task',Model(),{'knowledge':knowledge,'references':[]})
    try:
        assert host.run(slice_steps=80)['reason']=='completed'
        assert host.state['calls']==5
        assert len(host.plans)==2
    finally:host.close()


def test_submit_requires_evidence(tmp_path):
    k,p=fixture();host=PlanningHost(tmp_path/'task',None,{'knowledge':k,'references':[]})
    try:
        assert host.submit(p)['accepted'] is False
        host.read_context()
        assert host.submit(p)['accepted'] is False
    finally:host.close()


def test_real_packets_have_no_future_or_unknown_actors():
    for row in json.loads((DIRECTORY/'index.json').read_text(encoding='utf-8')):
        packet=planning_packet(row['id']);k=packet['knowledge']
        assert not {'actual','death_tick','events','snapshot','history'} & k.keys()
        known={p['player'] for p in k['players']}
        assert set(k['other_actor_routes'])<=known
        before=evidence_hash(packet);changed=copy.deepcopy(packet);changed['knowledge']['tick']+=1
        assert before!=evidence_hash(changed)
        assert all('future' not in r or not r['future'] for r in packet['references'])


def test_spectator_and_utility_stay_outside_planner():
    identifier='49fabf21b1c26f10-3233-008503562d79'
    payload=json.loads((DIRECTORY/(identifier+'.json')).read_text(encoding='utf-8'))
    packet=planning_packet(identifier)
    assert any(p['role']=='enemy' and p['alive'] for p in payload['spectator'][0]['players'])
    assert any(e['kind']!='weapon_fire' for e in payload['replay_events'])
    assert any(len(g['samples'])>1 for g in payload['grenade_trajectories'])
    assert all(k not in packet['knowledge'] for k in ('spectator','replay_events','grenade_trajectories'))
    assert 'steamid' not in json.dumps(payload)


def test_long_clutch_and_self_response_normalization():
    identifier='49fabf21b1c26f10-clutch-12463-008503562d79'
    c=json.loads((DIRECTORY/(identifier+'.json')).read_text(encoding='utf-8'))
    assert c['duration']==35 and len(c['actual'])==141
    assert c['knowledge']['alive']['own']==1
    assert c['knowledge']['own_loadout']['weapon']=='SSG 08'
    assert len(c['routes'])>3
    k,p=fixture();k['actor']='self'
    p[0]['responses']['counter'].append({'player':'self','route_id':p[0]['route_id']})
    assert all(a['player']!='self' for a in validate_plans(p,k)[0]['responses']['counter'])


def test_persistent_smoke_has_duration():
    c=json.loads((DIRECTORY/'49fabf21b1c26f10-3233-008503562d79.json').read_text(encoding='utf-8'))
    smoke=next(e for e in c['replay_events'] if e['kind']=='smokegrenade_detonate' and e['time']>0)
    assert smoke['duration']>10
    assert smoke['duration_source'] in ('demo_event','illustrative_fallback')
    assert c['professional_paths'] and c['professional_paths'][0]['samples']


def test_rejects_explicit_wrong_alive_count():
    k,p=fixture();k['alive']={'own':1,'enemy':2};p[0]['reason']='1v1无队友'
    with pytest.raises(ValueError,match='alive counts'):validate_plans(p,k)
