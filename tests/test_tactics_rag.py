import copy,json
import pytest
from langchain_core.messages import AIMessage
from cs2_agent import tactics_rag as r
def sample(**kw):return dict(map='de_dust2',side='T',economy='rifle',query='A 区夹击',**kw)
def test_actual_sources_filters_and_chinese_query():
 r.build_index();v=r.retrieve(sample());assert v['results'][0]['id']=='a-split---faze-2'
 assert all(c['map']=='de_dust2' and c['side']=='T' and c['economy']=='rifle' for c in v['results'])
 assert v['eligible_recommendations']==[] and all(not c['fit']['ready_for_recommendation'] for c in v['results'])
 assert not r.retrieve(dict(map='de_cache',side='T',economy='rifle'))['results']
def test_unknown_is_not_zero_or_satisfied():
 card=r.retrieve(sample())['results'][0];s=r.scenario(sample());assert 'utility' in r.eligibility(card,s)['unknown']
 card=copy.deepcopy(card);card['requirements'].update(players=4,coordination=3,utility={'smoke':2})
 assert 'coordination_not_available' in r.eligibility(card,s)['blocked']
 s.update(party_size=5,utility={'smoke':1});assert 'insufficient_smoke' in r.eligibility(card,s)['blocked']
 s['utility']=None;assert 'available_smoke' in r.eligibility(card,s)['unknown']
@pytest.mark.parametrize('change',[{'players':True},{'party_size':6},{'map':"' OR 1=1 --"},{'utility':{'smoke':-1}},{'enemy_positions':[]}])
def test_bad_scenario_rejected(change):
 with pytest.raises(ValueError):r.scenario({**sample(),**change})
def test_output_cannot_add_unsupported_advice():
 evidence=r.packet(sample());good=evidence['candidates'][0]['id'];assert r.validate_selection({'selected_ids':[good]},evidence)==[good]
 for v in [{'selected_ids':['not-a-source']},{'selected_ids':[good,good]},{'selected_ids':[good],'win_rate':.9},{'selected_ids':[],'steps':['invented lineup']}]:
  with pytest.raises(ValueError):r.validate_selection(v,evidence)
def test_mock_external_generation_one_call_and_sources():
 class Fake:
  calls=0
  def invoke(self,messages,tools):
   self.calls+=1;packet=json.loads(messages[-1].content);assert not tools;return AIMessage(content=json.dumps({'selected_ids':[packet['candidates'][0]['id']]}))
 model=Fake();out=r.generate(sample(),model);assert model.calls==1 and out['model_calls']==1;assert out['selected'][0]['source_url'].startswith('https://www.cs2.app/')
def test_provider_no_empty_tools():
 import httpx
 from cs2_agent.provider import ConfiguredModel
 def respond(request):
  body=json.loads(request.content);assert 'tools' not in body and 'tool_choice' not in body
  return httpx.Response(200,json={'choices':[{'message':{'content':'{"selected_ids":[]}'},'finish_reason':'stop'}]})
 config={'timeout':5,'LLM_MODEL_ID':'test','token_field':'max_tokens','max_tokens':256,'endpoint':'https://example.invalid/chat/completions','LLM_API_KEY':'test-only'}
 m=ConfiguredModel(config,transport=httpx.MockTransport(respond))
 try:assert m.invoke([],[]).content=='{"selected_ids":[]}'
 finally:m.close()
