"""Tactic room: the user's own tactic library, independent of any single match.
Plans are user content, never demo evidence. Older per-match boards are listed read-only and can be copied in."""
import json,re,time,uuid
from . import demo_review as dr
from .casebook import ROOT
from .lineup_catalog import write_json

BASE=ROOT/'data/tactics-room';MAPS=('de_dust2','de_mirage','de_inferno','de_nuke','de_ancient','de_anubis','de_cache')  # maps with a local radar

def _path(tid):
    if not isinstance(tid,str) or not re.fullmatch('[0-9a-f]{32}',tid):raise ValueError('无效战术编号')
    return BASE/(tid+'.json')

def _clean(raw):
    if not isinstance(raw,dict):raise ValueError('无效战术')
    name=str(raw.get('name','')).strip()
    if not 1<=len(name)<=120:raise ValueError('战术名称需 1–120 字')
    if raw.get('map') not in MAPS:raise ValueError('不支持的地图')
    tags=raw.get('tags',[])
    if not isinstance(tags,list) or len(tags)>12 or any(not isinstance(t,str) or not 1<=len(t.strip())<=24 for t in tags):raise ValueError('标签无效（最多 12 个，每个 ≤24 字）')
    folder=str(raw.get('folder','') or '').strip()
    if len(folder)>40:raise ValueError('文件夹名过长')
    side=raw.get('side','any')
    if side not in ('T','CT','any'):raise ValueError('阵营无效')
    src=raw.get('source') or None
    if src is not None:
        if not isinstance(src,dict) or set(src)-{'match','round','tick'}:raise ValueError('来源无效')
        if src.get('match') is not None:dr.folder(src['match'])
    return {'name':name,'map':raw['map'],'tags':sorted({t.strip() for t in tags}),'folder':folder,'side':side,'notes':str(raw.get('notes',''))[:2000],
            'steps':dr.validate_steps(raw.get('steps')),'source':src}

def save(raw):
    tid=raw.get('id') if isinstance(raw,dict) else None;now=time.time()
    if tid:
        old=get(tid)  # fields not sent keep their saved values
        data={**old,**_clean({**{k:old.get(k) for k in ('name','map','tags','folder','side','notes','steps','source')},**raw}),'updated':now}
    else:data=_clean(raw)
    if not tid:
        tid=uuid.uuid4().hex;data={**data,'id':tid,'created':now,'updated':now,'kind':'user_tactic_plan'}
    BASE.mkdir(parents=True,exist_ok=True);write_json(_path(tid),data);return summary(data)

def get(tid):
    p=_path(tid)
    if not p.exists():raise ValueError('战术不存在')
    return json.loads(p.read_text(encoding='utf-8'))

def delete(tid):
    p=_path(tid)
    if p.exists():p.unlink()
    return {'deleted':tid}

def duplicate(tid):
    t=get(tid);return save({**{k:t[k] for k in ('map','tags','folder','side','notes','steps','source')},'name':(t['name']+' 副本')[:120]})

def summary(t):
    return {k:t.get(k) for k in ('id','name','map','tags','folder','side','source','created','updated')}|{'stages':len(t['steps']),'players':len(t['steps'][0]['players']) if t['steps'] else 0,
            'items':sum(len(s.get('items',[]))+len(s.get('lines',[])) for s in t['steps'])}

def listing(map_=None,q='',tag=None,folder=None):
    rows=[]
    for p in sorted(BASE.glob('*.json')) if BASE.exists() else []:
        try:t=json.loads(p.read_text(encoding='utf-8'))
        except (OSError,ValueError):continue
        if map_ and t['map']!=map_:continue
        if tag and tag not in t.get('tags',[]):continue
        if folder is not None and folder!='' and t.get('folder','')!=folder:continue
        if q and q.lower() not in (t['name']+' '+' '.join(t.get('tags',[]))+' '+t.get('notes','')).lower():continue
        rows.append(summary(t))
    rows.sort(key=lambda r:-(r['updated'] or 0))
    legacy=[]
    for b in dr.BASE.glob('*/boards/*.json'):
        try:raw=json.loads(b.read_text(encoding='utf-8'));m=json.loads((b.parent.parent/'result.json').read_text(encoding='utf-8'))['map']
        except (OSError,ValueError,KeyError):continue
        if map_ and m!=map_:continue
        legacy.append({'id':raw['id'],'match':b.parent.parent.name,'name':raw['name'],'map':m,'stages':len(raw['steps'])})
    all_rows=[json.loads(p.read_text(encoding='utf-8')) for p in BASE.glob('*.json')] if BASE.exists() else []
    return {'tactics':rows,'legacy':legacy,'tags':sorted({t for r in all_rows for t in r.get('tags',[])}),'folders':sorted({r.get('folder','') for r in all_rows if r.get('folder')})}

def import_legacy(match,board_id):
    if not re.fullmatch('[0-9a-f]{32}',str(board_id)):raise ValueError('无效战术板')
    b=json.loads((dr.folder(match)/'boards'/(board_id+'.json')).read_text(encoding='utf-8'))
    m=dr.result(match)['map'];first=b['steps'][0]
    return save({'name':b['name'],'map':m,'tags':['导入'],'steps':b['steps'],'source':{'match':match,'round':first.get('source_round'),'tick':first.get('source_tick')}})
