import hashlib
import json
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import AIMessage

from cs2_agent.__main__ import SmokeModel
from cs2_agent.host import WorkspaceHost
from cs2_agent.provider import ConfiguredModel, ROOT, load_config
from cs2_agent.tools import foundation_tools
from eregion.runtime.core.engine import AgentLoop
from eregion.runtime.core.host_protocol import missing_methods


def finish(text="done"):
    return AIMessage(content="", tool_calls=[{"id": "finish", "name": "finish_task", "args": {"text": text}}])


class Replies:
    def __init__(self, replies):
        self.replies = iter(replies)
    def invoke(self, messages, tools):
        return next(self.replies)


def test_original_kernel_hashes_match():
    manifest = json.loads((ROOT / "docs/core-migration.json").read_text(encoding="utf-8-sig"))
    for item in manifest["files"]:
        if "/core/" in item["path"]:
            actual = hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
            assert actual == item["sourceSha256"].lower()
    import inspect
    assert Path(inspect.getfile(AgentLoop)).resolve().is_relative_to(ROOT)


def test_offline_loop_reads_tool_then_explicitly_finishes(tmp_path):
    host = WorkspaceHost(tmp_path, SmokeModel(), foundation_tools(), request="check")
    try:
        assert missing_methods(host) == []
        assert host.run()["reason"] == "completed"
        assert host.state["calls"] == 2
        assert [g["assistant"]["tool_calls"][0]["name"] for g in host.state["runtime"]["transcript"]] == ["inspect_capabilities", "finish_task"]
        assert host.run()["reason"] == "completed"
        assert host.state["calls"] == 2
    finally:
        host.close()


def test_restart_restores_history_without_repeating_inspection(tmp_path):
    first = WorkspaceHost(tmp_path, SmokeModel(), foundation_tools(), request="check")
    try:
        assert first.run(slice_steps=1)["reason"] == "yielded"
    finally:
        first.close()
    second = WorkspaceHost(tmp_path, SmokeModel(), foundation_tools())
    try:
        assert second.run()["reason"] == "completed"
        assert second.state["calls"] == 2
    finally:
        second.close()


def test_restart_does_not_reset_call_budget(tmp_path):
    first = WorkspaceHost(tmp_path, Replies([AIMessage(content="I will do it")]), [], request="check", max_calls=1)
    try:
        assert first.run()["reason"] == "call_budget"
        assert first.state["result"] is None
    finally:
        first.close()
    second = WorkspaceHost(tmp_path, Replies([]), [], max_calls=99)
    try:
        assert second.run()["reason"] == "call_budget"
        assert second.state["max_calls"] == 1
    finally:
        second.close()


def test_unknown_tool_does_not_execute(tmp_path):
    model = Replies([AIMessage(content="", tool_calls=[{"id": "bad", "name": "delete_all", "args": {}}]), finish()])
    host = WorkspaceHost(tmp_path, model, [], request="check")
    try:
        assert host.run()["reason"] == "completed"
        first_result = host.state["runtime"]["transcript"][0]["results"][0]["value"]
        assert first_result["error"] == "ToolArgumentsError"
    finally:
        host.close()


def test_inflight_recovery_does_not_replay_tool(tmp_path):
    host = WorkspaceHost(tmp_path, Replies([finish()]), [], request="check")
    host.state["runtime"]["inflight"] = {"tool": "unsafe_write", "call_id": "old", "arguments": {}}
    try:
        assert host.run()["reason"] == "completed"
        assert any(e["kind"] == "action_interrupted" for e in host.state["runtime"]["events"])
    finally:
        host.close()


def test_config_does_not_inherit_keys_or_interpolate(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "outside-secret")
    (tmp_path / ".env").write_text("LLM_BASE_URL=https://model.example/v1\nLLM_MODEL_ID=test\n")
    with pytest.raises(ValueError):
        load_config(tmp_path)
    (tmp_path / ".env").write_text("LLM_BASE_URL=https://model.example/v1\nLLM_MODEL_ID=test\nLLM_API_KEY=local-value\n")
    assert load_config(tmp_path)["LLM_API_KEY"] == "local-value"


def test_provider_adapter_and_usage_ledger_without_network(tmp_path):
    requests = []
    def respond(request):
        payload = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer test-only-secret"
        assert "test-only-secret" not in request.content.decode()
        requests.append(payload)
        name = "inspect_capabilities" if len(requests) == 1 else "finish_task"
        return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {
            "content": None, "tool_calls": [{"id": str(len(requests)), "type": "function", "function": {
                "name": name, "arguments": json.dumps({} if name == "inspect_capabilities" else {"text": "done"})}}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20}})
    config = {"LLM_API_KEY": "test-only-secret", "LLM_MODEL_ID": "fixture", "endpoint": "https://model.example/v1/chat/completions",
              "timeout": 5, "max_tokens": 256, "token_field": "max_tokens"}
    model = ConfiguredModel(config, transport=httpx.MockTransport(respond))
    host = WorkspaceHost(tmp_path, model, foundation_tools(), request="check")
    try:
        assert host.run()["reason"] == "completed"
        usage = host.ledger.summary(task_id=tmp_path.name)
        assert usage["calls"] == 2 and usage["input_tokens"] == 200
        assert "test-only-secret" not in host.path.read_text(encoding="utf-8")
        assert any(m["role"] == "tool" for m in requests[1]["messages"])
    finally:
        host.close()
        model.close()
