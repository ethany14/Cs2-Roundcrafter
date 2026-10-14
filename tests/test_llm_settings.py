"""In-app model settings and the Anthropic SDK path. No network: every call goes through a mock transport."""
import json

import httpx
import httpx2
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from cs2_agent import llm_settings as ls
from cs2_agent.provider import ConfiguredModel, anthropic_messages, load_config
from cs2_agent.host import WorkspaceHost
from cs2_agent.tools import foundation_tools

SECRET = "sk-test-only-0000-abcd"


def test_saved_key_is_never_returned_and_overrides_env(tmp_path):
    (tmp_path / ".env").write_text("LLM_BASE_URL=https://env.example/v1\nLLM_MODEL_ID=env-model\nLLM_API_KEY=env-key\n")
    assert load_config(tmp_path)["source"] == "env"
    state = ls.save(tmp_path, {"provider": "deepseek", "model": "deepseek-chat", "api_key": SECRET})
    assert SECRET not in json.dumps(state)
    assert state["saved"]["has_key"] and state["saved"]["key_hint"] == "…abcd"
    assert state["active"] == {"source": "app", "provider": "deepseek", "model": "deepseek-chat", "host": "api.deepseek.com"}
    config = load_config(tmp_path)
    assert config["LLM_API_KEY"] == SECRET and config["endpoint"] == "https://api.deepseek.com/chat/completions"
    # A blank key on the same provider keeps the saved one.
    ls.save(tmp_path, {"provider": "deepseek", "model": "deepseek-reasoner", "api_key": ""})
    assert load_config(tmp_path)["LLM_API_KEY"] == SECRET
    assert ls.clear(tmp_path)["active"]["source"] == "env"


def test_validation(tmp_path):
    with pytest.raises(ValueError):
        ls.save(tmp_path, {"provider": "openai", "model": "gpt-5", "api_key": ""})
    with pytest.raises(ValueError):
        ls.save(tmp_path, {"provider": "custom", "base_url": "http://remote.example/v1", "model": "m", "api_key": "k"})
    with pytest.raises(ValueError):
        ls.save(tmp_path, {"provider": "nope", "model": "m", "api_key": "k"})
    with pytest.raises(ValueError):
        ls.save(tmp_path, {"provider": "openai", "model": "bad model id", "api_key": "k"})
    # Local services need no key; OpenAI uses max_completion_tokens.
    ls.save(tmp_path, {"provider": "ollama", "model": "qwen3"})
    assert load_config(tmp_path)["LLM_API_KEY"] == ""
    ls.save(tmp_path, {"provider": "openai", "model": "gpt-5", "api_key": "k"})
    assert load_config(tmp_path)["token_field"] == "max_completion_tokens"
    assert load_config(tmp_path)["protocol"] == "openai"


def test_model_list_from_openai_compatible_provider(tmp_path):
    def respond(request):
        assert request.url.path == "/v1/models" and request.headers["authorization"] == "Bearer " + SECRET
        return httpx.Response(200, json={"data": [{"id": "b-model"}, {"id": "a-model"}]})
    r = ls.models(tmp_path, {"provider": "openai", "model": "gpt-5", "api_key": SECRET}, transport=httpx.MockTransport(respond))
    assert r == {"models": ["a-model", "b-model"]}


def test_message_conversion_keeps_tool_pairs():
    system, turns = anthropic_messages([
        SystemMessage(content="rules"),
        HumanMessage(content="hi"),
        AIMessage(content="", tool_calls=[{"id": "t1", "name": "look", "args": {"a": 1}},
                                          {"id": "t2", "name": "look", "args": {}}]),
        ToolMessage(content='{"ok":true}', tool_call_id="t1"),
        HumanMessage(content="observation"),
    ])
    assert system == "rules"
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    after = turns[2]["content"]
    assert [b["type"] for b in after] == ["tool_result", "tool_result", "text"]
    assert {b["tool_use_id"] for b in after[:2]} == {"t1", "t2"}


def anthropic_config(model="claude-opus-5-5", base="https://api.anthropic.com"):
    return {"protocol": "anthropic", "LLM_BASE_URL": base, "LLM_API_KEY": SECRET, "LLM_MODEL_ID": model,
            "endpoint": base + "/v1/messages", "timeout": 5, "max_tokens": 1024, "token_field": "max_tokens",
            "LLM_AGENT_REASONING": "low"}


def test_anthropic_sdk_request_shape_and_tool_calls():
    seen = []
    def respond(request):
        body = json.loads(request.content)
        seen.append((request, body))
        return httpx2.Response(200, json={"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "tool_use", "id": "toolu_1", "name": "report_status", "input": {"status": "ok"}}],
            "stop_reason": "tool_use", "stop_sequence": None, "usage": {"input_tokens": 12, "output_tokens": 7}})
    tool = {"type": "function", "function": {"name": "report_status", "description": "d",
            "parameters": {"type": "object", "properties": {"status": {"type": "string"}}}}}
    model = ConfiguredModel(anthropic_config(), transport=httpx2.MockTransport(respond))
    try:
        reply = model.invoke([SystemMessage(content="sys"), HumanMessage(content="go")], [tool])
    finally:
        model.close()
    request, body = seen[0]
    assert request.url.path == "/v1/messages" and request.headers["x-api-key"] == SECRET
    assert SECRET not in request.content.decode()
    assert body["system"] == "sys" and body["tools"][0]["input_schema"]["properties"]["status"]
    assert body["output_config"] == {"effort": "low"} and body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in request.headers["anthropic-beta"]
    assert reply.tool_calls == [{"id": "toolu_1", "name": "report_status", "args": {"status": "ok"}, "type": "tool_call"}]
    assert reply.response_metadata["finish_reason"] == "tool_calls"


