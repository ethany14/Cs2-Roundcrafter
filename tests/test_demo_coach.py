import copy,threading
import pytest
from cs2_agent.demo_coach import Session,evidence,PILOTS,CoachHost
from eregion.runtime.core.engine import LoopStop

def session():
 s=Session.__new__(Session);s.mid=next(iter(PILOTS));s.n=13;s.packet=evidence(s.mid,s.n);s.read=True;s.window_read=True;s.repairs=0;s.cancelled=threading.Event();s.state={'checks':[],'result':None};s.save=lambda:None;return s

def payload(s):
 h=s.packet['hypotheses'][0]
 return dict(summary='测试说明',claims=[dict(hypothesis_id=h['id'],evidence_ids=h['evidence_ids'],interpretation='可能的解释',clip={'start':0,'end':s.packet['duration']})],alternatives=[{'text':'意图未知'}])
def test_grounded_claim():
 s=session();assert s.submit(payload(s))['accepted'];c=s.state['result']['claims'][0];assert c['players'];assert 0<=c['start']<c['end']<=s.packet['duration'];assert len(c['facts'])==5
def test_fabricated_evidence_rejected():
 s=session();p=payload(s);p['claims'][0]['evidence_ids']=['fake'];assert not s.submit(p)['accepted'];assert s.state['result'] is None
 with pytest.raises(LoopStop):s.submit(p)
def test_no_inspection_no_submit():
 s=session();s.window_read=False;assert not s.submit(payload(s))['accepted']
def test_cancel_discards_submission():
 s=session();s.cancelled.set()
 with pytest.raises(LoopStop):s.submit(payload(s))
 assert s.state['result'] is None
def test_real_pilots_citations_and_bounds():
 for mid,rounds in PILOTS.items():
  for n in rounds:
   p=evidence(mid,n);ids={e['id'] for e in p['evidence']};assert p['hypotheses']
   for h in p['hypotheses']:assert set(h['evidence_ids'])<=ids
   for e in p['evidence']:assert 0<=e['start']<e['end']<=p['duration']
def test_window_bounds():
 s=session()
 with pytest.raises(ValueError):s.window({'start':0,'end':31})
 with pytest.raises(ValueError):s.window({'start':-1,'end':3})

def test_existing_eregion_loop_tool_sequence(tmp_path):
 from langchain_core.messages import AIMessage
 s=session();s.read=False;s.window_read=False;s.state['model_calls']=0
 class LocalFixture:
  request_timeout=5
  def __init__(self):self.calls=0
  def invoke(self,messages,tools):
   expected=['read_round_evidence','read_action_window','submit_analysis'][self.calls]
   assert expected in [t['function']['name'] for t in tools]
   args=[{},dict(start=17,end=28),payload(s)][self.calls];self.calls+=1
   return AIMessage(content='',tool_calls=[dict(id=str(self.calls),name=expected,args=args)])
 model=LocalFixture();h=CoachHost(s,tmp_path,model)
 try:
  result=h.run(slice_steps=8);assert s.state['result'];assert model.calls==3;assert result['reason']=='completed'
 finally:h.close()

def test_persistent_budget_cannot_reset(tmp_path,monkeypatch):
 import json
 from cs2_agent import demo_coach as c
 p=tmp_path/'coach.json';p.write_text(json.dumps({'model_calls':5}),encoding='utf-8')
 monkeypatch.setattr(c,'path',lambda *args:p)
 monkeypatch.setattr(c,'evidence',lambda *args:{})
 with pytest.raises(ValueError):c.Session('4f35a9243f58418b983a9ea1757b4cb3',17)
 assert json.loads(p.read_text())['model_calls']==5

def test_cross_floor_utility_is_not_entry_support():
 from cs2_agent import demo_coach as c
 mid='3f9df19a017b45a6a55a988b89ccab07';p=c.evidence(mid,24)
 # Original A-entry nearby-in-time B utilities are now excluded.
 assert not any(h['kind']=='utility_before_entry' for h in p['hypotheses'])

def test_all_pilot_results_have_valid_citations():
 from cs2_agent import demo_coach as c
 for mid,ns in c.PILOTS.items():
  for n in ns:
   s=c.get(mid,n);assert s['status']=='completed';assert s['model_calls']<=s['max_calls']
   ev={e['id']:e for e in s['packet']['evidence']}
   for claim in s['result']['claims']:
    assert all(x in ev for x in claim['evidence_ids']);assert claim['start']<claim['end']<=s['packet']['duration']

