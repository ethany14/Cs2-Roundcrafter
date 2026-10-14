"""Model provider settings entered in the web UI, so the Agent works without editing .env.

The key is stored in data/account/llm.json on this machine and is never returned to the browser
(only whether one is saved and its last four characters). Saved settings take precedence over .env;
clearing them falls back to .env. Every provider except Anthropic is reached through its
OpenAI-compatible chat-completions endpoint; Anthropic goes through the official SDK (provider.py).
"""
import json,re,time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from .lineup_catalog import write_json

def settings_path(root):return Path(root)/'data/account/llm.json'

# Model lists are suggestions for the picker, not a whitelist: any model ID the provider accepts works,
# and "Load models" asks the provider for its current list. The agents need tool (function) calling.
PROVIDERS=[
 {'id':'anthropic','label':'Anthropic Claude','protocol':'anthropic','base_url':'https://api.anthropic.com','key_url':'https://console.anthropic.com/settings/keys',
  'models':['claude-opus-5-5','claude-sonnet-5-5','claude-haiku-5-5','claude-fable-5-1']},
 {'id':'openai','label':'OpenAI','protocol':'openai','base_url':'https://api.openai.com/v1','token_field':'max_completion_tokens','key_url':'https://platform.openai.com/api-keys',
  'models':['gpt-5','gpt-5-mini','gpt-4.1']},
 {'id':'gemini','label':'Google Gemini','protocol':'openai','base_url':'https://generativelanguage.googleapis.com/v1beta/openai','key_url':'https://aistudio.google.com/apikey',
  'models':['gemini-2.5-pro','gemini-2.5-flash']},
 {'id':'deepseek','label':'DeepSeek','protocol':'openai','base_url':'https://api.deepseek.com','key_url':'https://platform.deepseek.com/api_keys',
  'models':['deepseek-chat','deepseek-reasoner']},
 {'id':'qwen','label':'Qwen (Alibaba Cloud)','protocol':'openai','base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1','key_url':'https://bailian.console.aliyun.com/',
  'models':['qwen-max','qwen-plus','qwen-turbo'],'note':'International accounts: https://dashscope-intl.aliyuncs.com/compatible-mode/v1'},
 {'id':'moonshot','label':'Moonshot Kimi','protocol':'openai','base_url':'https://api.moonshot.cn/v1','key_url':'https://platform.moonshot.cn/console/api-keys',
  'models':['kimi-latest','moonshot-v1-32k']},
 {'id':'zhipu','label':'Zhipu GLM','protocol':'openai','base_url':'https://open.bigmodel.cn/api/paas/v4','key_url':'https://open.bigmodel.cn/usercenter/apikeys',
  'models':['glm-4.5','glm-4-plus']},
 {'id':'xai','label':'xAI Grok','protocol':'openai','base_url':'https://api.x.ai/v1','key_url':'https://console.x.ai/',
  'models':['grok-4','grok-3-mini']},
 {'id':'mistral','label':'Mistral','protocol':'openai','base_url':'https://api.mistral.ai/v1','key_url':'https://console.mistral.ai/api-keys',
  'models':['mistral-large-latest','mistral-medium-latest']},
 {'id':'openrouter','label':'OpenRouter','protocol':'openai','base_url':'https://openrouter.ai/api/v1','key_url':'https://openrouter.ai/keys',
  'models':['openai/gpt-5','google/gemini-2.5-pro','deepseek/deepseek-chat']},
 {'id':'groq','label':'Groq','protocol':'openai','base_url':'https://api.groq.com/openai/v1','key_url':'https://console.groq.com/keys',
  'models':['llama-3.3-70b-versatile']},
 {'id':'ollama','label':'Ollama (local)','protocol':'openai','base_url':'http://localhost:11434/v1','key_optional':True,
  'models':['qwen3','llama3.1']},
 {'id':'custom','label':'Custom (OpenAI-compatible)','protocol':'openai','base_url':'','models':[]},
]
BY_ID={p['id']:p for p in PROVIDERS}
EFFORTS=('','low','medium','high')
LOCAL_HOSTS={'localhost','127.0.0.1','::1'}

def check_url(url):
    url=str(url or '').strip().rstrip('/');p=urlsplit(url)
    if (p.scheme not in {'https','http'} or not p.hostname or p.username or p.password or p.query or p.fragment
            or (p.scheme=='http' and p.hostname not in LOCAL_HOSTS) or len(url)>300):
        raise ValueError('接口地址无效：请使用 HTTPS，或本机 HTTP')
    return url

def is_local(url):return urlsplit(url).hostname in LOCAL_HOSTS

