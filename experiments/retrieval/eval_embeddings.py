"""Measure embedding quality on the bilingual CS2 retrieval benchmark.

Runs through the app's own embedding code (backend/cs2_agent/embeddings.py), so prefixes, normalisation and
the hybrid blend are exactly what retrieval uses. Compares keyword-only (BM25), vector-only and hybrid ranking.

    # a local model by name (downloads once from Hugging Face)
    python experiments/retrieval/eval_embeddings.py --local sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    # whatever is saved in the app's Embeddings settings (local or API)
    python experiments/retrieval/eval_embeddings.py --app
    # an ONNX export already on disk (needs tokenizer.json next to model.onnx)
    python experiments/retrieval/eval_embeddings.py --onnx DIR --name my-model --pooling cls --dim 512

Add --report outputs/retrieval/<name>.md to write a Markdown report (several runs append to one file).
"""
import argparse,json,math,re,sys,time
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from cs2_agent import embeddings as emb  # noqa: E402

BENCH=Path(__file__).with_name('cs2_retrieval_benchmark.json')

def tokens(text):
    t=text.lower()
    return re.findall(r'[a-z0-9]+',t)+[s[i:i+2] for s in re.findall(r'[一-鿿]+',t) for i in range(max(1,len(s)-1))]

def bm25(query,docs):
    toks=[tokens(d) for d in docs];avg=sum(map(len,toks))/len(toks);q=set(tokens(query));out=[]
    for doc in toks:
        s=0.
        for term in q:
            tf=doc.count(term);df=sum(term in d for d in toks)
            if tf:s+=math.log(1+(len(toks)-df+.5)/(df+.5))*tf*2.2/(tf+1.2*(.25+.75*len(doc)/avg))
        out.append(s)
    return np.array(out)

def load_bench():
    b=json.loads(BENCH.read_text(encoding='utf-8'))
    docs,doc_concept,doc_lang=[],[],[]
    for c in b['concepts']:
        for lang in ('en','zh'):docs.append(c[lang]);doc_concept.append(c['id']);doc_lang.append(lang)
    queries=[{'q':c['q_'+lang],'lang':lang,'concept':c['id']} for c in b['concepts'] for lang in ('en','zh')]
    return docs,np.array(doc_concept),np.array(doc_lang),queries,b['negatives']

def config_for(args):
    if args.app:
        cfg=emb.config()
        if not cfg:sys.exit('No embedding model is saved in the app settings.')
        return cfg
    if args.onnx:
        from fastembed import TextEmbedding
        from fastembed.common.model_description import PoolingType,ModelSource
        pooling={'cls':PoolingType.CLS,'mean':PoolingType.MEAN}[args.pooling]
        try:TextEmbedding.add_custom_model(model=args.name,pooling=pooling,normalization=True,sources=ModelSource(hf='local/'+args.name),dim=args.dim,model_file=args.model_file)
        except ValueError:pass
        emb.LOCAL[args.name]=TextEmbedding(model_name=args.name,specific_model_path=args.onnx)
        emb.LOCAL_BY_ID[args.name]={'id':args.name,'query_prefix':args.query_prefix or '','doc_prefix':args.doc_prefix or ''}
        model=args.name
    else:
        model=args.local
        if model not in emb.LOCAL_BY_ID:sys.exit('Unknown local model; choose one of: '+', '.join(emb.LOCAL_BY_ID))
    return {'provider':'local','model':model,'local':True,'batch':32,'api_key':'','root':str(ROOT)}

def ranks(scores,rel):
    order=np.argsort(-scores,kind='stable')
    return [int(np.where(rel[order])[0][0])+1] if rel.any() else []

