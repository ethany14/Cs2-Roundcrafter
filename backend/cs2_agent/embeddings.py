"""Vector embeddings for retrieval, computed by a local model on this machine or by a provider's embeddings API.

Settings live in data/account/embedding.json (the key is never returned to the browser). Vectors are cached
in data/vectors/index.sqlite, keyed by model and text hash, so each text is embedded once per model.
Retrieval is hybrid: hard filters first, then cosine similarity blended with the existing keyword score.
When no embedding model is configured, or the provider fails, callers keep their keyword ranking and say so.

With the local model nothing leaves the machine (after a one-time model download from Hugging Face).
With a provider API, what leaves the machine is: the library texts (tactic cards, reviewed notes, your case library, lineup and
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
# Local models run through fastembed (ONNX on the CPU, no PyTorch). Some models expect prefixes; fastembed
# does not add them, so they are applied here. Sizes are the one-time download.
LOCAL_MODELS=[
 {'id':'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2','label':'Multilingual MiniLM','size_gb':0.22,'dim':384,
  'note':'小而快，支持 50 多种语言，推荐默认。'},
 {'id':'BAAI/bge-small-zh-v1.5','label':'BGE small zh','size_gb':0.09,'dim':512,'query_prefix':'为这个句子生成表示以用于检索相关文章：',
  'note':'最小；以中文为主，纯英文文本较弱。'},
 {'id':'Qwen/Qwen3-Embedding-0.6B-Q','label':'Qwen3 Embedding 0.6B (quantized)','size_gb':1.12,'dim':1024,
  'query_prefix':'Instruct: Given a Counter-Strike 2 tactics question, retrieve notes that answer it\nQuery:',
  'note':'质量最好，多语言；CPU 上较慢。'},
 {'id':'intfloat/multilingual-e5-large','label':'Multilingual E5 large','size_gb':2.24,'dim':1024,'query_prefix':'query: ','doc_prefix':'passage: ',
  'note':'多语言能力强；下载较大。'},
 {'id':'minishlab/potion-multilingual-128M','label':'Potion multilingual (static)','size_gb':0.51,'dim':256,
  'note':'静态向量；最快，质量较低。'},
]
LOCAL_BY_ID={m['id']:m for m in LOCAL_MODELS}

PROVIDERS=[
 {'id':'local','label':'本地模型（本机运行）','base_url':'','models':[m['id'] for m in LOCAL_MODELS],'local':True,'key_optional':True,'batch':32,
  'local_models':LOCAL_MODELS},
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
ALPHA=0.65            # default weight of cosine similarity in the hybrid score (user-adjustable)
MIN_SIMILARITY=0.40   # floor used until a model is calibrated (user can override)
# Calibration: each model has its own baseline for unrelated text, so the floor for a vector-only hit comes from
# the model's own scores. Off-topic probe queries (embedded as queries, like real searches) are compared with the
# library; the floor is a high percentile of their best-match scores, i.e. what an unrelated query still reaches.
# Note-to-note similarity is not used: notes in one domain resemble each other far more than a query resembles
# a note, which put the floor above most correct matches (see outputs/retrieval/embedding-quality.md).
PROBE_QUERIES=['what graphics card do I need for 300 fps','how to change my steam profile picture','refund a game on steam',
  'best gaming headset under 100 dollars','how to stream with OBS on twitch','is my internet ping too high to play',
  '240Hz 显示器值得买吗','怎么改 Steam 名字','游戏闪退怎么修复','鼠标垫选什么材质','怎么开直播','网络延迟高怎么办']
CALIBRATION_PERCENTILE=75
CALIBRATION_MIN_VECTORS=20
FLOOR_RANGE=(0.15,0.90)
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
    model=str(raw.get('model') or '').strip()
    if not re.fullmatch(r'[\w.:/@+-]{1,120}',model):raise ValueError('请填写模型 ID')
    if p.get('local'):
        if model not in LOCAL_BY_ID:raise ValueError('请选择列表中的本地模型')
        url=''
    else:url=check_url(raw.get('base_url') or p['base_url'])
    dims=raw.get('dimensions')
    if dims in ('',None):dims=None
    else:
        try:dims=int(dims)
        except (TypeError,ValueError):raise ValueError('向量维度无效') from None
        if not 32<=dims<=8192:raise ValueError('向量维度无效')
    key=str(raw.get('api_key') or '').strip()
    if not key and previous and previous.get('provider')==p['id']:key=previous.get('api_key','')
    if key and (len(key)>400 or re.search(r'\s',key)):raise ValueError('API Key 格式不正确')
    if p.get('local'):key=''
    elif not key and not (p.get('key_optional') or is_local(url) or _chat_key(root,p['id'])):raise ValueError('请填写 API Key')
    def fraction(name,low,high,message):
        v=raw.get(name)
        if v in ('',None):return None
        try:v=float(v)
        except (TypeError,ValueError):raise ValueError(message) from None
        if not low<=v<=high:raise ValueError(message)
        return round(v,3)
    return {'provider':p['id'],'base_url':url,'model':model,'api_key':key,'dimensions':dims,
            'alpha':fraction('alpha',0,1,'语义权重须在 0 到 1 之间'),
            'min_similarity':fraction('min_similarity',0,1,'相似度下限须在 0 到 1 之间')}

def config(root=None,saved=None):
    """Runtime config, or None when embeddings are not set up."""
    root=_root(root);s=saved or load(root)
    if not s:return None
    p=BY_ID.get(s['provider'],BY_ID['custom'])
    key=s.get('api_key') or _chat_key(root,s['provider'])
    model_key=hashlib.sha256(f"{s['provider']}|{s['base_url']}|{s['model']}|{s.get('dimensions')}".encode()).hexdigest()[:24]
    return {**s,'api_key':key,'batch':p['batch'],'input_type':p.get('input_type',False),'send_dimensions':p.get('dimensions',False),'model_key':model_key,
            'local':bool(p.get('local')),'root':str(root)}

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
                'reuses_chat_key':not s.get('api_key') and bool(c and c['api_key']),
                'alpha':s.get('alpha'),'min_similarity':s.get('min_similarity')},
            'configured':bool(c),'index':index_status(root,c),'tuning':tuning(root,c),'local_runtime':local_runtime(root)}

# ---------------------------------------------------------------- provider calls
# ---------------------------------------------------------------- local model
LOCAL={}   # model id -> loaded fastembed model, shared by all requests

def models_dir(root):return Path(root)/'data/models/fastembed'

def local_runtime(root=None):
    """Whether fastembed is installed and which local models are already downloaded."""
    try:import fastembed
    except ImportError:return {'installed':False,'downloaded':[]}
    folder=models_dir(_root(root))
    names={p.name for p in folder.iterdir()} if folder.exists() else set()
    downloaded=[m['id'] for m in LOCAL_MODELS if any(m['id'].split('/')[-1].lower().removesuffix('-q') in n.lower() for n in names)]
    return {'installed':True,'version':fastembed.__version__,'downloaded':downloaded,'folder':'data/models/fastembed'}

def local_model(model_id,root=None):
    with LOCK:
        if model_id not in LOCAL:
            try:from fastembed import TextEmbedding
            except ImportError:raise RuntimeError('本地向量模型需要 fastembed：pip install -e ".[local-embeddings]"') from None
            folder=models_dir(_root(root));folder.mkdir(parents=True,exist_ok=True)
            try:LOCAL[model_id]=TextEmbedding(model_name=model_id,cache_dir=str(folder))
            except Exception as e:raise RuntimeError('本地模型加载失败：'+type(e).__name__) from None
        return LOCAL[model_id]

def local_embed(texts,cfg,kind):
    spec=LOCAL_BY_ID.get(cfg['model'],{})
    prefix=spec.get('query_prefix','') if kind=='query' else spec.get('doc_prefix','')
    model=local_model(cfg['model'],cfg.get('root'))
    try:return np.asarray(list(model.embed([prefix+(t[:MAX_CHARS] or ' ') for t in texts],batch_size=cfg['batch'])),dtype=np.float32)
    except Exception as e:raise RuntimeError('本地模型运行失败：'+type(e).__name__) from None

def _unit(m):
    norms=np.linalg.norm(m,axis=1,keepdims=True);norms[norms==0]=1
    return m/norms

def embed_texts(texts,cfg,kind='document',*,transport=None):
    """Embed a list of texts; returns an (n, dim) float32 array of unit vectors."""
    if not texts:return np.zeros((0,0),dtype=np.float32)
    if cfg.get('local'):return _unit(local_embed(texts,cfg,kind))
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
    db.execute('CREATE TABLE IF NOT EXISTS calibration(model_key TEXT PRIMARY KEY,floor REAL,pairs INTEGER,vectors INTEGER,updated REAL)')
    try:db.execute("ALTER TABLE vectors ADD COLUMN kind TEXT DEFAULT 'document'")
    except sqlite3.OperationalError:pass  # column already there
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
            db.executemany('INSERT OR REPLACE INTO vectors(model_key,text_hash,dim,vector,kind) VALUES(?,?,?,?,?)',[(cfg['model_key'],h,int(v.shape[0]),v.astype(np.float32).tobytes(),kind) for (h,_),v in zip(missing,new)])
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
    t=tuning(root,cfg)
    if t['floor_source']=='default' and calibrate(root,cfg) is not None:t=tuning(root,cfg)
    return docs@q,{'vector':'on','model':cfg['model'],'provider':cfg['provider'],'alpha':t['alpha'],'floor':t['floor'],'floor_source':t['floor_source']}

def hybrid(keyword,sims,alpha=None):
    """Blend keyword scores (any scale) with cosine similarities; keyword only when sims is None.
    alpha is the weight of meaning (0-1), or the info dict from semantic() carrying the user's setting."""
    if isinstance(alpha,dict):alpha=alpha.get('alpha')
    alpha=ALPHA if alpha is None else alpha
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
    calibrate(root,cfg)
    return {'rebuilt':done,'index':index_status(root,cfg),'tuning':tuning(root,cfg)}