def load(root):
    try:data=json.loads(settings_path(root).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None
    return data if isinstance(data,dict) and data.get('model') else None

def validate(raw,previous=None):
    """Return clean settings from the form; an empty api_key keeps the saved one."""
    if not isinstance(raw,dict):raise ValueError('无效设置')
    provider=BY_ID.get(raw.get('provider'))
    if not provider:raise ValueError('未知的服务商')
    url=check_url(raw.get('base_url') or provider['base_url'])
    model=str(raw.get('model') or '').strip()
    if not re.fullmatch(r'[\w.:/@+-]{1,120}',model):raise ValueError('请填写模型 ID')
    effort=str(raw.get('effort') or '')
    if effort not in EFFORTS:raise ValueError('推理强度无效')
    key=str(raw.get('api_key') or '').strip()
    if not key and previous and previous.get('provider')==provider['id']:key=previous.get('api_key','')
    if key and (len(key)>400 or re.search(r'\s',key)):raise ValueError('API Key 格式不正确')
    if not key and not (provider.get('key_optional') or is_local(url)):raise ValueError('请填写 API Key')
    return {'provider':provider['id'],'protocol':provider['protocol'],'base_url':url,'model':model,'api_key':key,'effort':effort,
            'token_field':provider.get('token_field','max_tokens')}

def save(root,raw):
    clean=validate(raw,load(root));clean['updated']=time.time()
    write_json(settings_path(root),clean);return public(root)

def clear(root):
    p=settings_path(root)
    if p.exists():p.unlink()
    return public(root)

def public(root):
    """What the browser may see: never the key itself."""
    from .provider import load_config
    s=load(root)
    try:active=load_config(root);configured=True
    except (ValueError,OSError):active=None;configured=False
    return {'providers':[{k:v for k,v in p.items()} for p in PROVIDERS],
            'saved':None if not s else {'provider':s['provider'],'base_url':s['base_url'],'model':s['model'],'effort':s.get('effort',''),
                'has_key':bool(s.get('api_key')),'key_hint':('…'+s['api_key'][-4:]) if len(s.get('api_key',''))>=8 else '','updated':s.get('updated')},
            'active':None if not active else {'source':active['source'],'provider':active.get('provider'),'model':active['LLM_MODEL_ID'],
                'host':urlsplit(active['endpoint']).hostname},
            'configured':configured}

def draft_config(root,raw):
    """Config for testing the form before it is saved (falls back to the saved key)."""
    from .provider import config_from_settings
    return config_from_settings(validate(raw,load(root)),root)

def test(root,raw):
    """One small request with one tool: proves the key, the model ID and tool calling."""
    from langchain_core.messages import HumanMessage
    from .provider import ConfiguredModel
    config={**draft_config(root,raw),'max_tokens':2048,'timeout':60}
    if config['protocol']=='anthropic' and not config.get('LLM_AGENT_REASONING'):config['LLM_AGENT_REASONING']='low'
    tool={'type':'function','function':{'name':'report_status','description':'Report that the connection works.',
          'parameters':{'type':'object','properties':{'status':{'type':'string'}},'required':['status']}}}
    model=ConfiguredModel(config);started=time.monotonic()
    try:reply=model.invoke([HumanMessage(content='Connection test. Call report_status with status "ok".')],[tool])
    except Exception as e:raise ValueError(friendly(e)) from None
    finally:model.close()
    return {'ok':True,'model':config['LLM_MODEL_ID'],'latency_ms':round((time.monotonic()-started)*1000),
            'tool_calls':bool(reply.tool_calls),'reply':(reply.content or '')[:160]}

def models(root,raw,*,transport=None):
    """Ask the provider for its current model list."""
    config=draft_config(root,raw)
    if config['protocol']=='anthropic':
        from .provider import anthropic_client
        try:
            with anthropic_client(config,timeout=20) as client:ids=[m.id for m in client.models.list(limit=100)]
        except Exception as e:raise ValueError(friendly(e)) from None
    else:
        headers={'Authorization':'Bearer '+config['LLM_API_KEY']} if config['LLM_API_KEY'] else {}
        try:
            with httpx.Client(timeout=20,follow_redirects=False,transport=transport) as c:r=c.get(config['LLM_BASE_URL']+'/models',headers=headers)
        except httpx.HTTPError as e:raise ValueError('无法连接服务商：'+type(e).__name__) from None
        if r.status_code!=200:raise ValueError(f'服务商获取模型列表时返回 HTTP {r.status_code}')
        try:rows=r.json().get('data') or r.json().get('models') or []
        except ValueError:raise ValueError('服务商返回的模型列表无法解析') from None
        ids=[str(m.get('id') or m.get('name') or '').removeprefix('models/') for m in rows if isinstance(m,dict)]
    return {'models':sorted({i for i in ids if i})[:300]}

def friendly(e):
    """Short, key-free error text for the UI (Chinese source strings; i18n-en.js translates)."""
    status=getattr(e,'status_code',None)
    m=re.search(r'HTTP (\d{3})',str(e))
    status=status or (int(m.group(1)) if m else None)
    if status in (401,403):return '服务商拒绝了这个 API Key（HTTP %d）'%status
    if status==404:return '服务商找不到这个模型 ID 或接口（HTTP 404）'
    if status==429:return '请求过于频繁，或服务商账户余额不足（HTTP 429）'
    if status:return '服务商返回 HTTP %d'%status
    name=type(e).__name__
    if 'Timeout' in name:return '服务商没有及时响应'
    if 'Connect' in name:return '无法连接服务商，请检查接口地址'
    return '测试失败：'+name