def evaluate(cfg,alphas=(0,.35,.5,.65,.8,1)):
    docs,concept,lang,queries,negatives=load_bench()
    t=time.perf_counter();D=emb.embed_texts(docs,cfg,'document');doc_ms=(time.perf_counter()-t)*1000/len(docs)
    Q=emb.embed_texts([q['q'] for q in queries],cfg,'query');N=emb.embed_texts([n['q'] for n in negatives],cfg,'query')
    # The app's calibration (embeddings.floor_from): off-topic probe queries against the notes.
    P=emb.embed_texts(emb.PROBE_QUERIES,cfg,'query');floor=emb.floor_from(D,P)
    rng=np.random.default_rng(0);i=rng.integers(0,len(D),4000);j=rng.integers(0,len(D),4000);keep=i!=j
    old_floor=float(np.clip(np.percentile(np.einsum('ij,ij->i',D[i[keep]],D[j[keep]]),95),*emb.FLOOR_RANGE))
    sims_rel=[float((D@Q[qi])[concept==q['concept']].max()) for qi,q in enumerate(queries)]
    neg_top=[float((D@N[k]).max()) for k in range(len(negatives))]
    rows={}
    for a in alphas:
        r1=r3=mrr=cross3=0.
        for qi,q in enumerate(queries):
            kw=bm25(q['q'],docs);sims=D@Q[qi]
            score=np.array(emb.hybrid(kw,sims,a)) if a>0 else kw
            rel=concept==q['concept'];order=np.argsort(-score,kind='stable')
            first=int(np.where(rel[order])[0][0])+1
            r1+=first==1;r3+=first<=3;mrr+=1/first
            other=rel&(lang!=q['lang']);cross3+=bool(other[order[:3]].any())
        n=len(queries);rows[a]={'R@1':r1/n,'R@3':r3/n,'MRR':mrr/n,'cross@3':cross3/n}
    by_lang={}
    for a in (0,emb.ALPHA,1):
        for lg in ('en','zh'):
            hits=[]
            for qi,q in enumerate(queries):
                if q['lang']!=lg:continue
                kw=bm25(q['q'],docs);score=np.array(emb.hybrid(kw,D@Q[qi],a)) if a>0 else kw
                order=np.argsort(-score,kind='stable');hits.append(int(np.where((concept==q['concept'])[order])[0][0])+1)
            by_lang.setdefault(a,{})[lg]={'R@1':float(np.mean(np.array(hits)==1)),'MRR':float(np.mean(1/np.array(hits)))}
    neg_lang={lg:float(np.mean([(D@N[k]).max()>=floor for k,n in enumerate(negatives) if n['lang']==lg])) for lg in ('en','zh')}
    other=[float(np.delete(D@Q[qi],np.where(concept==q['concept'])[0]).max()) for qi,q in enumerate(queries)]
    sweep={p:{'floor':round(emb.floor_from(D,P,p),3)} for p in (50,75,90,100)}
    for p,v in sweep.items():
        v['relevant_above']=float(np.mean(np.array(sims_rel)>=v['floor']));v['negatives_above']=float(np.mean(np.array(neg_top)>=v['floor']))
    return {'model':cfg['model'],'dim':int(D.shape[1]),'ms_per_doc':round(doc_ms,1),'alphas':rows,'floor':round(floor,3),'old_note_pair_floor':round(old_floor,3),'floor_sweep':sweep,'by_lang':by_lang,'negatives_above_by_lang':neg_lang,
            'relevant_above_floor':float(np.mean(np.array(sims_rel)>=floor)),'negatives_above_floor':float(np.mean(np.array(neg_top)>=floor)),
            'mean_sim':{'relevant':float(np.mean(sims_rel)),'best_wrong':float(np.mean(other)),'negative_top':float(np.mean(neg_top))}}

def markdown(r):
    head=f"### {r['model']}\n\n{r['dim']} dims · {r['ms_per_doc']} ms per note on this CPU · calibrated floor {r['floor']}\n\n"
    table='| Ranking | Recall@1 | Recall@3 | MRR | Other-language note in top 3 |\n|---|---:|---:|---:|---:|\n'
    for a,m in r['alphas'].items():
        name='Keyword only (BM25)' if a==0 else 'Vector only' if a==1 else f'Hybrid, {int(a*100)}% meaning'
        table+=f"| {name} | {m['R@1']:.2f} | {m['R@3']:.2f} | {m['MRR']:.2f} | {m['cross@3']:.2f} |\n"
    table+='\n| Query language | Keyword R@1 | Hybrid R@1 | Vector R@1 | Off-topic above floor |\n|---|---:|---:|---:|---:|\n'
    bl=r['by_lang'];k0,kh,k1=0,emb.ALPHA,1
    for lg,name in (('en','English'),('zh','Chinese')):
        table+=f"| {name} | {bl[k0][lg]['R@1']:.2f} | {bl[kh][lg]['R@1']:.2f} | {bl[k1][lg]['R@1']:.2f} | {r['negatives_above_by_lang'][lg]:.0%} |\n"
    s=r['mean_sim']
    sweep=' · '.join(f"p{p}: {v['floor']} ({v['relevant_above']:.0%} relevant / {v['negatives_above']:.0%} off-topic above)" for p,v in r['floor_sweep'].items())
    floor=(f"\nAt the calibrated floor, {r['relevant_above_floor']:.0%} of queries have their best relevant note above it and "
           f"{r['negatives_above_floor']:.0%} of off-topic queries wrongly clear it. Mean cosine: relevant {s['relevant']:.3f}, "
           f"best wrong note {s['best_wrong']:.3f}, off-topic query's top note {s['negative_top']:.3f}.\n\n"
           f"Floor by probe percentile: {sweep}. The earlier note-to-note calibration gave {r['old_note_pair_floor']}.\n")
    return head+table+floor

def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--local');g.add_argument('--app',action='store_true');g.add_argument('--onnx')
    ap.add_argument('--name');ap.add_argument('--pooling',choices=['cls','mean'],default='mean');ap.add_argument('--dim',type=int)
    ap.add_argument('--model-file',default='model.onnx');ap.add_argument('--query-prefix');ap.add_argument('--doc-prefix')
    ap.add_argument('--report');ap.add_argument('--json')
    args=ap.parse_args()
    if args.onnx and not (args.name and args.dim):ap.error('--onnx needs --name and --dim')
    r=evaluate(config_for(args));text=markdown(r);print(text)
    if args.report:
        p=Path(args.report);p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('a',encoding='utf-8') as f:f.write(text+'\n')
    if args.json:Path(args.json).write_text(json.dumps(r,indent=2),encoding='utf-8')

if __name__=='__main__':main()
