"""Offline contract tests. Fakes here do not constitute live-network acceptance."""
import copy
import json
import threading
from dataclasses import asdict
from pathlib import Path
import httpx
import pytest
from langchain_core.messages import AIMessage
from cs2_agent.lineup_catalog import (migrate, canonical_url, retrieve_cards, check_fit, UtilityNeed, LineupCard)
from cs2_agent.lineup_sources import (Budget,Sources,ResearchStop,public_url,accept_field_evidence,extract_metadata)
from cs2_agent.lineup_research import Research,ResearchHost,validate_request

@pytest.fixture
def cards(tmp_path):return migrate(tmp_path/'catalog.json')['cards']
@pytest.fixture
def card(cards):return next(c for c in cards if c['id']=='6518')
def need(**kwargs):return asdict(UtilityNeed('6518','de_nuke','smoke',['Roof'],['Heaven'],**kwargs))

def test_migration_lossless_six_with_null_coordinates(cards):
    from cs2_agent.casebook import ROOT
    original=json.loads((ROOT/'data/knowledge/metastack/teaching.json').read_text(encoding='utf-8'))['lessons'][:6]
    assert len(cards)==6
    for c in cards:
        assert c['coordinates'] is None and c['game_validation']=='unverified'
        assert c['legacy']['lesson']['id']==c['id'] and c['legacy']['source_observation']
        assert c['legacy']['lesson']==next(x for x in original if x['id']==c['id'])
        assert c['video_url'] and c['evidence'] and not c['steps']
        assert all(e['content_hash'] and e['source_url'] and e['method'] for e in c['evidence'])
    assert next(c for c in cards if c['id']=='6518')['legacy']['lesson']['candidates']==[]

@pytest.mark.parametrize('query,expected',[('Heaven smoke','6518'),('天堂烟怎么扔','6518'),('屋顶到黄房火','1370'),('外场过点烟','1361'),('backsite fire','1369'),('管道烟','1362')])
def test_aliases_destinations(query,expected,cards):assert retrieve_cards(query,cards=cards)[0]['id']==expected

def test_wrong_map_and_unseen_target_no_fallback(cards):
    assert not retrieve_cards('Heaven smoke','de_mirage',cards)
    assert not retrieve_cards('Secret smoke',cards=cards)
    assert not retrieve_cards('Heaven fire',cards=cards)

@pytest.mark.parametrize('field,value',[('map','de_mirage'),('side','CT'),('motion','Standing'),('throw','Normal Throw'),('kind','flash')])
def test_hard_fit_conflicts(card,field,value):
    n=need();n[field]=value;r=check_fit(n,card)
    assert r['status']=='incompatible' and field in r['conflicts']

def test_start_target_floor_and_party(card):
    n=need();n['origin']=['屋顶'];assert not check_fit(n,card)['conflicts']
    n=need();n['origin']=['Lobby'];assert 'origin' in check_fit(n,card)['conflicts']
    n=need();n['target']=['BombsiteB'];assert 'target' in check_fit(n,card)['conflicts']
    c=copy.deepcopy(card);c['participants']=2
    assert '配合人数不足' in check_fit(need(),c)['conflicts']

def test_missing_player_utility_and_unknowns(card):
    r=check_fit(need(),card,{'utility':{'smoke':0}});assert '持有人缺少该道具' in r['conflicts']
    r=check_fit(need(),card);assert r['status']=='unknown' and '所需配合人数' in r['unknown']
    assert r['game_validation']=='unverified'

def test_video_without_coordinates_still_retrievable(card,cards):
    assert retrieve_cards('Heaven smoke',cards=cards)[0]['video_url']
    assert card['coordinates'] is None

def test_canonical_source_dedup():
    assert canonical_url('https://www.metastack.gg/nades/a/?utm_source=x#aim')=='https://metastack.gg/nades/a'
    assert canonical_url('https://youtu.be/F8mjzdNhhAU?t=3')==canonical_url('https://www.youtube.com/watch?v=F8mjzdNhhAU&feature=share')

@pytest.mark.parametrize('url',['http://example.com','https://user:pass@example.com','file:///etc/passwd','https://example.com:8080'])
def test_source_url_boundaries(url):
    with pytest.raises(ValueError):canonical_url(url)

def test_private_sources_rejected():
    with pytest.raises(ValueError):public_url('https://127.0.0.1/private')

def test_cache_normalization_does_not_rewrite_transport_host(monkeypatch):
    monkeypatch.setattr('cs2_agent.lineup_sources.socket.getaddrinfo',lambda *a,**kw:[(2,1,6,'',('93.184.216.34',443))])
    assert public_url('https://www.example.com/source')=='https://www.example.com/source'

