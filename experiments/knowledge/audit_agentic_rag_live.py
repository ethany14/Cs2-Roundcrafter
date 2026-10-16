"""Read-only live-run audit; saves no credentials and makes no model requests."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from cs2_agent.lineup_catalog import write_json
from cs2_agent.lineup_research import RUNS


def audit(base):
    manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    rows = []
    for task in manifest['tasks']:
        result = json.loads((base / (task['name'] + '.json')).read_text(encoding='utf-8'))
        directory = RUNS / task['job_id']
        state = json.loads((directory / 'task.json').read_text(encoding='utf-8'))
        research = json.loads((directory / 'research.json').read_text(encoding='utf-8'))
        events = state['runtime']['events']
        groups = state['runtime']['transcript']
        started, latencies = None, []
        for event in events:
            if event['kind'] == 'model_started':
                started = datetime.fromisoformat(event['at'])
            elif event['kind'] in {'model_completed', 'output_rejected'} and started:
                latencies.append(round((datetime.fromisoformat(event['at']) - started).total_seconds(), 3))
                started = None
        citations = [c for f in (result.get('answer') or {}).get('findings', []) for c in f['citations']]
        evidence = research['rag']['read']
        rows.append({
            'name': task['name'], 'job_id': task['job_id'], 'status': result['status'],
            'seconds': result['seconds'], 'calls': state['calls'],
            'model_latency_seconds': latencies,
            'output_rejections': [e for e in events if e['kind'] == 'output_rejected'],
            'executed_tools': sum(e['kind'] == 'tool_started' for e in events),
            'requested_tools': sum(e.get('tool_count', 0) for e in events if e['kind'] == 'model_completed'),
            'deferred_in_retained_transcript': sum(bool(r.get('value', {}).get('deferred')) for g in groups for r in g['results']),
            'public_progress': [g['assistant']['text'] for g in groups if g['assistant']['text']],
            'network_used': research['budget']['used'], 'web_searches': research['rag'].get('web_searches', []),
            'read_source_attempts': research.get('source_attempts', []),
            'answer': result['answer'], 'citations_count': len(citations),
            'all_citations_match_read_text': all(c['evidence_id'] in evidence and c['quote'] in evidence[c['evidence_id']]['text'] for c in citations),
            'usage': result['agent']['usage'], 'tool_errors': result['tool_errors'],
        })
    write_json(base / 'evaluation-audit.json', rows)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directories', nargs='+', type=Path)
    args = parser.parse_args()
    for base in args.directories:
        rows = audit(base)
        print(json.dumps([{'name': r['name'], 'status': r['status'], 'calls': r['calls'],
                           'tools': r['executed_tools'], 'deferred': r['deferred_in_retained_transcript'],
                           'latency': r['model_latency_seconds']} for r in rows]))
