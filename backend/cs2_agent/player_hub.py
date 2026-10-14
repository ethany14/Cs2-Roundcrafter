"""Player hub: linked Steam account, automatic match import, career statistics.

Linking: Steam OpenID 2.0 (the user signs in on steamcommunity.com; we only receive and verify the SteamID64),
or a manual SteamID marked unverified. Secrets (Steam Web API key, match-history auth code) live in
data/account/secrets.json and are never returned to the browser.

Automatic tracking has two honest parts:
  1. the CS2 `replays` folder is watched; every demo the user downloads in-game is imported and parsed;
  2. with the user's own Web API key + match auth code, Valve's share-code API lists new matches.
     Valve does not expose matchmaking demo downloads without the game client, so those matches are
     listed (with decoded match id) until their demo appears in the replays folder.
"""
import json,re,secrets,threading,time,urllib.parse
from pathlib import Path
import httpx
from . import demo_review as dr
from .casebook import ROOT
from .lineup_catalog import write_json

BASE=ROOT/'data/account';ACCOUNT=BASE/'account.json';SECRETS=BASE/'secrets.json';SETTINGS=BASE/'settings.json';IMPORTS=BASE/'imports.json';CODES=BASE/'sharecodes.json'
DEFAULT_REPLAYS=r'C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\replays'
OPENID='https://steamcommunity.com/openid/login';ORIGIN='http://127.0.0.1:8790'
LOCK=threading.RLock();PENDING={};WATCH={'thread':None,'last_scan':None,'last_error':None,'imported':0}

def _read(p,default):
    try:return json.loads(p.read_text(encoding='utf-8'))
    except (OSError,ValueError):return default
def _write(p,data):BASE.mkdir(parents=True,exist_ok=True);write_json(p,data)

# ---------------------------------------------------------------- account & settings
def valid_steamid(s):
    s=str(s or '').strip();m=re.search(r'steamcommunity\.com/profiles/(\d{17})',s)
    if m:s=m.group(1)
    if not re.fullmatch(r'7656119\d{10}',s):raise ValueError('请输入 17 位 SteamID64（7656119…），或 steamcommunity.com/profiles/ 链接')
    return s

def account():
    a=_read(ACCOUNT,None);sec=_read(SECRETS,{});st=settings()
    return {'linked':bool(a),**(a or {}),'has_api_key':bool(sec.get('api_key')),'has_auth_code':bool(sec.get('auth_code')),
            'settings':st,'watcher':{k:v for k,v in WATCH.items() if k!='thread'},'sharecodes':_read(CODES,{'codes':[]})['codes'][-30:]}

def settings():
    s=_read(SETTINGS,{});return {'replays_dir':s.get('replays_dir',DEFAULT_REPLAYS),'auto_import':bool(s.get('auto_import',True)),'known_code':s.get('known_code','')}

def save_settings(raw):
    if not isinstance(raw,dict):raise ValueError('无效设置')
    s=_read(SETTINGS,{})
    if 'replays_dir' in raw:
        p=str(raw['replays_dir']).strip()
        if len(p)>400 or not p:raise ValueError('回放目录无效')
        s['replays_dir']=p
    if 'auto_import' in raw:s['auto_import']=raw['auto_import'] is True
    if 'known_code' in raw:
        c=str(raw['known_code']).strip()
        if c and not re.fullmatch(r'CSGO(-[A-Za-z0-9]{5}){5}',c):raise ValueError('分享码格式应为 CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx')
        s['known_code']=c
    _write(SETTINGS,s)
    sec=_read(SECRETS,{})
    if 'api_key' in raw:
        k=str(raw['api_key']).strip()
        if k and not re.fullmatch(r'[0-9A-Fa-f]{32}',k):raise ValueError('Steam Web API Key 应为 32 位十六进制')
        sec['api_key']=k
    if 'auth_code' in raw:
        c=str(raw['auth_code']).strip()
        if c and not re.fullmatch(r'[0-9A-Za-z]{4}-[0-9A-Za-z]{5}-[0-9A-Za-z]{4}',c):raise ValueError('比赛历史验证码格式应为 xxxx-xxxxx-xxxx')
        sec['auth_code']=c
    _write(SECRETS,sec)
    return account()

def link_manual(steamid):
    sid=valid_steamid(steamid);_write(ACCOUNT,{'steamid':sid,'linked_at':time.time(),'via':'manual','verified':False});refresh_profile();return account()

def unlink():
    for p in (ACCOUNT,):
        if p.exists():p.unlink()
    return account()

