"""Vector embeddings for retrieval, computed by a provider's embeddings API.

Settings live in data/account/embedding.json (the key is never returned to the browser). Vectors are cached
in data/vectors/index.sqlite, keyed by model and text hash, so each text is embedded once per model.
Retrieval is hybrid: hard filters first, then cosine similarity blended with the existing keyword score.
When no embedding model is configured, or the provider fails, callers keep their keyword ranking and say so.

What leaves the machine: the library texts (tactic cards, reviewed notes, your case library, lineup and
learning cards) and the search queries, sent to the embedding provider you chose. Situation vectors for
pro rounds and the casebook are numeric and computed locally (casebook.py, demo_compare.py).
"""
import hashlib,json,re,sqlite3,threading,time
from pathlib import Path
import httpx
import numpy as np
from .casebook import ROOT
from .lineup_catalog import write_json

def settings_path(root):return Path(root)/'data/account/embedding.json'
def index_path(root):return Path(root)/'data/vectors/index.sqlite'

# Suggested models only; any model ID the provider accepts works. batch = max inputs per request.
PROVIDERS=[
 {'id':'openai','label':'OpenAI','base_url':'https://api.openai.com/v1','models':['text-embedding-3-small','text-embedding-3-large'],'dimensions':True,'batch':64},
 {'id':'voyage','label':'Voyage AI','base_url':'https://api.voyageai.com/v1','models':['voyage-3.5','voyage-3.5-lite'],'input_type':True,'batch':64,
  'key_url':'https://dash.voyageai.com/','note':"Anthropic's recommended embeddings provider (Claude has no embeddings API)."},
 {'id':'gemini','label':'Google Gemini','base_url':'https://generativelanguage.googleapis.com/v1beta/openai','models':['gemini-embedding-001','text-embedding-004'],'batch':64},
 {'id':'qwen','label':'Qwen (Alibaba Cloud)','base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1','models':['text-embedding-v4','text-embedding-v3'],'batch':10,
  'note':'International accounts: https://dashscope-intl.aliyuncs.com/compatible-mode/v1'},
 {'id':'zhipu','label':'Zhipu GLM','base_url':'https://open.bigmodel.cn/api/paas/v4','models':['embedding-3'],'batch':32},
 {'id':'mistral','label':'Mistral','base_url':'https://api.mistral.ai/v1','models':['mistral-embed'],'batch':32},
 {'id':'ollama','label':'Ollama (local)','base_url':'http://localhost:11434/v1','models':['bge-m3','nomic-embed-text'],'key_optional':True,'batch':32},
 {'id':'custom','label':'Custom (OpenAI-compatible)','base_url':'','models':[],'batch':32},
]
BY_ID={p['id']:p for p in PROVIDERS}
MAX_CHARS=4000        # per text sent to the provider
MAX_NEW_PER_CALL=2000 # texts embedded by one retrieval or rebuild
ALPHA=0.65            # weight of cosine similarity in the hybrid score
MIN_SIMILARITY=0.40   # below this a vector-only hit is not treated as relevant
LOCK=threading.RLock()
TRANSPORT=None   # tests swap in a mock httpx transport

def _root(root):return Path(root) if root is not None else ROOT

