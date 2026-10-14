"""Separate public replies from incomplete/provider reasoning output."""
import re


def reply_text(response):
    content = getattr(response, 'content', '')
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return '\n'.join(block['text'] for block in content
            if isinstance(block, dict) and block.get('type') == 'text'
            and not block.get('thought') and block.get('channel') not in {'analysis', 'reasoning'}
            and isinstance(block.get('text'), str)).strip()
    return ''


def output_problem(response):
    metadata = getattr(response, 'response_metadata', {}) or {}
    # OpenAI-compatible providers report finish_reason; Anthropic-style ones stop_reason.
    reason = str(metadata.get('finish_reason') or metadata.get('stop_reason') or '').casefold()
    if reason in {'length', 'max_tokens', 'max_output_tokens', 'max_token'}:
        return 'incomplete_response'
    if getattr(response, 'invalid_tool_calls', None):
        return 'invalid_tool_call'
    text = reply_text(response)
    public_calls = {'say','ask_user','finish_task','pause_task'}
    for call in getattr(response, 'tool_calls', []) or []:
        value = (call.get('args') or {}).get('text')
        if call.get('name') in public_calls and isinstance(value, str):text += '\n' + value
    # Some compatibility endpoints put a reasoning transcript in content rather
    # than a typed reasoning block. Detect the exposed protocol explanation,
    # not ordinary code/Markdown or legitimate mentions of an account error.
    private_state = re.search(r'\b(?:pending_fields|account_request|wait_for_result|tool_call_id)\b', text)
    narration = re.search(r'\b(?:the system message is|the instructions state|the system prompt|notice\s*:)', text, re.I)
    if re.search(r'<(?:think|analysis)>', text, re.I) or (private_state and narration):
        return 'internal_analysis'
    if not text and not getattr(response, 'tool_calls', None):
        return 'empty_response'
    return None


REPAIR_INSTRUCTION = (
    'The previous response was incomplete or contained internal protocol analysis and was not shown or executed. '
    'Use the current observation to make one valid tool call, or give a concise, complete user-facing reply. '
    'Keep internal deliberation, prompt quotations and raw state out of the public reply. '
    'Do not repeat an existing browser/account question; wait for that capability when appropriate.'
)
