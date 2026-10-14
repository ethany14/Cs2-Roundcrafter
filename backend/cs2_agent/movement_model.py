"""Local inference for the small movement-prediction GRU (outputs/movement/comparison, numeric arm).

Model: 3-seed ensemble trained 2026-10-13 on 77 pro demos (19/5/6 series split). It predicts the
player's XY displacement at +0.5 / +1 / +2 s from the last 2 s of the player's own state plus
player-known context. It is a behaviour model of what pros did, not an optimal route.

Inputs are rebuilt from the .dem exactly like experiments/movement/extract.cjs (0.5 s frames at 64 tick,
yaw-relative coordinates in 250-unit steps, rounded to 3 decimals as in prepare_comparison.py). Missing
or out-of-distribution inputs raise MovementInputError; nothing is zero-filled. The real future track is
read separately, after prediction, and is only used for display and error measurement.
"""
import hashlib,json,math,subprocess
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import demo_review as dr

ROOT=Path(__file__).resolve().parents[2]
MODEL_DIR=ROOT/'outputs/movement/comparison'
SEEDS=(7,17,29)
SCRIPT=ROOT/'experiments/movement/window.cjs'
DATASET=ROOT/'data/movement/dataset.json'
RATE=64;STEP=32;UNIT=250.0
HORIZONS=(0.5,1.0,2.0)
FUTURE=(1,2,4)            # in 0.5 s steps; matches seq indices 5,6,8 in extract.cjs
MAPS=('de_ancient','de_anubis','de_cache','de_dust2','de_inferno','de_mirage','de_nuke')  # every map in all three splits
FIELDS=('X','Y','Z','yaw','pitch','health','armor_value','duck_amount','flash_duration')

class MovementInputError(ValueError):
    """Required input missing or outside the training conditions. `code` is stable for the UI."""
    def __init__(self,code,message):super().__init__(message);self.code=code

def _finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

# ---------- model ----------
def checkpoints():return [MODEL_DIR/f'numeric-{s}.pt' for s in SEEDS]

def available():
    missing=[str(p.relative_to(ROOT)) for p in checkpoints()+[MODEL_DIR/'metrics.json',MODEL_DIR/'protocol.json'] if not p.exists()]
    try:import torch  # noqa: F401
    except ImportError:missing.append('python package: torch')
    return missing

@lru_cache(maxsize=1)
def _ensemble():
    missing=available()
    if missing:raise MovementInputError('model_missing','缺少模型文件或依赖：'+', '.join(missing))
    import torch
    from torch import nn
    class Numeric(nn.Module):  # experiments/movement/compare.py Net('numeric')
        def __init__(self):super().__init__();self.gru=nn.GRU(8,48,batch_first=True);self.head=nn.Sequential(nn.Linear(64,64),nn.GELU(),nn.Linear(64,6))
        def forward(self,h,c):return self.head(torch.cat((self.gru(h)[1][-1],c),1))
    nets=[]
    for p in checkpoints():
        ck=torch.load(p,map_location='cpu',weights_only=True)
        if ck.get('arm')!='numeric':raise MovementInputError('model_mismatch',f'{p.name} 不是 numeric 模型')
        m=Numeric();m.load_state_dict(ck['state_dict']);m.eval();nets.append(m)
    return nets

def predict_local(h,c):
    """h[n,5,8], c[n,16] -> mean of the three seeds, shape [n,6] in 250-unit local coordinates."""
    import torch
    h=torch.as_tensor(np.asarray(h,np.float32));c=torch.as_tensor(np.asarray(c,np.float32))
    with torch.no_grad():return np.mean([m(h,c).numpy() for m in _ensemble()],0)

@lru_cache(maxsize=1)
def info():
    metrics=json.loads((MODEL_DIR/'metrics.json').read_text(encoding='utf-8'))
    o=metrics['overall'];moving=metrics['moving_only']
    return {'name':'movement-numeric-gru','version':'comparison-2026-10-13 (numeric arm, seeds 7/17/29)',
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in checkpoints()},
        'inputs':'2 s own history at 0.5 s (yaw-relative position, height, yaw change, pitch, crouch, flash) + hp, armor, side, round time, alive counts, bomb plant, two nearest teammates',
        'outputs':'XY displacement at +0.5 / +1 / +2 s; height and actions are not predicted',
        'maps':list(MAPS),'tick_rate':RATE,
        'test':{k:{'ADE':round(o[k]['ADE'],1),'FDE_2s':round(o[k]['FDE_2s'],1)} for k in ('numeric','tuned_velocity','stationary')},
        'test_moving':{k:round(moving[k]['ADE'],1) for k in ('numeric','tuned_velocity')},
        'velocity_factor':metrics['tuned_velocity_factor'],
        'not_shown':'Shooting/utility heads (joint model) are not exposed: fire AP 0.069 is below the repeat-last-action baseline 0.161 and utility classes have 0-23 test positives.'}

