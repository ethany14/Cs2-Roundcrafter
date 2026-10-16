"""Offline agent orchestration tests: these do not establish live model quality."""
import copy
import json
import pytest
from langchain_core.messages import AIMessage
from cs2_agent.agentic_rag import AgentRagResearch, AgentRagHost, MODEL_LIMIT
from cs2_agent.lineup_research import research_class, validate_request
from cs2_agent.lineup_sources import ResearchStop
from eregion.runtime.core.engine import LoopStop, ToolArgumentsError


@pytest.fixture
def research(tmp_path, monkeypatch):
    # Existing retrieval may use configured remote embeddings; never call these in offline tests.
    monkeypatch.setattr('cs2_agent.embeddings.semantic', lambda *a, **kw: (None, {'vector': 'off', 'reason': 'offline test'}))
    r = AgentRagResearch(tmp_path / 'job', {'query': 'Nuke Heaven smoke 配合', 'mode': 'rag',
                                         'map': 'de_nuke', 'side': 'T', 'party_size': 1})
    monkeypatch.setattr(r.reach, 'search', lambda *a: {'status': 'not_found', 'results': []})
    yield r
    r.sources.close()


def fixture_rows(corpus, query):
    if query == 'no match':
        return []
    return [dict(id='local-1', title='Heaven smoke', url='https://example.com/lineup',
                 text='Running Jump Throw. Origin Roof. Target Heaven.',
                 classification='historical_source_metadata', details={'game_validation': 'unverified'})]


def prepare(r, monkeypatch):
    monkeypatch.setattr(r, 'candidates', fixture_rows)
    return r.search({'corpus': 'lineups', 'query': 'Heaven'})['results'][0]['evidence_id']


def answer(eid):
    return {'findings': [{'text': '资料给出跑动跳投标签，精确瞄点仍待核对。',
                          'citations': [{'evidence_id': eid, 'quote': 'Running Jump Throw.'}]}],
            'unresolved': ['当前玩家的起点与装备未知'], 'stop_reason': 'supported_references'}


def test_dispatch_and_frozen_request():
    assert research_class({'mode': 'rag'}) is AgentRagResearch
    with pytest.raises(ValueError):
        validate_request({'query': 'Nuke', 'mode': 'rag', 'economy': 'invented'})
    with pytest.raises(ValueError):
        validate_request({'query': 'Mirage', 'mode': 'rag', 'map': 'de_nuke'})


def test_unread_or_fabricated_citation_rejected(research, monkeypatch):
    eid = prepare(research, monkeypatch)
    with pytest.raises(ValueError, match='exact passage'):
        research.submit(answer(eid))
    research.read({'evidence_id': eid})
    bad = answer(eid); bad['findings'][0]['citations'][0]['quote'] = '100 percent win rate'
    with pytest.raises(ValueError, match='exact passage'):
        research.submit(bad)
    assert research.submit(answer(eid))['accepted']
    result = research.state['result']['rag']['answer']
    assert result['findings'][0]['classification'] == 'model_inference_not_verified_advice'
    assert not result['verified_optimal']


def test_duplicate_query_persistent_snapshot_and_no_scope_relaxation(research, monkeypatch):
    eid = prepare(research, monkeypatch)
    original = copy.deepcopy(research.request)
    assert research.search({'corpus': 'lineups', 'query': ' HEAVEN  '})['cached']
    assert len(research.rag['queries']) == 1
    research.read({'evidence_id': eid})
    restored = AgentRagResearch(research.directory, research.request)
    try:
        assert restored.request == original
        assert restored.rag['read'][eid]['text'] == research.rag['read'][eid]['text']
        assert restored.submit(answer(eid))['accepted']
    finally:
        restored.sources.close()


class AdaptiveFake:
    request_timeout = 5
    def __init__(self, r): self.r, self.calls = r, 0
    def invoke(self, messages, tools):
        self.calls += 1
        names = {t['function']['name'] for t in tools}
        if self.calls == 1:
            name, args = 'search_knowledge', {'corpus': 'tactics', 'query': 'no match'}
        elif self.calls == 2:
            assert not self.r.rag['candidates']
            name, args = 'search_knowledge', {'corpus': 'lineups', 'query': 'Heaven'}
        elif self.calls == 3:
            name, args = 'read_knowledge', {'evidence_id': next(iter(self.r.rag['candidates']))}
        else:
            name, args = 'submit_rag_answer', answer(next(iter(self.r.rag['read'])))
        assert name in names
        return AIMessage(content='', tool_calls=[{'id': f'call-{self.calls}', 'name': name, 'args': args}])
    def close(self): pass


