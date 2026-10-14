"""Small transport adapter; credentials come only from this workspace's .env."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from langchain_core.messages import AIMessage
from eregion.runtime.provider_usage import provider_call, token_counts, input_reservation

ROOT = Path(__file__).resolve().parents[2]


def load_config(root=ROOT):
    values = dotenv_values(Path(root) / ".env", interpolate=False)
    if not all(values.get(key) for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL_ID")):
        raise ValueError("Fill LLM_BASE_URL, LLM_API_KEY and LLM_MODEL_ID in the project .env")
    url = values["LLM_BASE_URL"].rstrip("/")
    parsed = urlsplit(url)
    if (parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or (parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})):
        raise ValueError("Invalid model endpoint; use HTTPS or local HTTP")
    values["endpoint"] = url if url.endswith("/chat/completions") else url + "/chat/completions"
    token_field = values.get("LLM_TOKEN_LIMIT_FIELD") or "max_tokens"
    if token_field not in {"max_tokens", "max_completion_tokens"}:
        raise ValueError("Invalid token limit field")
    values["token_field"] = token_field
    values["timeout"] = float(values.get("LLM_TIMEOUT") or 180)
    values["max_tokens"] = int(values.get("LLM_MAX_OUTPUT_TOKENS") or 6000)
    if not 5 <= values["timeout"] <= 180 or not 256 <= values["max_tokens"] <= 8000:
        raise ValueError("Model limits out of range")
    return values


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
        self.client = httpx.Client(timeout=self.request_timeout, follow_redirects=False, transport=transport)

    def invoke(self, messages, tools):
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
                                    headers={"Authorization": "Bearer " + config["LLM_API_KEY"],
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