def test_cache_and_budget_no_duplicate_network(tmp_path,monkeypatch):
    monkeypatch.setattr('cs2_agent.lineup_sources.public_url',canonical_url)
    calls=[]
    def reply(request):
        calls.append(request.url)
        return httpx.Response(200,headers={'Content-Type':'text/html'},text='<title>Nuke</title><p>'+('Public instruction text. '*12)+'</p>')
    b=Budget();s=Sources(b,tmp_path,httpx.Client(transport=httpx.MockTransport(reply)))
    a=s.read('https://example.com/nade?utm_source=a');c=s.read('https://example.com/nade#aim')
    assert a['status']==c['status']=='read' and c['cache_hit'] and len(calls)==1
    assert b.state['used']['read']==1 and b.state['used']['cache_hits']==1
    b.state['limits']['read']=1
    with pytest.raises(ResearchStop,match='budget_exhausted'):s.read('https://example.com/other')

def test_unreadable_different_from_notfound(tmp_path,monkeypatch):
    monkeypatch.setattr('cs2_agent.lineup_sources.public_url',canonical_url)
    s=Sources(Budget(),tmp_path,httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(403))))
    assert s.read('https://example.com/source')['status']=='inaccessible'

def test_search_only_leads_dedup(tmp_path,monkeypatch):
    monkeypatch.setattr('cs2_agent.lineup_sources.public_url',canonical_url)
    xml='<rss><channel>'+('<item><title>Nuke Heaven</title><link>https://example.com/a</link><description>jump throw</description></item>'*2)+'</channel></rss>'
    s=Sources(Budget(),tmp_path,httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,headers={'Content-Type':'text/xml'},text=xml))))
    r=s.search('Nuke Heaven');assert len(r['results'])==1
    assert r['results'][0]['evidence_status']=='discovery_only'

def test_cancellation_reserves_no_call(tmp_path):
    event=threading.Event();event.set();s=Sources(Budget(cancelled=event),tmp_path)
    with pytest.raises(ResearchStop,match='cancelled'):s.search('Heaven')
    assert s.budget.state['used']['search']==0

def test_quote_validation_and_no_coordinate_injection(card):
    page={'status':'read','url':card['source_url'],'text':'Stand against the corner and aim at the upper edge.','observed_at':'2026-10-13','content_hash':'abc','title':'Heaven'}
    p={'field':'steps','value':page['text'],'quote':page['text']}
    assert accept_field_evidence(card,page,[p])[0]['quote']==page['text']
    for bad in [dict(p,value='Invented jump'),dict(p,field='coordinates'),dict(p,quote='not read on page')]:
        with pytest.raises(ValueError):accept_field_evidence(card,page,[bad])
    with pytest.raises(ValueError):accept_field_evidence(card,{**page,'status':'inaccessible'},[p])

def test_source_conflict_preserved_hard_reject(card):
    page={'status':'read','url':card['source_url'],'text':'Standing Jump Throw','observed_at':'2026-10-13','content_hash':'a','videos':[]}
    result=extract_metadata(card,page)
    assert result['motion']=='Running' and any(e['contradictions'] for e in result['evidence'])
    assert check_fit(need(),result)['status']=='incompatible'

def test_map_request_conflict_rejected():
    with pytest.raises(ValueError):validate_request({'query':'Mirage Heaven smoke','map':'de_nuke'})

def test_single_tactic_context_preserves_time_without_requiring_five_players(tmp_path):
    r=Research(tmp_path/'context',{'query':'这套 Nuke 战术里的 Heaven 烟怎么扔','mode':'single','party_size':1})
    try:
        n=r.requirements()['needs'][0]
        assert n['role']=='roof_support' and n['clock']==106 and n['party_size']==1
        r.local();result=r.compose()
        assert not result['roles'] and result['team_check'] is None
        assert result['tactic_context'][0]['clock']==106
    finally:r.sources.close()

class ScriptedModel:
    """Offline only: selects advertised phase tools to exercise the real kernel."""
    request_timeout=5
    def invoke(self,messages,tools):
        name=tools[0]['function']['name']
        return AIMessage(content='',tool_calls=[{'id':str(len(messages)),'name':name,'args':{'text':'测试工具流程，非真实联网验证'} if name=='finish_task' else {}}])

def test_existing_eregion_loop_phases_and_persistence(tmp_path,monkeypatch,cards):
    monkeypatch.setattr('cs2_agent.lineup_research.load_catalog',lambda:{'cards':cards})
    r=Research(tmp_path/'offline',{'query':'Heaven smoke','mode':'single','map':'de_nuke','party_size':1})
    def offline(args):r.state['phase']=3;return {'offline_fixture':True,'no_network':True}
    r.research_missing=offline
    h=ResearchHost(r,ScriptedModel());r.state['agent']={}
    try:
        assert h.run()['reason']=='completed'
        assert h.state['calls']==5 and r.state['phase']==4 and r.state['result']['learning_cards']
        assert (tmp_path/'offline/task.json').exists()
        assert r.state['budget']['used']['search']==0
    finally:h.close();r.sources.close()