def test_anthropic_without_fallback_off_the_official_host_and_truncation_flagged():
    seen = []
    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx2.Response(200, json={"id": "m", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": "partial"}], "stop_reason": "max_tokens", "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1}})
    model = ConfiguredModel(anthropic_config(model="claude-haiku-5-5", base="https://gateway.example"),
                            transport=httpx2.MockTransport(respond))
    try:
        reply = model.invoke([HumanMessage(content="go")], [])
    finally:
        model.close()
    assert "fallbacks" not in seen[0] and "tools" not in seen[0]
    assert reply.response_metadata["finish_reason"] == "length"


def scripted(calls, final_after=3):
    """Mock Messages API: each reply has a thinking block (with a signature) and one tool call."""
    def respond(request):
        body = json.loads(request.content)
        calls.append((request, body))
        n = len(calls)
        name = "inspect_capabilities" if n < final_after else "finish_task"
        return httpx2.Response(200, json={"id": f"m{n}", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "thinking", "thinking": "", "signature": f"sig-{n}"},
                        {"type": "tool_use", "id": f"toolu_{n}", "name": name,
                         "input": {} if name == "inspect_capabilities" else {"text": "done"}}],
            "stop_reason": "tool_use", "stop_sequence": None, "usage": {"input_tokens": 100, "output_tokens": 20}})
    return httpx2.MockTransport(respond)


def test_anthropic_agent_loop_history_is_append_only_with_thinking(tmp_path):
    calls = []
    model = ConfiguredModel(anthropic_config(), transport=scripted(calls))
    host = WorkspaceHost(tmp_path, model, foundation_tools(), request="check")
    try:
        assert host.run()["reason"] == "completed"
        assert len(calls) == 3
        for i in (1, 2):
            before, after = calls[i - 1][1], calls[i][1]
            # Each request is the previous one, plus the reply verbatim, plus one new user turn.
            assert after["messages"][:len(before["messages"])] == before["messages"]
            reply = after["messages"][len(before["messages"])]
            assert reply == {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "", "signature": f"sig-{i}"},
                {"type": "tool_use", "id": f"toolu_{i}", "name": "inspect_capabilities", "input": {}}]}
            assert after["system"] == before["system"] and after["tools"] == before["tools"]
            new = after["messages"][-1]["content"]
            assert new[0] == {"type": "tool_result", "tool_use_id": f"toolu_{i}", "content": new[0]["content"]}
        request, body = calls[2]
        assert body["thinking"] == {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
        assert body["cache_control"] == {"type": "ephemeral"}
        assert {"thinking-binding-controls-2026-08-01", "server-side-fallback-2026-07-01"} <= set(request.headers["anthropic-beta"].split(","))
        assert SECRET not in host.path.read_text(encoding="utf-8")
    finally:
        host.close()
        model.close()


def turn(snapshot, *exchanges):
    """LangChain messages the way the agent loop rebuilds them."""
    out = [SystemMessage(content="rules")]
    if exchanges:
        out.append(HumanMessage(content="historical request"))
    for call_id in exchanges:
        out += [AIMessage(content="", tool_calls=[{"id": call_id, "name": "inspect_capabilities", "args": {}}]),
                ToolMessage(content='{"ok":1}', tool_call_id=call_id)]
    return out + [HumanMessage(content=snapshot)]


def test_discarded_reply_continues_from_the_turn_before():
    calls = []
    model = ConfiguredModel(anthropic_config(), transport=scripted(calls, final_after=9))
    try:
        model.invoke(turn("obs 1"), [])
        model.invoke(turn("obs 2", "toolu_1"), [])
        # The loop rejected reply 2 (say, truncated) and asks again with the same history.
        reply = model.invoke(turn("obs 3 with repair note", "toolu_1"), [])
    finally:
        model.close()
    messages = calls[2][1]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig-1"}
    assert messages[2]["content"][-1]["text"] == "obs 3 with repair note"
    assert reply.response_metadata["history_restarts"] == 0


def test_changed_system_prompt_restarts_without_thinking():
    calls = []
    model = ConfiguredModel(anthropic_config(), transport=scripted(calls, final_after=9))
    try:
        model.invoke(turn("obs 1"), [])
        changed = turn("obs 2", "toolu_1")
        changed[0] = SystemMessage(content="different rules")
        reply = model.invoke(changed, [])
    finally:
        model.close()
    messages = calls[1][1]["messages"]
    assert not any(b["type"] == "thinking" for m in messages for b in m["content"])
    assert reply.response_metadata["history_restarts"] == 1