def test_real_kernel_adapts_query_reads_and_submits(research, monkeypatch):
    monkeypatch.setattr(research, 'candidates', fixture_rows)
    h = AgentRagHost(research, AdaptiveFake(research)); research.state['agent'] = {}
    try:
        assert h.run(slice_steps=8)['reason'] == 'completed'
        assert h.state['calls'] == 4
        assert [e['action'] for e in research.rag['trace']] == ['search_local', 'search_local', 'read_evidence', 'submit_answer']
        assert research.rag['trace'][0]['found'] == 0
        assert research.state['budget']['used']['search'] == 0
        assert (research.directory / 'task.json').exists()
    finally:
        h.close()


def test_full_worker_retains_answer_and_call_accounting(research, monkeypatch):
    monkeypatch.setattr(research, 'candidates', fixture_rows)
    monkeypatch.setattr('cs2_agent.lineup_research.load_config', lambda: {'max_tokens': 1000, 'timeout': 5, 'endpoint': 'https://example.invalid'})
    monkeypatch.setattr('cs2_agent.lineup_research.ConfiguredModel', lambda c: AdaptiveFake(research))
    research.run()
    assert research.state['status'] == 'completed'
    assert research.state['agent']['model_calls'] == 4
    assert research.state['result']['rag']['answer']['findings']
    assert research.state['result']['completion_status'] == 'completed'


def test_no_model_fallback_is_local_and_not_an_agent_answer(research, monkeypatch):
    monkeypatch.setattr(research, 'candidates', fixture_rows)
    def missing(): raise ValueError('not configured')
    monkeypatch.setattr('cs2_agent.lineup_research.load_config', missing)
    monkeypatch.setattr(research.sources, 'search', lambda q: pytest.fail('Fallback must not search the web'))
    research.run()
    assert research.state['status'] == 'partial_model_not_configured'
    assert research.state['agent']['model_calls'] == 0
    assert research.state['result']['rag']['answer'] is None
    assert len(research.rag['queries']) == 3


def test_budget_cancel_and_last_call_policy(research, monkeypatch):
    eid = prepare(research, monkeypatch)
    h = AgentRagHost(research, None)
    try:
        h.state['calls'] = MODEL_LIMIT - 1
        assert [t['function']['name'] for t in h.observe().tools] == ['submit_rag_answer']
        h.state['calls'] = MODEL_LIMIT
        with pytest.raises(LoopStop): h.observe()
        research.cancelled.set()
        with pytest.raises(ResearchStop): research.read({'evidence_id': eid})
        assert eid not in research.rag['read']
    finally:
        h.close()


def test_no_free_finish_and_source_search_order(research):
    h = AgentRagHost(research, None)
    try:
        with pytest.raises(ToolArgumentsError):
            h.validate({'name': 'finish_task', 'args': {'text': 'invented answer'}}, h.observe())
        with pytest.raises(ValueError, match='local knowledge'):
            research.search_public({'query': 'Heaven'})
        with pytest.raises(ValueError, match='discovered'):
            research.read_public({'url': 'https://example.com/unknown'})
    finally:
        h.close()


def test_live_local_lineups_preserve_map_side_and_motion(research):
    found = research.search({'corpus': 'lineups', 'query': 'Heaven smoke'})['results']
    assert found
    row = research.read({'evidence_id': found[0]['evidence_id']})
    assert row['details']['compatibility']['conflicts'] == []
    research.request['side'] = 'CT'
    assert not research.candidates('lineups', 'Heaven smoke')


def test_public_source_quote_requires_read_and_discoveries_survive_restart(research, monkeypatch):
    prepare(research, monkeypatch)
    url = 'https://example.com/public'
    def discover(q):
        research.sources.discovered.add(url)
        return {'status': 'found', 'results': [{'url': url, 'title': 'Nuke Heaven smoke tutorial', 'snippet': 'not evidence'}]}
    monkeypatch.setattr(research.sources, 'search', discover)
    research.search_public({'query': 'Heaven smoke'})
    assert not research.rag['read']
    restored = AgentRagResearch(research.directory, research.request)
    try:
        assert url in restored.sources.discovered
        monkeypatch.setattr(restored, 'read_source', lambda a: {'status': 'read', 'text': 'Running Jump Throw.', 'title': 'tutorial'})
        page = restored.read_public({'url': url})
        assert restored.submit(answer(page['evidence_id']))['accepted']
        assert page['classification'] == 'public_source_text_unverified_applicability'
    finally:
        restored.sources.close()


