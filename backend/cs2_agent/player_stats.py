"""Per-match player statistics from the 16 Hz replay track (real kill / damage / assist events).

ADR caps each hit at the victim's remaining health (raw dmg_health can exceed it), and ignores team damage.
KAST counts a round when the player killed, assisted, survived, or was traded within 5 s.
Rating 1.0 uses HLTV's published formula; "Rating 2.0≈" is a community approximation, not HLTV's official number.
"""
import json
from . import demo_review as dr

VERSION=1;TRADE_WINDOW=5.0
UTILITY=('hegrenade','inferno','molotov','incgrenade')

def replay_rounds(mid):
    d=dr.folder(mid)/'replay-v1'
    rows=[]
    for p in d.glob('round-*.json'):
        rows.append(json.loads(p.read_text(encoding='utf-8')))
    return sorted(rows,key=lambda r:r['number'])

def _blank(pid,side,name):
    return {'id':pid,'name':name or pid,'side_first':side,'rounds':0,'kills':0,'deaths':0,'assists':0,'flash_assists':0,'damage':0,'utility_damage':0,
            'headshots':0,'kast_rounds':0,'survived':0,'traded':0,'opening_kills':0,'opening_deaths':0,'multi':{2:0,3:0,4:0,5:0},'wallbangs':0,'smoke_kills':0}

def round_stats(r,acc,names):
    sides={pid:q['side'] for pid,q in r['players'].items()}
    for pid,side in sides.items():
        if pid not in acc:acc[pid]=_blank(pid,side,names.get(pid))
        acc[pid]['rounds']+=1
    hp={pid:100 for pid in sides};kills={pid:0 for pid in sides};assisted=set();traded=set();deaths=[];first=True
    for e in sorted(r['events'],key=lambda e:e['t']):
        if e['k']=='player_hurt':
            v,a=e.get('a'),e.get('by')
            if v not in hp:continue
            dealt=min(e.get('d') or 0,hp[v])
            hp[v]=e['h'] if isinstance(e.get('h'),(int,float)) else max(0,hp[v]-dealt)
            if a in sides and a!=v and sides[a]!=sides[v]:
                acc[a]['damage']+=dealt
                if (e.get('w') or '') in UTILITY:acc[a]['utility_damage']+=dealt
        elif e['k']=='player_death':
            v,a,ast=e.get('a'),e.get('by'),e.get('as')
            if v not in sides:continue
            acc[v]['deaths']+=1;hp[v]=0
            enemy_kill=a in sides and a!=v and sides[a]!=sides[v]
            if enemy_kill:
                acc[a]['kills']+=1;kills[a]+=1
                if e.get('hs'):acc[a]['headshots']+=1
                if e.get('wb'):acc[a]['wallbangs']+=1
                if e.get('ts'):acc[a]['smoke_kills']+=1
                if first:acc[a]['opening_kills']+=1;acc[v]['opening_deaths']+=1;first=False
                # trade: this kill avenges a teammate killed by the victim within the window
                for t0,dead,killer in deaths:
                    if killer==v and sides.get(dead)==sides[a] and e['t']-t0<=TRADE_WINDOW:traded.add(dead)
                deaths.append((e['t'],v,a))
            if ast in sides and ast!=a and ast!=v and sides[ast]!=sides[v]:
                acc[ast]['assists']+=1;assisted.add(ast)
                if e.get('fa'):acc[ast]['flash_assists']+=1
    for pid in sides:
        q=r['players'][pid];last=next((h for h in reversed(q['hp']) if h is not None),0)
        survived=last>0
        if survived:acc[pid]['survived']+=1
        if pid in traded:acc[pid]['traded']+=1
        if kills[pid]>0 or pid in assisted or survived or pid in traded:acc[pid]['kast_rounds']+=1
        if kills[pid]>=2:acc[pid]['multi'][min(5,kills[pid])]+=1

def finish(p):
    n=max(1,p['rounds']);kpr=p['kills']/n;dpr=p['deaths']/n;apr=p['assists']/n;adr=p['damage']/n;kast=100*p['kast_rounds']/n
    m=p['multi'];multi=(p['kills']-sum(k*v for k,v in m.items())+4*m[2]+9*m[3]+16*m[4]+25*m[5])/n
    rating1=(kpr/0.679+0.7*(n-p['deaths'])/n/0.317+multi/1.277)/2.7
    impact=2.13*kpr+0.42*apr-0.41
    rating2=0.0073*kast+0.3591*kpr-0.5329*dpr+0.2372*impact+0.0032*adr+0.1587
    return {**p,'multi':{str(k):v for k,v in m.items()},'kpr':round(kpr,3),'dpr':round(dpr,3),'adr':round(adr,1),'kast':round(kast,1),
            'hs_pct':round(100*p['headshots']/max(1,p['kills']),1),'kd':round(p['kills']/max(1,p['deaths']),2),'kd_diff':p['kills']-p['deaths'],
            'impact':round(impact,2),'rating1':round(rating1,2),'rating2_approx':round(rating2,2)}

def match_stats(mid):
    """Cached per replay-track version; recomputed whenever the replay files change."""
    d=dr.folder(mid);idx=d/'replay-v1'/'index.json'
    if not idx.exists():raise ValueError('replay track missing')
    stamp=[VERSION,idx.stat().st_mtime_ns];cache=d/'stats-v1.json'
    if cache.exists():
        try:
            c=json.loads(cache.read_text(encoding='utf-8'))
            if c.get('stamp')==stamp:return c['data']
        except (OSError,ValueError):pass
    from .demo_workbench import player_names
    names=player_names(mid);rounds=replay_rounds(mid);acc={}
    for r in rounds:round_stats(r,acc,names)
    steam={}
    pj=d/'players.json'
    if pj.exists():steam={k:v.get('steamid') for k,v in json.loads(pj.read_text(encoding='utf-8'))['players'].items()}
    first=rounds[0] if rounds else {};last=rounds[-1] if rounds else {}
    final={}
    for side in ('T','CT'):
        tm=(last.get('teams') or {}).get(side) or {}
        if tm.get('name') is not None:final[tm['name']]=(tm.get('score') or 0)+(1 if last.get('winner')==side else 0)
    team_of={pid:((first.get('teams') or {}).get(q['side']) or {}).get('name') for pid,q in (first.get('players') or {}).items()}
    players=[{**finish(p),'steamid':steam.get(p['id']),'team':team_of.get(p['id'])} for p in acc.values()]
    players.sort(key=lambda p:(p['team'] or '',-p['rating2_approx']))
    data={'match':mid,'rounds':len(rounds),'final_score':final,'players':players,
          'notes':['ADR 按受害者剩余血量截断，不计队友伤害','KAST：击杀、助攻、存活或 5 秒内被补枪','Rating 1.0 为 HLTV 公开公式；Rating 2.0≈ 为社区近似公式，非 HLTV 官方数值',
                   '只统计成功解析的回合；跳过的回合不计入']}
    try:
        tmp=cache.with_suffix('.tmp');tmp.write_text(json.dumps({'stamp':stamp,'data':data},ensure_ascii=False),encoding='utf-8');tmp.replace(cache)
    except OSError:pass
    return data