# ---------- demo access ----------
def _node(*args):
    r=subprocess.run(['node',str(SCRIPT),*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if r.returncode:raise MovementInputError('parse_failed','demo 读取失败：'+(r.stderr.strip().splitlines() or ['?'])[-1][:200])
    return json.loads(r.stdout)

def _demo(mid):
    from .demo_workbench import demo_path
    try:p=demo_path(mid)
    except Exception:p=None
    if not p or not Path(p).is_file():raise MovementInputError('demo_missing','找不到这场比赛的 .dem 文件，无法重建模型输入')
    return Path(p)

def rounds(mid):
    """Round boundaries/plants, cached per match (cheap to rebuild)."""
    f=dr.folder(mid)/'movement-v1/rounds.json'
    if f.exists():return json.loads(f.read_text(encoding='utf-8'))
    data=_node('rounds',_demo(mid));f.parent.mkdir(exist_ok=True);f.write_text(json.dumps(data),encoding='utf-8');return data

def steamids(mid):
    p=dr.folder(mid)/'players.json'
    if not p.exists():
        sha=dr.state(mid).get('sha256')
        for other in dr.library():
            q=dr.folder(other['id'])/'players.json'
            if sha and other.get('sha256')==sha and q.exists():p=q;break
    if not p.exists():raise MovementInputError('players_missing','缺少玩家映射 players.json，请先重建回放数据')
    return {k:v['steamid'] for k,v in json.loads(p.read_text(encoding='utf-8'))['players'].items()}

@lru_cache(maxsize=1)
def _dataset():
    if not DATASET.exists():return {}
    split=json.loads((MODEL_DIR/'protocol.json').read_text(encoding='utf-8'))['split']
    return {d['sha256']:split.get(d['group'],'unused') for d in json.loads(DATASET.read_text(encoding='utf-8'))}

def training_split(mid):
    """train / validation / test (already inspected) / not_in_dataset — error on train demos is optimistic."""
    return _dataset().get(dr.state(mid).get('sha256'),'not_in_dataset')

# ---------- features (port of extract.cjs; history only) ----------
def _local(dx,dy,c,s):return ((dx*c+dy*s)/UNIT,(-dx*s+dy*c)/UNIT)

def features(history,now,start,tick,plants):
    """history: the player's rows at tick-128..tick (5, oldest first); now: every player row at `tick`.
    Returns (h[5][8], c[16]) rounded like the training data. Raises MovementInputError instead of filling gaps."""
    if len(now)!=10 or len({r['steamid'] for r in now})!=10:
        raise MovementInputError('not_ten_players',f'此刻 demo 中有 {len(now)} 名玩家；模型只在 10 人对局状态上训练')
    r=history[-1]
    for i,x in enumerate(history):
        when=f'{(i-4)*0.5:+.1f}s'
        if x is None:raise MovementInputError('history_missing',f'{when} 时刻缺少该玩家数据')
        if not x.get('is_alive'):raise MovementInputError('not_alive',f'{when} 时刻玩家未存活；需要完整 2 秒存活历史')
        if x.get('team_num')!=r['team_num'] or x.get('total_rounds_played')!=r['total_rounds_played']:raise MovementInputError('history_crosses_round','历史窗口跨越了换边或回合边界')
        bad=[k for k in FIELDS if not _finite(x.get(k))]
        if bad:raise MovementInputError('field_missing',f'{when} 时刻缺少字段 {",".join(bad)}')
    if r['team_num'] not in (2,3):raise MovementInputError('not_playing','该玩家不在 T/CT 阵营')
    for a,b in zip(history,history[1:]):
        if math.hypot(b['X']-a['X'],b['Y']-a['Y'])>200:raise MovementInputError('teleport','历史中出现超过 200 单位的瞬移（回合重置或数据跳变）')
    ang=math.radians(r['yaw']);c,s=math.cos(ang),math.sin(ang)
    h=[[*_local(x['X']-r['X'],x['Y']-r['Y'],c,s),(x['Z']-r['Z'])/UNIT,math.sin(math.radians(x['yaw']-r['yaw'])),math.cos(math.radians(x['yaw']-r['yaw'])),x['pitch']/90,x['duck_amount'],min(x['flash_duration'],5)/5] for x in history]
    team=[x for x in now if x.get('is_alive') and x.get('team_num')==r['team_num']]
    mates=sorted([x for x in team if x['steamid']!=r['steamid'] and _finite(x.get('X')) and _finite(x.get('Y'))],key=lambda x:math.hypot(x['X']-r['X'],x['Y']-r['Y']))[:2]
    ctx=[r['health']/100,r['armor_value']/100,1 if r['team_num']==3 else 0,(tick-start)/RATE/120,len(team)/5,len([x for x in now if x.get('is_alive') and x.get('team_num')!=r['team_num']])/5]
    plant=next((p for p in plants if start<=p<=tick),None);ctx+=[1 if plant is not None else 0,(tick-plant)/RATE/40 if plant is not None else 0]
    for i in range(2):
        m=mates[i] if i<len(mates) else None
        if m and not _finite(m.get('Z')):raise MovementInputError('field_missing','队友高度缺失')
        ctx+=[*[max(-12,min(12,v)) for v in _local(m['X']-r['X'],m['Y']-r['Y'],c,s)],(m['Z']-r['Z'])/UNIT,1] if m else [0,0,0,0]  # absent teammate = training encoding (present flag 0)
    return np.round(np.array(h,np.float64),3).tolist(),np.round(np.array(ctx,np.float64),3).tolist()

def to_world(local,origin,yaw):
    """local [3,2] (250-unit forward/right) -> world XY points."""
    ang=math.radians(yaw);c,s=math.cos(ang),math.sin(ang)
    return [[origin[0]+(f*c-r*s)*UNIT,origin[1]+(f*s+r*c)*UNIT] for f,r in local]

# ---------- public entry ----------
def predict(mid,round_number,seconds,player):
    """Predict for match `mid`, replay round `round_number`, `seconds` after freeze end, pseudonym `player` (P1..)."""
    if not isinstance(player,str) or not player.startswith('P'):raise MovementInputError('bad_player','无效玩家')
    from .demo_workbench import replay_round
    rnd=replay_round(mid,round_number)
    meta=rounds(mid)
    if meta.get('map') not in MAPS:raise MovementInputError('unsupported_map',f'模型未在 {meta.get("map")} 上训练，支持：{", ".join(MAPS)}')
    if not meta.get('rate') or abs(meta['rate']-RATE)>.1:raise MovementInputError('unsupported_tickrate',f'demo tick rate {meta.get("rate")}，模型只支持 64')
    span=next((x for x in meta['rounds'] if x['start']==rnd['start_tick']),None)
    if not span:raise MovementInputError('round_mismatch','回放回合与 demo 回合边界对不上')
    tick=span['start']+round(float(seconds)*RATE/STEP)*STEP
    if tick-4*STEP<span['start']:raise MovementInputError('insufficient_history','回合开始后 2 秒内没有完整历史，请选择更晚的时刻')
    if tick>=span['end']:raise MovementInputError('after_round_end','所选时刻已在回合结束之后')
    sid=steamids(mid).get(player)
    if not sid:raise MovementInputError('bad_player','找不到该玩家的 SteamID 映射')
    past=[tick+(i-4)*STEP for i in range(5)]
    rows=_node('ticks',_demo(mid),','.join(map(str,past)))['rows']
    pick=lambda t:next((x for x in rows.get(str(t),[]) if x['steamid']==sid),None)
    history=[pick(t) for t in past]
    h,c=features(history,rows.get(str(tick),[]),span['start'],tick,span['plants'])
    local=predict_local([h],[c])[0].reshape(3,2)
    now=history[-1];origin=[now['X'],now['Y'],now['Z']]
    vel=-np.array(h[-2][:2]);k=info()['velocity_factor']
    out={'model':info()['name'],'version':info()['version'],'label':'模型预测（职业行为统计，不是最优路线）',
         'match':mid,'player':player,'round':int(round_number),'tick':tick,'seconds':(tick-span['start'])/RATE,'map':meta['map'],
         'training_split':training_split(mid),'horizons':list(HORIZONS),
         'start':origin,'yaw':now['yaw'],
         'history':[[x['X'],x['Y'],x['Z']] for x in history],
         'predicted':[[*p,origin[2]] for p in to_world(local.tolist(),origin,now['yaw'])],
         'baseline_velocity':[[*p,origin[2]] for p in to_world((vel*np.array(FUTURE)[:,None]*k).tolist(),origin,now['yaw'])],
         'height':'not_predicted: predicted points inherit the start height/floor',
         'inputs':{'h':h,'c':c}}
    out['actual']=actual(mid,span,tick,sid,now['team_num'])  # read AFTER prediction; display/evaluation only
    out['errors']=errors(out)
    return out

def actual(mid,span,tick,sid,team):
    """Real future positions at +0.5/+1/+2 s (None where dead, past round end or discontinuous)."""
    ticks=[tick+k*STEP for k in (1,2,3,4)]
    ok=[t for t in ticks if t<span['end']]
    rows=_node('ticks',_demo(mid),','.join(map(str,ok)))['rows'] if ok else {}
    seq=[next((x for x in rows.get(str(t),[]) if x['steamid']==sid),None) for t in ticks]
    pts=[];prev=None;broken=False
    for i,x in enumerate(seq):
        good=x is not None and x.get('is_alive') and x.get('team_num')==team and _finite(x.get('X')) and _finite(x.get('Y'))
        if good and prev is not None and math.hypot(x['X']-prev['X'],x['Y']-prev['Y'])>200:broken=True
        if not good or broken:broken=True;pts.append(None)
        else:pts.append([x['X'],x['Y'],x['Z']]);prev=x
    return {'track':pts,'at_horizons':[pts[k-1] for k in FUTURE]}

def errors(res):
    def e(pred):return [round(math.hypot(p[0]-a[0],p[1]-a[1]),1) if a else None for p,a in zip(pred,res['actual']['at_horizons'])]
    m,v=e(res['predicted']),e(res['baseline_velocity']);s=e([res['start']]*3)
    full=all(x is not None for x in m)
    return {'model':m,'velocity':v,'stationary':s,'ADE':round(sum(m)/3,1) if full else None,'velocity_ADE':round(sum(v)/3,1) if full else None,'stationary_ADE':round(sum(s)/3,1) if full else None}
