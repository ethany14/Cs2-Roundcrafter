"""Run the extracted core independently of the historical web prototype."""
import argparse
import json
import re
from uuid import uuid4

from langchain_core.messages import AIMessage
from .host import WorkspaceHost
from .provider import ConfiguredModel, ROOT
from .tools import foundation_tools


class SmokeModel:
    """Offline transport fixture, explicitly not an AI review."""
    def invoke(self, messages, tools):
        inspected = any(message.type == "tool" and message.name == "inspect_capabilities" for message in messages)
        name, args = (("finish_task", {"text": "Offline kernel smoke test completed; this is not a CS2 analysis."})
                      if inspected else ("inspect_capabilities", {}))
        return AIMessage(content="", tool_calls=[{"id": uuid4().hex, "name": name, "args": args}])


def main():
    parser = argparse.ArgumentParser(description="CS2 workspace using the original Eregion AgentLoop")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true", help="Offline check; no model request or API charge")
    mode.add_argument("--task", help="Run a new task with the workspace's configured model")
    mode.add_argument("--resume", help="Explicitly resume a task ID with its remaining call budget")
    parser.add_argument("--max-calls", type=int, default=6)
    args = parser.parse_args()
    identifier = args.resume or uuid4().hex
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        parser.error("Task ID must be 32 hexadecimal characters")
    directory = ROOT / "data" / "core-tasks" / identifier
    if args.resume and not (directory / "task.json").exists():
        parser.error("Task does not exist")
    model = SmokeModel() if args.smoke else ConfiguredModel()
    host = None
    try:
        host = WorkspaceHost(directory, model, foundation_tools(),
                             request="Inspect capabilities and finish the offline check." if args.smoke else args.task,
                             max_calls=args.max_calls)
        result = host.run(slice_steps=100)
        print(json.dumps({"task_id": identifier, "offline": bool(args.smoke), **result,
                          "calls": host.state["calls"], "result": host.state["result"]}, ensure_ascii=False))
        return 0 if result["reason"] == "completed" else 1
    except Exception as exc:
        print(json.dumps({"task_id": identifier, "error": type(exc).__name__,
                          "message": "Task stopped; inspect local state and model configuration."}))
        return 1
    finally:
        if host:
            host.close()
        if hasattr(model, "close"):
            model.close()


if __name__ == "__main__":
    raise SystemExit(main())