def test_phase_fence_and_model_budget(tmp_path):
    r=Research(tmp_path/'fence',{'query':'Heaven smoke','mode':'single'})
    h=ResearchHost(r,ScriptedModel())
    try:
        assert [t['function']['name'] for t in h.observe().allowed_tools]==['get_tactic_requirements']
        h.state['calls']=h.state['max_calls']
        from eregion.runtime.core.engine import LoopStop
        with pytest.raises(LoopStop):h.observe()
    finally:h.close();r.sources.close()

def test_reach_bilibili_envelope_without_private_flags(tmp_path,monkeypatch):
    from cs2_agent.reach_sources import ReachSources
    s=Sources(Budget(),tmp_path);reach=ReachSources(s);commands=[]
    def fixture(argv,timeout=35):
        commands.append(argv)
        return {'status':'ok','data':{'ok':True,'schema_version':'1','data':{'video':{
            'title':'Nuke fixture','description':'Public fixture metadata, not live evidence.'}}}}
    monkeypatch.setattr(reach,'_command',fixture)
    try:
        result=reach.read_video('https://www.bilibili.com/video/BV1Nx4y1m7ei')
        assert result['title']=='Nuke fixture' and result['text'].startswith('Public fixture')
        assert not any(flag in commands[0] for flag in ['--subtitle','--comments','--ai','login'])
        assert result['caption_status']=='requires_authorized_browser_channel'
    finally:s.close()

def test_reach_youtube_never_loads_personal_config_or_downloads():
    from cs2_agent.reach_sources import ReachSources
    args=ReachSources.ytdlp_args()
    assert '--ignore-config' in args and '--skip-download' in args and '--js-runtimes' in args
    assert not any('cookie' in a for a in args)


def test_discovered_www_source_can_be_read(tmp_path,monkeypatch):
    r=Research(tmp_path/'canonical',{'query':'Mirage window smoke','mode':'single','map':'de_mirage'})
    url='https://www.bilibili.com/video/BV1Nx4y1m7ei'
    r.sources.discovered.add(url)
    monkeypatch.setattr(r.reach,'read_video',lambda u:{'url':u,'status':'inaccessible'})
    try:assert r.read_source({'url':url})['status']=='inaccessible'
    finally:r.sources.close()


def test_no_local_cards_budget_returns_structured_result(tmp_path,monkeypatch):
    import cs2_agent.lineup_research as module
    r=Research(tmp_path/'empty-budget',{'query':'Mirage window smoke','mode':'single','map':'de_mirage'})
    monkeypatch.setattr(module,'ConfiguredModel',lambda config:ScriptedModel())
    monkeypatch.setattr(ScriptedModel,'close',lambda self:None,raising=False)
    monkeypatch.setattr(module,'load_config',lambda:{'max_tokens':1000,'timeout':5,'endpoint':'https://example.com'})
    def exhaust(self,**kw):self.state.update(status='yielded',calls=6)
    monkeypatch.setattr(ResearchHost,'run',exhaust)
    r.run()
    assert r.state['status']=='budget_exhausted'
    assert r.state['result']['learning_cards'][0]['status']=='budget_exhausted'
    assert r.state['agent']['model_calls']==6


def test_discovered_video_card_keeps_literal_description_not_visual_aim(tmp_path,monkeypatch):
    r=Research(tmp_path/'discovery',{'query':'Mirage window smoke','mode':'single','map':'de_mirage'})
    url='https://www.youtube.com/watch?v=WGFYA8RexbA'
    hit={'url':url,'title':'CS2 Mirage Window Smoke','snippet':''}
    def search(*args):r.sources.discovered.add(url);return {'results':[hit]}
    monkeypatch.setattr(r.reach,'search',search)
    monkeypatch.setattr(r,'search_web',search)
    sentence='To throw this smoke, position yourself next to the trash can, aim as shown, hold the D key, and jumpthrow.'
    monkeypatch.setattr(r.reach,'read_video',lambda u:{'url':u,'status':'read','title':hit['title'],'text':sentence,'scope':'video description only','observed_at':'test','content_hash':'fixture'})
    try:
        r.requirements();r.local();r.research_missing();result=r.compose()
        card=result['learning_cards'][0]['card']
        assert card['steps']==[sentence] and card['coordinates'] is None
        assert card['game_validation']=='unverified'
        assert any(e['field']=='steps' and e['quote']==sentence for e in card['field_evidence'])
        assert len(result['references'])==1
    finally:r.sources.close()
