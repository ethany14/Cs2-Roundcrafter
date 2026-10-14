"""The contract between the shared AgentLoop (core.engine) and a domain Host.

AgentLoop owns the decision cycle: observe -> one model request -> validate ->
execute -> persist. A Host supplies the domain: what to observe, how to invoke
the model, how to run a tool and how to persist the loop journal. Every
autonomous loop (career tasks, applications and sessions)
plugs in through this interface; fixed workflows do not use it.
"""
from typing import Any, Protocol, runtime_checkable

# Called by core.engine.AgentLoop on every Host.
REQUIRED = ('active', 'revision', 'observe', 'invoke', 'progress', 'on_text',
            'execute', 'action_error', 'after_action', 'persist')
# Used when present: fence text completion, validate a batch before any effect,
# turn a tool screenshot into model input, replace the default output check
# (model_output.output_problem) or per-call schema validation (validate_call).
OPTIONAL = ('text_guard', 'validate_batch', 'image_message', 'output_problem', 'validate')
# Attribute the engine assigns its ContextArchive to when the Host declares it.
ATTRIBUTES = ('context_archive',)


@runtime_checkable
class Host(Protocol):
    def active(self) -> bool:
        """False once the owner cancelled, paused or finished; no stale result is accepted."""

    def revision(self) -> int:
        """Current user-steering revision; a decision made for an older one is discarded."""

    def observe(self) -> Any:
        """Build the next Turn (prompt, snapshot, tools, revision); may raise LoopStop."""

    def invoke(self, messages: list, tools: list, turn: Any) -> Any:
        """Exactly one accounted model request; None when interrupted."""

    def progress(self, text: str, call: dict, turn: Any) -> None:
        """Publish text accompanying the first action; raise LoopStop if steered."""

    def on_text(self, text: str, turn: Any) -> dict | None:
        """Handle a reply with no tool call: a stop result, a notice, or None."""

    def execute(self, call: dict, turn: Any) -> Any:
        """Run one validated domain action and return its observed outcome."""

    def action_error(self, exc: Exception) -> dict:
        """Convert an action failure into a safe tool result."""

    def after_action(self, call: dict, outcome: dict, turn: Any) -> dict | None:
        """Record the outcome; a returned dict stops the slice with that result."""

    def persist(self, runtime: dict) -> None:
        """Durably save the loop journal (context, inflight action, events)."""


def missing_methods(host: Any) -> list[str]:
    """Required Host methods that the object does not provide as callables."""
    return [name for name in REQUIRED if not callable(getattr(host, name, None))]