def test_custom_inference_not_limited_to_rule_names():
 s=session();e=s.packet['evidence'][0]
 p=dict(summary='斜坡集中提速',claims=[dict(hypothesis_id='custom',title='斜坡集结后快速进B',confidence='high',evidence_ids=[e['id']],interpretation='判断是从斜坡方向集中提速')],alternatives=[])
 assert s.submit(p)['accepted'];assert s.state['result']['claims'][0]['observed_title']=='斜坡集结后快速进B'
 p['claims'][0]['evidence_ids']=['invented'];assert not s.submit(p)['accepted']


def test_custom_identifier_and_clip_normalization():
 s=session();e=s.packet['evidence'][0]
 p=dict(summary='说明',claims=[dict(hypothesis_id='custom-ramp-rush',title='斜坡快攻',confidence='high',evidence_ids=[e['id']],interpretation='由路线推断',clip={'start':-1,'end':s.packet['duration']+1})],alternatives=[])
 assert s.submit(p)['accepted'];c=s.state['result']['claims'][0]
 assert c['hypothesis_id']=='custom' and c['start']==0 and c['end']==s.packet['duration']
 p['claims'][0]['clip']={'start':s.packet['duration']+1,'end':s.packet['duration']+2}
 assert not s.submit(p)['accepted']


def test_completed_session_does_not_cancel_next_batch_round(tmp_path,monkeypatch):
 from cs2_agent import demo_coach as c
 from langchain_core.messages import AIMessage
 packet=evidence(next(iter(PILOTS)),13)
 monkeypatch.setattr(c,'path',lambda mid,n:tmp_path/('coach-'+str(n)+'.json'))
 monkeypatch.setattr(c,'evidence',lambda mid,n:copy.deepcopy(packet))
 monkeypatch.setattr(c,'audit_saved',lambda mid,n:__import__('json').loads(c.path(mid,n).read_text()))
 monkeypatch.setattr(c,'load_config',lambda:{'endpoint':'https://example.test/chat/completions'})
 class Fixture:
  request_timeout=5
  def __init__(self,config):pass
  def invoke(self,messages,tools):
   args=dict(summary='测试',claims=[dict(title='测试判断',confidence='medium',evidence_ids=[packet['evidence'][0]['id']],interpretation='测试推断',clip={'start':0,'end':packet['duration']})],alternatives=[])
   return AIMessage(content='',tool_calls=[dict(id='submit',name='submit_analysis',args=args)])
  def close(self):pass
 monkeypatch.setattr(c,'ConfiguredModel',Fixture)
 event=threading.Event()
 for n in (1,2):
  s=c.Session('a'*32,n,additional_calls=1,endpoint_host='example.test');s.cancelled=event;s.read=True;s.window_read=True;s.run()
  assert s.state['status']=='completed';assert not event.is_set();assert s.state['model_calls']==1


def test_local_preparation_and_actual_usage_settlement(tmp_path,monkeypatch):
 from cs2_agent import demo_coach as c
 from eregion.runtime.provider_usage import provider_call
 from langchain_core.messages import AIMessage
 mid=next(iter(PILOTS))
 monkeypatch.setattr(c,'path',lambda mid,n:tmp_path/'coach.json')
 monkeypatch.setattr(c,'audit_saved',lambda mid,n:__import__('json').loads(c.path(mid,n).read_text()))
 monkeypatch.setattr(c,'load_config',lambda:{'endpoint':'https://example.test/chat/completions'})
 monkeypatch.setattr(c,'input_reservation',lambda payload:30000)
 class Fixture:
  request_timeout=5
  def __init__(self,config):self.calls=0
  def invoke(self,messages,tools):
   assert 'submit_analysis' in [t['function']['name'] for t in tools]
   assert 'inspected_window' in messages[1].content
   self.calls+=1
   with provider_call('test',input_token_reservation=30000) as usage:
    usage.update(input_tokens=50,output_tokens=10)
    args=dict(summary='测试',claims=[dict(title='斜坡进攻',confidence='medium',evidence_ids=['fake' if self.calls==1 else 'E1'],interpretation='推断',clip={'start':0,'end':30})],alternatives=[])
    return AIMessage(content='',tool_calls=[dict(id=str(self.calls),name='submit_analysis',args=args)])
  def close(self):pass
 monkeypatch.setattr(c,'ConfiguredModel',Fixture)
 s=c.Session(mid,13,additional_calls=2,endpoint_host='example.test');s.run()
 assert s.state['status']=='completed'
 assert s.state['preparation']=='local_evidence_and_window'
 assert s.state['model_calls']==2
 assert s.state['input_budget']['charged_or_reserved']==100
