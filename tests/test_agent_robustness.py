"""Agent calls must not be wasted on format slips, and a rejected call must tell the retry why it was rejected."""
import json
import threading
import pytest
from eregion.runtime.core.engine import Turn, ToolArgumentsError
from cs2_agent.host import WorkspaceHost, repair_args
from cs2_agent.tools import Tool, function
from cs2_agent.lineup_catalog import write_json

CLAIM = {'type': 'object', 'properties': {'title': {'type': 'string', 'maxLength': 10}, 'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
         'clip': {'type': 'object', 'properties': {'start': {'type': 'number'}, 'end': {'type': 'number'}}, 'required': ['start', 'end'], 'additionalProperties': False}},
         'required': ['evidence_ids'], 'additionalProperties': False}
SUBMIT = function('submit', 'x', {'summary': {'type': 'string', 'maxLength': 20}, 'claims': {'type': 'array', 'maxItems': 2, 'items': CLAIM},
                                  'alternatives': {'type': 'array', 'items': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}}},
                  required=['summary', 'claims'])


def test_repair_fixes_format_slips_without_inventing_content():
    args = {'summary': 'x' * 50, 'extra': 1,
            'claims': [{'title': 'a very long title', 'evidence_ids': 'e1', 'facts': ['not in schema'], 'clip': {'start': '3', 'end': 9}}] * 3,
            'alternatives': ['plain string']}
    fixed = repair_args(args, SUBMIT['function']['parameters'])
    assert 'extra' not in fixed and len(fixed['summary']) == 20 and fixed['summary'].endswith('…')
    assert len(fixed['claims']) == 2 and fixed['claims'][0] == {'title': 'a very lo…', 'evidence_ids': ['e1'], 'clip': {'start': 3.0, 'end': 9}}
    assert fixed['alternatives'] == [{'text': 'plain string'}]


def host(tmp_path):
    return WorkspaceHost(tmp_path / 'task', None, [Tool(SUBMIT, lambda a: {'accepted': True})], request='r', max_calls=2)


def test_validate_repairs_then_still_rejects_real_gaps(tmp_path):
    h = host(tmp_path)
    turn = Turn('p', {}, [SUBMIT])
    call = {'name': 'submit', 'args': {'summary': 'ok', 'claims': [{'evidence_ids': ['e1'], 'clip': {'start': 0, 'end': 1}, 'note': 'x'}], 'alternatives': ['a']}}
    h.validate(call, turn)  # extra key and bare-string alternative are repaired, not rejected
    with pytest.raises(ToolArgumentsError):
        h.validate({'name': 'submit', 'args': {'summary': 'ok', 'claims': [{'title': 'no evidence'}]}}, turn)


def test_rejection_message_reaches_the_next_call(tmp_path):
    h = host(tmp_path)
    assert h.feedback() == {}
    out = h.action_error(ValueError('每条判断须引用双方真实证据'))
    assert out['message'] == '每条判断须引用双方真实证据'
    assert h.feedback() == {'previous_attempt_rejected': '每条判断须引用双方真实证据'}
    assert json.loads((tmp_path / 'task' / 'task.json').read_text(encoding='utf-8'))['tool_errors'][0]['message'] == '每条判断须引用双方真实证据'


def test_round_coach_does_not_require_clip_or_alternatives():
    from cs2_agent import demo_coach
    params = demo_coach.Session.tools(type('S', (), {'overview': None, 'window': None, 'submit': None})())[2].definition['function']['parameters']
    assert params['required'] == ['summary', 'claims'] and 'clip' not in params['properties']['claims']['items']['required']


def test_parallel_json_writes_do_not_collide(tmp_path):
    target = tmp_path / 'job.json'
    errors = []
    def writer(i):
        try:
            for k in range(30):write_json(target, {'writer': i, 'k': k})
        except Exception as e:errors.append(e)
    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert not errors and json.loads(target.read_text(encoding='utf-8'))['k'] == 29
    assert not list(tmp_path.glob('*.tmp'))