# ---------------------------------------------------------------- tuning
def floor_from(doc_vectors,probe_vectors,percentile=None):
    """Floor = a high percentile of the best similarity that each off-topic probe query reaches in the library."""
    top=(probe_vectors@doc_vectors.T).max(axis=1)
    return float(np.clip(np.percentile(top,CALIBRATION_PERCENTILE if percentile is None else percentile),*FLOOR_RANGE))

def calibrate(root=None,cfg=None,*,transport=None):
    """Set this model's floor from its own scores: off-topic probe queries against the library's notes."""
    root=_root(root);cfg=cfg or config(root)
    if not cfg:return None
    with LOCK,_db(root) as db:
        rows=db.execute("SELECT dim,vector FROM vectors WHERE model_key=? AND kind='document'",(cfg['model_key'],)).fetchall()
    if len(rows)<CALIBRATION_MIN_VECTORS:return None
    docs=np.stack([np.frombuffer(b,dtype=np.float32,count=d) for d,b in rows])
    try:probes=vectors(PROBE_QUERIES,cfg,root,'query',transport=transport)
    except RuntimeError:return None
    floor=floor_from(docs,probes)
    with LOCK,_db(root) as db:
        db.execute('INSERT OR REPLACE INTO calibration VALUES(?,?,?,?,?)',(cfg['model_key'],round(floor,4),len(PROBE_QUERIES)*len(docs),len(docs),time.time()))
    return floor

def tuning(root=None,cfg=None):
    """Effective blend and floor: the user's setting, else the model's calibration, else the defaults."""
    root=_root(root);cfg=cfg if cfg is not None else config(root)
    calibrated=None
    if cfg and index_path(root).exists():
        with _db(root) as db:
            row=db.execute('SELECT floor,pairs,vectors FROM calibration WHERE model_key=?',(cfg['model_key'],)).fetchone()
        if row:calibrated={'floor':row[0],'pairs':row[1],'vectors':row[2]}
    if cfg and cfg.get('min_similarity') is not None:floor,source=cfg['min_similarity'],'manual'
    elif calibrated:floor,source=calibrated['floor'],'calibrated'
    else:floor,source=MIN_SIMILARITY,'default'
    alpha=cfg.get('alpha') if cfg and cfg.get('alpha') is not None else ALPHA
    return {'alpha':alpha,'floor':floor,'floor_source':source,'calibrated':calibrated,'defaults':{'alpha':ALPHA,'floor':MIN_SIMILARITY}}
