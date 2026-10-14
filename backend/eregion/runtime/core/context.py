"""Bounded, restartable model context. Tool exchanges are retained as whole groups."""
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


PRIVATE_KEYS = {'image', 'password', 'credentials', 'secret', 'api_key', 'access_token',
                'refresh_token', 'cookies', 'resume_base64', 'decision_history',
                'user_messages', 'resume_context', 'sources', 'facts', 'loop_runtime'}


def compact(value, depth=0):
    if depth > 8:
        return '[nested data omitted]'
    if isinstance(value, str):
        return value[:3000]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, list):
        return [compact(v, depth + 1) for v in value[:30]]
    if isinstance(value, dict):
        return {k: compact(v, depth + 1) for k, v in list(value.items())[:60]
                if k.casefold() not in PRIVATE_KEYS}
    return type(value).__name__


def trace_value(value):
    value = compact(value)
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded) <= 8000:
        return value
    # Audit excerpts must not swallow the error/recovery signal appended after
    # a long page. Model replay uses lossless archive references separately.
    important = {k: value[k] for k in ('error', 'error_code', 'next', 'progress_feedback',
        'observation_id', 'context_ref', 'read_with', 'saved', 'failed', 'retryable') if isinstance(value, dict) and k in value}
    return {'excerpt': encoded[:6000], 'truncated': True, **important}


class ConversationWindow:
    """No screenshots or provider reasoning in storage; no orphaned tool results."""
    def __init__(self, groups=(), *, max_chars=24000, max_groups=8):
        self.max_chars, self.max_groups = max_chars, max_groups
        self.groups = []
        self.dropped_since_request = 0
        for group in groups:
            try:
                calls = group['assistant']['tool_calls']
                if [c['id'] for c in calls] != [r['id'] for r in group['results']]:
                    continue
                if not all(isinstance(c['args'], dict) for c in calls):
                    continue
                self.groups.append(group)
            except (KeyError, TypeError):
                continue
        self._trim()

    def _trim(self):
        from eregion.runtime.request_options import history_policy
        checkpoint = history_policy() == 'checkpoint'
        pressure = len(self.groups) > self.max_groups or len(json.dumps(self.groups, ensure_ascii=False)) > self.max_chars
        if checkpoint and pressure and len(self.groups) > 1:
            count = max(1, len(self.groups) // 2)
            del self.groups[:count]
            self.dropped_since_request += count
        while len(self.groups) > self.max_groups or (
                len(self.groups) > 1 and len(json.dumps(self.groups, ensure_ascii=False)) > self.max_chars):
            self.groups.pop(0)
            self.dropped_since_request += 1
        # An oversized exchange is represented by domain history in the live
        # snapshot instead. Never cut an argument JSON string or half a tool group.
        if self.groups and len(json.dumps(self.groups, ensure_ascii=False)) > self.max_chars:
            self.dropped_since_request += len(self.groups)
            self.groups.clear()

    def append(self, snapshot, text, calls, results, revision):
        messages = snapshot.get('messages') or snapshot.get('user_messages') or []
        latest = next((m for m in reversed(messages) if m.get('role') == 'user'), None)
        # Tool arguments are exact unless they contain a prohibited secret key.
        # Such a call is omitted from model replay, not persisted with changed semantics.
        encoded = json.dumps(calls, ensure_ascii=False)
        def contains_secret(value):
            if isinstance(value, dict):
                return any(k.casefold() in PRIVATE_KEYS or contains_secret(v) for k, v in value.items())
            return isinstance(value, list) and any(contains_secret(v) for v in value)
        if len(encoded) > 12000 or contains_secret(calls):
            return
        self.groups.append({'request': {'historical_request': trace_value(
                snapshot.get('current_request', {}).get('message') or latest),
                'context_note': 'Historical tool exchange only. The live current_request determines what to do now.'},
            'assistant': {'text': text[:4000], 'tool_calls': calls},
            'results': [{'id': call['id'], 'name': call['name'], 'value': result}
                        for call, result in zip(calls, results)], 'revision': revision})
        self._trim()

    def snapshot(self, snapshot):
        """Elide only exact duplicates already available as complete tool exchanges.

        Legacy histories without call IDs, changed outcomes and trimmed exchanges
        stay visible. Persisted domain history is never modified.
        """
        replay = {r['id']: (c, r) for g in self.groups
                  for c, r in zip(g['assistant']['tool_calls'], g['results'])}
        result = dict(snapshot)
        for key in ('history', 'decision_history'):
            if not isinstance(snapshot.get(key), list):
                continue
            rows = []
            for entry in snapshot[key]:
                pair = replay.get(entry.get('call_id'))
                if pair:
                    call, outcome = pair
                    if (entry.get('tool') == call['name']
                            and entry.get('arguments') == trace_value(call['args'])
                            and entry.get('result') == outcome['value']):
                        entry = {k: v for k, v in entry.items() if k not in {'arguments', 'result'}}
                        entry['result_in_tool_message'] = call['id']
                rows.append(entry)
            result[key] = rows
        return result

    def messages(self):
        messages, previous_request = [], None
        for group in self.groups:
            assistant = group['assistant']
            old_request = group['request']
            # Migrate replay at read time; preserve the original audit on disk.
            request = json.dumps({'historical_request': old_request.get('historical_request',
                old_request.get('request') or old_request.get('goal')),
                'historical_revision': group.get('revision'),
                'context_note': 'Past exchange, not a renewed instruction. Follow the live current_request and live outcomes.'},
                ensure_ascii=False, separators=(',', ':'))
            identity = (group.get('revision'), request)
            if identity != previous_request:
                messages.append(HumanMessage(content=request))
            previous_request = identity
            messages.append(AIMessage(content=assistant['text'], tool_calls=assistant['tool_calls']))
            messages.extend(ToolMessage(content=json.dumps(r['value'], ensure_ascii=False, separators=(',', ':')),
                tool_call_id=r['id'], name=r['name']) for r in group['results'])
        return messages