# ---------------------------------------------------------------- Steam OpenID
def openid_start():
    state=secrets.token_hex(16)
    with LOCK:
        for k in [k for k,v in PENDING.items() if time.time()-v>600]:PENDING.pop(k,None)
        PENDING[state]=time.time()
    q={'openid.ns':'http://specs.openid.net/auth/2.0','openid.mode':'checkid_setup','openid.return_to':f'{ORIGIN}/auth/steam/return?state={state}',
       'openid.realm':ORIGIN,'openid.identity':'http://specs.openid.net/auth/2.0/identifier_select','openid.claimed_id':'http://specs.openid.net/auth/2.0/identifier_select'}
    return OPENID+'?'+urllib.parse.urlencode(q)

def openid_return(params,transport=None):
    """Verify the assertion with Steam itself (check_authentication); accept only our own single-use state."""
    one=lambda k:(params.get(k) or [''])[0]
    state=one('state')
    with LOCK:started=PENDING.pop(state,None)
    if not started or time.time()-started>600:raise ValueError('登录请求已过期，请重新关联')
    if one('openid.mode')!='id_res' or not one('openid.return_to').startswith(f'{ORIGIN}/auth/steam/return?state={state}'):raise ValueError('Steam 返回内容无效')
    m=re.fullmatch(r'https://steamcommunity\.com/openid/id/(7656119\d{10})',one('openid.claimed_id'))
    if not m:raise ValueError('未取得 SteamID')
    body={k:v[0] for k,v in params.items() if k.startswith('openid.')};body['openid.mode']='check_authentication'
    with httpx.Client(timeout=15,transport=transport) as c:r=c.post(OPENID,data=body)
    if r.status_code!=200 or 'is_valid:true' not in r.text:raise ValueError('Steam 未确认此次登录')
    _write(ACCOUNT,{'steamid':m.group(1),'linked_at':time.time(),'via':'steam_openid','verified':True})
    refresh_profile();return m.group(1)

# ---------------------------------------------------------------- Steam Web API (user's own key)
def _key():return _read(SECRETS,{}).get('api_key')

def refresh_profile(transport=None):
    a=_read(ACCOUNT,None);k=_key()
    if not a or not k:return None
    try:
        with httpx.Client(timeout=15,transport=transport) as c:
            r=c.get('https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/',params={'key':k,'steamids':a['steamid']})
        p=(r.json().get('response',{}).get('players') or [None])[0]
        if p:a.update(persona=p.get('personaname'),avatar=p.get('avatarfull') or p.get('avatarmedium'),profile_url=p.get('profileurl'),profile_checked=time.time());_write(ACCOUNT,a)
        return p
    except (httpx.HTTPError,ValueError):return None

ALPHABET='ABCDEFGHJKLMNOPQRSTUVWXYZabcdefhijkmnopqrstuvwxyz23456789'
def decode_sharecode(code):
    """CSGO-xxxxx-… → match id / outcome id / token (public base-57 encoding)."""
    s=code.replace('CSGO','').replace('-','');n=0
    for ch in reversed(s):n=n*57+ALPHABET.index(ch)
    b=n.to_bytes(18,'big')[::-1]
    return {'match_id':str(int.from_bytes(b[0:8],'little')),'outcome_id':str(int.from_bytes(b[8:16],'little')),'token':int.from_bytes(b[16:18],'little')}

def check_sharecodes(transport=None,limit=20):
    a=_read(ACCOUNT,None);sec=_read(SECRETS,{});st=_read(SETTINGS,{})
    if not a:raise ValueError('请先关联 Steam 账号')
    if not sec.get('api_key') or not sec.get('auth_code') or not st.get('known_code'):raise ValueError('需要 Steam Web API Key、比赛历史验证码和一个已知分享码')
    data=_read(CODES,{'codes':[]});known=st['known_code'];found=[]
    with httpx.Client(timeout=15,transport=transport) as c:
        for _ in range(limit):
            r=c.get('https://api.steampowered.com/ICSGOPlayers_730/GetNextMatchSharingCode/v1',params={'key':sec['api_key'],'steamid':a['steamid'],'steamidkey':sec['auth_code'],'knowncode':known})
            if r.status_code==202:break
            if r.status_code==403:raise ValueError('Steam 拒绝：请检查 API Key 与比赛历史验证码')
            if r.status_code!=200:raise ValueError(f'Steam 返回 HTTP {r.status_code}')
            nxt=r.json().get('result',{}).get('nextcode')
            if not nxt or nxt=='n/a':break
            row={'code':nxt,'found_at':time.time(),**decode_sharecode(nxt)};found.append(row);data['codes'].append(row);known=nxt
    st['known_code']=known;_write(SETTINGS,st);_write(CODES,data)
    return {'found':found,'known_code':known,'note':'Valve 不允许在没有游戏客户端的情况下下载天梯 demo：请在 CS2「观战 → 你的比赛」中下载，下载完成后会自动导入。'}

