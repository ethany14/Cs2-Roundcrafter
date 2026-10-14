"""Small transport adapter. Credentials come from the in-app model settings (data/account/llm.json,
see llm_settings.py) or, when none are saved, from this workspace's .env."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from langchain_core.messages import AIMessage
from eregion.runtime.provider_usage import provider_call, token_counts, input_reservation

ROOT = Path(__file__).resolve().parents[2]


def _limits(values, env):
    token_field = values.get("LLM_TOKEN_LIMIT_FIELD") or "max_tokens"
    if token_field not in {"max_tokens", "max_completion_tokens"}:
        raise ValueError("Invalid token limit field")
    values["token_field"] = token_field
    values["timeout"] = float(env.get("LLM_TIMEOUT") or 180)
    values["max_tokens"] = int(env.get("LLM_MAX_OUTPUT_TOKENS") or 6000)
    if not 5 <= values["timeout"] <= 180 or not 256 <= values["max_tokens"] <= 8000:
        raise ValueError("Model limits out of range")
    return values


def config_from_settings(saved, root=ROOT):
    """Config from settings saved in the web UI; .env only contributes timeout and output limits."""
    from .llm_settings import check_url
    env = dotenv_values(Path(root) / ".env", interpolate=False)
    url = check_url(saved["base_url"])
    values = {"LLM_BASE_URL": url, "LLM_API_KEY": saved.get("api_key", ""), "LLM_MODEL_ID": saved["model"],
              "LLM_TOKEN_LIMIT_FIELD": saved.get("token_field") or "max_tokens",
              "LLM_AGENT_REASONING": saved.get("effort") or "", "protocol": saved.get("protocol", "openai"),
              "provider": saved.get("provider"), "source": "app"}
    if values["protocol"] == "anthropic":
        values["endpoint"] = url + "/v1/messages"
    else:
        values["endpoint"] = url if url.endswith("/chat/completions") else url + "/chat/completions"
    return _limits(values, env)


def load_config(root=ROOT):
    from .llm_settings import load
    saved = load(root)
    if saved:
        return config_from_settings(saved, root)
    values = dotenv_values(Path(root) / ".env", interpolate=False)
    if not all(values.get(key) for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL_ID")):
        raise ValueError("尚未配置模型：请在应用中打开“模型设置”，或在项目 .env 中填写 LLM_BASE_URL、LLM_API_KEY 和 LLM_MODEL_ID")
    url = values["LLM_BASE_URL"].rstrip("/")
    parsed = urlsplit(url)
    if (parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or (parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})):
        raise ValueError("Invalid model endpoint; use HTTPS or local HTTP")
    values["endpoint"] = url if url.endswith("/chat/completions") else url + "/chat/completions"
    values["protocol"], values["source"] = "openai", "env"
    return _limits(values, values)


def wire_messages(messages):
    result = []
    for message in messages:
        row = {"role": {"system": "system", "human": "user", "ai": "assistant", "tool": "tool"}[message.type],
               "content": message.content}
        if message.type == "tool":
            row["tool_call_id"] = message.tool_call_id
        if message.type == "ai" and message.tool_calls:
            row["tool_calls"] = [{"id": call["id"], "type": "function", "function": {
                "name": call["name"], "arguments": json.dumps(call["args"], ensure_ascii=False)}} for call in message.tool_calls]
        result.append(row)
    return result


class ConfiguredModel:
    def __init__(self, config=None, *, transport=None):
        self.config = load_config() if config is None else config
        self.request_timeout = self.config["timeout"]
        self.native = self.config.get("protocol") == "anthropic"
        if self.native:
            self.client = anthropic_client(self.config, timeout=self.request_timeout, transport=transport)
        else:
            self.client = httpx.Client(timeout=self.request_timeout, follow_redirects=False, transport=transport)

    def invoke(self, messages, tools):
        if self.native:
            return invoke_anthropic(self.client, self.config, messages, tools)
        config = self.config
        payload = {"model": config["LLM_MODEL_ID"], "messages": wire_messages(messages),
                   "stream": False,
                   config["token_field"]: config["max_tokens"]}
        if tools:
            payload.update(tools=tools, tool_choice="auto")
        if config.get("LLM_AGENT_REASONING"):
            payload["reasoning_effort"] = config["LLM_AGENT_REASONING"]
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(encoded) > 200_000:
            raise ValueError("Model request exceeds local size limit")
        with provider_call(config["LLM_MODEL_ID"], input_token_reservation=input_reservation(payload)) as details:
            with self.client.stream("POST", config["endpoint"], content=encoded,
                                    headers={**({"Authorization": "Bearer " + config["LLM_API_KEY"]} if config["LLM_API_KEY"] else {}),
                                             "Content-Type": "application/json"}) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"Model service returned HTTP {response.status_code}")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        raise ValueError("Model response exceeds local size limit")
            data = json.loads(body)
            details.update(token_counts(data.get("usage")))
            choice = data["choices"][0]
            message = choice["message"]
            calls, ids = [], set()
            for call in message.get("tool_calls") or []:
                if call["id"] in ids:
                    raise ValueError("Duplicate tool call ID")
                ids.add(call["id"])
                calls.append({"id": call["id"], "name": call["function"]["name"],
                              "args": json.loads(call["function"]["arguments"])})
            return AIMessage(content=message.get("content") or "", tool_calls=calls,
                             response_metadata={"finish_reason": choice.get("finish_reason")})

    def close(self):
        self.client.close()


# ---------------------------------------------------------------- Anthropic (official SDK)
# Claude models that accept server-side refusal fallbacks in the "default" form on the Claude API.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
STOP_REASONS = {"end_turn": "stop", "tool_use": "tool_calls", "max_tokens": "length", "stop_sequence": "stop",
                "refusal": "refusal", "pause_turn": "stop"}


def anthropic_client(config, *, timeout, transport=None):
    import anthropic
    http_client = None
    if transport is not None:
        http_client = anthropic.DefaultHttpxClient(transport=transport)
    return anthropic.Anthropic(api_key=config["LLM_API_KEY"], base_url=config["LLM_BASE_URL"],
                               timeout=timeout, max_retries=2, http_client=http_client)


def _image_block(part):
    url = (part.get("image_url") or {}).get("url", "") if isinstance(part.get("image_url"), dict) else str(part.get("image_url") or "")
    if url.startswith("data:") and ";base64," in url:
        media, data = url[5:].split(";base64,", 1)
        return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}
    return {"type": "image", "source": {"type": "url", "url": url}}


def _content_blocks(content):
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    blocks = []
    for part in content or []:
        if isinstance(part, str):
            blocks.append({"type": "text", "text": part})
        elif part.get("type") == "text" and part.get("text"):
            blocks.append({"type": "text", "text": part["text"]})
        elif part.get("type") == "image_url":
            blocks.append(_image_block(part))
    return blocks


def anthropic_messages(messages):
    """LangChain messages -> (system, Messages API turns).

    The agent loop rebuilds its history on every call, so earlier turns are not byte-identical
    between requests. Thinking blocks are therefore never replayed: each turn's text and tool_use
    blocks are kept, which is the documented strip-thinking form and avoids prefix-binding errors.
    """
    system, turns = [], []

    def add(role, blocks):
        if not blocks:
            return
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": role, "content": list(blocks)})

    for message in messages:
        if message.type == "system":
            system.extend(b["text"] for b in _content_blocks(message.content) if b["type"] == "text")
        elif message.type == "human":
            add("user", _content_blocks(message.content))
        elif message.type == "tool":
            add("user", [{"type": "tool_result", "tool_use_id": message.tool_call_id, "content": str(message.content)}])
        elif message.type == "ai":
            blocks = [b for b in _content_blocks(message.content) if b["type"] == "text"]
            blocks += [{"type": "tool_use", "id": call["id"], "name": call["name"], "input": call["args"]}
                       for call in message.tool_calls or []]
            add("assistant", blocks or [{"type": "text", "text": "(no reply)"}])
    # Every tool_use needs a tool_result at the start of the next user turn.
    for i, turn in enumerate(turns):
        if turn["role"] != "assistant":
            continue
        pending = [b["id"] for b in turn["content"] if b["type"] == "tool_use"]
        if not pending:
            continue
        if i + 1 == len(turns) or turns[i + 1]["role"] != "user":
            turns.insert(i + 1, {"role": "user", "content": []})
        answered = {b.get("tool_use_id") for b in turns[i + 1]["content"]}
        turns[i + 1]["content"] += [{"type": "tool_result", "tool_use_id": x, "content": "(result not retained)"}
                                    for x in pending if x not in answered]
    for turn in turns:
        if turn["role"] == "user":
            turn["content"].sort(key=lambda block: block["type"] != "tool_result")
    if not turns or turns[0]["role"] != "user":
        turns.insert(0, {"role": "user", "content": [{"type": "text", "text": "Begin."}]})
    return "\n\n".join(system), turns


def anthropic_tools(tools):
    return [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
             "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}}
            for t in tools or []]


def invoke_anthropic(client, config, messages, tools):
    system, turns = anthropic_messages(messages)
    params = {"model": config["LLM_MODEL_ID"], "max_tokens": config["max_tokens"], "messages": turns}
    if system:
        params["system"] = system
    if tools:
        params["tools"] = anthropic_tools(tools)
        params["tool_choice"] = {"type": "auto"}
    if config.get("LLM_AGENT_REASONING"):
        params["output_config"] = {"effort": config["LLM_AGENT_REASONING"]}
    if len(json.dumps(params, ensure_ascii=False).encode("utf-8")) > 200_000:
        raise ValueError("Model request exceeds local size limit")
    official = urlsplit(config["LLM_BASE_URL"]).hostname == "api.anthropic.com"
    with provider_call(config["LLM_MODEL_ID"], input_token_reservation=input_reservation(params)) as details:
        if official and config["LLM_MODEL_ID"] in FALLBACK_MODELS:
            # A safety-classifier decline is re-run server-side on Anthropic's recommended model.
            response = client.beta.messages.create(**params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        else:
            response = client.messages.create(**params)
        usage = response.usage
        details.update(token_counts({"input_tokens": (usage.input_tokens or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0)
                                     + (getattr(usage, "cache_creation_input_tokens", 0) or 0),
                                     "output_tokens": usage.output_tokens}))
    if response.stop_reason == "refusal":
        raise RuntimeError("模型拒绝了这个请求（refusal）")
    text = "\n".join(b.text for b in response.content if b.type == "text").strip()
    calls, ids = [], set()
    for block in response.content:
        if block.type == "tool_use":
            if block.id in ids:
                raise ValueError("Duplicate tool call ID")
            ids.add(block.id)
            calls.append({"id": block.id, "name": block.name, "args": dict(block.input or {})})
    return AIMessage(content=text, tool_calls=calls,
                     response_metadata={"finish_reason": STOP_REASONS.get(response.stop_reason, response.stop_reason),
                                        "stop_reason": response.stop_reason})
