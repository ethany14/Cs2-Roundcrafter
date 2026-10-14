"""Local evidence casebook: deterministic structured retrieval, no paid indexing."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / 'data/casebook/cases.sqlite'


def connect(path=DEFAULT_DB):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    return db


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, match_id TEXT, demo_hash TEXT,
      split TEXT, map TEXT, side TEXT, payload TEXT);
    CREATE INDEX IF NOT EXISTS case_filter ON cases(split,map,side);
    CREATE TABLE IF NOT EXISTS knowledge(id TEXT PRIMARY KEY, kind TEXT, map TEXT,
      title TEXT, body TEXT, source TEXT, reviewed INTEGER, version TEXT);
    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(id UNINDEXED,title,body);
    ''')


def ingest(db, extraction, entry):
    if entry['split'] not in ('train', 'test'):
        raise ValueError('Unknown split')
    overlap = db.execute('SELECT 1 FROM cases WHERE (match_id=? OR demo_hash=?) AND split<>?',
                         (entry['match_id'], extraction['sha256'], entry['split'])).fetchone()
    if overlap:
        raise ValueError('Match/demo crosses reference and evaluation partitions')
    with db:
        db.execute('DELETE FROM cases WHERE match_id=?', (entry['match_id'],))
        for case in extraction['cases']:
            case = {**case, 'match_id': entry['match_id'], 'source_url': entry['source_url'],
                    'date': entry['date'], 'split': entry['split']}
            db.execute('INSERT INTO cases VALUES(?,?,?,?,?,?,?)',
                       (case['id'], entry['match_id'], extraction['sha256'], entry['split'],
                        case['map'], case['side'], json.dumps(case, ensure_ascii=False)))


def get_case(db, identifier):
    row = db.execute('SELECT payload FROM cases WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise ValueError('Unknown case')
    return json.loads(row[0])


def model_case(db,identifier):
    """Keep dense raw history on disk; bounded evidence goes to the agent."""
    case=get_case(db,identifier)
    case['evidence'].pop('history',None)
    case['evidence'].pop('smokes',None)
    case['evidence'].pop('smoke_disturbances',None)
    case['evidence']['history_access']='Use inspect_player_information for causal spotting history and geometry.'
    return case


def distance(query, reference):
    """Only pre-event features; outcomes and commentary never affect rank."""
    a, b = query['features'], reference['features']
    terms = {'position': math.dist(a['position'], b['position']) / 1000,
             'time': abs(a['elapsed']-b['elapsed']) / 30,
             'equipment': abs(a['equipment']-b['equipment']) / 3000}
    x,y = a['nearest_teammate'],b['nearest_teammate']
    terms['proximity'] = 0 if x is None and y is None else (2 if x is None or y is None else abs(x-y)/700)
    return sum(terms.values()), terms


def situation_vectors(cases):
    """Pre-event situation vectors: position, elapsed time, equipment value, nearest-teammate distance."""
    import numpy as np
    f=[c['features'] for c in cases]
    return {'position':np.array([x['position'] for x in f],dtype=float).reshape(len(f),-1),
            'time':np.array([x['elapsed'] for x in f],dtype=float),
            'equipment':np.array([x['equipment'] for x in f],dtype=float),
            'proximity':np.array([np.nan if x['nearest_teammate'] is None else x['nearest_teammate'] for x in f],dtype=float)}


def situation_distances(query, vectors):
    """The same weighted distance as distance(), computed against every candidate vector at once."""
    import numpy as np
    q=situation_vectors([query])
    parts={'position':np.linalg.norm(vectors['position']-q['position'][0],axis=1)/1000,
           'time':np.abs(vectors['time']-q['time'][0])/30,
           'equipment':np.abs(vectors['equipment']-q['equipment'][0])/3000}
    a,b=np.isnan(q['proximity'][0]),np.isnan(vectors['proximity'])
    parts['proximity']=np.where(a&b,0.,np.where(a|b,2.,np.abs(vectors['proximity']-q['proximity'][0])/700))
    return sum(parts.values()),parts


def retrieve(db, identifier, limit=3):
    query = get_case(db, identifier)
    candidates=[]
    for row in db.execute("SELECT payload FROM cases WHERE split='train' AND map=? AND side=? AND match_id<>? AND demo_hash<>?",
                          (query['map'],query['side'],query['match_id'],query['demo_sha256'])):
        candidate=json.loads(row[0])
        a,b=query['features'],candidate['features']
        if any(a[k]!=b[k] for k in ('own_alive','enemy_alive','bomb_planted')):
            continue
        candidates.append(candidate)
    ranked=[]
    if candidates:
        scores,parts=situation_distances(query,situation_vectors(candidates))
        for i,candidate in enumerate(candidates):
            p={k:float(v[i]) for k,v in parts.items()};score=float(scores[i])
            if p['position']>1 or p['time']>1.5 or score>3:
                continue
            ranked.append({'id':candidate['id'],'match_id':candidate['match_id'],'round':candidate['round'],
                           'tick':candidate['tick'],'source_url':candidate['source_url'],'features':candidate['features'],
                           'distance':score,'distance_components':p,'review_status':candidate['review_status']})
    ranked.sort(key=lambda c:(c['distance'],c['id']))
    # One example per source round avoids adjacent deaths dominating retrieval.
    result=[];seen=set()
    for item in ranked:
        key=(item['match_id'],item['round'])
        if key not in seen: result.append(item);seen.add(key)
        if len(result)>=max(1,min(int(limit),5)): break
    return {'query_id':identifier,'matches':result,'status':'candidates_not_validated_analogies' if result else 'no_comparable_case',
            'method':'hard state filters + nearest neighbours over pre-event situation vectors (position, time, equipment, teammate spacing), computed locally',
            'limits':'All examples selected before deaths; no outcome-based ranking; no proof of optimal actions.'}


def shortlist(db, match_id, limit=3):
    cases=[json.loads(r[0]) for r in db.execute('SELECT payload FROM cases WHERE match_id=?',(match_id,))]
    # Prioritize isolation candidates, but only one per round. This is not a mistake score.
    # A last survivor cannot wait for a living teammate: exclude clutches from this task.
    cases=[c for c in cases if c['features']['own_alive']>=2 and c['features']['nearest_teammate'] is not None]
    cases.sort(key=lambda c:(-c['features']['nearest_teammate'],c['id']))
    selected=[];rounds=set()
    for c in cases:
        if c['round'] in rounds:continue
        rounds.add(c['round'])
        selected.append({'id':c['id'],'round':c['round'],'tick':c['tick'],'features':c['features'],
                         'reason':'large Euclidean teammate distance before death; investigate, do not label error'})
        if len(selected)>=max(1,min(int(limit),10)):break
    return selected


def knowledge_texts(db, map_name=None):
    rows=db.execute('SELECT title,body FROM knowledge WHERE reviewed=1'+(' AND map=?' if map_name else '')+' ORDER BY id',(map_name,) if map_name else ()).fetchall()
    return [t+'\n'+b for t,b in rows]


def knowledge_search(db, query, map_name='de_dust2'):
    """Hybrid search over reviewed notes only: full-text rank blended with embedding similarity."""
    # Quote words as literals: source strings never become FTS operators.
    tokens=query.split()[:12]
    if not tokens:return []
    expression=' OR '.join('"'+t.replace('"','""')+'"' for t in tokens)
    lexical=[dict(r) for r in db.execute('''SELECT k.* FROM knowledge_fts f JOIN knowledge k ON k.id=f.id
       WHERE knowledge_fts MATCH ? AND k.map=? AND k.reviewed=1 ORDER BY rank LIMIT 50''',(expression,map_name))]
    from .embeddings import semantic,hybrid
    rows=[dict(r) for r in db.execute('SELECT * FROM knowledge WHERE map=? AND reviewed=1 ORDER BY id',(map_name,))]
    sims,info=semantic('reviewed_notes',[r['title']+'\n'+r['body'] for r in rows],query)
    if sims is None:return lexical[:5]
    rank={r['id']:i for i,r in enumerate(lexical)}
    keyword=[1/(1+rank[r['id']]) if r['id'] in rank else 0 for r in rows]
    scored=[(score,r,float(s)) for score,r,s in zip(hybrid(keyword,sims,info),rows,sims) if r['id'] in rank or s>=info['floor']]
    scored.sort(key=lambda x:(-x[0],x[1]['id']))
    return [{**r,'similarity':round(s,4)} for _,r,s in scored[:5]]


def import_knowledge(db, records):
    """Human-curated source notes; never promote autogenerated interpretations."""
    from urllib.parse import urlsplit
    for item in records:
        if item['kind'] not in ('utility','tactic') or item['map']!='de_dust2':
            raise ValueError('Only Dust2 utility/tactic notes are supported in this pilot')
        if urlsplit(item['source']).scheme!='https' or not item.get('version'):
            raise ValueError('Source URL and map/version context are required')
        if not item.get('title') or not item.get('body') or len(item['body'])>6000:
            raise ValueError('A bounded evidence note is required')
        if not isinstance(item.get('reviewed'),bool):raise ValueError('Explicit human review status required')
    with db:
        for item in records:
            db.execute('INSERT OR REPLACE INTO knowledge VALUES(?,?,?,?,?,?,?,?)',
                       tuple(item[k] for k in ('id','kind','map','title','body','source','reviewed','version')))
            db.execute('DELETE FROM knowledge_fts WHERE id=?',(item['id'],))
            db.execute('INSERT INTO knowledge_fts VALUES(?,?,?)',(item['id'],item['title'],item['body']))


def evaluate(db, directory):
    directory.mkdir(parents=True,exist_ok=True)
    queries=[json.loads(r[0]) for r in db.execute("SELECT payload FROM cases WHERE split='test' ORDER BY match_id,id")]
    eligible=[c for c in queries if c['features']['own_alive']>=2]
    found=[(c,retrieve(db,c['id'])) for c in eligible]
    for c,result in found:
        assert all(r['match_id']!=c['match_id'] for r in result['matches'])
    report={'reference_cases':db.execute("SELECT count(*) FROM cases WHERE split='train'").fetchone()[0],
            'evaluation_cases':len(queries),'support_queries':len(eligible),
            'queries_with_references':sum(bool(r['matches']) for _,r in found),
            'knowledge_notes':db.execute('SELECT count(*) FROM knowledge WHERE reviewed=1').fetchone()[0],
            'quality_validated':False,'limitation':'Retrieval coverage only. Human relevance and advice quality not evaluated. Previous experimental matches reused.'}
    (directory/'retrieval-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    # Spread a small annotation queue across evaluation matches; leave judgments blank.
    groups={}
    for c,result in found:
        if result['matches']:groups.setdefault(c['match_id'],[]).append((c,result['matches'][0]))
    selected=[]
    while len(selected)<20 and any(groups.values()):
        for group in groups.values():
            if group and len(selected)<20:selected.append(group.pop(0))
    with (directory/'human-review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['query_id','reference_id','same_tactical_problem','important_differences','evidence_sufficient','reviewer_notes'])
        for c,r in selected:writer.writerow([c['id'],r['id'],'','','',''])
    return report


def build(manifest_path):
    manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    DEFAULT_DB.parent.mkdir(parents=True,exist_ok=True)
    with connect() as db:
        initialize(db)
        for entry in manifest['demos']:
            source=(manifest_path.parent/entry['path']).resolve()
            cache=DEFAULT_DB.parent/(entry['match_id']+'.json')
            # Cached extraction bound to demo bytes AND extractor version.
            extractor=ROOT/'experiments/situation/extract_cases.cjs'
            fingerprint=hashlib.sha256(source.read_bytes()).hexdigest()+hashlib.sha256(extractor.read_bytes()).hexdigest()
            stamp=cache.with_suffix('.fingerprint')
            if not cache.exists() or not stamp.exists() or stamp.read_text()!=fingerprint:
                subprocess.run(['node',str(extractor),str(source),str(cache)],cwd=ROOT,check=True)
                stamp.write_text(fingerprint)
            ingest(db,json.loads(cache.read_text()),entry)
        counts=[dict(r) for r in db.execute('SELECT split,count(*) AS cases,count(DISTINCT match_id) AS matches FROM cases GROUP BY split')]
    return counts


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['build','inspect','evaluate','import-knowledge']);p.add_argument('--file',type=Path);args=p.parse_args()
    if args.action=='build':result=build(ROOT/'data/situation/manifest.json')
    else:
        with connect() as db:
            if args.action=='evaluate':result=evaluate(db,ROOT/'outputs/casebook')
            elif args.action=='import-knowledge':
                if not args.file:p.error('--file is required')
                records=json.loads(args.file.read_text(encoding='utf-8-sig'));import_knowledge(db,records);result={'imported':len(records)}
            else:result=[dict(r) for r in db.execute('SELECT split,count(*) AS cases FROM cases GROUP BY split')]
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
