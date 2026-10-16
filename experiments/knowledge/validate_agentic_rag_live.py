"""Bounded live acceptance. Uses production research/tools, no scripted model responses.

Prepare a fixed manifest before running. Existing completed attempts are never replayed.
Audit wrapper records tool I/O but leaves policy, provider, data and budgets unchanged.
"""
import argparse
import json
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from cs2_agent.agentic_rag import AgentRagResearch, AgentRagHost
from cs2_agent.lineup_research import RUNS
from cs2_agent.lineup_catalog import write_json, now
from cs2_agent.provider import load_config
from cs2_agent.casebook import ROOT

BASE = ROOT / 'outputs/agentic-rag/2026-10-15-live-v1'
CALL_LIMIT = 8
TASKS = [
    ('roof_heaven', {'query': 'Nuke T方，我在Roof，想封Heaven烟配合进A。具体站在哪里、瞄哪里、怎么出手？这颗烟能不能让我一个人直接进点？',
                     'mode': 'rag', 'map': 'de_nuke', 'side': 'T', 'party_size': 1, 'origin': ['Roof']}),
    ('force_ramp', {'query': 'Nuke T方强起局，只有3个人能配合，想用外场或A区牵制再转Ramp。有什么职业战术或比赛参考？哪些动作能借鉴，哪些配合条件不满足？',
                    'mode': 'rag', 'map': 'de_nuke', 'side': 'T', 'party_size': 3, 'economy': 'force'}),
    ('mirage_window', {'query': 'Mirage T方，我想学习从T出生区域封中路Window的烟，最好一个人就能扔。请给出可用的教学来源和动作方法，并说明目前还不能确认什么。',
                       'mode': 'rag', 'map': 'de_mirage', 'side': 'T', 'party_size': 1}),
]


class AuditHost(AgentRagHost):
    def execute(self, call, turn):
        path = self.directory / 'live-tool-audit.json'
        events = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        entry = {'model_call': self.state['calls'], 'at': now(), 'tool': call['name'], 'arguments': call['args']}
        events.append(entry)
        write_json(path, events)  # Record intent, including interrupted attempts.
        started = time.monotonic()
        try:
            result = super().execute(call, turn)
            entry['result'] = result
            return result
        except Exception as exc:
            entry['exception_type'] = type(exc).__name__
            raise
        finally:
            entry['seconds'] = round(time.monotonic() - started, 3)
            write_json(path, events)
            print(json.dumps({'event': 'tool', 'job': self.directory.name, 'call': self.state['calls'],
                              'tool': call['name'], 'seconds': entry['seconds'], 'failed': 'exception_type' in entry}), flush=True)


def prepare():
    target = BASE / 'manifest.json'
    if target.exists():
        return json.loads(target.read_text(encoding='utf-8'))
    cfg = load_config()
    manifest = {'created_at': now(), 'model': cfg['LLM_MODEL_ID'], 'host': urlsplit(cfg['endpoint']).hostname,
                'model_calls_per_job': CALL_LIMIT, 'total_model_call_limit': CALL_LIMIT * len(TASKS),
                'policy': 'Current production AgentLoop and retrieval; no test-specific prompts, scripted responses or forced follow-up queries.',
                'criteria': ['Model chooses corpus/query', 'Reads evidence before citing',
                             'After a concrete missing field or no result, takes a relevant follow-up action',
                             'Distinguishes discovering leads from filling the information gap',
                             'Reports unresolved conditions without invented aiming instructions or win rates'],
                'tasks': [{'name': name, 'job_id': uuid.uuid4().hex, 'request': request} for name, request in TASKS]}
    write_json(target, manifest)
    return manifest


def run(task, manifest):
    output = BASE / (task['name'] + '.json')
    if output.exists():
        print(json.dumps({'event': 'skip_existing', 'name': task['name']}), flush=True)
        return
    cfg = load_config()
    if (cfg['LLM_MODEL_ID'], urlsplit(cfg['endpoint']).hostname) != (manifest['model'], manifest['host']):
        raise ValueError('Model configuration changed after manifest preparation')
    directory = RUNS / task['job_id']
    if (directory / 'task.json').exists():
        raise ValueError('Partial attempt exists; inspect before any further live call')
    r = AgentRagResearch(directory, task['request'])
    r.model_limit = manifest['model_calls_per_job']
    r.host_class = AuditHost
    print(json.dumps({'event': 'start', 'name': task['name'], 'job_id': task['job_id']}), flush=True)
    started = time.monotonic()
    r.run()
    state = json.loads((directory / 'research.json').read_text(encoding='utf-8'))
    host = json.loads((directory / 'task.json').read_text(encoding='utf-8')) if (directory / 'task.json').exists() else {}
    result = {'name': task['name'], 'job_id': task['job_id'], 'request': task['request'],
              'seconds': round(time.monotonic() - started, 3), 'status': state['status'],
              'agent': state.get('agent'), 'network': state['budget'], 'trace': state['rag']['trace'],
              'answer': state['rag']['answer'], 'tool_errors': host.get('tool_errors', []),
              'read_evidence': list(state['rag']['read'].values()), 'failure': state.get('failure'),
              'viewer': 'http://127.0.0.1:8790/demos?view=research&job=' + task['job_id']}
    write_json(output, result)
    print(json.dumps({'event': 'complete', 'name': task['name'], 'status': result['status'],
                      'seconds': result['seconds'], 'calls': (result['agent'] or {}).get('model_calls'),
                      'actions': [x['action'] for x in result['trace']], 'tool_errors': len(result['tool_errors'])}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--run-all', action='store_true')
    parser.add_argument('--output-dir', type=Path, help='New directory for an explicitly authorized rerun; never overwrites previous attempts.')
    parser.add_argument('--tasks', nargs='+', choices=[n for n, _ in TASKS])
    parser.add_argument('--calls', type=int, choices=range(1, 9), default=8)
    args = parser.parse_args()
    CALL_LIMIT = args.calls
    if args.tasks:
        TASKS = [(n, r) for n, r in TASKS if n in args.tasks]
    if args.output_dir:
        BASE = args.output_dir.resolve()
    manifest = prepare()
    if args.run_all:
        for task in manifest['tasks']:
            run(task, manifest)
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
