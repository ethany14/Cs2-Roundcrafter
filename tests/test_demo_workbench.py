"""Workbench contracts on tiny hand-computable rounds. Offline: model is a stub, not live acceptance."""
import copy,json,os,threading,time
import pytest
from langchain_core.messages import AIMessage
from cs2_agent import demo_workbench as wb

A,B,C,D='a'*32,'b'*32,'c'*32,'d'*32

def frames(path,hz=4,duration=10,dead_after=None,missing=(),floor_z=0,extra=None):
    """path(t)->(x,y) for P1 (T). P6 is a static CT. Positions in world units; test radar is identity-ish."""
    out=[];n=int(duration*hz)
    for i in range(n+1):
        t=i/hz;x,y=path(t);players=[]
        if not any(lo<=t<hi for lo,hi in missing):
            players.append({'id':'P1','side':'T','position':[x,y,floor_z],'alive':dead_after is None or t<dead_after,'area':'BombsiteB' if x>=500 else 'Mid','inventory':['AK-47','Smoke Grenade'],'hp':100,'yaw':0,'weapon':'ak-47'})
        players.append({'id':'P6','side':'CT','position':[900,900,0],'alive':True,'area':'CTSpawn','inventory':['M4A1-S'],'hp':100,'yaw':0,'weapon':'m4a1'})
        if extra:players+=extra(t)
        out.append({'tick':1000+i*(64//hz),'seconds':t,'players':players})
    return out

def write_match(base,mid,name,rounds,kind='professional',verified=True,sha=None,map_='de_dust2',created=0):
    d=base/mid;d.mkdir(parents=True)
    (d/'state.json').write_text(json.dumps({'id':mid,'name':name,'status':'completed','created_at':created,'sha256':sha or mid}))
    (d/'identity.json').write_text(json.dumps({'kind':kind,'verified':verified,'source_url':'https://example.com' if kind=='professional' else None,'basis':'test'}))
    rows=[]
    for n,r in enumerate(rounds,1):
        r={'number':n,'source_round':n,'start_tick':1000,'end_tick':1000+int(r['duration']*64),**r}
        (d/f'round-{n}.json').write_text(json.dumps(r));rows.append({'number':n,'duration':r['duration'],'winner':r['winner']})
    obs={'map':map_,'tick_rate':64,'rounds':rows}
    (d/'observations.json').write_text(json.dumps(obs));(d/'result.json').write_text(json.dumps({**obs,'tactics':[]}))
    return d

def rnd(path=lambda t:(100,100),duration=10,winner='T',events=(),**kw):
    return {'duration':duration,'winner':winner,'frames':frames(path,duration=duration,**kw),'events':list(events)}

def plant(t,x=600):return {'id':f'e-plant','type':'bomb_planted','tick':1000+int(t*64),'seconds':t,'actor':'P1','side':'T','position':[x,100,0],'entity':None}

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setattr(wb.dr,'BASE',tmp_path)
    monkeypatch.setattr(wb.dr,'JOBS',{})
    meta={'pos_x':0,'pos_y':1024,'scale':1,'lower_url':None,'floor_split_z':None}
    monkeypatch.setattr(wb,'radar',lambda m:dict(meta,lower_url='x',floor_split_z=-100) if m=='de_nuke' else meta)
    for c in (wb._CACHE,wb._ROUNDS,wb._SUPP):c.clear()
    yield tmp_path
    for c in (wb._CACHE,wb._ROUNDS,wb._SUPP):c.clear()

def q(**kw):return {'map':'de_dust2','group':'pro_verified','side':'T','window':[0,20],**kw}

def test_groups_stay_separate_and_duplicates_collapse(env):
    write_match(env,A,'pro.dem',[rnd()],sha='same',created=2)
    write_match(env,B,'copy.dem',[rnd()],sha='same',created=1,kind='unknown',verified=False)
    write_match(env,C,'declared.dem',[rnd()],verified=False)
    write_match(env,D,'mine.dem',[rnd()],kind='player',verified=False)
    cat={m['id']:m for m in wb.catalog()}
    assert set(cat)=={A,C,D} and cat[A]['duplicates']==[B]  # verified copy wins, unknown copy never indexed twice
    assert [m['id'] for m in wb.run_query(q())['matches']]==[A]
    assert [m['id'] for m in wb.run_query(q(group='pro_declared'))['matches']]==[C]
    assert [m['id'] for m in wb.run_query(q(group='player'))['matches']]==[D]
    assert wb.run_query(q(group='unknown'))['matches']==[]

def test_missing_alignment_is_excluded_not_substituted(env):
    write_match(env,A,'m.dem',[rnd(events=[plant(5)]),rnd(),rnd(winner='CT')])
    r=wb.run_query(q(alignment='plant'))
    assert r['counts']['rounds']==1 and {e['reason']:e['count'] for e in r['excluded']}=={'missing_alignment':2}
    assert r['selection'][0]['anchor']==5 and r['selection'][0]['window']==[5,10]  # clipped to round end, never padded
    assert wb.run_query(q(outcome='win'))['counts']['rounds']==2

def test_alive_time_outside_round_and_window(env):
    write_match(env,A,'m.dem',[rnd(dead_after=4)])
    r=wb.run_query(q(alive={'at':'time','time':30,'own_min':1}))
    assert r['excluded'][0]['reason']=='alive_time_out_of_range'
    assert wb.run_query(q(alive={'at':'time','time':2,'own_min':1}))['counts']['rounds']==1
    assert wb.run_query(q(alive={'at':'time','time':6,'own_min':1}))['excluded'][0]['reason']=='alive'
    assert wb.run_query(q(window=[50,60]))['excluded'][0]['reason']=='window_out_of_range'

def test_unchecked_rounds_and_cache_invalidation(env):
    d=write_match(env,A,'m.dem',[rnd(),rnd()])
    r=wb.run_query(q());assert r['counts']['rounds']==2 and not r['usage']['cache_hit']
    assert wb.run_query(q())['usage']['cache_hit']
    r=wb.run_query(q(),[f'{A}:1']);assert r['counts']['rounds']==1 and r['excluded'][0]['reason']=='unchecked'
    time.sleep(.01);(d/'result.json').write_text((d/'result.json').read_text());os.utime(d/'result.json')
    assert not wb.run_query(q())['usage']['cache_hit']

def test_zone_passed_vs_at_instant(env):
    write_match(env,A,'m.dem',[rnd(path=lambda t:(100+60*t,100))])  # x crosses 500 at t≈6.67
    rect=[480,0,700,200]
    assert wb.run_query(q(zone={'mode':'passed','rect':rect}))['counts']['rounds']==1
    assert wb.run_query(q(zone={'mode':'at','time':2,'rect':rect}))['counts']['rounds']==0
    assert wb.run_query(q(zone={'mode':'at','time':8,'rect':rect}))['counts']['rounds']==1
    hits=wb.zone_rounds(q(),[],{'mode':'passed','rect':rect})['hits']
    assert hits[0]['raw_seconds']==pytest.approx(6.5) and hits[0]['evidence']['round']==1
    with pytest.raises(ValueError):wb.normalize(q(zone={'mode':'passed'}))

def test_dwell_is_hand_computable_and_sampling_invariant(env):
    # Stationary 10 s at (100,100): dwell in cell = 10 s at any sampling rate.
    write_match(env,A,'four.dem',[rnd(duration=10)])
    write_match(env,B,'two.dem',[{'duration':10,'winner':'T','frames':frames(lambda t:(100,100),hz=2,duration=10),'events':[]}])
    h4=wb.heat_grid(q(matches=[A]),metric='dwell',cell=16);h2=wb.heat_grid(q(matches=[B]),metric='dwell',cell=16)
    assert h4['cells']==[[6,57,10.0,1.0]] and h2['cells']==[[6,57,10.0,1.0]]
    assert h4['observed_seconds']==10.0==h2['observed_seconds']

def test_dead_and_missing_samples_not_counted(env):
    write_match(env,A,'m.dem',[rnd(duration=10,dead_after=4,missing=[(1,2)])])
    h=wb.heat_grid(q(),metric='dwell',cell=16)
    # alive 0–4 s minus missing 1–2 s; the 0.75→1 interval is kept only when the next sample exists within GAP
    assert h['observed_seconds']==pytest.approx(3.0,abs=.26)
    assert h['cells'][0][2]==pytest.approx(h['observed_seconds'])

def test_reach_rate_denominator_is_valid_rounds(env):
    write_match(env,A,'m.dem',[rnd(path=lambda t:(100+60*t,100)),rnd(path=lambda t:(100,100))])
    h=wb.heat_grid(q(),metric='reach',cell=16)
    cells={(c[0],c[1]):c for c in h['cells']}
    assert h['valid_rounds']==2 and cells[(6,57)][3]==1.0 and cells[(40,57)][3]==.5
    # contiguous segment walk: every cell between 100 and 700 is visited despite 15-unit steps
    assert all((x,57) in cells for x in range(6,44))
    contrib=wb.heat_cell(q(),[], 'reach','upper',16,40,57)
    assert [c['round'] for c in contrib['contributors']]==[1] and contrib['contributors'][0]['players']==['P1'] and contrib['contributors'][0]['evidence']['match']==A

def test_nuke_floor_isolation_and_scoped_requires_field(env):
    lower=lambda t:[{'id':'P2','side':'T','position':[100,100,-300],'alive':True,'area':'Ramp','inventory':[],'hp':100,'yaw':0,'weapon':None}]
    write_match(env,A,'n.dem',[rnd(extra=lower)],map_='de_nuke')
    up=wb.heat_grid(q(map='de_nuke'),metric='dwell',floor='upper',cell=16);lo=wb.heat_grid(q(map='de_nuke'),metric='dwell',floor='lower',cell=16)
    assert up['cells'][0][2]==10.0 and lo['cells'][0][2]==10.0 and up['observed_seconds']==20.0
    with pytest.raises(ValueError,match='is_scoped'):wb.heat_grid(q(map='de_nuke'),metric='scoped_dwell')

def grenade_round(entity=7,x=300,with_supplement=True):
    ev=[{'id':'g1','type':'smokegrenade_detonate','tick':1300,'seconds':4.0,'actor':'P1','side':'T','position':[x,100,0],'entity':entity}]
    return rnd(events=ev)

def write_supplement(d,grenades):
    (d/'supplement-v1.json').write_text(json.dumps({'schema':1,'rounds':[{'number':1,'start_tick':1000,'economy':[{'player':'P1','side':'T','current_equip_value':4700,'start_balance':800}],
        'scoped_ticks':{'P1':[1016]},'scope_known_samples':{'P1':41},'grenades':grenades}]}))

def test_grenade_links_real_projectile_and_never_fakes_trajectory(env):
    d=write_match(env,A,'m.dem',[grenade_round()]);write_match(env,B,'n.dem',[grenade_round()])
    write_supplement(d,[{'entity':7,'kind':'smoke','thrower':'P1','side':'T','spawn_seconds':2.0,'spawn_tick':1128,'origin':[100,100,64],
                         'trajectory':[[2.0,100,100,64],[3.0,200,100,90],[4.0,300,100,0],[9.0,300,100,0]],'throw_event':{'seconds':1.98,'player_position':[95,100,0],'pitch':-10,'yaw':0}}])
    g=wb.grenades(q())
    linked=next(i for i in g['items'] if i['match']==A);bare=next(i for i in g['items'] if i['match']==B)
    assert linked['origin']==[100,100,64] and linked['link_basis']=='projectile_entity_id' and [p[0] for p in linked['trajectory']]==[2.0,3.0,4.0]
    assert bare['origin'] is None and bare['trajectory'] is None and bare['position']==[300,100,0]
    assert g['trajectory_coverage']=={'with_trajectory':1,'total':2}
    assert g['clusters'][0]['occurrences']==2

def test_economy_filter_needs_parsed_field(env):
    d=write_match(env,A,'m.dem',[grenade_round()]);write_match(env,B,'n.dem',[grenade_round()]);write_supplement(d,[])
    r=wb.run_query(q(economy={'field':'freeze_end_equip_value','min':4000}))
    assert r['counts']['rounds']==1 and {e['reason'] for e in r['excluded']}=={'economy_missing'}
    assert wb.run_query(q(economy={'field':'freeze_end_equip_value','min':5000}))['counts']['rounds']==0

def test_cluster_tolerance_and_floor_split():
    def it(i,x,z=0,t=4,floor='upper'):return {'id':str(i),'match':A,'round':i,'kind':'smoke','side':'T','floor':floor,'position':[x,0,z],'t':t}
    assert len(wb.cluster([it(1,0),it(2,100)],160,5))==1
    assert len(wb.cluster([it(1,0),it(2,100)],50,5))==2
    assert len(wb.cluster([it(1,0),it(2,0,t=12)],160,5))==2
    assert len(wb.cluster([it(1,0),it(2,0,floor='lower')],160,5))==2  # same XY, different floor

def test_tracks_relative_time_and_batches(env):
    write_match(env,A,'m.dem',[rnd(events=[plant(5)]),rnd(events=[plant(7)])])
    t=wb.tracks(q(alignment='plant',window=[-2,2]),offset=0,limit=1)
    assert t['total']==2 and not t['done']
    s=t['rounds'][0]['players'][0]['samples'];assert s[0][0]==-2 and s[-1][0]==2 and t['rounds'][0]['anchor']==5
    t2=wb.tracks(q(alignment='plant',window=[-2,2]),offset=1,limit=1);assert t2['done'] and t2['rounds'][0]['anchor']==7
    with pytest.raises(ValueError):wb.normalize(q(foo=1))

def test_heat_compare_requires_same_frame(env):
    write_match(env,A,'m.dem',[rnd()]);write_match(env,B,'p.dem',[rnd()],kind='player',verified=False)
    c=wb.heat_compare(q(group='player'),[],q(),[],'dwell','upper',16)
    assert c['shared_max']==1.0 and c['a']['valid_rounds']==1 and any('少于 5' in n for n in c['notes'])
    with pytest.raises(ValueError):wb.heat_compare(q(group='player',side='CT'),[],q(),[],'dwell','upper',16)

class Submitting:
    calls=0
    def __init__(self,args):self.args=args
    def invoke(self,messages,tools):
        type(self).calls+=1;return AIMessage(content='',tool_calls=[{'id':'x','name':'submit_findings','args':copy.deepcopy(self.args)}])

def wait(jid):
    for _ in range(200):
        s=wb.agent_get(jid)
        if s['status']!='running' and jid not in wb.AGENT_JOBS:return s
        time.sleep(.02)
    raise AssertionError('job did not finish')

def test_agent_evidence_budget_dedupe_and_consent(env):
    write_match(env,A,'m.dem',[rnd(events=[plant(5)]),rnd()])
    with pytest.raises(ValueError):wb.agent_start({'query':q(),'consent':False},model_factory=lambda:None)
    pack=wb.evidence_pack(q());eid=pack['evidence'][0]['id']
    assert 'm.dem' not in json.dumps(pack['packet']) and A not in json.dumps(pack['packet'])
    good={'summary':'s','findings':[{'conclusion':'c','facts':['f'],'inference':'i','uncertainty':'u','recommendation':'r','evidence_ids':[eid]}],'missing':[]}
    Submitting.calls=0
    s=wait(wb.agent_start({'query':q(),'consent':True,'endpoint_host':'offline-test'},model_factory=lambda:Submitting(good))['id'])
    assert s['status']=='completed' and s['model_calls']==1 and s['result']['findings'][0]['classification']=='model_inference'
    again=wb.agent_start({'query':q(),'consent':True,'endpoint_host':'offline-test'},model_factory=lambda:Submitting(good))
    assert again['deduplicated'] and again['id']==s['id'] and Submitting.calls==1
    bad=copy.deepcopy(good);bad['findings'][0]['evidence_ids']=['E999']
    s=wait(wb.agent_start({'query':q(outcome='win'),'consent':True,'endpoint_host':'offline-test'},model_factory=lambda:Submitting(bad))['id'])
    assert s['status']=='budget_exhausted' and s['model_calls']==2 and s['result'] is None

def test_agent_cancel_before_call(env):
    write_match(env,A,'m.dem',[rnd()])
    pack=wb.evidence_pack(q());e=threading.Event();e.set()
    h=wb.make_host(pack['packet'],pack['evidence'],env/'agent-cancel',None,e,lambda n:None)
    try:assert h.run()['reason']=='cancelled' and h.state['calls']==0
    finally:h.close()

def test_condition_labels_for_every_time_mode():
    for at in ('round_start','alignment','time'):
        labels=[c['label'] for c in wb.conditions(wb.normalize(q(alive={'at':at,'time':5,'own_min':4},equipment={'at':'opening','weapon':'awp'},zone={'mode':'passed','place':'BombsiteB'})))]
        assert len(labels)==3 and ('对齐后 5 秒' in labels[0])==(at=='time')

def test_disk_cache_rebuilds_when_round_changes(env):
    d=write_match(env,A,'m.dem',[rnd(winner='T')])
    assert wb.run_query(q(outcome='win'))['counts']['rounds']==1 and (d/'workbench-v1/round-1.json').exists()
    r=json.loads((d/'round-1.json').read_text());r['winner']='CT';time.sleep(.02);(d/'round-1.json').write_text(json.dumps(r))
    wb._CACHE.clear();wb._ROUNDS.clear()
    assert wb.run_query(q(outcome='win'))['counts']['rounds']==0

def test_combos_count_co_occurring_clusters():
    def it(i,r,x,kind):return {'id':str(i),'match':A,'round':r,'kind':kind,'side':'T','floor':'upper','position':[x,0,0],'t':4}
    items=[it(1,1,0,'smoke'),it(2,1,900,'flash'),it(3,2,0,'smoke'),it(4,2,900,'flash'),it(5,3,0,'smoke')]
    cl=wb.cluster(items);co=wb.combos(items,cl)
    assert co[0]['occurrences']==2 and len(co[0]['clusters'])==2

def test_replay_round_merges_supplement_and_shares_by_hash(env):
    d=write_match(env,A,'m.dem',[rnd()],sha='same');write_match(env,B,'copy.dem',[rnd()],sha='same',created=5)
    (d/'replay-v1').mkdir();(d/'replay-v1/round-1.json').write_text(json.dumps({'schema':1,'times':[0],'players':{},'events':[]}))
    write_supplement(d,[{'entity':1,'kind':'smoke','thrower':'P1','trajectory':[[1,0,0,0],[2,5,5,0]],'spawn_seconds':1,'origin':[0,0,0],'throw_event':None}])
    r=wb.replay_round(A,1);assert r['grenades'][0]['kind']=='smoke' and r['economy'][0]['player']=='P1'
    assert wb.replay_round(B,1)['times']==[0]  # duplicate upload reuses the canonical track by content hash
    with pytest.raises(ValueError):wb.replay_round(A,2)

def test_truncated_model_output_is_reported_not_called_budget(env):
    write_match(env,A,'m.dem',[rnd()])
    class Cut:
        def invoke(self,messages,tools):return AIMessage(content='思考到一半',response_metadata={'finish_reason':'length'})
    s=wait(wb.agent_start({'query':q(),'consent':True,'endpoint_host':'offline-test'},model_factory=Cut)['id'])
    assert s['status']=='output_truncated' and s['model_calls']==2 and s['result'] is None

def test_kill_and_death_heat_use_event_positions(env):
    death={'id':'k1','type':'player_death','tick':1300,'seconds':4.0,'actor':'P6','attacker':'P1','side':'CT','position':[900,900,0],'entity':None}
    write_match(env,A,'m.dem',[rnd(events=[death])])
    k=wb.heat_grid(q(),metric='kills',cell=16);d=wb.heat_grid(q(side='CT'),metric='deaths',cell=16)
    assert k['cells']==[[6,57,1.0,1.0]] and k['observed_seconds']==1  # attacker P1 stood at (100,100)
    assert d['cells']==[[56,7,1.0,1.0]]

def test_tactic_board_items_validated(env,monkeypatch):
    write_match(env,A,'m.dem',[rnd()])
    monkeypatch.setattr(wb.dr,'result',lambda mid:{'rounds':[]})
    step={'players':[{'id':'P1','side':'T','position':[1,2,3]}],'items':[{'type':'arrow','pts':[[1,2],[30,40]],'color':'#ffb23f'},{'type':'smoke','pts':[[5,5]],'color':'#fff'},{'type':'text','pts':[[1,1]],'color':'#fff','text':'go'}],'lines':[],'note':'x'}
    assert wb.dr.save_board({'match':A,'name':'b','steps':[step]*8})['id']
    for bad in [{'type':'laser','pts':[[1,1]]},{'type':'pen','pts':[[1,float('nan')]]},{'type':'text','pts':[[1,1]],'text':'x'*81},{'type':'arrow','pts':[[1,1]],'color':'red;x'}]:
        with pytest.raises(ValueError):wb.dr.save_board({'match':A,'name':'b','steps':[{**step,'items':[bad]}]})
    with pytest.raises(ValueError):wb.dr.save_board({'match':A,'name':'b','steps':[step]*9})

def test_player_names_for_display_never_reach_model_packet(env):
    d=write_match(env,A,'m.dem',[rnd()])
    (d/'players.json').write_text(json.dumps({'schema':1,'players':{'P1':{'name':'ZywOo','steamid':'765'},'P6':{'name':'ropz','steamid':'766'}}}))
    assert wb.player_names(A)=={'P1':'ZywOo','P6':'ropz'}
    assert wb.catalog()[0]['names']['P1']=='ZywOo'
    packet=json.dumps(wb.evidence_pack(q())['packet'],ensure_ascii=False)
    assert 'ZywOo' not in packet and 'ropz' not in packet and '765' not in packet and 'P1' in packet
