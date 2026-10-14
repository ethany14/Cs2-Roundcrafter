"""AgentLoop never acts on a model result that arrives after cancel or steering."""
from langchain_core.messages import AIMessage

from eregion.runtime.core.engine import AgentLoop, Turn
from cs2_agent.tools import function

TOOL = function('write_item', 'Update an item.', {'value': {'type': 'string'}})


class Host:
    """Minimal contract Host; `during_invoke` simulates what happens while the model runs."""

    def __init__(self, during_invoke, replies):
        self.is_active, self.rev, self.executed, self.events = True, 0, [], []
        self.during_invoke, self.replies, self.invocations = during_invoke, list(replies), 0

    def active(self): return self.is_active
    def revision(self): return self.rev
    def observe(self): return Turn('system', {'current_request': {'message': {'role': 'user', 'text': 'go'}}},
                                   [TOOL], self.rev)
    def invoke(self, messages, tools, turn):
        self.invocations += 1
        if self.invocations == 1:
            self.during_invoke(self)
        return self.replies.pop(0)
    def progress(self, text, call, turn): pass
    def on_text(self, text, turn): return {'reason': 'completed'}
    def execute(self, call, turn):
        self.executed.append((call['args']['value'], turn.revision))
        return {'saved': call['args']['value']}
    def action_error(self, exc): return {'error': str(exc)}
    def after_action(self, call, outcome, turn): return None
    def persist(self, runtime): self.runtime = runtime


def write(value):
    return AIMessage(content='', tool_calls=[{'id': value, 'name': 'write_item', 'args': {'value': value}}])


def cancel(host): host.is_active = False


def steer(host): host.rev += 1


def test_result_after_cancel_is_not_executed():
    host = Host(cancel, [write('stale')])
    result = AgentLoop(host).run()
    assert result['reason'] == 'cancelled'
    assert host.executed == [] and host.invocations == 1


def test_result_for_an_older_revision_is_discarded_and_redecided():
    host = Host(steer, [write('stale'), write('fresh'), AIMessage(content='done')])
    AgentLoop(host).run()
    assert host.executed == [('fresh', 1)]
    kinds = [e['kind'] for e in host.runtime['events']]
    assert kinds.count('decision_discarded') == 1 and host.invocations == 3