# ---------------------------------------------------------------- settings
def load(root=None):
    try:data=json.loads(settings_path(_root(root)).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None
    return data if isinstance(data,dict) and data.get('model') else None

def _chat_key(root,provider):
    from .llm_settings import load as chat
    s=chat(root)
    return s.get('api_key','') if s and s.get('provider')==provider else ''

def validate(raw,previous=None,root=None):
    root=_root(root)
    from .llm_settings import check_url,is_local
    if not isinstance(raw,dict):raise ValueError('无效设置')
    p=BY_ID.get(raw.get('provider'))
    if not p:raise ValueError('未知的服务商')
    url=check_url(raw.get('base_url') or p['base_url'])
    model=str(raw.get('model') or '').strip()
    if not re.fullmatch(r'[\w.:/@+-]{1,120}',model):raise ValueError('请填写模型 ID')
    dims=raw.get('dimensions')
    if dims in ('',None):dims=None
    else:
        try:dims=int(dims)
        except (TypeError,ValueError):raise ValueError('向量维度无效') from None
        if not 32<=dims<=8192:raise ValueError('向量维度无效')
    key=str(raw.get('api_key') or '').strip()
    if not key and previous and previous.get('provider')==p['id']:key=previous.get('api_key','')
    if key and (len(key)>400 or re.search(r'\s',key)):raise ValueError('API Key 格式不正确')
    if not key and not (p.get('key_optional') or is_local(url) or _chat_key(root,p['id'])):raise ValueError('请填写 API Key')
    return {'provider':p['id'],'base_url':url,'model':model,'api_key':key,'dimensions':dims}

def config(root=None,saved=None):
    """Runtime config, or None when embeddings are not set up."""
    root=_root(root);s=saved or load(root)
    if not s:return None
    p=BY_ID.get(s['provider'],BY_ID['custom'])
    key=s.get('api_key') or _chat_key(root,s['provider'])
    model_key=hashlib.sha256(f"{s['provider']}|{s['base_url']}|{s['model']}|{s.get('dimensions')}".encode()).hexdigest()[:24]
    return {**s,'api_key':key,'batch':p['batch'],'input_type':p.get('input_type',False),'send_dimensions':p.get('dimensions',False),'model_key':model_key}

def save(root,raw):
    clean=validate(raw,load(root),root);clean['updated']=time.time()
    write_json(settings_path(root),clean);return public(root)

def clear(root):
    p=settings_path(root)
    if p.exists():p.unlink()
    return public(root)

def public(root):
    s=load(root);c=config(root)
    return {'providers':PROVIDERS,
            'saved':None if not s else {'provider':s['provider'],'base_url':s['base_url'],'model':s['model'],'dimensions':s.get('dimensions'),
                'has_key':bool(s.get('api_key')),'key_hint':('…'+s['api_key'][-4:]) if len(s.get('api_key',''))>=8 else '',
                'reuses_chat_key':not s.get('api_key') and bool(c and c['api_key'])},
            'configured':bool(c),'index':index_status(root,c)}

# ---------------------------------------------------------------- provider calls
def embed_texts(texts,cfg,kind='document',*,transport=None):
    """Embed a list of texts; returns an (n, dim) float32 array of unit vectors."""
    if not texts:return np.zeros((0,0),dtype=np.float32)
    headers={'Content-Type':'application/json'}
    if cfg['api_key']:headers['Authorization']='Bearer '+cfg['api_key']
    rows=[]
    with httpx.Client(timeout=60,follow_redirects=False,transport=transport) as client:
        for i in range(0,len(texts),cfg['batch']):
            body={'model':cfg['model'],'input':[t[:MAX_CHARS] or ' ' for t in texts[i:i+cfg['batch']]]}
            if cfg['input_type']:body['input_type']=kind
            if cfg.get('dimensions') and cfg['send_dimensions']:body['dimensions']=cfg['dimensions']
            try:r=client.post(cfg['base_url']+'/embeddings',json=body,headers=headers)
            except httpx.HTTPError as e:raise RuntimeError('无法连接服务商：'+type(e).__name__) from None
            if r.status_code!=200:raise RuntimeError(f'服务商返回 HTTP {r.status_code}')
            try:data=sorted(r.json()['data'],key=lambda d:d.get('index',0))
            except (ValueError,KeyError,TypeError):raise RuntimeError('服务商返回的向量无法解析') from None
            if len(data)!=len(body['input']):raise RuntimeError('服务商返回的向量数量不对')
            rows.extend(d['embedding'] for d in data)
    m=np.asarray(rows,dtype=np.float32)
    if m.ndim!=2 or not m.shape[1]:raise RuntimeError('服务商返回的向量无法解析')
    norms=np.linalg.norm(m,axis=1,keepdims=True);norms[norms==0]=1
    return m/norms

def _hash(text,kind):return hashlib.sha256((kind+'\0'+text[:MAX_CHARS]).encode('utf-8')).hexdigest()

def _db(root):
    p=index_path(root);p.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(p)
    db.execute('CREATE TABLE IF NOT EXISTS vectors(model_key TEXT,text_hash TEXT,dim INTEGER,vector BLOB,PRIMARY KEY(model_key,text_hash))')
    db.execute('CREATE TABLE IF NOT EXISTS libraries(library TEXT,model_key TEXT,items INTEGER,updated REAL,PRIMARY KEY(library,model_key))')
    return db

def vectors(texts,cfg,root=None,kind='document',*,transport=None,library=None):
    """Cached vectors for texts, embedding only the ones not seen before with this model."""
    root=_root(root);transport=transport or TRANSPORT
    hashes=[_hash(t,kind) for t in texts]
    with LOCK,_db(root) as db:
        found={}
        for i in range(0,len(hashes),500):
            chunk=hashes[i:i+500]
            for h,dim,blob in db.execute(f'SELECT text_hash,dim,vector FROM vectors WHERE model_key=? AND text_hash IN ({",".join("?"*len(chunk))})',[cfg['model_key'],*chunk]):
                found[h]=np.frombuffer(blob,dtype=np.float32,count=dim)
        missing=sorted({h:t for h,t in zip(hashes,texts) if h not in found}.items())
        if len(missing)>MAX_NEW_PER_CALL:raise RuntimeError('需要嵌入的文本过多，请先在模型设置中重建向量索引')
        if missing:
            new=embed_texts([t for _,t in missing],cfg,kind,transport=transport)
            db.executemany('INSERT OR REPLACE INTO vectors VALUES(?,?,?,?)',[(cfg['model_key'],h,int(v.shape[0]),v.astype(np.float32).tobytes()) for (h,_),v in zip(missing,new)])
            for (h,_),v in zip(missing,new):found[h]=v
        if library:db.execute('INSERT OR REPLACE INTO libraries VALUES(?,?,?,?)',(library,cfg['model_key'],len(set(hashes)),time.time()))
    dims={v.shape[0] for v in found.values()}
    if len(dims)>1:raise RuntimeError('向量维度不一致，请重建向量索引')
    return np.stack([found[h] for h in hashes]) if hashes else np.zeros((0,0),dtype=np.float32)

# ---------------------------------------------------------------- retrieval helpers
def semantic(library,texts,query,root=None,*,transport=None):
    """Cosine similarity of query to each text, or (None, reason) when vector search is unavailable."""
    root=_root(root);cfg=config(root)
    if not cfg:return None,{'vector':'off','reason':'no embedding model configured'}
    if not texts or not str(query or '').strip():return None,{'vector':'skipped','reason':'empty query or library','model':cfg['model']}
    try:
        docs=vectors(texts,cfg,root,'document',transport=transport,library=library)
        q=vectors([query],cfg,root,'query',transport=transport)[0]
    except (RuntimeError,OSError,sqlite3.Error) as e:
        return None,{'vector':'unavailable','reason':str(e)[:160],'model':cfg['model']}
    if docs.shape[1]!=q.shape[0]:return None,{'vector':'unavailable','reason':'dimension mismatch','model':cfg['model']}
    return docs@q,{'vector':'on','model':cfg['model'],'provider':cfg['provider']}

def hybrid(keyword,sims,alpha=ALPHA):
    """Blend keyword scores (any scale) with cosine similarities; keyword only when sims is None."""
    kw=np.asarray(keyword,dtype=np.float32)
    top=float(kw.max()) if kw.size and kw.max()>0 else 0.
    kwn=kw/top if top else kw*0
    if sims is None:return [float(x) for x in kw]
    return [float(alpha*s+(1-alpha)*k) for s,k in zip(np.asarray(sims,dtype=np.float32),kwn)]

def method(info,keyword):
    if info.get('vector')=='on':return f"hybrid: vector embeddings ({info['model']}) + {keyword}"
    return f"{keyword} (vector search {info.get('vector')}: {info.get('reason')})"

# ---------------------------------------------------------------- status, test, rebuild
def index_status(root,cfg=None):
    cfg=cfg if cfg is not None else config(root)
    if not cfg or not index_path(root).exists():return {'libraries':[],'vectors':0}
    with _db(root) as db:
        rows=db.execute('SELECT library,items,updated FROM libraries WHERE model_key=? ORDER BY library',(cfg['model_key'],)).fetchall()
        total=db.execute('SELECT COUNT(*) FROM vectors WHERE model_key=?',(cfg['model_key'],)).fetchone()[0]
    return {'libraries':[{'library':l,'items':n,'updated':u} for l,n,u in rows],'vectors':total}

def test(root,raw,*,transport=None):
    from .llm_settings import friendly
    cfg=config(root,validate(raw,load(root),root));started=time.monotonic()
    try:m=embed_texts(['B site retake through tunnels','从 B 洞回防 B 包点'],cfg,'document',transport=transport or TRANSPORT)
    except RuntimeError as e:raise ValueError(str(e)) from None
    except Exception as e:raise ValueError(friendly(e)) from None
    return {'ok':True,'model':cfg['model'],'dimensions':int(m.shape[1]),'latency_ms':round((time.monotonic()-started)*1000),
            'cross_language_similarity':round(float(m[0]@m[1]),3)}

def library_texts():
    """Every text library that is present on this machine, as (name, texts)."""
    out=[]
    def add(name,fn):
        try:texts=fn()
        except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):return
        if texts:out.append((name,texts))
    from . import tactics_rag,tactic_cases,lineup_catalog,learning_resources
    from .casebook import connect,knowledge_texts
    add('tactic_cards',tactics_rag.card_texts)
    add('case_library',lambda:[tactic_cases.case_text(c) for c in tactic_cases.catalog()['cases']])
    add('lineup_cards',lambda:[lineup_catalog.card_text(c) for c in lineup_catalog.load_catalog()['cards']])
    add('learning_resources',lambda:[learning_resources.card_text(c) for c in learning_resources.load_cards()])
    def notes():
        db=connect()
        try:return knowledge_texts(db)
        finally:db.close()
    add('reviewed_notes',notes)
    return out

def rebuild(root=None,*,transport=None):
    root=_root(root);cfg=config(root)
    if not cfg:raise ValueError('尚未配置向量嵌入模型')
    done=[]
    for name,texts in library_texts():
        try:vectors(texts,cfg,root,'document',transport=transport,library=name)
        except RuntimeError as e:raise ValueError(str(e)) from None
        done.append({'library':name,'items':len(texts)})
    return {'rebuilt':done,'index':index_status(root,cfg)}
