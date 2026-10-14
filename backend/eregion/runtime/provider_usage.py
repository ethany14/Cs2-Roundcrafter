"""Provider-call ledger. Stores counts and identifiers, never prompts or credentials."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
import json
import logging
import time
import os
from functools import wraps
from uuid import uuid4

from sqlalchemy import Boolean, Column, String, Text, or_, select, update
from eregion.runtime.storage import Base

log = logging.getLogger(__name__)
_scope = ContextVar('provider_usage_scope', default={})
_observers = ContextVar('provider_attempt_observers', default=())


class TaskProviderBudgetExceeded(BaseException):
    """Control-flow stop: semantic fallbacks must never swallow a task limit."""
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def task_limits():
    result = {}
    for metric, name in (('provider_attempts', 'JOB_AGENT_TASK_MAX_PROVIDER_ATTEMPTS'),
                         ('input_tokens', 'JOB_AGENT_TASK_MAX_INPUT_TOKENS')):
        value = os.getenv(name, '').strip()
        if value:
            try:
                number = int(value)
                if number < 0: raise ValueError()
            except ValueError:
                raise TaskProviderBudgetExceeded('invalid_' + name)
            result[metric] = number
    return result


def input_reservation(payload):
    """Conservative text reservation; exact provider usage replaces it on finish.

    UTF-8 bytes plus framing allowance, rather than pretending chars are tokens.
    Images have provider-specific accounting and fail closed under an input cap.
    """
    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    if 'image_url' in encoded or 'input_audio' in encoded:
        return None
    return len(encoded.encode('utf-8')) + 1024


@contextmanager
def capture_provider_attempts():
    """Attempt events independent of ledger availability; copied into workers."""
    rows = []
    token = _observers.set((*_observers.get(), rows))
    try:
        yield rows
    finally:
        _observers.reset(token)


def _observe(details):
    for rows in _observers.get():
        rows.append(details)


@contextmanager
def adapter_attempt(model='unmetered-analyzer'):
    """Count an unmetered adapter only when it has no concrete child attempts.

    Adapter fallback has unknown tokens and explicit origin. It never fabricates
    durable provider records or a zero-cost claim.
    """
    started = time.monotonic()
    scope = current_scope()
    details = {'model':model, 'purpose':scope.get('purpose','analysis-adapter'),
        'call_id':str(uuid4()),
        'model_route':scope.get('model_route','main'), 'attempt':scope.get('attempt',1),
        'source':'adapter', 'status':'pending'}
    try:
        with capture_provider_attempts() as children:
            try:
                yield
                details['status'] = 'completed'
            except BaseException as exc:
                details.update(status='failed', error_type=type(exc).__name__)
                raise
    finally:
        details['duration_seconds'] = round(time.monotonic()-started,3)
        if not children:
            _observe(details)


class ProviderUsageRow(Base):
    __tablename__ = 'provider_usage'
    call_id = Column(String(40), primary_key=True)
    task_id = Column(String(40), index=True)
    run_id = Column(String(40), index=True)
    request_id = Column(String(40), index=True)
    adopted = Column(Boolean, nullable=False, default=True)
    created_at = Column(String(40), nullable=False)
    details_json = Column(Text, nullable=False)


@contextmanager
def usage_scope(**values):
    token = _scope.set({**_scope.get(), **values})
    try:
        yield
    finally:
        _scope.reset(token)


def current_scope():
    return dict(_scope.get())


def track_run(identifier, purpose):
    """Re-establish attribution on worker resume, including after a server restart."""
    def decorate(function):
        @wraps(function)
        def tracked(self, run_id, *args, **kwargs):
            sessions = getattr(self.repository, 'sessions', None)
            with usage_scope(**{identifier: run_id}, purpose=purpose,
                             ledger=UsageLedger(sessions) if sessions is not None else None):
                return function(self, run_id, *args, **kwargs)
        return tracked
    return decorate


def token_counts(usage):
    """Normalize LangChain and OpenAI/TypeSafe counters; absent is not zero."""
    usage = usage if isinstance(usage, dict) else {}
    result = {}
    for name, alias in (('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens')):
        value = usage.get(name, usage.get(alias))
        if type(value) is int and value >= 0:
            result[name] = value
    for name, paths in {
        'cached_input_tokens': [('input_token_details', 'cache_read'), ('prompt_tokens_details', 'cached_tokens')],
        'reasoning_tokens': [('output_token_details', 'reasoning'), ('completion_tokens_details', 'reasoning_tokens')],
    }.items():
        for parent, child in paths:
            nested = usage.get(parent)
            value = nested.get(child) if isinstance(nested, dict) else None
            if type(value) is int and value >= 0:
                result[name] = value
                break
    return result


class UsageLedger:
    def __init__(self, sessions):
        self.sessions = sessions

    def start(self, call_id, scope, details, *, limits=None):
        with self.sessions.begin() as db:
            if limits and scope.get('task_id'):
                # Serialize reservations across workers AND restarted processes.
                # Production task stores use SQLite; pending rows reserve capacity.
                if db.bind.dialect.name != 'sqlite':
                    raise TaskProviderBudgetExceeded('unsupported_budget_store')
                db.connection().exec_driver_sql('BEGIN IMMEDIATE')
                rows = [json.loads(r.details_json) for r in db.scalars(select(ProviderUsageRow)
                    .where(ProviderUsageRow.task_id == scope['task_id']))]
                total = summarize(rows)
                if 'provider_attempts' in limits and total['calls'] + 1 > limits['provider_attempts']:
                    raise TaskProviderBudgetExceeded('provider_attempts')
                if 'input_tokens' in limits:
                    reserve = details.get('reserved_input_tokens')
                    unknown = any(r.get('source') != 'tool_action' and 'input_tokens' not in r
                                  and r.get('reserved_input_tokens') is None for r in rows)
                    if unknown or reserve is None or total['budget_input_tokens'] + reserve > limits['input_tokens']:
                        raise TaskProviderBudgetExceeded('input_tokens')
            discarded = scope.get('request_discarded')
            db.add(ProviderUsageRow(call_id=call_id, task_id=scope.get('task_id'),
                run_id=scope.get('run_id'), request_id=scope.get('request_id'), adopted=not (discarded and discarded.is_set()),
                created_at=datetime.now(UTC).isoformat(), details_json=json.dumps(details)))

    def finish(self, call_id, details):
        # Do not overwrite the independently updated adoption flag on a late response.
        with self.sessions.begin() as db:
            db.execute(update(ProviderUsageRow).where(ProviderUsageRow.call_id == call_id)
                .values(details_json=json.dumps(details)))

    def discard(self, request_id):
        with self.sessions.begin() as db:
            db.execute(update(ProviderUsageRow).where(ProviderUsageRow.request_id == request_id).values(adopted=False))

    def summary(self, *, task_id=None, run_ids=()):
        conditions = []
        if task_id: conditions.append(ProviderUsageRow.task_id == task_id)
        if run_ids: conditions.append(ProviderUsageRow.run_id.in_(run_ids))
        if not conditions:
            return summarize([])
        with self.sessions() as db:
            rows = db.scalars(select(ProviderUsageRow).where(or_(*conditions)))
            return summarize([{**json.loads(row.details_json), 'adopted': row.adopted} for row in rows])


def summarize(rows):
    result = {'calls': 0, 'completed': 0, 'failed': 0, 'pending': 0, 'discarded': 0, 'retries': 0,
              'input_tokens': 0, 'output_tokens': 0, 'unknown_usage_calls': 0, 'groups': [],
              'budget_input_tokens': 0}
    groups = {}
    for row in rows:
        if row.get('source') == 'tool_action':
            continue
        result['calls'] += 1
        result['budget_input_tokens'] += row.get('input_tokens', row.get('reserved_input_tokens', 0))
        result[row.get('status', 'pending')] += 1
        result['discarded'] += int(not row.get('adopted', True))
        result['retries'] += int(row.get('attempt', 1) > 1)
        known = all(key in row for key in ('input_tokens', 'output_tokens'))
        result['unknown_usage_calls'] += int(not known)
        key = (row.get('purpose', 'unspecified'), row.get('model', 'unknown'))
        group = groups.setdefault(key, {'purpose': key[0], 'model': key[1], 'calls': 0,
            'input_tokens': 0, 'output_tokens': 0, 'unknown_usage_calls': 0})
        group['calls'] += 1
        group['unknown_usage_calls'] += int(not known)
        for metric in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens'):
            if metric in row:
                result[metric] = result.get(metric, 0) + row[metric]
                group[metric] = group.get(metric, 0) + row[metric]
    result['groups'] = list(groups.values())
    for target in [result, *result['groups']]:
        target['cache_hit_ratio'] = (target['cached_input_tokens'] / target['input_tokens']
            if target.get('input_tokens') and 'cached_input_tokens' in target else None)
        target['reasoning_share'] = (target['reasoning_tokens'] / target['output_tokens']
            if target.get('output_tokens') and 'reasoning_tokens' in target else None)
    result['usage_complete'] = result['calls'] > 0 and result['unknown_usage_calls'] == 0
    result['provider_attempts'] = result['calls']
    return result


@contextmanager
def provider_call(model, **sizes):
    scope = current_scope()
    guard=scope.get('provider_guard')
    if guard:guard()  # Includes nested worker requests copied from a task batch.
    ledger = scope.get('ledger')
    limits = task_limits() if scope.get('task_id') else {}
    started = time.monotonic()
    call_id = str(uuid4())
    details = {'call_id': call_id, 'model': str(model), 'purpose': scope.get('purpose', 'unspecified'),
               'model_route': scope.get('model_route', 'main'), 'source': 'provider',
               'attempt': scope.get('attempt', 1),
               'status': 'pending', **{k: v for k, v in sizes.items() if k in
                {'context_chars', 'tool_schema_chars', 'image_count'}}}
    for key in ('context_metrics', 'queue_wait_seconds', 'reasoning_escalation', 'reasoning_fallback', 'effective_reasoning'):
        if key in scope:
            details[key] = scope[key]
    if limits:
        if ledger is None:
            raise TaskProviderBudgetExceeded('missing_usage_ledger')
        if 'input_tokens' in limits:
            details['reserved_input_tokens'] = sizes.get('input_token_reservation')
            if details['reserved_input_tokens'] is None:
                raise TaskProviderBudgetExceeded('unknown_input_size')
    persistence = 0.0
    def persist(method):
        nonlocal persistence
        if ledger is not None:
            before = time.monotonic()
            try:
                if method == 'start': ledger.start(call_id, scope, details, **({'limits': limits} if limits else {}))
                else: ledger.finish(call_id, details)
            except Exception as exc:
                if limits:
                    raise TaskProviderBudgetExceeded('usage_persistence_failed') from exc
                # Telemetry failure must not repeat a paid request or a browser action.
                log.warning('Provider usage persistence failed: %s', type(exc).__name__)
            finally:
                persistence += time.monotonic() - before
    persist('start')
    _observe(details)
    provider_started = time.monotonic()
    try:
        yield details
        if details['status'] == 'pending': details['status'] = 'completed'
    except BaseException as exc:
        details.update(status='failed', error_type=type(exc).__name__)
        raise
    finally:
        details['provider_duration_seconds'] = time.monotonic() - provider_started
        # Start-write duration is known before the final row write. The final
        # write cannot measure its own commit; keep this boundary explicit.
        details['persistence_seconds'] = persistence
        details['persistence_boundary'] = 'attempt_start_write'
        details['duration_seconds'] = round(time.monotonic() - started, 3)
        persist('finish')
        if ledger is not None:
            details['persistence_seconds'] = persistence
            details['persistence_boundary'] = 'start_and_finish_writes_excluding_timing_update'
            try:
                ledger.finish(call_id, details)
            except Exception as exc:
                log.warning('Provider timing update failed: %s', type(exc).__name__)
        discarded = scope.get('request_discarded')
        if ledger is not None and discarded and discarded.is_set():
            try: ledger.discard(scope['request_id'])
            except Exception as exc: log.warning('Late usage discard failed: %s', type(exc).__name__)


def record_chat_usage(details, result):
    generations = getattr(result, 'generations', [])
    message = generations[0].message if generations else None
    usage = getattr(message, 'usage_metadata', None) or (getattr(result, 'llm_output', None) or {}).get('token_usage')
    details.update(token_counts(usage))


def record_tool_action(details):
    """Durable action timings in the same store, excluded from provider counts."""
    scope = current_scope()
    ledger = scope.get('ledger')
    if ledger is None:
        return
    row = {'source': 'tool_action', 'status': 'completed', **details}
    try:
        ledger.start(str(uuid4()), scope, row)
    except Exception as exc:
        log.warning('Tool timing persistence failed: %s', type(exc).__name__)
