"""Offline tests exercise real AgentLoop; transport doubles are not live-network proof."""
import copy
import pytest
from langchain_core.messages import AIMessage
from cs2_agent import case_learning as m
from cs2_agent.lineup_sources import ResearchStop

@pytest.fixture
def research(tmp_path,monkeypatch):
 c={'id':'a'*24,'match':'b'*32,'round':1,'map':'de_nuke','side':'T','title':'Secret 下 B','interpretation':'推断转B','start':10,'end':30,'players':['P1'],'evidence':[],'replay_url':'/demos?case='+('a'*24)}
 monkeypatch.setattr(m.tactic_cases,'get',lambda cid:copy.deepcopy(c))
 players=[{'id':'P'+str(i),'side':'T','area':'Outside','alive':True,'armor':100,'inventory':['AK-47','Smoke Grenade']} for i in range(1,6)]
 frames=[{'tick':10,'seconds':10,'players':players},{'tick':25,'seconds':25,'players':[{**p,'area':'Tunnels'} for p in players]}]
 events=[{'id':'event'+str(i),'type':'smokegrenade_detonate','seconds':15+i,'actor':'P'+str(i),'side':'T','position':[i,2,3]} for i in (1,2)]
 monkeypatch.setattr(m.demo_review,'round_data',lambda *a:{'frames':frames,'events':events})
 monkeypatch.setattr(m,'retrieve_cards',lambda *a:[])
 r=m.CaseResearch(tmp_path/'run',{'query':'整套 Nuke 教学','mode':'case','map':'de_nuke','source_case':c['id']})
 r.requirements();r.local()
 yield r
 r.sources.close()

def steps(r):return [{'player':p['player'],'instruction':'按原路线推进并等待队友配合','evidence_ids':['equipment-'+p['player']]} for p in r.state['batch']['roles']]

def test_all_players_all_events_and_no_invented_release(research):
 r=research;assert len(r.state['needs'])==2
 result=r.compose();assert len(result['roles'])==5
 assert result['roles'][0]['required_utility']=={'smoke':1}
 assert all(n['origin']==[] and n['target']==[] and n['clock'] is None for n in r.state['needs'])
 assert result['ready_for_execution'] is False

def test_shared_search_dedup_read_and_missing_states(research,monkeypatch):
 r=research;calls=[]
 def search(channel,query):
  r.budget.reserve('search',channel);return {'status':'found','results':[{'url':'https://www.youtube.com/watch?v=abcdefghijk','title':'CS2 Nuke smoke','snippet':''}]}
 def read(url):
  r.budget.reserve('read',url);calls.append(url)
  page={'url':url,'status':'read','title':'CS2 Nuke smoke','text':'Stand against the wall and aim at the corner.','observed_at':'now','content_hash':'123'}
  r.state['read_documents'][url]=page;return page
 monkeypatch.setattr(r.reach,'search',search);monkeypatch.setattr(r.sources,'search',lambda q:search('web',q));monkeypatch.setattr(r,'read_source',lambda a:read(a['url']))
 r.research_missing();result=r.compose()
 assert r.budget.state['used']['search']==3 # two events, one query, three channels
 assert len(calls)==1 and len(r.state['references'])==2
 assert all(row['status']=='insufficient_evidence' for row in result['learning_cards'])
 assert r.state['cards'][0]['map'] is None and not r.state['cards'][0]['steps']
 r.research_missing();assert len(calls)==1 and r.budget.state['used']['search']==3

def test_budget_salvages_every_need(research,monkeypatch):
 r=research;r.budget.state['limits']['search']=1
 def search(*a):r.budget.reserve('search','x');return {'status':'not_found','results':[]}
 monkeypatch.setattr(r.reach,'search',search)
 r.research_missing()
 assert r.state['research_stop']=='budget_exhausted';assert r.budget.state['used']['search']==1
 assert len(r.state['result']['learning_cards'])==2;assert len(r.state['result']['roles'])==5

def test_cancel_prevents_more_search(research,monkeypatch):
 r=research;r.cancelled.set()
 monkeypatch.setattr(r.reach,'search',lambda *a:pytest.fail('network after cancel'))
 with pytest.raises(ResearchStop,match='cancelled'):r.research_missing()
 assert r.state['result']['roles']

