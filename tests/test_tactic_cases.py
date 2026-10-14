import json,pytest
from cs2_agent import tactic_cases as t

@pytest.fixture
def library(tmp_path,monkeypatch):
 monkeypatch.setattr(t.dr,'BASE',tmp_path);monkeypatch.setattr(t.dr,'state',lambda mid:{'status':'completed','sha256':mid})
 mid='a'*32;folder=tmp_path/mid;folder.mkdir();p=folder/'coach-1.json'
 state={'status':'completed','version':4,'packet':{'round':1,'map':'de_nuke','duration':100,'evidence':[{'id':'E1','kind':'utility','text':'P1 20秒闪光引爆','start':18,'end':24,'players':['P1']}]},'result':{'claims':[{'evidence_ids':['E1'],'observed_title':'Secret 转 B','interpretation':'推断经外场下B','side':'T','start':18,'end':24,'players':['P1']}]}}
 p.write_text(json.dumps(state),encoding='utf-8')
 monkeypatch.setattr(t.dr,'round_data',lambda *a:{'events':[{'id':'r1-e1','type':'flashbang_detonate','seconds':20,'actor':'P1','side':'T'},{'id':'r1-e2','type':'smokegrenade_detonate','seconds':50,'actor':'P2','side':'T'}]})
 monkeypatch.setattr(t,'retrieve_cards',lambda *a:[])
 return p,state

def test_search_keeps_inference_and_provenance(library):
 found=t.search('Secret', 'de_nuke','T');assert found['total']==1
 c=t.get(found['cases'][0]['id']);assert c['classification']=='model_inference';assert c['evidence'][0]['id']=='E1';assert 'case=' in c['replay_url'];assert c['source']['artifact'].endswith('coach-1.json')
 assert t.search('Secret','de_dust2')['total']==0
 assert t.search('Secret','de_nuke','CT')['total']==0

def test_cache_invalidates_and_stale_case_rejected(library):
 p,s=library;old=t.catalog()['cases'][0]['id'];s['result']['claims'][0]['interpretation']='新的判断';p.write_text(json.dumps(s),encoding='utf-8')
 assert t.catalog()['cases'][0]['id']!=old
 with pytest.raises(ValueError):t.get(old)

def test_invalid_refs_and_incomplete_not_indexed(library):
 p,s=library;s['result']['claims'][0]['evidence_ids']=['fake'];p.write_text(json.dumps(s));assert not t.catalog()['cases']
 s['status']='running';p.write_text(json.dumps(s));assert not t.catalog()['cases']

def test_learning_uses_actual_clip_events_and_unknowns(library):
 c=t.catalog()['cases'][0];plan=t.learning(c['id']);assert len(plan['utility_needs'])==1
 n=plan['utility_needs'][0];assert n['classification']=='demo_observation';assert n['kind']=='flash';assert n['candidates']==[];assert n['unknown'];assert plan['players'][0]['facts']

def test_bad_ids_and_filters(library):
 for cid in ['../x','a'*25]:
  with pytest.raises(ValueError):t.get(cid)
 with pytest.raises(ValueError):t.search('x',side='invalid')

def test_case_cannot_use_fixed_tactic_template(library):
 from cs2_agent.lineup_research import validate_request
 cid=t.catalog()['cases'][0]['id']
 with pytest.raises(ValueError):validate_request({'query':'Nuke smoke','mode':'tactic','source_case':cid})
 assert validate_request({'query':'Nuke smoke','mode':'single','source_case':cid})['source_case']==cid
