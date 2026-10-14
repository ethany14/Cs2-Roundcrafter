"""Offline identity/retrieval/real AgentLoop contracts; not live provider acceptance."""
import copy,json
import pytest
from langchain_core.messages import AIMessage
from cs2_agent import demo_compare as c,demo_identity as ident

@pytest.fixture
def pool(tmp_path,monkeypatch):
 monkeypatch.setattr(c.dr,'BASE',tmp_path)
 matches=[{'id':str(i)*32,'status':'completed','sha256':str(i),'name':str(i)+'.dem'} for i in range(1,5)]
 matches[3]['sha256']='1'
 monkeypatch.setattr(c.dr,'library',lambda:matches)
 monkeypatch.setattr(c.dr,'state',lambda mid:next(m for m in matches if m['id']==mid))
 monkeypatch.setattr(c.identity,'get',lambda mid:{'kind':'player' if mid=='1'*32 else 'professional','verified':False,'source_url':'https://example.com/match'})
 monkeypatch.setattr(c.dr,'result',lambda mid:{'map':'de_dust2','rounds':[{'number':1}]})
 def profile(mid,n,side):return {'match':mid,'round':n,'map':'de_dust2','side':side,'target':'B','phase':'entry','anchor':30,'anchors':{'round_start':0,'entry':30},'duration':100,'alive':{'T':5,'CT':5},'equipment':'rifle','rifles':5,'entry_gap':1.5,'utility_count':3,'evidence':[{'id':x,'start':25,'end':35,'text':x} for x in ['shape','equipment','entry_gap','utility']],'unknown':[],'routes':[]}
 monkeypatch.setattr(c,'profile',profile)
 return matches,profile

def test_professional_only_and_same_content_excluded(pool,monkeypatch):
 monkeypatch.setattr(c.identity,'get',lambda mid:{'kind':'player' if mid=='2'*32 else 'professional'})
 r=c.retrieve('1'*32,1,'T')
 assert [x['match'] for x in r['candidates']]==['3'*32]
 assert r['excluded']['same_demo']==2

def test_context_filters_wrong_map_site_phase_and_players(pool,monkeypatch):
 matches,profile=pool
 for key,value in [('target','A'),('phase','retake'),('alive',{'T':2,'CT':5})]:
  monkeypatch.setattr(c,'profile',lambda mid,n,side,key=key,value=value:profile(mid,n,side) if mid=='1'*32 else {**profile(mid,n,side),key:value})
  assert c.retrieve('1'*32,1,'T')['candidates']==[]
 monkeypatch.setattr(c.dr,'result',lambda mid:{'map':'de_nuke','rounds':[{'number':1}]})
 assert c.retrieve('1'*32,1,'T')['candidates']==[]

def test_pair_evidence_namespaces_and_guard(pool):
 p=c.pair('1'*32,1,'2'*32,1,'T')
 assert len({e['id'] for e in p['evidence']})==8
 assert p['observations'][0]['delta']==0
 with pytest.raises(ValueError):c.pair('1'*32,1,'4'*32,1,'T')

def test_explicit_identity_and_invalid_pro_source(tmp_path,monkeypatch):
 monkeypatch.setattr(ident.dr,'BASE',tmp_path);monkeypatch.setattr(ident.dr,'state',lambda mid:{'sha256':None});monkeypatch.setattr(ident,'ROOT',tmp_path)
 mid='a'*32
 assert ident.get(mid)['kind']=='unknown'
 assert ident.set_identity(mid,'player')['kind']=='player'
 with pytest.raises(ValueError):ident.set_identity(mid,'professional','')
 assert ident.set_identity(mid,'professional','https://example.com/match')['verified'] is False
 assert ident.get(mid)['basis']=='user_declared'

def test_filename_cannot_spoof_curated_source(tmp_path,monkeypatch):
 monkeypatch.setattr(ident.dr,'BASE',tmp_path/'outputs');monkeypatch.setattr(ident,'ROOT',tmp_path);ident.HASHES.clear()
 base=tmp_path/'data';(base/'demos').mkdir(parents=True);(base/'situation').mkdir();(base/'demos/pro.dem').write_bytes(b'real')
 (base/'situation/manifest.json').write_text(json.dumps({'demos':[{'path':'../demos/pro.dem','professional':True,'source_url':'https://example.com/match'}]}))
 monkeypatch.setattr(ident.dr,'state',lambda mid:{'name':'pro.dem','sha256':'wrong'})
 assert ident.get('a'*32)['kind']=='unknown'
 sha=ident.dr.hash_file(base/'demos/pro.dem');monkeypatch.setattr(ident.dr,'state',lambda mid:{'name':'renamed.dem','sha256':sha})
 assert ident.get('a'*32)['verified'] is True

