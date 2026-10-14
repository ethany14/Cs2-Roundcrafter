"""Local demo ingestion, observed round evidence, and conservative tactic candidates."""
import hashlib,json,math,re,shutil,subprocess,threading,time,uuid
from pathlib import Path
from .casebook import ROOT
from .lineup_catalog import write_json

BASE=ROOT/'outputs/demo-review'
LOCK=threading.Lock();JOBS={};MAX_BYTES=1024*1024*1024;TIMEOUT=240
UTILITY={'smokegrenade_detonate','flashbang_detonate','hegrenade_detonate','inferno_startburn'}

def folder(identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('无效比赛编号')
    return BASE/identifier

def snapshot(round_,seconds):
    frames=round_['frames']
    return min(frames,key=lambda f:abs(f['seconds']-seconds)) if frames else {'tick':round_['start_tick'],'seconds':0,'players':[]}

def site(area):
    if not area:return None
    a=area.lower().replace(' ','')
    return 'A' if a in ('bombsitea','asite') else 'B' if a in ('bombsiteb','bsite') else None

def dist(a,b):return math.dist(a,b)

def analyze_round(r):
    cards=[]
    if not r['frames']:return cards
    plant=next((e for e in r['events'] if e['type']=='bomb_planted'),None)
    deaths=[e for e in r['events'] if e['type']=='player_death']
    for side in ('T','CT'):
        initial=snapshot(r,2);opening=snapshot(r,min(20,r['duration']/3))
        team=[p for p in initial['players'] if p['side']==side];utilities=[e for e in r['events'] if e['type'] in UTILITY and e['side']==side]
        if not team:continue
        entry=None;objective=None
        for frame in r['frames']:
            for target in ('A','B'):
                present=[p for p in frame['players'] if p['side']==side and p['alive'] and site(p['area'])==target]
                if len(present)>=3:entry=frame;objective=target;break
            if entry:break
        if plant:
            pf=snapshot(r,plant['seconds']);planter=next((p for p in pf['players'] if p['id']==plant['actor']),None)
            if side=='CT' or not entry:objective=site(planter['area']) if planter and site(planter['area']) else objective
        focus=entry['seconds'] if side=='T' and entry else plant['seconds'] if plant else deaths[0]['seconds'] if deaths else r['duration']/2
        focus=max(0,min(r['duration'],focus));burst=[e for e in utilities if focus-10<=e['seconds']<=focus+3]
        before=snapshot(r,max(0,focus-8));approaches=sorted({p['area'] for p in before['players'] if p['side']==side and p['alive'] and p['area'] and not site(p['area']) and 'Spawn' not in p['area']})
        family='default';title='分散控图 / 常规推进（候选）' if side=='T' else '开局防守布置（候选）'
        inference=[]
        if side=='T' and entry:
            if focus<=25:family='fast_entry';title=f'{objective or "目标"} 区快速集中进入（候选）';inference.append('至少三名存活 T 在冻结结束后 25 秒内进入同一包点区域。')
            elif len(burst)>=3:family='utility_entry';title=f'{objective or "目标"} 区道具配合集合（候选）';inference.append('至少三名 T 集中进入包点，前 10 秒至后 3 秒出现至少三次己方道具事件。')
            else:family='group_entry';title=f'{objective or "目标"} 区集中推进（候选）';inference.append('同帧至少三名存活 T 位于同一包点区域。')
        elif side=='T':inference.append('未达到集中进入规则；保留观察到的开局分布与路线，不强行命名进攻战术。')
        if side=='CT' and plant and plant['position']:
            a=snapshot(r,plant['seconds']);b=snapshot(r,min(r['duration']-.1,plant['seconds']+10));moved=[]
            for p in a['players']:
                q=next((x for x in b['players'] if x['id']==p['id'] and x['alive']),None)
                if p['side']=='CT' and p['alive'] and q and dist(p['position'],plant['position'])-dist(q['position'],plant['position'])>=384:moved.append(p['id'])
            if len(moved)>=2:family='retake_approach';title=f'{objective or "下包点"} 区多人接近回防（候选）';inference.append('下包后 10 秒窗口内至少两名存活 CT 与下包点距离减少 384 单位；并非确认指挥意图。')
        ticks=sorted(set([r['start_tick'],snapshot(r,max(0,focus-8))['tick'],snapshot(r,focus)['tick'],snapshot(r,min(r['duration']-.1,focus+12))['tick']]))
        while len(ticks)<4:ticks.append(ticks[-1])
        roles=[]
        for p in team:
            route=[]
            for frame in r['frames'][::8]:
                q=next((x for x in frame['players'] if x['id']==p['id']),None)
                if q and q['area'] and (not route or route[-1]['area']!=q['area']):route.append({'area':q['area'],'tick':frame['tick'],'seconds':frame['seconds']})
            roles.append({'player':p['id'],'opening_inventory':p['inventory'],'route':route[:30],
                          'utility_events':[e['id'] for e in utilities if e['actor']==p['id']]})
        facts=[{'kind':'observed','tick':opening['tick'],'text':'开局区域：'+'；'.join(f"{p['id']} {p['area'] or '未知区域'}" for p in opening['players'] if p['side']==side)},
               {'kind':'observed','tick':snapshot(r,focus)['tick'],'text':f'本回合己方道具生效事件 {len(utilities)} 次，焦点窗口内 {len(burst)} 次。'}]
        if plant:facts.append({'kind':'observed','event_id':plant['id'],'tick':plant['tick'],'text':f"{plant['seconds']:.2f} 秒发生下包事件。"})
        cards.append({'id':f"r{r['number']}-{side}",'round':r['number'],'side':side,'title':title,'family':family,'objective':objective,
            'focus_seconds':focus,'phase_ticks':ticks[:4],'facts':facts,'inferences':inference,'approach_regions':approaches,
            'roles':roles,'event_ids':[e['id'] for e in utilities],
            'unknown':['没有队内语音，不能确定预先战术、临场指挥、假打或诱骗意图','观察到的结果不构成战术因果效果或胜率','逐人职责仅还原实际路径与道具，不猜测指挥分工'],
            'rule_version':'observed-tactics-v1','evidence_scope':'demo_observations_with_explicit_rules'})
    return cards

def build(directory):
    obs=json.loads((directory/'observations.json').read_text(encoding='utf-8'));cards=[]
    for row in obs['rounds']:
        r=json.loads((directory/f"round-{row['number']}.json").read_text(encoding='utf-8'));cards+=analyze_round(r)
    groups={}
    for c in cards:
        k=(c['side'],c['family'],c['objective']);groups.setdefault(k,[]).append(c['id'])
    result={**obs,'tactics':cards,'patterns':[{'side':k[0],'family':k[1],'objective':k[2],'cards':v,'occurrences':len(v)} for k,v in groups.items()],
      'analysis':{'method':'deterministic_observation_rules','model_calls':0,'network_calls':0,
       'note':'自动提取战术候选，不是战队真实战术命名或意图识别。原有 Eregion 保留；此流程复用解析器和证据数据，不新建聊天机器人。'}}
    write_json(directory/'result.json',result);return result

def samples():return [{'name':p.name,'bytes':p.stat().st_size} for p in sorted((ROOT/'data/demos').glob('*.dem'))]

def _state(identifier,**kwargs):
    d=folder(identifier);state=json.loads((d/'state.json').read_text(encoding='utf-8'));state.update(kwargs);write_json(d/'state.json',state)

def allocate(name):
    if not LOCK.acquire(False):raise RuntimeError('已有 demo 正在上传或解析')
    try:
        identifier=uuid.uuid4().hex;d=folder(identifier);d.mkdir(parents=True)
        write_json(d/'state.json',{'id':identifier,'name':name[:150],'status':'uploading','stage':'正在保存 demo','created_at':time.time(),'model_calls':0,'network_calls':0})
        JOBS[identifier]=threading.Event();return identifier,d
    except Exception:LOCK.release();raise


def launch(identifier,path,sha):
    def worker():
        d=folder(identifier);process=None;started=time.monotonic()
        try:
            _state(identifier,status='parsing',stage='正在解析比赛',sha256=sha)
            for prior in BASE.glob('*/state.json'):
                if JOBS[identifier].is_set():_state(identifier,status='cancelled',stage='已取消');return
                if prior.parent==d:continue
                s=json.loads(prior.read_text(encoding='utf-8'))
                if s.get('status')=='completed' and s.get('sha256')==sha and s.get('pipeline_version')==1:
                    for f in prior.parent.glob('*.json'):
                        if f.name in ('observations.json','result.json') or re.fullmatch(r'round-\d+\.json',f.name):shutil.copy2(f,d/f.name)
                    _state(identifier,status='completed',stage='复用相同 demo 的解析结果',cache_hit=True,pipeline_version=1);return
            with (d/'parser.log').open('wb') as log:
                process=subprocess.Popen(['node',str(ROOT/'experiments/knowledge/extract_match.cjs'),str(path),str(d)],cwd=ROOT,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                while process.poll() is None:
                    if JOBS[identifier].wait(.25):process.kill();process.wait();_state(identifier,status='cancelled',stage='已取消');return
                    if time.monotonic()-started>TIMEOUT:process.kill();process.wait();_state(identifier,status='budget_exhausted',stage='解析超出 240 秒预算');return
                if process.returncode:raise ValueError('parser_failed')
            _state(identifier,status='analyzing',stage='正在整理逐回合路线与战术候选')
            result=build(d)
            if JOBS[identifier].is_set():_state(identifier,status='cancelled',stage='已取消');return
            _state(identifier,status='completed',stage='比赛解析完成',map=result['map'],rounds=len(result['rounds']),tactics=len(result['tactics']),elapsed_seconds=round(time.monotonic()-started,2),pipeline_version=1)
            try:  # smooth replay + economy/trajectory supplement, in the background; replay falls back to 4 Hz until ready
                from .demo_workbench import start_supplements
                start_supplements([identifier])
            except (RuntimeError,ImportError):pass
        except Exception as exc:_state(identifier,status='failed',stage='解析失败：格式不兼容、数据不完整或本地解析器异常',error_type=type(exc).__name__)
        finally:
            if process is not None and process.poll() is None:process.kill();process.wait()
            LOCK.release()
    threading.Thread(target=worker,daemon=True,name='demo-review').start()

def import_local(path,kind='player'):
    """Import a demo the user downloaded in CS2 (watched replays folder). Parsed in place, never copied."""
    path=Path(path)
    if path.suffix.lower()!='.dem' or not path.is_file():raise ValueError('不是 .dem 文件')
    with path.open('rb') as f:
        if f.read(8)!=b'PBDEMS2\x00':raise ValueError('不是 CS2 demo 文件')
    sha=hash_file(path)
    for s in library():
        if s.get('sha256')==sha and s['status']=='completed':return {'id':s['id'],'duplicate':True}
    identifier,d=allocate(path.name)
    try:
        _state(identifier,source_path=str(path),played_at=path.stat().st_mtime,origin='replays_folder')
        from .demo_identity import set_identity
        set_identity(identifier,kind)
        launch(identifier,path,sha)
    except Exception:LOCK.release();raise
    return {'id':identifier}

def hash_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def start_sample(raw):
    if not isinstance(raw,dict) or set(raw)!={'sample'} or raw['sample'] not in {x['name'] for x in samples()}:raise ValueError('请选择已有 demo')
    path=ROOT/'data/demos'/raw['sample'];identifier,d=allocate(path.name)
    try:launch(identifier,path,hash_file(path))
    except Exception:LOCK.release();raise
    return {'id':identifier}

def upload(stream,length,name):
    if type(length) is not int or not 8<=length<=MAX_BYTES:raise ValueError('demo 大小必须在 8 字节至 1 GiB 之间')
    if not isinstance(name,str) or not name.lower().endswith('.dem'):raise ValueError('请上传未压缩 .dem 文件')
    identifier,d=allocate(Path(name.replace('\\','/')).name);h=hashlib.sha256()
    try:
        with (d/'upload.dem').open('xb') as f:
            remaining=length;first=True
            while remaining:
                chunk=stream.read(min(1024*1024,remaining))
                if not chunk:raise ValueError('上传中断')
                if first and chunk[:8]!=b'PBDEMS2\x00':raise ValueError('不是 CS2 demo 文件')
                first=False;f.write(chunk);h.update(chunk);remaining-=len(chunk)
        launch(identifier,d/'upload.dem',h.hexdigest());return {'id':identifier}
    except Exception:
        _state(identifier,status='failed',stage='上传失败或文件格式无效');LOCK.release();raise

def state(identifier):
    d=folder(identifier)
    for attempt in range(4):
        try:s=json.loads((d/'state.json').read_text(encoding='utf-8'));break
        except OSError:
            if attempt==3:raise
            time.sleep(.01)
    if s['status'] in ('uploading','parsing','analyzing') and identifier not in JOBS:s.update(status='interrupted',stage='服务重启中断，可重新导入原文件')
    if s['status']=='parsing' and (d/'parser-progress.json').exists():
        try:s['stage']=json.loads((d/'parser-progress.json').read_text(encoding='utf-8'))['stage']
        except (ValueError,OSError):pass
    return s

def library():
    return sorted([state(p.parent.name) for p in BASE.glob('*/state.json') if re.fullmatch('[0-9a-f]{32}',p.parent.name)],key=lambda x:x['created_at'],reverse=True)

def result(identifier):
    if state(identifier)['status']!='completed':raise ValueError('比赛尚未完成解析')
    return json.loads((folder(identifier)/'result.json').read_text(encoding='utf-8'))

def round_data(identifier,number):
    data=result(identifier)
    if number not in [r['number'] for r in data['rounds']]:raise ValueError('回合不存在')
    return json.loads((folder(identifier)/f'round-{number}.json').read_text(encoding='utf-8'))

def cancel(identifier):
    s=state(identifier)
    if identifier in JOBS and s['status'] in ('uploading','parsing','analyzing'):JOBS[identifier].set()
    return {'id':identifier,'status':s['status']}

BOARD_ITEMS={'arrow','pen','text','smoke','flash','fire','he'}

def validate_steps(steps):
    """Tactic-board stages: shared by per-match boards and the tactic room. Plans, never match evidence."""
    if not isinstance(steps,list) or not 1<=len(steps)<=8:raise ValueError('最多八个阶段')
    for s in steps:
        if not isinstance(s,dict) or not isinstance(s.get('players'),list) or len(s['players'])>32:raise ValueError('阶段无效')
        if not isinstance(s.get('note',''),str) or len(s.get('note',''))>2000:raise ValueError('说明过长')
        if 'dur' in s and (type(s['dur']) not in (int,float) or not .5<=s['dur']<=30):raise ValueError('阶段时长需 0.5–30 秒')
        for player in s['players']:
            if not isinstance(player,dict) or player.get('side') not in ('T','CT') or not isinstance(player.get('id'),str) or len(player['id'])>40:raise ValueError('玩家无效')
            pos=player.get('position')
            if not isinstance(pos,list) or len(pos)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>100000 for v in pos):raise ValueError('坐标无效')
        lines=s.get('lines',[])
        if not isinstance(lines,list) or len(lines)>500:raise ValueError('标注过多')
        for line in lines:
            if not isinstance(line,list) or len(line)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in line):raise ValueError('标注无效')
        items=s.get('items',[])
        if not isinstance(items,list) or len(items)>300:raise ValueError('标注过多')
        for it in items:
            if not isinstance(it,dict) or it.get('type') not in BOARD_ITEMS or set(it)-{'type','pts','color','text','dash','floor'} or it.get('floor','upper') not in ('upper','lower'):raise ValueError('标注无效')
            pts=it.get('pts')
            if not isinstance(pts,list) or not 1<=len(pts)<=500 or any(not isinstance(q,list) or len(q)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>5000 for v in q) for q in pts):raise ValueError('标注无效')
            if not re.fullmatch(r'#[0-9a-fA-F]{3,8}',str(it.get('color','#fff'))) or not isinstance(it.get('text',''),str) or len(it.get('text',''))>80:raise ValueError('标注无效')
    if len(json.dumps(steps,allow_nan=False))>500000:raise ValueError('战术板过大')
    return steps

def save_board(raw):
    if not isinstance(raw,dict) or set(raw)!={'match','name','steps'}:raise ValueError('无效战术板')
    result(raw['match'])
    if not isinstance(raw['name'],str) or not 1<=len(raw['name'])<=120:raise ValueError('战术板名称无效')
    validate_steps(raw['steps'])
    identifier=uuid.uuid4().hex;d=folder(raw['match'])/'boards';d.mkdir(exist_ok=True)
    write_json(d/(identifier+'.json'),{**raw,'id':identifier,'kind':'user_edited_plan_not_demo_observation'});return {'id':identifier}

def boards(identifier):
    result(identifier)
    return [json.loads(p.read_text(encoding='utf-8')) for p in (folder(identifier)/'boards').glob('*.json')]