def test_tactic_economy_and_player_constraints_are_passed_without_model_control(research, monkeypatch):
    seen = []
    def retrieve(raw):
        seen.append(raw)
        return {'results': []}
    monkeypatch.setattr('cs2_agent.tactics_rag.retrieve', retrieve)
    research.request['economy'] = 'eco'
    research.candidates('tactics', 'rifle CT Dust2')
    assert seen[0]['map'] == 'de_nuke' and seen[0]['side'] == 'T'
    assert seen[0]['economy'] == 'eco' and seen[0]['party_size'] == 1


def test_case_search_filters_other_maps_and_sides_and_keeps_inference_scope(research, monkeypatch):
    def case(cid, map_name, side):
        return {'id': cid, 'map': map_name, 'side': side, 'title': 'Heaven smoke', 'interpretation': 'Smoke toward Heaven',
                'evidence': [{'text': 'Smoke event observed'}], 'source': {'demo_sha256': 'fixture'},
                'replay_url': '/demos?match=fixture', 'round': 2}
    monkeypatch.setattr('cs2_agent.tactic_cases.catalog', lambda: {'cases': [
        case('1', 'de_nuke', 'T'), case('2', 'de_nuke', 'CT'), case('3', 'de_mirage', 'T')]})
    rows = research.candidates('cases', 'Heaven')
    assert [r['id'] for r in rows] == ['1']
    assert rows[0]['classification'] == 'demo_observations_plus_model_inference'
    assert rows[0]['details']['economy_compatibility'] == 'unknown'


def test_query_limit_and_failed_search_remain_visible(research, monkeypatch):
    def fail(*args): raise OSError('fixture unavailable')
    monkeypatch.setattr(research, 'candidates', fail)
    with pytest.raises(OSError): research.search({'corpus': 'cases', 'query': 'Heaven'})
    assert research.search({'corpus': 'cases', 'query': 'Heaven'})['failure'] == 'OSError'
    monkeypatch.setattr(research, 'candidates', fixture_rows)
    for i in range(5): research.search({'corpus': 'lineups', 'query': str(i)})
    with pytest.raises(ValueError, match='query budget'):
        research.search({'corpus': 'lineups', 'query': 'seventh query'})


def test_model_failure_salvages_read_evidence(research, monkeypatch):
    eid = prepare(research, monkeypatch); research.read({'evidence_id': eid})
    monkeypatch.setattr('cs2_agent.lineup_research.load_config', lambda: {'max_tokens': 1000, 'timeout': 5, 'endpoint': 'https://example.invalid'})
    class Broken:
        request_timeout = 1
        def invoke(self, *args): raise OSError('offline fixture')
        def close(self): pass
    monkeypatch.setattr('cs2_agent.lineup_research.ConfiguredModel', lambda c: Broken())
    research.run()
    assert research.state['status'] == 'model_or_runtime_failed'
    assert research.state['result']['rag']['evidence'][0]['evidence_id'] == eid
    assert research.state['result']['rag']['answer'] is None


def test_resume_preserves_model_budget(research, monkeypatch):
    prepare(research, monkeypatch)
    h = AgentRagHost(research, None)
    h.state['calls'] = MODEL_LIMIT; h._save(); h.close()
    restored = AgentRagResearch(research.directory, research.request)
    again = AgentRagHost(restored, None)
    try:
        assert again.state['calls'] == MODEL_LIMIT
        with pytest.raises(LoopStop): again.observe()
    finally:
        again.close(); restored.sources.close()


def test_kernel_executes_independent_queries_in_one_response(research, monkeypatch):
    monkeypatch.setattr(research, 'candidates', fixture_rows)
    class BatchModel(AdaptiveFake):
        def invoke(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content='', tool_calls=[
                    {'id': 'q-' + c, 'name': 'search_knowledge', 'args': {'corpus': c, 'query': 'Heaven'}}
                    for c in ('lineups', 'tactics', 'cases')])
            assert len(self.r.rag['queries']) == 3
            return AIMessage(content='', tool_calls=[{'id': 'done', 'name': 'submit_rag_answer',
                'args': {'findings': [], 'unresolved': ['Only leads were found'], 'stop_reason': 'insufficient_evidence'}}])
    h = AgentRagHost(research, BatchModel(research)); research.state['agent'] = {}
    try:
        assert h.run(slice_steps=8)['reason'] == 'completed'
        assert h.state['calls'] == 2
        assert len(research.rag['queries']) == 3
        assert 'submit_rag_answer' not in h.observe().batchable
    finally:
        h.close()


