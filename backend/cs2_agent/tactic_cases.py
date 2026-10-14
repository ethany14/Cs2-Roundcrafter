"""Local, provenance-preserving retrieval of completed demo interpretations."""
import hashlib,json,re,threading
from . import demo_review as dr
from .lineup_catalog import write_json,retrieve_cards
LOCK=threading.RLock()

def terms(text):
    text=text.lower()
    for a,b in {'斜坡':'ramp','天堂':'heaven','外场':'outside','消毒间':'decon','地道':'tunnels','b洞':'tunnel','a小':'catwalk','烟':'smoke','闪':'flash','火':'fire'}.items():text=text.replace(a,a+' '+b+' ')
    return set(re.findall('[a-z0-9]+',text)+[s[i:i+2] for s in re.findall('[\u4e00-\u9fff]+',text) for i in range(len(s)-1)])

def catalog():
    with LOCK:
        files=sorted(p for p in dr.BASE.glob('*/coach-*.json') if re.fullmatch(r'coach-\d+\.json',p.name))
        stamp=[(str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in files]
        fingerprint=hashlib.sha256(json.dumps(stamp).encode()).hexdigest();out=dr.BASE/'tactic-cases.json'
        if out.exists():
            old=json.loads(out.read_text(encoding='utf-8'))
            if old.get('fingerprint')==fingerprint:return old
        cases=[];seen=set()
        for p in files:
            try:
                s=json.loads(p.read_text(encoding='utf-8'));packet=s['packet'];report=s.get('result')
                if s.get('status')!='completed' or not report:continue
                source=dr.state(p.parent.name);ev={e['id']:e for e in packet['evidence']}
                for c in report['claims']:
                    refs=c['evidence_ids']
                    if not refs or any(i not in ev for i in refs) or not 0<=c['start']<c['end']<=packet['duration']:continue
                    identity=json.dumps([source.get('sha256',p.parent.name),packet['round'],c['observed_title'],c['interpretation'],refs],ensure_ascii=False)
                    dedup=hashlib.sha256(identity.encode()).hexdigest()
                    if dedup in seen:continue
                    seen.add(dedup);cid=hashlib.sha256((p.parent.name+identity).encode()).hexdigest()[:24]
                    cases.append(dict(id=cid,match=p.parent.name,round=packet['round'],map=packet['map'],side=c.get('side','T'),title=c['observed_title'],interpretation=c['interpretation'],classification='model_inference',confidence=c.get('confidence','unknown'),players=c['players'],start=c['start'],end=c['end'],evidence=[ev[i] for i in refs],source={'artifact':str(p.relative_to(dr.BASE)),'demo_sha256':source.get('sha256'),'analysis_version':s.get('version')},replay_url=f"/demos?match={p.parent.name}&round={packet['round']}&case={cid}"))
            except (OSError,ValueError,KeyError,TypeError):continue
        value={'version':1,'fingerprint':fingerprint,'cases':cases};write_json(out,value);return value

def get(cid):
    if not isinstance(cid,str) or not re.fullmatch('[0-9a-f]{24}',cid):raise ValueError('无效案例编号')
    case=next((c for c in catalog()['cases'] if c['id']==cid),None)
    if not case:raise ValueError('案例已更新或不存在，请重新检索')
    return case

def search(query='',map_name='',side='',limit=30):
    if len(query)>200 or map_name not in ('','de_nuke','de_dust2') or side not in ('','T','CT','both'):raise ValueError('无效检索条件')
    wanted=terms(query);ranked=[]
    for c in catalog()['cases']:
        if map_name and c['map']!=map_name:continue
        if side and c['side'] not in (side,'both'):continue
        title=terms(c['title']);body=terms(c['interpretation']+' '+' '.join(e['text'] for e in c['evidence']))
        score=3*len(wanted&title)+len(wanted&body)
        if wanted and not score:continue
        ranked.append((score,c))
    ranked.sort(key=lambda row:(-row[0],row[1]['map'],row[1]['round'],row[1]['id']))
    return {'total':len(ranked),'method':'local_alias_and_lexical_overlap','cases':[{k:v for k,v in c.items() if k!='evidence'}|{'evidence_count':len(c['evidence']),'retrieval_score':score} for score,c in ranked[:max(1,min(limit,50))]]}

def learning(cid):
    c=get(cid);r=dr.round_data(c['match'],c['round']);kinds={'smokegrenade_detonate':'smoke','flashbang_detonate':'flash','hegrenade_detonate':'he','inferno_startburn':'fire'}
    needs=[]
    for e in r['events']:
        if e['type'] not in kinds or not c['start']<=e['seconds']<=c['end'] or (c['side']!='both' and e['side']!=c['side']):continue
        query=f"{c['map'].removeprefix('de_')} {kinds[e['type']]} {c['title']} 教学"[:250]
        cards=[x for x in retrieve_cards(query,c['map']) if x.get('side') in (None,e['side'])]
        needs.append({'event_id':e['id'],'actor':e['actor'],'side':e['side'],'seconds':e['seconds'],'kind':kinds[e['type']],'classification':'demo_observation','research_query':query,'candidates':[{'id':x['id'],'title':x['title'],'source_url':x['source_url'],'video_url':x.get('video_url'),'classification':'unverified_teaching_candidate'} for x in cards], 'unknown':['投掷起点、瞄点和按键动作未由此事件确定','本地候选未核对战术适配或游戏实投']})
    return {'case':c,'players':[{'id':pid,'classification':'demo_observation','facts':[e['text'] for e in c['evidence'] if pid in e['players']]} for pid in c['players']], 'utility_needs':needs,'unknown':['行动记录是复盘依据，不等于已验证的五人执行方案','模型推断不能作为教学来源事实','缺少原始教学时不生成坐标、瞄点或投掷动作']}