def test_unbacked_or_incomplete_model_steps_rejected(research):
 r=research
 with pytest.raises(ValueError):r.compose_batch({'steps':[{'player':'P1','instruction':'do it','evidence_ids':['fake']}],'extractions':[]})
 with pytest.raises(ValueError):r.compose_batch({'steps':steps(r)[:1],'extractions':[]})
 assert r.state['suggestions']==[]

def test_real_loop_composes_whole_team_in_one_call(research):
 r=research;r.state['agent']={};r.state['phase']=3
 class Model:
  def invoke(self,messages,tools):return AIMessage(content='',tool_calls=[{'id':'batch','name':'compose_execution_plan','args':{'steps':steps(r),'extractions':[]}}])
 host=m.CaseHost(r,Model())
 try:
  assert host.run()['reason']=='completed';assert host.state['calls']==1
  assert len(r.state['suggestions'])==5
  assert all(x['classification']=='model_inference' for x in r.state['suggestions'])
 finally:host.close()

def test_loop_caps_bad_model_at_two_calls(research):
 r=research;r.state['agent']={};r.state['phase']=3
 class Model:
  def invoke(self,messages,tools):return AIMessage(content='still thinking')
 host=m.CaseHost(r,Model())
 try:
  host.run();assert host.state['calls']==2
 finally:host.close()

def test_unavailable_distinct_from_empty(research,monkeypatch):
 r=research
 monkeypatch.setattr(r.reach,'search',lambda *a:{'status':'inaccessible','results':[]})
 monkeypatch.setattr(r.sources,'search',lambda *a:{'status':'search_unavailable','results':[]})
 r.research_missing();assert all(x['status']=='search_unavailable' for x in r.compose()['learning_cards'])
 r.state['searches']={k:{'status':'not_found','results':[]} for k in r.state['searches']}
 assert all(x['status']=='not_found' for x in r.compose()['learning_cards'])

def test_snapshot_inventory_does_not_prove_later_incompatibility(research):
 from dataclasses import asdict
 from cs2_agent.lineup_catalog import LineupCard
 r=research;r.state['batch']['roles'][0]['inventory']=[]
 r.state['cards']=[asdict(LineupCard('candidate','Nuke smoke','de_nuke','smoke','https://example.com/nuke',side='T'))]
 row=r.compose()['learning_cards'][0]
 assert row['status']!='incompatible'
 assert any('后续拾取' in x for x in row['candidates'][0]['compatibility']['unknown'])

def test_unread_or_forged_teaching_cannot_be_committed(research):
 from dataclasses import asdict
 from cs2_agent.lineup_catalog import LineupCard
 r=research;url='https://example.com/nuke'
 r.state['cards']=[asdict(LineupCard('candidate','Nuke smoke','de_nuke','smoke',url))]
 item={'card_id':'candidate','source_url':url,'proposals':[{'field':'steps','value':'Stand in the corner and aim at the roof.','quote':'Stand in the corner and aim at the roof.'}]}
 with pytest.raises(ValueError):r.compose_batch({'steps':steps(r),'extractions':[item]})
 r.state['read_documents'][url]={'url':url,'status':'read','title':'Nuke smoke','text':'No throwing instructions here.','content_hash':'123','observed_at':'now'}
 with pytest.raises(ValueError):r.compose_batch({'steps':steps(r),'extractions':[item]})
 assert r.state['cards'][0]['steps']==[] and r.state['suggestions']==[]

def test_exact_teaching_quote_preserves_scope(research):
 from dataclasses import asdict
 from cs2_agent.lineup_catalog import LineupCard
 r=research;url='https://example.com/nuke';quote='Stand in the corner and aim at the roof.'
 r.state['cards']=[asdict(LineupCard('candidate','Nuke smoke','de_nuke','smoke',url))]
 r.state['read_documents'][url]={'url':url,'status':'read','title':'Nuke smoke','text':quote,'content_hash':'123','observed_at':'now'}
 r.compose_batch({'steps':steps(r),'extractions':[{'card_id':'candidate','source_url':url,'proposals':[{'field':'steps','value':quote,'quote':quote}]}]})
 c=r.state['cards'][0];assert c['steps']==[quote] and c['evidence'][0]['scope']=='literal_text_only';assert c['game_validation']=='unverified'