def test_web_relevance_filters_generic_and_wrong_target(research, monkeypatch):
    prepare(research, monkeypatch)
    monkeypatch.setattr(research.sources, 'search', lambda q: {'status': 'found', 'results': [
        {'url': 'https://counter-strike.net/cs2', 'title': 'Counter Strike 2'},
        {'url': 'https://example.com/nuke-ramp', 'title': 'Nuke Ramp smoke'},
        {'url': 'https://example.com/heaven', 'title': 'Nuke Heaven smoke from Roof'}]})
    result = research.search_public({'query': 'Nuke Heaven smoke'})
    assert result['rejected_count'] == 2
    assert [r['url'] for r in result['results']] == ['https://example.com/heaven']
    result = research.search_public({'query': 'Nuke Secret smoke'})
    assert result['status'] == 'no_relevant_results'
    assert not result['results']


def test_empty_scope_feedback_does_not_relax_economy(research):
    research.request['economy'] = 'force'
    assert research.coverage()['tactics']['scope_count'] == 0
    assert research.coverage()['cases']['scope_count'] > 0
    assert research.request['economy'] == 'force'


def test_irrelevant_web_uses_bounded_video_discovery(research, monkeypatch):
    prepare(research, monkeypatch)
    monkeypatch.setattr(research.sources, 'search', lambda q: {'status': 'found', 'results': [
        {'url': 'https://example.com', 'title': 'Nuclear explosions'}]})
    used = []
    def video(platform, query):
        used.append(platform)
        return {'status': 'found', 'provider': 'youtube', 'results': [
            {'url': 'https://youtube.com/watch?v=abcdefghijk', 'title': 'CS2 Nuke Heaven smoke'}]}
    monkeypatch.setattr(research.reach, 'search', video)
    result = research.search_public({'query': 'Heaven smoke'})
    assert used == ['youtube']
    assert result['provider'] == 'youtube'
    assert result['attempts'][0]['relevant'] == 0
    assert result['results'] and not research.rag['read']
    research.budget.state['used']['search'] = research.budget.state['limits']['search']
    research.search_public({'query': 'Heaven smoke'})
    assert len(used) == 1


def test_rag_timeout_respects_configuration_without_45_second_cap(research, monkeypatch):
    monkeypatch.setattr(research, 'candidates', fixture_rows)
    monkeypatch.setattr('cs2_agent.lineup_research.load_config', lambda: {'max_tokens': 1800, 'timeout': 180, 'endpoint': 'https://example.invalid'})
    seen = []
    def model(config):
        seen.append(config['timeout'])
        return AdaptiveFake(research)
    monkeypatch.setattr('cs2_agent.lineup_research.ConfiguredModel', model)
    research.run()
    assert seen == [120]
    assert research.state['status'] == 'completed'


def test_cooperation_is_not_alive_or_equipment(research):
    research.request.update(party_size=3, economy='force')
    assert research.conditions()['alive_players'] is None
    result = research.compare_conditions({'cooperating_players':5,'alive_players':5,'smoke':2})
    assert [x['status'] for x in result['comparisons']] == ['insufficient','unknown','unknown']
    research.request.update(alive_players=5,utility={'smoke':0,'flash':2})
    result = research.compare_conditions({'alive_players':5,'smoke':1,'flash':2,'fire':1})
    assert [x['status'] for x in result['comparisons']] == ['enough_for_this_count_only','insufficient','enough_for_this_count_only','unknown']


def test_unfilled_and_invalid_conditions():
    base={'query':'Nuke tactics','mode':'rag','map':'de_nuke'}
    assert validate_request(base)['party_size'] is None
    for fields in [{'party_size':True},{'alive_players':0},{'party_size':4,'alive_players':3},{'utility':{'smoke':True}},{'utility':{'smoke':-1}}]:
        with pytest.raises(ValueError):validate_request({**base,**fields})
    assert validate_request({**base,'utility':{'smoke':0}})['utility'] == {'smoke':0}


def test_unknown_player_count_does_not_filter_case_or_lineup(research):
    research.request['party_size']=None
    assert research.candidates('lineups','Heaven smoke')
    assert research.conditions()['cooperating_players'] is None
