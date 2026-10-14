"""Demo role is explicit provenance metadata, never guessed from a filename."""
import json, threading
from urllib.parse import urlsplit
from . import demo_review as dr
from .casebook import ROOT
from .lineup_catalog import write_json
LOCK=threading.RLock();HASHES={}

def validate(kind,source=''):
    if kind not in ('player','professional','unknown'):raise ValueError('请选择普通玩家或职业比赛类型')
    source=source.strip()
    if kind=='professional':
        p=urlsplit(source)
        if p.scheme not in ('https','http') or not p.hostname or p.username or p.password or len(source)>1000:raise ValueError('职业比赛请提供公开比赛来源链接')
    return {'kind':kind,'source_url':source if kind=='professional' else None,'basis':'user_declared','verified':False}

def set_identity(mid,kind,source=''):
    info=validate(kind,source);dr.state(mid)
    with LOCK:write_json(dr.folder(mid)/'identity.json',info)
    return info

def get(mid):
    state=dr.state(mid);p=dr.folder(mid)/'identity.json'
    if p.exists():return json.loads(p.read_text(encoding='utf-8'))
    # Existing curated archive manifest: require content hash equality, not name equality.
    manifest=ROOT/'data/situation/manifest.json'
    if state.get('sha256') and manifest.exists():
        for row in json.loads(manifest.read_text(encoding='utf-8'))['demos']:
            if row.get('professional') is not True:continue
            f=(manifest.parent/row['path']).resolve()
            if not f.is_relative_to((ROOT/'data/demos').resolve()) or not f.exists():continue
            stamp=(str(f),f.stat().st_mtime_ns,f.stat().st_size)
            with LOCK:
                if stamp not in HASHES:HASHES[stamp]=_disk_hashes().get('|'.join(map(str,stamp))) or dr.hash_file(f);_remember(stamp,HASHES[stamp])
                sha=HASHES[stamp]
            if sha==state['sha256']:
                return {'kind':'professional','source_url':row['source_url'],'basis':'curated_manifest_and_sha256','verified':True,'match_id':row.get('match_id'),'date':row.get('date')}
    return {'kind':'unknown','source_url':None,'basis':'unclassified','verified':False}

def _disk_hashes():
    # Persisted only as a speed-up: keyed by path+mtime+size, so any change to the demo forces a fresh SHA256.
    p=dr.BASE/'.demo-hash-cache.json'
    try:return json.loads(p.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def _remember(stamp,sha):
    p=dr.BASE/'.demo-hash-cache.json';data=_disk_hashes();key='|'.join(map(str,stamp))
    if data.get(key)!=sha:
        data[key]=sha
        try:write_json(p,data)
        except OSError:pass

def library():return [{**s,'identity':get(s['id'])} for s in dr.library()]