def test_eregion_comparison_requires_both_sides(pool,tmp_path):
 import threading
 packet=c.pair('1'*32,1,'2'*32,1,'T')
 args={'summary':'局部可比','findings':[{'title':'配合区别','interpretation':'有依据的推断','recommendation':'先核对进点配合','evidence_ids':['current:entry_gap','reference:entry_gap']}],'limits':['不是补枪时间']}
 class Model:
  def invoke(self,messages,tools):return AIMessage(content='',tool_calls=[{'id':'a','name':'submit_comparison','args':copy.deepcopy(args)}])
 h=c.CompareHost(packet,tmp_path/'agent',Model(),threading.Event(),lambda n:None)
 try:
  bad=copy.deepcopy(args);bad['findings'][0]['evidence_ids']=['current:shape','fake']
  with pytest.raises(ValueError):h.submit(bad)
  assert h.run()['reason']=='completed';assert h.state['calls']==1;assert h.result['findings'][0]['classification']=='model_inference'
 finally:h.close()

def test_consent_required_and_cancel_before_model(pool,tmp_path):
 import threading
 e=threading.Event();e.set();h=c.CompareHost(c.pair('1'*32,1,'2'*32,1,'T'),tmp_path/'cancel',None,e,lambda n:None)
 try:assert h.run()['reason']=='cancelled';assert h.state['calls']==0
 finally:h.close()
 with pytest.raises(ValueError):c.start({'consent':False})

def test_disjoint_approaches_not_same_tactic(pool,monkeypatch):
 _,original=pool
 monkeypatch.setattr(c,'profile',lambda mid,n,side:{**original(mid,n,side),'approach_zones':['UpperTunnel'] if mid=='1'*32 else ['BDoors']})
 assert c.retrieve('1'*32,1,'T')['candidates']==[]

def test_raw_profiles_keep_arrival_semantics_and_bounds(tmp_path,monkeypatch):
 mid='a'*32;folder=tmp_path/mid;folder.mkdir();(folder/'round-1.json').write_text('{}')
 monkeypatch.setattr(c.dr,'BASE',tmp_path);c.CACHE.clear()
 def team(area,second=False):return [{'id':'P1','side':'T','alive':True,'area':area,'inventory':['AK-47']},{'id':'P2','side':'T','alive':True,'area':area if second else 'UpperTunnel','inventory':['AK-47']}]
 frames=[{'tick':0,'seconds':0,'players':team('UpperTunnel')},{'tick':10,'seconds':10,'players':team('BombsiteB')},{'tick':11,'seconds':11,'players':team('BombsiteB',True)}]
 r={'frames':frames,'events':[],'duration':12}
 monkeypatch.setattr(c.dr,'round_data',lambda *a:r);monkeypatch.setattr(c.dr,'result',lambda *a:{'map':'de_dust2'})
 monkeypatch.setattr(c.dr,'analyze_round',lambda r:[{'side':'T','objective':'B'}])
 p=c.profile(mid,1,'T');assert p['entry_gap']==1;assert p['anchors']['entry']==10
 assert '不是补枪' in next(e['text'] for e in p['evidence'] if e['id']=='entry_gap')
 assert all(0<=e['start']<=e['end']<=12 for e in p['evidence'])
 assert p['approach_zones']==['UpperTunnel']

def test_comparison_budget_stops_non_submitting_model(pool,tmp_path):
 import threading
 class Model:
  def invoke(self,messages,tools):return AIMessage(content='继续思考')
 h=c.CompareHost(c.pair('1'*32,1,'2'*32,1,'T'),tmp_path/'limited',Model(),threading.Event(),lambda n:None)
 try:
  h.run();assert h.state['calls']==2;assert h.result is None
 finally:h.close()

def test_saved_reference_outside_top8_stays_restorable(pool,monkeypatch):
 matches,profile=pool
 monkeypatch.setattr(c.dr,'result',lambda mid:{'map':'de_dust2','rounds':[{'number':i} for i in range(1,13)]})
 monkeypatch.setattr(c,'profile',lambda mid,n,side:{**profile(mid,n,side),'anchor':30+n*5})
 r=c.retrieve('1'*32,1,'T');assert len(r['candidates'])==8
 last=('3'*32,12);assert not any((x['match'],x['round'])==last for x in r['candidates'])
 r=c.retrieve('1'*32,1,'T',ensure=last);assert r['candidates'][-1]['restored'] is True
 assert c.pair('1'*32,1,*last,'T')['reference']['round']==12