# ---------------------------------------------------------------- replays folder watcher
def scan_once():
    st=settings();folder=Path(st['replays_dir'])
    WATCH['last_scan']=time.time()
    if not folder.is_dir():WATCH['last_error']='回放目录不存在（在 CS2 中下载第一场 demo 后会创建）';return {'imported':0,'pending':0}
    seen=_read(IMPORTS,{'files':{}});pending=0;imported=0
    for f in sorted(folder.glob('*.dem'),key=lambda p:p.stat().st_mtime):
        stt=f.stat();key=f'{f.name}|{stt.st_size}|{stt.st_mtime_ns}'
        if key in seen['files']:continue
        if time.time()-stt.st_mtime<30:pending+=1;continue  # still downloading / extracting
        try:res=dr.import_local(f,kind='player')
        except RuntimeError:pending+=1;break           # parser busy: next scan
        except (ValueError,OSError) as e:seen['files'][key]={'error':str(e)[:120]};continue
        seen['files'][key]={'match':res['id'],'at':time.time()};imported+=1;WATCH['imported']+=1;_write(IMPORTS,seen);break  # one at a time
    _write(IMPORTS,seen);WATCH['last_error']=None
    return {'imported':imported,'pending':pending}

def start_watcher(interval=60):
    if WATCH['thread'] and WATCH['thread'].is_alive():return
    def run():
        while True:
            try:
                if settings()['auto_import']:scan_once()
            except Exception as e:WATCH['last_error']=type(e).__name__
            time.sleep(interval)
    WATCH['thread']=threading.Thread(target=run,daemon=True,name='replays-watcher');WATCH['thread'].start()

# ---------------------------------------------------------------- career statistics
def _match_players(mid):
    p=dr.folder(mid)/'players.json'
    if not p.exists():return {}
    return {v.get('steamid'):k for k,v in _read(p,{'players':{}})['players'].items()}

def players_index():
    from .demo_workbench import catalog
    out={}
    for m in catalog():
        p=_read(dr.folder(m['id'])/'players.json',{'players':{}})['players']
        for pid,v in p.items():
            sid=v.get('steamid')
            if not sid:continue
            row=out.setdefault(sid,{'steamid':sid,'name':v.get('name'),'matches':0});row['matches']+=1;row['name']=v.get('name') or row['name']
    return sorted(out.values(),key=lambda r:(-r['matches'],(r['name'] or '').lower()))

def profile(steamid):
    from .demo_workbench import catalog
    from .player_stats import match_stats,finish,_blank
    sid=valid_steamid(steamid);rows=[];tot=_blank('total','',None);per_map={};name=None
    for m in catalog():
        pid=_match_players(m['id']).get(sid)
        if not pid:continue
        try:st=match_stats(m['id'])
        except (ValueError,OSError):continue
        me=next((p for p in st['players'] if p['id']==pid),None)
        if not me:continue
        name=me['name'];state=dr.state(m['id']);sc=st['final_score'];own=sc.get(me['team']);opp=next((v for k,v in sc.items() if k!=me['team']),None)
        result='W' if own is not None and opp is not None and own>opp else 'L' if own is not None and opp is not None and own<opp else 'T'
        rows.append({'match':m['id'],'file':m['name'],'map':m['map'],'played_at':state.get('played_at') or state.get('created_at'),'group':m['group'],'team':me['team'],
                     'score':[own,opp],'result':result,'player_id':pid,**{k:me[k] for k in ('kills','deaths','assists','adr','kast','hs_pct','rating1','rating2_approx','rounds','opening_kills','opening_deaths','kd')}})
        for acc in (tot,per_map.setdefault(m['map'],_blank(m['map'],'',m['map']))):
            for k in ('rounds','kills','deaths','assists','flash_assists','damage','utility_damage','headshots','kast_rounds','survived','traded','opening_kills','opening_deaths','wallbangs','smoke_kills'):acc[k]+=me[k]
            for k,v in me['multi'].items():acc['multi'][int(k)]+=v
    rows.sort(key=lambda r:r['played_at'] or 0)
    summary=finish(tot) if rows else None
    maps=[{**finish(v),'map':k,'matches':sum(1 for r in rows if r['map']==k),'wins':sum(1 for r in rows if r['map']==k and r['result']=='W')} for k,v in per_map.items()]
    acc=_read(ACCOUNT,None)
    return {'steamid':sid,'name':name,'is_me':bool(acc and acc.get('steamid')==sid),'matches':rows,'summary':summary,'maps':maps,
            'wins':sum(r['result']=='W' for r in rows),'losses':sum(r['result']=='L' for r in rows),
            'notes':['Rating 1.0 为 HLTV 公开公式；Rating 2.0≈ 为社区近似公式，非 HLTV 官方数值','统计只来自本机已解析的 demo']}
